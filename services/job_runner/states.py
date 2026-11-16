"""Nombres y constantes del control de ejecuciones nocturnas (DEV-53).

Solo librería estándar. Los estados son los cuatro del enunciado; `skipped` y
`locked` (omisión por duplicado y bloqueo) **solo existen en el log** y en el
resultado de `run_job`, nunca como estado de la base (M8).
"""

from enum import StrEnum

SCHEMA = "ops"
TABLE = "job_runs"
QUALIFIED_TABLE = f"{SCHEMA}.{TABLE}"

NIGHTLY_EXPORT = "nightly_export"

# El índice del enunciado, el lock y la idempotencia como garantía de base de datos.
TARGET_INDEX = "ix_job_runs_job_target"
ONE_PROCESSING_INDEX = "ux_job_runs_one_processing"
ONE_COMPLETED_INDEX = "ux_job_runs_one_completed_per_day"

# Una fila `processing` más antigua se barre como abandonada: el máximo legítimo
# es el export (segundos) + el timeout del pipeline (20 min) + el cierre, ~21 min.
STALE_PROCESSING_MINUTES = 45
# Una `pending` solo puede quedar huérfana si el proceso muere entre el INSERT y el claim.
STALE_PENDING_MINUTES = 5

# Escritura del estado final: 1 intento + 3 reintentos, con estas esperas (s).
FINALIZE_RETRY_DELAYS = (1.0, 2.0, 4.0)

# Tope del mensaje que describe una excepción (la base admite 1000).
MAX_ERROR_MESSAGE_CHARS = 500
DATABASE_MESSAGE_LIMIT = 1000

ABANDONED_PROCESSING_MESSAGE = (
    f"Abandoned: processing for more than {STALE_PROCESSING_MINUTES} minutes without finishing "
    "(process presumed dead)"
)
ABANDONED_PENDING_MESSAGE = (
    f"Abandoned: pending for more than {STALE_PENDING_MINUTES} minutes (process died before starting)"
)


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
