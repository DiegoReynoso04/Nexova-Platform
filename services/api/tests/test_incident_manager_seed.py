"""`scripts/seed_incidents.py` (F3): carga del CSV histórico en el gestor de incidencias.

Cada test usa una base TinyDB y CSV temporales: nunca toca services/api/data/
ni data/raw/. Solo datos ficticios (`example.invalid`).
"""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from nexova_shared.incidents import Branch, IncidentCategory, IncidentOrigin, IncidentStatus

from app.modules.incident_manager.repository import IncidentRepository

from .support import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "seed_incidents.py"
FIXTURES = REPO_ROOT / "packages" / "incident-analyzer" / "tests" / "fixtures"
ACCEPTANCE_FIXTURE = FIXTURES / "incidents-acceptance-synthetic.csv"
HEADER = "ticket_id,date,client_company,category,description,agent_id,status,customer_email,satisfaction_score"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_incidents", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_incidents = load_script()


class SeedScriptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.db = self.tmp / "incidents.json"

    def run_seed(self, *args: str | Path) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = seed_incidents.main([str(arg) for arg in args])
        return code, stdout.getvalue(), stderr.getvalue()

    def write_csv(self, *rows: str, header: str = HEADER, name: str = "incidents.csv") -> Path:
        path = self.tmp / name
        path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
        return path


class AcceptanceFixtureTests(SeedScriptTestCase):
    def test_first_run_inserts_96_and_reports_the_4_invalid_rows(self) -> None:
        code, out, err = self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            out.splitlines(),
            [
                "Archivo CSV: incidents-acceptance-synthetic.csv",
                f"Base de datos: {self.db}",
                "Filas leídas: 100",
                "Insertadas: 96",
                "Ya existentes (omitidas): 0",
                "Inválidas (no insertadas): 4",
                "  - fila 18: missing_client_company",
                "  - fila 45: invalid_category",
                "  - fila 71: invalid_email",
                "  - fila 93: closed_without_score",
                "No mapeables (no insertadas): 0",
                "Duplicadas en el archivo (no insertadas): 0",
                "Total de incidencias en la base: 96",
            ],
        )

    def test_second_run_inserts_nothing(self) -> None:
        self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        code, out, _ = self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        self.assertEqual(code, 0)
        self.assertIn("Insertadas: 0", out.splitlines())
        self.assertIn("Ya existentes (omitidas): 96", out.splitlines())
        self.assertIn("Total de incidencias en la base: 96", out.splitlines())
        self.assertEqual(len(IncidentRepository(self.db).find()), 96)

    def test_summary_after_the_seed_matches_the_context(self) -> None:
        self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        summary = IncidentRepository(self.db).summary().model_dump(mode="json")
        self.assertEqual(summary["total"], 96)
        self.assertEqual(summary["by_status"], {"open": 27, "in_progress": 0, "resolved": 56, "discarded": 13})
        expected_categories = {category.value: 0 for category in IncidentCategory}
        expected_categories.update({"technical_failure": 49, "process_error": 35, "client_complaint": 12})
        self.assertEqual(summary["by_category"], expected_categories)
        self.assertEqual(summary["by_origin"], {"customer": 96, "branch": 0, "internal": 0})
        self.assertEqual(summary["by_branch"], {"central": 96, "valencia_operations": 0, "miami_office": 0, "remote": 0})

    def test_every_seeded_incident_is_customer_and_central(self) -> None:
        self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        for incident in IncidentRepository(self.db).find():
            self.assertEqual((incident.origin, incident.branch), (IncidentOrigin.CUSTOMER, Branch.CENTRAL))
            self.assertLessEqual(len(incident.title), 120)

    def test_database_holds_no_emails_or_ticket_ids(self) -> None:
        self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        raw = self.db.read_text(encoding="utf-8")
        self.assertNotIn("@", raw)
        self.assertNotIn("ticket_id", raw)
        self.assertNotIn("NXV-", raw)
        self.assertNotIn("example.invalid", raw)
        self.assertNotIn("AGT-", raw)


class ReportTests(SeedScriptTestCase):
    def test_unmapped_and_duplicated_rows_are_reported_by_row_number(self) -> None:
        csv_file = self.write_csv(
            "T-1,2026-08-01,Synthetic Client,TECHNICAL,Synthetic printer issue,AGT-01,OPEN,a@example.invalid,",
            "T-2,2026-08-01,Synthetic Client,BILLING,Synthetic invoice issue,AGT-02,PENDING,b@example.invalid,",
            "T-3,01/08/2026,Synthetic Client,ACCESS,Synthetic access issue,AGT-03,OPEN,c@example.invalid,",
            "T-1,2026-08-02,Synthetic Client,COMPLAINT,Synthetic repeated id,AGT-04,OPEN,d@example.invalid,",
        )
        code, out, _ = self.run_seed(csv_file, "--db", self.db)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertIn("Insertadas: 1", lines)
        self.assertIn("No mapeables (no insertadas): 2", lines)
        self.assertIn("  - fila 3: unmapped_status", lines)
        self.assertIn("  - fila 4: invalid_date", lines)
        self.assertIn("Duplicadas en el archivo (no insertadas): 1", lines)
        self.assertIn("  - fila 5", lines)

    def test_report_never_shows_row_content(self) -> None:
        csv_file = self.write_csv(
            "NXV-777,2026-08-01,Hidden Client,TECHNICAL,Hidden description text,AGT-01,OPEN,leak@example.invalid,",
            "NXV-778,2026-08-01,,TECHNICAL,Hidden description text,AGT-01,OPEN,leak@example.invalid,",
            "NXV-779,bad-date,Hidden Client,TECHNICAL,Hidden description text,AGT-01,OPEN,leak@example.invalid,",
        )
        code, out, err = self.run_seed(csv_file, "--db", self.db)
        self.assertEqual(code, 0)
        for text in (out, err):
            for secret in ("leak", "@", "Hidden", "NXV-", "AGT-"):
                self.assertNotIn(secret, text)


