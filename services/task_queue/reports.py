"""El reporte técnico de telemetría, calculado en el worker (A1, A3).

La API resuelve el periodo (`resolve_period`: 7 días por defecto, UTC, ≤ 90 días) y
encola solo `start` y `end` ya resueltos, en el formato del envelope
(`2026-11-05T12:00:00.000Z`). Aquí se leen de `telemetry_events` con las mismas
métricas de siempre (`services/telemetry/analysis.py`, sin cambios) y se devuelve la
misma forma que respondía `GET /telemetry/report`: `{"period": {"from", "to"}, "metrics"}`.

La consulta va en una transacción con `SET LOCAL statement_timeout` (A7, A13).
Importar `telemetry.analysis` carga Pandas y el modelo de la tabla
(`app.modules.telemetry.models`, SQLModel): nada de FastAPI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine

from .config import statement_timeout_ms
from .database import transaction

ENVELOPE_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def parse_envelope_instant(value: str) -> datetime:
    """`2026-11-05T12:00:00.000Z` → datetime en UTC. Cualquier otra forma, `ValueError` (no se reintenta)."""
    if not isinstance(value, str) or len(value) != 24 or not value.endswith("Z"):
        raise ValueError("start and end must use the envelope format YYYY-MM-DDTHH:MM:SS.mmmZ")
    return datetime.strptime(value, ENVELOPE_FORMAT).replace(tzinfo=UTC)


def build_telemetry_report(engine: Engine, start: str, end: str, *, timeout_ms: int | None = None) -> dict[str, Any]:
    start_at, end_at = parse_envelope_instant(start), parse_envelope_instant(end)
    if start_at >= end_at:
        raise ValueError("start must be earlier than end")
    from telemetry.analysis import all_metrics  # Pandas y el modelo de la tabla, solo al calcular
    with transaction(engine, timeout_ms if timeout_ms is not None else statement_timeout_ms()) as connection:
        metrics = all_metrics(connection, start_at, end_at)
    return {"period": {"from": start, "to": end}, "metrics": metrics}
