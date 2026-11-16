"""Integración contra un PostgreSQL **local** (`JOB_RUNNER_TEST_DATABASE_URL`).

Se niega con un host que no es local o una base que no termina en `_test` (borra y
recrea el esquema `ops`). Sin la variable, los tests se omiten con su motivo. Los
mismos casos que SQLite (`cases.py`) más lo propio de PostgreSQL: la migración,
`CHECK`, RLS, privilegios y las carreras reales entre conexiones.
"""

import os
import threading
import time
import unittest
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from job_runner import JobRunRepository, JobStatus, Outcome, run_job
from job_runner.config import build_engine, target_from_url
from job_runner.migrate import index_statements, migrate, revoke_statements
from job_runner.states import ONE_COMPLETED_INDEX, ONE_PROCESSING_INDEX, QUALIFIED_TABLE, TARGET_INDEX

from .cases import RepositoryCases, RunnerCases, statuses
from .support import DAY, JOB, T0, FakeClock, insert_row

URL = os.environ.get("JOB_RUNNER_TEST_DATABASE_URL", "").strip()
SKIP = "JOB_RUNNER_TEST_DATABASE_URL is not set (local PostgreSQL only)"
ENGINE = None


def setUpModule():
    global ENGINE
    if not URL:
        return
    target = target_from_url(URL, "entorno")
    database = target.url.rsplit("/", 1)[-1].split("?")[0]
    if not target.is_local or not database.endswith("_test"):
        raise RuntimeError("JOB_RUNNER_TEST_DATABASE_URL must point to a local database whose name ends in _test")
    ENGINE = build_engine(target.url)


def tearDownModule():
    if ENGINE is not None:
        ENGINE.dispose()


def reset_schema():
    with ENGINE.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS ops CASCADE"))
    migrate(ENGINE, dry_run=False)


@unittest.skipUnless(URL, SKIP)
class PostgresBase(unittest.TestCase):
    def setUp(self):
        reset_schema()
        self.engine = ENGINE
        self.table = QUALIFIED_TABLE
        self.repo = JobRunRepository(self.engine, self.table)
        self.clock = FakeClock()


class PostgresRepositoryTests(RepositoryCases, PostgresBase):
    pass


class PostgresRunnerTests(RunnerCases, PostgresBase):
    def setUp(self):
        super().setUp()
        self.setUp_logging()


