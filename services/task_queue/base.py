"""Clase base de todas las tareas: reintentos (A8), DLQ (A9) y logs (A12).

`ReliableTask.__call__` envuelve cada ejecución, en el proceso que la ejecuta:

1. línea `status=started` con el intento (`attempt=n/4`);
2. si la tarea termina: línea `status=success` con la duración;
3. si falla con un error transitorio (`errors.RETRYABLE_EXCEPTIONS`) y quedan
   reintentos: línea `status=retry` con la cuenta atrás de `retries.backoff_countdown`
   y `self.retry(...)` con una excepción ya redactada (`TaskFailedError`);
4. si no: fallo definitivo. Línea `status=dead_letter` (ERROR) con el error
   completo redactado, fila en `ops.task_dead_letters` (o línea
   `dead_letter_not_stored` si la base no responde) y `TaskFailedError`, que es lo
   que guarda el result backend y muestra Flower.

`max_retries=3` literal (A8-A): 4 ejecuciones; la DLQ guarda `attempt=4` y `retries=3`.

El **límite duro** (`task_time_limit`) mata el proceso hijo, así que no pasa por
`__call__`: lo registra `DeadLetterRequest.on_timeout` en el proceso principal del
worker, que sí conoce los reintentos del mensaje.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from billiard.exceptions import SoftTimeLimitExceeded
from celery import Task
from celery.exceptions import Retry
from celery.worker import state as worker_state
from celery.worker.request import Request

from .config import MAX_RETRIES
from .dead_letters import DeadLetter, record_dead_letter
from .errors import RETRYABLE_EXCEPTIONS, DeadLetterReason, TaskFailedError
from .logs import log_task
from .redaction import describe_failure, install_redacting_filter
from .retries import backoff_countdown

install_redacting_filter()


def task_kwargs_of(args: tuple[Any, ...] | list[Any], kwargs: dict[str, Any] | None) -> dict[str, Any]:
    """Las referencias del mensaje para la DLQ. Las tareas se llaman con kwargs; si hay posicionales, van en `args`."""
    values = dict(kwargs or {})
    if args:
        values["args"] = list(args)
    return values


def _ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


class DeadLetterRequest(Request):
    """Petición del worker que registra en la DLQ las tareas que superan el límite duro."""

    def on_timeout(self, soft: bool, timeout: float) -> None:
        super().on_timeout(soft, timeout)
        if soft or worker_state.should_terminate:
            return
        retries = int(self.request_dict.get("retries") or 0)
        max_retries = int(getattr(self.task, "max_retries", MAX_RETRIES) or 0)
        message = f"TimeLimitExceeded: hard time limit ({timeout}s) exceeded"
        letter = DeadLetter(
            task_id=self.id,
            task_name=self.name,
            retries=retries,
            max_retries=max_retries,
            reason=DeadLetterReason.TIME_LIMIT,
            error_class="TimeLimitExceeded",
            error_message=message,
            task_kwargs=task_kwargs_of(self.args, self.kwargs),
            queue=(self.delivery_info or {}).get("routing_key"),
            worker=self.hostname,
        )
        log_task(
            logging.ERROR,
            task_id=self.id,
            task=self.name,
            attempt=letter.attempt,
            total=max_retries + 1,
            status="dead_letter",
            reason=str(letter.reason),
            error_class=letter.error_class,
            error=message,
        )
        record_dead_letter(letter)


class ReliableTask(Task):
    max_retries = MAX_RETRIES
    Request = "task_queue.base:DeadLetterRequest"
    # Fallos esperados: Celery los registra sin traza; el detalle está en nuestra línea.
    throws = (TaskFailedError,)
    #: Inyectable en los tests (SQLite o un registro en memoria).
    dead_letter_recorder = staticmethod(record_dead_letter)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        request = self.request
        retries = int(request.retries or 0)
        total = self.max_retries + 1
        common = {"task_id": request.id, "task": self.name, "attempt": retries + 1, "total": total}
        log_task(logging.INFO, **common, status="started")
        started = time.monotonic()
        try:
            result = super().__call__(*args, **kwargs)
        except Retry:  # una tarea que llama a self.retry() por su cuenta
            raise
        except Exception as error:
            error_class, message = describe_failure(error)
            if isinstance(error, RETRYABLE_EXCEPTIONS) and retries < self.max_retries:
                countdown = backoff_countdown(retries)
                log_task(
                    logging.WARNING,
                    **common,
                    status="retry",
                    duration_ms=_ms(started),
                    countdown_s=countdown,
                    error_class=error_class,
                    error=message,
                )
                raise self.retry(
                    exc=TaskFailedError(error_class, message), countdown=countdown, max_retries=self.max_retries
                ) from None
            reason = self._reason(error)
            log_task(
                logging.ERROR,
                **common,
                status="dead_letter",
                duration_ms=_ms(started),
                reason=str(reason),
                error_class=error_class,
                error=message,
            )
            delivery = request.delivery_info or {}
            self.dead_letter_recorder(
                DeadLetter(
                    task_id=request.id,
                    task_name=self.name,
                    retries=retries,
                    max_retries=self.max_retries,
                    reason=reason,
                    error_class=error_class,
                    error_message=message,
                    task_kwargs=task_kwargs_of(args, kwargs),
                    queue=delivery.get("routing_key"),
                    worker=request.hostname,
                )
            )
            raise TaskFailedError(error_class, message) from None
        log_task(logging.INFO, **common, status="success", duration_ms=_ms(started))
        return result

    def _reason(self, error: BaseException) -> DeadLetterReason:
        if isinstance(error, SoftTimeLimitExceeded):
            return DeadLetterReason.TIME_LIMIT
        if isinstance(error, RETRYABLE_EXCEPTIONS):
            return DeadLetterReason.RETRIES_EXHAUSTED
        return DeadLetterReason.NON_RETRYABLE
