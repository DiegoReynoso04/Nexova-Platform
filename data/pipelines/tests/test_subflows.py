"""Los subflows de la Parte 3: nombres, entradas y salidas explícitas, ejecución por separado y fallos.

Con Prefect de verdad (`prefect_test_harness`) y un repositorio en memoria: ningún
test toca una base de datos. «Ejecutable por separado» = se llama solo desde
Python con sus entradas, sin pasar por el flow principal ni por `main()`.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from prefect.testing.utilities import prefect_test_harness
from sqlalchemy.exc import IntegrityError

import pipeline
import weekly_performance as process
from tests.support import InMemoryRepository, closed_week, fake_event
from weekly_performance import ExtractionResult, LoadOutcome, QualityCounts

_harness = None


def setUpModule():
    global _harness
    _harness = prefect_test_harness(server_startup_timeout=60)
    _harness.__enter__()


def tearDownModule():
    _harness.__exit__(None, None, None)


class SubflowTestCase(unittest.TestCase):
    def setUp(self):
        self.week = closed_week()
        self.events = [
            fake_event("inbound_order_created", week=self.week, quantity="4", unit_cost="12.50", order_id="1"),
            fake_event("outbound_order_created", week=self.week, order_id="2"),
            fake_event("outbound_order_created", week=self.week, office="miami", order_id="3"),
            fake_event("stock_threshold_triggered", week=self.week, office="miami", order_id="3"),
        ]
        self.repo = InMemoryRepository(events=list(self.events))
        pipeline.set_repository(self.repo)
        self.addCleanup(pipeline.set_repository, None)


class DeclarationTests(SubflowTestCase):
    SUBFLOWS = (
        (pipeline.extract_telemetry_events, "extract_telemetry_events"),
        (pipeline.transform_weekly_kpis, "transform_weekly_kpis"),
        (pipeline.load_weekly_office_program_performance, "load_weekly_office_program_performance"),
        (pipeline.snapshot_weekly_performance, "snapshot_weekly_performance"),
    )

    def test_the_main_flow_has_four_named_subflows(self):
        for subflow, name in self.SUBFLOWS:
            with self.subTest(subflow=name):
                self.assertEqual(subflow.name, name)

    def test_subflows_do_not_retry_themselves(self):
        # Los reintentos son de las tasks: con los del subflow se multiplicarían (3 × 3 intentos).
        for subflow, name in self.SUBFLOWS:
            with self.subTest(subflow=name):
                self.assertEqual(subflow.retries, 0)

    def test_kpi_tasks_are_named_after_the_briefing_columns(self):
        self.assertEqual(
            [task.name for task in (pipeline.compute_total_material_cost, pipeline.compute_kits_delivered_count,
                                    pipeline.compute_shortage_events_count,
                                    pipeline.compute_cost_variance_events_count)],
            ["compute_total_material_cost", "compute_kits_delivered_count", "compute_shortage_events_count",
             "compute_cost_variance_events_count"],
        )


class StandaloneTests(SubflowTestCase):
    def test_transform_runs_alone_without_a_database(self):
        pipeline.set_repository(None)
        with mock.patch.object(pipeline, "get_repository", side_effect=AssertionError("no database in transform")):
            result = pipeline.transform_weekly_kpis(
                pipeline.EventBatch(self.events), QualityCounts(), self.week, self.week)
        expected = process.transform(self.events, QualityCounts(), self.week, self.week)
        self.assertEqual(result.rows, expected.rows)
        self.assertEqual(result.stats, expected.stats)
        self.assertEqual(result.quality, expected.quality)
        self.assertEqual(len(result.rows), 2)

    def test_snapshot_runs_alone_without_a_database(self):
        pipeline.set_repository(None)
        result = process.transform(self.events, QualityCounts(), self.week, self.week)
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(pipeline, "get_repository", side_effect=AssertionError("no database in snapshot")):
            name = pipeline.snapshot_weekly_performance(
                directory, pipeline.uuid4(), self.week, self.week, result, LoadOutcome(2, 0)
            )
            self.assertTrue((Path(directory) / name).is_file())

    def test_extract_runs_alone_with_a_repository(self):
        extraction = pipeline.extract_telemetry_events(self.week, self.week)
        self.assertIsInstance(extraction, ExtractionResult)
        self.assertEqual({event.event_id for event in extraction.events}, {event.event_id for event in self.events})

    def test_load_runs_alone_with_an_existing_run(self):
        run_id = pipeline.uuid4()
        self.repo.start_run(run_id, "manual", None, None, self.week, self.week)
        result = process.transform(self.events, QualityCounts(), self.week, self.week)
        outcome = pipeline.load_weekly_office_program_performance(result, self.week, self.week, run_id)
        self.assertEqual(outcome, LoadOutcome(rows_upserted=2, rows_deleted=0))
        self.assertEqual(len(self.repo.table), 2)


class PhaseOnFailureTests(SubflowTestCase):
    """Un fallo dentro de un subflow deja en `pipeline_runs` la fase en la que se llamó, y la clase del error."""

    def run_flow(self):
        with mock.patch.object(pipeline, "EVAL_DIR", Path(tempfile.mkdtemp(prefix="nexova-eval-"))):
            return pipeline.weekly_office_program_performance(week_start=self.week, return_state=True)

    def only_run(self):
        (run,) = self.repo.runs.values()
        return run

    def test_extract_failure_leaves_phase_extract(self):
        error = IntegrityError("SELECT", {}, Exception("rejected (fictitious)"))  # permanente: sin reintentos
        with mock.patch.object(self.repo, "extract_business_events", side_effect=error):
            self.assertTrue(self.run_flow().is_failed())
        run = self.only_run()
        self.assertEqual((run["status"], run["phase"], run["error_class"]), ("failed", "extract", "IntegrityError"))

    def test_transform_failure_leaves_phase_transform(self):
        with mock.patch.object(pipeline.process, "assemble_rows",
                               side_effect=process.DataQualityError("a report cell has more than one currency")):
            self.assertTrue(self.run_flow().is_failed())
        run = self.only_run()
        self.assertEqual((run["status"], run["phase"], run["error_class"]), ("failed", "transform", "DataQualityError"))
        self.assertEqual(self.repo.table, {})

    def test_load_failure_leaves_phase_load_without_a_wrapper_class(self):
        error = IntegrityError("INSERT", {}, Exception("check violation (fictitious)"))
        self.repo.load_failures = [error]
        self.assertTrue(self.run_flow().is_failed())
        run = self.only_run()
        self.assertEqual((run["status"], run["phase"], run["error_class"]), ("failed", "load", "IntegrityError"))


if __name__ == "__main__":
    unittest.main()
