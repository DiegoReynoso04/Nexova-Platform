"""Origen de `DATABASE_URL` (D5), guarda de la migración y salidas del CLI. Sin base de datos."""

import contextlib
import io
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from business_performance import config, migrate
from business_performance.config import ConfigError, read_env_file_value, resolve_database_target

import pipeline
from tests.support import closed_week

FAKE_REMOTE = "postgresql://fake_user:fake-password-123@db.example.invalid:6543/postgres"
FAKE_LOCAL = "postgresql://fake_user:fake-password-123@127.0.0.1:55432/nexova_test"


def _env_file(text: str) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="nexova-env-"))
    path = directory / ".env"
    path.write_text(text, encoding="utf-8")
    return path


class DatabaseTargetTests(unittest.TestCase):
    def test_terminal_environment_wins_over_the_env_file(self):
        env_file = _env_file(f"DATABASE_URL={FAKE_REMOTE}\n")
        target = resolve_database_target({"DATABASE_URL": FAKE_LOCAL}, env_file)
        self.assertEqual((target.source, target.host, target.is_local), ("entorno", "127.0.0.1", True))
        self.assertTrue(target.url.startswith("postgresql+psycopg2://"))

    def test_falls_back_to_the_env_file(self):
        env_file = _env_file(f"# comment\nJWT_SECRET_KEY=x\nexport DATABASE_URL=\"{FAKE_REMOTE}\"\n")
        target = resolve_database_target({}, env_file)
        self.assertEqual((target.source, target.host, target.is_local), (".env de la raíz", "db.example.invalid", False))

    def test_only_the_host_is_ever_shown(self):
        target = resolve_database_target({"DATABASE_URL": FAKE_REMOTE}, Path("missing.env"))
        for text in (target.describe(), repr(target), str(target)):
            with self.subTest(text=text):
                self.assertNotIn("fake-password-123", text)
                self.assertNotIn("fake_user", text)
        self.assertEqual(target.describe(), "DATABASE_URL: entorno, host db.example.invalid")

    def test_missing_or_invalid_url(self):
        with self.assertRaises(ConfigError):
            resolve_database_target({}, Path("missing.env"))
        with self.assertRaises(ConfigError):
            resolve_database_target({"DATABASE_URL": "sqlite:///x.db"}, Path("missing.env"))
        try:
            resolve_database_target({"DATABASE_URL": "mysql://u:secret@h/db"}, Path("missing.env"))
        except ConfigError as error:
            self.assertNotIn("secret", str(error))

    def test_env_file_reader_reads_only_that_key(self):
        env_file = _env_file("A=1\nDATABASE_URL='x'\nB = 2\n")
        self.assertEqual(read_env_file_value(env_file, "DATABASE_URL"), "x")
        self.assertEqual(read_env_file_value(env_file, "B"), "2")
        self.assertIsNone(read_env_file_value(env_file, "C"))

    def test_env_file_is_the_repository_root(self):
        self.assertEqual(config.ENV_FILE, Path(__file__).resolve().parents[3] / ".env")


