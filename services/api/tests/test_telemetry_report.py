"""`GET /telemetry/report`: 202, forma del resultado, periodo, autenticación y deduplicación.

Desde DEV-55 la ruta encola `task_queue.telemetry_report` y responde `202 {"task_id"}`;
el reporte, con la forma de siempre, llega por `GET /tasks/{id}` (SPECS §48 y Parte J).
App real con SQLite en memoria y la cola en memoria (`task_queue_support`): el
cliente real de `task_queue` con metadatos y deduplicación de verdad, y un backend
que ejecuta en el acto el mismo cálculo que el worker. Las métricas se prueban en
`test_telemetry_analysis.py`; `/tasks` en sí, en `test_tasks_api.py`.

Las consultas se cuentan con `before_cursor_execute`: encolar no ejecuta ninguna, y
una petición deduplicada tampoco.
"""

import json
import unittest
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from kombu.exceptions import OperationalError as BrokerDown
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlmodel import Session
from task_queue.config import DEDUPE_TTL_SECONDS
from task_queue.metadata import DEDUPE_PREFIX
from task_queue.names import TELEMETRY_REPORT_TASK

from app.auth.models import UserRole
from app.modules.telemetry.models import TelemetryEventRecord
from app.modules.telemetry.report import DEFAULT_WINDOW, MAX_WINDOW, cache_key, iso_utc, resolve_period, to_utc
from app.modules.telemetry.router import dedupe_scope

from .support import authorize
from .task_queue_support import install_task_queue
from .telemetry_support import storage_client

URL = "/telemetry/report"
METRIC_KEYS = {"events_per_day", "error_rate_by_type", "page_load_latency_by_route", "dominant_event_types", "auth_failure_rate"}
NOW = datetime(2026, 11, 5, 12, 0, 0, 123456, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class ReportCase(unittest.TestCase):
    hold = False

    def setUp(self) -> None:
        self.client = storage_client(authenticated=True)
        self.addCleanup(self.client.auth_dir.cleanup)  # type: ignore[attr-defined]
        self.app = self.client.app
        self.engine = self.app.state.inventory_engine  # type: ignore[attr-defined]
        self.clock = Clock()
        self.queue, self.store, self.backend = install_task_queue(self.app, self.engine, clock=self.clock, hold=self.hold)  # type: ignore[arg-type]

    def add(self, event_type: str, moment: datetime, tags: dict[str, Any] | None = None, service: str = "backoffice") -> None:
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

    def enqueue(self, **params: str) -> str:
        response = self.client.get(URL, params=params)
        self.assertEqual(response.status_code, 202, response.text)
        task_id: str = response.json()["task_id"]
        return task_id

    def task(self, task_id: str) -> dict[str, Any]:
        response = self.client.get(f"/tasks/{task_id}")
        self.assertEqual(response.status_code, 200, response.text)
        body: dict[str, Any] = response.json()
        return body

    def report(self, **params: str) -> dict[str, Any]:
        """Lo que antes respondía la ruta: 202 → `GET /tasks/{id}` → `result`."""
        body = self.task(self.enqueue(**params))
        self.assertEqual(body["status"], "success", body)
        result: dict[str, Any] = body["result"]
        return result

    def queries(self, call: Any = None, **params: str) -> int:
        statements: list[str] = []

        def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record)
        try:
            (call or self.report)(**params)
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        return len([statement for statement in statements if "telemetry_events" in statement])


class AcceptedTests(ReportCase):
    """El contrato nuevo (DEV-55): 202 inmediato, sin tocar la base y con solo dos fechas en el mensaje."""

    hold = True

    def test_202_with_only_the_task_id(self) -> None:
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(set(body), {"task_id"})
        self.assertEqual(response.headers["location"], f"/tasks/{body['task_id']}")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_enqueueing_runs_no_query(self) -> None:
        self.assertEqual(self.queries(self.enqueue), 0)
        self.assertEqual(len(self.backend.sent), 1)

    def test_the_message_only_carries_start_and_end(self) -> None:
        self.enqueue(start_date="2026-11-01T10:00:00Z", end_date="2026-11-02T10:00:00Z")
        [(name, kwargs, _)] = self.backend.sent
        self.assertEqual(name, TELEMETRY_REPORT_TASK)
        self.assertEqual(kwargs, {"start": "2026-11-01T10:00:00.000Z", "end": "2026-11-02T10:00:00.000Z"})

    def test_the_task_is_pending_until_the_worker_runs_it(self) -> None:
        task_id = self.enqueue()
        self.assertEqual(self.task(task_id), {"task_id": task_id, "status": "pending", "result": None})
        self.backend.run(task_id)
        self.assertEqual(self.task(task_id)["status"], "success")

    def test_without_a_task_queue_is_503(self) -> None:
        self.app.state.task_queue = None  # type: ignore[attr-defined]
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "the task queue is not available", "code": "task_queue_unavailable"})

    def test_a_broker_failure_is_503_and_leaves_nothing_behind(self) -> None:
        self.backend.fail_sending = BrokerDown("Error 111 connecting to redis://:secret@redis:6379/0")
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "task_queue_unavailable")
        self.assertNotIn("secret", response.text)
        self.assertEqual(self.store.values, {})

    def test_validation_comes_before_the_queue(self) -> None:
        self.app.state.task_queue = None  # type: ignore[attr-defined]
        self.assertEqual(self.client.get(URL, params={"start_date": "2026-11-02", "end_date": "2026-11-01"}).status_code, 422)


