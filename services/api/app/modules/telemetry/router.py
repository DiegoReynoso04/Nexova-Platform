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
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session
from telemetry.analysis import all_metrics

from app.auth.dependencies import get_current_user
from app.auth.security import TokenClaims, read_token_claims
from app.core.cache import CacheDep
from app.modules.inventory.database import get_db
from app.modules.telemetry.collector import EventRateLimiter, collect
from app.modules.telemetry.report import ReportPeriod, cache_key, iso_utc, resolve_period
from app.modules.telemetry.schemas import ReportMetrics, ReportPeriodRead, TelemetryBatch, TelemetryBatchResult, TelemetryReport

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Plan §2.4: tope del body del colector, por debajo del límite general.
TELEMETRY_MAX_BODY_BYTES = 64 * 1024
TELEMETRY_EVENTS_PATH = "/telemetry/events"
# Ticket del reporte: dentro de este TTL, la misma combinación no se recalcula.
# Nada lo invalida: el colector escribe a menudo y limpiar anularía la caché.
CACHE_NAMESPACE = "telemetry_report"
CACHE_TTL_SECONDS = 60


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


def _build_report(session: Session, period: ReportPeriod) -> TelemetryReport:
    # `session.connection()`, aquí dentro: un acierto de caché no abre conexión,
    # y Pandas solo acepta una conexión de SQLAlchemy, no una `Session`.
    metrics = all_metrics(session.connection(), period.start, period.end)
    return TelemetryReport(
        period=ReportPeriodRead(from_=iso_utc(period.start), to=iso_utc(period.end)),
        metrics=ReportMetrics.model_validate(metrics),
    )


@router.get(
    "/report",
    response_model=TelemetryReport,
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"description": "Sin token o con uno no válido."},
        422: {"description": "Fechas no válidas, `start_date` ≥ `end_date` o más de 90 días (`validation_error`)."},
        503: {"description": "La base no responde (`storage_unavailable`)."},
    },
)
def read_report(
    session: Annotated[Session, Depends(get_db)],
    cache: CacheDep,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> TelemetryReport:
    period = resolve_period(start_date, end_date, datetime.now(UTC))
    return cache.get_or_set(
        CACHE_NAMESPACE, cache_key(start_date, end_date), CACHE_TTL_SECONDS, lambda: _build_report(session, period)
    )
