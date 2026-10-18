"""Hito 5, F3b: órdenes de entrada y salida del inventario y la regla del stock.

SQLite en memoria y `with TestClient`. Incluye los casos del evaluador (salida
mayor que el stock → 400; `allocation` sin `assigned_to` → 422; `current_stock`
igual al neto). `FOR UPDATE` no existe en SQLite: se comprueba compilando la
consulta con el dialecto de PostgreSQL y la regla se prueba de forma secuencial.
"""

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql, sqlite
from sqlmodel import Session

from app.core.config import Settings
from app.main import create_app
from app.modules.inventory import service
from app.modules.inventory.models import AssetEntry, AssetExit

from .inventory_support import INBOUND_URL, ORDERS_URL, OUTBOUND_URL, USER_UUID, InventoryTestCase
from .support import with_test_auth

INBOUND_KEYS = {"type", "id", "asset", "quantity", "supplier", "office", "created_at", "user_uuid"}
OUTBOUND_KEYS = {"type", "id", "asset", "quantity", "exit_type", "assigned_to", "office", "created_at", "user_uuid"}
QUANTITY_MAX = 2_147_483_647


class OrdersTestCase(InventoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.asset = self.create(name="Example laptop", sku="EXAMPLE-LAPTOP", office="Valencia")

    def inbound(self, quantity: int = 5, **changes: Any) -> Any:
        body = {"asset_id": self.asset["id"], "quantity": quantity, "supplier": "Example supplier", "office": "Valencia"}
        return self.client.post(INBOUND_URL, json=body | changes)

    def outbound(self, quantity: int = 1, **changes: Any) -> Any:
        body = {
            "asset_id": self.asset["id"],
            "quantity": quantity,
            "exit_type": "allocation",
            "assigned_to": "Example employee",
            "office": "Valencia",
        }
        return self.client.post(OUTBOUND_URL, json=body | changes)

    def consumption(self, quantity: int = 1, **changes: Any) -> Any:
        return self.outbound(quantity, exit_type="consumption", assigned_to=None, **changes)

    def orders(self) -> list[dict[str, Any]]:
        response = self.client.get(ORDERS_URL)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def assertCreated(self, response: Any) -> dict[str, Any]:
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def assertValidationError(self, response: Any, field: str) -> None:
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertIn(["body", field], [error["loc"] for error in response.json()["detail"]])


class EvaluatorCasesTests(OrdersTestCase):
    def test_exit_above_stock_is_400_with_the_literal_message_and_writes_nothing(self) -> None:
        self.assertCreated(self.inbound(5))
        before = self.orders()
        response = self.outbound(7)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "Insufficient stock for asset 'Example laptop'. Available: 5, requested: 7.", "code": "insufficient_stock"},
        )
        self.assertEqual(self.stock(self.asset["id"]), 5)
        self.assertEqual(self.orders(), before)

    def test_message_uses_the_asset_name_as_stored(self) -> None:
        asset = self.create(name='Portátil 14" Business', sku="EXAMPLE-QUOTE")
        response = self.consumption(1, asset_id=asset["id"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"], "Insufficient stock for asset 'Portátil 14\" Business'. Available: 0, requested: 1."
        )

    def test_allocation_without_assigned_to_is_422_on_that_field(self) -> None:
        self.assertCreated(self.inbound(5))
        body = {"asset_id": self.asset["id"], "quantity": 1, "exit_type": "allocation", "office": "Valencia"}
        for label, payload in (
            ("missing", body),
            ("null", body | {"assigned_to": None}),
            ("empty", body | {"assigned_to": ""}),
            ("blank", body | {"assigned_to": "   "}),
        ):
            with self.subTest(case=label):
                self.assertValidationError(self.client.post(OUTBOUND_URL, json=payload), "assigned_to")
        self.assertEqual(self.stock(self.asset["id"]), 5)

    def test_current_stock_is_the_net_of_several_orders_through_the_api(self) -> None:
        for quantity in (10, 5, 3):
            self.assertCreated(self.inbound(quantity))
        self.assertCreated(self.outbound(2))
        self.assertCreated(self.consumption(4))
        self.assertCreated(self.outbound(1, assigned_to="Other employee"))
        self.assertEqual(self.stock(self.asset["id"]), 18 - 7)
        listed = {item["id"]: item["current_stock"] for item in self.client.get("/inventory/products").json()}
        self.assertEqual(listed[self.asset["id"]], 11)


class OutboundRulesTests(OrdersTestCase):
    def test_consumption_with_assigned_to_is_422_on_that_field(self) -> None:
        self.assertCreated(self.inbound(5))
        response = self.outbound(1, exit_type="consumption", assigned_to="Example employee")
        self.assertValidationError(response, "assigned_to")
        self.assertEqual(self.orders()[0]["type"], "inbound")

    def test_consumption_without_assigned_to_is_stored_as_null(self) -> None:
        self.assertCreated(self.inbound(5))
        body = self.assertCreated(self.consumption(2))
        self.assertIsNone(body["assigned_to"])
        self.assertEqual(body["exit_type"], "consumption")

    def test_exit_equal_to_stock_is_accepted_and_leaves_zero(self) -> None:
        self.assertCreated(self.inbound(4))
        self.assertCreated(self.outbound(4))
        self.assertEqual(self.stock(self.asset["id"]), 0)
        response = self.consumption(1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"], "Insufficient stock for asset 'Example laptop'. Available: 0, requested: 1."
        )

    def test_assigned_to_is_stripped(self) -> None:
        self.assertCreated(self.inbound(1))
        self.assertEqual(self.assertCreated(self.outbound(1, assigned_to="  Example employee  "))["assigned_to"], "Example employee")

    def test_unknown_exit_type_is_422(self) -> None:
        self.assertValidationError(self.outbound(1, exit_type="loss"), "exit_type")


class CommonOrderRulesTests(OrdersTestCase):
    def test_unknown_asset_is_404_on_both_routes(self) -> None:
        for response in (self.inbound(5, asset_id=999), self.outbound(1, asset_id=999), self.consumption(1, asset_id=999)):
            with self.subTest(url=str(response.request.url)):
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "asset not found", "code": "asset_not_found"})
        self.assertEqual(self.orders(), [])

    def test_office_mismatch_is_400_and_writes_nothing(self) -> None:
        self.assertCreated(self.inbound(5))
        before = self.orders()
        for response in (self.inbound(5, office="Miami"), self.outbound(1, office="Miami"), self.consumption(1, office="Miami")):
            with self.subTest(url=str(response.request.url)):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(), {"detail": "order office does not match the asset office", "code": "office_mismatch"}
                )
        self.assertEqual(self.orders(), before)
        self.assertEqual(self.stock(self.asset["id"]), 5)

    def test_checks_run_in_order_422_404_office_stock(self) -> None:
        # 422 antes que 404: cuerpo inválido para un activo inexistente.
        self.assertEqual(self.outbound(0, asset_id=999).status_code, 422)
        # 404 antes que la oficina.
        self.assertEqual(self.outbound(1, asset_id=999, office="Miami").json()["code"], "asset_not_found")
        # Oficina antes que el stock (el activo no tiene stock).
        self.assertEqual(self.outbound(50, office="Miami").json()["code"], "office_mismatch")
        self.assertEqual(self.outbound(50).json()["code"], "insufficient_stock")

    def test_user_uuid_is_the_authenticated_user_id(self) -> None:
        expected = str(self.user.id)
        self.assertEqual(self.assertCreated(self.inbound(5))["user_uuid"], expected)
        self.assertEqual(self.assertCreated(self.outbound(1))["user_uuid"], expected)
        self.assertEqual({order["user_uuid"] for order in self.orders()}, {expected})

    def test_user_uuid_in_the_body_is_rejected(self) -> None:
        self.assertValidationError(self.inbound(5, user_uuid=USER_UUID), "user_uuid")
        self.assertCreated(self.inbound(5))
        self.assertValidationError(self.outbound(1, user_uuid=USER_UUID), "user_uuid")
        self.assertEqual({order["user_uuid"] for order in self.orders()}, {str(self.user.id)})

    def test_quantity_limits(self) -> None:
        for quantity in (0, -1, QUANTITY_MAX + 1, "5", True, 1.5, None):
            with self.subTest(quantity=quantity):
                self.assertValidationError(self.inbound(quantity), "quantity")  # type: ignore[arg-type]
                self.assertValidationError(self.outbound(quantity), "quantity")  # type: ignore[arg-type]
        self.assertCreated(self.inbound(QUANTITY_MAX))
        self.assertEqual(self.stock(self.asset["id"]), QUANTITY_MAX)

    def test_other_invalid_bodies_are_422(self) -> None:
        self.assertValidationError(self.inbound(5, supplier="  "), "supplier")
        self.assertValidationError(self.inbound(5, supplier="s" * 201), "supplier")
        self.assertValidationError(self.inbound(5, office="valencia"), "office")
        self.assertValidationError(self.inbound(5, asset_id="1"), "asset_id")
        self.assertValidationError(self.inbound(5, extra="x"), "extra")
        self.assertValidationError(self.outbound(1, current_stock=3), "current_stock")
        self.assertEqual(self.orders(), [])

    def test_inbound_response_shape(self) -> None:
        body = self.assertCreated(self.inbound(5, supplier="  TechDistrib Valencia S.L. "))
        self.assertEqual(set(body), INBOUND_KEYS)
        self.assertEqual(body["type"], "inbound")
        self.assertEqual(body["asset"], {"id": self.asset["id"], "name": "Example laptop", "sku": "EXAMPLE-LAPTOP"})
        self.assertEqual((body["quantity"], body["supplier"], body["office"]), (5, "TechDistrib Valencia S.L.", "Valencia"))
        self.assertEqual(datetime.fromisoformat(body["created_at"]).utcoffset(), timedelta(0))


