"""La API no lleva el ETL ni Prefect: comprobaciones estáticas (AST y archivos de build).

- `services/reporting/` no importa `prefect`, `pandas`, el flow (`pipeline`), la
  transformación (`weekly_performance`) ni nada de `business_performance` salvo
  `trigger`, y su SQL no escribe.
- `data/pipelines/business_performance/trigger.py` solo usa la librería estándar.
- La imagen y Compose solo meten en la API `business_performance/__init__.py` y
  `trigger.py`; el `__init__` no importa nada.
- Prefect no está en `services/api` (ni en `pyproject.toml` ni en `uv.lock`).
"""

import ast
import re
import sys
import tomllib
import unittest

from .support import APP_DIR, REPO_ROOT, SERVICE_ROOT

REPORTING_DIR = REPO_ROOT / "services" / "reporting"
BUSINESS_PERFORMANCE_DIR = REPO_ROOT / "data" / "pipelines" / "business_performance"
TRIGGER = BUSINESS_PERFORMANCE_DIR / "trigger.py"
FORBIDDEN_ROOTS = {"prefect", "pandas", "pipeline", "weekly_performance"}
WRITE_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|DROP|ALTER|GRANT|REVOKE)\b", re.IGNORECASE)


def imports(path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def string_constants(path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


class ReportingHasNoEtlTests(unittest.TestCase):
    def test_reporting_sources_exist(self):
        self.assertEqual({path.name for path in REPORTING_DIR.glob("*.py")},
                         {"__init__.py", "reads.py", "router.py", "schemas.py"})

    def test_no_prefect_pandas_or_flow_imports(self):
        for path in REPORTING_DIR.glob("*.py"):
            for module in imports(path):
                with self.subTest(file=path.name, module=module):
                    self.assertNotIn(module.split(".")[0], FORBIDDEN_ROOTS)
                    if module.startswith("business_performance"):
                        self.assertEqual(module, "business_performance.trigger")

    def test_reporting_sql_only_reads(self):
        for path in REPORTING_DIR.glob("*.py"):
            for constant in string_constants(path):
                with self.subTest(file=path.name, sql=constant[:50]):
                    self.assertIsNone(WRITE_SQL.search(constant))

    def test_the_api_app_does_not_import_prefect_or_the_pipeline(self):
        for path in APP_DIR.rglob("*.py"):
            for module in imports(path):
                with self.subTest(file=str(path.relative_to(APP_DIR)), module=module):
                    self.assertNotIn(module.split(".")[0], {"prefect", "pipeline", "weekly_performance"})
                    self.assertFalse(module.startswith("business_performance"))


class TriggerIsStandardLibraryTests(unittest.TestCase):
    def test_trigger_only_imports_the_standard_library(self):
        for module in imports(TRIGGER):
            with self.subTest(module=module):
                self.assertIn(module.split(".")[0], sys.stdlib_module_names | {"__future__"})
        relative = [node for node in ast.walk(ast.parse(TRIGGER.read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom) and node.level > 0]
        self.assertEqual(relative, [])

    def test_package_init_imports_nothing(self):
        tree = ast.parse((BUSINESS_PERFORMANCE_DIR / "__init__.py").read_text(encoding="utf-8"))
        self.assertEqual([node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))], [])


class ApiImageTests(unittest.TestCase):
    def test_image_copies_only_the_trigger_from_the_pipeline(self):
        dockerfile = (REPO_ROOT / "services" / "Dockerfile").read_text(encoding="utf-8")
        copies = [line for line in dockerfile.splitlines() if line.startswith("COPY --from=pipelines")]
        self.assertEqual(copies, [
            "COPY --from=pipelines business_performance/__init__.py business_performance/trigger.py "
            "/pipelines/business_performance/"])

    def test_compose_mounts_only_the_trigger_in_the_api(self):
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        api = compose[compose.index("\n  api:"):compose.index("\n  ui:")]
        mounts = {line.strip() for line in api.splitlines() if "./data/" in line}
        self.assertEqual(mounts, {
            "pipelines: ./data/pipelines",  # el contexto de build (la imagen copia solo los dos archivos)
            "- ./data/pipelines/business_performance/__init__.py:/pipelines/business_performance/__init__.py",
            "- ./data/pipelines/business_performance/trigger.py:/pipelines/business_performance/trigger.py",
        })

    def test_prefect_is_not_a_dependency_of_the_api(self):
        pyproject = tomllib.loads((SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertFalse(any(dep.lower().startswith("prefect") for dep in pyproject["project"]["dependencies"]))
        lock = tomllib.loads((SERVICE_ROOT / "uv.lock").read_text(encoding="utf-8"))
        self.assertNotIn("prefect", {package["name"] for package in lock["package"]})


if __name__ == "__main__":
    unittest.main()
