"""Colector de telemetría: `POST /telemetry/events`, el contrato HTTP (ticket de almacenamiento).

Valida cada item por separado, acepta lotes sin token, responde
`200 {"received", "stored", "rejected"}` mientras haya un arreglo `events` (D11)
y corta los bodies de más de 64 KiB. Lo que se guarda en la tabla, en
`test_telemetry_storage.py`. Ver docs/telemetry/storage-analysis.md.
"""

import json
import unittest
from typing import Any

from app.core.config import ConfigError, Settings
from app.modules.telemetry.catalog import EVENT_TYPES, FRONTEND_EVENT_TYPES, SCHEMA_VERSION
from app.modules.telemetry.schemas import (
    EVENT_TYPE_PATTERN,
    MAX_EVENTS_PER_BATCH,
    TIMESTAMP_PATTERN,
    UUID_V4_PATTERN,
    TelemetryEvent,
)

from .support import capture_logs, chunked
from .telemetry_support import contract, envelope, plan_examples, storage_client

URL = "/telemetry/events"
ENVELOPE_KEYS = ["eventId", "timestamp", "sessionId", "userId", "event_type", "schemaVersion", "requestId", "properties"]


def collector_lines(logs) -> list[str]:  # type: ignore[no-untyped-def]
    return [record.getMessage() for record in logs.records if record.name == "api.telemetry"]


class CollectorCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = storage_client()
        self.addCleanup(self.client.auth_dir.cleanup)  # type: ignore[attr-defined]

    def post(self, body: Any) -> dict[str, int]:
        response = self.client.post(URL, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        result: dict[str, int] = response.json()
        return result

    def assert_rejected(self, event: Any) -> None:
        """El item se rechaza solo: el evento válido del mismo lote se guarda."""
        self.assertEqual(self.post({"events": [event, envelope()]}), {"received": 2, "stored": 1, "rejected": 1})


class CollectorAcceptsBatchesTests(CollectorCase):
    def test_batches_of_1_20_and_50_events(self) -> None:
        for size in (1, 20, MAX_EVENTS_PER_BATCH):
            with self.subTest(size=size):
                result = self.post({"events": [envelope() for _ in range(size)]})
                self.assertEqual(result, {"received": size, "stored": size, "rejected": 0})

    def test_no_token_or_an_invalid_token_is_not_a_401(self) -> None:
        # sendBeacon no lleva Authorization, y un 401 cerraría la sesión en el backoffice.
        for headers in ({}, {"Authorization": "Bearer not-a-jwt"}):
            with self.subTest(headers=headers):
                response = self.client.post(URL, json={"events": [envelope()]}, headers=headers)
                self.assertEqual(response.status_code, 200)

    def test_every_example_of_the_plan_is_a_valid_envelope(self) -> None:
        examples = plan_examples()
        self.assertEqual(len(examples), 53)
        for example in examples:
            with self.subTest(event_type=example["event_type"]):
                TelemetryEvent.model_validate(example)

    def test_null_identity_is_accepted_where_the_plan_allows_it(self) -> None:
        self.assertEqual(self.post({"events": [envelope(sessionId=None, userId=None)]})["stored"], 1)

    def test_beacon_body_without_json_content_type_header_is_still_json(self) -> None:
        # sendBeacon con un Blob `application/json`: llega como un POST normal.
        body = json.dumps({"events": [envelope()]}).encode()
        response = self.client.post(URL, content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)


class ParseableBodyTests(CollectorCase):
    """D11: «parseable» = tiene un arreglo `events`."""

    def test_an_empty_batch_is_a_200_with_zeros(self) -> None:
        self.assertEqual(self.post({"events": []}), {"received": 0, "stored": 0, "rejected": 0})

    def test_over_50_only_the_first_50_are_processed_and_the_rest_rejected(self) -> None:
        events = [envelope() for _ in range(MAX_EVENTS_PER_BATCH + 3)]
        self.assertEqual(self.post({"events": events}), {"received": 53, "stored": 50, "rejected": 3})

    def test_items_that_are_not_objects_are_rejected_one_by_one(self) -> None:
        for item in ("text", 7, None, True, ["x"]):
            with self.subTest(item=item):
                self.assert_rejected(item)

    def test_a_body_without_an_events_array_is_a_422(self) -> None:
        for body in ({}, [envelope()], {"events": "x"}, {"events": {"a": 1}}, {"events": None}, {"events": [], "sent_at": "now"}):
            with self.subTest(body=body):
                response = self.client.post(URL, json=body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["code"], "validation_error")

    def test_a_body_that_is_not_json_is_a_422(self) -> None:
        response = self.client.post(URL, content=b"no-es-json", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)


class CollectorRejectsEventsTests(CollectorCase):
    def test_extra_keys_in_the_envelope(self) -> None:
        self.assert_rejected(envelope(email="leak@example.invalid"))

    def test_every_envelope_key_is_required(self) -> None:
        for key in ENVELOPE_KEYS:
            with self.subTest(key=key):
                event = envelope()
                del event[key]
                self.assert_rejected(event)

    def test_malformed_ids_timestamps_and_versions(self) -> None:
        upper = envelope()["eventId"].upper()
        cases = {
            "eventId uppercase": envelope(eventId=upper),
            "eventId not v4": envelope(eventId="5c1e7a2b-3d4f-1a6b-8c9d-0e1f2a3b4c5d"),
            "sessionId text": envelope(sessionId="session-1"),
            "userId email": envelope(userId="leak@example.invalid"),
            "requestId number": envelope(requestId=7),
            "requestId null": envelope(requestId=None),
            "timestamp without Z": envelope(timestamp="2026-11-03T10:00:00.000"),
            "timestamp without ms": envelope(timestamp="2026-11-03T10:00:00Z"),
            "other schemaVersion": envelope(schemaVersion="1.1.0"),
            "properties not an object": envelope(properties=["route"]),
        }
        for name, event in cases.items():
            with self.subTest(name):
                self.assert_rejected(event)

    def test_event_types_outside_the_catalog(self) -> None:
        for event_type in ("button_clicked", "Page_Viewed", "pageviewed", ""):
            with self.subTest(event_type=event_type):
                self.assert_rejected(envelope(event_type))

    def test_events_of_the_api_cannot_come_from_a_client(self) -> None:
        for event_type in sorted(set(EVENT_TYPES) - FRONTEND_EVENT_TYPES):
            with self.subTest(event_type=event_type):
                self.assert_rejected(envelope(event_type))

    def test_the_response_never_echoes_the_rejected_value(self) -> None:
        response = self.client.post(URL, json={"events": [envelope(userId="leak@example.invalid")]})
        self.assertNotIn("leak@example.invalid", response.text)


class CollectorBodyLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = storage_client()
        self.addCleanup(self.client.auth_dir.cleanup)  # type: ignore[attr-defined]

    def oversized_body(self) -> bytes:
        event = envelope(properties={"padding": "x" * (64 * 1024)})
        return json.dumps({"events": [event]}).encode()

    def test_bodies_over_64_kib_are_413(self) -> None:
        response = self.client.post(URL, content=self.oversized_body(), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "file_too_large")

    def test_without_content_length_the_body_is_still_cut(self) -> None:
        response = self.client.post(
            URL, content=chunked(self.oversized_body(), size=8 * 1024), headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.status_code, 413)

    def test_the_limit_only_applies_to_the_collector(self) -> None:
        # Otra ruta con el mismo body llega a la app (401 o 422), sin el 413 del colector.
        response = self.client.post(
            "/suppliers", content=self.oversized_body(), headers={"Content-Type": "application/json"}
        )
        self.assertNotEqual(response.status_code, 413)


class CollectorLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = storage_client()
        self.addCleanup(self.client.auth_dir.cleanup)  # type: ignore[attr-defined]

    def test_one_line_per_batch_with_counters_and_event_types_only(self) -> None:
        events = [envelope(), envelope("form_started", properties={"form": "inbound_order", "email": "leak@example.invalid"})]
        with capture_logs() as logs:
            self.client.post(URL, json={"events": [*events, envelope("button_clicked"), events[0]]})
        self.assertEqual(
            collector_lines(logs),
            ["batch received: 4 events, stored 3, rejected 1, duplicates 1, dropped keys 1 [page_viewed, form_started, page_viewed]"],
        )
        text = logs.text()
        for event in events:
            for key in ("eventId", "sessionId", "userId", "requestId"):
                self.assertNotIn(event[key], text)
        for secret in ("inbound_order", "/inventory/products", "leak@example.invalid", "button_clicked", "email"):
            self.assertNotIn(secret, text)

    def test_a_rejected_item_is_counted_but_never_named(self) -> None:
        with capture_logs() as logs:
            self.client.post(URL, json={"events": [envelope("button_clicked")]})
        self.assertEqual(collector_lines(logs), ["batch received: 1 events, stored 0, rejected 1, duplicates 0, dropped keys 0 []"])


class CatalogFollowsTheContractTests(unittest.TestCase):
    def test_event_types_are_the_contract_ones_in_the_same_order(self) -> None:
        definitions = [name for name in contract()["definitions"] if name != "envelope"]
        self.assertEqual(list(EVENT_TYPES), definitions)

    def test_frontend_event_types_are_the_contract_ones(self) -> None:
        definitions = contract()["definitions"]
        expected = {name for name, item in definitions.items() if name != "envelope" and "emisor=frontend" in item["$comment"]}
        self.assertEqual(FRONTEND_EVENT_TYPES, expected)
        self.assertEqual(len(expected), 14)

    def test_schema_version_matches_every_event_const(self) -> None:
        for name, definition in contract()["definitions"].items():
            if name == "envelope":
                continue
            with self.subTest(name):
                self.assertEqual(definition["properties"]["schemaVersion"], {"const": SCHEMA_VERSION})
        self.assertEqual(TelemetryEvent.model_fields["schemaVersion"].annotation.__args__, (SCHEMA_VERSION,))  # type: ignore[union-attr]

    def test_envelope_keys_and_patterns_are_the_contract_ones(self) -> None:
        schema = contract()["definitions"]["envelope"]
        self.assertEqual(schema["required"], ENVELOPE_KEYS)
        self.assertEqual(list(TelemetryEvent.model_fields), ENVELOPE_KEYS)
        properties = schema["properties"]
        for key in ("eventId", "sessionId", "userId", "requestId"):
            self.assertEqual(properties[key]["pattern"], UUID_V4_PATTERN, key)
        # El JSON usa `\d`; la API, `[0-9]` (ver schemas.py).
        self.assertEqual(properties["timestamp"]["pattern"].replace(r"\d", "[0-9]"), TIMESTAMP_PATTERN)
        self.assertEqual(properties["event_type"]["pattern"], EVENT_TYPE_PATTERN)


class TelemetryEndpointSettingTests(unittest.TestCase):
    def test_optional_and_validated(self) -> None:
        self.assertEqual(Settings.from_env({}).telemetry_endpoint, "")
        for value in ("/telemetry/events", "http://localhost:8000/telemetry/events", "https://telemetry.example.invalid/e"):
            with self.subTest(value=value):
                self.assertEqual(Settings.from_env({"TELEMETRY_ENDPOINT": f" {value} "}).telemetry_endpoint, value)
        for value in ("telemetry/events", "ftp://example.invalid/e", "localhost:8000"):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                Settings.from_env({"TELEMETRY_ENDPOINT": value})


if __name__ == "__main__":
    unittest.main()
