"""La tarea del reporte (A1, A3): nombre, mensaje con solo dos fechas y su validación.

El cálculo en sí (SQLite y el mismo `build_telemetry_report`) lo prueban los tests de
la API (`services/api/tests/test_telemetry_report.py`), que tienen el modelo de la
tabla; contra PostgreSQL, la verificación de la parada 3 con el efímero.
"""

import inspect
import unittest
from datetime import UTC, datetime

from task_queue import tasks
from task_queue.base import ReliableTask
from task_queue.celery_app import app
from task_queue.names import TELEMETRY_REPORT_TASK
from task_queue.reports import build_telemetry_report, parse_envelope_instant


class TaskRegistrationTests(unittest.TestCase):
    def test_registered_by_name_with_only_start_and_end(self):
        self.assertEqual(TELEMETRY_REPORT_TASK, "task_queue.telemetry_report")
        self.assertIn(TELEMETRY_REPORT_TASK, app.tasks)
        self.assertEqual(list(inspect.signature(tasks.telemetry_report.run).parameters), ["start", "end"])

    def test_inherits_retries_and_the_dlq(self):
        self.assertEqual(app.tasks[TELEMETRY_REPORT_TASK].max_retries, 3)
        self.assertIsInstance(app.tasks[TELEMETRY_REPORT_TASK], ReliableTask)


class EnvelopeInstantTests(unittest.TestCase):
    def test_the_envelope_format(self):
        self.assertEqual(parse_envelope_instant("2026-11-05T12:00:00.123Z"), datetime(2026, 11, 5, 12, 0, 0, 123000, tzinfo=UTC))

    def test_anything_else_is_a_value_error(self):
        for value in ("2026-11-05", "2026-11-05T12:00:00Z", "2026-11-05T12:00:00.123+00:00", "x" * 24, 7):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_envelope_instant(value)  # type: ignore[arg-type]

    def test_start_must_be_before_end(self):
        with self.assertRaises(ValueError):
            build_telemetry_report(None, "2026-11-05T12:00:00.000Z", "2026-11-05T12:00:00.000Z")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
