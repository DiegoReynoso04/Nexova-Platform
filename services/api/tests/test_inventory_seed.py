"""Hito 5, F4: `seed-inventory` sobre una SQLite temporal y una TinyDB de usuarios temporal.

Nunca toca Supabase ni services/api/data/. Incluye el caso del evaluador:
después del seed, `GET /inventory/products` devuelve exactamente el neto
sembrado.
"""

import contextlib
import dataclasses
import io
import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.auth.models import ProfileFields, UserInDB, UserRole
from app.auth.repository import AuthRepository
from app.auth.security import hash_password
from app.core.config import Settings
from app.main import create_app
from app.modules.inventory import seed
from app.modules.inventory.database import build_engine, init_db
from app.modules.inventory.models import Asset, AssetEntry, AssetExit

from .support import SERVICE_ROOT, authorize, with_test_auth

SEED_EMAIL = "seed-user@example.invalid"
EXPECTED_PRODUCTS = [
    {"id": 1, "name": 'Portátil 14" Business', "sku": "NXV-IT-001", "category": "hardware", "office": "Valencia", "current_stock": 13},
    {"id": 2, "name": 'Portátil 14" Business', "sku": "NXV-IT-002", "category": "hardware", "office": "Miami", "current_stock": 0},
    {"id": 3, "name": "Ratón ergonómico", "sku": "NXV-PER-001", "category": "peripherals", "office": "Valencia", "current_stock": 0},
    {"id": 4, "name": "Hub USB-C", "sku": "NXV-PER-002", "category": "peripherals", "office": "Miami", "current_stock": 7},
    {"id": 5, "name": "Resma de papel A4", "sku": "NXV-OFF-001", "category": "office_supplies", "office": "Valencia", "current_stock": 15},
    {
        "id": 6,
        "name": "Cuaderno de formación en liderazgo",
        "sku": "NXV-TRN-001",
        "category": "training_materials",
        "office": "Valencia",
        "current_stock": 0,
    },
]
EXPECTED_STOCK_LINES = [f"  {item['sku']}: {item['current_stock']}" for item in EXPECTED_PRODUCTS]
# Credenciales ficticias de una base inalcanzable (puerto local cerrado).
DB_USER, DB_PASSWORD, DB_NAME, DB_HOST = "probeuser", "probe-secret-value", "probedb", "localhost"
UNREACHABLE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:9/{DB_NAME}"
SECRETS = (DB_USER, DB_PASSWORD, DB_NAME, DB_HOST)
LEAKS = (*SECRETS, "postgresql://", "psycopg2", "Traceback")


class SeedTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.auth_path = self.dir / "auth.json"
        self.database_url = f"sqlite:///{(self.dir / 'inventory.db').as_posix()}"
        self.settings = Settings(auth_db_path=self.auth_path, database_url=self.database_url)
        self.user = self.add_user(SEED_EMAIL)

    def add_user(self, email: str) -> UserInDB:
        user, _ = AuthRepository(self.auth_path).create_user(
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(16)),
            role=UserRole.USER,
            profile=ProfileFields(),
        )
        return user

    def run_seed(self, *argv: str, settings: Settings | None = None) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = seed.run(list(argv) or ["--email", SEED_EMAIL], settings=settings or self.settings)
        return code, stdout.getvalue(), stderr.getvalue()

    def counts(self) -> tuple[int, int, int]:
        engine = build_engine(self.database_url)
        try:
            init_db(engine)
            with Session(engine) as session:
                return tuple(  # type: ignore[return-value]
                    session.exec(select(func.count()).select_from(model)).one() for model in (Asset, AssetEntry, AssetExit)
                )
        finally:
            engine.dispose()

    def api(self) -> TestClient:
        settings = dataclasses.replace(with_test_auth(Settings(), self.auth_path), database_url=self.database_url)
        client = TestClient(create_app(settings))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        authorize(client)
        return client


