"""Tasks de transformación del pipeline de desempeño de negocio: los 4 KPI del BRIEFING.

Cada test llama a las tasks con `.fn` (la función de Python, sin motor, sin servidor de Prefect, sin
base de datos y sin red) sobre eventos ficticios en memoria con la forma de `telemetry_events`
(ver `conftest.py`). Comando, desde la raíz del monorepo:

    python -m pytest tests/pipelines/test_pipeline.py

KPI (BRIEFING §2 y §4; el diseño, en `data/pipelines/PIPELINE_DESIGN.md` §2.2):
  total_material_cost         Costo de material por oficina/programa
  kits_delivered_count        Kits entregados
  shortage_events_count       Frecuencia de escasez
  cost_variance_events_count  Frecuencia de variación de costo
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pipeline
from weekly_performance import WeeklyRow

W1 = date(2026, 11, 2)  # lunes
W2 = date(2026, 11, 9)  # lunes siguiente
TUESDAY_W1 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
TUESDAY_W2 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
UNASSIGNED = "_unassigned"
FICTITIOUS_PROGRAMME = "programa-ficticio"


def kept_events(events, week_from=W1, week_to=None):
    """Lo que reciben las tasks por KPI: eventos tipados y sin órdenes duplicadas."""
    typed = pipeline.type_and_validate_events.fn(events, week_from, week_to or week_from)
    return pipeline.collapse_duplicate_orders.fn(typed.items).items


# --- Un KPI por task ----------------------------------------------------------------------------


def test_total_material_cost_sums_unit_cost_times_quantity(telemetry_row, extracted):
    events = extracted([
        telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=1, quantity=4, unit_cost=12.5),
        telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=2, quantity=2, unit_cost=3.25),
    ])
    # Cálculo a mano: 4 × 12,50 = 50,00 y 2 × 3,25 = 6,50; 50,00 + 6,50 = 56,50 (EUR, Valencia).
    assert pipeline.compute_total_material_cost.fn(kept_events(events)) == {("valencia", UNASSIGNED, W1): Decimal("56.50")}


def test_kits_delivered_counts_orders_not_units(telemetry_row, extracted):
    events = extracted([
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=1, office="miami", quantity=12),
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=2, office="miami", quantity=1),
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=3, office="miami", quantity=5),
    ])
    # D4 del diseño: una orden es 1 kit entregado en el KPI, sin importar sus unidades (12 + 1 + 5 = 18 no).
    assert pipeline.compute_kits_delivered_count.fn(kept_events(events)) == {("miami", UNASSIGNED, W1): 3}


def test_shortage_events_count_counts_threshold_crossings_per_week(telemetry_row, extracted):
    events = extracted([
        telemetry_row("stock_threshold_triggered", at=TUESDAY_W1, order_id=10),
        telemetry_row("stock_threshold_triggered", at=TUESDAY_W1, order_id=11),
        telemetry_row("stock_threshold_triggered", at=TUESDAY_W2, order_id=12),
    ])
    assert pipeline.compute_shortage_events_count.fn(kept_events(events, W1, W2)) == {
        ("valencia", UNASSIGNED, W1): 2,
        ("valencia", UNASSIGNED, W2): 1,
    }


def test_cost_variance_events_count_counts_variations_per_cell(telemetry_row, extracted, transform_with_tasks):
    events = extracted([
        telemetry_row("kit_cost_variance_detected", at=TUESDAY_W1, order_id=5),
        telemetry_row("kit_cost_variance_detected", at=TUESDAY_W1, order_id=6),
        telemetry_row("kit_cost_variance_detected", at=TUESDAY_W1, order_id=7, office="miami"),
    ])
    assert pipeline.compute_cost_variance_events_count.fn(kept_events(events)) == {
        ("valencia", UNASSIGNED, W1): 2,
        ("miami", UNASSIGNED, W1): 1,
    }
    # Una celda que solo tuvo variaciones sigue saliendo en el reporte, con costo 0.
    rows = transform_with_tasks(events, W1).rows
    assert [(row.office, row.total_material_cost, row.cost_variance_events_count) for row in rows] == [
        ("miami", Decimal("0"), 1),
        ("valencia", Decimal("0"), 2),
    ]


# --- El reporte de una semana contra un cálculo a mano -----------------------------------------------


def test_week_report_matches_hand_calculation(telemetry_row, extracted, transform_with_tasks):
    # Definiciones del BRIEFING (§4), semana del lunes 2026-11-02 (UTC), una fila por oficina y programa:
    #   total_material_cost         suma de los costos de inbound_order_created de la semana, en la
    #                               moneda local de la oficina (aquí unit_cost × quantity, §2.2 del diseño)
    #   kits_delivered_count        conteo de outbound_order_created de la semana
    #   shortage_events_count       conteo de stock_threshold_triggered de la semana
    #   cost_variance_events_count  conteo de kit_cost_variance_detected de la semana
    #   currency                    EUR (Valencia) o USD (Miami), sin conversión
    #
    # Valencia (EUR):
    #   costo      10 × 18,50 = 185,00  y  5 × 20,00 = 100,00   →  285,00
    #   kits       4 órdenes de salida (ids 1, 2, 3 y 4)         →  4
    #   escasez    1 cruce del mínimo (orden de salida 4)        →  1
    #   variación  1 entrada con costo anómalo (entrada 2)       →  1
    # Miami (USD):
    #   costo      3 × 40,00 = 120,00                            →  120,00
    #   kits       2 órdenes de salida (ids 1 y 2)               →  2
    #   escasez 0, variación 0
    events = extracted([
        telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=1, quantity=10, unit_cost=18.5),
        telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=2, quantity=5, unit_cost=20),
        *[telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=order) for order in (1, 2, 3, 4)],
        telemetry_row("stock_threshold_triggered", at=TUESDAY_W1, order_id=4),
        telemetry_row("kit_cost_variance_detected", at=TUESDAY_W1, order_id=2),
        telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=1, office="miami", quantity=3, unit_cost=40),
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=1, office="miami"),
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=2, office="miami"),
    ])
    result = transform_with_tasks(events, W1)
    assert result.rows == (
        WeeklyRow("miami", UNASSIGNED, W1, Decimal("120.00"), 2, 0, 0, "USD"),
        WeeklyRow("valencia", UNASSIGNED, W1, Decimal("285.00"), 4, 1, 1, "EUR"),
    )
    assert (result.stats.source_rows_read, result.stats.rows_rejected, result.stats.duplicates_collapsed) == (11, 0, 0)


# --- Reglas del reporte ----------------------------------------------------------------------------


def test_valencia_and_miami_are_never_mixed(telemetry_row, extracted, transform_with_tasks):
    events = extracted([
        telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=1, quantity=1, unit_cost=10),
        telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=2, office="miami", quantity=1, unit_cost=10),
    ])
    rows = transform_with_tasks(events, W1).rows
    # BRIEFING §7: EUR y USD por separado, nunca sumados: dos filas, cada oficina con su moneda.
    assert {row.office: row.currency for row in rows} == {"valencia": "EUR", "miami": "USD"}
    assert [row.total_material_cost for row in rows] == [Decimal("10"), Decimal("10")]


def test_missing_programme_goes_to_the_unassigned_bucket(telemetry_row, extracted, transform_with_tasks):
    events = extracted([
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=1),
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=2, programme_id=FICTITIOUS_PROGRAMME),
    ])
    rows = transform_with_tasks(events, W1).rows
    assert [(row.programme_id, row.kits_delivered_count) for row in rows] == [
        (UNASSIGNED, 1),
        (FICTITIOUS_PROGRAMME, 1),
    ]


def test_same_order_with_two_event_ids_counts_once(telemetry_row, extracted, transform_with_tasks):
    events = extracted([
        telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=7),
        telemetry_row("outbound_order_created", at=datetime(2026, 11, 3, 9, 5, tzinfo=UTC), order_id=7),
    ])
    result = transform_with_tasks(events, W1)
    assert [row.kits_delivered_count for row in result.rows] == [1]
    assert result.stats.duplicates_collapsed == 1


def test_week_start_is_the_utc_monday(telemetry_row, extracted, transform_with_tasks):
    sunday_evening = datetime(2026, 11, 8, 23, 30, tzinfo=UTC)
    monday_midnight = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
    events = extracted([
        telemetry_row("outbound_order_created", at=sunday_evening, order_id=1),
        telemetry_row("outbound_order_created", at=monday_midnight, order_id=2),
    ])
    rows = transform_with_tasks(events, W1, W2).rows
    # El domingo a las 23:30 UTC cuenta en la semana del 2 de noviembre; el lunes a las 00:00, en la del 9.
    assert [(row.week_start, row.kits_delivered_count) for row in rows] == [(W1, 1), (W2, 1)]


# --- Defensivos: datos nulos, mal tipados o mal formados --------------------------------------------------


def test_malformed_events_are_rejected_not_crashing(telemetry_row, extracted, transform_with_tasks):
    inbound = extracted([telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=1, quantity=2, unit_cost=5)])[0]
    outbound = extracted([telemetry_row("outbound_order_created", at=TUESDAY_W1, order_id=2)])[0]
    malformed = [
        replace(outbound, quantity="abc"),  # no es un número
        replace(outbound, quantity="1.5"),  # no es entero
        replace(outbound, quantity="0"),  # menor que 1
        replace(inbound, unit_cost=None),  # la entrada sin costo
        replace(inbound, unit_cost="-5"),  # costo negativo
        replace(inbound, unit_cost="NaN"),  # costo que no es un número finito
        replace(outbound, office="madrid"),  # una oficina que no existe
        replace(outbound, timestamp=datetime(2026, 11, 3, 9, 0)),  # sin zona horaria
        replace(outbound, currency="USD"),  # Valencia no factura en USD
    ]
    result = transform_with_tasks(malformed, W1)
    assert result.rows == ()
    assert (result.stats.source_rows_read, result.stats.rows_rejected) == (9, 9)


def test_wrong_types_are_rejected_not_crashing(telemetry_row, extracted, transform_with_tasks):
    inbound = extracted([telemetry_row("inbound_order_created", at=TUESDAY_W1, order_id=1, quantity=2, unit_cost=5)])[0]
    wrong_types = [
        replace(inbound, quantity=5),  # entero en lugar de texto
        replace(inbound, unit_cost=2.5),  # float en lugar de texto
        replace(inbound, order_id=None),  # orden nula
    ]
    result = transform_with_tasks(wrong_types, W1)
    assert result.rows == ()
    assert result.stats.rows_rejected == 3


def test_empty_input_means_no_rows(transform_with_tasks):
    assert pipeline.type_and_validate_events.fn([], W1, W1).rejected == 0
    for compute in (
        pipeline.compute_total_material_cost,
        pipeline.compute_kits_delivered_count,
        pipeline.compute_shortage_events_count,
        pipeline.compute_cost_variance_events_count,
    ):
        assert compute.fn(()) == {}, compute.name
    result = transform_with_tasks([], W1)
    assert result.rows == ()
    assert (result.stats.source_rows_read, result.stats.rows_rejected) == (0, 0)

