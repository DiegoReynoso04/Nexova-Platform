"""El ciclo de vida de una ejecución: `pending → processing → completed | failed` (apartado C.1).

`run_job` es genérico: recibe la función de trabajo (`work`), así que la máquina
de estados se prueba sin Prefect ni subprocesos. No importa FastAPI ni nada de
`services/api`.

Pasos: barrer abandonadas → ¿ya `completed` ese día? (omitir) → ¿hay lock?
(abortar) → crear `pending` → **claim** atómico (el índice único parcial manda) →
re-comprobar `completed` (ventana de carrera) → `work()` → `completed`. Cualquier
excepción, también `KeyboardInterrupt`/`SystemExit`, deja la fila en `failed`.

Omitir y abortar por lock **no escriben fila**: solo el log (`status=skipped` o
`status=locked`); la fila propia de la instancia que pierde se borra (M8).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from .logs import LOGGER_NAME, JobLogger
from .redact import describe_exception
from .repository import AlreadyCompletedError, JobRun, JobRunRepository
from .states import FINALIZE_RETRY_DELAYS, JobStatus

Clock = Callable[[], datetime]
Sleep = Callable[[float], None]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Outcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # ya había un `completed` para ese día
    LOCKED = "locked"  # otra instancia tiene el lock


@dataclass(frozen=True, slots=True)
class RunResult:
    outcome: Outcome
    run_id: UUID | None = None
    error_message: str | None = None


def run_job(
    repository: JobRunRepository,
    job_name: str,
    target_date: date,
    work: Callable[[], None],
    *,
    logger: logging.Logger | None = None,
    clock: Clock = utc_now,
    sleep: Sleep = time.sleep,
) -> RunResult:
    """Ejecuta `work` bajo la máquina de estados y devuelve qué pasó.

    Un error de infraestructura **antes** del claim (la base caída al crear la
    fila) se propaga: no hay fila que cerrar. Un fallo de `work` devuelve
    `Outcome.FAILED`; `KeyboardInterrupt`/`SystemExit` se registran como `failed`
    y se relanzan.
    """
    log = JobLogger(logger or logging.getLogger(LOGGER_NAME), job_name, target_date)

    swept = repository.sweep_stale(job_name, clock())
    if swept:
        log.info(JobStatus.FAILED, "abandoned rows closed", rows=swept)

    if repository.has_completed_for_date(job_name, target_date):
        log.info("skipped", "already completed for this day, nothing to do", reason="already_completed")
        return RunResult(Outcome.SKIPPED)
    if repository.has_processing_lock(job_name):
        log.info("locked", "another instance is processing, aborting", reason="another_instance_processing")
        return RunResult(Outcome.LOCKED)

    run = repository.create_job_run(job_name, target_date, clock())
    log.info(JobStatus.PENDING, "created", run.id)

    try:
        claimed = repository.claim(run.id, clock())
    except BaseException:
        _discard_quietly(repository, run.id)
        raise
    if not claimed:
        repository.discard(run.id)
        log.info("locked", "another instance is processing, aborting", run.id, reason="another_instance_processing")
        return RunResult(Outcome.LOCKED)

    # Ventana de carrera: otra instancia pudo pasar a `completed` justo antes del claim.
    if repository.has_completed_for_date(job_name, target_date):
        repository.discard(run.id)
        log.info("skipped", "already completed for this day, nothing to do", run.id, reason="already_completed")
        return RunResult(Outcome.SKIPPED)

    started = clock()
    log.info(JobStatus.PROCESSING, "lock acquired", run.id)
    try:
        work()
    except BaseException as error:  # noqa: BLE001  (se relanzan las que no son Exception)
        message = describe_exception(error)
        _record_failure(repository, log, run, message, clock, sleep)
        if not isinstance(error, Exception):
            raise
        return RunResult(Outcome.FAILED, run.id, message)

    return _record_completion(repository, log, run, started, clock, sleep)


def _record_completion(
    repository: JobRunRepository, log: JobLogger, run: JobRun, started: datetime, clock: Clock, sleep: Sleep
) -> RunResult:
    try:
        completed = _with_retries(lambda: repository.complete(run.id, clock()), sleep)
    except AlreadyCompletedError:
        message = "a completed run already exists for this day"
        _record_failure(repository, log, run, message, clock, sleep)
        return RunResult(Outcome.FAILED, run.id, message)
    except SQLAlchemyError as error:
        # La fila queda `processing`: el barrido de la siguiente ejecución la cierra (C.5).
        message = f"could not record completion: {describe_exception(error)}"
        log.error(JobStatus.PROCESSING, message, run.id)
        return RunResult(Outcome.FAILED, run.id, message)
    if not completed:
        message = "lock lost: the run was closed by another process while it was working"
        log.error(JobStatus.FAILED, message, run.id)
        return RunResult(Outcome.FAILED, run.id, message)
    log.info(JobStatus.COMPLETED, "finished", run.id, seconds=f"{(clock() - started).total_seconds():.1f}")
    return RunResult(Outcome.COMPLETED, run.id)


def _record_failure(
    repository: JobRunRepository, log: JobLogger, run: JobRun, message: str, clock: Clock, sleep: Sleep
) -> None:
    """`failed` con el mensaje. Si ni así se puede escribir, queda `processing` y se registra."""
    try:
        written = _with_retries(lambda: repository.fail(run.id, message, clock()), sleep)
    except SQLAlchemyError as write_error:
        log.error(
            JobStatus.PROCESSING,
            f"{message}; could not record the failure ({describe_exception(write_error)}), "
            "the next run will close the row as abandoned",
            run.id,
        )
        return
    if not written:
        log.error(JobStatus.FAILED, f"{message}; the run was already closed", run.id)
        return
    log.error(JobStatus.FAILED, message, run.id)


def _with_retries(action: Callable[[], object], sleep: Sleep):
    """`action` con 1 intento + 1 reintento por cada espera de `FINALIZE_RETRY_DELAYS`."""
    for delay in FINALIZE_RETRY_DELAYS:
        try:
            return action()
        except SQLAlchemyError:
            sleep(delay)
    return action()


def _discard_quietly(repository: JobRunRepository, run_id: UUID) -> None:
    try:
        repository.discard(run_id)
    except SQLAlchemyError:
        pass  # la `pending` huérfana la barre la siguiente ejecución
