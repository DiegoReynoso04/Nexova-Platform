"""Cola de tareas asíncronas de Nexova (DEV-55): Celery con Redis como broker y backend.

Biblioteca, como `services/job_runner` y `services/telemetry`: la API la usa para
encolar y leer estados, y el servicio `worker` de Compose la ejecuta con
`celery -A task_queue.celery_app worker`. No importa FastAPI ni el paquete `app`
de la API. Decisiones: `docs/async-tasks/analysis.md` (A5–A7).
"""