class ShapeTests(ReportCase):
    def test_period_and_metrics(self) -> None:
        body = self.report()
        self.assertEqual(set(body), {"period", "metrics"})
        self.assertEqual(set(body["period"]), {"from", "to"})
        self.assertEqual(set(body["metrics"]), METRIC_KEYS)

    def test_default_window_is_the_last_seven_days_in_utc(self) -> None:
        before = datetime.now(UTC) - timedelta(seconds=1)
        period = self.report()["period"]
        start = datetime.fromisoformat(period["from"])
        end = datetime.fromisoformat(period["to"])
        self.assertEqual(end - start, timedelta(days=7))
        self.assertGreaterEqual(end, before)
        self.assertLessEqual(end, datetime.now(UTC))

    def test_period_uses_the_envelope_format(self) -> None:
        period = self.report(start_date="2026-11-01T10:00:00Z", end_date="2026-11-02T10:00:00Z")["period"]
        self.assertEqual(period, {"from": "2026-11-01T10:00:00.000Z", "to": "2026-11-02T10:00:00.000Z"})

    def test_a_report_without_rows_has_zero_days_and_empty_metrics(self) -> None:
        metrics = self.report(start_date="2026-11-01", end_date="2026-11-03")["metrics"]
        self.assertEqual(
            metrics["events_per_day"],
            [
                {"day": "2026-11-01", "service": "backoffice", "events": 0},
                {"day": "2026-11-01", "service": "api", "events": 0},
                {"day": "2026-11-02", "service": "backoffice", "events": 0},
                {"day": "2026-11-02", "service": "api", "events": 0},
            ],
        )
        self.assertEqual({key: value for key, value in metrics.items() if key != "events_per_day" and value}, {})

    def test_the_real_pipeline_end_to_end(self) -> None:
        moment = datetime(2026, 11, 1, 12, tzinfo=UTC)
        self.add("page_viewed", moment)
        self.add("form_submitted", moment, {"form": "login", "outcome": "api_rejected"})
        self.add("form_submitted", moment, {"form": "login", "outcome": "success"})
        self.add("page_load_recorded", moment, {"route_template": "/suppliers", "duration_ms": 120, "outcome": "data"})
        metrics = self.report(start_date="2026-11-01", end_date="2026-11-02")["metrics"]
        self.assertEqual(metrics["auth_failure_rate"], [{"day": "2026-11-01", "failed": 1, "succeeded": 1, "attempts": 2, "failure_rate": 0.5}])
        self.assertEqual(metrics["error_rate_by_type"][0]["error_type"], "form_submitted:api_rejected")
        self.assertEqual(metrics["error_rate_by_type"][0]["total_events"], 4)
        self.assertEqual(metrics["page_load_latency_by_route"][0]["max_ms"], 120)
        self.assertEqual(metrics["dominant_event_types"][0], {"event_type": "form_submitted", "service": "backoffice", "events": 2, "share": 0.5})

    def test_no_identifier_nor_business_value_reaches_the_response(self) -> None:
        moment = datetime(2026, 11, 1, 12, tzinfo=UTC)
        self.add("outbound_order_created", moment, {"office": "valencia", "currency": "EUR", "quantity": 3})
        task_id = self.enqueue(start_date="2026-11-01", end_date="2026-11-02")
        text = self.client.get(f"/tasks/{task_id}").text
        for fragment in ("user_id", "session_id", "event_id", "valencia", "EUR", "quantity"):
            self.assertNotIn(fragment, text)

    def test_no_metric_field_is_null(self) -> None:
        moment = datetime(2026, 11, 1, 12, tzinfo=UTC)
        self.add("client_request_failed", moment, {"suppressed_count": 1})
        self.add("form_submitted", moment, {"form": "login", "outcome": "api_rejected"})
        self.add("page_load_recorded", moment, {"route_template": "/suppliers", "duration_ms": 1, "outcome": "error"})
        metrics = self.report(start_date="2026-11-01", end_date="2026-11-02")["metrics"]
        self.assertNotIn("null", json.dumps(metrics))

    def test_the_period_is_resolved_once_and_passed_to_the_analysis(self) -> None:
        empty = dict.fromkeys(METRIC_KEYS, [])
        with patch("telemetry.analysis.all_metrics", return_value=empty) as analysis:
            period = self.report()["period"]
        analysis.assert_called_once()
        _, start, end = analysis.call_args.args
        self.assertEqual((iso_utc(start), iso_utc(end)), (period["from"], period["to"]))
        [(_, kwargs, _)] = self.backend.sent
        self.assertEqual(kwargs, {"start": period["from"], "end": period["to"]})


