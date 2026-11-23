"""Utilidades de los tests de task_queue (sin Redis ni PostgreSQL)."""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.pool import StaticPool

from task_queue.dead_letters import DeadLetter, DeadLetterRepository, build_table
from task_queue.errors import DeadLetterReason


def sqlite_repository() -> DeadLetterRepository:
    """La DLQ en SQLite en memoria, sin esquema (`ops` solo existe en PostgreSQL)."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda connection, _record: connection.execute("PRAGMA foreign_keys=ON"))
    metadata = MetaData()
    table = build_table(metadata, schema=None)
    metadata.create_all(engine)
    return DeadLetterRepository(engine, table)


def letter(task_id: str = "0f8f3c52-6f7e-4a52-9d0c-3e0c6c1f6a11", **overrides) -> DeadLetter:
    values = {
        "task_id": task_id,
        "task_name": "task_queue.example",
        "retries": 3,
        "max_retries": 3,
        "reason": DeadLetterReason.RETRIES_EXHAUSTED,
        "error_class": "OperationalError",
        "error_message": "OperationalError (QueryCanceled)",
        "task_kwargs": {"start": "2026-11-13T00:00:00.000Z", "end": "2026-11-20T00:00:00.000Z"},
        "queue": "nexova.tasks",
        "worker": "worker@test",
    }
    values.update(overrides)
    return DeadLetter(**values)
