"""Control de estado de los jobs nocturnos (DEV-53): `ops.job_runs` y su máquina de estados.

Biblioteca (como `services/telemetry` y `services/reporting`), no un servicio
desplegable. Solo SQLAlchemy y la librería estándar; no importa FastAPI ni nada
de `services/api`. Ver `README.md` y `docs/telemetry/nightly-export-analysis.md`.
"""

from .repository import AlreadyCompletedError, JobRun, JobRunRepository, JobRunStateError
from .runner import Outcome, RunResult, run_job
from .states import NIGHTLY_EXPORT, JobStatus

__all__ = [
    "NIGHTLY_EXPORT",
    "AlreadyCompletedError",
    "JobRun",
    "JobRunRepository",
    "JobRunStateError",
    "JobStatus",
    "Outcome",
    "RunResult",
    "run_job",
]
