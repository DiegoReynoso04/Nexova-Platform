"""`services/telemetry/analysis.py`: las métricas, su fórmula y sus límites.

SQLite en memoria, con la tabla real. Ningún test conecta con Supabase: lo propio
de PostgreSQL se comprueba compilando la SQL con su dialecto y en el efímero
(docs/telemetry/report-review.md).
"""

import ast
import json
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlmodel import Session, SQLModel
from telemetry import analysis
from telemetry.analysis import (
    ERROR_CLASSES,
    TECHNICAL_EVENT_TYPES,
    all_metrics,
    auth_failure_rate,
    dominant_event_types,
    error_rate_by_type,
    events_per_day,
    page_load_latency_by_route,
)

from app.modules.inventory.database import build_engine
from app.modules.telemetry.allowlists import EVENT_ALLOWLISTS
from app.modules.telemetry.models import TelemetryEventRecord

ANALYSIS_PATH = Path(analysis.__file__)
METRICS = (events_per_day, error_rate_by_type, page_load_latency_by_route, dominant_event_types, auth_failure_rate)
METRIC_NAMES = {metric.__name__ for metric in METRICS}
BUSINESS_EVENT_TYPES = {
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "kit_cost_variance_detected",
}
# §4 de report-analysis.md: dimensiones de negocio de `tags`.
BUSINESS_KEYS = {
    "office",
    "product_id",
    "product_category",
    "programme_id",
    "quantity",
    "currency",
    "unit_cost",
    "supplier_key",
    "variance_pct",
    "stock_before",
    "stock_after",
    "min_stock",
    "inbound_order_id",
    "outbound_order_id",
    "exit_type",
    "asset_category",
}
PERSONAL_KEYS = {"user_id", "session_id", "event_id", "userId", "sessionId", "eventId"}
STEPS = (
    "# 1. cargar (SQL)",
    "# 2. refinar (Pandas)",
    "# 3. convertir tipos",
    "# 4. agrupar",
    "# 5. agregar",
    "# 6. servir",
)

START = datetime(2026, 11, 1, tzinfo=UTC)
END = datetime(2026, 11, 4, tzinfo=UTC)


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def login(outcome: str) -> dict[str, Any]:
    return {"form": "login", "outcome": outcome, "duration_ms": 900, "attempt_number": 1}


def page_load(route: str, duration: int, outcome: str = "data") -> dict[str, Any]:
    return {"route_template": route, "duration_ms": duration, "outcome": outcome}


class AnalysisCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = build_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        SQLModel.metadata.create_all(self.engine, tables=[TelemetryEventRecord.__table__])  # type: ignore[attr-defined]

    def add(self, event_type: str, moment: datetime = at(2), tags: dict[str, Any] | None = None, service: str = "backoffice") -> None:
        with Session(self.engine) as session:
            session.add(
                TelemetryEventRecord(
                    event_id=uuid4(),
                    event_type=event_type,
                    timestamp=moment,
                    service=service,
                    user_id=uuid4(),
                    session_id=uuid4(),
                    schema_version="1.0.0",
                    tags=tags or {},
                )
            )
            session.commit()

    def run_metric(self, metric: Any, start: datetime = START, end: datetime = END) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            result: list[dict[str, Any]] = metric(connection, start, end)
        return result


