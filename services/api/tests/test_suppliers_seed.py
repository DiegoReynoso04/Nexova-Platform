"""Seeder idempotente y persistencia de TinyDB entre reinicios."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import seed
from app.database import SupplierRepository
from app.seed import SUPPLIERS_SEED, run_seed

from .suppliers_support import SUPPLIERS_URL, SupplierTestCase, context_definitions


class SeedDataTests(unittest.TestCase):
    def test_seed_is_exactly_the_context_one(self) -> None:
        self.assertEqual(SUPPLIERS_SEED, context_definitions()["SUPPLIERS_SEED"])
        self.assertEqual(len(SUPPLIERS_SEED), 15)


class SeederTests(SupplierTestCase):
    def repository(self) -> SupplierRepository:
        return SupplierRepository(self.db_path, clock=self.clock)

    def test_first_run_inserts_all_suppliers_as_defined(self) -> None:
        result = run_seed(self.repository())
        self.assertEqual((result.inserted, result.skipped, result.total), (15, 0, 15))
        stored = {s["name"]: s for s in self.client.get(SUPPLIERS_URL).json()}
        for record in SUPPLIERS_SEED:
            with self.subTest(name=record["name"]):
                supplier = stored[record["name"]]
                # Mismos valores que el CONTEXT; los opcionales ausentes quedan en null.
                for field in ("contract_renewal_date", "contact_email", "notes"):
                    self.assertEqual(supplier[field], record.get(field))
                for field, value in record.items():
                    self.assertEqual(supplier[field], value)
                self.assertEqual(supplier["updated_at"], self.clock.now.isoformat().replace("+00:00", "Z"))

    def test_second_run_does_not_duplicate(self) -> None:
        run_seed(self.repository())
        result = run_seed(self.repository())
        self.assertEqual((result.inserted, result.skipped, result.total), (0, 15, 15))
        self.assertEqual(self.count(), 15)

    def test_existing_suppliers_are_not_overwritten(self) -> None:
        run_seed(self.repository())
        workable = next(s for s in self.client.get(SUPPLIERS_URL).json() if s["name"] == "Workable")
        self.client.patch(f"{SUPPLIERS_URL}/{workable['id']}/rate", json={"monthly_rate": 349.0})
        run_seed(self.repository())
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/{workable['id']}").json()["monthly_rate"], 349.0)

    def test_only_missing_suppliers_are_inserted(self) -> None:
        run_seed(self.repository())
        greenhouse = next(s for s in self.client.get(SUPPLIERS_URL).json() if s["name"] == "Greenhouse")
        self.client.delete(f"{SUPPLIERS_URL}/{greenhouse['id']}")
        self.create(name="Synthetic Supplier")
        result = run_seed(self.repository())
        self.assertEqual((result.inserted, result.skipped, result.total), (1, 14, 16))

    def test_main_reports_inserted_count(self) -> None:
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"SUPPLIERS_DB_PATH": str(self.db_path)}), contextlib.redirect_stdout(output):
            seed.main()
            seed.main()
        text = output.getvalue()
        self.assertIn("Proveedores insertados: 15", text)
        self.assertIn("Proveedores insertados: 0", text)
        self.assertIn("Ya existentes (omitidos): 15", text)
        self.assertIn("Total en el directorio: 15", text)


class SeedMainErrorTests(unittest.TestCase):
    """S2 de la auditoría: `uv run seed` termina con código 1 y sin traceback."""

    SECRET = "re_secret_value_that_must_not_be_printed"
    EMAIL_VARIABLES = ("RESEND_API_KEY", "EMAIL_FROM", "PASSWORD_RESET_URL")

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.db_path = self.tmp / "suppliers.json"

    def run_main(self, environ: dict[str, str]) -> tuple[int | str | None, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, environ):
            for name in self.EMAIL_VARIABLES:
                if name not in environ:
                    os.environ.pop(name, None)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    seed.main()
        return raised.exception.code, stdout.getvalue(), stderr.getvalue()

    def test_incomplete_email_configuration(self) -> None:
        code, out, err = self.run_main({"SUPPLIERS_DB_PATH": str(self.db_path), "RESEND_API_KEY": self.SECRET})
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Error de configuración: RESEND_API_KEY, EMAIL_FROM and PASSWORD_RESET_URL must be set together", err)
        self.assertNotIn(self.SECRET, err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(self.db_path.exists())

    def test_corrupt_database(self) -> None:
        self.db_path.write_text('{"suppliers": {"1": {"contact_email": "leak@example.invalid"', encoding="utf-8")
        code, out, err = self.run_main({"SUPPLIERS_DB_PATH": str(self.db_path)})
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Error: no se pudo abrir o escribir la base de proveedores (suppliers.json)", err)
        self.assertIn("storage suppliers is unavailable: JSONDecodeError", err)
        for secret in ("Traceback", str(self.tmp), "leak@example.invalid"):
            self.assertNotIn(secret, err)


class PersistenceTests(SupplierTestCase):
    def test_data_survives_an_api_restart(self) -> None:
        self.seed()
        created = self.create(name="Synthetic Supplier", monthly_rate=10)
        self.client.patch(f"{SUPPLIERS_URL}/{created['id']}/rate", json={"monthly_rate": 20})
        self.client.patch(f"{SUPPLIERS_URL}/{created['id']}/status", json={"status": "suspended"})
        before = self.client.get(SUPPLIERS_URL).json()

        restarted = self.make_client()  # nueva app, mismo archivo
        self.assertEqual(restarted.get(SUPPLIERS_URL).json(), before)
        detail = restarted.get(f"{SUPPLIERS_URL}/{created['id']}").json()
        self.assertEqual((detail["monthly_rate"], detail["status"]), (20.0, "suspended"))

    def test_database_is_a_readable_json_file(self) -> None:
        self.seed()
        content = json.loads(self.db_path.read_text(encoding="utf-8"))
        self.assertEqual(len(content["suppliers"]), 15)


if __name__ == "__main__":
    unittest.main()
