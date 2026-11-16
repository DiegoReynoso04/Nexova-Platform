"""Casos del repositorio y del ciclo de vida, compartidos por SQLite y por PostgreSQL.

Son *mixins* (no `TestCase`): `test_repository.py` y `test_runner.py` los corren sobre
SQLite; `test_postgres_integration.py` sobre un PostgreSQL local, con el mismo
código. Quien los usa define `engine`, `table`, `repo` y `clock` en `setUp`.
"""

import io
import logging
import os
import re
from unittest import mock
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError, OperationalError

from job_runner import (
    AlreadyCompletedError,
    JobRunRepository,
    JobRunStateError,
    JobStatus,
    Outcome,
    run_job,
)
from job_runner.logs import LOGGER_NAME, configure_logging
from job_runner.states import ABANDONED_PENDING_MESSAGE, ABANDONED_PROCESSING_MESSAGE

from .support import DAY, JOB, T0, insert_row

LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z (INFO|ERROR) job=nightly_export "
    r"status=(starting|pending|processing|completed|failed|skipped|locked|rejected) target_date=\d{4}-\d{2}-\d{2}( run=[0-9a-f-]{36})? .+"
)


def statuses(repo: JobRunRepository, day: date | None = DAY) -> list[JobStatus]:
    return [row.status for row in repo.list_job_runs(JOB, day)]


