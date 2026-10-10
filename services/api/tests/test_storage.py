"""Almacenamiento TinyDB no disponible o corrupto → 503 `storage_unavailable` (A2 de la auditoría).

Cada test usa bases temporales fuera del repositorio (nunca services/api/data/).
El contenido corrupto incluye un email ficticio para comprobar que ni la
respuesta ni el registro reproducen el archivo, y la ruta temporal para
comprobar que no se filtra.
"""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import Response

from app.auth.models import ProfileFields, UserRole
from app.core.config import Settings
from app.core.errors import INTERNAL_ERROR_DETAIL, StorageUnavailableError
from app.core.storage import GuardedJSONStorage, Store
from app.main import create_app

from .support import authorize, capture_logs, with_test_auth

LEAK = "leak@example.invalid"
STORAGE_ERROR = {"detail": "storage is temporarily unavailable", "code": "storage_unavailable"}
SUPPLIERS_URL = "/suppliers"
INCIDENTS_URL = "/api/incidents"

# Contenidos que no son una base TinyDB legible.
CORRUPT_CONTENTS: dict[str, bytes] = {
    "invalid_json": f'{{"users": {{"1": {{"email": "{LEAK}"'.encode(),
    "not_utf8": b'{"users": "\xff\xfe' + LEAK.encode() + b'"}',
    "not_a_database": json.dumps([LEAK]).encode(),
    "table_is_not_an_object": json.dumps({"users": [LEAK]}).encode(),
}

VALID_SUPPLIER: dict[str, Any] = {
    "name": "Synthetic Supplier",
    "country": "Spain",
    "categories": ["job_boards"],
    "monthly_rate": 100.0,
    "currency": "EUR",
    "status": "active",
}


