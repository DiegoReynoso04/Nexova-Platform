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

from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (OperationalError, InterfaceError, PoolTimeoutError)


def root_error(error: BaseException) -> BaseException:
    """El error de SQLAlchemy que hay debajo de `error`, si lo hay; si no, `error`.

    `pandas.read_sql` envuelve los errores de SQLAlchemy en su `pandas.errors.DatabaseError`
    (`raise DatabaseError(f"Execution failed on sql '...': {exc}") from exc`), con la SQL y
    sus parámetros en el mensaje. Sin desenvolverlo, una cancelación por `statement_timeout`
    no se reintentaría y la SQL llegaría al log y a la DLQ (hallazgo de la parada 3).
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, SQLAlchemyError):
            return current
        seen.add(id(current))
        current = current.__cause__
    return error


def is_retryable(error: BaseException) -> bool:
    return isinstance(root_error(error), RETRYABLE_EXCEPTIONS)


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