def _run_capturing(function, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = function(*args, **kwargs)
    return code, out.getvalue(), err.getvalue()


class MigrationGuardTests(unittest.TestCase):
    def test_remote_database_needs_allow_demo_and_is_never_touched(self):
        target = config.target_from_url(FAKE_REMOTE, "entorno")
        with mock.patch.object(migrate, "build_engine") as build:
            code, out, err = _run_capturing(migrate.run, ["--dry-run"], target=target)
        self.assertEqual(code, migrate.CONFIG_ERROR_EXIT)
        self.assertIn("--allow-demo", err)
        self.assertIn("host db.example.invalid", out)
        build.assert_not_called()
        self.assertNotIn("fake-password-123", out + err)

    def test_allow_demo_lets_it_through(self):
        target = config.target_from_url(FAKE_REMOTE, "entorno")
        with mock.patch.object(migrate, "build_engine"), mock.patch.object(migrate, "migrate", return_value=[]):
            code, out, _ = _run_capturing(migrate.run, ["--dry-run", "--allow-demo"], target=target)
        self.assertEqual(code, 0)
        self.assertIn("Nada que migrar", out)

    def test_local_database_needs_no_flag(self):
        target = config.target_from_url(FAKE_LOCAL, "entorno")
        with mock.patch.object(migrate, "build_engine"), mock.patch.object(migrate, "migrate", return_value=["X"]):
            code, out, _ = _run_capturing(migrate.run, [], target=target)
        self.assertEqual(code, 0)
        self.assertIn("Aplicado en una transacción", out)


class MigrationStatementsTests(unittest.TestCase):
    EMPTY = migrate.DatabaseState(False, frozenset(), frozenset(), frozenset(), False, ())

    def test_everything_is_pending_on_an_empty_database(self):
        statements = migrate.pending_statements(self.EMPTY)
        self.assertEqual(statements[0], "CREATE SCHEMA IF NOT EXISTS reporting")
        self.assertTrue(statements[1].startswith("CREATE TABLE IF NOT EXISTS reporting.pipeline_runs"))
        self.assertTrue(statements[2].startswith("CREATE TABLE IF NOT EXISTS reporting.weekly_office_program_performance"))
        self.assertIn("REVOKE ALL ON ALL TABLES IN SCHEMA reporting FROM PUBLIC", statements)

    def test_supabase_roles_are_revoked_when_they_exist(self):
        state = migrate.DatabaseState(False, frozenset(), frozenset(), frozenset(), False, ("anon", "authenticated"))
        self.assertIn("REVOKE ALL ON SCHEMA reporting FROM PUBLIC, anon, authenticated", migrate.pending_statements(state))

    def test_nothing_is_pending_when_everything_exists(self):
        state = migrate.DatabaseState(
            True,
            frozenset({"pipeline_runs", "weekly_office_program_performance"}),
            frozenset(migrate.INDEXES),
            frozenset({"pipeline_runs", "weekly_office_program_performance"}),
            False,
            (),
        )
        self.assertEqual(migrate.pending_statements(state), [])

    def test_the_briefing_ddl_is_intact(self):
        briefing = (Path(__file__).resolve().parents[3] / "docs"
                    / "proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md").read_text(encoding="utf-8")
        start = briefing.index("create table reporting.weekly_office_program_performance (")
        block = briefing[start:briefing.index(");", start)]
        ddl = migrate.CREATE_WEEKLY_TABLE
        for line in block.splitlines()[1:]:
            line = line.strip().rstrip(",")
            if line:
                with self.subTest(line=line):
                    self.assertIn(line, ddl)


class CliTests(unittest.TestCase):
    def test_non_monday_and_bad_combinations_exit_2(self):
        for argv in (["--week-start", "2026-11-03"], ["--to", closed_week().isoformat()], ["--week-start", "x"]):
            with self.subTest(argv=argv):
                code, _, _ = _run_capturing(pipeline.main, argv)
                self.assertEqual(code, pipeline.CONFIG_EXIT)

    def test_current_week_is_refused(self):
        current = closed_week() + timedelta(weeks=1)
        code, _, err = _run_capturing(pipeline.main, ["--week-start", current.isoformat()])
        self.assertEqual(code, pipeline.CONFIG_EXIT)
        self.assertIn("closed weeks", err)

    def test_missing_schema_exits_2_with_the_migration_command_and_no_traceback(self):
        fake = mock.Mock()
        fake.schema_ready.return_value = False
        with mock.patch.dict("os.environ", {"DATABASE_URL": FAKE_LOCAL}), \
                mock.patch.object(pipeline, "PostgresRepository", return_value=fake), \
                mock.patch.object(pipeline, "weekly_office_program_performance") as flow:
            code, out, err = _run_capturing(pipeline.main, [])
        self.assertEqual(code, pipeline.CONFIG_EXIT)
        self.assertIn("python -m business_performance.migrate", err)
        self.assertNotIn("Traceback", err)
        self.assertIn("host 127.0.0.1", out)
        flow.assert_not_called()

    def test_unreachable_database_exits_2_without_the_url(self):
        fake = mock.Mock()
        fake.schema_ready.side_effect = RuntimeError("could not connect to fake-password-123")
        with mock.patch.dict("os.environ", {"DATABASE_URL": FAKE_LOCAL}), \
                mock.patch.object(pipeline, "PostgresRepository", return_value=fake):
            code, out, err = _run_capturing(pipeline.main, [])
        self.assertEqual(code, pipeline.CONFIG_EXIT)
        self.assertNotIn("fake-password-123", out + err)

    def test_default_is_the_last_closed_week(self):
        week_from, week_to = pipeline.requested_weeks("manual", None, datetime.now(UTC))
        self.assertEqual((week_from, week_to), (closed_week(), closed_week()))


if __name__ == "__main__":
    unittest.main()
