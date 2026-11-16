"""`main()` con la base en SQLite y el pipeline simulado: códigos de salida, filas y logs."""

import contextlib
import io
import os
import re
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest import mock

from job_runner import JobRunRepository, JobStatus
from job_runner.states import ABANDONED_PROCESSING_MESSAGE
from sqlalchemy.exc import OperationalError

from .cases import LINE
from .support import TABLE, events_engine, insert_event, insert_row, load_script

script = load_script()
NOW = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)
DAY = date(2026, 11, 15)
URL = "postgresql://nexova_app:s3cretPass@127.0.0.1:5432/nexova_test"
ENV = {"DATABASE_URL": URL}


class MainTests(unittest.TestCase):
    def setUp(self):
        self.engine = events_engine()
        self.addCleanup(self.engine.dispose)
        self.repo = JobRunRepository(self.engine, TABLE)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out_dir = Path(directory.name)
        self.pipeline_calls = []
        patches = [
            mock.patch.object(script, "utc_now", return_value=NOW),
            mock.patch.object(script, "build_engine", return_value=self.engine),
            mock.patch.object(script, "JOB_RUNS_TABLE", TABLE),
            mock.patch.object(script, "OUTPUT_DIR", self.out_dir),
            mock.patch.object(script, "run_pipeline", side_effect=lambda week, url: self.pipeline_calls.append(week)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        mock.patch.object(self.engine, "dispose").start()  # el motor es de la prueba

    def run_main(self, environ=None, expected_exit=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = script.main([], environ=environ if environ is not None else ENV)
        if expected_exit is not None:
            self.assertEqual(code, expected_exit, out.getvalue() + err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def test_completed_exits_0_writes_the_csv_and_runs_the_pipeline_for_the_sunday_week(self):
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        (row,) = self.repo.list_job_runs("nightly_export")
        self.assertEqual((row.status, row.target_date), (JobStatus.COMPLETED, DAY))
        self.assertTrue((self.out_dir / "telemetry_2026-11-15.csv").exists())
        self.assertEqual(self.pipeline_calls, [date(2026, 11, 9)])
        for line in out.splitlines():
            self.assertRegex(line, LINE)

    def test_target_date_selects_the_day_and_its_week(self):
        self.run_main({**ENV, "TARGET_DATE": "2026-10-27"}, expected_exit=0)
        self.assertEqual(self.pipeline_calls, [date(2026, 10, 26)])
        self.assertTrue((self.out_dir / "telemetry_2026-10-27.csv").exists())
        self.assertEqual(self.repo.list_job_runs("nightly_export")[0].target_date, date(2026, 10, 27))

    def test_second_run_is_skipped_exit_0_without_rows_csv_or_pipeline(self):
        self.run_main(expected_exit=0)
        csv_file = self.out_dir / "telemetry_2026-11-15.csv"
        before = csv_file.stat().st_mtime_ns
        self.pipeline_calls.clear()
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.repo.list_job_runs("nightly_export")), 1)
        self.assertEqual(self.pipeline_calls, [])
        self.assertEqual(csv_file.stat().st_mtime_ns, before)
        self.assertRegex(out, r"status=skipped .*already_completed")

    def test_locked_exits_0_silently_without_error_lines(self):
        insert_row(self.engine, TABLE, status=JobStatus.PROCESSING, target_date=date(2026, 11, 1),
                   started_at=datetime.now(UTC) - timedelta(minutes=5))
        code, out, err = self.run_main()
        self.assertEqual(code, 0)
        self.assertRegex(out, r"status=locked ")
        self.assertNotIn(" ERROR ", out)
        self.assertEqual(err, "")
        self.assertEqual(self.pipeline_calls, [])

    def test_pipeline_failure_exits_1_with_failed_and_the_message(self):
        with mock.patch.object(script, "run_pipeline", side_effect=script.PipelineError("pipeline exited with code 1 (run failed)")):
            code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        (row,) = self.repo.list_job_runs("nightly_export")
        self.assertEqual(row.status, JobStatus.FAILED)
        self.assertEqual(row.error_message, "PipelineError: pipeline exited with code 1 (run failed)")
        self.assertRegex(out, r" ERROR job=nightly_export status=failed ")

    def test_after_a_failure_the_same_day_can_be_retried_and_the_csv_is_kept(self):
        with mock.patch.object(script, "run_pipeline", side_effect=script.PipelineError("boom")):
            self.run_main(expected_exit=1)
        csv_file = self.out_dir / "telemetry_2026-11-15.csv"
        before = csv_file.stat().st_mtime_ns
        _, out, _ = self.run_main(expected_exit=0)
        self.assertEqual(csv_file.stat().st_mtime_ns, before)
        self.assertIn("csv already exists, export skipped", out)
        self.assertEqual(sorted(r.status for r in self.repo.list_job_runs("nightly_export")), [JobStatus.COMPLETED, JobStatus.FAILED])

    def test_sigterm_leaves_the_row_failed(self):
        def terminated(week, url):
            script._on_sigterm(15, None)

        with mock.patch.object(script, "run_pipeline", side_effect=terminated):
            code, _, _ = self.run_main()
        self.assertEqual(code, 1)
        (row,) = self.repo.list_job_runs("nightly_export")
        self.assertEqual((row.status, row.error_message), (JobStatus.FAILED, "TerminatedBySignal: terminated by SIGTERM"))

    def test_the_sigterm_handler_is_installed_during_the_run_and_restored_after(self):
        import signal

        before = signal.getsignal(signal.SIGTERM)
        seen = []
        with mock.patch.object(script, "run_pipeline", side_effect=lambda w, u: seen.append(signal.getsignal(signal.SIGTERM))):
            self.run_main(expected_exit=0)
        self.assertIs(seen[0], script._on_sigterm)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_a_zombie_row_is_swept_and_the_run_completes(self):
        zombie = insert_row(self.engine, TABLE, status=JobStatus.PROCESSING, target_date=date(2026, 11, 1),
                            started_at=datetime.now(UTC) - timedelta(minutes=50))
        self.run_main(expected_exit=0)
        self.assertEqual(self.repo.get_job_run(zombie).error_message, ABANDONED_PROCESSING_MESSAGE)

    def test_invalid_target_date_exits_2_without_connecting_or_creating_rows(self):
        for raw in ("2026-13-01", "20261015", "2026-11-16", "2026-11-17", "2020-01-01", "nope"):
            with self.subTest(raw=raw):
                script.build_engine.reset_mock()
                code, out, err = self.run_main({**ENV, "TARGET_DATE": raw})
                self.assertEqual(code, 2)
                script.build_engine.assert_not_called()
                self.assertEqual(self.repo.list_job_runs("nightly_export"), [])
                self.assertIn("TARGET_DATE", err)
                self.assertNotIn(raw, err)  # (el log lleva su propia marca de tiempo)
                self.assertRegex(out.strip(), r"ERROR job=nightly_export status=rejected target_date=-")

    def test_missing_database_url_exits_2(self):
        with mock.patch.object(script, "resolve_database_target", side_effect=script.ConfigError("DATABASE_URL is not set")):
            code, _, err = self.run_main({})
        self.assertEqual(code, 2)
        self.assertIn("DATABASE_URL is not set", err)

    def test_schema_missing_exits_2_with_the_migration_command(self):
        with mock.patch.object(script, "JOB_RUNS_TABLE", "no_such_table"):
            code, out, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("job_runner.migrate", err)
        self.assertEqual(self.pipeline_calls, [])
        self.assertRegex(out, r"ERROR job=nightly_export status=rejected .*schema ops is missing")

    def test_database_unavailable_exits_2_with_only_the_class(self):
        error = OperationalError("x", {}, Exception(f"could not connect to {URL}"))
        with mock.patch.object(JobRunRepository, "schema_ready", side_effect=error):
            code, out, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("OperationalError", err)
        self.assertNotIn("s3cretPass", out + err)

    def test_nothing_sensitive_is_printed(self):
        with mock.patch.object(script, "run_pipeline", side_effect=script.PipelineError("boom")):
            _, out, err = self.run_main()
        for text in (out, err):
            self.assertNotIn("s3cretPass", text)
            self.assertNotIn("nexova_app", text)
        self.assertIn("host_127.0.0.1", out)

    def test_the_real_export_runs_with_rows_from_the_database(self):
        insert_event(self.engine, "00000000-0000-4000-9000-000000000001", datetime(2026, 11, 15, 10, 0, tzinfo=UTC), {"office": "miami"})
        insert_event(self.engine, "00000000-0000-4000-9000-000000000002", datetime(2026, 11, 14, 10, 0, tzinfo=UTC), {"office": "miami"})
        _, out, _ = self.run_main(expected_exit=0)
        self.assertIn("csv written file=telemetry_2026-11-15.csv rows=1", out)
        self.assertEqual(len((self.out_dir / "telemetry_2026-11-15.csv").read_text().splitlines()), 2)

    def test_help_exits_0_and_bad_arguments_exit_2(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(script.main(["--help"], environ=ENV), 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(script.main(["--nope"], environ=ENV), 2)
