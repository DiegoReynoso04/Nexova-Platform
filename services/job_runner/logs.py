"""Formato del log del job (apartado H del análisis).

Una línea por evento, con marca de tiempo UTC, nivel, job y estado:

    2026-11-16T02:00:34Z INFO job=nightly_export status=completed target_date=2026-11-15 run=<uuid> finished

`status` es el estado resultante (`pending`/`processing`/`completed`/`failed`)
o, solo en el log, `skipped`/`locked`. Toda línea pasa por `redact` antes de salir.
"""

import logging
import sys
import time
from datetime import date
from typing import TextIO
from uuid import UUID

from .redact import redact

LOGGER_NAME = "job_runner"


class RedactingUtcFormatter(logging.Formatter):
    converter = time.gmtime

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")

    def format(self, record: logging.LogRecord) -> str:
        # Sin trazas: el mensaje de una excepción ya viene descrito y redactado por quien registra.
        return redact(super().format(record))


def configure_logging(stream: TextIO | None = None, *, level: int = logging.INFO) -> logging.Logger:
    """El logger del job a stdout (o `stream`), sin duplicar manejadores si se llama dos veces."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(RedactingUtcFormatter())
    logger.addHandler(handler)
    return logger


class JobLogger:
    """Construye las líneas `job=… status=… target_date=… [run=…] mensaje`."""

    def __init__(self, logger: logging.Logger, job_name: str, target_date: date | None) -> None:
        self._logger = logger
        self._job_name = job_name
        self._target_date = target_date

    def _line(self, status: str, message: str, run_id: UUID | None, fields: dict[str, object]) -> str:
        parts = [f"job={self._job_name}", f"status={status}", f"target_date={self._target_date.isoformat() if self._target_date else '-'}"]
        if run_id is not None:
            parts.append(f"run={run_id}")
        parts.append(message)
        parts.extend(f"{key}={value}" for key, value in fields.items())
        return " ".join(parts)

    def info(self, status: str, message: str, run_id: UUID | None = None, **fields: object) -> None:
        self._logger.info(self._line(status, message, run_id, fields))

    def error(self, status: str, message: str, run_id: UUID | None = None, **fields: object) -> None:
        self._logger.error(self._line(status, message, run_id, fields))
