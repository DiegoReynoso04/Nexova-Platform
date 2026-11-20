"""Una línea por ejecución de tarea (criterio de observabilidad del ticket, A12).

Formato, en el logger `task_queue` (el worker de Celery le añade su marca de tiempo):

    task_id=<uuid> task=<nombre> attempt=2/4 status=retry duration_ms=12.3 countdown_s=4.81 error="OperationalError (QueryCanceled)"

Estados: `started`, `success`, `retry`, `dead_letter`, `dead_letter_stored` y
`dead_letter_not_stored`. El `error` ya llega redactado (`redaction.describe_failure`);
además, el filtro de `redaction` vuelve a pasar por cada línea.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("task_queue")


def _value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    text = str(value)
    if not text or any(character.isspace() for character in text) or '"' in text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def task_line(*, task_id: str, task: str, attempt: int, total: int, status: str, **fields: Any) -> str:
    parts = [f"task_id={task_id}", f"task={task}", f"attempt={attempt}/{total}", f"status={status}"]
    parts += [f"{name}={_value(value)}" for name, value in fields.items() if value is not None]
    return " ".join(parts)


def log_task(level: int, **fields: Any) -> None:
    logger.log(level, "%s", task_line(**fields))
