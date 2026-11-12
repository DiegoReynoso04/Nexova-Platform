"""La SQL real de `repository.py` y `migrate.py` contra un Postgres **local** (opcional).

Se salta si no está `PIPELINE_TEST_DATABASE_URL`, y se niega con un host que no
sea local: nunca contra la demo. Pensado para el Postgres efímero de la guía de
revisión, con un rol sin superusuario. Deja la base como la encontró: borra
solo las filas de `reporting` que crea (las suyas, por `run_id`).
"""

import os
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from business_performance import migrate
from business_performance.config import target_from_url
from business_performance.repository import PostgresRepository, RunInProgressError, build_engine
from sqlalchemy import text
from weekly_performance import WeeklyRow

from tests.support import closed_week

URL = os.environ.get("PIPELINE_TEST_DATABASE_URL", "").strip()


@unittest.skipUnless(URL, "PIPELINE_TEST_DATABASE_URL not set (local Postgres only)")
class PostgresRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = target_from_url(URL, "PIPELINE_TEST_DATABASE_URL")
        if not target.is_local:
            raise unittest.SkipTest("PIPELINE_TEST_DATABASE_URL must point to a local host")
        cls.engine = build_engine(target.url)
        migrate.migrate(cls.engine, dry_run=False)
        cls.repo = PostgresRepository(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.run_ids = []
        # Una semana sin datos del seed de la guía: el test no toca sus celdas.
        self.week = closed_week(10)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        with self.engine.begin() as connection:
            for run_id in self.run_ids:
                connection.execute(
                    text("DELETE FROM reporting.weekly_office_program_performance WHERE run_id = :id"), {"id": run_id})
                connection.execute(text("DELETE FROM reporting.pipeline_runs WHERE run_id = :id"), {"id": run_id})

    def _start(self):
        run_id = uuid4()
        self.run_ids.append(run_id)
        self.repo.start_run(run_id, "manual", None, None, self.week, self.week)
        return run_id

    def _finish(self, run_id):
        self.repo.finish_run(run_id, status="completed", phase="done", week_from=self.week, week_to=self.week)

    def test_schema_is_ready_and_migration_is_idempotent(self):
        self.assertTrue(self.repo.schema_ready())
        self.assertEqual(migrate.migrate(self.engine, dry_run=True), [])

    def test_start_run_is_idempotent_and_exclusive(self):
        run_id = self._start()
        self.repo.start_run(run_id, "manual", None, None, self.week, self.week)  # reintento: no choca
        with self.assertRaises(RunInProgressError):
            self._start()
        self.run_ids.pop()  # esa no llegó a insertarse
        self._finish(run_id)
        with self.assertRaises(RunInProgressError):  # una corrida cerrada no se reabre
            self.repo.start_run(run_id, "manual", None, None, self.week, self.week)

    def test_load_upserts_and_deletes_orphans_without_duplicates(self):
        rows = (
            WeeklyRow("valencia", "_unassigned", self.week, Decimal("10.25"), 1, 0, 0, "EUR"),
            WeeklyRow("miami", "_unassigned", self.week, Decimal("0"), 2, 1, 0, "USD"),
        )
        first = self._start()
        self.assertEqual(self.repo.load_weekly_rows(rows, self.week, self.week, first), (2, 0))
        self._finish(first)
        second = self._start()
        self.assertEqual(self.repo.load_weekly_rows(rows[:1], self.week, self.week, second), (1, 1))
        self._finish(second)
        with self.engine.connect() as connection:
            stored = connection.execute(
                text("SELECT office, total_material_cost, run_id FROM reporting.weekly_office_program_performance "
                     "WHERE week_start = :week"), {"week": self.week}).all()
        self.assertEqual([(office, cost, run) for office, cost, run in stored], [("valencia", Decimal("10.25"), second)])

    def test_check_constraints_reject_a_mixed_currency(self):
        run_id = self._start()
        bad = (WeeklyRow("miami", "_unassigned", self.week, Decimal("1"), 0, 0, 0, "EUR"),)
        from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

        with self.assertRaises(IntegrityError):
            self.repo.load_weekly_rows(bad, self.week, self.week, run_id)
        self._finish(run_id)

    def test_abandoned_runs_are_closed(self):
        stale = self._start()
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE reporting.pipeline_runs SET started_at = :at WHERE run_id = :id"),
                               {"at": datetime.now(UTC) - timedelta(minutes=31), "id": stale})
        fresh = self._start()
        with self.engine.connect() as connection:
            status, error_class = connection.execute(
                text("SELECT status, error_class FROM reporting.pipeline_runs WHERE run_id = :id"), {"id": stale}).one()
        self.assertEqual((status, error_class), ("failed", "Abandoned"))
        self._finish(fresh)


if __name__ == "__main__":
    unittest.main()