class OrdersListTests(OrdersTestCase):
    def test_lists_entries_and_exits_with_type_asset_and_user(self) -> None:
        self.assertCreated(self.inbound(5))
        self.assertCreated(self.outbound(2))
        orders = self.orders()
        self.assertEqual([order["type"] for order in orders], ["outbound", "inbound"])
        self.assertEqual(set(orders[0]), OUTBOUND_KEYS)
        self.assertEqual(set(orders[1]), INBOUND_KEYS)
        for order in orders:
            self.assertEqual(order["asset"], {"id": self.asset["id"], "name": "Example laptop", "sku": "EXAMPLE-LAPTOP"})
            self.assertEqual(order["user_uuid"], str(self.user.id))
            self.assertEqual(datetime.fromisoformat(order["created_at"]).utcoffset(), timedelta(0))

    def test_newest_first_with_a_deterministic_tie_break(self) -> None:
        other = self.create(sku="EXAMPLE-OTHER", office="Miami")
        base = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
        with Session(self.engine) as session:
            rows = [
                AssetEntry(asset_id=self.asset["id"], quantity=5, supplier="S", office="Valencia", created_at=base, user_uuid=USER_UUID),
                AssetEntry(asset_id=other["id"], quantity=5, supplier="S", office="Miami", created_at=base, user_uuid=USER_UUID),
                AssetExit(asset_id=self.asset["id"], quantity=1, exit_type="consumption", office="Valencia", created_at=base, user_uuid=USER_UUID),
                AssetEntry(asset_id=self.asset["id"], quantity=5, supplier="S", office="Valencia", created_at=base + timedelta(hours=1), user_uuid=USER_UUID),
                AssetExit(asset_id=other["id"], quantity=1, exit_type="consumption", office="Miami", created_at=base - timedelta(hours=1), user_uuid=USER_UUID),
            ]
            session.add_all(rows)
            session.commit()
        listed = [(order["type"], order["id"], order["created_at"]) for order in self.orders()]
        self.assertEqual(
            [(kind, order_id) for kind, order_id, _ in listed],
            [("inbound", 3), ("outbound", 1), ("inbound", 2), ("inbound", 1), ("outbound", 2)],
        )
        self.assertEqual(listed[0][2], "2026-10-01T10:00:00Z")

    def test_same_number_of_queries_with_1_and_20_orders(self) -> None:
        self.assertCreated(self.inbound(100))
        with_one = self.count_queries("GET", ORDERS_URL)
        for index in range(19):
            asset = self.create(sku=f"EXAMPLE-N-{index}")
            self.add_orders(asset["id"], entries=[3], exits=[])
            self.assertCreated(self.consumption(1))
        self.assertEqual(len(self.orders()), 39)
        self.assertEqual(self.count_queries("GET", ORDERS_URL), with_one)
        self.assertEqual(with_one, 2)