class SeedRunTests(SeedTestCase):
    def test_first_run_inserts_everything_and_second_run_inserts_nothing(self) -> None:
        code, out, err = self.run_seed()
        self.assertEqual((code, err), (0, ""))
        for line in (
            f"Órdenes a nombre del usuario {self.user.id}",
            "Activos insertados: 6",
            "Activos ya existentes (omitidos): 0",
            "Entradas insertadas: 4",
            "Salidas insertadas: 3",
            *EXPECTED_STOCK_LINES,
        ):
            self.assertIn(line, out.splitlines())
        self.assertEqual(self.counts(), (6, 4, 3))

        code, out, err = self.run_seed()
        self.assertEqual((code, err), (0, ""))
        for line in ("Activos insertados: 0", "Activos ya existentes (omitidos): 6", "Entradas insertadas: 0", "Salidas insertadas: 0"):
            self.assertIn(line, out.splitlines())
        # Los 3 activos con órdenes en el seed (IT-001, PER-002, OFF-001).
        self.assertIn("Activos que ya tenían órdenes (no se les añade ninguna): 3", out.splitlines())
        self.assertEqual(self.counts(), (6, 4, 3))
        self.assertNotIn(SEED_EMAIL, out)

    def test_products_reflect_the_seeded_net_stock(self) -> None:
        # Caso del evaluador.
        self.assertEqual(self.run_seed()[0], 0)
        client = self.api()
        self.assertEqual(client.get("/inventory/products").json(), EXPECTED_PRODUCTS)

    def test_orders_are_registered_to_the_seed_user(self) -> None:
        self.assertEqual(self.run_seed()[0], 0)
        orders = self.api().get("/inventory/orders").json()
        self.assertEqual(len(orders), 7)
        self.assertEqual({order["user_uuid"] for order in orders}, {str(self.user.id)})
        self.assertEqual(sorted(order["type"] for order in orders), ["inbound"] * 4 + ["outbound"] * 3)
        exits = {(order["asset"]["sku"], order["exit_type"], order["assigned_to"]) for order in orders if order["type"] == "outbound"}
        self.assertEqual(
            exits,
            {
                ("NXV-IT-001", "allocation", "EMPLEADO-FICTICIO-01"),
                ("NXV-OFF-001", "consumption", None),
                ("NXV-PER-002", "allocation", "EMPLEADO-FICTICIO-02"),
            },
        )
        suppliers = sorted((order["asset"]["sku"], order["quantity"], order["supplier"]) for order in orders if order["type"] == "inbound")
        self.assertEqual(
            suppliers,
            [
                ("NXV-IT-001", 5, "TechDistrib Valencia S.L."),
                ("NXV-IT-001", 10, "TechDistrib Valencia S.L."),
                ("NXV-OFF-001", 20, "TechDistrib Valencia S.L."),
                ("NXV-PER-002", 8, "Office Depot Miami"),
            ],
        )

    def test_existing_assets_with_orders_are_not_duplicated(self) -> None:
        engine = build_engine(self.database_url)
        init_db(engine)
        with Session(engine) as session:
            laptop = Asset(name="Existing laptop", sku="NXV-IT-001", category="hardware", office="Valencia")
            session.add(laptop)
            session.flush()
            session.add(AssetEntry(asset_id=laptop.id, quantity=3, supplier="Earlier supplier", office="Valencia", user_uuid=str(self.user.id)))
            session.commit()
        engine.dispose()

        code, out, _ = self.run_seed()
        self.assertEqual(code, 0)
        for line in (
            "Activos insertados: 5",
            "Activos ya existentes (omitidos): 1",
            "Entradas insertadas: 2",
            "Salidas insertadas: 2",
            "Activos que ya tenían órdenes (no se les añade ninguna): 1",
            "  NXV-IT-001: 3",
        ):
            self.assertIn(line, out.splitlines())
        self.assertEqual(self.counts(), (6, 3, 2))
        products = {item["sku"]: item for item in self.api().get("/inventory/products").json()}
        self.assertEqual(products["NXV-IT-001"]["name"], "Existing laptop")
        self.assertEqual(products["NXV-IT-001"]["current_stock"], 3)

    def test_seed_data_that_breaks_the_stock_rule_writes_nothing(self) -> None:
        exits = [*seed.SEED_EXITS, {"sku": "NXV-IT-001", "quantity": 99, "exit_type": "consumption", "assigned_to": None}]
        with mock.patch.object(seed, "SEED_EXITS", exits):
            code, out, err = self.run_seed()
        self.assertEqual((code, out), (1, ""))
        self.assertIn(
            "Error en los datos semilla: orden de NXV-IT-001: "
            "Insufficient stock for asset 'Portátil 14\" Business'. Available: 13, requested: 99. No se ha cargado nada.",
            err,
        )
        # Una sola transacción: ni los activos ni las órdenes anteriores quedan escritos.
        self.assertEqual(self.counts(), (0, 0, 0))