class EventsPerDayTests(AnalysisCase):
    def days(self, start: datetime, end: datetime) -> list[str]:
        return sorted({row["day"] for row in self.run_metric(events_per_day, start, end)})

    def test_counts_by_day_and_service(self) -> None:
        self.add("page_viewed", at(1))
        self.add("page_viewed", at(1, 13))
        self.add("direct_stock_edit_rejected", at(1), service="api")
        self.add("page_viewed", at(3))
        self.assertEqual(
            self.run_metric(events_per_day),
            [
                {"day": "2026-11-01", "service": "backoffice", "events": 2},
                {"day": "2026-11-01", "service": "api", "events": 1},
                {"day": "2026-11-02", "service": "backoffice", "events": 0},
                {"day": "2026-11-02", "service": "api", "events": 0},
                {"day": "2026-11-03", "service": "backoffice", "events": 1},
                {"day": "2026-11-03", "service": "api", "events": 0},
            ],
        )

    def test_an_empty_day_in_the_middle_is_zero_for_every_service(self) -> None:
        self.add("page_viewed", at(1))
        self.add("page_viewed", at(3))
        empty = [row for row in self.run_metric(events_per_day) if row["day"] == "2026-11-02"]
        self.assertEqual({row["service"] for row in empty}, {"backoffice", "api"})
        self.assertEqual({row["events"] for row in empty}, {0})

    def test_a_period_without_rows_still_returns_every_day_at_zero(self) -> None:
        rows = self.run_metric(events_per_day)
        self.assertEqual([row["day"] for row in rows[::2]], ["2026-11-01", "2026-11-02", "2026-11-03"])
        self.assertEqual({row["events"] for row in rows}, {0})

    def test_end_at_midnight_leaves_that_day_out(self) -> None:
        self.assertEqual(self.days(at(1, 0), at(3, 0)), ["2026-11-01", "2026-11-02"])

    def test_end_after_midnight_includes_that_day(self) -> None:
        self.assertEqual(self.days(at(1, 0), at(3, 0) + timedelta(milliseconds=1)), ["2026-11-01", "2026-11-02", "2026-11-03"])

    def test_a_start_in_the_middle_of_a_day_includes_that_day(self) -> None:
        self.assertEqual(self.days(at(1, 18), at(2, 6)), ["2026-11-01", "2026-11-02"])

    def test_a_window_inside_one_day_has_that_day_only(self) -> None:
        self.assertEqual(self.days(at(1, 9), at(1, 10)), ["2026-11-01"])

    def test_the_month_change_has_no_gap(self) -> None:
        self.assertEqual(self.days(datetime(2026, 10, 31, 23, tzinfo=UTC), at(1, 1)), ["2026-10-31", "2026-11-01"])

    def test_an_event_in_the_last_partial_day_is_counted(self) -> None:
        self.add("page_viewed", at(3, 5))
        rows = self.run_metric(events_per_day, at(1, 0), at(3, 6))
        self.assertIn({"day": "2026-11-03", "service": "backoffice", "events": 1}, rows)

    def test_counts_are_rows_not_occurrences(self) -> None:
        self.add("client_request_failed", at(1), {"suppressed_count": 9})
        self.assertEqual(self.run_metric(events_per_day)[0], {"day": "2026-11-01", "service": "backoffice", "events": 1})

    def test_business_events_count_as_rows(self) -> None:
        self.add("outbound_order_created", at(1), {"office": "valencia"})
        self.assertEqual(self.run_metric(events_per_day)[0]["events"], 1)