class StockLockTests(OrdersTestCase):
    def test_asset_query_locks_the_row_in_postgresql(self) -> None:
        query = service.locked_asset_query(1)
        self.assertIn("FOR UPDATE", str(query.compile(dialect=postgresql.dialect())))
        # SQLite no tiene FOR UPDATE: SQLAlchemy no lo emite.
        self.assertNotIn("FOR UPDATE", str(query.compile(dialect=sqlite.dialect())))

    def test_outbound_reads_the_asset_with_the_locking_query_before_inserting(self) -> None:
        self.assertCreated(self.inbound(5))
        real = service.locked_asset_query
        with mock.patch.object(service, "locked_asset_query", side_effect=real) as spy:
            self.assertCreated(self.outbound(1))
            self.assertEqual(self.outbound(10).status_code, 400)
        self.assertEqual([call.args for call in spy.call_args_list], [(self.asset["id"],), (self.asset["id"],)])

    def test_inbound_does_not_lock(self) -> None:
        with mock.patch.object(service, "locked_asset_query", side_effect=service.locked_asset_query) as spy:
            self.assertCreated(self.inbound(5))
        spy.assert_not_called()


class AuthenticationTests(unittest.TestCase):
    def test_every_order_route_requires_a_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, TestClient(
            create_app(with_test_auth(Settings(), Path(tmp) / "auth.json"))
        ) as client:
            for method, url in (("POST", INBOUND_URL), ("POST", OUTBOUND_URL), ("GET", ORDERS_URL)):
                with self.subTest(method=method, url=url):
                    response = client.request(method, url, json={} if method == "POST" else None)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json()["code"], "not_authenticated")


if __name__ == "__main__":
    unittest.main()
