"""Contrato de la cola en la API (SPECS Parte J): el 202 de encolar y `GET /tasks/{task_id}`."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.modules.telemetry.schemas import TelemetryReport


class TaskAccepted(BaseModel):
    """`202 Accepted`: la tarea está en la cola. Su estado, en `GET /tasks/{task_id}` (cabecera `Location`)."""

    model_config = ConfigDict(frozen=True)

    task_id: str


class TaskFailure(BaseModel):
    """`result` de una tarea fallida: fijo, sin clase, mensaje ni traza (el detalle está en el log y en la DLQ)."""

    model_config = ConfigDict(frozen=True)

    code: Literal["task_failed"] = "task_failed"
    detail: str = "the task failed"


class TaskStatusRead(BaseModel):
    """`status` con los cuatro estados del contrato; `result` solo al terminar."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    status: Literal["pending", "started", "success", "failure"]
    result: TelemetryReport | TaskFailure | None = None
