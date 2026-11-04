"""Colector de telemetría: `POST /telemetry/events`.

Cada item del lote se valida por separado y los válidos se guardan en
`telemetry_events` con un solo insert (`collector.py`). Responde
`200 {"received", "stored", "rejected"}` mientras el cuerpo tenga un arreglo
`events`; el frontend solo mira si es 2xx, así que no cambia.

Sin autenticación a propósito: `navigator.sendBeacon` (el envío al ocultar la
pestaña) no puede llevar `Authorization`, y un 401 haría que el cliente del
backoffice cerrase la sesión. Un token, si llega y es válido, da la identidad.
Límites: 50 eventos procesados por lote, 120 por minuto (`EventRateLimiter`) y
64 KiB de body (`BodySizeLimitMiddleware`, por ruta).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.auth.security import TokenClaims, read_token_claims
from app.modules.inventory.database import get_db
from app.modules.telemetry.collector import EventRateLimiter, collect
from app.modules.telemetry.schemas import TelemetryBatch, TelemetryBatchResult

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Plan §2.4: tope del body del colector, por debajo del límite general.
TELEMETRY_MAX_BODY_BYTES = 64 * 1024
TELEMETRY_EVENTS_PATH = "/telemetry/events"


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
