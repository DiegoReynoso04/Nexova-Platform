"""Transformación pura (§2.5 del diseño). Datos ficticios: ningún programa ni orden real."""

import ast
import sys
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from weekly_performance import (
    DataQualityError,
    ExtractedEvent,
    QualityCounts,
    WeekSelectionError,
    last_closed_week,
    resolve_weeks,
    transform,
    week_start_of,
    weeks_between,
    window_of,
)

# Lunes 2026-11-02 y la semana siguiente. «Hoy» es el martes 2026-11-17.
W1 = date(2026, 11, 2)
W2 = date(2026, 11, 9)
NOW = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
FAKE_PROGRAMME = "programa-ficticio"

_counter = 0


def event(event_type="outbound_order_created", *, ts=None, office="valencia", currency=None, quantity="1",
          unit_cost=None, order_id="1", programme_id=None, event_id=None):
    global _counter
    _counter += 1
    if currency is None:
        currency = "EUR" if office == "valencia" else "USD"
    return ExtractedEvent(
        event_id=event_id or f"00000000-0000-4000-8000-{_counter:012d}",
        event_type=event_type,
        timestamp=ts or datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        office=office,
        programme_id=programme_id,
        currency=currency,
        quantity=quantity,
        unit_cost=unit_cost,
        order_id=order_id,
    )


def _asdict(item):
    return {name: getattr(item, name) for name in item.__slots__}


def run(events, week_from=W1, week_to=W1, quality=None):
    return transform(events, quality or QualityCounts(), week_from, week_to)


class WeekTests(unittest.TestCase):
    def test_week_start_is_the_utc_monday(self):
        self.assertEqual(week_start_of(datetime(2026, 11, 8, 23, 59, tzinfo=UTC)), W1)
        self.assertEqual(week_start_of(datetime(2026, 11, 9, 0, 0, tzinfo=UTC)), W2)

    def test_miami_sunday_evening_is_already_next_week_in_utc(self):
        from zoneinfo import ZoneInfo

        try:
            miami = ZoneInfo("America/New_York")
        except Exception:  # tzdata ausente en Windows sin el paquete
            self.skipTest("time zone data not available")
        sunday_evening = datetime(2026, 11, 8, 20, 30, tzinfo=miami)  # 01:30 UTC del lunes
        self.assertEqual(week_start_of(sunday_evening), W2)

    def test_naive_timestamps_are_refused(self):
        with self.assertRaises(ValueError):
            week_start_of(datetime(2026, 11, 3))

    def test_last_closed_week(self):
        self.assertEqual(last_closed_week(NOW), W2)
        self.assertEqual(last_closed_week(datetime(2026, 11, 9, 0, 0, tzinfo=UTC)), W1)

    def test_resolve_weeks(self):
        self.assertEqual(resolve_weeks("manual", None, NOW), (W2, W2))
        self.assertEqual(resolve_weeks("manual", W1, NOW), (W1, W1))
        self.assertEqual(resolve_weeks("schedule", None, NOW), (W1, W2))

    def test_resolve_weeks_refuses_bad_weeks(self):
        for week in (date(2026, 11, 3), date(2026, 11, 16), date(2026, 11, 23), date(2026, 8, 3)):
            with self.subTest(week=week), self.assertRaises(WeekSelectionError):
                resolve_weeks("manual", week, NOW)

    def test_weeks_between_and_window(self):
        self.assertEqual(weeks_between(W1, W2), [W1, W2])
        self.assertEqual(window_of(W1, W2), (datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 16, tzinfo=UTC)))


