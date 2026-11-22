"""Telemetría: colector `POST /telemetry/events` y reporte `GET /telemetry/report`.

Cada item del lote se valida por separado y los válidos se guardan en
`telemetry_events` con un solo insert (`collector.py`). Responde
`200 {"received", "stored", "rejected"}` mientras el cuerpo tenga un arreglo
`events`; el frontend solo mira si es 2xx, así que no cambia.

Sin autenticación a propósito: `navigator.sendBeacon` (el envío al ocultar la
pestaña) no puede llevar `Authorization`, y un 401 haría que el cliente del
backoffice cerrase la sesión. Un token, si llega y es válido, da la identidad.
Límites: 50 eventos procesados por lote, 120 por minuto (`EventRateLimiter`) y
64 KiB de body (`BodySizeLimitMiddleware`, por ruta).

El reporte sí exige token: expone actividad y errores, y su llamada es un `fetch`
normal. Por eso la dependencia va en la ruta, y no al registrar este router.

**Desde DEV-55 el reporte es asíncrono (A1–A4, A11):** la ruta valida y resuelve el
periodo (422 como siempre, sin crear tarea), **encola** `task_queue.telemetry_report`
con solo `start` y `end` y responde `202 {"task_id"}` con `Location: /tasks/<id>`. El
cálculo con Pandas lo hace el worker, fuera de este proceso; el resultado, con la
forma de siempre, llega por `GET /tasks/{id}`. La ruta no toca la base: el 202 no
espera a Supabase. La caché de 60 s en memoria la sustituye la deduplicación por
usuario de `task_queue` (A4): la misma combinación del mismo usuario en 60 s devuelve
la misma tarea.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlmodel import Session
from task_queue.client import TaskQueueUnavailableError as QueueDownError
from task_queue.names import TELEMETRY_REPORT_TASK

from app.auth.dependencies import get_current_user
from app.auth.models import UserInDB
from app.auth.security import TokenClaims, read_token_claims
from app.core.errors import TaskQueueUnavailableError
from app.modules.inventory.database import get_db
from app.modules.tasks.dependencies import task_queue_client
from app.modules.tasks.schemas import TaskAccepted
from app.modules.telemetry.collector import EventRateLimiter, collect
from app.modules.telemetry.report import cache_key, iso_utc, resolve_period
from app.modules.telemetry.schemas import TelemetryBatch, TelemetryBatchResult

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Plan §2.4: tope del body del colector, por debajo del límite general.
TELEMETRY_MAX_BODY_BYTES = 64 * 1024
TELEMETRY_EVENTS_PATH = "/telemetry/events"
TASKS_PATH = "/tasks/{task_id}"
NO_STORE = "no-store"


def _claims(request: Request) -> TokenClaims | None:
    """Los claims de un token válido, o `None`. Nunca un 401."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return read_token_claims(request.app.state.settings, token.strip())


@router.post(
    "/events",
    response_model=TelemetryBatchResult,
    responses={
        413: {"description": "El body supera 64 KiB (`file_too_large`)."},
        503: {"description": "La base no responde (`storage_unavailable`): el frontend reintenta."},
    },
)
def receive_events(
    batch: TelemetryBatch, request: Request, session: Annotated[Session, Depends(get_db)]
) -> TelemetryBatchResult:
    limiter = request.app.state.telemetry_rate_limiter
    assert isinstance(limiter, EventRateLimiter)
    return collect(batch.events, session=session, limiter=limiter, claims=_claims(request))


def dedupe_scope(start_date: datetime | None, end_date: datetime | None) -> str:
    """Lo que pidió el cliente, en UTC (la antigua clave de caché): la ventana por defecto es `-|-`."""
    start, end = cache_key(start_date, end_date)  # type: ignore[misc]
    return f"{'-' if start is None else iso_utc(start)}|{'-' if end is None else iso_utc(end)}"


@router.get(
    "/report",
    status_code=202,
    response_model=TaskAccepted,
    responses={
        202: {
            "description": "Tarea encolada. Su estado y el reporte, en `GET /tasks/{task_id}`.",
            "headers": {
                "Location": {"description": "`/tasks/<task_id>`", "schema": {"type": "string"}},
                "Cache-Control": {"description": NO_STORE, "schema": {"type": "string"}},
            },
        },
        401: {"description": "Sin token o con uno no válido."},
        422: {"description": "Fechas no válidas, `start_date` ≥ `end_date` o más de 90 días (`validation_error`)."},
        503: {"description": "La cola no está configurada o Redis no responde (`task_queue_unavailable`)."},
    },
)
def read_report(
    request: Request,
    response: Response,
    user: Annotated[UserInDB, Depends(get_current_user)],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> TaskAccepted:
    period = resolve_period(start_date, end_date, datetime.now(UTC))
    client = task_queue_client(request)
    try:
        submission = client.submit(
            TELEMETRY_REPORT_TASK,
            # El mensaje solo lleva las dos fechas (C8): el worker lee la tabla.
            {"start": iso_utc(period.start), "end": iso_utc(period.end)},
            owner_id=str(user.id),
            dedupe_scope=dedupe_scope(start_date, end_date),
        )
    except QueueDownError:
        raise TaskQueueUnavailableError() from None
    response.headers["Location"] = TASKS_PATH.format(task_id=submission.task_id)
    response.headers["Cache-Control"] = NO_STORE
    return TaskAccepted(task_id=submission.task_id)
