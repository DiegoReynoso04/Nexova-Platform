"""Colector de telemetría, fase stub: `POST /telemetry/events`.

Solo valida el formato (`TelemetryBatch`), registra cuántos eventos llegan y
de qué tipo, y responde `200 {"received": N}`. **No persiste nada:** la
persistencia es del ticket de almacenamiento, que sustituirá esta ruta sin
que el frontend cambie (el frontend no lee el cuerpo de la respuesta).

Sin autenticación a propósito: `navigator.sendBeacon` (el envío al ocultar la
pestaña) no puede llevar `Authorization`, y un 401 haría que el cliente del
backoffice cerrase la sesión. Límites: 1–50 eventos por lote (schema) y
64 KiB de body (`BodySizeLimitMiddleware`, por ruta).
"""

from fastapi import APIRouter

from app.core.telemetry import log_batch_received
from app.modules.telemetry.schemas import TelemetryBatch, TelemetryBatchReceived

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Plan §2.4: tope del body del colector, por debajo del límite general.
TELEMETRY_MAX_BODY_BYTES = 64 * 1024
TELEMETRY_EVENTS_PATH = "/telemetry/events"


@router.post(
    "/events",
    response_model=TelemetryBatchReceived,
    responses={413: {"description": "El body supera 64 KiB (`file_too_large`)."}},
)
def receive_events(batch: TelemetryBatch) -> TelemetryBatchReceived:
    log_batch_received([event.event_type for event in batch.events])
    return TelemetryBatchReceived(received=len(batch.events))
