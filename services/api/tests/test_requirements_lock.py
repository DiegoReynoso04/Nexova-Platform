"""requirements.txt (imagen de Docker, #infra-40) sigue a uv.lock y a pyproject.toml.

La imagen de services/api instala `requirements.txt` con `uv pip install
--require-hashes`, no `uv.lock`. Si alguien cambia una dependencia y no lo
regenera, la imagen instalaría otras versiones que el venv local. Se compara
leyendo los archivos con `tomllib`, sin llamar a uv.

DEV-55 (A14): `requirements-flower.txt` es lo que instala el target `flower` de
services/Dockerfile: las dependencias principales más el grupo `flower` de uv. Flower
es solo de desarrollo y nunca entra en `requirements.txt` (la imagen de la API).
"""

import re
import tomllib
import unittest
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS = SERVICE_DIR / "requirements.txt"
FLOWER_REQUIREMENTS = SERVICE_DIR / "requirements-flower.txt"
LOCKFILE = SERVICE_DIR / "uv.lock"
PYPROJECT = SERVICE_DIR / "pyproject.toml"

REGENERATE = (
    "regenerate it from services/api with: "
    "uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt"
)
REGENERATE_FLOWER = (
    "regenerate it from services/api with: "
    "uv export --frozen --no-dev --group flower --no-emit-project --format requirements-txt -o requirements-flower.txt"
)
# Paquetes del monorepo: no están publicados y nunca se instalan desde PyPI
# (ver el comentario de pyproject.toml); entran en la imagen por PYTHONPATH.
MONOREPO_PACKAGES = {"nexova-incident-analyzer", "nexova-shared"}

REQUIREMENT_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)")
REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """Nombre de distribución normalizado (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(specifier: str) -> str:
    match = REQUIREMENT_NAME.match(specifier.strip())
    assert match is not None, specifier
    return normalize(match.group(1))


def read_requirements(path: Path = REQUIREMENTS) -> dict[str, str]:
    pinned = {}
    for line in path.read_text(encoding="utf-8").splitlines():
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

    def test_monorepo_packages_are_not_pinned(self) -> None:
        for name in sorted(MONOREPO_PACKAGES):
            with self.subTest(package=name):
                self.assertNotIn(name, self.pinned, f"{name} must never be installed from PyPI; {REGENERATE}")

    def test_dev_group_is_not_pinned(self) -> None:
        dev = {requirement_name(specifier) for specifier in self.pyproject["dependency-groups"]["dev"]}
        self.assertTrue({"pytest", "pytest-cov"} <= dev)
        for name in sorted(dev):
            with self.subTest(package=name):
                self.assertNotIn(name, self.pinned, f"{name} is a dev dependency, not for the image; {REGENERATE}")

    def test_every_pin_has_hashes(self) -> None:
        assert_every_pin_has_hashes(self, REQUIREMENTS, REGENERATE)


def assert_every_pin_has_hashes(case: unittest.TestCase, path: Path, regenerate: str) -> None:
    # Líneas lógicas, como las lee el parser de requirements: una barra
    # invertida al final de línea continúa la línea siguiente.
    text = path.read_text(encoding="utf-8").replace("\\\r\n", " ").replace("\\\n", " ")
    for line in text.splitlines():
        stripped = line.strip()
        with case.subTest(file=path.name, line=stripped[:40]):
            case.assertFalse(stripped.startswith("--hash"), f"hash without a requirement on its line; {regenerate}")
        match = REQUIREMENT_LINE.match(stripped)
        if match:
            with case.subTest(file=path.name, package=normalize(match.group(1))):
                case.assertIn("--hash=sha256:", stripped, f"uv pip install --require-hashes needs hashes; {regenerate}")


class FlowerRequirementsFollowLockTests(unittest.TestCase):
    """DEV-55 (A14): el target `flower` instala lo de la imagen de la API más el grupo `flower`."""

    def setUp(self) -> None:
        self.flower = read_requirements(FLOWER_REQUIREMENTS)
        self.pinned = read_requirements()
        self.locked = read_lock()
        self.pyproject = read_pyproject()
        self.group = {requirement_name(spec) for spec in self.pyproject["dependency-groups"]["flower"]}

    def test_every_pin_has_the_same_version_in_the_lock(self) -> None:
        self.assertGreater(len(self.flower), len(self.pinned), f"requirements-flower.txt looks incomplete; {REGENERATE_FLOWER}")
        for name, version in sorted(self.flower.items()):
            with self.subTest(package=name):
                self.assertEqual(version, self.locked.get(name), f"{name}=={version} does not follow uv.lock; {REGENERATE_FLOWER}")

    def test_includes_the_api_requirements_with_the_same_versions(self) -> None:
        for name, version in sorted(self.pinned.items()):
            with self.subTest(package=name):
                self.assertEqual(self.flower.get(name), version, f"{name} differs from requirements.txt; {REGENERATE_FLOWER}")

    def test_flower_group_is_pinned_here_and_never_in_the_api_image(self) -> None:
        self.assertEqual(self.group, {"flower"})
        for name in sorted(self.group):
            with self.subTest(package=name):
                self.assertIn(name, self.flower, f"{name} is missing; {REGENERATE_FLOWER}")
                self.assertNotIn(name, self.pinned, f"{name} is development-only, not for the API image; {REGENERATE}")

    def test_dev_group_and_monorepo_packages_are_not_pinned(self) -> None:
        dev = {requirement_name(spec) for spec in self.pyproject["dependency-groups"]["dev"]}
        for name in sorted(dev | MONOREPO_PACKAGES):
            with self.subTest(package=name):
                self.assertNotIn(name, self.flower, f"{name} must not be in requirements-flower.txt; {REGENERATE_FLOWER}")

    def test_every_pin_has_hashes(self) -> None:
        assert_every_pin_has_hashes(self, FLOWER_REQUIREMENTS, REGENERATE_FLOWER)


if __name__ == "__main__":
    unittest.main()
