"""Soporte de los tests del inventario (Hito 5): app real con SQLite en memoria.

`with TestClient` ejecuta el lifespan (crea las tablas). Datos ficticios.
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, func, select

from app.auth.models import UserInDB
from app.core.config import Settings
from app.main import create_app
from app.modules.inventory.models import Asset, AssetEntry, AssetExit

from .support import authorize, with_test_auth

PRODUCTS_URL = "/inventory/products"
ORDERS_URL = "/inventory/orders"
INBOUND_URL = "/inventory/orders/inbound"
OUTBOUND_URL = "/inventory/orders/outbound"
USER_UUID = "00000000-0000-4000-8000-000000000000"


def valid_asset(**changes: Any) -> dict[str, Any]:
    return {"name": "Example laptop", "sku": "EXAMPLE-001", "category": "hardware", "office": "Valencia"} | changes


def inventory_app() -> tuple[Any, tempfile.TemporaryDirectory[str]]:
    tmp = tempfile.TemporaryDirectory()
    return create_app(with_test_auth(Settings(), Path(tmp.name) / "auth.json")), tmp


class InventoryTestCase(unittest.TestCase):
    """App real con SQLite en memoria, lifespan ejecutado y un usuario autenticado."""

    user: UserInDB

    def setUp(self) -> None:
        self.app, tmp = inventory_app()
        self.addCleanup(tmp.cleanup)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.user = authorize(self.client)

    @property
    def engine(self) -> Any:
        return self.app.state.inventory_engine

    def create(self, **changes: Any) -> dict[str, Any]:
        response = self.client.post(PRODUCTS_URL, json=valid_asset(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def add_orders(self, asset_id: int, entries: list[int], exits: list[int], office: str = "Valencia") -> None:
        """Inserta órdenes directamente con la sesión (sin pasar por las rutas)."""
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

    def stock(self, asset_id: int) -> int:
        response = self.client.get(f"{PRODUCTS_URL}/{asset_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["current_stock"]

    def count_queries(self, method: str, url: str, **kwargs: Any) -> int:
        statements: list[str] = []

        def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record)
        try:
            response = self.client.request(method, url, **kwargs)
            self.assertLess(response.status_code, 300, response.text)
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        return len(statements)