class RepositoryCases:
    def test_create_job_run_inserts_pending(self):
        run = self.repo.create_job_run(JOB, DAY, T0)
        stored = self.repo.get_job_run(run.id)
        self.assertEqual(stored.status, JobStatus.PENDING)
        self.assertEqual((stored.job_name, stored.target_date, stored.created_at), (JOB, DAY, T0))
        self.assertIsNone(stored.started_at)
        self.assertIsNone(stored.finished_at)
        self.assertIsNone(stored.error_message)

    def test_get_job_run_unknown_is_none(self):
        from uuid import uuid4

        self.assertIsNone(self.repo.get_job_run(uuid4()))

    def test_claim_moves_pending_to_processing(self):
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.assertTrue(self.repo.claim(run.id, T0 + timedelta(seconds=1)))
        stored = self.repo.get_job_run(run.id)
        self.assertEqual(stored.status, JobStatus.PROCESSING)
        self.assertEqual(stored.started_at, T0 + timedelta(seconds=1))
        self.assertTrue(self.repo.has_processing_lock(JOB))

    def test_second_claim_for_the_same_job_loses_the_lock(self):
        first = self.repo.create_job_run(JOB, DAY, T0)
        second = self.repo.create_job_run(JOB, DAY, T0)
        self.assertTrue(self.repo.claim(first.id, T0))
        self.assertFalse(self.repo.claim(second.id, T0))
        self.assertEqual(self.repo.get_job_run(first.id).status, JobStatus.PROCESSING)
        self.assertEqual(self.repo.get_job_run(second.id).status, JobStatus.PENDING)

    def test_the_lock_is_per_job_name_not_per_day(self):
        other_day = self.repo.create_job_run(JOB, date(2026, 11, 10), T0)
        today = self.repo.create_job_run(JOB, DAY, T0)
        self.assertTrue(self.repo.claim(other_day.id, T0))
        self.assertFalse(self.repo.claim(today.id, T0))

    def test_a_different_job_does_not_share_the_lock(self):
        mine = self.repo.create_job_run(JOB, DAY, T0)
        other = self.repo.create_job_run("another_job", DAY, T0)
        self.assertTrue(self.repo.claim(mine.id, T0))
        self.assertTrue(self.repo.claim(other.id, T0))

    def test_claim_of_a_non_pending_run_raises(self):
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.repo.claim(run.id, T0)
        with self.assertRaises(JobRunStateError):
            self.repo.claim(run.id, T0)

    def test_complete_releases_the_lock(self):
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.repo.claim(run.id, T0)
        self.assertTrue(self.repo.complete(run.id, T0 + timedelta(seconds=5)))
        stored = self.repo.get_job_run(run.id)
        self.assertEqual(stored.status, JobStatus.COMPLETED)
        self.assertEqual(stored.finished_at, T0 + timedelta(seconds=5))
        self.assertFalse(self.repo.has_processing_lock(JOB))
        self.assertTrue(self.repo.has_completed_for_date(JOB, DAY))

    def test_complete_only_from_processing(self):
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.assertFalse(self.repo.complete(run.id, T0))
        self.assertEqual(self.repo.get_job_run(run.id).status, JobStatus.PENDING)

    def test_complete_twice_returns_false(self):
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.repo.claim(run.id, T0)
        self.assertTrue(self.repo.complete(run.id, T0))
        self.assertFalse(self.repo.complete(run.id, T0))

    def test_a_second_completed_for_the_same_day_is_rejected_by_the_database(self):
        insert_row(self.engine, self.table, status=JobStatus.COMPLETED)
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.repo.claim(run.id, T0)
        with self.assertRaises(AlreadyCompletedError):
            self.repo.complete(run.id, T0)
        self.assertEqual(self.repo.get_job_run(run.id).status, JobStatus.PROCESSING)

    def test_completed_rows_for_different_days_coexist(self):
        insert_row(self.engine, self.table, status=JobStatus.COMPLETED, target_date=date(2026, 11, 14))
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.repo.claim(run.id, T0)
        self.assertTrue(self.repo.complete(run.id, T0))

    def test_fail_records_the_message_from_pending_or_processing(self):
        pending = self.repo.create_job_run(JOB, DAY, T0)
        self.assertTrue(self.repo.fail(pending.id, "boom", T0))
        processing = self.repo.create_job_run(JOB, DAY, T0)
        self.repo.claim(processing.id, T0)
        self.assertTrue(self.repo.fail(processing.id, "kaboom", T0 + timedelta(seconds=2)))
        for run_id, message in ((pending.id, "boom"), (processing.id, "kaboom")):
            stored = self.repo.get_job_run(run_id)
            self.assertEqual((stored.status, stored.error_message), (JobStatus.FAILED, message))
            self.assertIsNotNone(stored.finished_at)
        self.assertFalse(self.repo.has_processing_lock(JOB))

    def test_fail_never_reopens_a_closed_run(self):
        run = self.repo.create_job_run(JOB, DAY, T0)
        self.repo.claim(run.id, T0)
        self.repo.complete(run.id, T0)
        self.assertFalse(self.repo.fail(run.id, "late", T0))
        self.assertEqual(self.repo.get_job_run(run.id).status, JobStatus.COMPLETED)

    def test_failed_rows_for_the_same_day_keep_the_history(self):
        for message in ("first", "second", "third"):
            run = self.repo.create_job_run(JOB, DAY, T0)
            self.repo.fail(run.id, message, T0)
        self.assertEqual(statuses(self.repo), [JobStatus.FAILED] * 3)

    def test_discard_only_removes_an_unfinished_run(self):
        pending = self.repo.create_job_run(JOB, DAY, T0)
        self.assertTrue(self.repo.discard(pending.id))
        self.assertIsNone(self.repo.get_job_run(pending.id))
        closed = insert_row(self.engine, self.table, status=JobStatus.COMPLETED)
        self.assertFalse(self.repo.discard(closed))
        self.assertEqual(self.repo.get_job_run(closed).status, JobStatus.COMPLETED)

    def test_has_completed_for_date_is_per_job_and_day(self):
        insert_row(self.engine, self.table, status=JobStatus.COMPLETED)
        self.assertTrue(self.repo.has_completed_for_date(JOB, DAY))
        self.assertFalse(self.repo.has_completed_for_date(JOB, date(2026, 11, 14)))
        self.assertFalse(self.repo.has_completed_for_date("another_job", DAY))

    def test_failed_does_not_count_as_completed(self):
        insert_row(self.engine, self.table, status=JobStatus.FAILED, error_message="x")
        self.assertFalse(self.repo.has_completed_for_date(JOB, DAY))

    def test_sweep_closes_processing_older_than_45_minutes(self):
        stale = insert_row(self.engine, self.table, status=JobStatus.PROCESSING, started_at=T0 - timedelta(minutes=46))
        self.assertEqual(self.repo.sweep_stale(JOB, T0), 1)
        stored = self.repo.get_job_run(stale)
        self.assertEqual((stored.status, stored.error_message), (JobStatus.FAILED, ABANDONED_PROCESSING_MESSAGE))
        self.assertEqual(stored.finished_at, T0)
        self.assertFalse(self.repo.has_processing_lock(JOB))

    def test_sweep_keeps_a_recent_processing_run(self):
        alive = insert_row(self.engine, self.table, status=JobStatus.PROCESSING, started_at=T0 - timedelta(minutes=44))
        self.assertEqual(self.repo.sweep_stale(JOB, T0), 0)
        self.assertEqual(self.repo.get_job_run(alive).status, JobStatus.PROCESSING)

    def test_sweep_closes_orphan_pending_after_5_minutes(self):
        stale = insert_row(self.engine, self.table, status=JobStatus.PENDING, created_at=T0 - timedelta(minutes=6))
        fresh = insert_row(self.engine, self.table, status=JobStatus.PENDING, created_at=T0 - timedelta(minutes=4))
        self.assertEqual(self.repo.sweep_stale(JOB, T0), 1)
        self.assertEqual(self.repo.get_job_run(stale).error_message, ABANDONED_PENDING_MESSAGE)
        self.assertEqual(self.repo.get_job_run(fresh).status, JobStatus.PENDING)

    def test_sweep_ignores_other_jobs_and_closed_rows(self):
        other = insert_row(
            self.engine, self.table, status=JobStatus.PROCESSING, job_name="another_job", started_at=T0 - timedelta(hours=3)
        )
        done = insert_row(self.engine, self.table, status=JobStatus.COMPLETED, created_at=T0 - timedelta(hours=3))
        self.assertEqual(self.repo.sweep_stale(JOB, T0), 0)
        self.assertEqual(self.repo.get_job_run(other).status, JobStatus.PROCESSING)
        self.assertEqual(self.repo.get_job_run(done).status, JobStatus.COMPLETED)

    def test_list_job_runs_filters_by_day(self):
        insert_row(self.engine, self.table, status=JobStatus.COMPLETED, target_date=date(2026, 11, 14))
        insert_row(self.engine, self.table, status=JobStatus.FAILED, error_message="x")
        self.assertEqual(len(self.repo.list_job_runs(JOB)), 2)
        self.assertEqual(len(self.repo.list_job_runs(JOB, DAY)), 1)

    def test_schema_ready(self):
        self.assertTrue(self.repo.schema_ready())

    def test_the_two_partial_unique_indexes_exist_in_the_database(self):
        with self.assertRaises(IntegrityError):
            insert_row(self.engine, self.table, status=JobStatus.PROCESSING)
            insert_row(self.engine, self.table, status=JobStatus.PROCESSING, target_date=date(2026, 11, 14))


