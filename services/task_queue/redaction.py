"""Mensajes de error y logs sin secretos (A12): la redacción de `job_runner.redact`.

- `describe_failure` da la clase y el «mensaje completo» de un fallo: de un error
  de SQLAlchemy, solo las clases (su mensaje lleva SQL y datos de conexión); del
  resto, `Clase: mensaje` sin URL con esquema ni valores secretos, truncado a
  `ERROR_MESSAGE_MAX_CHARS`.
- `RedactingFilter` aplica la misma redacción al mensaje y a la traza de los
  registros de los loggers de Celery que escriben excepciones (`celery.app.trace`,
  `celery.worker.request`) y del propio `task_queue`.

`job_runner.redact` ya cubre `DATABASE_URL`, `JWT_SECRET_KEY`, `RESEND_API_KEY` y
`TELEMETRY_SUPPLIER_KEY`; aquí se añaden los secretos de la cola (`REDIS_URL`,
`REDIS_PASSWORD`, `FLOWER_BASIC_AUTH`) sin tocar `job_runner`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from job_runner.redact import redact
from sqlalchemy.exc import SQLAlchemyError

from .config import ERROR_MESSAGE_MAX_CHARS
from .errors import root_error

QUEUE_SECRET_VARIABLES = ("REDIS_URL", "REDIS_PASSWORD", "FLOWER_BASIC_AUTH")
REDACTED_LOGGERS = ("celery.app.trace", "celery.worker.request", "task_queue")
_MIN_SECRET_LENGTH = 4


def queue_secrets(environ: Mapping[str, str]) -> list[str]:
    """Los valores secretos de la cola: las variables enteras y la contraseña de cada una."""
    values: set[str] = set()
    for name in QUEUE_SECRET_VARIABLES:
        value = (environ.get(name) or "").strip()
        if len(value) < _MIN_SECRET_LENGTH:
            continue
        values.add(value)
        password: str | None = None
        if "://" in value:
            try:
                password = urlsplit(value).password
            except ValueError:
                password = None
        elif ":" in value:  # FLOWER_BASIC_AUTH = usuario:contraseña
            password = value.split(":", 1)[1]
        if password and len(password) >= _MIN_SECRET_LENGTH:
            values.add(password)
    return sorted(values, key=len, reverse=True)


def redact_text(text: str, environ: Mapping[str, str] | None = None) -> str:
    environ = os.environ if environ is None else environ
    return redact(text, environ=environ, extra=queue_secrets(environ))


def describe_failure(error: BaseException, environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    """`(clase, mensaje)` del fallo, listos para el log, la DLQ y el result backend.

    Un error de SQLAlchemy envuelto (p. ej. por `pandas.read_sql`) se describe por el
    original: solo sus clases, nunca la SQL ni los parámetros del envoltorio.
    """
    error = root_error(error)
    error_class = type(error).__name__
    if isinstance(error, SQLAlchemyError):
        origin = getattr(error, "orig", None)
        message = error_class + (f" ({type(origin).__name__})" if origin is not None else "")
    else:
        text = " ".join(str(error).split())
        message = redact_text(f"{error_class}: {text}" if text else error_class, environ)
    return error_class, message[:ERROR_MESSAGE_MAX_CHARS]


class RedactingFilter(logging.Filter):
    """Redacta el mensaje ya formateado y la traza de cada registro. Nunca descarta uno."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # un registro mal formado no debe romper el log
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True


def install_redacting_filter() -> None:
    """Idempotente: un filtro por logger, aunque el módulo se importe varias veces."""
    for name in REDACTED_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(existing, RedactingFilter) for existing in logger.filters):
            logger.addFilter(RedactingFilter())
