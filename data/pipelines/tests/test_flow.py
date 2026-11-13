"""El flow con Prefect de verdad (`prefect_test_harness`) y un repositorio en memoria.

Cubre los cuatro puntos del enunciado: paso opcional con `return_state=True`
que falla y el flow sigue; caché de las tasks `compute_*` (segunda corrida en
menos de 1 h que no recalcula); retries declarados y efectivos; segunda corrida
sobre las mismas semanas sin duplicados. Además, el fallo manejado de la carga.
"""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock
from uuid import uuid4

from prefect.testing.utilities import prefect_test_harness
from sqlalchemy.exc import IntegrityError, OperationalError

import pipeline
from tests.support import InMemoryRepository, closed_week, fake_event

_harness = None


def setUpModule():
    global _harness
    _harness = prefect_test_harness(server_startup_timeout=60)
    _harness.__enter__()


def tearDownModule():
    _harness.__exit__(None, None, None)


def _operational_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection reset (fictitious)"))


class FlowTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()
        pipeline.set_repository(self.repo)
        self.addCleanup(pipeline.set_repository, None)
        self.eval_dir = Path(tempfile.mkdtemp(prefix="nexova-eval-"))
        patcher = mock.patch.object(pipeline, "EVAL_DIR", self.eval_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Sin esperas en los reintentos de la carga (la declaración real se prueba aparte).
        patcher = mock.patch.object(pipeline, "load_weekly_rows",
                                    pipeline.load_weekly_rows.with_options(retry_delay_seconds=0))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.week = closed_week()
        self.repo.events = [
            fake_event("inbound_order_created", week=self.week, quantity="4", unit_cost="12.50", order_id="1"),
            fake_event("outbound_order_created", week=self.week, order_id="2"),
            fake_event("outbound_order_created", week=self.week, office="miami", order_id="3"),
            fake_event("stock_threshold_triggered", week=self.week, office="miami", order_id="3"),
        ]

    def run_flow(self, **parameters):
        return pipeline.weekly_office_program_performance(week_start=self.week, return_state=True, **parameters)

    def run_rows(self):
        return [run for run in self.repo.runs.values()]


class SuccessfulRunTests(FlowTestCase):
    def test_extract_transform_load_and_log(self):
        state = self.run_flow()
        self.assertTrue(state.is_completed(), state)
        self.assertEqual(sorted(key[0] for key in self.repo.table), ["miami", "valencia"])
        valencia = self.repo.table[("valencia", "_unassigned", self.week)]["row"]
        self.assertEqual(str(valencia.total_material_cost), "50.00")
        (run,) = self.run_rows()
        self.assertEqual((run["status"], run["phase"], run["rows_upserted"], run["source_rows_read"]),
                         ("completed", "done", 2, 4))
        self.assertEqual(run["quality"]["optional_steps"], {"eval_snapshot": "completed"})
        self.assertEqual(len(list(self.eval_dir.glob("*.json"))), 1)

    def test_second_run_on_the_same_weeks_does_not_duplicate(self):
        self.assertTrue(self.run_flow().is_completed())
        first = {key: value["row"] for key, value in self.repo.table.items()}
        self.assertTrue(self.run_flow().is_completed())
        self.assertEqual({key: value["row"] for key, value in self.repo.table.items()}, first)
        self.assertEqual(len(self.repo.table), 2)
        runs = self.run_rows()
        self.assertEqual([run["status"] for run in runs], ["completed", "completed"])
        latest_run_id = list(self.repo.runs)[-1]
        self.assertTrue(all(value["run_id"] == latest_run_id for value in self.repo.table.values()))

    def test_recalculation_deletes_cells_that_no_longer_exist(self):
        self.assertTrue(self.run_flow().is_completed())
        self.repo.events = [event for event in self.repo.events if event.office == "valencia"]
        self.assertTrue(self.run_flow().is_completed())
        self.assertEqual(list(self.repo.table), [("valencia", "_unassigned", self.week)])
        self.assertEqual(self.run_rows()[-1]["rows_deleted"], 1)


class CacheTests(FlowTestCase):
    def test_second_run_within_the_hour_does_not_recompute(self):
        # Órdenes con ids únicos en cada ejecución: la clave de un KPI depende de
        # sus eventos (no de su `event_id`), así que ids fijos podrían venir de la
        # caché en disco de una ejecución anterior de la misma hora.
        base = uuid4().int % 10**9 * 10
        self.repo.events = [
            fake_event("inbound_order_created", week=self.week, quantity="4", unit_cost="12.50", order_id=str(base + 1)),
            fake_event("outbound_order_created", week=self.week, order_id=str(base + 2)),
            fake_event("outbound_order_created", week=self.week, office="miami", order_id=str(base + 3)),
            fake_event("stock_threshold_triggered", week=self.week, office="miami", order_id=str(base + 3)),
        ]
        with mock.patch.object(pipeline.process, "kits_delivered_by_cell",
                               wraps=pipeline.process.kits_delivered_by_cell) as kits,                 mock.patch.object(pipeline.process, "total_material_cost_by_cell",
                                  wraps=pipeline.process.total_material_cost_by_cell) as cost:
            self.assertTrue(self.run_flow().is_completed())
            self.assertTrue(self.run_flow().is_completed())
            self.assertEqual((kits.call_count, cost.call_count), (1, 1))  # la segunda vino de la caché
            # Una salida más cambia la clave de los kits (se recalcula) y no la del costo (sigue en caché).
            self.repo.events.append(fake_event("outbound_order_created", week=self.week, order_id=str(base + 9)))
            self.assertTrue(self.run_flow().is_completed())
            self.assertEqual((kits.call_count, cost.call_count), (2, 1))
        self.assertEqual(self.repo.table[("valencia", "_unassigned", self.week)]["row"].kits_delivered_count, 2)

    def test_cache_is_declared_for_one_hour_on_the_four_kpi_tasks_only(self):
        kpi_tasks = (pipeline.compute_total_material_cost, pipeline.compute_kits_delivered_count,
                     pipeline.compute_shortage_events_count, pipeline.compute_cost_variance_events_count)
        for task in kpi_tasks:
            with self.subTest(task=task.name):
                self.assertEqual(task.cache_expiration, timedelta(hours=1))
                self.assertIsNotNone(task.cache_key_fn)
                self.assertTrue(task.persist_result)
        # Las que reciben o devuelven identificadores, la E/S y la carga no se cachean (D6).
        for task in (pipeline.start_run, pipeline.extract_business_events, pipeline.extract_quality_counts,
                     pipeline.mark_phase, pipeline.type_and_validate_events, pipeline.collapse_duplicate_orders,
                     pipeline.assemble_weekly_rows, pipeline.load_weekly_rows, pipeline.finish_run,
                     pipeline.write_eval_snapshot):
            with self.subTest(task=task.name):
                self.assertIsNone(task.cache_key_fn)
                self.assertIsNone(task.cache_expiration)
                self.assertFalse(task.persist_result)

    def test_cache_key_depends_on_every_event_of_the_kpi(self):
        kept = pipeline.process.type_and_validate(self.repo.events, self.week, self.week).items
        kits = pipeline.BusinessEvent.OUTBOUND_ORDER_CREATED
        key = pipeline.kpi_cache_key("kits_delivered_count", kits, {"kept": kept})
        self.assertEqual(key, pipeline.kpi_cache_key("kits_delivered_count", kits, {"kept": kept[::-1]}))
        # Otro KPI, otra clave.
        self.assertNotEqual(key, pipeline.kpi_cache_key("shortage_events_count", kits, {"kept": kept}))
        # Una salida de más cambia la clave de los kits...
        extra = pipeline.process.type_and_validate(
            [fake_event("outbound_order_created", week=self.week, order_id="99")], self.week, self.week).items
        self.assertNotEqual(key, pipeline.kpi_cache_key("kits_delivered_count", kits, {"kept": (*kept, *extra)}))
        # ...y una entrada de más no (no es un evento de ese KPI).
        inbound = pipeline.process.type_and_validate(
            [fake_event("inbound_order_created", week=self.week, unit_cost="1", order_id="98")],
            self.week, self.week).items
        self.assertEqual(key, pipeline.kpi_cache_key("kits_delivered_count", kits, {"kept": (*kept, *inbound)}))
        # Una semana distinta cambia la clave.
        other_week = pipeline.process.type_and_validate(
            [fake_event("outbound_order_created", week=closed_week(1), order_id="2")],
            closed_week(1), closed_week(1)).items
        self.assertNotEqual(key, pipeline.kpi_cache_key("kits_delivered_count", kits, {"kept": other_week}))


def _fields(item):
    return {name: getattr(item, name) for name in item.__slots__}


class OptionalStepTests(FlowTestCase):
    def test_failed_snapshot_does_not_stop_the_flow(self):
        # Forzado: el directorio de salida es un fichero, así que mkdir/escritura fallan.
        blocker = self.eval_dir / "not-a-directory"
        blocker.write_text("x", encoding="utf-8")
        with mock.patch.object(pipeline, "EVAL_DIR", blocker):
            state = self.run_flow()
        self.assertTrue(state.is_completed(), state)
        (run,) = self.run_rows()
        self.assertEqual((run["status"], run["phase"]), ("completed", "done"))
        self.assertEqual(run["quality"]["optional_steps"]["eval_snapshot"], "failed")
        self.assertIn(run["quality"]["optional_steps"]["error_class"], {"FileExistsError", "NotADirectoryError", "OSError"})
        self.assertEqual(len(self.repo.table), 2)  # extract → transform → load siguió


class HandledFailureTests(FlowTestCase):
    def test_load_failure_is_handled_with_return_state(self):
        self.repo.load_failures = [_operational_error() for _ in range(3)]
        state = self.run_flow()
        self.assertTrue(state.is_failed())
        self.assertEqual(self.repo.load_attempts, 3)  # 1 + 2 reintentos
        (run,) = self.run_rows()
        self.assertEqual((run["status"], run["phase"], run["error_class"]), ("failed", "load", "OperationalError"))
        self.assertEqual(self.repo.table, {})  # la transacción no dejó nada
        self.assertEqual(list(self.eval_dir.glob("*.json")), [])  # el opcional no corre tras un fallo

    def test_second_run_after_a_failed_load_completes(self):
        self.repo.load_failures = [_operational_error() for _ in range(3)]
        self.assertTrue(self.run_flow().is_failed())
        self.assertTrue(self.run_flow().is_completed())
        self.assertEqual([run["status"] for run in self.run_rows()], ["failed", "completed"])
        self.assertEqual(len(self.repo.table), 2)

    def test_week_outside_retention_fails_before_reading(self):
        state = pipeline.weekly_office_program_performance(week_start=closed_week(13), return_state=True)
        self.assertTrue(state.is_failed())
        (run,) = self.run_rows()
        self.assertEqual((run["status"], run["phase"], run["error_class"]), ("failed", "extract", "WeekSelectionError"))

    def test_another_run_in_progress_is_refused(self):
        self.repo.runs[pipeline.uuid4()] = {"status": "running"}
        state = self.run_flow()
        self.assertTrue(state.is_failed())
        self.assertEqual(len(self.repo.runs), 1)


class RetryTests(FlowTestCase):
    def test_retries_are_declared_with_their_delays(self):
        for task in (pipeline.start_run, pipeline.extract_business_events, pipeline.extract_quality_counts,
                     pipeline.mark_phase, pipeline.finish_run):
            with self.subTest(task=task.name):
                self.assertEqual((task.retries, task.retry_delay_seconds), (2, 10))
        # La task tal como la declara pipeline.py, no la copia sin esperas de setUp.
        self.assertEqual((_ORIGINAL_LOAD.retries, _ORIGINAL_LOAD.retry_delay_seconds), (2, 30))
        for task in (pipeline.resolve_weeks, pipeline.type_and_validate_events, pipeline.collapse_duplicate_orders,
                     pipeline.compute_total_material_cost, pipeline.compute_kits_delivered_count,
                     pipeline.compute_shortage_events_count, pipeline.compute_cost_variance_events_count,
                     pipeline.assemble_weekly_rows, pipeline.write_eval_snapshot):
            with self.subTest(task=task.name):
                self.assertEqual(task.retries, 0)

    def test_transient_load_error_is_retried(self):
        self.repo.load_failures = [_operational_error()]
        self.assertTrue(self.run_flow().is_completed())
        self.assertEqual(self.repo.load_attempts, 2)

    def test_permanent_error_is_not_retried(self):
        self.repo.load_failures = [IntegrityError("INSERT", {}, Exception("check violation (fictitious)"))]
        self.assertTrue(self.run_flow().is_failed())
        self.assertEqual(self.repo.load_attempts, 1)
        self.assertEqual(self.run_rows()[0]["error_class"], "IntegrityError")


# La task de carga tal como la declara pipeline.py (setUp la sustituye por una copia sin esperas).
_ORIGINAL_LOAD = pipeline.load_weekly_rows


class BackfillTests(FlowTestCase):
    def test_backfill_runs_one_subflow_per_week(self):
        previous = closed_week(1)
        self.repo.events.append(fake_event("outbound_order_created", week=previous, order_id="7"))
        state = pipeline.backfill_weekly_office_program_performance(previous, self.week, return_state=True)
        self.assertTrue(state.is_completed(), state)
        runs = self.run_rows()
        self.assertEqual([(run["trigger"], run["week_from"]) for run in runs],
                         [("backfill", previous), ("backfill", self.week)])
        self.assertIn(("valencia", "_unassigned", previous), self.repo.table)


if __name__ == "__main__":
    unittest.main()
