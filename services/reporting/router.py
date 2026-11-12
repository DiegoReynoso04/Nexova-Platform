"""`/reporting`: el reporte semanal de desempeño, la última corrida y el disparo manual (§5 del diseño).

| Ruta | Auth | Respuestas |
|---|---|---|
| `GET /reporting/weekly-office-program-performance?week_start=` | Bearer, cualquier rol | 200 (contrato del BRIEFING), 404 `week_not_computed`, 422, 401, 503 `storage_unavailable` |
| `GET /reporting/pipeline-runs/latest` | Bearer, cualquier rol | 200 (sin `requested_by`), 404 `pipeline_run_not_found`, 401, 503 |
| `POST /reporting/pipeline-runs` | Bearer, solo `admin` | 202, 409 `pipeline_run_in_progress`, 422, 401, 403, 503 `pipeline_unavailable` |

El token lo exige `app/main.py` al registrar el router; el `POST` añade `admin`.
**Sin caché** (D12 del diseño): la tabla la escribe otro proceso (el worker),
que no puede invalidar la caché en memoria de la API.

**Por qué la API importa `request_manual_run` y no el flow** (D2): Prefect no
está en la API (D1) y un flow ejecutado aquí moriría con cada recarga de
`--reload`. `request_manual_run` (librería estándar) solo pide el flow run al
servidor de Prefect; lo ejecuta el `pipeline-worker`.
"""

import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated, TypeVar

from business_performance.trigger import PipelineUnavailableError, RunAlreadyActiveError, request_manual_run
from fastapi import APIRouter, Depends, Request
from sqlalchemy.engine import Connection
from sqlalchemy.exc import ProgrammingError
from sqlmodel import Session

from app.auth.dependencies import AdminDep
from app.core.errors import ApiError, StorageUnavailableError
from app.modules.inventory.database import get_db

from . import reads
from .schemas import ManualRunAccepted, ManualRunRequest, MondayDate, PipelineRunRead, WeeklyPerformance

logger = logging.getLogger("api.reporting")

router = APIRouter(prefix="/reporting", tags=["reporting"])

T = TypeVar("T")


class WeekNotComputedError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "week_not_computed", "no completed pipeline run covers this week")


class PipelineRunNotFoundError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "pipeline_run_not_found", "the pipeline has not run yet")


class PipelineRunInProgressError(ApiError):
    def __init__(self) -> None:
        super().__init__(409, "pipeline_run_in_progress", "a pipeline run is already in progress")


class PipelineUnavailableApiError(ApiError):
    def __init__(self) -> None:
        super().__init__(503, "pipeline_unavailable", "the pipeline orchestrator is not available")


def _connection(session: Annotated[Session, Depends(get_db)]) -> Iterator[Connection]:
    yield session.connection()


ConnectionDep = Annotated[Connection, Depends(_connection)]


def _read(read: Callable[[], T]) -> T:
    """Sin el esquema `reporting` (migración sin aplicar), 503 `storage_unavailable`, no un 500.

    Solo se registra la clase: el mensaje de psycopg2 lleva la SQL y el host.
    """
    try:
        return read()
    except ProgrammingError as error:
        logger.error("reporting schema is unavailable: %s", type(error).__name__)
        raise StorageUnavailableError() from None


@router.get(
    "/weekly-office-program-performance",
    response_model=WeeklyPerformance,
    responses={
        401: {"description": "Sin token o con uno no válido."},
        404: {"description": "Ninguna corrida completada cubre la semana (`week_not_computed`)."},
        422: {"description": "`week_start` no es una fecha o no es lunes (`validation_error`)."},
        503: {"description": "La base no responde o falta el esquema `reporting` (`storage_unavailable`)."},
    },
)
def read_weekly_performance(connection: ConnectionDep, week_start: MondayDate | None = None) -> WeeklyPerformance:
    """Las combinaciones oficina/programa de una semana. Sin `week_start`: la semana calculada más reciente."""

    def read() -> WeeklyPerformance:
        week = week_start if week_start is not None else reads.latest_computed_week(connection)
        if week is None or not reads.week_is_computed(connection, week):
            raise WeekNotComputedError()
        # Semana calculada sin actividad → `entries: []` (no se inventan filas a 0).
        return WeeklyPerformance.model_validate({"week_start": week, "entries": reads.week_rows(connection, week)})

    return _read(read)


@router.get(
    "/pipeline-runs/latest",
    response_model=PipelineRunRead,
    responses={
        401: {"description": "Sin token o con uno no válido."},
        404: {"description": "El pipeline aún no ha corrido (`pipeline_run_not_found`)."},
        503: {"description": "La base no responde o falta el esquema `reporting` (`storage_unavailable`)."},
    },
)
def read_latest_pipeline_run(connection: ConnectionDep) -> PipelineRunRead:
    """La última corrida por `started_at`: estado, fase, semanas, contadores y `quality`."""
    run = _read(lambda: reads.latest_run(connection))
    if run is None:
        raise PipelineRunNotFoundError()
    return PipelineRunRead.model_validate(run)


@router.post(
    "/pipeline-runs",
    status_code=202,
    response_model=ManualRunAccepted,
    responses={
        401: {"description": "Sin token o con uno no válido."},
        403: {"description": "El usuario no es `admin`."},
        409: {"description": "Ya hay una corrida en marcha o programada (`pipeline_run_in_progress`)."},
        422: {"description": "`week_start` no es lunes, no es una semana cerrada o sale de la retención."},
        503: {"description": "Prefect no está configurado o no responde (`pipeline_unavailable`)."},
    },
)
def request_pipeline_run(
    request: Request, connection: ConnectionDep, admin: AdminDep, body: ManualRunRequest | None = None
) -> ManualRunAccepted:
    """Dispara una corrida manual (asíncrona); su estado se sigue en `GET /reporting/pipeline-runs/latest`."""
    api_url = request.app.state.settings.pipeline_prefect_api_url
    if not api_url:
        raise PipelineUnavailableApiError()
    if _read(lambda: reads.has_running_run(connection, datetime.now(UTC))):
        raise PipelineRunInProgressError()
    week_start = body.week_start if body is not None else None
    try:
        # `requested_by` sale del token, nunca del cuerpo.
        run = request_manual_run(api_url, week_start=week_start, requested_by=admin.id)
    except RunAlreadyActiveError:
        raise PipelineRunInProgressError() from None
    except PipelineUnavailableError as error:
        logger.error("pipeline orchestrator is unavailable: %s", error)
        raise PipelineUnavailableApiError() from None
    return ManualRunAccepted(prefect_flow_run_id=run.prefect_flow_run_id, status="scheduled")