class StorageTestCase(unittest.TestCase):
    """Tres bases temporales sanas; cada test estropea la que necesita."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.paths = {
            Store.SUPPLIERS: self.dir / "suppliers.json",
            Store.AUTH: self.dir / "auth.json",
            Store.INCIDENTS: self.dir / "incidents.json",
        }
        settings = Settings(suppliers_db_path=self.paths[Store.SUPPLIERS], incidents_db_path=self.paths[Store.INCIDENTS])
        self.app = create_app(with_test_auth(settings, self.paths[Store.AUTH]))
        self.client = TestClient(self.app)
        authorize(self.client)  # crea auth.json sano y fija el JWT

    def corrupt(self, store: Store, content: bytes) -> None:
        self.paths[store].write_bytes(content)

    def assertUnavailable(self, response: Response, store: Store, logs: Any) -> None:
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json(), STORAGE_ERROR)
        for secret in (str(self.dir), self.paths[store].name, LEAK):
            self.assertNotIn(secret, response.text)
            self.assertNotIn(secret, logs.text())
        self.assertIn(f"storage {store.value} is unavailable:", logs.text())
        # Lo registra el storage, no el middleware del 500.
        self.assertNotIn("unhandled error", logs.text())


class CorruptStorageTests(StorageTestCase):
    def test_corrupt_suppliers_file(self) -> None:
        for name, content in CORRUPT_CONTENTS.items():
            with self.subTest(content=name):
                self.corrupt(Store.SUPPLIERS, content)
                for method, url, body in (
                    ("GET", SUPPLIERS_URL, None),
                    ("POST", SUPPLIERS_URL, VALID_SUPPLIER),
                    ("GET", f"{SUPPLIERS_URL}/1", None),
                ):
                    with self.subTest(method=method, url=url), capture_logs() as logs:
                        self.assertUnavailable(self.client.request(method, url, json=body), Store.SUPPLIERS, logs)

    def test_corrupt_incidents_file(self) -> None:
        for name, content in CORRUPT_CONTENTS.items():
            with self.subTest(content=name):
                self.corrupt(Store.INCIDENTS, content)
                for method, url, body in (
                    ("GET", INCIDENTS_URL, None),
                    ("GET", f"{INCIDENTS_URL}/summary", None),
                    ("GET", f"{INCIDENTS_URL}/{uuid4()}", None),
                    ("PATCH", f"{INCIDENTS_URL}/{uuid4()}/status", {"status": "in_progress"}),
                ):
                    with self.subTest(method=method, url=url), capture_logs() as logs:
                        self.assertUnavailable(self.client.request(method, url, json=body), Store.INCIDENTS, logs)

    def test_corrupt_auth_file(self) -> None:
        # Con auth.json corrupto fallan el login y toda ruta protegida (get_current_user lee la base).
        for name, content in CORRUPT_CONTENTS.items():
            with self.subTest(content=name):
                self.corrupt(Store.AUTH, content)
                with capture_logs() as logs:
                    response = self.client.post(
                        "/auth/login", data={"username": "someone@example.invalid", "password": "irrelevant-password"}
                    )
                self.assertUnavailable(response, Store.AUTH, logs)
                for url in ("/auth/me", SUPPLIERS_URL, INCIDENTS_URL):
                    with self.subTest(url=url), capture_logs() as logs:
                        self.assertUnavailable(self.client.get(url), Store.AUTH, logs)

    def test_database_path_that_cannot_be_opened(self) -> None:
        # Un directorio en lugar de un archivo: falla al abrirlo (OSError en JSONStorage.__init__).
        self.paths[Store.SUPPLIERS].mkdir()
        with capture_logs() as logs:
            self.assertUnavailable(self.client.get(SUPPLIERS_URL), Store.SUPPLIERS, logs)

    def test_write_failure(self) -> None:
        with mock.patch("tinydb.storages.JSONStorage.write", side_effect=OSError(28, "No space left", str(self.dir))):
            with capture_logs() as logs:
                self.assertUnavailable(self.client.post(SUPPLIERS_URL, json=VALID_SUPPLIER), Store.SUPPLIERS, logs)
        self.assertIn("OSError", logs.text())

    def test_the_503_does_not_carry_the_original_exception(self) -> None:
        self.corrupt(Store.SUPPLIERS, CORRUPT_CONTENTS["invalid_json"])
        storage = GuardedJSONStorage(str(self.paths[Store.SUPPLIERS]), store=Store.SUPPLIERS, encoding="utf-8")
        self.addCleanup(storage.close)
        with capture_logs(), self.assertRaises(StorageUnavailableError) as raised:
            storage.read()
        self.assertIsNone(raised.exception.__cause__)
        # Lanzado fuera del except: ni siquiera queda como __context__ (el JSONDecodeError guarda el archivo en .doc).
        self.assertIsNone(raised.exception.__context__)

    def test_a_sound_database_keeps_working(self) -> None:
        created = self.client.post(SUPPLIERS_URL, json=VALID_SUPPLIER)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(self.client.get(SUPPLIERS_URL).status_code, 200)
        self.assertEqual(self.client.get(INCIDENTS_URL).json(), [])


class ValidationIsNotAStorageErrorTests(StorageTestCase):
    """Regresión del ámbito de la captura: los errores del cuerpo del `with` no son 503."""

    def test_invalid_supplier_payload_is_still_422(self) -> None:
        response = self.client.post(SUPPLIERS_URL, json={**VALID_SUPPLIER, "monthly_rate": -1})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_invalid_incident_payload_is_still_400(self) -> None:
        response = self.client.post(INCIDENTS_URL, json={"title": ""})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_invalid_transition_inside_the_db_context_is_still_400(self) -> None:
        # InvalidStatusTransitionError (ValueError) se lanza dentro de `with self._db()`.
        created = self.client.post(
            INCIDENTS_URL,
            json={
                "title": "Synthetic incident",
                "description": "Synthetic description.",
                "category": "technical_failure",
                "origin": "internal",
                "branch": "central",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        response = self.client.patch(f"{INCIDENTS_URL}/{created.json()['id']}/status", json={"status": "resolved"})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "invalid_status_transition")

    def test_pydantic_error_inside_the_db_context_is_still_an_opaque_500(self) -> None:
        # Base TinyDB válida con un documento que no cumple el modelo: `_to_incident`
        # lanza ValidationError (subclase de ValueError) dentro de `with self._db()`.
        incident_id = str(uuid4())
        self.paths[Store.INCIDENTS].write_text(
            json.dumps({"incidents": {"1": {"id": incident_id, "title": LEAK, "status": "not-a-status"}}}),
            encoding="utf-8",
        )
        with capture_logs() as logs:
            response = self.client.patch(f"{INCIDENTS_URL}/{incident_id}/status", json={"status": "in_progress"})
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json(), {"detail": INTERNAL_ERROR_DETAIL, "code": "internal_error"})
        self.assertIn("ValidationError", logs.text())
        self.assertNotIn("storage", logs.text())

    def test_duplicate_email_is_still_409(self) -> None:
        service = self.app.state.user_service
        service.repository.create_user("dup@example.invalid", "x", UserRole.USER, ProfileFields())
        response = self.client.post("/users", json={"email": "dup@example.invalid", "password": "synthetic-pass-1"})
        self.assertEqual(response.status_code, 409, response.text)


if __name__ == "__main__":
    unittest.main()
