"""Utilidades de los tests de `/reporting`: el esquema `reporting` en el SQLite de la app de test.

SQLite no tiene esquemas: se adjunta una base en memoria como `reporting`
(`ATTACH`) en la única conexión del motor de test (`StaticPool`). Las tablas
llevan las columnas que lee `services/reporting` (la DDL real, con sus `CHECK`,
la prueba `data/pipelines/tests/test_repository_postgres.py` en PostgreSQL).
Solo datos ficticios.
"""

import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from nexova_shared.reporting import last_closed_week
from sqlalchemy import Engine, text

RUNS_DDL = """
CREATE TABLE reporting.pipeline_runs (
  run_id TEXT PRIMARY KEY, pipeline_name TEXT NOT NULL, trigger TEXT NOT NULL, requested_by TEXT,
  prefect_flow_run_id TEXT, status TEXT NOT NULL, phase TEXT NOT NULL, week_from TEXT NOT NULL,
  week_to TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, source_rows_read INTEGER NOT NULL DEFAULT 0,
  rows_rejected INTEGER NOT NULL DEFAULT 0, duplicates_collapsed INTEGER NOT NULL DEFAULT 0,
  rows_upserted INTEGER NOT NULL DEFAULT 0, rows_deleted INTEGER NOT NULL DEFAULT 0,
  quality TEXT NOT NULL DEFAULT '{}', error_class TEXT, schema_version TEXT NOT NULL)
"""
WEEKLY_DDL = """
CREATE TABLE reporting.weekly_office_program_performance (
  id TEXT PRIMARY KEY, office TEXT NOT NULL, programme_id TEXT NOT NULL, week_start TEXT NOT NULL,
  total_material_cost NUMERIC NOT NULL DEFAULT 0, kits_delivered_count INTEGER NOT NULL DEFAULT 0,
  shortage_events_count INTEGER NOT NULL DEFAULT 0, cost_variance_events_count INTEGER NOT NULL DEFAULT 0,
  currency TEXT NOT NULL, computed_at TEXT NOT NULL, run_id TEXT NOT NULL,
  UNIQUE (office, programme_id, week_start))
"""

FAKE_PREFECT_URL = "http://prefect.invalid:4200/api"


def closed_week(weeks_back: int = 0) -> date:
    return last_closed_week(datetime.now(UTC)) - timedelta(weeks=weeks_back)


def engine_of(client: TestClient) -> Engine:
    engine = client.app.state.inventory_engine  # type: ignore[attr-defined]
    assert isinstance(engine, Engine)
    return engine


def attach_reporting(client: TestClient, *, tables: bool = True) -> None:
    with engine_of(client).begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS reporting")
        if tables:
            connection.exec_driver_sql(RUNS_DDL)
            connection.exec_driver_sql(WEEKLY_DDL)


def add_run(client: TestClient, *, week_from: date, week_to: date | None = None, status: str = "completed",
            started_at: datetime | None = None, requested_by: UUID | None = None, quality: dict | None = None) -> UUID:
    run_id = uuid4()
    started = started_at or datetime.now(UTC)
    with engine_of(client).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO reporting.pipeline_runs (run_id, pipeline_name, trigger, requested_by, prefect_flow_run_id, "
                "status, phase, week_from, week_to, started_at, finished_at, source_rows_read, rows_upserted, quality, "
                "schema_version) VALUES (:run_id, 'weekly_office_program_performance', 'manual', :requested_by, "
                ":flow_run, :status, :phase, :week_from, :week_to, :started, :finished, 4, 2, :quality, '1.0.0')"
            ),
            {
                "run_id": str(run_id),
                "requested_by": str(requested_by) if requested_by else None,
                "flow_run": str(uuid4()),
                "status": status,
                "phase": "done" if status == "completed" else "extract",
                "week_from": week_from.isoformat(),
                "week_to": (week_to or week_from).isoformat(),
                "started": started.isoformat(),
                "finished": None if status == "running" else started.isoformat(),
                "quality": json.dumps(quality or {"optional_steps": {"eval_snapshot": "completed"}}),
            },
        )
    return run_id


def add_row(client: TestClient, run_id: UUID, week: date, office: str, cost: str, kits: int = 0,
            shortage: int = 0, variance: int = 0, programme_id: str = "_unassigned") -> None:
    with engine_of(client).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO reporting.weekly_office_program_performance VALUES (:id, :office, :programme, :week, "
                ":cost, :kits, :shortage, :variance, :currency, :computed, :run_id)"
            ),
            {
                "id": str(uuid4()),
                "office": office,
                "programme": programme_id,
                "week": week.isoformat(),
                "cost": cost,
                "kits": kits,
                "shortage": shortage,
                "variance": variance,
                "currency": "EUR" if office == "valencia" else "USD",
                "computed": datetime.now(UTC).isoformat(),
                "run_id": str(run_id),
            },
        )
