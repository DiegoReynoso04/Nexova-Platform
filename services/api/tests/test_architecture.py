"""La API es una capa fina: no duplica reglas del núcleo y el núcleo no depende de la API.

Análisis estático (ast) de services/api/app y de packages/incident-analyzer.
"""

import ast
import unittest
from pathlib import Path

from incident_analyzer import Category, Rule, Status, analyze_stream
from nexova_shared.incidents import BRANCH_LABELS, Branch, IncidentCategory, IncidentOrigin, IncidentStatus

from .support import APP_DIR, CORE_PACKAGE_DIR, HEADER

# Etiquetas de puntuación tal como las define el núcleo (sin repetirlas aquí).
SCORE_LABELS = {item.label for item in analyze_stream([HEADER]).satisfaction.distribution}

# Literales que solo deben existir en el núcleo. Si aparecen en la API, se
# estaría reimplementando una regla, una categoría, un estado o el formato.
CORE_LITERALS = {
    *(category.value for category in Category),
    *(status.value for status in Status),
    *(rule.code for rule in Rule),
    *(rule.label for rule in Rule),
    *SCORE_LABELS,
    "utf-8-sig",
    "@",
}
FORBIDDEN_IMPORTS = {"csv", "re", "statistics", "fractions"}
FORBIDDEN_NAMES = {"ROUND_HALF_UP", "ROUND_HALF_EVEN", "quantize", "round", "parse_score", "print"}
# Únicos módulos que pueden imprimir: scripts de consola que no manejan datos de
# incidentes. El seeder confirma cuántos proveedores insertó; `create-admin`
# confirma el usuario creado (nunca imprime la contraseña).
PRINT_ALLOWED = {"seed.py", "auth/create_admin.py"}
# "@" es la regla de email del núcleo de incidentes y no debe reimplementarse
# en la API. Única excepción: la validación del email de login de AUTH-01, que
# no tiene relación con el CSV de incidentes.
CORE_LITERAL_EXCEPTIONS = {"auth/models.py": {"@"}}
# Vocabulario del gestor centralizado de incidencias: vive en nexova_shared
# (packages/shared) y la API no lo repite. "branch" es a la vez un origen y el
# nombre de un campo del modelo, así que no se puede prohibir como literal.
MANAGER_LITERALS = {
    *(member.value for vocabulary in (IncidentStatus, IncidentOrigin, IncidentCategory, Branch) for member in vocabulary),
    *BRANCH_LABELS.values(),
} - {"branch"}


def python_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class ApiDoesNotDuplicateCoreTests(unittest.TestCase):
    def test_app_has_python_files(self) -> None:
        self.assertGreater(len(python_files(APP_DIR)), 5)

    def test_no_core_literals_in_api(self) -> None:
        for path in python_files(APP_DIR):
            forbidden = CORE_LITERALS - CORE_LITERAL_EXCEPTIONS.get(path.relative_to(APP_DIR).as_posix(), set())
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    with self.subTest(file=path.name, literal=node.value):
                        self.assertNotIn(node.value, forbidden)
                        self.assertNotIn("AGT-", node.value)
                        self.assertNotIn(r"\d", node.value)

    def test_no_incident_manager_vocabulary_in_api(self) -> None:
        for path in python_files(APP_DIR):
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    with self.subTest(file=path.name, literal=node.value):
                        self.assertNotIn(node.value, MANAGER_LITERALS)

    def test_no_parsing_or_rounding_tools_in_api(self) -> None:
        for path in python_files(APP_DIR):
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], FORBIDDEN_IMPORTS, path.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], FORBIDDEN_IMPORTS, path.name)
                elif isinstance(node, ast.Name):
                    if node.id == "print" and path.relative_to(APP_DIR).as_posix() in PRINT_ALLOWED:
                        continue
                    self.assertNotIn(node.id, FORBIDDEN_NAMES, f"{node.id} in {path.name}")
                elif isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_NAMES, f"{node.attr} in {path.name}")

    def test_api_only_uses_the_public_core_api(self) -> None:
        used = False
        for path in python_files(APP_DIR):
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("incident_analyzer"):
                    used = True
                    self.assertEqual(node.module, "incident_analyzer", f"private import in {path.name}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith("incident_analyzer."), path.name)
        self.assertTrue(used, "the API must consume incident_analyzer")

    def test_only_core_errors_module_logs(self) -> None:
        for path in python_files(APP_DIR):
            source = path.read_text(encoding="utf-8")
            if "logging" in source:
                self.assertEqual(path.relative_to(APP_DIR).as_posix(), "core/errors.py")


class CoreDoesNotDependOnApiTests(unittest.TestCase):
    def test_core_has_no_web_framework_imports(self) -> None:
        for path in python_files(CORE_PACKAGE_DIR):
            for node in ast.walk(parse(path)):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for module in modules:
                    with self.subTest(file=path.name, module=module):
                        self.assertNotIn(module.split(".")[0], {"fastapi", "starlette", "pydantic", "uvicorn", "app"})


if __name__ == "__main__":
    unittest.main()