class ErrorRateTests(AnalysisCase):
    def rows(self) -> dict[str, dict[str, Any]]:
        return {row["error_type"]: row for row in self.run_metric(error_rate_by_type)}

    def test_each_candidate_has_its_class(self) -> None:
        self.add("client_request_failed", tags={"suppressed_count": 0})
        self.add("frontend_error_captured", tags={"suppressed_count": 0})
        self.add("page_load_recorded", tags=page_load("/suppliers", 10, "error"))
        self.add("form_submitted", tags=login("network_error"))
        self.add("form_submitted", tags=login("server_error"))
        self.add("form_submitted", tags=login("api_rejected"))
        self.add("form_submitted", tags=login("validation_error"))
        self.add("form_submitted", tags=login("session_expired"))
        self.add("form_validation_failed", tags={"form": "login", "fields": ["email"]})
        self.add("page_not_found_viewed", tags={"previous_route_template": None})
        self.add("direct_stock_edit_rejected", tags={"suppressed_count": 0}, service="api")
        self.assertEqual({key: row["error_class"] for key, row in self.rows().items()}, dict(ERROR_CLASSES))

    def test_rate_is_over_the_technical_events_of_the_day(self) -> None:
        self.add("page_viewed", at(1))
        self.add("page_viewed", at(1))
        self.add("page_viewed", at(1))
        self.add("form_submitted", at(1), login("api_rejected"))
        self.add("page_viewed", at(2))
        self.assertEqual(
            self.run_metric(error_rate_by_type),
            [
                {
                    "day": "2026-11-01",
                    "error_type": "form_submitted:api_rejected",
                    "error_class": "rejected",
                    "errors": 1,
                    "total_events": 4,
                    "error_rate": 0.25,
                }
            ],
        )

    def test_success_and_data_are_not_errors(self) -> None:
        self.add("form_submitted", tags=login("success"))
        self.add("page_load_recorded", tags=page_load("/suppliers", 10, "data"))
        self.add("page_load_recorded", tags=page_load("/suppliers", 10, "empty"))
        self.assertEqual(self.run_metric(error_rate_by_type), [])

    def test_suppressed_events_count_in_the_errors_and_in_the_total(self) -> None:
        self.add("client_request_failed", tags={"suppressed_count": 9})
        self.add("page_viewed")
        row = self.rows()["client_request_failed"]
        self.assertEqual((row["errors"], row["total_events"], row["error_rate"]), (10, 11, 10 / 11))

    def test_business_events_are_not_in_the_denominator(self) -> None:
        self.add("form_submitted", tags=login("api_rejected"))
        self.add("outbound_order_created", tags={"office": "valencia"})
        self.assertEqual(self.rows()["form_submitted:api_rejected"]["total_events"], 1)

    def test_rows_without_outcome_do_not_break_the_labels(self) -> None:
        self.add("page_viewed")
        self.add("form_abandoned", tags={"form": "login"})
        self.assertEqual(self.run_metric(error_rate_by_type), [])


class LatencyTests(AnalysisCase):
    def test_groups_by_day_route_and_outcome(self) -> None:
        self.add("page_load_recorded", at(1), page_load("/suppliers", 100))
        self.add("page_load_recorded", at(1), page_load("/suppliers", 300))
        self.add("page_load_recorded", at(1), page_load("/suppliers", 5000, "error"))
        self.add("page_load_recorded", at(2), page_load("/inventory/orders", 50, "empty"))
        self.assertEqual(
            self.run_metric(page_load_latency_by_route),
            [
                {"day": "2026-11-01", "route_template": "/suppliers", "outcome": "data", "loads": 2, "avg_ms": 200.0, "max_ms": 300},
                {"day": "2026-11-01", "route_template": "/suppliers", "outcome": "error", "loads": 1, "avg_ms": 5000.0, "max_ms": 5000},
                {"day": "2026-11-02", "route_template": "/inventory/orders", "outcome": "empty", "loads": 1, "avg_ms": 50.0, "max_ms": 50},
            ],
        )

    def test_rows_with_null_dimensions_are_discarded(self) -> None:
        self.add("page_load_recorded", tags={"route_template": None, "duration_ms": 10, "outcome": "data"})
        self.add("page_load_recorded", tags={"route_template": "/suppliers", "duration_ms": None, "outcome": "data"})
        self.add("page_load_recorded", tags={"route_template": "/suppliers", "duration_ms": 10})
        self.assertEqual(self.run_metric(page_load_latency_by_route), [])

    def test_form_durations_are_not_latency(self) -> None:
        self.add("form_submitted", tags=login("success"))
        self.assertEqual(self.run_metric(page_load_latency_by_route), [])


class DominantEventTypesTests(AnalysisCase):
    def test_most_frequent_first_with_their_share(self) -> None:
        self.add("page_viewed")
        self.add("page_viewed")
        self.add("page_viewed")
        self.add("direct_stock_edit_rejected", service="api")
        self.assertEqual(
            self.run_metric(dominant_event_types),
            [
                {"event_type": "page_viewed", "service": "backoffice", "events": 3, "share": 0.75},
                {"event_type": "direct_stock_edit_rejected", "service": "api", "events": 1, "share": 0.25},
            ],
        )

    def test_ties_have_a_stable_order(self) -> None:
        self.add("page_viewed")
        self.add("form_started")
        self.assertEqual([row["event_type"] for row in self.run_metric(dominant_event_types)], ["form_started", "page_viewed"])


