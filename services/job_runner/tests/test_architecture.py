"""job_runner es un proceso independiente de la API (criterio del enunciado)."""

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[2]
PACKAGE = SERVICES / "job_runner"
REPO = SERVICES.parent
SCRIPT = REPO / "scripts" / "nightly_export.py"
API_APP = SERVICES / "api" / "app"
FORBIDDEN_ROOTS = {"fastapi", "starlette", "uvicorn", "sqlmodel", "app"}
SCHEDULERS = re.compile(r"apscheduler|repeat_every|BackgroundScheduler|AsyncIOScheduler|\bcelery\b|import schedule|from schedule")


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class IndependenceTests(unittest.TestCase):
    def test_importing_job_runner_does_not_load_fastapi_or_the_api_app(self):
        """Proceso limpio (`-I`): tras importar todo el paquete, ni FastAPI ni `app` ni `app.main` en `sys.modules`."""
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "import job_runner, job_runner.migrate, job_runner.runner, job_runner.config, job_runner.logs;"
            "roots = {name.split('.')[0] for name in sys.modules};"
            f"bad = sorted(roots & set({sorted(FORBIDDEN_ROOTS)!r}));"
            "assert 'app.main' not in sys.modules;"
            "print('LOADED:' + ','.join(bad)) if bad else print('CLEAN')"
        )
        result = subprocess.run([sys.executable, "-I", "-c", code, str(SERVICES)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "CLEAN")

    def test_no_module_of_the_package_imports_fastapi_or_the_api(self):
        for path in sorted(PACKAGE.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertEqual(imported_roots(path) & FORBIDDEN_ROOTS, set())

    def test_the_package_does_not_import_the_data_pipelines_or_prefect(self):
        for path in sorted(PACKAGE.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertEqual(imported_roots(path) & {"prefect", "business_performance", "pipeline"}, set())

    def test_the_api_has_no_scheduler_inside_its_process(self):
        """El disparador nunca vive en FastAPI. `lifespan=inventory_lifespan` es legítimo y no cuenta."""
        offenders = [
            str(path.relative_to(SERVICES))
            for path in API_APP.rglob("*.py")
            if SCHEDULERS.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_the_package_never_prints(self):
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name == "migrate.py":  # la CLI de la migración imprime a propósito
                continue
            with self.subTest(module=path.name):
                calls = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                         if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "print"]
                self.assertEqual(calls, [])


class ScriptIndependenceTests(unittest.TestCase):
    def test_importing_the_nightly_script_does_not_load_fastapi_or_the_api_app(self):
        """Proceso limpio (`-I`): el script y todo lo que importa, sin FastAPI, `app` ni `app.main` (ni Prefect)."""
        code = (
            "import sys; sys.path[:0] = sys.argv[1:4];"
            "import nightly_export;"
            "roots = {name.split('.')[0] for name in sys.modules};"
            f"bad = sorted(roots & set({sorted(FORBIDDEN_ROOTS | {'prefect'})!r}));"
            "assert 'app.main' not in sys.modules;"
            "print('LOADED:' + ','.join(bad)) if bad else print('CLEAN')"
        )
        paths = [str(SCRIPT.parent), str(SERVICES), str(REPO / "packages" / "shared")]
        result = subprocess.run([sys.executable, "-I", "-c", code, *paths], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "CLEAN")

    def test_the_script_does_not_import_fastapi_the_api_or_the_pipeline_modules(self):
        self.assertEqual(imported_roots(SCRIPT) & (FORBIDDEN_ROOTS | {"prefect", "business_performance", "pipeline"}), set())

    def test_the_pipeline_never_reads_the_csv_export(self):
        """El CSV es backup, no input: el pipeline lee `telemetry_events` por SQL."""
        needle = re.compile(r"telemetry_[^\"'\s]*\.csv|raw[/\\]telemetry_|csv\.reader|DictReader|read_csv")
        offenders = []
        for folder in (REPO / "data" / "pipelines", REPO / "data" / "process"):
            for path in folder.rglob("*.py"):
                if ".venv" in path.parts or "tests" in path.parts or "__pycache__" in path.parts:
                    continue
                if needle.search(path.read_text(encoding="utf-8")):
                    offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(offenders, [])
        self.assertIn("FROM telemetry_events", (REPO / "data" / "pipelines" / "business_performance" / "repository.py").read_text(encoding="utf-8"))
