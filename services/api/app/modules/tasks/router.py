"""`GET /tasks/{task_id}`: estado y resultado de una tarea de la cola (DEV-55, A10; SPECS Parte J).

- Bearer, cualquier rol. Solo el propietario o un `admin` ven la tarea; a cualquier
  otro, el mismo 404 que a un id que no existe (no se confirma que exista).
- Un id que la API no encoló, uno caducado o uno que no es un UUID → 404
  `task_not_found` (la cola respondería «pendiente» a cualquier id inventado).
- `status`: `pending`, `started`, `success` o `failure`. `result`: `null` mientras no
  termina; en `success`, el resultado con el esquema de su tarea; en `failure`, un
  objeto fijo, sin clase, mensaje ni traza.
- `Cache-Control: no-store`: el estado cambia con cada consulta.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from task_queue.client import TaskQueueUnavailableError as QueueDownError
from task_queue.names import TELEMETRY_REPORT_TASK

from app.auth.dependencies import get_current_user
from app.auth.models import UserInDB, UserRole
from app.core.errors import TaskNotFoundError, TaskQueueUnavailableError
from app.modules.tasks.dependencies import task_queue_client
from app.modules.tasks.schemas import TaskFailure, TaskStatusRead
from app.modules.telemetry.schemas import TelemetryReport

router = APIRouter(prefix="/tasks", tags=["tasks"])

NO_STORE = "no-store"
# Esquema del resultado de cada tarea que puede consultar la API.
RESULT_MODELS: dict[str, Any] = {TELEMETRY_REPORT_TASK: TelemetryReport}


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@router.get(
    "/{task_id}",
    response_model=TaskStatusRead,
    responses={
        401: {"description": "Sin token o con uno no válido."},
        404: {"description": "El id no existe, caducó o es de otro usuario (`task_not_found`)."},
        503: {"description": "La cola no está configurada o Redis no responde (`task_queue_unavailable`)."},
    },
)
def read_task(
    task_id: str, request: Request, response: Response, user: Annotated[UserInDB, Depends(get_current_user)]
) -> TaskStatusRead:
    response.headers["Cache-Control"] = NO_STORE
    if not _is_uuid(task_id):
        raise TaskNotFoundError()
    client = task_queue_client(request)
    try:
        status = client.status(task_id, viewer_id=str(user.id), viewer_is_admin=user.role == UserRole.ADMIN)
    except QueueDownError:
        raise TaskQueueUnavailableError() from None
    if status is None:
        raise TaskNotFoundError()
    result: TelemetryReport | TaskFailure | None = None
    if status.status == "success" and status.task_name in RESULT_MODELS:
        result = RESULT_MODELS[status.task_name].model_validate(status.result)
    elif status.status == "failure":
        result = TaskFailure()
    return TaskStatusRead(task_id=status.task_id, status=status.status, result=result)
