"""La analítica anónima de Prefect está desactivada en todos los modos.

Prefect 3.9.2 tiene dos interruptores: el del servidor
(`PREFECT_SERVER_ANALYTICS_ENABLED`) y el del cliente (`DO_NOT_TRACK`). Con
solo el primero, al importar Prefect en una terminal aparece el aviso «Prefect
collects anonymous usage data…». Se comprueban los dos en: el script y los
módulos del worker (aunque el entorno intente reactivarlos), la suite, la
imagen y los dos servicios de Compose.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml  # dependencia de Prefect (pyyaml), ya en el entorno de data/pipelines

import pipeline  # noqa: F401  (como el script: primero el pipeline, después Prefect)
from business_performance._bootstrap import ANALYTICS_OFF

PIPELINES_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINES_DIR.parents[1]

_CHECK = (
    "import pipeline, business_performance.serve, business_performance.secret\n"
    "from prefect._internal.analytics import is_telemetry_enabled\n"
    "from prefect.settings import get_current_settings\n"
    "print(is_telemetry_enabled(), get_current_settings().server.analytics_enabled)\n"
)


class AnalyticsOffTests(unittest.TestCase):
    def test_in_this_process_both_switches_are_off(self):
        from prefect._internal.analytics import is_telemetry_enabled  # noqa: PLC0415
        from prefect.settings import get_current_settings  # noqa: PLC0415

        self.assertEqual(ANALYTICS_OFF, {"DO_NOT_TRACK": "1", "PREFECT_SERVER_ANALYTICS_ENABLED": "false"})
        for name, value in ANALYTICS_OFF.items():
            with self.subTest(variable=name):
                self.assertEqual(os.environ[name], value)
        self.assertFalse(is_telemetry_enabled())
        self.assertFalse(get_current_settings().server.analytics_enabled)

    def test_the_script_turns_them_off_even_if_the_environment_turns_them_on(self):
        env = {key: value for key, value in os.environ.items() if key not in ANALYTICS_OFF}
        env.update({"DO_NOT_TRACK": "0", "PREFECT_SERVER_ANALYTICS_ENABLED": "true"})
        result = subprocess.run(
            [sys.executable, "-c", _CHECK], cwd=PIPELINES_DIR, env=env, capture_output=True, text=True, timeout=120
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "False False")
        self.assertNotIn("collects anonymous usage data", result.stdout + result.stderr)

    def test_the_image_sets_both_variables(self):
        dockerfile = (REPO_ROOT / "data" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("PREFECT_SERVER_ANALYTICS_ENABLED=false", dockerfile)
        self.assertIn("DO_NOT_TRACK=1", dockerfile)

    def test_both_compose_services_set_both_variables(self):
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        for service in ("prefect-server", "pipeline-worker"):
            environment = compose["services"][service]["environment"]
            with self.subTest(service=service):
                self.assertEqual(str(environment["DO_NOT_TRACK"]), "1")
                self.assertEqual(str(environment["PREFECT_SERVER_ANALYTICS_ENABLED"]).lower(), "false")


if __name__ == "__main__":
    unittest.main()
