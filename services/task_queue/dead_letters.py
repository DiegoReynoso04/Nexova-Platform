"""Dead Letter Queue (A9): `ops.task_dead_letters`, solo registro.

Una fila por tarea que termina en fallo definitivo (reintentos agotados, error no
reintentable o límite de tiempo). `task_id` es único: con `acks_late`, un mismo
fallo definitivo puede llegar dos veces y el segundo `INSERT` no hace nada
(`ON CONFLICT DO NOTHING`). `attempt` = `retries` + 1 (con `max_retries=3`, la fila
de unos reintentos agotados lleva `attempt=4` y `retries=3`).

**Si la base no está disponible al registrar** (o la tabla no existe todavía: la
demo no tiene el esquema `ops` hasta que el usuario la migre), un reintento corto
y, si vuelve a fallar, una línea `ERROR` con todos los campos de la fila
(`status=dead_letter_not_stored`). La tarea termina igual en `FAILURE`.

La tabla la crea `python -m task_queue.migrate`, nunca el worker.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, Engine, Integer, MetaData, String, Table, Text, Uuid, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.types import DateTime

from .config import DEAD_LETTER_RETRY_DELAY_SECONDS, DEAD_LETTER_STATEMENT_TIMEOUT_MS, ERROR_MESSAGE_MAX_CHARS
from .database import ConfigError, get_engine, transaction
from .errors import DeadLetterReason
from .logs import log_task

SCHEMA = "ops"
TABLE = "task_dead_letters"
QUALIFIED_TABLE = f"{SCHEMA}.{TABLE}"
FAILED_AT_INDEX = "ix_task_dead_letters_failed_at"
TASK_ID_UNIQUE = "uq_task_dead_letters_task_id"

_TRANSIENT = (OperationalError, InterfaceError, PoolTimeoutError)


def build_table(metadata: MetaData, schema: str | None = SCHEMA) -> Table:
    """La tabla como la crea la migración (los tests de SQLite la crean sin esquema)."""
    return Table(
        TABLE,
        metadata,
        # BIGSERIAL en PostgreSQL; en SQLite, INTEGER PRIMARY KEY (el único que autoincrementa).
        Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
        Column("task_id", Uuid(as_uuid=False), nullable=False, unique=True),
        Column("task_name", String(200), nullable=False),
        Column("attempt", Integer, nullable=False),
        Column("retries", Integer, nullable=False),
        Column("max_retries", Integer, nullable=False),
        Column("reason", String(32), nullable=False),
        Column("error_class", String(200), nullable=False),
        Column("error_message", Text, nullable=False),
        Column("task_kwargs", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        Column("queue", String(100)),
        Column("worker", String(100)),
        Column("failed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint("attempt >= 1", name="ck_task_dead_letters_attempt_positive"),
        CheckConstraint("retries >= 0", name="ck_task_dead_letters_retries_non_negative"),
        CheckConstraint("attempt = retries + 1", name="ck_task_dead_letters_attempt_retries"),
        CheckConstraint(
            "reason IN ('retries_exhausted', 'non_retryable', 'time_limit')", name="ck_task_dead_letters_reason"
        ),
        schema=schema,
    )


DEAD_LETTERS = build_table(MetaData())


@dataclass(frozen=True, slots=True)
class DeadLetter:
    task_id: str
    task_name: str
    retries: int
    max_retries: int
    reason: DeadLetterReason
    error_class: str
    error_message: str
    task_kwargs: dict[str, Any] = field(default_factory=dict)
    queue: str | None = None
    worker: str | None = None

    @property
    def attempt(self) -> int:
        """Ejecuciones, contando la primera (1-based)."""
        return self.retries + 1

    def row(self) -> dict[str, Any]:
        values = asdict(self)
        values["reason"] = str(self.reason)
        values["attempt"] = self.attempt
        values["error_message"] = self.error_message[:ERROR_MESSAGE_MAX_CHARS]
        return values


class DeadLetterRepository:
    def __init__(self, engine: Engine, table: Table = DEAD_LETTERS) -> None:
        self.engine = engine
        self.table = table

    def record(self, letter: DeadLetter) -> bool:
        """`True` si la fila es nueva; `False` si ese `task_id` ya estaba."""
        insert = postgresql_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        statement = insert(self.table).values(**letter.row()).on_conflict_do_nothing(index_elements=["task_id"])
        with transaction(self.engine, DEAD_LETTER_STATEMENT_TIMEOUT_MS) as connection:
            return connection.execute(statement).rowcount == 1

    def list(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(select(self.table).order_by(self.table.c.id)).mappings()]


def _letter_fields(letter: DeadLetter) -> dict[str, Any]:
    return {
        "reason": str(letter.reason),
        "retries": letter.retries,
        "max_retries": letter.max_retries,
        "error_class": letter.error_class,
        "error": letter.error_message,
        "task_kwargs": letter.task_kwargs,
        "queue": letter.queue,
        "worker": letter.worker,
    }


def record_dead_letter(
    letter: DeadLetter,
    *,
    repository: DeadLetterRepository | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Registra la fila. Nunca lanza: si no puede, lo deja en el log con todos los campos."""
    base = {"task_id": letter.task_id, "task": letter.task_name, "attempt": letter.attempt, "total": letter.max_retries + 1}
    failure: str
    try:
        repository = repository if repository is not None else DeadLetterRepository(get_engine())
    except ConfigError:
        failure = "ConfigError"
    else:
        for try_number in (1, 2):
            try:
                inserted = repository.record(letter)
            except _TRANSIENT as error:
                failure = type(error).__name__
                if try_number == 1:
                    sleep(DEAD_LETTER_RETRY_DELAY_SECONDS)
                    continue
            except SQLAlchemyError as error:  # p. ej. ProgrammingError: la tabla no existe
                failure = type(error).__name__
            else:
                log_task(logging.INFO, **base, status="dead_letter_stored", duplicate=not inserted, table=QUALIFIED_TABLE)
                return True
            break
    log_task(logging.ERROR, **base, status="dead_letter_not_stored", cause=failure, **_letter_fields(letter))
    return False