class AuthFailureRateTests(AnalysisCase):
    def test_daily_rate(self) -> None:
        self.add("form_submitted", at(1), login("api_rejected"))
        self.add("form_submitted", at(1), login("api_rejected"))
        self.add("form_submitted", at(1), login("api_rejected"))
        self.add("form_submitted", at(1), login("success"))
        self.add("form_submitted", at(3), login("success"))
        self.assertEqual(
            self.run_metric(auth_failure_rate),
            [
                {"day": "2026-11-01", "failed": 3, "succeeded": 1, "attempts": 4, "failure_rate": 0.75},
                {"day": "2026-11-03", "failed": 0, "succeeded": 1, "attempts": 1, "failure_rate": 0.0},
            ],
        )

    def test_other_outcomes_are_not_attempts(self) -> None:
        self.add("form_submitted", tags=login("validation_error"))
        self.add("form_submitted", tags=login("network_error"))
        self.add("form_submitted", tags=login("server_error"))
        self.add("form_submitted", tags=login("session_expired"))
        self.assertEqual(self.run_metric(auth_failure_rate), [])

    def test_other_forms_do_not_count(self) -> None:
        self.add("form_submitted", tags={"form": "inbound_order", "outcome": "api_rejected"})
        self.add("form_submitted", tags={"form": "register", "outcome": "success"})
        self.assertEqual(self.run_metric(auth_failure_rate), [])


class WindowTests(AnalysisCase):
    def statements(self, metric: Any) -> list[tuple[str, Any]]:
        captured: list[tuple[str, Any]] = []

        def record(conn: Any, cursor: Any, statement: str, parameters: Any, *args: Any) -> None:
            captured.append((statement, parameters))

        event.listen(self.engine, "before_cursor_execute", record)
        try:
            self.run_metric(metric)
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        return captured

    def test_start_is_inclusive_and_end_is_exclusive(self) -> None:
        self.add("form_submitted", START, login("success"))
        self.add("form_submitted", END, login("api_rejected"))
        self.add("form_submitted", END - timedelta(milliseconds=1), login("success"))
        self.add("form_submitted", START - timedelta(milliseconds=1), login("api_rejected"))
        rows = self.run_metric(auth_failure_rate)
        self.assertEqual([(row["day"], row["succeeded"], row["failed"]) for row in rows], [("2026-11-01", 1, 0), ("2026-11-03", 1, 0)])

    def test_every_metric_filters_the_window_in_one_sql_statement(self) -> None:
        for metric in METRICS:
            with self.subTest(metric=metric.__name__):
                [(statement, _)] = self.statements(metric)
                self.assertIn("telemetry_events.timestamp >= ", statement)
                self.assertIn("telemetry_events.timestamp < ", statement)

    def test_event_types_are_filtered_in_sql(self) -> None:
        for metric, expected in (
            (error_rate_by_type, "form_submitted"),
            (page_load_latency_by_route, "page_load_recorded"),
            (auth_failure_rate, "form_submitted"),
        ):
            with self.subTest(metric=metric.__name__):
                [(statement, parameters)] = self.statements(metric)
                self.assertIn("telemetry_events.event_type IN", statement)
                self.assertIn(expected, parameters)

    def test_no_metric_selects_identifiers(self) -> None:
        for metric in METRICS:
            with self.subTest(metric=metric.__name__):
                [(statement, _)] = self.statements(metric)
                selected = statement.split("FROM")[0]
                self.assertNotIn("user_id", selected)
                self.assertNotIn("session_id", selected)
                self.assertNotIn("event_id", selected)

    def test_volume_metrics_do_not_load_tags(self) -> None:
        for metric in (events_per_day, dominant_event_types):
            with self.subTest(metric=metric.__name__):
                [(statement, _)] = self.statements(metric)
                self.assertNotIn("tags", statement.split("FROM")[0])

    def test_the_filter_compiles_for_postgresql(self) -> None:
        columns = TelemetryEventRecord.__table__.c  # type: ignore[attr-defined]
        statement = (
            select(columns.timestamp)
            .where(columns.timestamp >= START, columns.timestamp < END)
            .where(columns.event_type.in_(("page_viewed",)))
        )
        sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        self.assertIn("telemetry_events.timestamp >= '2026-11-01 00:00:00+00:00'", sql)
        self.assertIn("telemetry_events.timestamp < '2026-11-04 00:00:00+00:00'", sql)
        self.assertIn("telemetry_events.event_type IN ('page_viewed')", sql)

    def test_utc_conversion_matches_naive_sqlite_and_aware_postgresql_values(self) -> None:
        naive = pd.to_datetime(pd.Series([datetime(2026, 11, 1, 23, 30)]), utc=True)
        aware = pd.to_datetime(pd.Series([datetime(2026, 11, 2, 0, 30, tzinfo=timezone(timedelta(hours=1)))]), utc=True)
        self.assertEqual(naive.iloc[0], aware.iloc[0])


