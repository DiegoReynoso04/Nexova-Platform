"""`ReliableTask` sin Redis: ejecución local (`apply`), con la DLQ y el backoff interceptados.

En local, Celery ejecuta los reintentos en el acto (sin esperar la cuenta atrás);
aquí se comprueba qué cuenta atrás se pide, cuántas ejecuciones hay y qué llega a
la DLQ. Las esperas reales y las marcas de tiempo del log las prueba la
integración con Redis y un worker de verdad (`test_worker_integration.py`).
"""

import os
import unittest
from unittest import mock

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import OperationalError

from task_queue import base
from task_queue.celery_app import create_app
from task_queue.config import TaskQueueSettings
from task_queue.errors import TaskFailedError
from task_queue.retries import backoff_floor

SECRET_URL = "postgresql://nexova:db-Secret-123@db.example.invalid:6543/postgres"


def transient():
    return OperationalError("SELECT 1", {}, Exception(f"could not connect to {SECRET_URL}"))


class ReliableTaskTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TaskQueueSettings.from_redis_url("redis://localhost:6399/0"), include=())
        self.app.conf.task_store_eager_result = False
        self.letters = []
        self.countdowns = []
        self.executions = []
        patcher = mock.patch.object(base.ReliableTask, "dead_letter_recorder", staticmethod(self.letters.append))
        patcher.start()
        self.addCleanup(patcher.stop)
        real = base.backoff_countdown

        def recording_backoff(retries):
            value = real(retries)
            self.countdowns.append((retries, value))
            return value

        patcher = mock.patch.object(base, "backoff_countdown", recording_backoff)
        patcher.start()
        self.addCleanup(patcher.stop)

    def task(self, body, name="tests.task"):
        executions = self.executions

        @self.app.task(name=name, bind=True)
        def wrapped(self, **kwargs):
            executions.append(self.request.retries)
            return body(self, **kwargs)

        return wrapped

    def run_task(self, task, **kwargs):
        with self.assertLogs("task_queue", "INFO") as logs:
            result = task.apply(kwargs=kwargs, task_id="5c2d0f0e-2c55-4f53-9a43-6f0d9b1c7e10")
        return result, [line.split(":", 2)[2] for line in logs.output]

    def test_every_task_is_reliable(self):
        task = self.task(lambda self: "ok")
        self.assertIsInstance(task._get_current_object(), base.ReliableTask)
        self.assertEqual(task.max_retries, 3)

    def test_success_logs_started_and_success(self):
        result, lines = self.run_task(self.task(lambda self, value: value * 2), value=21)
        self.assertEqual(result.get(), 42)
        self.assertEqual(len(lines), 2)
        self.assertIn("attempt=1/4 status=started", lines[0])
        self.assertRegex(lines[1], r"attempt=1/4 status=success duration_ms=\d+\.\d\d")
        self.assertEqual(self.letters, [])

    def test_transient_failures_exhaust_max_retries_and_reach_the_dlq(self):
        def body(self, start, end):
            raise transient()

        result, lines = self.run_task(self.task(body), start="2026-11-13T00:00:00.000Z", end="2026-11-20T00:00:00.000Z")
        # max_retries=3 literal: 1 + 3 = 4 ejecuciones.
        self.assertEqual(self.executions, [0, 1, 2, 3])
        self.assertEqual([retries for retries, _ in self.countdowns], [0, 1, 2])
        for retries, countdown in self.countdowns:
            self.assertGreaterEqual(countdown, backoff_floor(retries))
            self.assertLess(countdown, backoff_floor(retries) + 2)
        [letter] = self.letters
        self.assertEqual((letter.attempt, letter.retries, letter.max_retries), (4, 3, 3))
        self.assertEqual(str(letter.reason), "retries_exhausted")
        self.assertEqual(letter.error_message, "OperationalError (Exception)")
        self.assertEqual(letter.task_kwargs, {"start": "2026-11-13T00:00:00.000Z", "end": "2026-11-20T00:00:00.000Z"})
        statuses = [line.split("status=")[1].split()[0] for line in lines]
        self.assertEqual(statuses, ["started", "retry", "started", "retry", "started", "retry", "started", "dead_letter"])
        self.assertIn("attempt=4/4 status=dead_letter", lines[-1])
        self.assertIn("countdown_s=", lines[1])

    def test_transient_then_success_does_not_reach_the_dlq(self):
        def body(self):
            if self.request.retries < 2:
                raise transient()
            return "ok"

        self.run_task(self.task(body))
        self.assertEqual(self.executions, [0, 1, 2])
        self.assertEqual(self.letters, [])

    def test_non_retryable_goes_straight_to_the_dlq(self):
        def body(self):
            raise ValueError(f"bad input near {SECRET_URL}")

        result, lines = self.run_task(self.task(body))
        self.assertEqual(self.executions, [0])
        self.assertEqual(self.countdowns, [])
        [letter] = self.letters
        self.assertEqual((letter.attempt, letter.retries, str(letter.reason)), (1, 0, "non_retryable"))
        self.assertEqual(letter.error_message, "ValueError: bad input near <redacted-url>")
        with self.assertRaises(TaskFailedError) as raised:
            result.get()
        self.assertEqual(str(raised.exception), "ValueError: bad input near <redacted-url>")
        self.assertIn('error="ValueError: bad input near <redacted-url>"', lines[-1])

    def test_soft_time_limit_is_not_retried(self):
        def body(self):
            raise SoftTimeLimitExceeded()

        self.run_task(self.task(body))
        [letter] = self.letters
        self.assertEqual((letter.attempt, str(letter.reason), letter.error_class), (1, "time_limit", "SoftTimeLimitExceeded"))

    def test_no_secret_reaches_the_result_the_dlq_or_the_log(self):
        def body(self):
            raise RuntimeError(f"could not connect to {SECRET_URL}")

        with mock.patch.dict(os.environ, {"DATABASE_URL": SECRET_URL}):
            result, lines = self.run_task(self.task(body))
        for text in [*lines, self.letters[0].error_message, repr(result.result)]:
            self.assertNotIn("db-Secret-123", text)
            self.assertNotIn("db.example.invalid", text)

    def test_the_backend_only_sees_the_redacted_failure(self):
        result, _ = self.run_task(self.task(lambda self: (_ for _ in ()).throw(transient())))
        self.assertIsInstance(result.result, TaskFailedError)
        self.assertEqual(result.result.args, ("OperationalError", "OperationalError (Exception)"))


class TaskKwargsTests(unittest.TestCase):
    def test_positional_arguments_are_kept_under_args(self):
        self.assertEqual(base.task_kwargs_of((1, "a"), {"b": 2}), {"b": 2, "args": [1, "a"]})
        self.assertEqual(base.task_kwargs_of((), None), {})


if __name__ == "__main__":
    unittest.main()
