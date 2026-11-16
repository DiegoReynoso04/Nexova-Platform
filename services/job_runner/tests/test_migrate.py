import contextlib
import io
import unittest
from unittest import mock

from job_runner import migrate
from job_runner.config import target_from_url
from job_runner.migrate import DatabaseState, pending_statements
from job_runner.states import ONE_COMPLETED_INDEX, ONE_PROCESSING_INDEX, TARGET_INDEX

ALL_INDEXES = frozenset({TARGET_INDEX, ONE_PROCESSING_INDEX, ONE_COMPLETED_INDEX})
EMPTY = DatabaseState(False, frozenset(), frozenset(), frozenset(), False, ("anon", "authenticated"))
READY = DatabaseState(True, frozenset({"job_runs"}), ALL_INDEXES, frozenset({"job_runs"}), False, ("anon",))
LOCAL = "postgresql://nexova_app:s3cretPass@127.0.0.1:55432/nexova_test"
REMOTE = "postgresql://nexova_app:s3cretPass@db.internal.example:6543/postgres"


class PendingStatementsTests(unittest.TestCase):
    def test_empty_database_gets_everything_in_order(self):
        statements = pending_statements(EMPTY)
        self.assertEqual(statements[0], "CREATE SCHEMA IF NOT EXISTS ops")
        self.assertTrue(statements[1].startswith("CREATE TABLE IF NOT EXISTS ops.job_runs"))
        self.assertEqual(len(statements), 8)
        self.assertEqual(statements[5], "ALTER TABLE ops.job_runs ENABLE ROW LEVEL SECURITY")
        self.assertEqual(statements[6], "REVOKE ALL ON SCHEMA ops FROM PUBLIC, anon, authenticated")
        self.assertEqual(statements[7], "REVOKE ALL ON ALL TABLES IN SCHEMA ops FROM PUBLIC, anon, authenticated")

    def test_the_ddl_has_the_fields_of_the_ticket_and_the_lock_index(self):
        text = " ".join(pending_statements(EMPTY))
        for column in ("id uuid", "job_name text", "target_date date", "status text", "started_at timestamptz",
                       "finished_at timestamptz", "error_message text", "created_at timestamptz"):
            self.assertIn(column, text)
        self.assertIn("(job_name, target_date)", text)
        self.assertIn(f"{ONE_PROCESSING_INDEX} ON ops.job_runs (job_name) WHERE status = 'processing'", text)
        self.assertIn(f"{ONE_COMPLETED_INDEX} ON ops.job_runs (job_name, target_date) WHERE status = 'completed'", text)

    def test_nothing_to_do_when_everything_exists(self):
        self.assertEqual(pending_statements(READY), [])

    def test_missing_pieces_are_added_alone(self):
        no_index = DatabaseState(True, frozenset({"job_runs"}), ALL_INDEXES - {ONE_PROCESSING_INDEX}, frozenset({"job_runs"}), False, ())
        self.assertEqual(len(pending_statements(no_index)), 1)
        no_rls = DatabaseState(True, frozenset({"job_runs"}), ALL_INDEXES, frozenset(), False, ())
        self.assertEqual(pending_statements(no_rls), ["ALTER TABLE ops.job_runs ENABLE ROW LEVEL SECURITY"])

    def test_a_new_table_in_an_existing_schema_is_revoked_too(self):
        state = DatabaseState(True, frozenset(), frozenset(), frozenset(), False, ())
        self.assertTrue(any(s.startswith("REVOKE ALL ON ALL TABLES") for s in pending_statements(state)))

    def test_leftover_grants_are_revoked(self):
        state = DatabaseState(True, frozenset({"job_runs"}), ALL_INDEXES, frozenset({"job_runs"}), True, ())
        self.assertEqual(len(pending_statements(state)), 2)


class RunTests(unittest.TestCase):
    def run_cli(self, argv, target):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = migrate.run(argv, target=target)
        return code, out.getvalue(), err.getvalue()

    def test_a_non_local_database_is_refused_without_allow_demo(self):
        with mock.patch.object(migrate, "build_engine") as engine:
            code, out, err = self.run_cli([], target_from_url(REMOTE, "entorno"))
        self.assertEqual(code, 1)
        engine.assert_not_called()
        self.assertIn("--allow-demo", err)
        for text in (out, err):
            self.assertNotIn("s3cretPass", text)
            self.assertNotIn("nexova_app", text)

    def test_dry_run_prints_the_sql_and_applies_nothing(self):
        with mock.patch.object(migrate, "build_engine"), mock.patch.object(
            migrate, "migrate", return_value=["CREATE SCHEMA IF NOT EXISTS ops"]
        ) as apply:
            code, out, _ = self.run_cli(["--dry-run"], target_from_url(LOCAL, "entorno"))
        self.assertEqual(code, 0)
        apply.assert_called_once()
        self.assertTrue(apply.call_args.kwargs["dry_run"])
        self.assertIn("SQL pendiente (no se ha aplicado)", out)
        self.assertIn("DATABASE_URL: entorno, host 127.0.0.1", out)
        self.assertNotIn("s3cretPass", out)

    def test_nothing_to_migrate_message(self):
        with mock.patch.object(migrate, "build_engine"), mock.patch.object(migrate, "migrate", return_value=[]):
            code, out, _ = self.run_cli([], target_from_url(LOCAL, "entorno"))
        self.assertEqual(code, 0)
        self.assertIn("Nada que migrar", out)

    def test_database_failure_exits_2_with_the_class_only(self):
        from sqlalchemy.exc import OperationalError

        error = OperationalError("x", {}, Exception(f"connect to {LOCAL} failed"))
        with mock.patch.object(migrate, "build_engine"), mock.patch.object(migrate, "migrate", side_effect=error):
            code, out, err = self.run_cli([], target_from_url(LOCAL, "entorno"))
        self.assertEqual(code, 2)
        self.assertIn("OperationalError", err)
        self.assertNotIn("s3cretPass", out + err)

    def test_still_granted_rolls_back_with_exit_1(self):
        with mock.patch.object(migrate, "build_engine"), mock.patch.object(
            migrate, "migrate", side_effect=migrate.StillGrantedError()
        ):
            code, _, err = self.run_cli([], target_from_url(LOCAL, "entorno"))
        self.assertEqual(code, 1)
        self.assertIn("Se ha deshecho todo", err)

    def test_missing_configuration_exits_1(self):
        with mock.patch.object(migrate, "resolve_database_target", side_effect=migrate.ConfigError("DATABASE_URL is not set")):
            code, _, err = self.run_cli([], None)
        self.assertEqual(code, 1)
        self.assertIn("DATABASE_URL is not set", err)

    def test_bad_arguments_exit_1(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(migrate.run(["--nope"]), 1)
