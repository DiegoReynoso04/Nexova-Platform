"""requirements.txt (imagen del pipeline) sigue a uv.lock y a pyproject.toml.

La imagen del pipeline instala `requirements.txt` con `uv pip install
--require-hashes`, no `uv.lock`; el venv del host se instala del mismo archivo.
Si alguien cambia una dependencia y no lo regenera, la imagen y el venv
instalarían otras versiones que el lock. Se compara leyendo los archivos con
`tomllib`, sin llamar a uv (mismo patrón que services/api).
"""

import re
import tomllib
import unittest
from pathlib import Path

PIPELINES_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS = PIPELINES_DIR / "requirements.txt"
LOCKFILE = PIPELINES_DIR / "uv.lock"
PYPROJECT = PIPELINES_DIR / "pyproject.toml"

REGENERATE = (
    "regenerate it from data/pipelines with: uv lock && "
    "uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt"
)
# Paquete del monorepo: no está publicado y nunca se instala desde PyPI
# (ver el comentario de pyproject.toml); entra por ruta.
MONOREPO_PACKAGES = {"nexova-shared", "nexova-incident-analyzer"}

REQUIREMENT_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)")
REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """Nombre de distribución normalizado (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(specifier: str) -> str:
    match = REQUIREMENT_NAME.match(specifier.strip())
    assert match is not None, specifier
    return normalize(match.group(1))


def read_requirements() -> dict[str, str]:
    pinned = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        match = REQUIREMENT_LINE.match(line)
        if match:
            pinned[normalize(match.group(1))] = match.group(2)
    return pinned


def read_lock() -> dict[str, str]:
    with LOCKFILE.open("rb") as handle:
        lock = tomllib.load(handle)
    return {normalize(package["name"]): package["version"] for package in lock["package"] if "version" in package}


def read_pyproject() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


class RequirementsFollowLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pinned = read_requirements()
        self.locked = read_lock()
        self.pyproject = read_pyproject()

    def test_requirements_is_not_empty(self) -> None:
        self.assertGreater(len(self.pinned), 0, f"requirements.txt has no pinned packages; {REGENERATE}")

    def test_every_pinned_package_has_the_same_version_in_the_lock(self) -> None:
        for name, version in sorted(self.pinned.items()):
            with self.subTest(package=name):
                self.assertIn(name, self.locked, f"{name} is in requirements.txt but not in uv.lock; {REGENERATE}")
                self.assertEqual(
                    version,
                    self.locked[name],
                    f"{name}=={version} in requirements.txt but {self.locked[name]} in uv.lock; {REGENERATE}",
                )

    def test_every_project_dependency_is_pinned(self) -> None:
        for specifier in self.pyproject["project"]["dependencies"]:
            name = requirement_name(specifier)
            with self.subTest(dependency=name):
                self.assertIn(name, self.pinned, f"{name} (pyproject.toml) is missing from requirements.txt; {REGENERATE}")

    def test_prefect_stays_on_the_authorised_series(self) -> None:
        # D1: prefect>=3 (ticket) acotado a la 3.9, la versión probada.
        self.assertRegex(self.pinned.get("prefect", ""), r"^3\.9\.", f"prefect must be 3.9.x; {REGENERATE}")

    def test_monorepo_packages_are_not_pinned(self) -> None:
        for name in sorted(MONOREPO_PACKAGES):
            with self.subTest(package=name):
                self.assertNotIn(name, self.pinned, f"{name} must never be installed from PyPI; {REGENERATE}")

    def test_project_is_virtual(self) -> None:
        # Sin build: el código se importa por ruta (pyproject.toml, [tool.uv]).
        self.assertIs(self.pyproject["tool"]["uv"]["package"], False)
        self.assertNotIn(normalize(self.pyproject["project"]["name"]), self.pinned)

    def test_every_pin_has_hashes(self) -> None:
        # Líneas lógicas, como las lee el parser de requirements: una barra
        # invertida al final de línea continúa la línea siguiente.
        text = REQUIREMENTS.read_text(encoding="utf-8").replace("\\\r\n", " ").replace("\\\n", " ")
        for line in text.splitlines():
            stripped = line.strip()
            with self.subTest(line=stripped[:40]):
                self.assertFalse(stripped.startswith("--hash"), f"hash without a requirement on its line; {REGENERATE}")
            match = REQUIREMENT_LINE.match(stripped)
            if match:
                with self.subTest(package=normalize(match.group(1))):
                    self.assertIn("--hash=sha256:", stripped, f"uv pip install --require-hashes needs hashes; {REGENERATE}")


if __name__ == "__main__":
    unittest.main()
