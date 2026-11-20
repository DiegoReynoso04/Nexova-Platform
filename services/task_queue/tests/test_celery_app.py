"""La instancia de Celery y la tarea trivial de la parada 1, sin Redis."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from task_queue import celery_app, tasks
from task_queue.config import TaskQueueSettings, celery_config

SERVICES = Path(__file__).resolve().parents[2]


class CeleryAppTests(unittest.TestCase):
    def test_create_app_applies_the_a7_configuration(self):
        settings = TaskQueueSettings.from_redis_url("redis://:pw@redis:6379/0")
        app = celery_app.create_app(settings)
        for key, value in celery_config(settings).items():
            with self.subTest(setting=key):
                self.assertEqual(app.conf[key], value)

    def test_module_app_reads_redis_url_from_the_environment(self):
        expected = TaskQueueSettings.from_env()
        self.assertEqual(celery_app.app.conf.broker_url, expected.broker_url)
        self.assertEqual(celery_app.app.conf.result_backend, expected.result_backend)

    def test_ping_is_registered_by_name(self):
        self.assertEqual(tasks.PING_TASK, "task_queue.ping")
        self.assertIn(tasks.PING_TASK, celery_app.app.tasks)
        # `tasks.ping` es un proxy de Celery: se compara la tarea a la que apunta.
        self.assertIs(celery_app.app.tasks[tasks.PING_TASK], tasks.ping._get_current_object())
        self.assertIs(tasks.ping.app, celery_app.app)

    def test_ping_runs_locally_without_a_broker(self):
        self.assertEqual(tasks.ping.run(), "pong")
        self.assertEqual(tasks.ping.apply().get(timeout=5), "pong")

    def test_importing_without_redis_url_fails_without_the_url(self):
        env = {key: value for key, value in os.environ.items() if key != "REDIS_URL"}
        code = "import sys; sys.path.insert(0, sys.argv[1]); import task_queue.celery_app"
        result = subprocess.run([sys.executable, "-c", code, str(SERVICES)], capture_output=True, text=True, env=env, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ConfigError: REDIS_URL is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
