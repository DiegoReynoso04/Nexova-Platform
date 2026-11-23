"""`python -m task_queue.migrate`, sin base: SQL pendiente, guarda de la demo y códigos de salida.

Lo propio de PostgreSQL (aplicarla, RLS, privilegios y el orden con
`job_runner.migrate`) está en `test_postgres_integration.py`.
"""

import contextlib
import io
import unittest
from unittest import mock

from job_runner.config import target_from_url
from sqlalchemy.exc import OperationalError

from task_queue import migrate
from task_queue.migrate import CREATE_INDEX, CREATE_SCHEMA, DatabaseState, pending_statements

LOCAL = "postgresql://nexova_app:local-Pass-1@127.0.0.1:55432/nexova_test"
DEMO = "postgresql://postgres:demo-Pass-2@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
ROLES = ("anon", "authenticated", "service_role")


def state(**overrides):
    values = dict(schema_exists=True, table_exists=True, index_exists=True, rls_enabled=True, granted=False, supabase_roles=ROLES)
    values.update(overrides)
    return DatabaseState(**values)


class PendingStatementsTests(unittest.TestCase):
    def test_empty_database_gets_everything_in_order(self):
        statements = pending_statements(state(schema_exists=False, table_exists=False, index_exists=False, rls_enabled=False))
        self.assertEqual(statements[0], CREATE_SCHEMA)
        self.assertTrue(statements[1].startswith("CREATE TABLE IF NOT EXISTS ops.task_dead_letters ("))
        self.assertEqual(statements[2], CREATE_INDEX)
        self.assertEqual(statements[3], "ALTER TABLE ops.task_dead_letters ENABLE ROW LEVEL SECURITY")
        self.assertEqual(
            statements[4:],
            [
                "REVOKE ALL ON SCHEMA ops FROM PUBLIC, anon, authenticated, service_role",
                "REVOKE ALL ON ALL TABLES IN SCHEMA ops FROM PUBLIC, anon, authenticated, service_role",
            ],
        )

    def test_ddl_has_attempt_retries_and_the_unique_task_id(self):
        ddl = pending_statements(state(table_exists=False))[0]
        for fragment in (
            "task_id uuid not null",
            "attempt integer not null",
            "retries integer not null",
            "error_message text not null",
            "failed_at timestamptz not null default now()",
            "constraint uq_task_dead_letters_task_id unique (task_id)",
            "check (attempt = retries + 1)",
            "check (reason in ('retries_exhausted', 'non_retryable', 'time_limit'))",
        ):
            self.assertIn(fragment, ddl)

    def test_existing_ops_schema_from_job_runner_is_reused(self):
        statements = pending_statements(state(table_exists=False, index_exists=False, rls_enabled=False))
        self.assertNotIn(CREATE_SCHEMA, statements)
        self.assertTrue(any(s.startswith("REVOKE ALL ON ALL TABLES") for s in statements))

    def test_nothing_to_do(self):
        self.assertEqual(pending_statements(state()), [])

    def test_leftover_grants_are_revoked(self):
        self.assertEqual(len(pending_statements(state(granted=True))), 2)


class CliTests(unittest.TestCase):
    def run_cli(self, argv, url, migrate_result=None, migrate_error=None):
        target = target_from_url(url, "entorno")
        stdout, stderr = io.StringIO(), io.StringIO()
        fake = mock.Mock(side_effect=migrate_error, return_value=migrate_result or [])
        with mock.patch.object(migrate, "migrate", fake), mock.patch.object(migrate, "build_engine"), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = migrate.run(argv, target=target)
        return code, stdout.getvalue(), stderr.getvalue(), fake

    def test_a_non_local_database_is_refused_without_allow_demo(self):
        code, out, err, fake = self.run_cli([], DEMO)
        self.assertEqual(code, 1)
        self.assertIn("--allow-demo", err)
        fake.assert_not_called()
        for secret in ("demo-Pass-2", "postgres:"):
            self.assertNotIn(secret, out + err)

    def test_allow_demo_lets_it_through(self):
        code, _, _, fake = self.run_cli(["--allow-demo", "--dry-run"], DEMO)
        self.assertEqual(code, 0)
        self.assertTrue(fake.call_args.kwargs["dry_run"])

    def test_dry_run_prints_without_applying(self):
        code, out, _, fake = self.run_cli(["--dry-run"], LOCAL, migrate_result=[CREATE_SCHEMA])
        self.assertEqual(code, 0)
        self.assertIn("SQL pendiente (no se ha aplicado):", out)
        self.assertIn(f"  {CREATE_SCHEMA};", out)
        self.assertTrue(fake.call_args.kwargs["dry_run"])

    def test_nothing_to_migrate(self):
        _, out, _, _ = self.run_cli([], LOCAL)
        self.assertIn("Nada que migrar", out)

    def test_database_failure_exits_2_with_the_class_only(self):
        code, out, err, _ = self.run_cli([], LOCAL, migrate_error=OperationalError("SELECT", {}, Exception("conn to 127.0.0.1 failed")))
        self.assertEqual(code, 2)
        self.assertIn("(OperationalError)", err)
        self.assertNotIn("local-Pass-1", out + err)

    def test_still_granted_exits_1(self):
        code, _, err, _ = self.run_cli([], LOCAL, migrate_error=migrate.StillGrantedError())
        self.assertEqual(code, 1)
        self.assertIn("Se ha deshecho todo", err)

    def test_bad_arguments_exit_1(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(migrate.run(["--nope"], target=target_from_url(LOCAL, "entorno")), 1)


if __name__ == "__main__":
    unittest.main()