class SeedErrorTests(SeedTestCase):
    def assertFails(self, result: tuple[int, str, str], code: int, message: str) -> None:
        actual_code, out, err = result
        self.assertEqual(actual_code, code, err)
        self.assertEqual(out, "")
        self.assertIn(message, err)
        self.assertNotIn("Traceback", err)

    def test_unknown_email_is_1_without_repeating_it(self) -> None:
        for email in ("nobody@example.invalid", "not-an-email"):
            with self.subTest(email=email):
                code, out, err = self.run_seed("--email", email)
                self.assertFails((code, out, err), 1, "no existe ningún usuario activo con ese email")
                self.assertNotIn(email, err)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_email_is_matched_like_the_login(self) -> None:
        self.assertEqual(self.run_seed("--email", "  Seed-User@Example.Invalid ")[0], 0)

    def test_inactive_user_is_1(self) -> None:
        AuthRepository(self.auth_path).update_user(str(self.user.id), {"is_active": False})
        self.assertFails(self.run_seed(), 1, "no existe ningún usuario activo con ese email")

    def test_missing_or_invalid_database_url_is_1(self) -> None:
        for environ in ({}, {"DATABASE_URL": "sqlite:///inventory.db"}, {"DATABASE_URL": f"mysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/x"}):
            with self.subTest(environ=environ), mock.patch.dict(
                os.environ, {"AUTH_DB_PATH": str(self.auth_path), **environ}, clear=True
            ):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = seed.run(["--email", SEED_EMAIL])
                self.assertFails((code, stdout.getvalue(), stderr.getvalue()), 1, "Error de configuración: DATABASE_URL")
                # El mensaje nombra los esquemas aceptados, nunca la URL recibida.
                for leaked in SECRETS:
                    self.assertNotIn(leaked, stderr.getvalue())

    def test_unreachable_database_is_2_without_connection_details(self) -> None:
        settings = dataclasses.replace(self.settings, database_url=UNREACHABLE_URL)
        code, out, err = self.run_seed(settings=settings)
        self.assertFails(
            (code, out, err), 2, "Error: la base de datos del inventario no está disponible (OperationalError). No se ha cargado nada."
        )
        for leaked in LEAKS:
            self.assertNotIn(leaked, err)

    def test_unreadable_users_database_is_2(self) -> None:
        self.auth_path.write_text("not json", encoding="utf-8")
        code, out, err = self.run_seed()
        self.assertFails((code, out, err), 2, "no se pudo leer la base de usuarios (auth.json)")
        self.assertNotIn(str(self.dir), err)


class SeedCommandTests(SeedTestCase):
    def test_command_with_the_database_down_exits_2_and_leaks_nothing(self) -> None:
        env = {
            **os.environ,
            "DATABASE_URL": UNREACHABLE_URL,
            "AUTH_DB_PATH": str(self.auth_path),
            "PYTHONIOENCODING": "utf-8",
        }
        result = subprocess.run(
            [sys.executable, "-m", "app.modules.inventory.seed", "--email", SEED_EMAIL],
            cwd=SERVICE_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("la base de datos del inventario no está disponible (OperationalError)", result.stderr)
        for leaked in (*LEAKS, SEED_EMAIL):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, result.stderr)

    def test_email_is_required_and_is_a_configuration_error(self) -> None:
        # argparse terminaría con 2, que aquí significa «base no disponible».
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(seed.run([], settings=self.settings), 1)
        self.assertIn("--email", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
