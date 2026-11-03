"""Telemetría del inventario en la API (ticket de captura, D1 «A ligera»).

- La API calcula y el frontend emite: las respuestas de alta llevan lo que solo
  sabe la API (stock antes y después y mínimo; coste, moneda, `supplier_key` y
  variación de coste), y con ellas el frontend construye eventos que validan
  contra `docs/telemetry/event-schemas.json`. Aquí se construyen igual que en el
  backoffice y se validan con el validador del repositorio.
- P3 (coste y moneda), P4 (`sid`), P9 (HMAC del proveedor), P10 (variación).
- P7: `direct_stock_edit_rejected`, el único que emite la API (405 y 422).
- La migración de P3 (`app/modules/inventory/migrate.py`).
"""

import dataclasses
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock
from uuid import UUID

from fastapi.testclient import TestClient
from jose import jwt
from sqlmodel import Session

from app.auth.security import JWT_ALGORITHM, create_access_token, read_token_claims
from app.core.config import ConfigError, Settings
from app.main import create_app
from app.modules.inventory import migrate
from app.modules.inventory.models import AssetEntry
from app.modules.telemetry.emitter import Throttle, normalize_supplier, supplier_key

from .inventory_support import INBOUND_URL, ORDERS_URL, OUTBOUND_URL, PRODUCTS_URL, valid_asset
from .support import TEST_JWT_SECRET, authorize, capture_logs, with_test_auth
from .telemetry_support import contract_errors, envelope

SUPPLIER_KEY = "k" * 40
SUPPLIER = "TechDistrib Valencia S.L."


def make_app(**changes: Any) -> tuple[TestClient, Any]:
    tmp = tempfile.TemporaryDirectory()
    settings = dataclasses.replace(with_test_auth(Settings(), Path(tmp.name) / "auth.json"), **changes)
    app = create_app(settings)
    client = TestClient(app)
    client.__enter__()
    client.tmp = tmp  # type: ignore[attr-defined]
    return client, app


def close(client: TestClient) -> None:
    client.__exit__(None, None, None)
    client.tmp.cleanup()  # type: ignore[attr-defined]


def telemetry_events(logs: Any) -> list[dict[str, Any]]:
    return [json.loads(record.getMessage()) for record in logs.records if record.name == "nexova.telemetry"]


# --- Lo que hace el backoffice con las respuestas (hooks de Entrada y Salida) ---


def inventory_minimum(order: dict[str, Any], asset_category: str) -> dict[str, Any]:
    return {
        "office": order["office"].lower(),
        "product_id": order["asset"]["id"],
        "product_category": None,
        "programme_id": None,
        "quantity": order["quantity"],
        "currency": order["currency"],
        "asset_category": asset_category,
    }


def frontend_events_for_outbound(order: dict[str, Any], asset_category: str) -> list[dict[str, Any]]:
    base = inventory_minimum(order, asset_category)
    events = [
        envelope(
            "outbound_order_created",
            properties=base
            | {"outbound_order_id": order["id"], "exit_type": order["exit_type"], "stock_after": order["stock_after"]},
        )
    ]
    if order["stock_before"] >= order["min_stock"] > order["stock_after"]:
        events.append(
            envelope(
                "stock_threshold_triggered",
                properties=base
                | {
                    "outbound_order_id": order["id"],
                    "stock_before": order["stock_before"],
                    "stock_after": order["stock_after"],
                    "min_stock": order["min_stock"],
                },
            )
        )
    return events


def frontend_events_for_inbound(order: dict[str, Any], asset_category: str) -> list[dict[str, Any]]:
    if order["unit_cost"] is None or order["supplier_key"] is None:
        return []
    base = inventory_minimum(order, asset_category) | {"inbound_order_id": order["id"], "supplier_key": order["supplier_key"]}
    events = [envelope("inbound_order_created", properties=base | {"unit_cost": order["unit_cost"]})]
    variance = order["cost_variance"]
    if variance is not None:
        events.append(envelope("kit_cost_variance_detected", properties=base | {"unit_cost": order["unit_cost"], **variance}))
    return events


