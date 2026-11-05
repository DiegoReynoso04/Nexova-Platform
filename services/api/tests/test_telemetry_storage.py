"""Lo que el colector guarda en `telemetry_events` (ticket de almacenamiento).

Ningún test conecta con Supabase. `insert_statement` se ejecuta en SQLite y se
compila con el dialecto de PostgreSQL. Ver docs/telemetry/storage-analysis.md.
"""

import ast
import json
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.auth.security import TokenClaims, create_access_token
from app.modules.telemetry import collector
from app.modules.telemetry.allowlists import EVENT_ALLOWLISTS
from app.modules.telemetry.catalog import FRONTEND_EVENT_TYPES
from app.modules.telemetry.collector import EVENTS_PER_WINDOW, EventRateLimiter, build_row, insert_statement
from app.modules.telemetry.models import TelemetryEventRecord, TelemetryService
from app.modules.telemetry.schemas import TelemetryEvent

from .support import APP_DIR, authorize, capture_logs, make_client
from .telemetry_support import contract, contract_errors, envelope, plan_examples, storage_client

URL = "/telemetry/events"
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
DIMENSIONS = ("office", "product_id", "product_category", "programme_id", "quantity", "currency")


def outbound(**overrides: Any) -> dict[str, Any]:
    """`outbound_order_created` tal como lo envía el backoffice hoy: dos dimensiones en `null` (P1)."""
    properties = {
        "office": "valencia",
        "product_id": 7,
        "product_category": None,
        "programme_id": None,
        "quantity": 3,
        "currency": "EUR",
        "outbound_order_id": 88,
        "exit_type": "allocation",
        "stock_after": 6,
        "asset_category": "training_materials",
    }
    return envelope("outbound_order_created", properties=properties, **overrides)


class StorageCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = storage_client()
        self.addCleanup(self.client.auth_dir.cleanup)  # type: ignore[attr-defined]
        self.engine = self.client.app.state.inventory_engine  # type: ignore[attr-defined]

    def post(self, *events: Any, **kwargs: Any) -> dict[str, int]:
        response = self.client.post(URL, json={"events": list(events)}, **kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        result: dict[str, int] = response.json()
        return result

    def records(self) -> list[TelemetryEventRecord]:
        with Session(self.engine) as session:
            return list(session.scalars(select(TelemetryEventRecord)).all())

    def record(self, event_id: str) -> TelemetryEventRecord:
        return next(record for record in self.records() if record.event_id == UUID(event_id))


class MappingTests(StorageCase):
    def test_the_envelope_goes_to_the_eight_columns(self) -> None:
        sent = envelope(timestamp=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"))
        self.post(sent)
        stored = self.record(sent["eventId"])
        self.assertEqual(stored.event_type, "page_viewed")
        self.assertEqual(stored.service, "backoffice")
        self.assertEqual(stored.user_id, UUID(sent["userId"]))
        self.assertEqual(stored.session_id, UUID(sent["sessionId"]))
        self.assertEqual(stored.schema_version, "1.0.0")
        self.assertEqual(stored.tags, sent["properties"])
        self.assertEqual(stored.timestamp.replace(tzinfo=UTC), datetime.fromisoformat(sent["timestamp"]))

    def test_a_technical_and_a_business_event(self) -> None:
        business = outbound()
        technical = envelope("form_started", properties={"form": "inbound_order"})
        self.assertEqual(self.post(business, technical), {"received": 2, "stored": 2, "rejected": 0})
        self.assertEqual(self.record(technical["eventId"]).tags, {"form": "inbound_order"})
        self.assertEqual(self.record(business["eventId"]).tags, business["properties"])

    def test_the_briefing_dimensions_survive_and_nulls_are_kept(self) -> None:
        sent = outbound()
        self.post(sent)
        tags = self.record(sent["eventId"]).tags
        for key in DIMENSIONS:
            self.assertIn(key, tags)
        self.assertIsNone(tags["product_category"])
        self.assertIsNone(tags["programme_id"])

    def test_request_id_is_not_stored(self) -> None:
        sent = envelope()
        self.post(sent)
        self.assertNotIn("request_id", TelemetryEventRecord.__table__.columns)  # type: ignore[attr-defined]


class AllowlistTests(StorageCase):
    def test_an_extra_key_in_properties_is_dropped_and_the_event_kept(self) -> None:
        sent = envelope()
        clean = dict(sent["properties"])
        sent["properties"] |= {"email": "leak@example.invalid"}
        self.assertEqual(self.post(sent), {"received": 1, "stored": 1, "rejected": 0})
        self.assertEqual(self.record(sent["eventId"]).tags, clean)

    def test_a_missing_key_rejects_the_event(self) -> None:
        sent = outbound()
        del sent["properties"]["programme_id"]
        self.assertEqual(self.post(sent)["rejected"], 1)

    def test_a_value_out_of_its_enum_or_type_rejects_the_event(self) -> None:
        invalid = {"quantity": "3", "office": "madrid", "programme_id": "NOT A SLUG", "stock_after": -1, "product_id": True}
        for key, value in invalid.items():
            with self.subTest(key=key):
                sent = outbound()
                sent["properties"][key] = value
                self.assertEqual(self.post(sent)["rejected"], 1)
        self.assertEqual(self.records(), [])

    def test_office_and_currency_must_match(self) -> None:
        sent = outbound()
        sent["properties"]["currency"] = "USD"
        self.assertEqual(self.post(sent)["rejected"], 1)

    def test_every_key_of_the_15_events_is_really_checked(self) -> None:
        for example in plan_examples():
            allowlist = EVENT_ALLOWLISTS.get(example["event_type"])
            if allowlist is None:
                continue
            for key in allowlist.properties:
                with self.subTest(event_type=example["event_type"], key=key):
                    parsed = TelemetryEvent.model_validate(example | {"properties": example["properties"] | {key: {"not": "valid"}}})
                    self.assertIsNone(build_row(parsed, TelemetryService.BACKOFFICE, NOW))


class PoisonEventsTests(StorageCase):
    """C4: lo que pasa el modelo y haría fallar el único insert de todo el lote."""

    def test_impossible_dates_with_the_right_pattern(self) -> None:
        for timestamp in ("2026-13-45T99:99:99.000Z", "2026-02-30T10:00:00.000Z", "0000-01-01T00:00:00.000Z"):
            with self.subTest(timestamp=timestamp):
                self.assertEqual(self.post(envelope(timestamp=timestamp), envelope())["rejected"], 1)

    def post_raw(self, literal: str) -> dict[str, int]:
        inbound = {
            "office": "valencia", "product_id": 1, "product_category": None, "programme_id": None, "quantity": 1, "currency": "EUR",
            "inbound_order_id": 1, "unit_cost": "@@", "supplier_key": "a" * 64, "asset_category": "hardware",
        }  # fmt: skip
        body = json.dumps({"events": [envelope("inbound_order_created", properties=inbound), envelope()]}).replace('"@@"', literal)
        response = self.client.post(URL, content=body.encode(), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        result: dict[str, int] = response.json()
        return result

    def test_nan_and_infinity_reject_only_their_event(self) -> None:
        for literal in ("NaN", "Infinity", "-Infinity", "1e400"):
            with self.subTest(literal=literal):
                self.assertEqual(self.post_raw(literal), {"received": 2, "stored": 1, "rejected": 1})

    def test_a_nul_character_never_reaches_the_table(self) -> None:
        sent = envelope()
        sent["properties"]["\u0000key"] = "a\u0000b"
        bad_value = envelope()
        bad_value["properties"]["route_template"] = "/\u0000"
        self.assertEqual(self.post(sent, bad_value), {"received": 2, "stored": 1, "rejected": 1})
        self.assertNotIn("\\u0000", json.dumps(self.record(sent["eventId"]).tags))


class MixedBatchTests(StorageCase):
    def test_one_invalid_event_never_cancels_the_batch(self) -> None:
        extra_key = envelope()
        extra_key["properties"]["email"] = "leak@example.invalid"
        bad_route = envelope()
        bad_route["properties"]["route_template"] = "/ruta-inventada"
        batch = [
            envelope(),
            outbound(),
            extra_key,
            envelope(email="leak@example.invalid"),
            envelope("button_clicked"),
            envelope("direct_stock_edit_rejected"),
            envelope(timestamp="2026-11-04T12:00:00Z"),
            envelope(timestamp="2026-13-45T99:99:99.000Z"),
            bad_route,
            "no-soy-un-objeto",
        ]
        self.assertEqual(self.post(*batch), {"received": 10, "stored": 3, "rejected": 7})
        self.assertEqual(len(self.records()), 3)
        self.assertEqual(self.post(*batch), {"received": 10, "stored": 3, "rejected": 7})
        self.assertEqual(len(self.records()), 3)


class BulkInsertTests(StorageCase):
    def statements(self) -> list[tuple[str, bool]]:
        seen: list[tuple[str, bool]] = []

        def before(_conn: object, _cursor: object, statement: str, _params: object, _context: object, executemany: bool) -> None:
            if statement.startswith("INSERT"):
                seen.append((statement, executemany))

        event.listen(self.engine, "before_cursor_execute", before)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", before)
        return seen

    def test_one_statement_per_batch_and_not_an_executemany(self) -> None:
        seen = self.statements()
        self.post(*[envelope() for _ in range(20)])
        self.assertEqual(len(seen), 1)
        statement, executemany = seen[0]
        self.assertFalse(executemany)
        self.assertEqual(statement.count("(?, ?, ?, ?, ?, ?, ?, ?)"), 20)

    def test_no_statement_when_nothing_is_valid(self) -> None:
        seen = self.statements()
        self.assertEqual(self.post(envelope("button_clicked"), "x"), {"received": 2, "stored": 0, "rejected": 2})
        self.assertEqual(seen, [])

    def test_the_sql_of_postgresql(self) -> None:
        row = build_row(TelemetryEvent.model_validate(envelope()), TelemetryService.BACKOFFICE, NOW)
        assert row is not None
        sql = str(insert_statement([row, row]).compile(dialect=postgresql.dialect()))
        self.assertEqual(sql.count("INSERT INTO telemetry_events"), 1)
        self.assertTrue(sql.endswith("ON CONFLICT (event_id) DO NOTHING"))
        self.assertIn("::JSONB", sql)


class DeduplicationTests(StorageCase):
    def test_a_retry_gives_the_same_answer_and_no_new_rows(self) -> None:
        batch = [envelope(), envelope()]
        first = self.post(*batch)
        self.assertEqual(first, {"received": 2, "stored": 2, "rejected": 0})
        self.assertEqual(self.post(*batch), first)
        self.assertEqual(len(self.records()), 2)

    def test_a_repeated_event_inside_a_batch(self) -> None:
        sent = envelope()
        self.assertEqual(self.post(sent, sent), {"received": 2, "stored": 2, "rejected": 0})
        self.assertEqual(len(self.records()), 1)

    def test_the_first_copy_wins(self) -> None:
        sent = envelope()
        self.post(sent)
        changed = dict(sent, properties=sent["properties"] | {"entry": "in_app_navigation"})
        self.post(changed)
        self.assertEqual(self.record(sent["eventId"]).tags["entry"], sent["properties"]["entry"])


class IdentityTests(StorageCase):
    def token(self) -> tuple[dict[str, str], str]:
        """La cabecera de un token válido, sin dejarla fija en el cliente, y el id del usuario."""
        user = authorize(self.client)
        del self.client.headers["Authorization"]
        settings = self.client.app.state.settings  # type: ignore[attr-defined]
        return {"Authorization": f"Bearer {create_access_token(settings, str(user.id))}"}, str(user.id)

    def test_the_token_replaces_what_the_client_declares(self) -> None:
        headers, user_id = self.token()
        sent = envelope()
        self.post(sent, headers=headers)
        stored = self.record(sent["eventId"])
        self.assertEqual(stored.user_id, UUID(user_id))
        self.assertNotEqual(stored.session_id, UUID(sent["sessionId"]))
        self.assertIsNotNone(stored.session_id)

    def test_without_a_token_the_declared_ids_stay(self) -> None:
        sent = envelope()
        self.post(sent)
        self.assertEqual(self.record(sent["eventId"]).user_id, UUID(sent["userId"]))

    def test_an_invalid_token_changes_nothing(self) -> None:
        sent = envelope()
        self.post(sent, headers={"Authorization": "Bearer not-a-jwt"})
        self.assertEqual(self.record(sent["eventId"]).user_id, UUID(sent["userId"]))

    def test_a_business_event_needs_an_identity(self) -> None:
        anonymous = outbound(userId=None, sessionId=None)
        self.assertEqual(self.post(anonymous)["rejected"], 1)
        headers, _ = self.token()
        self.assertEqual(self.post(anonymous, headers=headers)["stored"], 1)

    def test_a_token_whose_subject_is_not_a_uuid_is_ignored(self) -> None:
        sent = TelemetryEvent.model_validate(envelope())
        row = build_row(sent, TelemetryService.BACKOFFICE, NOW, TokenClaims(sub="not-a-uuid", sid=None))
        assert row is not None
        self.assertEqual(row["user_id"], UUID(sent.userId or ""))


class TimestampTests(unittest.TestCase):
    def moment_for(self, drift: timedelta) -> object:
        sent = (NOW + drift).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        row = build_row(TelemetryEvent.model_validate(envelope(timestamp=sent)), TelemetryService.BACKOFFICE, NOW)
        assert row is not None
        return row["timestamp"]

    def test_the_client_time_is_kept_within_five_minutes(self) -> None:
        for drift in (timedelta(0), timedelta(minutes=5), timedelta(minutes=-5)):
            with self.subTest(drift=drift):
                self.assertEqual(self.moment_for(drift), NOW + drift)

    def test_otherwise_the_reception_time_is_stored(self) -> None:
        for drift in (timedelta(minutes=5, milliseconds=1), timedelta(minutes=-5, milliseconds=-1), timedelta(days=400)):
            with self.subTest(drift=drift):
                self.assertEqual(self.moment_for(drift), NOW)


class ThrottleTests(StorageCase):
    def test_the_limiter_grants_what_is_left_and_resets_with_the_window(self) -> None:
        now = [0.0]
        limiter = EventRateLimiter(limit=5, window_seconds=60, clock=lambda: now[0])
        self.assertEqual(limiter.take("a", 3), 3)
        self.assertEqual(limiter.take("a", 3), 2)
        self.assertEqual(limiter.take("a", 1), 0)
        self.assertEqual(limiter.take("b", 5), 5)
        now[0] = 60.0
        self.assertEqual(limiter.take("a", 1), 1)

    def test_the_excess_counts_as_rejected(self) -> None:
        results = [self.post(*[envelope() for _ in range(50)]) for _ in range(3)]
        self.assertEqual(sum(result["stored"] for result in results), EVENTS_PER_WINDOW)
        self.assertEqual(results[2], {"received": 50, "stored": 20, "rejected": 30})
        self.assertEqual(len(self.records()), EVENTS_PER_WINDOW)

    def test_each_token_has_its_own_budget(self) -> None:
        self.client.app.state.telemetry_rate_limiter = EventRateLimiter(limit=1)  # type: ignore[attr-defined]
        self.assertEqual(self.post(envelope(), envelope())["stored"], 1)
        authorize(self.client)
        self.assertEqual(self.post(envelope())["stored"], 1)

    def test_invalid_events_do_not_spend_the_budget(self) -> None:
        self.client.app.state.telemetry_rate_limiter = EventRateLimiter(limit=1)  # type: ignore[attr-defined]
        self.post(envelope("button_clicked"), envelope("button_clicked"))
        self.assertEqual(self.post(envelope())["stored"], 1)


class DatabaseFailureTests(StorageCase):
    def test_a_503_so_the_frontend_retries_and_no_sql_in_the_answer(self) -> None:
        failure = OperationalError("INSERT INTO telemetry_events", {}, Exception("could not connect to db.example.invalid"))
        with mock.patch.object(collector, "store_rows", side_effect=failure), capture_logs() as logs:
            response = self.client.post(URL, json={"events": [envelope()]})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "storage_unavailable")
        self.assertNotIn("example.invalid", response.text + logs.text())
        self.assertNotIn("INSERT", response.text + logs.text())

    def test_a_batch_without_valid_events_does_not_touch_the_database(self) -> None:
        with mock.patch.object(collector, "store_rows", side_effect=AssertionError):
            self.assertEqual(self.post(envelope("button_clicked")), {"received": 1, "stored": 0, "rejected": 1})


class ApiEmittedEventTests(StorageCase):
    def stock_edits(self) -> list[TelemetryEventRecord]:
        return [record for record in self.records() if record.event_type == "direct_stock_edit_rejected"]

    def test_the_stock_edit_attempt_is_stored_with_service_api(self) -> None:
        response = self.client.put("/inventory/products/1", json={})
        self.assertEqual(response.status_code, 405)
        (stored,) = self.stock_edits()
        self.assertEqual(stored.service, "api")
        self.assertEqual(stored.schema_version, "1.0.0")
        self.assertIsNone(stored.user_id)
        self.assertEqual(stored.tags["attempt_kind"], "method_not_allowed")
        self.assertEqual(stored.tags["route_template"], "/inventory/products/{id}")
        for key in DIMENSIONS:
            self.assertIn(key, stored.tags)

    def test_the_throttle_also_limits_what_is_stored(self) -> None:
        for _ in range(3):
            self.client.put("/inventory/products/1", json={})
        self.assertEqual(len(self.stock_edits()), 1)

    def test_the_same_function_stores_it(self) -> None:
        with mock.patch.object(collector, "store_rows", wraps=collector.store_rows) as store:
            self.client.put("/inventory/products/1", json={})
        self.assertEqual(store.call_count, 1)

    def test_a_failure_never_changes_the_response_and_the_log_line_stays(self) -> None:
        client = make_client(authenticated=False)  # sin la tabla
        self.addCleanup(client.auth_dir.cleanup)  # type: ignore[attr-defined]
        with capture_logs() as logs:
            response = client.put("/inventory/products/1", json={})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(sum(record.name == "nexova.telemetry" for record in logs.records), 1)
        warnings = [record.getMessage() for record in logs.records if record.name == "api.telemetry"]
        self.assertEqual(warnings, ["telemetry event not stored: OperationalError"])

    def test_an_invalid_event_is_not_stored(self) -> None:
        event_body = envelope("direct_stock_edit_rejected", properties={"attempt_kind": "guess"})
        with capture_logs() as logs:
            collector.store_api_event(self.engine, event_body)
        self.assertEqual(self.stock_edits(), [])
        self.assertIn("telemetry event not stored: invalid event", logs.text())


class AllowlistsFollowTheContractTests(unittest.TestCase):
    def test_the_copy_is_the_json_without_descriptions(self) -> None:
        definitions = contract()["definitions"]
        self.assertEqual(set(EVENT_ALLOWLISTS), FRONTEND_EVENT_TYPES | {"direct_stock_edit_rejected"})
        for name, allowlist in EVENT_ALLOWLISTS.items():
            with self.subTest(name):
                schema = definitions[name]["properties"]
                properties = schema["properties"]
                expected = {key: {k: v for k, v in spec.items() if k != "description"} for key, spec in properties["properties"].items()}
                self.assertEqual(allowlist.properties, expected)
                self.assertEqual(sorted(properties["required"]), sorted(expected))
                self.assertFalse(properties["additionalProperties"])
                self.assertEqual(allowlist.identity_required, schema.get("sessionId") == {"type": "string"})
                self.assertEqual(allowlist.identity_required, schema.get("userId") == {"type": "string"})
                self.assertEqual(schema["requestId"], {"type": "string"})
                pairs = tuple(
                    (option["properties"]["office"]["const"], option["properties"]["currency"]["const"])
                    for option in properties.get("oneOf", [])
                )
                self.assertEqual(allowlist.office_currency, pairs)

    def test_only_the_keywords_the_validator_understands(self) -> None:
        known = {"enum", "type", "minimum", "maximum", "exclusiveMinimum", "maxLength", "pattern", "items", "maxItems", "uniqueItems"}
        for name, allowlist in EVENT_ALLOWLISTS.items():
            for key, spec in allowlist.properties.items():
                self.assertLessEqual(set(spec), known, f"{name}.{key}")

    def test_every_example_of_the_plan_keeps_all_its_properties(self) -> None:
        checked = 0
        for example in plan_examples():
            if example["event_type"] not in EVENT_ALLOWLISTS:
                continue
            with self.subTest(event_type=example["event_type"]):
                row = build_row(TelemetryEvent.model_validate(example), TelemetryService.BACKOFFICE, NOW)
                assert row is not None
                self.assertEqual(row["tags"], example["properties"])
                self.assertEqual(contract_errors(example), [])
                checked += 1
        self.assertGreaterEqual(checked, 15)

    def test_service_follows_the_emitter_of_the_catalog(self) -> None:
        definitions = contract()["definitions"]
        for name in EVENT_ALLOWLISTS:
            emitter = "api" if name not in FRONTEND_EVENT_TYPES else "frontend"
            self.assertIn(f"emisor={emitter}", definitions[name]["$comment"])


class ImmutableInTheApplicationTests(unittest.TestCase):
    def test_no_code_updates_or_deletes_telemetry_events(self) -> None:
        for path in sorted((APP_DIR / "modules" / "telemetry").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    names = {alias.name for alias in node.names}
                    self.assertFalse(names & {"update", "delete"}, path.name)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, {"on_conflict_do_update", "delete"}, path.name)


if __name__ == "__main__":
    unittest.main()
