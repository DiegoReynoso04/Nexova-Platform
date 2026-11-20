"""task_queue es una biblioteca independiente de la API (A5): el worker no carga FastAPI ni `app`."""

import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[2]
PACKAGE = SERVICES / "task_queue"
FORBIDDEN_ROOTS = {"fastapi", "starlette", "uvicorn", "app", "prefect"}


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class IndependenceTests(unittest.TestCase):
    def test_no_module_imports_the_api_or_prefect(self):
        for path in sorted(PACKAGE.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertFalse(imported_roots(path) & FORBIDDEN_ROOTS)

    def test_loading_the_worker_app_does_not_load_fastapi(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "import task_queue.celery_app, task_queue.tasks;"
            "roots = {name.split('.')[0] for name in sys.modules};"
            f"bad = sorted(roots & set({sorted(FORBIDDEN_ROOTS)!r}));"
            "print('LOADED:' + ','.join(bad)) if bad else print('CLEAN')"
        )
        env = {**os.environ, "REDIS_URL": "redis://localhost:6399/0"}
        result = subprocess.run([sys.executable, "-c", code, str(SERVICES)], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "CLEAN")

    def test_no_module_uses_pickle(self):
        """Ni un `import pickle` ni un literal `"pickle"` (p. ej. en `accept_content`): solo JSON."""
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
            with self.subTest(module=path.name):
                self.assertNotIn("pickle", imported_roots(path))
                self.assertFalse({"pickle", "application/x-python-serialize"} & literals)


if __name__ == "__main__":
    unittest.main()
