"""Crear, actualizar y consultar `ops.job_runs` (DEV-53, apartados B y C del análisis).

SQL portable con `text()`: sin ORM y sin funciones de la base. Las marcas de
tiempo las pone Python (UTC) y los parámetros llevan su tipo, así que el mismo
código corre sobre PostgreSQL y, en los tests unitarios, sobre SQLite.

**El estado `processing` es el lock** (sin tabla, columna ni flag aparte): el
índice único parcial `ux_job_runs_one_processing` hace que la base rechace, en el
mismo `UPDATE`, al segundo que intenta pasar a `processing`. Todas las
transiciones son *compare-and-set* sobre `status` y devuelven si afectaron a una
fila. Cada método abre su propia transacción.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Engine, String, Uuid, bindparam, inspect, text
from sqlalchemy.exc import IntegrityError

from .states import (
    ABANDONED_PENDING_MESSAGE,
    ABANDONED_PROCESSING_MESSAGE,
    QUALIFIED_TABLE,
    STALE_PENDING_MINUTES,
    STALE_PROCESSING_MINUTES,
    JobStatus,
)

_TABLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")
_ID = Uuid(as_uuid=True)
_TIMESTAMP = DateTime(timezone=True)


class JobRunStateError(Exception):
    """La fila no estaba en el estado esperado (la barrió otro proceso o no existe)."""


class AlreadyCompletedError(Exception):
    """Ya hay una fila `completed` para ese job y día (`ux_job_runs_one_completed_per_day`)."""


@dataclass(frozen=True, slots=True)
class JobRun:
    id: UUID
    job_name: str
    target_date: date
    status: JobStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    created_at: datetime


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _typed(sql: str, **types):
    statement = text(sql)
    return statement.bindparams(*(bindparam(name, type_=kind) for name, kind in types.items()))


class JobRunRepository:
    """E/S de `job_runs`. `engine` y, en los tests, `table` los pone quien llama."""

    def __init__(self, engine: Engine, table: str = QUALIFIED_TABLE) -> None:
        if not _TABLE_NAME.match(table):
            raise ValueError("invalid table name")
        self.engine = engine
        self.table = table

    def schema_ready(self) -> bool:
        schema, _, name = self.table.rpartition(".")
        return bool(inspect(self.engine).has_table(name, schema=schema or None))

    # --- Escritura -----------------------------------------------------------

    def create_job_run(self, job_name: str, target_date: date, now: datetime) -> JobRun:
        """Inserta una fila `pending` (commit propio, visible para las demás instancias)."""
        run_id = uuid4()
        statement = _typed(
            f"INSERT INTO {self.table} (id, job_name, target_date, status, created_at) "
            f"VALUES (:id, :job_name, :target_date, '{JobStatus.PENDING}', :now)",
            id=_ID,
            target_date=Date(),
            now=_TIMESTAMP,
        )
        with self.engine.begin() as connection:
            connection.execute(
                statement, {"id": run_id, "job_name": job_name, "target_date": target_date, "now": now}
            )
        return JobRun(run_id, job_name, target_date, JobStatus.PENDING, None, None, None, now)

    def claim(self, run_id: UUID, now: datetime) -> bool:
        """`pending` → `processing`. `False` si otra instancia ya tiene el lock.

        Solo el índice único parcial de `processing` puede chocar aquí (el
        `UPDATE` solo cambia `status` y `started_at`), así que cualquier
        `IntegrityError` es «lock tomado».
        """
        statement = _typed(
            f"UPDATE {self.table} SET status = '{JobStatus.PROCESSING}', started_at = :now "
            f"WHERE id = :id AND status = '{JobStatus.PENDING}'",
            id=_ID,
            now=_TIMESTAMP,
        )
        try:
            with self.engine.begin() as connection:
                updated = connection.execute(statement, {"id": run_id, "now": now}).rowcount
        except IntegrityError:
            return False
        if updated != 1:
            raise JobRunStateError("the run is not pending")
        return True

    def complete(self, run_id: UUID, now: datetime) -> bool:
        """`processing` → `completed`. `False` si la fila ya no estaba en `processing` (lock perdido)."""
        statement = _typed(
            f"UPDATE {self.table} SET status = '{JobStatus.COMPLETED}', finished_at = :now "
            f"WHERE id = :id AND status = '{JobStatus.PROCESSING}'",
            id=_ID,
            now=_TIMESTAMP,
        )
        try:
            with self.engine.begin() as connection:
                return connection.execute(statement, {"id": run_id, "now": now}).rowcount == 1
        except IntegrityError:
            raise AlreadyCompletedError() from None

    def fail(self, run_id: UUID, message: str, now: datetime) -> bool:
        """`pending` o `processing` → `failed`, con el mensaje. `False` si la fila ya estaba cerrada."""
        statement = _typed(
            f"UPDATE {self.table} SET status = '{JobStatus.FAILED}', finished_at = :now, error_message = :message "
            f"WHERE id = :id AND status IN ('{JobStatus.PENDING}', '{JobStatus.PROCESSING}')",
            id=_ID,
            now=_TIMESTAMP,
        )
        with self.engine.begin() as connection:
            return connection.execute(statement, {"id": run_id, "now": now, "message": message}).rowcount == 1

    def discard(self, run_id: UUID) -> bool:
        """Borra una fila propia que **no ejecutó nada** (perdió el lock o resultó duplicada).

        Es el único `DELETE` del job: solo `pending` o `processing` (nunca una
        cerrada) y solo por su id.
        """
        statement = _typed(
            f"DELETE FROM {self.table} WHERE id = :id "
            f"AND status IN ('{JobStatus.PENDING}', '{JobStatus.PROCESSING}')",
            id=_ID,
        )
        with self.engine.begin() as connection:
            return connection.execute(statement, {"id": run_id}).rowcount == 1

    def sweep_stale(self, job_name: str, now: datetime) -> int:
        """Cierra como `failed` las filas abandonadas. Devuelve cuántas.

        `processing` con más de `STALE_PROCESSING_MINUTES` y `pending` con más
        de `STALE_PENDING_MINUTES`: el proceso murió sin pasar por su `finally`
        (kill -9, reinicio, caída de la base).
        """
        total = 0
        for status, column, minutes, message in (
            (JobStatus.PROCESSING, "started_at", STALE_PROCESSING_MINUTES, ABANDONED_PROCESSING_MESSAGE),
            (JobStatus.PENDING, "created_at", STALE_PENDING_MINUTES, ABANDONED_PENDING_MESSAGE),
        ):
            statement = _typed(
                f"UPDATE {self.table} SET status = '{JobStatus.FAILED}', finished_at = :now, error_message = :message "
                f"WHERE job_name = :job_name AND status = '{status}' AND {column} < :cutoff",
                now=_TIMESTAMP,
                cutoff=_TIMESTAMP,
            )
            with self.engine.begin() as connection:
                total += connection.execute(
                    statement,
                    {"now": now, "cutoff": now - timedelta(minutes=minutes), "message": message, "job_name": job_name},
                ).rowcount
        return total

    # --- Lectura -------------------------------------------------------------

    def has_processing_lock(self, job_name: str) -> bool:
        """¿Hay una fila `processing` de este job? Informativa: la garantía es el índice único."""
        statement = text(
            f"SELECT 1 FROM {self.table} WHERE job_name = :job_name AND status = '{JobStatus.PROCESSING}' LIMIT 1"
        )
        with self.engine.connect() as connection:
            return connection.execute(statement, {"job_name": job_name}).first() is not None

    def has_completed_for_date(self, job_name: str, target_date: date) -> bool:
        statement = _typed(
            f"SELECT 1 FROM {self.table} WHERE job_name = :job_name AND target_date = :target_date "
            f"AND status = '{JobStatus.COMPLETED}' LIMIT 1",
            target_date=Date(),
        )
        with self.engine.connect() as connection:
            return connection.execute(statement, {"job_name": job_name, "target_date": target_date}).first() is not None

    def get_job_run(self, run_id: UUID) -> JobRun | None:
        rows = self._select("WHERE id = :id", {"id": run_id}, id=_ID)
        return rows[0] if rows else None

    def list_job_runs(self, job_name: str, target_date: date | None = None) -> list[JobRun]:
        """Las filas de un job (y día, si se da), de la más antigua a la más reciente."""
        if target_date is None:
            return self._select("WHERE job_name = :job_name", {"job_name": job_name})
        return self._select(
            "WHERE job_name = :job_name AND target_date = :target_date",
            {"job_name": job_name, "target_date": target_date},
            target_date=Date(),
        )

    def _select(self, where: str, params: dict[str, object], **types) -> list[JobRun]:
        statement = _typed(
            "SELECT id, job_name, target_date, status, started_at, finished_at, error_message, created_at "
            f"FROM {self.table} {where} ORDER BY created_at, id",
            **types,
        ).columns(
            id=_ID,
            job_name=String(),
            target_date=Date(),
            status=String(),
            started_at=_TIMESTAMP,
            finished_at=_TIMESTAMP,
            error_message=String(),
            created_at=_TIMESTAMP,
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement, params).all()
        return [
            JobRun(
                id=row.id,
                job_name=row.job_name,
                target_date=row.target_date,
                status=JobStatus(row.status),
                started_at=_aware(row.started_at),
                finished_at=_aware(row.finished_at),
                error_message=row.error_message,
                created_at=_aware(row.created_at),
            )
            for row in rows
        ]