class EmptyTests(AnalysisCase):
    def test_without_rows_the_other_metrics_are_empty(self) -> None:
        for metric in METRICS:
            if metric is not events_per_day:
                with self.subTest(metric=metric.__name__):
                    self.assertEqual(self.run_metric(metric), [])

    def test_rows_outside_the_window_are_not_counted(self) -> None:
        self.add("form_submitted", at(20), login("api_rejected"))
        self.add("page_load_recorded", at(20), page_load("/suppliers", 10))
        for metric in METRICS:
            if metric is not events_per_day:
                with self.subTest(metric=metric.__name__):
                    self.assertEqual(self.run_metric(metric), [])
        self.assertEqual({row["events"] for row in self.run_metric(events_per_day)}, {0})


class SerializableTests(AnalysisCase):
    def setUp(self) -> None:
        super().setUp()
        self.add("page_viewed", at(1))
        self.add("form_submitted", at(1), login("api_rejected"))
        self.add("form_submitted", at(2), login("success"))
        self.add("client_request_failed", at(2), {"suppressed_count": 2})
        self.add("page_load_recorded", at(2), page_load("/suppliers", 123))
        self.add(
            "outbound_order_created",
            at(2),
            {"office": "valencia", "product_id": 7, "quantity": 3, "currency": "EUR", "exit_type": "allocation", "stock_after": 6},
        )

    def metrics(self) -> dict[str, list[dict[str, Any]]]:
        with self.engine.connect() as connection:
            return all_metrics(connection, START, END)

    def test_the_report_has_the_five_metrics(self) -> None:
        self.assertEqual(set(self.metrics()), METRIC_NAMES)

    def test_only_python_types_and_no_nulls(self) -> None:
        for name, rows in self.metrics().items():
            self.assertTrue(rows, name)
            for row in rows:
                for key, value in row.items():
                    with self.subTest(metric=name, key=key):
                        self.assertIn(type(value), {str, int, float})
                        self.assertEqual(value, value, "NaN")

    def test_strict_json(self) -> None:
        json.dumps(self.metrics(), allow_nan=False)

    def test_no_business_field_nor_identifier_in_any_metric(self) -> None:
        metrics = self.metrics()
        keys = {key for rows in metrics.values() for row in rows for key in row}
        self.assertFalse(keys & (BUSINESS_KEYS | PERSONAL_KEYS))
        text = json.dumps(metrics)
        self.assertNotIn("valencia", text)
        self.assertNotIn("EUR", text)


class CatalogTests(unittest.TestCase):
    def outcomes(self, event_type: str) -> Any:
        return EVENT_ALLOWLISTS[event_type].properties["outcome"]["enum"]

    def test_technical_events_are_the_stored_ones_minus_business(self) -> None:
        self.assertEqual(set(TECHNICAL_EVENT_TYPES), set(EVENT_ALLOWLISTS) - BUSINESS_EVENT_TYPES)

    def test_every_error_type_exists_in_the_allowlist(self) -> None:
        for error_type in ERROR_CLASSES:
            with self.subTest(error_type=error_type):
                event_type, _, outcome = error_type.partition(":")
                self.assertIn(event_type, EVENT_ALLOWLISTS)
                if outcome:
                    self.assertIn(outcome, self.outcomes(event_type))

    def test_every_failing_form_outcome_is_classified(self) -> None:
        for outcome in self.outcomes("form_submitted"):
            if outcome != "success":
                self.assertIn(f"form_submitted:{outcome}", ERROR_CLASSES)