class InventoryTelemetryCase(unittest.TestCase):
    settings_changes: dict[str, Any] = {"telemetry_supplier_key": SUPPLIER_KEY}

    def setUp(self) -> None:
        self.client, self.app = make_app(**self.settings_changes)
        self.addCleanup(close, self.client)
        self.user = authorize(self.client)

    def create_asset(self, **changes: Any) -> dict[str, Any]:
        response = self.client.post(PRODUCTS_URL, json=valid_asset(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def inbound(self, asset: dict[str, Any], unit_cost: Any = 10, quantity: int = 5, **changes: Any) -> Any:
        body = {"asset_id": asset["id"], "quantity": quantity, "supplier": SUPPLIER, "office": asset["office"], "unit_cost": unit_cost}
        return self.client.post(INBOUND_URL, json=body | changes)

    def created(self, response: Any) -> dict[str, Any]:
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def outbound(self, asset: dict[str, Any], quantity: int) -> dict[str, Any]:
        body = {"asset_id": asset["id"], "quantity": quantity, "exit_type": "consumption", "assigned_to": None, "office": asset["office"]}
        return self.created(self.client.post(OUTBOUND_URL, json=body))


class UnitCostTests(InventoryTelemetryCase):
    """P3: `unit_cost` obligatorio y `currency` de la oficina."""

    def test_unit_cost_is_required_positive_and_with_two_decimals_at_most(self) -> None:
        asset = self.create_asset()
        body = {"asset_id": asset["id"], "quantity": 1, "supplier": SUPPLIER, "office": "Valencia"}
        for invalid in (None, 0, -1, 1.234, "abc", True, 10_000_000_000):
            with self.subTest(unit_cost=invalid):
                response = self.client.post(INBOUND_URL, json=body | ({} if invalid is None else {"unit_cost": invalid}))
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual([error["loc"] for error in response.json()["detail"]], [["body", "unit_cost"]])
        for valid in (0.01, 18.5, 9_999_999_999.99):
            with self.subTest(unit_cost=valid):
                self.assertEqual(self.created(self.inbound(asset, valid))["unit_cost"], valid)

    def test_currency_comes_from_the_office_and_is_never_accepted_from_the_client(self) -> None:
        valencia = self.create_asset()
        miami = self.create_asset(sku="EXAMPLE-MIA", office="Miami")
        self.assertEqual(self.created(self.inbound(valencia))["currency"], "EUR")
        self.assertEqual(self.created(self.inbound(miami))["currency"], "USD")
        response = self.inbound(valencia, currency="USD")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"][0]["loc"], ["body", "currency"])

    def test_the_order_list_carries_cost_and_currency_and_old_entries_have_null(self) -> None:
        asset = self.create_asset()
        with Session(self.app.state.inventory_engine) as session:
            session.add(AssetEntry(asset_id=asset["id"], quantity=2, supplier=SUPPLIER, office="Valencia", user_uuid=str(self.user.id)))
            session.commit()
        self.created(self.inbound(asset, 18.5))
        orders = self.client.get(ORDERS_URL).json()
        self.assertEqual(sorted((order["unit_cost"], order["currency"]) for order in orders if order["unit_cost"]), [(18.5, "EUR")])
        self.assertEqual([order for order in orders if order["unit_cost"] is None][0]["currency"], None)
        for order in orders:
            self.assertNotIn("supplier_key", order)
            self.assertNotIn("cost_variance", order)


class SupplierKeyTests(InventoryTelemetryCase):
    """P9: HMAC-SHA256 del proveedor normalizado, nunca el nombre."""

    def test_supplier_key_is_the_hmac_of_the_normalized_supplier(self) -> None:
        asset = self.create_asset()
        body = self.created(self.inbound(asset))
        self.assertEqual(body["supplier_key"], supplier_key(SUPPLIER_KEY, SUPPLIER))
        self.assertRegex(body["supplier_key"], r"^[0-9a-f]{64}$")
        self.assertNotIn(SUPPLIER.lower(), body["supplier_key"])

    def test_normalization_groups_case_spacing_and_compatibility_forms(self) -> None:
        self.assertEqual(normalize_supplier("  TechDistrib   VALENCIA s.l. "), "techdistrib valencia s.l.")
        self.assertEqual(normalize_supplier("Ｔｅｃｈ"), "tech")
        self.assertEqual(supplier_key(SUPPLIER_KEY, "Office Depot Miami"), supplier_key(SUPPLIER_KEY, " office  depot MIAMI"))
        self.assertNotEqual(supplier_key(SUPPLIER_KEY, "Office Depot Miami"), supplier_key(SUPPLIER_KEY, "Office Depot Miami S.L."))
        self.assertNotEqual(supplier_key(SUPPLIER_KEY, SUPPLIER), supplier_key("x" * 40, SUPPLIER))

    def test_without_the_key_there_is_no_supplier_key(self) -> None:
        client, _ = make_app()
        self.addCleanup(close, client)
        authorize(client)
        asset = client.post(PRODUCTS_URL, json=valid_asset()).json()
        body = client.post(
            INBOUND_URL, json={"asset_id": asset["id"], "quantity": 1, "supplier": SUPPLIER, "office": "Valencia", "unit_cost": 5}
        ).json()
        self.assertIsNone(body["supplier_key"])
        self.assertEqual(frontend_events_for_inbound(body, "hardware"), [])


class CostVarianceTests(InventoryTelemetryCase):
    """P10 (D3): umbral 10 %, media de las 3 entradas anteriores del mismo activo y proveedor."""

    def costs(self, asset: dict[str, Any], *values: float, supplier: str = SUPPLIER) -> list[dict[str, Any]]:
        return [self.created(self.inbound(asset, value, supplier=supplier)) for value in values]

    def test_fewer_than_three_previous_entries_are_not_evaluated(self) -> None:
        asset = self.create_asset()
        self.assertEqual([body["cost_variance"] for body in self.costs(asset, 10, 10, 50)], [None, None, None])

    def test_an_increase_over_the_threshold_is_reported(self) -> None:
        asset = self.create_asset()
        *_, body = self.costs(asset, 18.5, 18.5, 18.5, 21.4)
        self.assertEqual(
            body["cost_variance"],
            {"reference_unit_cost": 18.5, "variance_pct": 15.68, "direction": "increase", "threshold_pct": 10.0, "reference_window": 3},
        )
        events = frontend_events_for_inbound(body, asset["category"])
        self.assertEqual([event["event_type"] for event in events], ["inbound_order_created", "kit_cost_variance_detected"])
        for event in events:
            self.assertEqual(contract_errors(event), [], event["event_type"])

    def test_a_decrease_is_reported_and_exactly_the_threshold_is_not(self) -> None:
        asset = self.create_asset()
        *_, at_threshold, below = self.costs(asset, 10, 10, 10, 9, 5)
        self.assertIsNone(at_threshold["cost_variance"])  # −10 % no supera el umbral
        self.assertEqual(below["cost_variance"]["direction"], "decrease")
        # Referencia: 10, 10 y 9 (las 3 anteriores) → 9.67.
        self.assertEqual(below["cost_variance"]["reference_unit_cost"], 9.67)
        self.assertEqual(below["cost_variance"]["variance_pct"], -48.28)

    def test_only_the_same_asset_and_normalized_supplier_count(self) -> None:
        asset = self.create_asset()
        other = self.create_asset(sku="EXAMPLE-002")
        self.costs(other, 10, 10, 10)
        self.costs(asset, 10, 10, supplier="Another supplier")
        self.costs(asset, 10, 10, supplier="  techdistrib valencia S.L.")
        self.assertIsNone(self.costs(asset, 50)[0]["cost_variance"])  # solo 2 anteriores del par
        self.costs(asset, 10)
        self.assertIsNotNone(self.costs(asset, 50)[0]["cost_variance"])

    def test_entries_without_cost_are_not_part_of_the_reference(self) -> None:
        asset = self.create_asset()
        with Session(self.app.state.inventory_engine) as session:
            for _ in range(3):
                session.add(AssetEntry(asset_id=asset["id"], quantity=1, supplier=SUPPLIER, office="Valencia", user_uuid="u"))
            session.commit()
        self.assertIsNone(self.costs(asset, 50)[0]["cost_variance"])


class CostVarianceSettingsTests(InventoryTelemetryCase):
    settings_changes = {"telemetry_supplier_key": SUPPLIER_KEY, "cost_variance_threshold_pct": 50.0, "cost_variance_window": 1}

    def test_threshold_and_window_are_configurable(self) -> None:
        asset = self.create_asset()
        self.created(self.inbound(asset, 10))
        self.assertIsNone(self.created(self.inbound(asset, 14))["cost_variance"])
        variance = self.created(self.inbound(asset, 30))["cost_variance"]
        self.assertEqual((variance["reference_unit_cost"], variance["threshold_pct"], variance["reference_window"]), (14.0, 50.0, 1))


class OutboundStockTests(InventoryTelemetryCase):
    def test_the_response_carries_stock_before_after_min_stock_and_currency(self) -> None:
        asset = self.create_asset(sku="EXAMPLE-MIA", office="Miami")
        self.created(self.inbound(asset, quantity=8))
        body = self.outbound(asset, 2)
        self.assertEqual((body["stock_before"], body["stock_after"], body["min_stock"], body["currency"]), (8, 6, 5, "USD"))
        events = frontend_events_for_outbound(body, asset["category"])
        self.assertEqual([event["event_type"] for event in events], ["outbound_order_created"])
        self.assertEqual(contract_errors(events[0]), [])

    def test_crossing_the_minimum_gives_the_threshold_event_once(self) -> None:
        asset = self.create_asset()
        self.created(self.inbound(asset, quantity=7))
        crossing = self.outbound(asset, 3)  # 7 → 4: cruza 5
        below = self.outbound(asset, 1)  # 4 → 3: ya estaba por debajo
        self.assertEqual(
            [event["event_type"] for event in frontend_events_for_outbound(crossing, asset["category"])],
            ["outbound_order_created", "stock_threshold_triggered"],
        )
        for event in frontend_events_for_outbound(crossing, asset["category"]):
            self.assertEqual(contract_errors(event), [], event["event_type"])
        self.assertEqual(len(frontend_events_for_outbound(below, asset["category"])), 1)
        self.assertEqual(self.client.get(f"{PRODUCTS_URL}/{asset['id']}").json()["current_stock"], 3)

    def test_the_order_list_does_not_carry_the_creation_fields(self) -> None:
        asset = self.create_asset()
        self.created(self.inbound(asset))
        self.outbound(asset, 1)
        outbound = [order for order in self.client.get(ORDERS_URL).json() if order["type"] == "outbound"][0]
        self.assertFalse({"stock_before", "stock_after", "min_stock", "currency"} & set(outbound))


class MinStockSettingTests(InventoryTelemetryCase):
    settings_changes = {"inventory_default_min_stock": 0}

    def test_min_stock_comes_from_the_setting(self) -> None:
        asset = self.create_asset()
        self.created(self.inbound(asset, quantity=1))
        body = self.outbound(asset, 1)
        self.assertEqual(body["min_stock"], 0)
        # Con 0 nunca se cruza (`stock_after < 0` es imposible).
        self.assertEqual(len(frontend_events_for_outbound(body, asset["category"])), 1)


class SessionClaimTests(unittest.TestCase):
    """P4: `sid` (UUID v4) en cada login; `read_token_claims` sin TinyDB."""

    settings = Settings(jwt_secret_key=TEST_JWT_SECRET, access_token_expire_minutes=15)

    def test_every_token_gets_a_new_v4_sid(self) -> None:
        first = read_token_claims(self.settings, create_access_token(self.settings, "user-1"))
        second = read_token_claims(self.settings, create_access_token(self.settings, "user-1"))
        assert first is not None and second is not None and first.sid is not None
        self.assertEqual(UUID(first.sid).version, 4)
        self.assertEqual(first.sub, "user-1")
        self.assertNotEqual(first.sid, second.sid)

    def test_invalid_expired_or_foreign_tokens_give_none_and_old_tokens_no_sid(self) -> None:
        now = datetime.now(UTC)
        expired = create_access_token(self.settings, "user-1", now=now - timedelta(hours=1))
        foreign = create_access_token(dataclasses.replace(self.settings, jwt_secret_key="o" * 48), "user-1")
        for token in ("not-a-jwt", expired, foreign):
            self.assertIsNone(read_token_claims(self.settings, token))
        old = jwt.encode({"sub": "user-1", "iat": now, "exp": now + timedelta(minutes=5)}, TEST_JWT_SECRET, algorithm=JWT_ALGORITHM)
        claims = read_token_claims(self.settings, old)
        assert claims is not None
        self.assertIsNone(claims.sid)


class DirectStockEditTests(InventoryTelemetryCase):
    """P7 (D5): 405 de escritura sobre el activo y 422 `current_stock` en un alta."""

    def attempt(self, method: str, url: str, **kwargs: Any) -> tuple[Any, list[dict[str, Any]]]:
        with capture_logs() as logs:
            response = self.client.request(method, url, **kwargs)
        return response, telemetry_events(logs)

    def test_write_methods_on_the_asset_are_reported_with_the_asset_office(self) -> None:
        asset = self.create_asset(sku="EXAMPLE-MIA", office="Miami")
        for method in ("PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                response, events = self.attempt(method, f"{PRODUCTS_URL}/{asset['id']}", json={"current_stock": 99})
                self.assertEqual(response.status_code, 405)
                [event] = events
                self.assertEqual(contract_errors(event), [])
                self.assertEqual(event["userId"], str(self.user.id))
                self.assertIsNotNone(event["sessionId"])
                self.assertEqual(
                    event["properties"],
                    {
                        "office": "miami",
                        "product_id": asset["id"],
                        "product_category": None,
                        "programme_id": None,
                        "quantity": None,
                        "currency": "USD",
                        "attempt_kind": "method_not_allowed",
                        "http_method": method,
                        "route_template": "/inventory/products/{id}",
                        "status_code": 405,
                        "authenticated": True,
                        "suppressed_count": 0,
                    },
                )

    def test_anonymous_unknown_or_non_numeric_ids_and_the_collection(self) -> None:
        del self.client.headers["Authorization"]
        cases = [("PUT", f"{PRODUCTS_URL}/999", 999), ("PATCH", f"{PRODUCTS_URL}/abc", None), ("DELETE", PRODUCTS_URL, None)]
        for method, url, product_id in cases:
            with self.subTest(url=url):
                response, [event] = self.attempt(method, url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(contract_errors(event), [])
                self.assertEqual((event["userId"], event["sessionId"]), (None, None))
                props = event["properties"]
                self.assertEqual((props["product_id"], props["office"], props["currency"], props["authenticated"]), (product_id, None, None, False))

    def test_other_405s_and_404s_are_not_reported(self) -> None:
        for method, url in (("POST", f"{PRODUCTS_URL}/1"), ("PUT", ORDERS_URL), ("PUT", "/suppliers/abc/xyz"), ("PUT", f"{PRODUCTS_URL}/1/stock")):
            with self.subTest(method=method, url=url):
                _, events = self.attempt(method, url)
                self.assertEqual(events, [])

    def test_the_405_response_does_not_change(self) -> None:
        response, _ = self.attempt("PUT", f"{PRODUCTS_URL}/1")
        self.assertEqual(response.json(), {"detail": "Method Not Allowed", "code": "method_not_allowed"})
        self.assertIn("GET", response.headers["allow"])

    def test_current_stock_in_a_create_body_is_reported_once_with_the_quantity(self) -> None:
        asset = self.create_asset()
        cases = [
            (PRODUCTS_URL, valid_asset(sku="EXAMPLE-NEW", current_stock=40), None, "valencia"),
            (INBOUND_URL, {"asset_id": asset["id"], "quantity": 1, "supplier": SUPPLIER, "office": "Valencia", "unit_cost": 1, "current_stock": 7}, asset["id"], "valencia"),
            (OUTBOUND_URL, {"asset_id": asset["id"], "quantity": 1, "exit_type": "consumption", "office": "Valencia", "current_stock": True}, asset["id"], "valencia"),
        ]
        for url, body, product_id, office in cases:
            with self.subTest(url=url):
                response, [event] = self.attempt("POST", url, json=body)
                self.assertEqual(response.status_code, 422)
                # La respuesta no cambia: sin `input` (el valor enviado) en el detalle.
                self.assertTrue(all("input" not in error for error in response.json()["detail"]))
                self.assertEqual(contract_errors(event), [])
                props = event["properties"]
                expected_quantity = body["current_stock"] if type(body["current_stock"]) is int else None
                self.assertEqual(
                    (props["attempt_kind"], props["route_template"], props["status_code"], props["product_id"], props["office"], props["quantity"]),
                    ("stock_field_in_body", url, 422, product_id, office, expected_quantity),
                )

    def test_other_validation_errors_are_not_reported_and_without_token_it_is_a_401(self) -> None:
        _, events = self.attempt("POST", PRODUCTS_URL, json=valid_asset(stock=3))
        self.assertEqual(events, [])
        del self.client.headers["Authorization"]
        response, events = self.attempt("POST", PRODUCTS_URL, json=valid_asset(current_stock=3))
        self.assertEqual((response.status_code, events), (401, []))

    def test_a_database_failure_still_emits_with_a_null_office(self) -> None:
        reporter = self.app.state.stock_edit_reporter
        with mock.patch.object(reporter, "engine", None):
            response, [event] = self.attempt("PUT", f"{PRODUCTS_URL}/1")
        self.assertEqual(response.status_code, 405)
        self.assertEqual((event["properties"]["office"], event["properties"]["currency"]), (None, None))

    def test_repeated_attempts_are_throttled_and_counted(self) -> None:
        clock = [0.0]
        self.app.state.stock_edit_reporter.throttle = Throttle(clock=lambda: clock[0])
        url = f"{PRODUCTS_URL}/1"
        counts = []
        for _ in range(3):
            counts.append(len(self.attempt("PUT", url)[1]))
        clock[0] = 61.0
        _, [event] = self.attempt("PUT", url)
        _, other_method = self.attempt("PATCH", url)
        self.assertEqual(counts, [1, 0, 0])
        self.assertEqual(event["properties"]["suppressed_count"], 2)
        self.assertEqual(len(other_method), 1)


class NewSettingsTests(unittest.TestCase):
    def test_defaults_and_parsing(self) -> None:
        settings = Settings.from_env({})
        self.assertEqual(
            (settings.inventory_default_min_stock, settings.telemetry_supplier_key, settings.cost_variance_threshold_pct, settings.cost_variance_window),
            (5, "", 10.0, 3),
        )
        parsed = Settings.from_env(
            {
                "INVENTORY_DEFAULT_MIN_STOCK": "8",
                "TELEMETRY_SUPPLIER_KEY": SUPPLIER_KEY,
                "TELEMETRY_COST_VARIANCE_THRESHOLD_PCT": "12.5",
                "TELEMETRY_COST_VARIANCE_WINDOW": "4",
            }
        )
        self.assertEqual((parsed.inventory_default_min_stock, parsed.cost_variance_threshold_pct, parsed.cost_variance_window), (8, 12.5, 4))
        self.assertNotIn(SUPPLIER_KEY, repr(parsed))

    def test_invalid_values_stop_the_startup(self) -> None:
        invalid = [
            {"INVENTORY_DEFAULT_MIN_STOCK": "-1"},
            {"INVENTORY_DEFAULT_MIN_STOCK": "cinco"},
            {"TELEMETRY_SUPPLIER_KEY": "short"},
            {"TELEMETRY_COST_VARIANCE_THRESHOLD_PCT": "0"},
            {"TELEMETRY_COST_VARIANCE_THRESHOLD_PCT": "nan"},
            {"TELEMETRY_COST_VARIANCE_THRESHOLD_PCT": "1001"},
            {"TELEMETRY_COST_VARIANCE_WINDOW": "0"},
            {"TELEMETRY_COST_VARIANCE_WINDOW": "101"},
            {"TELEMETRY_COST_VARIANCE_WINDOW": "3.5"},
        ]
        for environ in invalid:
            with self.subTest(environ=environ), self.assertRaises(ConfigError) as raised:
                Settings.from_env(environ)
            self.assertNotIn("short", str(raised.exception))


class MigrationTests(unittest.TestCase):
    """P3 en una base existente: solo lo que falta, y solo en PostgreSQL."""

    def test_pending_statements_are_only_the_missing_ones(self) -> None:
        everything = migrate.pending_statements(set(), set())
        self.assertEqual(len(everything), 4)
        self.assertTrue(everything[0].startswith("ALTER TABLE asset_entries ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(12, 2) NULL"))
        self.assertIn("CHECK (currency IN ('EUR', 'USD'))", everything[3])
        done = migrate.pending_statements({"unit_cost", "currency"}, {migrate.UNIT_COST_CHECK, migrate.CURRENCY_CHECK})
        self.assertEqual(done, [])
        self.assertEqual(len(migrate.pending_statements({"unit_cost", "currency"}, set())), 2)

    def test_only_postgresql_and_never_the_url_in_the_messages(self) -> None:
        settings = Settings(database_url="sqlite://")
        with capture_logs(), mock.patch("sys.stderr") as stderr:
            self.assertEqual(migrate.run(["--dry-run"], settings=settings), migrate.CONFIG_ERROR_EXIT)
        written = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn("solo se aplica a PostgreSQL", written)
        self.assertEqual(migrate.run([], settings=Settings()), migrate.CONFIG_ERROR_EXIT)

    def test_the_model_constraints_have_the_migration_names(self) -> None:
        names = {constraint.name for constraint in AssetEntry.__table__.constraints}  # type: ignore[attr-defined]
        self.assertLessEqual({migrate.UNIT_COST_CHECK, migrate.CURRENCY_CHECK}, names)


if __name__ == "__main__":
    unittest.main()
