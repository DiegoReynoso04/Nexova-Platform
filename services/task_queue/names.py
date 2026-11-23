"""Nombres de las tareas. Los comparten la API (que las envía por nombre) y el worker.

Aquí y no en `tasks.py`: importar `tasks` carga la instancia de Celery del worker,
que lee `REDIS_URL` del entorno al importarse.
"""

PING_TASK = "task_queue.ping"
TELEMETRY_REPORT_TASK = "task_queue.telemetry_report"
