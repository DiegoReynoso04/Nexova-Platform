"""Instancia de Celery: `celery -A task_queue.celery_app worker` (y `flower`).

`create_app` no hace E/S (Celery conecta con Redis al primer uso), así que los tests
la construyen con una configuración propia. La instancia del módulo, `app`, lee
`REDIS_URL` del entorno al importarse: sin ella, el worker no arranca (ConfigError,
sin la URL en el mensaje).
"""

from __future__ import annotations

from celery import Celery

from .config import TaskQueueSettings, celery_config

TASK_MODULES = ("task_queue.tasks",)


def create_app(settings: TaskQueueSettings) -> Celery:
    celery = Celery("task_queue", include=list(TASK_MODULES))
    celery.conf.update(celery_config(settings))
    return celery


app = create_app(TaskQueueSettings.from_env())
