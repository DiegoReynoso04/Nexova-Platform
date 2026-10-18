"""Hito 5, F3a: rutas de productos (activos) del inventario.

SQLite en memoria y `with TestClient` (el lifespan crea las tablas). Las
órdenes se insertan directamente con la sesión: sus rutas llegan en F3b.
"""

import ast
import tempfile
import typing
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, func, select

from app.core.config import Settings
from app.main import create_app
from app.modules.inventory import schemas, service
from app.modules.inventory.models import Asset, AssetEntry, AssetExit
from app.modules.inventory.router import router as inventory_router
from app.modules.inventory.schemas import AssetCreate, AssetRead

from .support import APP_DIR, authorize, with_test_auth

PRODUCTS_URL = "/inventory/products"
ASSET_KEYS = {"id", "name", "sku", "category", "office", "current_stock"}
USER_UUID = "00000000-0000-4000-8000-000000000000"


def valid_asset(**changes: Any) -> dict[str, Any]:
    return {"name": "Example laptop", "sku": "EXAMPLE-001", "category": "hardware", "office": "Valencia"} | changes


class InventoryTestCase(unittest.TestCase):
    """App real con SQLite en memoria, lifespan ejecutado y un usuario autenticado."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = create_app(with_test_auth(Settings(), Path(tmp.name) / "auth.json"))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        authorize(self.client)

    @property
    def engine(self) -> Any:
        return self.app.state.inventory_engine

    def create(self, **changes: Any) -> dict[str, Any]:
        response = self.client.post(PRODUCTS_URL, json=valid_asset(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def add_orders(self, asset_id: int, entries: list[int], exits: list[int], office: str = "Valencia") -> None:
        with Session(self.engine) as session:
            for quantity in entries:
                session.add(
                    AssetEntry(
                        asset_id=asset_id, quantity=quantity, supplier="Example supplier", office=office, user_uuid=USER_UUID
                    )
                )
            for quantity in exits:
                session.add(
                    AssetExit(
                        asset_id=asset_id,
                        quantity=quantity,
                        exit_type="consumption",
                        office=office,
                        user_uuid=USER_UUID,
                    )
                )
            session.commit()

    def asset_count(self) -> int:
        with Session(self.engine) as session:
            return session.exec(select(func.count()).select_from(Asset)).one()


class CreateProductTests(InventoryTestCase):
    def test_creates_an_asset_with_zero_stock(self) -> None:
        body = self.create()
        self.assertEqual(set(body), ASSET_KEYS)
        self.assertEqual(
            body,
            {
                "id": body["id"],
                "name": "Example laptop",
                "sku": "EXAMPLE-001",
                "category": "hardware",
                "office": "Valencia",
                "current_stock": 0,
            },
        )

    def test_texts_are_stripped(self) -> None:
        body = self.create(name="  Example mouse  ", sku="\tEXAMPLE-002 ")
        self.assertEqual((body["name"], body["sku"]), ("Example mouse", "EXAMPLE-002"))

    def test_accepts_the_whole_vocabulary_and_200_characters(self) -> None:
        categories = ("hardware", "peripherals", "office_supplies", "training_materials")
        for index, category in enumerate(categories):
            for office in ("Valencia", "Miami"):
                with self.subTest(category=category, office=office):
                    body = self.create(sku=f"EXAMPLE-{category}-{office}", category=category, office=office)
                    self.assertEqual((body["category"], body["office"]), (category, office))
        body = self.create(name="n" * 200, sku="s" * 200)
        self.assertEqual(len(body["name"]), 200)

    def test_duplicate_sku_is_409_without_repeating_it(self) -> None:
        self.create(sku="EXAMPLE-DUP")
        for changes in ({}, {"office": "Miami", "name": "Other"}, {"sku": "  EXAMPLE-DUP  "}):
            with self.subTest(changes=changes):
                response = self.client.post(PRODUCTS_URL, json=valid_asset(**({"sku": "EXAMPLE-DUP"} | changes)))
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), {"detail": "an asset with this sku already exists", "code": "sku_already_exists"})
                self.assertNotIn("EXAMPLE-DUP", response.text)
        self.assertEqual(self.asset_count(), 1)

    def test_duplicate_sku_in_a_race_is_409_not_500(self) -> None:
        # La comprobación previa no ve el SKU (otra petición lo inserta justo
        # después): el UNIQUE de la base lanza IntegrityError en el commit.
        self.create(sku="EXAMPLE-RACE")
        real = service._sku_taken
        calls: list[bool] = []

        def first_check_misses(session: Session, sku: str) -> bool:
            calls.append(True)
            return False if len(calls) == 1 else real(session, sku)

        with mock.patch.object(service, "_sku_taken", side_effect=first_check_misses):
            response = self.client.post(PRODUCTS_URL, json=valid_asset(sku="EXAMPLE-RACE"))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "sku_already_exists")
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.asset_count(), 1)
        # La sesión de la petición se deshizo bien: la siguiente alta funciona.
        self.create(sku="EXAMPLE-AFTER-RACE")

    def test_invalid_bodies_are_422(self) -> None:
        cases = {
            "unknown category": valid_asset(category="furniture"),
            "category in another case": valid_asset(category="Hardware"),
            "unknown office": valid_asset(office="Madrid"),
            "office in lower case": valid_asset(office="valencia"),
            "extra field": valid_asset(colour="black"),
            "current_stock in the body": valid_asset(current_stock=10),
            "id in the body": valid_asset(id=5),
            "empty name": valid_asset(name=""),
            "blank name": valid_asset(name="   "),
            "blank sku": valid_asset(sku=" \t "),
            "name over 200": valid_asset(name="n" * 201),
            "sku over 200": valid_asset(sku="s" * 201),
            "name not a string": valid_asset(name=123),
            "missing office": {key: value for key, value in valid_asset().items() if key != "office"},
        }
        for label, payload in cases.items():
            with self.subTest(case=label):
                response = self.client.post(PRODUCTS_URL, json=payload)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(self.asset_count(), 0)


class ReadProductTests(InventoryTestCase):
    def test_list_is_ordered_by_id_and_includes_office(self) -> None:
        created = [self.create(sku=f"EXAMPLE-{index}", office=office) for index, office in enumerate(("Miami", "Valencia", "Miami"))]
        body = self.client.get(PRODUCTS_URL).json()
        self.assertEqual(body, created)
        self.assertEqual([item["id"] for item in body], sorted(item["id"] for item in body))
        for item in body:
            self.assertEqual(set(item), ASSET_KEYS)

    def test_empty_list(self) -> None:
        self.assertEqual(self.client.get(PRODUCTS_URL).json(), [])

    def test_get_by_id(self) -> None:
        created = self.create()
        response = self.client.get(f"{PRODUCTS_URL}/{created['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), created)

    def test_unknown_id_is_404(self) -> None:
        self.create()
        for asset_id in ("999", "0", "-1"):
            with self.subTest(asset_id=asset_id):
                response = self.client.get(f"{PRODUCTS_URL}/{asset_id}")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "asset not found", "code": "asset_not_found"})

    def test_non_integer_id_is_422(self) -> None:
        self.assertEqual(self.client.get(f"{PRODUCTS_URL}/abc").status_code, 422)


class CurrentStockTests(InventoryTestCase):
    def test_current_stock_is_entries_minus_exits(self) -> None:
        laptop = self.create(sku="EXAMPLE-LAPTOP")
        paper = self.create(sku="EXAMPLE-PAPER")
        hub = self.create(sku="EXAMPLE-HUB", office="Miami")
        untouched = self.create(sku="EXAMPLE-UNTOUCHED")
        # Varias entradas y varias salidas: un JOIN sin agregar antes daría 24.
        self.add_orders(laptop["id"], entries=[10, 5], exits=[2, 1])
        self.add_orders(paper["id"], entries=[20], exits=[])
        self.add_orders(hub["id"], entries=[], exits=[], office="Miami")
        expected = {laptop["id"]: 12, paper["id"]: 20, hub["id"]: 0, untouched["id"]: 0}
        listed = {item["id"]: item["current_stock"] for item in self.client.get(PRODUCTS_URL).json()}
        self.assertEqual(listed, expected)
        for asset_id, stock in expected.items():
            with self.subTest(asset_id=asset_id):
                self.assertEqual(self.client.get(f"{PRODUCTS_URL}/{asset_id}").json()["current_stock"], stock)

    def test_stock_is_never_stored(self) -> None:
        self.assertNotIn("current_stock", Asset.__table__.columns)


class QueryCountTests(InventoryTestCase):
    def count_queries(self, url: str) -> int:
        statements: list[str] = []

        def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record)
        try:
            self.assertEqual(self.client.get(url).status_code, 200)
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        return len(statements)

    def test_list_uses_the_same_single_query_for_1_and_20_assets(self) -> None:
        first = self.create(sku="EXAMPLE-Q-0")
        self.add_orders(first["id"], entries=[5, 3], exits=[1])
        with_one = self.count_queries(PRODUCTS_URL)
        for index in range(1, 20):
            asset = self.create(sku=f"EXAMPLE-Q-{index}")
            self.add_orders(asset["id"], entries=[5, 3], exits=[1])
        self.assertEqual(len(self.client.get(PRODUCTS_URL).json()), 20)
        with_twenty = self.count_queries(PRODUCTS_URL)
        self.assertEqual(with_one, 1)
        self.assertEqual(with_twenty, with_one)

    def test_get_by_id_is_a_single_query(self) -> None:
        asset = self.create()
        self.add_orders(asset["id"], entries=[4], exits=[1])
        self.assertEqual(self.count_queries(f"{PRODUCTS_URL}/{asset['id']}"), 1)


class AuthenticationTests(unittest.TestCase):
    def test_every_product_route_requires_a_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, TestClient(
            create_app(with_test_auth(Settings(), Path(tmp) / "auth.json"))
        ) as client:
            for method, url, body in (
                ("GET", PRODUCTS_URL, None),
                ("POST", PRODUCTS_URL, valid_asset()),
                ("GET", f"{PRODUCTS_URL}/1", None),
            ):
                with self.subTest(method=method, url=url):
                    response = client.request(method, url, json=body)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json()["code"], "not_authenticated")
                    self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")


class NoOrmInResponsesTests(unittest.TestCase):
    def inventory_routes(self) -> list[APIRoute]:
        # FastAPI 0.141 guarda los routers incluidos como `_IncludedRouter` en
        # `app.routes`: se recorren las rutas del router del inventario (todas
        # con el prefijo `/inventory`). Que la app las publica lo comprueba
        # `test_openapi_lists_the_inventory_routes`.
        return [route for route in inventory_router.routes if isinstance(route, APIRoute)]

    def test_every_inventory_route_has_a_non_orm_response_model(self) -> None:
        routes = self.inventory_routes()
        self.assertEqual(
            {(route.path, method) for route in routes for method in route.methods},
            {(PRODUCTS_URL, "GET"), (PRODUCTS_URL, "POST"), (f"{PRODUCTS_URL}/{{id}}", "GET")},
        )
        for route in routes:
            with self.subTest(path=route.path, methods=sorted(route.methods)):
                self.assertIsNotNone(route.response_model)
                models = typing.get_args(route.response_model) or (route.response_model,)
                for model in models:
                    self.assertFalse(issubclass(model, SQLModel), model)

    def test_schemas_are_plain_pydantic_and_do_not_import_the_orm(self) -> None:
        for model in (AssetCreate, AssetRead):
            self.assertFalse(issubclass(model, SQLModel))
        tree = ast.parse((APP_DIR / "modules" / "inventory" / "schemas.py").read_text(encoding="utf-8"))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertNotIn("models", imported)
        self.assertNotIn("sqlmodel", imported)
        self.assertFalse(any(module and module.endswith("inventory.models") for module in imported))
        self.assertIs(schemas.AssetRead, AssetRead)

    def test_schemas_differ_structurally_from_the_tables(self) -> None:
        self.assertNotIn("id", AssetCreate.model_fields)
        self.assertIn("current_stock", AssetRead.model_fields)
        self.assertNotIn("current_stock", Asset.model_fields)

    def test_openapi_lists_the_inventory_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(with_test_auth(Settings(), Path(tmp) / "auth.json")))
            paths = client.get("/openapi.json").json()["paths"]
        inventory_paths = {path for path in paths if path.startswith("/inventory")}
        self.assertIn(f"{PRODUCTS_URL}/{{id}}", inventory_paths)
        self.assertNotIn(f"{PRODUCTS_URL}/{{asset_id}}", inventory_paths)
        self.assertEqual(set(paths[PRODUCTS_URL]), {"get", "post"})
        self.assertEqual(set(paths[f"{PRODUCTS_URL}/{{id}}"]), {"get"})
        parameters = paths[f"{PRODUCTS_URL}/{{id}}"]["get"]["parameters"]
        self.assertEqual([(item["name"], item["in"]) for item in parameters], [("id", "path")])


if __name__ == "__main__":
    unittest.main()