class ParameterTests(ReportCase):
    def period(self, **params: str) -> dict[str, str]:
        period: dict[str, str] = self.report(**params)["period"]
        return period

    def rejected(self, **params: str) -> dict[str, Any]:
        response = self.client.get(URL, params=params)
        self.assertEqual(response.status_code, 422, response.text)
        body: dict[str, Any] = response.json()
        self.assertEqual(body["code"], "validation_error")
        return body

    def test_a_date_without_zone_is_utc(self) -> None:
        period = self.period(start_date="2026-11-01", end_date="2026-11-02T06:30:00")
        self.assertEqual(period, {"from": "2026-11-01T00:00:00.000Z", "to": "2026-11-02T06:30:00.000Z"})

    def test_another_zone_is_converted_to_utc(self) -> None:
        period = self.period(start_date="2026-11-01T01:00:00+01:00", end_date="2026-11-01T20:00:00-05:00")
        self.assertEqual(period, {"from": "2026-11-01T00:00:00.000Z", "to": "2026-11-02T01:00:00.000Z"})

    def test_a_filter_in_another_zone_finds_the_same_rows(self) -> None:
        self.add("page_viewed", datetime(2026, 11, 1, 12, tzinfo=UTC))
        rows = self.report(start_date="2026-11-01T12:30:00+01:00", end_date="2026-11-01T13:30:00+01:00")["metrics"]["dominant_event_types"]
        self.assertEqual([row["events"] for row in rows], [1])

    def test_only_start_ends_now(self) -> None:
        start = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        period = self.period(start_date=start)
        self.assertAlmostEqual(datetime.fromisoformat(period["to"]).timestamp(), datetime.now(UTC).timestamp(), delta=5)

    def test_only_end_starts_seven_days_before(self) -> None:
        period = self.period(end_date="2026-10-20T00:00:00Z")
        self.assertEqual(period, {"from": "2026-10-13T00:00:00.000Z", "to": "2026-10-20T00:00:00.000Z"})

    def test_start_equal_to_end_is_rejected(self) -> None:
        body = self.rejected(start_date="2026-11-01T00:00:00Z", end_date="2026-11-01T00:00:00Z")
        self.assertEqual(body["detail"][0]["loc"], ["query", "start_date"])

    def test_start_after_end_is_rejected(self) -> None:
        self.rejected(start_date="2026-11-02", end_date="2026-11-01")

    def test_only_start_in_the_future_is_rejected(self) -> None:
        self.rejected(start_date=(datetime.now(UTC) + timedelta(days=1)).isoformat())

    def test_ninety_days_are_allowed_and_one_millisecond_more_is_not(self) -> None:
        self.report(start_date="2026-08-01T00:00:00Z", end_date="2026-10-30T00:00:00Z")
        self.rejected(start_date="2026-08-01T00:00:00Z", end_date="2026-10-30T00:00:00.001Z")

    def test_invalid_dates_are_rejected(self) -> None:
        for value in ("no-es-fecha", "2026-13-45T00:00:00Z", ""):
            with self.subTest(value=value):
                self.rejected(start_date=value)

    def test_a_rejected_period_enqueues_no_task(self) -> None:
        self.rejected(start_date="2026-11-02", end_date="2026-11-01")
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(self.store.values, {})


class ResolvePeriodTests(unittest.TestCase):
    def test_defaults(self) -> None:
        period = resolve_period(None, None, NOW)
        self.assertEqual(period.end, NOW.replace(microsecond=123000))
        self.assertEqual(period.end - period.start, DEFAULT_WINDOW)

    def test_the_limits_are_the_documented_ones(self) -> None:
        self.assertEqual((DEFAULT_WINDOW, MAX_WINDOW), (timedelta(days=7), timedelta(days=90)))

    def test_to_utc_truncates_to_milliseconds(self) -> None:
        self.assertEqual(to_utc(NOW).microsecond, 123000)

    def test_to_utc_accepts_naive_and_aware(self) -> None:
        naive = datetime(2026, 11, 1, 10)
        aware = datetime(2026, 11, 1, 11, tzinfo=timezone(timedelta(hours=1)))
        self.assertEqual(to_utc(naive), to_utc(aware))

    def test_iso_utc(self) -> None:
        self.assertEqual(iso_utc(to_utc(NOW)), "2026-11-05T12:00:00.123Z")

    def test_the_cache_key_never_contains_now(self) -> None:
        self.assertEqual(cache_key(None, None), (None, None))
        self.assertEqual(dedupe_scope(None, None), "-|-")


