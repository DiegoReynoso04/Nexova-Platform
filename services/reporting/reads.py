"""Lecturas del esquema `reporting` (solo `SELECT`; lo escribe el pipeline, nunca la API).

SQL de texto con parámetros, válida en PostgreSQL y en el SQLite de los tests
(`ATTACH … AS reporting`). Las fechas viajan como texto ISO, que PostgreSQL
convierte al tipo de la columna y SQLite compara como texto.
"""

import json
from datetime import date, datetime, timedelta
from typing import Any

from nexova_shared.reporting import (
    ABANDONED_AFTER_MINUTES,
    PIPELINE_NAME,
    QUALIFIED_RUNS_TABLE,
    QUALIFIED_WEEKLY_TABLE,
    RunStatus,
)
from sqlalchemy import text
from sqlalchemy.engine import Connection

_RUN_COLUMNS = (
    "run_id, pipeline_name, trigger, prefect_flow_run_id, status, phase, week_from, week_to, started_at, "
    "finished_at, source_rows_read, rows_rejected, duplicates_collapsed, rows_upserted, rows_deleted, quality, "
    "error_class, schema_version"
)  # sin requested_by: nunca sale por la API

_LATEST_RUN = text(
    f"SELECT {_RUN_COLUMNS} FROM {QUALIFIED_RUNS_TABLE} WHERE pipeline_name = :pipeline "
    "ORDER BY started_at DESC LIMIT 1"
)
# La semana más reciente cubierta por una corrida completada (no la mayor de la
# tabla, que no ve las semanas calculadas sin actividad).
_LATEST_COMPUTED_WEEK = text(
    f"SELECT week_to FROM {QUALIFIED_RUNS_TABLE} WHERE pipeline_name = :pipeline AND status = :completed "
    "ORDER BY week_to DESC LIMIT 1"
)
_WEEK_COMPUTED = text(
    f"SELECT 1 FROM {QUALIFIED_RUNS_TABLE} WHERE pipeline_name = :pipeline AND status = :completed "
    "AND week_from <= :week AND week_to >= :week LIMIT 1"
)
_WEEK_ROWS = text(
    "SELECT office, programme_id, total_material_cost, kits_delivered_count, shortage_events_count, "
    f"cost_variance_events_count, currency FROM {QUALIFIED_WEEKLY_TABLE} WHERE week_start = :week "
    "ORDER BY office, programme_id"
)
# Una corrida `running` reciente bloquea un disparo nuevo; una más vieja la
# cerrará la siguiente corrida como abandonada (§3.4 del diseño).
_RUNNING = text(
    f"SELECT 1 FROM {QUALIFIED_RUNS_TABLE} WHERE pipeline_name = :pipeline AND status = :running "
    "AND started_at >= :cutoff LIMIT 1"
)


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def latest_run(connection: Connection) -> dict[str, Any] | None:
    row = connection.execute(_LATEST_RUN, {"pipeline": PIPELINE_NAME}).mappings().first()
    if row is None:
        return None
    run = dict(row)
    if isinstance(run["quality"], str):  # jsonb en PostgreSQL; texto en SQLite
        run["quality"] = json.loads(run["quality"])
    return run


def latest_computed_week(connection: Connection) -> date | None:
    value = connection.execute(
        _LATEST_COMPUTED_WEEK, {"pipeline": PIPELINE_NAME, "completed": RunStatus.COMPLETED.value}
    ).scalar()
    return None if value is None else _as_date(value)


def week_is_computed(connection: Connection, week: date) -> bool:
    params = {"pipeline": PIPELINE_NAME, "completed": RunStatus.COMPLETED.value, "week": week.isoformat()}
    return connection.execute(_WEEK_COMPUTED, params).first() is not None


def week_rows(connection: Connection, week: date) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(_WEEK_ROWS, {"week": week.isoformat()}).mappings()]


def has_running_run(connection: Connection, now: datetime) -> bool:
    cutoff = (now - timedelta(minutes=ABANDONED_AFTER_MINUTES)).isoformat()
    params = {"pipeline": PIPELINE_NAME, "running": RunStatus.RUNNING.value, "cutoff": cutoff}
    return connection.execute(_RUNNING, params).first() is not None
