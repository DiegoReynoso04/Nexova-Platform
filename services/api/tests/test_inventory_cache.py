"""Caché de `GET /inventory/products` y `/products/{id}` (ticket de caching, D1–D4).

App real con SQLite en memoria (como el resto de tests del inventario). Las
consultas se cuentan con el evento `before_cursor_execute` del motor: un
acierto no ejecuta ninguna.
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.inventory.router import CACHE_NAMESPACE, CACHE_TTL_SECONDS

from .inventory_support import INBOUND_URL, OUTBOUND_URL, PRODUCTS_URL, InventoryTestCase, valid_asset
from .support import authorize, with_test_auth


def inbound(asset_id: int, quantity: int = 5) -> dict[str, Any]:
    return {"asset_id": asset_id, "quantity": quantity, "supplier": "Example supplier", "office": "Valencia", "unit_cost": 10}


def outbound(asset_id: int, quantity: int = 1) -> dict[str, Any]:
    return {"asset_id": asset_id, "quantity": quantity, "exit_type": "consumption", "office": "Valencia"}


class InventoryCacheTestCase(InventoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.asset = self.create()
        self.detail_url = f"{PRODUCTS_URL}/{self.asset['id']}"

    def queries(self, url: str) -> int:
        return self.count_queries("GET", url)

    def stock_in_list(self) -> int:
        [item] = [item for item in self.client.get(PRODUCTS_URL).json() if item["id"] == self.asset["id"]]
        return item["current_stock"]


class HitTests(InventoryCacheTestCase):
    def test_ttl_is_60_seconds_in_the_inventory_namespace(self) -> None:
        self.assertEqual((CACHE_NAMESPACE, CACHE_TTL_SECONDS), ("inventory", 60))

    def test_a_hit_on_the_list_does_not_repeat_the_query(self) -> None:
        self.assertEqual(self.queries(PRODUCTS_URL), 1)
        self.assertEqual(self.queries(PRODUCTS_URL), 0)

    def test_a_hit_on_the_detail_does_not_repeat_the_query(self) -> None:
        self.assertEqual(self.queries(self.detail_url), 1)
        self.assertEqual(self.queries(self.detail_url), 0)

    def test_the_hit_returns_the_same_body(self) -> None:
        first = self.client.get(PRODUCTS_URL)
        second = self.client.get(PRODUCTS_URL)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())

    def test_list_and_detail_are_different_keys(self) -> None:
        self.queries(PRODUCTS_URL)
        self.assertEqual(self.queries(self.detail_url), 1)

    def test_a_404_is_not_cached(self) -> None:
        missing = f"{PRODUCTS_URL}/999"
        self.assertEqual(self.client.get(missing).status_code, 404)
        created = self.create(sku="EXAMPLE-404")
        self.assertEqual(self.client.get(f"{PRODUCTS_URL}/{created['id']}").status_code, 200)
        self.assertEqual(self.client.get(missing).status_code, 404)
        self.assertEqual(self.app.state.response_cache.size(CACHE_NAMESPACE), 1)


class InvalidationTests(InventoryCacheTestCase):
    def warm(self) -> None:
        self.assertEqual(self.queries(PRODUCTS_URL), 1)
        self.assertEqual(self.queries(self.detail_url), 1)

    def assert_cold(self) -> None:
        self.assertEqual(self.queries(PRODUCTS_URL), 1)
        self.assertEqual(self.queries(self.detail_url), 1)

    def test_a_successful_inbound_order_invalidates_list_and_detail(self) -> None:
        self.warm()
        self.assertEqual(self.client.post(INBOUND_URL, json=inbound(self.asset["id"], 5)).status_code, 201)
        self.assert_cold()
        self.assertEqual(self.stock_in_list(), 5)
        self.assertEqual(self.stock(self.asset["id"]), 5)

    def test_a_successful_outbound_order_invalidates(self) -> None:
        self.client.post(INBOUND_URL, json=inbound(self.asset["id"], 5))
        self.warm()
        self.assertEqual(self.client.post(OUTBOUND_URL, json=outbound(self.asset["id"], 2)).status_code, 201)
        self.assert_cold()
        self.assertEqual(self.stock(self.asset["id"]), 3)

    def test_a_new_asset_invalidates_the_list(self) -> None:
        self.warm()
        self.create(sku="EXAMPLE-NEW")
        self.assertEqual(len(self.client.get(PRODUCTS_URL).json()), 2)

    def test_failed_writes_do_not_invalidate(self) -> None:
        self.warm()
        failures = [
            # 400: salida mayor que el stock (0).
            (OUTBOUND_URL, outbound(self.asset["id"], 1), 400),
            # 400: la oficina no es la del activo.
            (INBOUND_URL, inbound(self.asset["id"]) | {"office": "Miami"}, 400),
            # 404: el activo no existe.
            (INBOUND_URL, inbound(999), 404),
            # 409: SKU repetido.
            (PRODUCTS_URL, valid_asset(), 409),
            # 422: cuerpo no válido.
            (INBOUND_URL, inbound(self.asset["id"]) | {"quantity": 0}, 422),
        ]
        for url, body, status in failures:
            with self.subTest(url=url, status=status):
                self.assertEqual(self.client.post(url, json=body).status_code, status)
                self.assertEqual(self.queries(PRODUCTS_URL), 0)
                self.assertEqual(self.queries(self.detail_url), 0)

    def test_the_stock_rule_is_checked_against_the_database_not_the_cache(self) -> None:
        self.client.post(INBOUND_URL, json=inbound(self.asset["id"], 5))
        self.assertEqual(self.stock(self.asset["id"]), 5)
        # Un cambio externo (como un seed): la caché sigue diciendo 5 hasta el TTL.
        self.add_orders_without_invalidating(self.asset["id"], exits=[4])
        self.assertEqual(self.stock(self.asset["id"]), 5)
        response = self.client.post(OUTBOUND_URL, json=outbound(self.asset["id"], 2))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Available: 1, requested: 2", response.json()["detail"])

    def add_orders_without_invalidating(self, asset_id: int, exits: list[int]) -> None:
        cache = self.app.state.response_cache
        invalidate = cache.invalidate
        cache.invalidate = lambda namespace: None
        try:
            self.add_orders(asset_id, entries=[], exits=exits)
        finally:
            cache.invalidate = invalidate


class AuthenticationTests(unittest.TestCase):
    def test_without_a_token_a_cached_route_is_still_401(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, TestClient(
            create_app(with_test_auth(Settings(), Path(tmp) / "auth.json"))
        ) as client:
            authorize(client)
            created = client.post(PRODUCTS_URL, json=valid_asset())
            self.assertEqual(created.status_code, 201)
            for url in (PRODUCTS_URL, f"{PRODUCTS_URL}/{created.json()['id']}"):
                self.assertEqual(client.get(url).status_code, 200)  # ya en caché
            client.headers.pop("Authorization")
            for url in (PRODUCTS_URL, f"{PRODUCTS_URL}/{created.json()['id']}"):
                with self.subTest(url=url):
                    self.assertEqual(client.get(url).status_code, 401)
            client.headers["Authorization"] = "Bearer not-a-valid-token"
            self.assertEqual(client.get(PRODUCTS_URL).status_code, 401)


if __name__ == "__main__":
    unittest.main()
