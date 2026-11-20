"""Integración contra un PostgreSQL **local** (`TASK_QUEUE_TEST_DATABASE_URL`).

Se niega con un host que no es local o una base que no termina en `_test`: **borra y
recrea el esquema `ops`** de esa base. Sin la variable, los tests se omiten con su
motivo. Cubre la migración (dry-run, idempotencia, RLS, privilegios), el orden
indiferente con `job_runner.migrate`, la tabla frente a `build_table` y el registro
de la DLQ, también con la tabla sin migrar (línea de log).
"""

import os
import unittest

from job_runner import migrate as job_runner_migrate
from job_runner.config import build_engine, target_from_url
from job_runner.states import QUALIFIED_TABLE as JOB_RUNS
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from task_queue import migrate
from task_queue.dead_letters import DEAD_LETTERS, QUALIFIED_TABLE, DeadLetterRepository, record_dead_letter

from .support import letter

URL = os.environ.get("TASK_QUEUE_TEST_DATABASE_URL", "").strip()
SKIP = "TASK_QUEUE_TEST_DATABASE_URL is not set (local PostgreSQL only)"
ENGINE = None


def check_test_database(url: str):
    target = target_from_url(url, "entorno")
    database = target.url.rsplit("/", 1)[-1].split("?")[0]
    if not target.is_local or not database.endswith("_test"):
        raise RuntimeError("TASK_QUEUE_TEST_DATABASE_URL must point to a local database whose name ends in _test")
    return target


def setUpModule():
    global ENGINE
    if URL:
        ENGINE = build_engine(check_test_database(URL).url)


def tearDownModule():
    if ENGINE is not None:
        ENGINE.dispose()


def drop_ops():
    with ENGINE.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS ops CASCADE"))


def scalar(sql, **params):
    with ENGINE.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


@unittest.skipUnless(URL, SKIP)
class MigrationTests(unittest.TestCase):
    def setUp(self):
        drop_ops()

    def test_dry_run_applies_nothing(self):
        statements = migrate.migrate(ENGINE, dry_run=True)
        self.assertEqual(statements[0], "CREATE SCHEMA IF NOT EXISTS ops")
        self.assertFalse(scalar("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ops')"))

    def test_apply_then_nothing_to_migrate(self):
        self.assertGreater(len(migrate.migrate(ENGINE, dry_run=False)), 0)
        self.assertEqual(migrate.migrate(ENGINE, dry_run=False), [])
        self.assertTrue(scalar("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:t)", t=QUALIFIED_TABLE))
        self.assertFalse(scalar("SELECT has_schema_privilege('public', 'ops', 'USAGE')"))
        self.assertFalse(scalar("SELECT has_table_privilege('public', :t, 'SELECT')", t=QUALIFIED_TABLE))

    def test_columns_match_the_table_the_worker_writes(self):
        migrate.migrate(ENGINE, dry_run=False)
        columns = {column["name"] for column in inspect(ENGINE).get_columns("task_dead_letters", schema="ops")}
        self.assertEqual(columns, {column.name for column in DEAD_LETTERS.columns})

    def test_checks_and_unique_task_id(self):
        migrate.migrate(ENGINE, dry_run=False)
        repo = DeadLetterRepository(ENGINE)
        self.assertTrue(repo.record(letter()))
        self.assertFalse(repo.record(letter()))
        [row] = repo.list()
        self.assertEqual((row["attempt"], row["retries"], row["max_retries"], row["reason"]), (4, 3, 3, "retries_exhausted"))
        self.assertEqual(row["task_kwargs"]["start"], "2026-11-13T00:00:00.000Z")
        self.assertIsNotNone(row["failed_at"].tzinfo)
        with self.assertRaises(IntegrityError):
            with ENGINE.begin() as connection:
                connection.execute(
                    text(
                        f"INSERT INTO {QUALIFIED_TABLE} (task_id, task_name, attempt, retries, max_retries, reason, error_class, error_message) "
                        "VALUES (gen_random_uuid(), 'x', 2, 3, 3, 'retries_exhausted', 'E', 'm')"
                    )
                )

    def run_in_order(self, first, second):
        first(ENGINE, dry_run=False)
        second(ENGINE, dry_run=False)
        # Las dos tablas, con RLS, sin privilegios y sin nada pendiente en ninguna de las dos.
        for table in (QUALIFIED_TABLE, JOB_RUNS):
            self.assertTrue(scalar("SELECT to_regclass(:t) IS NOT NULL", t=table))
            self.assertTrue(scalar("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:t)", t=table))
            self.assertFalse(scalar("SELECT has_table_privilege('public', :t, 'SELECT')", t=table))
        self.assertEqual(migrate.migrate(ENGINE, dry_run=False), [])
        self.assertEqual(job_runner_migrate.migrate(ENGINE, dry_run=False), [])

    def test_task_queue_first_then_job_runner(self):
        self.run_in_order(migrate.migrate, job_runner_migrate.migrate)

    def test_job_runner_first_then_task_queue(self):
        self.run_in_order(job_runner_migrate.migrate, migrate.migrate)


@unittest.skipUnless(URL, SKIP)
class UnmigratedTableTests(unittest.TestCase):
    def test_missing_table_goes_to_the_log(self):
        drop_ops()
        with self.assertLogs("task_queue", "ERROR") as logs:
            self.assertFalse(record_dead_letter(letter(), repository=DeadLetterRepository(ENGINE), sleep=lambda _s: None))
        self.assertIn("status=dead_letter_not_stored", logs.output[0])
        self.assertIn("cause=ProgrammingError", logs.output[0])
        self.assertIn("retries=3", logs.output[0])


if __name__ == "__main__":
    unittest.main()
