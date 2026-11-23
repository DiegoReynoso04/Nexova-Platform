"""Instancia de Celery del worker y de Flower: `celery -A task_queue.celery_app worker`.

Lee `REDIS_URL` del entorno al importarse: sin ella, el worker no arranca
(ConfigError, sin la URL en el mensaje). La API **no** importa este módulo: crea su
propia instancia con `factory.create_app` desde sus `Settings` (`client.py`).
"""

from __future__ import annotations

from .config import TaskQueueSettings
from .factory import TASK_CLASS, TASK_MODULES, create_app

__all__ = ["TASK_CLASS", "TASK_MODULES", "app", "create_app"]

app = create_app(TaskQueueSettings.from_env())
