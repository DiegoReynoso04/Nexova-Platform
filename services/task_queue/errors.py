"""Qué fallos se reintentan (A8) y la excepción que ve el exterior (A10, A12).

Solo se reintenta lo transitorio: los errores de la base que la API traduce a
`503 storage_unavailable` (también la cancelación por `statement_timeout`, que
psycopg2 entrega como `OperationalError`). Lo demás va directo a la DLQ.

`TaskFailedError` sustituye a la excepción original en el result backend de
Redis (y, por tanto, en Flower y en `GET /tasks/{id}`): lleva solo la clase y el
mensaje **ya redactados**, nunca un host, una URL ni una consulta.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (OperationalError, InterfaceError, PoolTimeoutError)


class DeadLetterReason(StrEnum):
    RETRIES_EXHAUSTED = "retries_exhausted"
    NON_RETRYABLE = "non_retryable"
    TIME_LIMIT = "time_limit"


class TaskFailedError(Exception):
    """Fallo de una tarea, sin datos sensibles. Serializable en JSON (dos cadenas)."""

    def __init__(self, error_class: str, message: str) -> None:
        super().__init__(error_class, message)
        self.error_class = error_class
        self.message = message

    def __str__(self) -> str:
        return self.message
