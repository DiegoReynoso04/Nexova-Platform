"""La cola de tareas en los tests de la API: el `TaskQueueClient` real con dobles en memoria.

`install_task_queue(app, engine)` sustituye `app.state.task_queue` por un cliente
con `MemoryStore` (metadatos y deduplicación de verdad, con reloj inyectable) y un
`EagerBackend` que ejecuta la tarea del reporte en el acto con
`task_queue.reports.build_telemetry_report` sobre la base del test (SQLite): el
mismo cálculo que hace el worker. Con `hold=True`, las tareas se quedan en `pending`
hasta `backend.run(task_id)`.
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine
from task_queue.client import TaskQueueClient
from task_queue.memory import EagerBackend, MemoryStore
from task_queue.names import TELEMETRY_REPORT_TASK
from task_queue.reports import build_telemetry_report


def install_task_queue(
    app: FastAPI, engine: Engine, *, clock: Callable[[], float] | None = None, hold: bool = False
) -> tuple[TaskQueueClient, MemoryStore, EagerBackend]:
    store = MemoryStore(clock) if clock is not None else MemoryStore()

    def telemetry_report(start: str, end: str) -> dict[str, Any]:
        return build_telemetry_report(engine, start, end)

    backend = EagerBackend({TELEMETRY_REPORT_TASK: telemetry_report}, hold=hold)
    client = TaskQueueClient(store=store, backend=backend)
    app.state.task_queue = client
    return client, store, backend
