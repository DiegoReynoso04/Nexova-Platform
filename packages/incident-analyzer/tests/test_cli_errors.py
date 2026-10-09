"""`scripts/analyze.py` ante interrupciones y errores de E/S sin `strerror` (S4 de la auditoría).

En proceso (no como subproceso) para poder simular `input` y las funciones del
núcleo. `test_cli.py` cubre el comportamiento de extremo a extremo.
"""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from .support import CLI, FIXTURE


def load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("analyze_cli", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(CLI.exists(), f"CLI not found at {CLI}")
class CliErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cli = load_cli()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.output = Path(tmp.name) / "results.csv"

    def run_main(self, *args: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.cli.main([str(FIXTURE), "--output", str(self.output), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_ctrl_c_at_the_export_prompt_means_no_export(self) -> None:
        try:
            with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
                code, out, err = self.run_main()
        except KeyboardInterrupt:
            # Sin esto, una regresión abortaría toda la suite en vez de fallar este test.
            self.fail("KeyboardInterrupt escaped from ask_export")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("SUPPORT TICKET ANALYSIS", out)
        self.assertFalse(self.output.exists())

    def test_read_error_without_strerror_shows_the_class_name(self) -> None:
        with mock.patch.object(self.cli, "analyze_file", side_effect=OSError()):
            code, out, err = self.run_main("--no-export")
        self.assertEqual((code, out), (1, ""))
        self.assertIn(f"error: cannot read {FIXTURE}: OSError", err)
        self.assertNotIn("None", err)

    def test_write_error_without_strerror_shows_the_class_name(self) -> None:
        with mock.patch.object(self.cli, "write_results_csv", side_effect=PermissionError()):
            code, _, err = self.run_main("--export")
        self.assertEqual(code, 1)
        self.assertIn(f"error: cannot write {self.output}: PermissionError", err)
        self.assertNotIn("None", err)


if __name__ == "__main__":
    unittest.main()
