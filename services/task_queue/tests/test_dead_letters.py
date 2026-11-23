"""DLQ (A9): fila con attempt y retries, idempotente, y log si la base no está disponible."""

import os
import unittest
from unittest import mock

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from task_queue import dead_letters
from task_queue.dead_letters import record_dead_letter
from task_queue.errors import DeadLetterReason

from .support import letter, sqlite_repository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = sqlite_repository()
        self.addCleanup(self.repo.engine.dispose)

    def test_row_has_attempt_one_based_and_retries(self):
        self.assertTrue(self.repo.record(letter()))
        [row] = self.repo.list()
        self.assertEqual((row["attempt"], row["retries"], row["max_retries"]), (4, 3, 3))
        self.assertEqual(row["reason"], "retries_exhausted")
        self.assertEqual(row["error_class"], "OperationalError")
        self.assertEqual(row["task_kwargs"], {"start": "2026-11-13T00:00:00.000Z", "end": "2026-11-20T00:00:00.000Z"})
        self.assertIsNotNone(row["failed_at"])

    def test_same_task_id_twice_keeps_one_row(self):
        self.assertTrue(self.repo.record(letter()))
        self.assertFalse(self.repo.record(letter(error_message="other")))
        self.assertEqual(len(self.repo.list()), 1)

    def test_non_retryable_first_attempt(self):
        self.repo.record(letter(retries=0, reason=DeadLetterReason.NON_RETRYABLE))
        [row] = self.repo.list()
        self.assertEqual((row["attempt"], row["retries"], row["reason"]), (1, 0, "non_retryable"))

    def test_checks_reject_inconsistent_rows(self):
        bad = letter().row() | {"attempt": 2}
        with self.assertRaises(IntegrityError):
            with self.repo.engine.begin() as connection:
                connection.execute(insert(self.repo.table).values(**bad))
        with self.assertRaises(IntegrityError):
            with self.repo.engine.begin() as connection:
                connection.execute(insert(self.repo.table).values(**(letter().row() | {"reason": "other"})))


class FakeRepository:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def record(self, _letter):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def operational():
    return OperationalError("INSERT", {}, Exception("could not connect to server"))


class RecordWithFallbackTests(unittest.TestCase):
    def test_stored(self):
        repo = sqlite_repository()
        self.addCleanup(repo.engine.dispose)
        with self.assertLogs("task_queue", "INFO") as logs:
            self.assertTrue(record_dead_letter(letter(), repository=repo))
        self.assertIn("status=dead_letter_stored", logs.output[0])
        self.assertIn("attempt=4/4", logs.output[0])
        self.assertEqual(len(repo.list()), 1)

    def test_transient_failure_is_retried_once(self):
        repo, sleeps = FakeRepository(operational(), True), []
        with self.assertLogs("task_queue", "INFO"):
            self.assertTrue(record_dead_letter(letter(), repository=repo, sleep=sleeps.append))
        self.assertEqual((repo.calls, sleeps), (2, [dead_letters.DEAD_LETTER_RETRY_DELAY_SECONDS]))

    def test_unavailable_database_goes_to_the_log_with_every_field(self):
        repo, sleeps = FakeRepository(operational(), operational()), []
        with self.assertLogs("task_queue", "ERROR") as logs:
            self.assertFalse(record_dead_letter(letter(), repository=repo, sleep=sleeps.append))
        [line] = logs.output
        for expected in (
            "status=dead_letter_not_stored",
            "cause=OperationalError",
            "task_id=0f8f3c52-6f7e-4a52-9d0c-3e0c6c1f6a11",
            "attempt=4/4",
            "retries=3",
            "reason=retries_exhausted",
            'error="OperationalError (QueryCanceled)"',
            "2026-11-13T00:00:00.000Z",
        ):
            self.assertIn(expected, line)
        self.assertEqual(len(sleeps), 1)

    def test_missing_table_goes_to_the_log_without_waiting(self):
        repo, sleeps = FakeRepository(ProgrammingError("INSERT", {}, Exception('relation "ops.task_dead_letters" does not exist'))), []
        with self.assertLogs("task_queue", "ERROR") as logs:
            self.assertFalse(record_dead_letter(letter(), repository=repo, sleep=sleeps.append))
        self.assertIn("cause=ProgrammingError", logs.output[0])
        self.assertEqual((repo.calls, sleeps), (1, []))

    def test_without_database_url_goes_to_the_log(self):
        env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
        with mock.patch.dict(os.environ, env, clear=True), self.assertLogs("task_queue", "ERROR") as logs:
            self.assertFalse(record_dead_letter(letter()))
        self.assertIn("cause=ConfigError", logs.output[0])

    def test_never_raises(self):
        repo = FakeRepository(ProgrammingError("INSERT", {}, Exception("x")))
        with self.assertLogs("task_queue", "ERROR"):
            record_dead_letter(letter(), repository=repo)


if __name__ == "__main__":
    unittest.main()