LOOP_NODES = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
# Fila a fila, ventana propia, redondeo y SQL sin tipos.
FORBIDDEN_ATTRIBUTES = {"iterrows", "itertuples", "apply", "applymap", "round", "quantize", "now", "utcnow", "today", "Timedelta", "between"}
FORBIDDEN_NAMES = {"round", "print", "text"}


class FormulaRulesTests(unittest.TestCase):
    """La fórmula y sus prohibiciones, sobre el código fuente de `analysis.py`.

    `tests/test_architecture.py` solo mira `app/`: esta carpeta tiene sus reglas aquí.
    """

    source: str
    tree: ast.Module
    functions: dict[str, ast.FunctionDef]

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ANALYSIS_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {node.name: node for node in cls.tree.body if isinstance(node, ast.FunctionDef)}

    def metric_functions(self) -> list[ast.FunctionDef]:
        return [self.functions[name] for name in sorted(METRIC_NAMES)]

    def test_there_are_at_least_three_metrics(self) -> None:
        self.assertGreaterEqual(len(self.metric_functions()), 3)

    def test_no_loops_anywhere(self) -> None:
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, LOOP_NODES, f"line {getattr(node, 'lineno', '?')}")

    def test_no_row_by_row_window_or_rounding_tools(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, FORBIDDEN_ATTRIBUTES, f"line {node.lineno}")
            elif isinstance(node, ast.Name):
                self.assertNotIn(node.id, FORBIDDEN_NAMES, f"line {node.lineno}")

    def test_no_web_framework(self) -> None:
        imported = {node.module.split(".")[0] for node in ast.walk(self.tree) if isinstance(node, ast.ImportFrom) and node.module}
        imported |= {alias.name.split(".")[0] for node in ast.walk(self.tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imported & {"fastapi", "starlette", "logging"})

    def test_each_function_marks_the_six_steps_in_order(self) -> None:
        lines = self.source.splitlines()
        for function in self.metric_functions():
            with self.subTest(metric=function.name):
                body = lines[function.lineno - 1 : function.end_lineno]
                positions = [next(i for i, line in enumerate(body) if line.strip().startswith(step)) for step in STEPS]
                self.assertEqual(positions, sorted(positions))

    def test_to_datetime_with_utc_comes_before_any_groupby(self) -> None:
        for function in self.metric_functions():
            with self.subTest(metric=function.name):
                calls = [node for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
                conversions = [
                    call.lineno
                    for call in calls
                    if call.func.attr == "to_datetime"  # type: ignore[attr-defined]
                    and any(k.arg == "utc" and isinstance(k.value, ast.Constant) and k.value.value is True for k in call.keywords)
                ]
                groupbys = [call.lineno for call in calls if call.func.attr == "groupby"]  # type: ignore[attr-defined]
                self.assertTrue(conversions)
                self.assertTrue(groupbys)
                self.assertLess(max(conversions), min(groupbys))

    def test_each_function_starts_by_loading(self) -> None:
        for function in self.metric_functions():
            with self.subTest(metric=function.name):
                first = function.body[1]  # body[0] es el docstring
                assert isinstance(first, ast.Assign) and isinstance(first.value, ast.Call)
                assert isinstance(first.value.func, ast.Name)
                self.assertEqual(first.value.func.id, "_load")

    def test_no_business_key_or_identifier_appears_as_a_literal(self) -> None:
        literals = {node.value for node in ast.walk(self.tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertFalse(literals & (BUSINESS_KEYS | PERSONAL_KEYS))


if __name__ == "__main__":
    unittest.main()
