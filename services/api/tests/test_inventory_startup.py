"""Hito 5, F2: arranque cuando la base del inventario no responde.

- En proceso: `with TestClient(app)` lanza `InventoryStartupError`, sin la
  excepción original encadenada, y el proceso del test sigue vivo.
- Con uvicorn real, en un subproceso: `DATABASE_URL` apunta a un puerto local
  cerrado (nunca a Supabase). uvicorn no arranca y nada de lo que imprimen
  psycopg2, Starlette o uvicorn lleva el host, el usuario, la contraseña, la
  base ni la URL.
"""

import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.main import create_app
from app.modules.inventory import database
from app.modules.inventory.database import InventoryStartupError, build_engine, init_db

from .support import SERVICE_ROOT, TEST_DATABASE_URL, with_test_auth

# Credenciales ficticias; el puerto 9 (discard) no tiene nada escuchando en local.
DB_USER = "probeuser"
DB_PASSWORD = "probe-secret-value"
DB_NAME = "probedb"
DB_HOST = "localhost"
UNREACHABLE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:9/{DB_NAME}"
LEAKS = (DB_USER, DB_PASSWORD, DB_NAME, DB_HOST, "postgresql://", "psycopg2")
EXPECTED_MESSAGE = "inventory database is unavailable at startup: OperationalError"
UVICORN = (
    "import uvicorn; "
    "uvicorn.run('app.main:create_app', factory=True, host='127.0.0.1', port=0, log_level='info')"
)
# uvicorn termina con 3 (`STARTUP_FAILURE`) cuando falla el lifespan.
UVICORN_STARTUP_FAILURE = 3


def database_down() -> OperationalError:
    orig = Exception(f'connection to server at "{DB_HOST}" failed for user "{DB_USER}" ({DB_PASSWORD})')
    return OperationalError(f"SELECT 1 FROM {DB_NAME}", {"password": DB_PASSWORD}, orig)


class InProcessStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings = with_test_auth(Settings(), Path(tmp.name) / "auth.json")

    def assertClean(self, error: InventoryStartupError) -> None:
        self.assertEqual(str(error), EXPECTED_MESSAGE)
        self.assertEqual(error.error_class, "OperationalError")
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        for leaked in LEAKS:
            self.assertNotIn(leaked, repr(error))

    def test_init_db_raises_only_the_error_class(self) -> None:
        engine = build_engine(TEST_DATABASE_URL)
        self.addCleanup(engine.dispose)
        with (
            mock.patch.object(database, "enable_row_level_security", side_effect=database_down()),
            self.assertRaises(InventoryStartupError) as caught,
        ):
            init_db(engine)
        self.assertClean(caught.exception)

    def test_test_client_startup_fails_and_the_process_survives(self) -> None:
        app = create_app(self.settings)
        engine = app.state.inventory_engine
        with (
            mock.patch.object(database, "enable_row_level_security", side_effect=database_down()),
            mock.patch.object(engine, "dispose", wraps=engine.dispose) as dispose,
            self.assertRaises(InventoryStartupError) as caught,
            TestClient(app),
        ):
            pass  # pragma: no cover — el arranque no llega a terminar
        self.assertClean(caught.exception)
        # El motor se libera también tras el arranque fallido.
        dispose.assert_called_once_with()
        # El proceso del test sigue vivo: otra app arranca y responde.
        healthy = create_app(self.settings)
        with TestClient(healthy) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertIn("assets", inspect(healthy.state.inventory_engine).get_table_names())


class UvicornStartupWithoutDatabaseTests(unittest.TestCase):
    def test_uvicorn_does_not_start_and_leaks_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                **os.environ,
                "JWT_SECRET_KEY": secrets.token_urlsafe(48),
                "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
                "DATABASE_URL": UNREACHABLE_URL,
                # Nunca services/api/data/.
                "AUTH_DB_PATH": str(Path(tmp) / "auth.json"),
                "SUPPLIERS_DB_PATH": str(Path(tmp) / "suppliers.json"),
                "INCIDENTS_DB_PATH": str(Path(tmp) / "incidents.json"),
            }
            result = subprocess.run(
                [sys.executable, "-c", UVICORN],
                cwd=SERVICE_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, UVICORN_STARTUP_FAILURE, output)
        self.assertIn(f"InventoryStartupError: {EXPECTED_MESSAGE}", output)
        self.assertIn("Application startup failed", output)
        self.assertNotIn("Application startup complete", output)
        for leaked in LEAKS:
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, output)
        # La traza es solo la de InventoryStartupError: nada de la excepción original.
        self.assertNotIn("During handling of the above exception", output)
        self.assertNotIn("The above exception was the direct cause", output)


if __name__ == "__main__":
    unittest.main()
