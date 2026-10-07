"""Garantías del código del paquete: solo librería estándar, sin salida y sin duplicar la validación."""

import ast
import importlib.util
import sys
import unittest

import nexova_shared.incident_csv as incident_csv

from .support import REPO_ROOT, SOURCE_DIR

# El analizador se importa desde el monorepo si no está instalado (los tests se
# lanzan con cualquier Python ≥ 3.11 desde la raíz).
if importlib.util.find_spec("incident_analyzer") is None:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "incident-analyzer"))

import incident_analyzer  # noqa: E402
import incident_analyzer.reader  # noqa: E402
import incident_analyzer.schema  # noqa: E402
import incident_analyzer.validation  # noqa: E402


def source_files() -> list:
    return sorted(SOURCE_DIR.rglob("*.py"))


def imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    return modules


class StandardLibraryOnlyTests(unittest.TestCase):
    def test_has_source_files(self) -> None:
        self.assertGreaterEqual(len(source_files()), 8)

    def test_only_standard_library_imports(self) -> None:
        for path in source_files():
            for module in imported_modules(ast.parse(path.read_text(encoding="utf-8"))):
                with self.subTest(file=path.name, module=module):
                    self.assertIn(module.split(".")[0], sys.stdlib_module_names)

    def test_does_not_print_or_log(self) -> None:
        for path in source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(file=path.name):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotEqual(node.func.id, "print")
                self.assertNotIn("logging", imported_modules(tree))


class AnalyzerReusesSharedValidationTests(unittest.TestCase):
    """El analizador no tiene una copia propia: reexporta exactamente los mismos objetos."""

    def test_public_api_is_the_shared_one(self) -> None:
        for name in ("Category", "IncidentFileError", "IncidentRow", "Rule", "Status", "ValidationResult", "validate_row"):
            with self.subTest(name=name):
                self.assertIs(getattr(incident_analyzer, name), getattr(incident_csv, name))

    def test_legacy_modules_are_reexports(self) -> None:
        self.assertIs(incident_analyzer.reader.read_rows, incident_csv.read_rows)
        self.assertIs(incident_analyzer.validation.parse_score, incident_csv.parse_score)
        self.assertIs(incident_analyzer.schema.FIELDS, incident_csv.FIELDS)

    def test_analyzer_defines_no_validation_functions(self) -> None:
        analyzer_dir = REPO_ROOT / "packages" / "incident-analyzer" / "incident_analyzer"
        for module in ("schema.py", "reader.py", "validation.py"):
            tree = ast.parse((analyzer_dir / module).read_text(encoding="utf-8"))
            with self.subTest(module=module):
                defined = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
                self.assertEqual(defined, [])


if __name__ == "__main__":
    unittest.main()
