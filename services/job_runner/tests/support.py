"""Utilidades de los tests: reloj falso, tabla en SQLite y filas insertadas a mano."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Engine, Uuid, bindparam, create_engine, text
from sqlalchemy.pool import StaticPool

from job_runner.migrate import index_statements
from job_runner.states import JobStatus

T0 = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)
DAY = date(2026, 11, 15)
JOB = "nightly_export"
TABLE = "job_runs"

# Espejo SQLite de CREATE_TABLE (migrate.py): los índices son los mismos, los de verdad.
SQLITE_DDL = f"""CREATE TABLE {TABLE} (
  id CHAR(32) PRIMARY KEY,
  job_name TEXT NOT NULL,
  target_date DATE NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_job_runs_finished CHECK ((status IN ('completed', 'failed')) = (finished_at IS NOT NULL)),
  CONSTRAINT ck_job_runs_error CHECK (error_message IS NULL OR status = 'failed')
)"""


def sqlite_engine() -> Engine:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(text(SQLITE_DDL))
        for statement in index_statements(TABLE).values():
            connection.execute(text(statement))
    return engine


class FakeClock:
    """Reloj que solo avanza cuando se le pide."""

    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


def insert_row(
    engine: Engine,
    table: str,
    *,
    status: JobStatus,
    job_name: str = JOB,
    target_date: date = DAY,
    started_at: datetime | None = None,
    created_at: datetime = T0,
    error_message: str | None = None,
) -> UUID:
    """Inserta una fila en el estado dado, saltándose la máquina de estados (para preparar casos)."""
    run_id = uuid4()
    finished_at = created_at if status in (JobStatus.COMPLETED, JobStatus.FAILED) else None
    if status in (JobStatus.PROCESSING, JobStatus.COMPLETED, JobStatus.FAILED) and started_at is None:
        started_at = created_at
    statement = text(
        f"INSERT INTO {table} (id, job_name, target_date, status, started_at, finished_at, error_message, created_at) "
        "VALUES (:id, :job_name, :target_date, :status, :started_at, :finished_at, :error_message, :created_at)"
    ).bindparams(
        bindparam("id", type_=Uuid(as_uuid=True)),
        bindparam("target_date", type_=Date()),
        bindparam("started_at", type_=DateTime(timezone=True)),
        bindparam("finished_at", type_=DateTime(timezone=True)),
        bindparam("created_at", type_=DateTime(timezone=True)),
    )
    with engine.begin() as connection:
        connection.execute(
            statement,
            {
                "id": run_id,
                "job_name": job_name,
                "target_date": target_date,
                "status": str(status),
                "started_at": started_at,
                "finished_at": finished_at,
                "error_message": error_message,
                "created_at": created_at,
            },
        )
    return run_id


# --- El script nocturno (scripts/nightly_export.py) -------------------------------------------

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts"


def load_script():
    """`nightly_export` importado desde `scripts/` (no es un paquete)."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import nightly_export

    return nightly_export


EVENTS_DDL = """CREATE TABLE telemetry_events (
  event_id CHAR(36) PRIMARY KEY, event_type TEXT NOT NULL, timestamp TIMESTAMP NOT NULL,
  service TEXT NOT NULL, user_id CHAR(36), session_id CHAR(36), schema_version TEXT NOT NULL, tags TEXT NOT NULL
)"""


def events_engine():
    engine = sqlite_engine()
    with engine.begin() as connection:
        connection.execute(text(EVENTS_DDL))
    return engine


def insert_event(engine, event_id, moment, tags, *, event_type="page_viewed", user_id=None, session_id=None):
    import json

    statement = text(
        "INSERT INTO telemetry_events (event_id, event_type, timestamp, service, user_id, session_id, schema_version, tags) "
        "VALUES (:id, :type, :ts, 'backoffice', :user_id, :session_id, '1.0.0', :tags)"
    ).bindparams(bindparam("ts", type_=DateTime(timezone=True)))
    with engine.begin() as connection:
        connection.execute(
            statement,
            {"id": event_id, "type": event_type, "ts": moment, "user_id": user_id, "session_id": session_id, "tags": json.dumps(tags)},
        )