class PostgresMigrationTests(PostgresBase):
    def columns(self):
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'ops' AND table_name = 'job_runs' ORDER BY ordinal_position"
                )
            ).all()
        return {name: (kind, nullable) for name, kind, nullable in rows}

    def test_structure_matches_the_ticket(self):
        self.assertEqual(
            self.columns(),
            {
                "id": ("uuid", "NO"),
                "job_name": ("text", "NO"),
                "target_date": ("date", "NO"),
                "status": ("text", "NO"),
                "started_at": ("timestamp with time zone", "YES"),
                "finished_at": ("timestamp with time zone", "YES"),
                "error_message": ("text", "YES"),
                "created_at": ("timestamp with time zone", "NO"),
            },
        )

    def test_indexes_exist_and_the_two_unique_ones_are_partial(self):
        with self.engine.connect() as connection:
            rows = dict(connection.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'ops'")).all())
        self.assertIn(TARGET_INDEX, rows)
        self.assertIn("(job_name, target_date)", rows[TARGET_INDEX])
        self.assertIn("UNIQUE", rows[ONE_PROCESSING_INDEX])
        self.assertIn("(status = 'processing'", rows[ONE_PROCESSING_INDEX])
        self.assertIn("UNIQUE", rows[ONE_COMPLETED_INDEX])
        self.assertIn("(status = 'completed'", rows[ONE_COMPLETED_INDEX])

    def test_the_migration_is_idempotent_and_dry_run_writes_nothing(self):
        self.assertEqual(migrate(self.engine, dry_run=False), [])
        self.assertEqual(migrate(self.engine, dry_run=True), [])
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA ops CASCADE"))
        planned = migrate(self.engine, dry_run=True)
        self.assertGreater(len(planned), 5)
        with self.engine.connect() as connection:
            self.assertFalse(connection.execute(text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ops')")).scalar_one())
        migrate(self.engine, dry_run=False)
        self.assertEqual(migrate(self.engine, dry_run=False), [])

    def test_row_level_security_is_on_and_nobody_but_the_owner_has_access(self):
        with self.engine.connect() as connection:
            self.assertTrue(connection.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('ops.job_runs')")).scalar_one())
            self.assertEqual(connection.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname = 'ops'")).scalar_one(), 0)
            public_acls = connection.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a "
                    "WHERE n.nspname = 'ops' AND a.grantee = 0"
                )
            ).scalar_one()
            schema_public = connection.execute(
                text("SELECT count(*) FROM pg_namespace n, aclexplode(n.nspacl) a WHERE n.nspname = 'ops' AND a.grantee = 0")
            ).scalar_one()
            self.assertEqual((public_acls, schema_public), (0, 0))

    def test_public_and_the_supabase_roles_have_no_privileges(self):
        """`PUBLIC` siempre; `anon`, `authenticated` y `service_role` si la base los tiene (Supabase)."""
        with self.engine.connect() as connection:
            present = connection.execute(
                text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated', 'service_role')")
            ).scalars().all()
            for role in ("public", *present):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    self.assertFalse(
                        connection.execute(
                            text("SELECT has_table_privilege(:r, 'ops.job_runs', :p)"), {"r": role, "p": privilege}
                        ).scalar_one(),
                        (role, privilege),
                    )
                for privilege in ("USAGE", "CREATE"):
                    self.assertFalse(
                        connection.execute(text("SELECT has_schema_privilege(:r, 'ops', :p)"), {"r": role, "p": privilege}).scalar_one(),
                        (role, privilege),
                    )

    def test_revoke_statements_are_part_of_a_fresh_migration(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA ops CASCADE"))
        planned = migrate(self.engine, dry_run=True)
        for statement in revoke_statements(()):
            self.assertTrue(any(item.startswith(statement) for item in planned), statement)

    def test_the_index_statements_for_sqlite_are_the_same_as_the_real_ones(self):
        for statement in index_statements().values():
            self.assertIn("ops.job_runs", statement)

    def test_check_constraints_reject_inconsistent_rows(self):
        bad_rows = {
            "unknown status": "INSERT INTO ops.job_runs (job_name, target_date, status) VALUES ('j', '2026-11-15', 'done')",
            "completed without finished_at": "INSERT INTO ops.job_runs (job_name, target_date, status) VALUES ('j', '2026-11-15', 'completed')",
            "message on a processing row": (
                "INSERT INTO ops.job_runs (job_name, target_date, status, started_at, error_message) "
                "VALUES ('j', '2026-11-15', 'processing', now(), 'x')"
            ),
            "message too long": (
                "INSERT INTO ops.job_runs (job_name, target_date, status, finished_at, error_message) "
                "VALUES ('j', '2026-11-15', 'failed', now(), repeat('x', 1001))"
            ),
        }
        for label, sql in bad_rows.items():
            with self.subTest(label), self.assertRaises(DBAPIError):
                with self.engine.begin() as connection:
                    connection.execute(text(sql))

    def test_default_id_and_created_at_come_from_the_database(self):
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO ops.job_runs (job_name, target_date, status) VALUES ('j', '2026-11-15', 'pending')"))
            row = connection.execute(text("SELECT id IS NOT NULL, created_at IS NOT NULL FROM ops.job_runs")).one()
        self.assertEqual(tuple(row), (True, True))


class PostgresConcurrencyTests(PostgresBase):
    def test_two_simultaneous_claims_exactly_one_wins_the_lock(self):
        """La carrera de verdad: dos conexiones, dos filas `pending`, un solo `processing`."""
        for round_number in range(25):
            with self.subTest(round=round_number):
                with self.engine.begin() as connection:
                    connection.execute(text("TRUNCATE ops.job_runs"))
                first = self.repo.create_job_run(JOB, DAY, T0)
                second = self.repo.create_job_run(JOB, DAY, T0)
                barrier = threading.Barrier(2)
                results: dict[str, bool] = {}

                def claim(name, run_id):
                    barrier.wait()
                    results[name] = JobRunRepository(self.engine, self.table).claim(run_id, T0)

                threads = [threading.Thread(target=claim, args=(n, r.id)) for n, r in (("a", first), ("b", second))]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=20)
                self.assertEqual(sorted(results.values()), [False, True])
                self.assertEqual(statuses(self.repo).count(JobStatus.PROCESSING), 1)
                self.assertEqual(statuses(self.repo).count(JobStatus.PENDING), 1)

    def test_two_simultaneous_instances_one_completes_and_the_other_aborts(self):
        """`run_job` completo desde dos hilos con conexiones propias: el trabajo se ejecuta una sola vez."""
        barrier = threading.Barrier(2)
        calls: list[str] = []
        results: list = []

        def work():
            calls.append("work")
            time.sleep(0.8)

        def instance():
            repo = JobRunRepository(build_engine(target_from_url(URL, "entorno").url), self.table)
            barrier.wait()
            results.append(run_job(repo, JOB, DAY, work, sleep=lambda _: None))

        threads = [threading.Thread(target=instance) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        outcomes = sorted(result.outcome for result in results)
        self.assertEqual(outcomes, [Outcome.COMPLETED, Outcome.LOCKED])
        self.assertEqual(calls, ["work"])
        self.assertEqual(statuses(self.repo), [JobStatus.COMPLETED])

    def test_a_third_run_after_both_is_skipped(self):
        run_job(self.repo, JOB, DAY, lambda: None)
        result = run_job(self.repo, JOB, DAY, lambda: self.fail("must not run"))
        self.assertEqual(result.outcome, Outcome.SKIPPED)
        self.assertEqual(statuses(self.repo), [JobStatus.COMPLETED])

    def test_real_zombie_row_is_swept_and_the_new_run_completes(self):
        zombie = insert_row(self.engine, self.table, status=JobStatus.PROCESSING, started_at=T0 - timedelta(hours=2))
        result = run_job(self.repo, JOB, DAY, lambda: None, clock=self.clock)
        self.assertEqual(result.outcome, Outcome.COMPLETED)
        stored = self.repo.get_job_run(zombie)
        self.assertEqual(stored.status, JobStatus.FAILED)
        self.assertTrue(stored.error_message.startswith("Abandoned: processing"))

    def test_the_unique_indexes_reject_duplicates_at_the_database_level(self):
        insert_row(self.engine, self.table, status=JobStatus.PROCESSING)
        with self.assertRaises(IntegrityError):
            insert_row(self.engine, self.table, status=JobStatus.PROCESSING, target_date=date(2026, 11, 14))
        insert_row(self.engine, self.table, status=JobStatus.COMPLETED)
        with self.assertRaises(IntegrityError):
            insert_row(self.engine, self.table, status=JobStatus.COMPLETED)
