"""El servidor efímero de Prefect tiene 90 s para arrancar, no los 20 por defecto (DEV-53).

Medido: el arranque tarda 18–21 s (desde «Starting temporary server» hasta «Beginning flow run»);
con el timeout por defecto de 20 s, el job nocturno fallaba al azar con «Timed out while
attempting to connect to ephemeral Prefect API server». Se fija en `_bootstrap.py` con
`setdefault`: vale a mano, en el subproceso del job nocturno y en su contenedor.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from business_performance._bootstrap import EPHEMERAL_STARTUP_TIMEOUT_SECONDS, EPHEMERAL_STARTUP_TIMEOUT_VARIABLE

PIPELINES_DIR = Path(__file__).resolve().parents[1]
VARIABLE = "PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS"

_CHECK = (
    "import os, pipeline\n"
    "from prefect.settings import get_current_settings\n"
    "print(os.environ.get(%r), get_current_settings().server.ephemeral.startup_timeout_seconds)\n" % VARIABLE
)
_DEFAULT_CHECK = (
    "from prefect.settings import get_current_settings\n"
    "print(get_current_settings().server.ephemeral.startup_timeout_seconds)\n"
)


def run_python(code: str, env_overrides: dict[str, str]) -> str:
    env = {key: value for key, value in os.environ.items() if key != VARIABLE}
    env.update(env_overrides)
    result = subprocess.run([sys.executable, "-c", code], cwd=PIPELINES_DIR, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout.strip().splitlines()[-1]


class EphemeralStartupTimeoutTests(unittest.TestCase):
    def test_the_constants(self):
        self.assertEqual(EPHEMERAL_STARTUP_TIMEOUT_VARIABLE, VARIABLE)
        self.assertEqual(EPHEMERAL_STARTUP_TIMEOUT_SECONDS, "90")

    def test_prefect_default_is_20_seconds_the_reason_for_this_fix(self):
        """Si una versión nueva de Prefect cambia el valor por defecto, este test avisa de que hay que revisar el 90."""
        self.assertEqual(run_python(_DEFAULT_CHECK, {}), "20")

    def test_it_is_set_to_90_when_the_environment_does_not_have_it(self):
        self.assertEqual(run_python(_CHECK, {}), "90 90")

    def test_a_variable_already_set_is_respected(self):
        for value in ("45", "300"):
            with self.subTest(value=value):
                self.assertEqual(run_python(_CHECK, {VARIABLE: value}), f"{value} {value}")

    def test_the_scripts_that_start_prefect_import_the_bootstrap_first(self):
        """El ajuste debe estar puesto antes de importar Prefect: el orden de imports lo garantiza."""
        for name in ("pipeline.py", "business_performance/serve.py"):
            text = (PIPELINES_DIR / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertLess(text.index("_bootstrap"), text.index("from prefect"))


if __name__ == "__main__":
    unittest.main()
