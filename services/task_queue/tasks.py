"""Tareas del worker. Los nombres son explícitos (`names.py`): la API las envía por
nombre (`client.TaskQueueClient`), sin importar este módulo.

Cada mensaje lleva solo referencias (C8): `task_queue.telemetry_report` recibe
`start` y `end` (dos fechas ISO); el worker lee `telemetry_events` él mismo.
"""

from __future__ import annotations

from typing import Any

from .celery_app import app
from .database import get_engine
from .names import PING_TASK, TELEMETRY_REPORT_TASK

__all__ = ["PING_TASK", "TELEMETRY_REPORT_TASK", "ping", "telemetry_report"]


@app.task(name=PING_TASK)
def ping() -> str:
    """Tarea trivial: responde `pong`. Sin argumentos, sin base de datos."""
    return "pong"


@app.task(name=TELEMETRY_REPORT_TASK)
def telemetry_report(start: str, end: str) -> dict[str, Any]:
    """`GET /telemetry/report` (A1): las 5 métricas técnicas del periodo `[start, end)`."""
    from .reports import build_telemetry_report

    return build_telemetry_report(get_engine(), start, end)
