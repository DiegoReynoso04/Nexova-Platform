"""Guardia de `EventBatch` (ver su docstring en `pipeline.py`).

El subflow `transform_weekly_kpis` recibe los eventos extraídos. Prefect guarda en
su servidor los parámetros de cada flow run, con un tope de 524 288 bytes
(`server.api.max_parameter_size`). `EventBatch` evita las dos cosas: que el tope
rompa la corrida con unos 2 000 eventos y que `event_id` y `order_id` queden
guardados en Prefect. Depende de un comportamiento interno de Prefect 3.9
(`prefect>=3.9.2,<3.10`): si cambia, estos tests tienen que fallar.

Con Prefect de verdad (`prefect_test_harness`); datos ficticios y sin base de datos.
"""

import asyncio
import json
import unittest

from prefect import get_client
from prefect.settings import get_current_settings
from prefect.testing.utilities import prefect_test_harness

import pipeline
from tests.support import closed_week, fake_event
from weekly_performance import QualityCounts

_harness = None


def setUpModule():
    global _harness
    _harness = prefect_test_harness(server_startup_timeout=60)
    _harness.__enter__()


def tearDownModule():
    _harness.__exit__(None, None, None)


async def _stored_parameters() -> list[dict]:
    """Los parámetros que el servidor de Prefect guardó para los flow runs del subflow de transformación."""
    async with get_client() as client:
        stored = []
        for run in await client.read_flow_runs():
            if (await client.read_flow(run.flow_id)).name == pipeline.transform_weekly_kpis.name:
                stored.append(run.parameters)
        return stored


def _events(count: int, week) -> list:
    kinds = ("inbound_order_created", "outbound_order_created", "stock_threshold_triggered", "kit_cost_variance_detected")
    events = []
    for index in range(count):
        kind = kinds[index % 4]
        events.append(fake_event(kind, week=week, office="valencia" if index % 2 == 0 else "miami",
                                 quantity="3", unit_cost="12.50" if kind == "inbound_order_created" else None,
                                 order_id=str(index + 1)))
    return events


class EventBatchGuardTests(unittest.TestCase):
    def setUp(self):
        self.week = closed_week()

    def test_prefect_still_has_the_limit_that_event_batch_avoids(self):
        # Si Prefect subiera o quitara el tope, el motivo de `EventBatch` cambia: revisar el docstring.
        self.assertEqual(get_current_settings().server.api.max_parameter_size, 524_288)

    def test_only_the_marker_is_stored_in_flow_run_parameters(self):
        events = _events(8, self.week)
        result = pipeline.transform_weekly_kpis(pipeline.EventBatch(events), QualityCounts(), self.week, self.week)
        self.assertEqual(len(result.rows), 2)
        stored = asyncio.run(_stored_parameters())
        mine = [params for params in stored if params.get("week_from") == self.week.isoformat()]
        self.assertTrue(mine, "the transform flow run was not found in the server")
        for params in mine:
            self.assertEqual(params["events"], "<EventBatch>")
            # `quality` solo lleva conteos (sin identificadores): Prefect lo guarda o lo sustituye por
            # un marcador, según si sus claves son texto. Ninguna de las dos cosas es un riesgo.
        dump = json.dumps(stored)
        for event in events:
            self.assertNotIn(event.event_id, dump)
        self.assertNotIn("order_id", dump)
        self.assertNotIn("unit_cost", dump)

    def test_the_guard_would_catch_a_plain_list(self):
        # Control negativo: con una lista de eventos, el serializador de Prefect sí los incluye.
        events = _events(3, self.week)
        serialized = pipeline.transform_weekly_kpis.serialize_parameters(
            {"events": events, "quality": QualityCounts(), "week_from": self.week, "week_to": self.week})
        self.assertIsInstance(serialized["events"], list)
        self.assertIn(events[0].event_id, json.dumps(serialized))

    def test_ten_thousand_events_create_the_subflow_and_finish(self):
        # Una lista de 10 000 eventos son 2,6 MB de JSON: con el tope por defecto, un 422 al crear el flow run.
        events = _events(10_000, self.week)
        state = pipeline.transform_weekly_kpis(
            pipeline.EventBatch(events), QualityCounts(), self.week, self.week, return_state=True)
        self.assertTrue(state.is_completed(), state)
        result = state.result()
        self.assertEqual(result.stats.source_rows_read, 10_000)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(sum(row.kits_delivered_count for row in result.rows), 2_500)


if __name__ == "__main__":
    unittest.main()
