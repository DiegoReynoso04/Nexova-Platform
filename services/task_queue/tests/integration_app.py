"""App de Celery **solo para los tests de integración** (`test_worker_integration.py`).

Vive en `tests/`, que no entra en la imagen (`services/.dockerignore`): estas tareas
que fallan a propósito nunca existen en el worker de verdad (A13: sin interruptores
en el código). Misma configuración de A7 salvo una cola propia y límites de tiempo
cortos (2 s / 4 s) para poder probarlos.

    celery -A task_queue.tests.integration_app worker -P prefork -c 1
"""

from __future__ import annotations

import os
import time

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import OperationalError

from task_queue.celery_app import create_app
from task_queue.config import TaskQueueSettings

QUEUE = "nexova.integration"
SOFT_LIMIT, HARD_LIMIT = 2, 4

app = create_app(TaskQueueSettings.from_env(), include=())
app.conf.update(task_default_queue=QUEUE, task_soft_time_limit=SOFT_LIMIT, task_time_limit=HARD_LIMIT, worker_concurrency=1)


def _transient() -> OperationalError:
    # El mensaje lleva la URL de la base: comprueba que nunca llega al log, a la DLQ ni al backend.
    return OperationalError("SELECT 1", {}, Exception(f"could not connect to {os.environ.get('DATABASE_URL', '')}"))


@app.task(name="integration.succeed")
def succeed(token: str) -> dict:
    return {"token": token}


@app.task(name="integration.always_transient")
def always_transient(token: str) -> None:
    raise _transient()


@app.task(name="integration.transient_twice", bind=True)
def transient_twice(self, token: str) -> str:
    if self.request.retries < 2:
        raise _transient()
    return "recovered"


@app.task(name="integration.non_retryable")
def non_retryable(token: str) -> None:
    raise ValueError(f"invalid token {token}; broker {os.environ.get('REDIS_URL', '')}")


@app.task(name="integration.soft_timeout")
def soft_timeout(token: str) -> None:
    time.sleep(SOFT_LIMIT * 5)


@app.task(name="integration.hard_timeout")
def hard_timeout(token: str) -> None:
    deadline = time.monotonic() + HARD_LIMIT * 5
    while time.monotonic() < deadline:
        try:
            time.sleep(0.2)
        except SoftTimeLimitExceeded:
            continue  # ignora el límite blando: solo el duro lo para
