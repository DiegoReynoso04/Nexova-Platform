"""Utilidades de test del pipeline. Solo datos ficticios.

`InMemoryRepository` imita lo que garantiza la SQL de `repository.py`: una
sola corrida `running` por pipeline, `ON CONFLICT (run_id) DO NOTHING`, upsert
por (`office`, `programme_id`, `week_start`) y borrado de huérfanas en las
semanas recalculadas, todo o nada. La SQL real se prueba contra un Postgres
local en `test_repository_postgres.py` (si hay uno configurado).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from business_performance.repository import RunInProgressError
from weekly_performance import ExtractedEvent, QualityCounts, WeeklyRow, last_closed_week, week_start_of

_order_ids = itertools.count(1000)


def closed_week(weeks_back: int = 0) -> date:
    """El lunes de la última semana cerrada (hoy, en UTC), o `weeks_back` semanas antes."""
    return last_closed_week(datetime.now(UTC)) - timedelta(weeks=weeks_back)


def fake_event(event_type: str = "outbound_order_created", *, week: date | None = None, office: str = "valencia",
               quantity: str = "1", unit_cost: str | None = None, order_id: str | None = None,
               hour: int = 9) -> ExtractedEvent:
    week = week or closed_week()
    return ExtractedEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        timestamp=datetime(week.year, week.month, week.day, hour, tzinfo=UTC) + timedelta(days=1),
        office=office,
        programme_id=None,
        currency="EUR" if office == "valencia" else "USD",
        quantity=quantity,
        unit_cost=unit_cost,
        order_id=order_id or str(next(_order_ids)),
    )


@dataclass
class InMemoryRepository:
    events: list[ExtractedEvent] = field(default_factory=list)
    quality: QualityCounts = field(default_factory=QualityCounts)
    runs: dict[UUID, dict] = field(default_factory=dict)
    table: dict[tuple[str, str, date], dict] = field(default_factory=dict)
    # Inyección de fallos en la carga: excepciones a lanzar en los próximos intentos.
    load_failures: list[BaseException] = field(default_factory=list)
    load_attempts: int = 0

    def schema_ready(self) -> bool:
        return True

    def start_run(self, run_id, trigger, requested_by, prefect_flow_run_id, week_from, week_to) -> None:
        if run_id in self.runs:  # ON CONFLICT (run_id) DO NOTHING
            if self.runs[run_id]["status"] != "running":
                raise RunInProgressError()
            return
        if any(run["status"] == "running" for run in self.runs.values()):
            raise RunInProgressError()
        self.runs[run_id] = {
            "trigger": trigger,
            "requested_by": requested_by,
            "prefect_flow_run_id": prefect_flow_run_id,
            "status": "running",
            "phase": "extract",
            "week_from": week_from,
            "week_to": week_to,
            "started_at": datetime.now(UTC),
        }

    def mark_phase(self, run_id, phase) -> None:
        if self.runs[run_id]["status"] == "running":
            self.runs[run_id]["phase"] = phase

    def finish_run(self, run_id, **fields) -> None:
        run = self.runs[run_id]
        if run["status"] == "running":
            run.update(fields, finished_at=datetime.now(UTC))

    def extract_business_events(self, window_start, window_end) -> list[ExtractedEvent]:
        selected = [event for event in self.events if window_start <= event.timestamp < window_end]
        return sorted(selected, key=lambda event: (event.timestamp, event.event_id))

    def extract_quality_counts(self, window_start, window_end) -> QualityCounts:
        return self.quality

    def load_weekly_rows(self, rows: tuple[WeeklyRow, ...], week_from, week_to, run_id) -> tuple[int, int]:
        self.load_attempts += 1
        if self.load_failures:
            raise self.load_failures.pop(0)  # la transacción se deshace: nada cambia
        new = {(row.office, row.programme_id, row.week_start): row for row in rows}
        orphans = [key for key in self.table if week_from <= key[2] <= week_to and key not in new]
        for key in orphans:
            del self.table[key]
        for key, row in new.items():
            self.table[key] = {"row": row, "run_id": run_id, "computed_at": datetime.now(UTC)}
        return len(new), len(orphans)


def week_of(event: ExtractedEvent) -> date:
    return week_start_of(event.timestamp)
