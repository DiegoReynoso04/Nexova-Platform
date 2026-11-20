"""Tareas de la cola. Parada 1 de F1: solo `task_queue.ping`, para comprobar que el
worker está conectado al broker antes de convertir ningún endpoint.

Los nombres son explícitos (`name=`): la API envía las tareas por nombre
(`send_task`), sin importar este módulo.
"""

from __future__ import annotations

from .celery_app import app

PING_TASK = "task_queue.ping"


@app.task(name=PING_TASK)
def ping() -> str:
    """Tarea trivial: responde `pong`. Sin argumentos, sin base de datos."""
    return "pong"
