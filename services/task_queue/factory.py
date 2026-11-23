"""`create_app(settings)`: una instancia de Celery con la configuración de A7, sin E/S.

La usan el worker y Flower (vía `celery_app.app`, que lee `REDIS_URL` del entorno)
y la API (vía `client.TaskQueueClient.from_redis_url`, con la `REDIS_URL` de sus
`Settings` y sin registrar ninguna tarea: solo envía por nombre).

Todas las tareas heredan de `base.ReliableTask` (`task_cls`): reintentos con
backoff, DLQ y una línea de log por ejecución (A8, A9, A12).
"""

from __future__ import annotations

from collections.abc import Sequence

from celery import Celery

from .config import TaskQueueSettings, celery_config

TASK_MODULES = ("task_queue.tasks",)
TASK_CLASS = "task_queue.base:ReliableTask"


def create_app(settings: TaskQueueSettings, *, include: Sequence[str] = TASK_MODULES) -> Celery:
    celery = Celery("task_queue", include=list(include), task_cls=TASK_CLASS)
    celery.conf.update(celery_config(settings))
    return celery