class AuthTests(ReportCase):
    def test_without_token_is_401(self) -> None:
        del self.client.headers["Authorization"]
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_with_an_invalid_token_is_401(self) -> None:
        self.client.headers["Authorization"] = "Bearer no-es-un-token"
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_a_dedupe_hit_does_not_skip_the_401(self) -> None:
        self.report()
        del self.client.headers["Authorization"]
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_any_role_can_read_it(self) -> None:
        for role in UserRole:
            with self.subTest(role=role):
                authorize(self.client, role)
                self.assertEqual(self.client.get(URL).status_code, 202)

    def test_the_collector_stays_public(self) -> None:
        del self.client.headers["Authorization"]
        self.assertEqual(self.client.post("/telemetry/events", json={"events": []}).status_code, 200)


class DedupeTests(ReportCase):
    """A4: sustituye a la caché de 60 s en memoria. Misma combinación del mismo usuario en 60 s → misma tarea."""

    def test_ttl_is_60_seconds_per_user(self) -> None:
        self.assertEqual(DEDUPE_TTL_SECONDS, 60)
        self.enqueue()
        [key] = [key for key in self.store.values if key.startswith(DEDUPE_PREFIX)]
        self.assertTrue(key.startswith(f"{DEDUPE_PREFIX}{TELEMETRY_REPORT_TASK}:"))
        self.assertTrue(key.endswith(":-|-"))
        self.assertEqual(self.store.ttl(key), 60)

    def test_the_default_window_dedupes_even_if_now_has_changed(self) -> None:
        self.assertEqual(self.queries(), 5)
        self.assertEqual(self.queries(), 0)
        self.assertEqual(len(self.backend.sent), 1)

    def test_a_hit_returns_the_same_task_and_the_same_report(self) -> None:
        first, second = self.enqueue(), self.enqueue()
        self.assertEqual(first, second)
        self.assertEqual(self.task(first), self.task(second))

    def test_within_the_ttl_new_rows_do_not_change_the_report(self) -> None:
        params = {"start_date": "2026-11-01", "end_date": "2026-11-02"}
        first = self.report(**params)
        self.add("page_viewed", datetime(2026, 11, 1, 12, tzinfo=UTC))
        self.assertEqual(self.report(**params), first)

    def test_it_recalculates_when_the_ttl_ends(self) -> None:
        self.assertEqual(self.queries(), 5)
        self.clock.now += DEDUPE_TTL_SECONDS - 0.001
        self.assertEqual(self.queries(), 0)
        self.clock.now += 0.001
        self.assertEqual(self.queries(), 5)

    def test_the_same_instants_in_another_format_hit(self) -> None:
        self.assertEqual(self.queries(start_date="2026-11-01T00:00:00Z", end_date="2026-11-02T00:00:00Z"), 5)
        self.assertEqual(self.queries(start_date="2026-11-01", end_date="2026-11-02T01:00:00+01:00"), 0)

    def test_another_combination_is_another_task(self) -> None:
        self.assertEqual(self.queries(start_date="2026-11-01", end_date="2026-11-02"), 5)
        self.assertEqual(self.queries(start_date="2026-11-01", end_date="2026-11-03"), 5)
        self.assertEqual(len({task_id for _, _, task_id in self.backend.sent}), 2)

    def test_another_user_gets_another_task(self) -> None:
        first = self.enqueue()
        authorize(self.client, UserRole.ADMIN)
        self.assertNotEqual(self.enqueue(), first)

    def test_a_failed_task_is_not_reused(self) -> None:
        failure = OperationalError("SELECT 1", {}, Exception("down"))
        with patch("telemetry.analysis.all_metrics", side_effect=failure):
            failed = self.enqueue()
        self.assertEqual(self.task(failed), {"task_id": failed, "status": "failure", "result": {"code": "task_failed", "detail": "the task failed"}})
        retried = self.enqueue()
        self.assertNotEqual(retried, failed)
        self.assertEqual(self.task(retried)["status"], "success")

    def test_the_collector_does_not_invalidate_the_report(self) -> None:
        self.report()
        self.client.post("/telemetry/events", json={"events": []})
        self.assertEqual(self.queries(), 0)


if __name__ == "__main__":
    unittest.main()