class TransformTests(unittest.TestCase):
    def test_four_kpis_per_cell_with_unassigned_programme(self):
        result = run([
            event("inbound_order_created", quantity="12", unit_cost="18.5", order_id="41"),
            event("inbound_order_created", quantity="3", unit_cost="0.10", order_id="42"),
            event("outbound_order_created", order_id="7"),
            event("outbound_order_created", order_id="8"),
            event("stock_threshold_triggered", order_id="8"),
            event("kit_cost_variance_detected", order_id="42"),
        ])
        (row,) = result.rows
        self.assertEqual((row.office, row.programme_id, row.week_start, row.currency), ("valencia", "_unassigned", W1, "EUR"))
        self.assertEqual(row.total_material_cost, Decimal("222.30"))
        self.assertIsInstance(row.total_material_cost, Decimal)
        self.assertEqual((row.kits_delivered_count, row.shortage_events_count, row.cost_variance_events_count), (2, 1, 1))
        self.assertEqual((result.stats.source_rows_read, result.stats.rows_rejected, result.stats.duplicates_collapsed), (6, 0, 0))

    def test_offices_never_mix(self):
        result = run([event(office="valencia"), event(office="miami", order_id="2")])
        self.assertEqual([(row.office, row.currency) for row in result.rows], [("miami", "USD"), ("valencia", "EUR")])

    def test_same_order_with_two_event_ids_counts_once(self):
        first = event(order_id="9", ts=datetime(2026, 11, 3, 9, tzinfo=UTC))
        resent = event(order_id="9", ts=datetime(2026, 11, 3, 9, 1, tzinfo=UTC))
        result = run([resent, first])
        self.assertEqual(result.rows[0].kits_delivered_count, 1)
        self.assertEqual(result.stats.duplicates_collapsed, 1)

    def test_same_order_id_in_two_weeks_counts_in_each(self):
        result = run([event(order_id="9"), event(order_id="9", ts=datetime(2026, 11, 10, tzinfo=UTC))], W1, W2)
        self.assertEqual([row.week_start for row in result.rows], [W1, W2])
        self.assertEqual(result.stats.duplicates_collapsed, 0)

    def test_programme_slug_is_kept(self):
        result = run([event(programme_id=FAKE_PROGRAMME)])
        self.assertEqual(result.rows[0].programme_id, FAKE_PROGRAMME)

    def test_invalid_records_are_rejected_and_counted(self):
        result = run([
            event(office="madrid"),
            event(office="miami", currency="EUR"),
            event(quantity="0"),
            event(quantity="1.5"),
            event(order_id="x"),
            event("inbound_order_created", unit_cost=None),
            event("inbound_order_created", unit_cost="-1"),
            event("inbound_order_created", unit_cost="NaN"),
            event(programme_id="_unassigned"),
            event(programme_id="Not A Slug"),
            event("page_viewed"),
            event(ts=datetime(2026, 11, 10, tzinfo=UTC)),  # fuera de las semanas pedidas
        ])
        self.assertEqual(result.rows, ())
        self.assertEqual(result.stats.rows_rejected, 12)

    def test_no_activity_means_no_rows(self):
        result = run([])
        self.assertEqual(result.rows, ())
        self.assertEqual(result.quality["weeks"]["2026-11-02"]["technical_events"], 0)

    def test_two_currencies_in_one_cell_fail(self):
        # Inalcanzable con el tipado (la moneda tiene que ser la de la oficina, y la
        # oficina es parte de la celda): se fuerza quitando esa comprobación.
        import weekly_performance  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415

        with mock.patch.dict(weekly_performance.OFFICE_CURRENCY, {weekly_performance.Office.VALENCIA: "EUR"}):
            original = weekly_performance._typed

            def lenient(item):
                typed = original(ExtractedEvent(**{**_asdict(item), "currency": "EUR"}))
                return None if typed is None else type(typed)(**{**_asdict(typed), "currency": item.currency})

            with mock.patch.object(weekly_performance, "_typed", lenient):
                with self.assertRaises(DataQualityError):
                    run([event(order_id="1"), event(order_id="2", currency="USD")])

    def test_deterministic(self):
        events = [event("inbound_order_created", unit_cost="2.5", order_id=str(n)) for n in range(1, 6)]
        self.assertEqual(run(events), run(list(reversed(events))))

    def test_reconciliation_counts(self):
        quality = QualityCounts(
            technical={"2026-11-02": 40},
            inventory_entries_with_cost={("2026-11-02", "valencia"): 2},
            inventory_exits={("2026-11-02", "miami"): 1},
        )
        result = run([event("inbound_order_created", unit_cost="1", order_id="1")], quality=quality)
        week = result.quality["weeks"]["2026-11-02"]
        self.assertEqual(week["technical_events"], 40)
        self.assertEqual(week["offices"]["valencia"], {
            "inventory_entries_with_cost": 2, "inbound_events": 1, "inventory_exits": 0, "outbound_events": 0})
        self.assertEqual(week["offices"]["miami"]["inventory_exits"], 1)


class SourceTests(unittest.TestCase):
    def test_standard_library_and_nexova_shared_only(self):
        path = Path(__file__).resolve().parents[1] / "weekly_performance.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                with self.subTest(module=name):
                    self.assertTrue(root in sys.stdlib_module_names or root in {"nexova_shared", "__future__"})


if __name__ == "__main__":
    unittest.main()