class RunnerCases:
    """`run_job` con una función de trabajo falsa: sin Prefect ni subprocesos."""

    def setUp_logging(self):
        self.stream = io.StringIO()
        self.logger = configure_logging(self.stream)
        self.addCleanup(logging.getLogger(LOGGER_NAME).handlers.clear)
        self.calls = []
        self.sleeps = []

    def run_job(self, work=None, repo=None, **kwargs):
        def default_work():
            self.calls.append("work")

        return run_job(
            repo or self.repo,
            JOB,
            DAY,
            work or default_work,
            logger=self.logger,
            clock=self.clock,
            sleep=self.sleeps.append,
            **kwargs,
        )

    def lines(self):
        return [line for line in self.stream.getvalue().splitlines() if line]

    def test_a_successful_run_ends_completed(self):
        result = self.run_job()
        self.assertEqual(result.outcome, Outcome.COMPLETED)
        self.assertEqual(self.calls, ["work"])
        (row,) = self.repo.list_job_runs(JOB, DAY)
        self.assertEqual(row.id, result.run_id)
        self.assertEqual((row.status, row.target_date, row.error_message), (JobStatus.COMPLETED, DAY, None))
        self.assertIsNotNone(row.started_at)
        self.assertIsNotNone(row.finished_at)

    def test_every_log_line_has_timestamp_level_job_and_status(self):
        self.run_job()
        lines = self.lines()
        self.assertGreaterEqual(len(lines), 3)
        for line in lines:
            self.assertRegex(line, LINE)
        self.assertEqual([re.search(r"status=(\w+)", line).group(1) for line in lines], ["pending", "processing", "completed"])

    def test_work_exception_leaves_failed_with_the_message_and_logs_error(self):
        def boom():
            raise ValueError("bad input")

        result = self.run_job(boom)
        self.assertEqual((result.outcome, result.error_message), (Outcome.FAILED, "ValueError: bad input"))
        (row,) = self.repo.list_job_runs(JOB, DAY)
        self.assertEqual((row.status, row.error_message), (JobStatus.FAILED, "ValueError: bad input"))
        self.assertIsNotNone(row.finished_at)
        self.assertFalse(self.repo.has_processing_lock(JOB))
        error_lines = [line for line in self.lines() if " ERROR " in line]
        self.assertEqual(len(error_lines), 1)
        self.assertRegex(error_lines[0], r"status=failed .*ValueError: bad input")

    def test_no_row_is_left_processing_after_any_failure(self):
        for error in (RuntimeError("a"), KeyError("b"), OSError("c")):
            with self.subTest(error=type(error).__name__):
                self.run_job(lambda error=error: (_ for _ in ()).throw(error))
        self.assertNotIn(JobStatus.PROCESSING, statuses(self.repo))
        self.assertNotIn(JobStatus.PENDING, statuses(self.repo))

    def test_keyboard_interrupt_and_system_exit_mark_failed_and_propagate(self):
        for error in (KeyboardInterrupt(), SystemExit(1)):
            with self.subTest(error=type(error).__name__):

                def stop(error=error):
                    raise error

                with self.assertRaises(type(error)):
                    self.run_job(stop)
        self.assertEqual(statuses(self.repo), [JobStatus.FAILED, JobStatus.FAILED])
        self.assertFalse(self.repo.has_processing_lock(JOB))

    def test_retry_after_failure_is_allowed_and_keeps_the_history(self):
        self.run_job(lambda: (_ for _ in ()).throw(RuntimeError("first")))
        self.clock.advance(minutes=1)  # el orden del historial es por created_at
        result = self.run_job()
        self.assertEqual(result.outcome, Outcome.COMPLETED)
        self.assertEqual(statuses(self.repo), [JobStatus.FAILED, JobStatus.COMPLETED])

    def test_second_run_for_a_completed_day_is_skipped_without_work_or_rows(self):
        self.run_job()
        self.calls.clear()
        result = self.run_job()
        self.assertEqual(result.outcome, Outcome.SKIPPED)
        self.assertEqual(self.calls, [])
        self.assertEqual(statuses(self.repo), [JobStatus.COMPLETED])
        self.assertRegex(self.lines()[-1], r"INFO job=nightly_export status=skipped .*already_completed")

    def test_a_live_lock_aborts_silently_without_work_or_rows(self):
        held = insert_row(self.engine, self.table, status=JobStatus.PROCESSING, started_at=T0 - timedelta(minutes=5))
        result = self.run_job()
        self.assertEqual(result.outcome, Outcome.LOCKED)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.repo.list_job_runs(JOB)), 1)
        self.assertEqual(self.repo.get_job_run(held).status, JobStatus.PROCESSING)
        self.assertRegex(self.lines()[-1], r"INFO job=nightly_export status=locked .*another_instance_processing")
        self.assertNotIn(" ERROR ", self.stream.getvalue())

    def test_losing_the_claim_deletes_the_own_pending_row(self):
        held = insert_row(self.engine, self.table, status=JobStatus.PROCESSING, started_at=T0 - timedelta(minutes=5))

        class StaleReads(JobRunRepository):
            """Las dos lecturas rápidas ven «libre» (como dos instancias que comprueban a la vez)."""

            def has_processing_lock(self, job_name):
                return False

        repo = StaleReads(self.engine, self.table)
        result = self.run_job(repo=repo)
        self.assertEqual(result.outcome, Outcome.LOCKED)
        self.assertEqual(self.calls, [])
        self.assertEqual([row.id for row in self.repo.list_job_runs(JOB)], [held])

    def test_completed_by_another_instance_between_check_and_claim_is_skipped(self):
        engine, table = self.engine, self.table

        class CompletesAfterClaim(JobRunRepository):
            """La otra instancia termina justo después de nuestro claim (la ventana de carrera)."""

            def claim(self, run_id, now):
                insert_row(engine, table, status=JobStatus.COMPLETED)
                return super().claim(run_id, now)

        result = self.run_job(repo=CompletesAfterClaim(self.engine, self.table))
        self.assertEqual(result.outcome, Outcome.SKIPPED)
        self.assertEqual(self.calls, [])
        self.assertEqual(statuses(self.repo), [JobStatus.COMPLETED])

    def test_abandoned_processing_row_is_swept_and_the_new_run_proceeds(self):
        zombie = insert_row(self.engine, self.table, status=JobStatus.PROCESSING, started_at=T0 - timedelta(minutes=50))
        result = self.run_job()
        self.assertEqual(result.outcome, Outcome.COMPLETED)
        self.assertEqual(self.repo.get_job_run(zombie).status, JobStatus.FAILED)
        self.assertEqual(self.repo.get_job_run(zombie).error_message, ABANDONED_PROCESSING_MESSAGE)
        self.assertIn("abandoned rows closed", self.stream.getvalue())

    def test_lock_lost_while_working_does_not_mark_completed(self):
        def work():
            # Otra ejecución barre esta fila como zombi mientras seguimos vivos.
            self.assertEqual(self.repo.sweep_stale(JOB, self.clock() + timedelta(minutes=46)), 1)

        result = self.run_job(work)
        self.assertEqual(result.outcome, Outcome.FAILED)
        self.assertIn("lock lost", result.error_message)
        (row,) = self.repo.list_job_runs(JOB, DAY)
        self.assertEqual(row.status, JobStatus.FAILED)
        self.assertEqual(row.error_message, ABANDONED_PROCESSING_MESSAGE)

    def test_a_completed_row_appearing_during_work_fails_the_run(self):
        result = self.run_job(lambda: insert_row(self.engine, self.table, status=JobStatus.COMPLETED))
        self.assertEqual(result.outcome, Outcome.FAILED)
        self.assertIn("already exists", result.error_message)
        self.assertEqual(sorted(statuses(self.repo)), [JobStatus.COMPLETED, JobStatus.FAILED])
        self.assertFalse(self.repo.has_processing_lock(JOB))

    def test_failure_write_is_retried_three_times_then_the_row_stays_processing(self):
        engine, table = self.engine, self.table

        class WriteDown(JobRunRepository):
            attempts = 0

            def fail(self, run_id, message, now):
                WriteDown.attempts += 1
                raise OperationalError("UPDATE", {}, Exception("connection to server at db.example.com lost"))

        result = self.run_job(lambda: (_ for _ in ()).throw(RuntimeError("boom")), repo=WriteDown(engine, table))
        self.assertEqual(result.outcome, Outcome.FAILED)
        self.assertEqual(WriteDown.attempts, 4)
        self.assertEqual(self.sleeps, [1.0, 2.0, 4.0])
        (row,) = self.repo.list_job_runs(JOB, DAY)
        self.assertEqual(row.status, JobStatus.PROCESSING)
        text = self.stream.getvalue()
        self.assertIn("could not record the failure", text)
        self.assertNotIn("db.example.com", text)
        # ...y la siguiente ejecución, pasados 45 min, la cierra como abandonada.
        self.clock.advance(minutes=46)
        self.assertEqual(self.repo.sweep_stale(JOB, self.clock()), 1)
        self.assertEqual(self.repo.get_job_run(row.id).status, JobStatus.FAILED)

    def test_failure_write_succeeds_on_a_retry(self):
        engine, table = self.engine, self.table

        class Flaky(JobRunRepository):
            attempts = 0

            def fail(self, run_id, message, now):
                Flaky.attempts += 1
                if Flaky.attempts < 3:
                    raise OperationalError("UPDATE", {}, Exception("down"))
                return super().fail(run_id, message, now)

        self.run_job(lambda: (_ for _ in ()).throw(RuntimeError("boom")), repo=Flaky(engine, table))
        self.assertEqual(statuses(self.repo), [JobStatus.FAILED])
        self.assertEqual(self.sleeps, [1.0, 2.0])

    def test_completion_write_failure_leaves_processing_for_the_sweep(self):
        engine, table = self.engine, self.table

        class CompleteDown(JobRunRepository):
            def complete(self, run_id, now):
                raise OperationalError("UPDATE", {}, Exception("down"))

        result = self.run_job(repo=CompleteDown(engine, table))
        self.assertEqual(result.outcome, Outcome.FAILED)
        self.assertIn("could not record completion", result.error_message)
        self.assertEqual(statuses(self.repo), [JobStatus.PROCESSING])

    def test_database_down_before_the_claim_propagates_and_leaves_nothing(self):
        engine, table = self.engine, self.table

        class ClaimDown(JobRunRepository):
            def claim(self, run_id, now):
                raise OperationalError("UPDATE", {}, Exception("down"))

        with self.assertRaises(OperationalError):
            self.run_job(repo=ClaimDown(engine, table))
        self.assertEqual(self.repo.list_job_runs(JOB), [])
        self.assertEqual(self.calls, [])

    def test_error_message_and_log_never_contain_the_database_url_or_password(self):
        url = "postgresql://nexova_app:s3cretPass@db.internal.example:6543/postgres"

        def boom():
            raise RuntimeError(f"could not connect to {url} (password s3cretPass)")

        with mock.patch.dict(os.environ, {"DATABASE_URL": url}):
            result = self.run_job(boom)
            logged = self.stream.getvalue()
        row = self.repo.get_job_run(result.run_id)
        for text in (result.error_message, row.error_message, logged):
            self.assertNotIn("s3cretPass", text)
            self.assertNotIn("db.internal.example", text)
            self.assertNotIn("nexova_app", text)