class ExitCodeTests(SeedScriptTestCase):
    def test_missing_csv(self) -> None:
        code, out, err = self.run_seed(self.tmp / "missing.csv", "--db", self.db)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("CSV file not found", err)
        self.assertFalse(self.db.exists())

    def test_header_of_another_schema(self) -> None:
        csv_file = self.write_csv("Synthetic,Text,other,open,internal,central", header="title,description,category,status,origin,branch")
        code, out, err = self.run_seed(csv_file, "--db", self.db)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("missing required columns", err)
        self.assertFalse(self.db.exists())

    def test_empty_file(self) -> None:
        csv_file = self.tmp / "empty.csv"
        csv_file.write_bytes(b"")
        code, _, err = self.run_seed(csv_file, "--db", self.db)
        self.assertEqual(code, 1)
        self.assertIn("no header row", err)

    def test_not_utf8(self) -> None:
        csv_file = self.tmp / "latin1.csv"
        csv_file.write_bytes((HEADER + "\nT-1,2026-08-01,Cliente Ñ,TECHNICAL,Descripción,AGT-01,OPEN,x@example.invalid,\n").encode("latin-1"))
        code, _, err = self.run_seed(csv_file, "--db", self.db)
        self.assertEqual(code, 1)
        self.assertIn("not valid UTF-8", err)
        self.assertNotIn("x@example.invalid", err)

    def test_read_error_without_strerror_shows_the_class_name(self) -> None:
        # S4 aplicado también aquí: un OSError sin errno no debe imprimir "None".
        with mock.patch.object(seed_incidents, "read_batch", side_effect=OSError()):
            code, out, err = self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        self.assertEqual((code, out), (1, ""))
        self.assertIn(f"error: cannot read {ACCEPTANCE_FIXTURE}: OSError", err)
        self.assertNotIn("None", err)
        self.assertFalse(self.db.exists())

    def test_header_only_is_a_valid_empty_load(self) -> None:
        code, out, _ = self.run_seed(self.write_csv(), "--db", self.db)
        self.assertEqual(code, 0)
        self.assertIn("Insertadas: 0", out.splitlines())
        self.assertIn("Total de incidencias en la base: 0", out.splitlines())


class StorageErrorTests(SeedScriptTestCase):
    """S1 de la auditoría: una base que no se puede abrir o está corrupta → código 2, sin traceback."""

    def assertStorageError(self, code: int, out: str, err: str) -> None:
        self.assertEqual((code, out), (2, ""))
        self.assertIn("error: cannot open or write the incidents database (incidents.json)", err)
        # Línea de log_storage_failure (handler de último recurso de logging): almacén y clase.
        self.assertIn("storage incidents is unavailable:", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn(str(self.tmp), err)

    def test_database_path_is_a_directory(self) -> None:
        self.db.mkdir()
        self.assertStorageError(*self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db))

    def test_corrupt_database(self) -> None:
        self.db.write_text('{"incidents": {"1": {"title": "leak@example.invalid"', encoding="utf-8")
        code, out, err = self.run_seed(ACCEPTANCE_FIXTURE, "--db", self.db)
        self.assertStorageError(code, out, err)
        self.assertIn("JSONDecodeError", err)
        self.assertNotIn("leak@example.invalid", err)


class DefaultsTests(SeedScriptTestCase):
    def test_default_csv_is_the_ignored_raw_dataset(self) -> None:
        self.assertEqual(seed_incidents.DEFAULT_CSV, REPO_ROOT / "data" / "raw" / "incidents" / "incidents-nexova.csv")
        self.assertEqual(seed_incidents.parse_args([]).csv_file, seed_incidents.DEFAULT_CSV)

    def test_database_from_incidents_db_path(self) -> None:
        with mock.patch.dict("os.environ", {"INCIDENTS_DB_PATH": str(self.db)}):
            code, out, _ = self.run_seed(ACCEPTANCE_FIXTURE)
        self.assertEqual(code, 0)
        self.assertIn(f"Base de datos: {self.db}", out.splitlines())
        self.assertEqual(IncidentRepository(self.db).summary().by_status[IncidentStatus.OPEN], 27)


if __name__ == "__main__":
    unittest.main()
