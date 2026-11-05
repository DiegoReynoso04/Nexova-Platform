"""Emisor mínimo de la API (ticket de captura, D1 «A ligera») y derivados del plan.

La API solo emite lo que la interfaz no puede provocar: `direct_stock_edit_rejected`
(P7). El resto de eventos obligatorios los emite el frontend con lo que le
devuelve la API; los derivados que necesita (`supplier_key`, `currency`, la
oficina en minúsculas) se calculan aquí para que no se repitan.

`emit` construye el envelope del plan (§5), lo escribe con
`app.core.telemetry.log_event` y lo entrega a `sink` (el guardado en la tabla,
D8). Nunca lanza.
"""

import hashlib
import hmac
import time
import unicodedata
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from uuid import uuid4

from app.core.telemetry import log_event
from app.modules.inventory.vocabulary import OFFICE_CURRENCY, Currency, Office
from app.modules.telemetry.catalog import SCHEMA_VERSION

# Plan §7.2: un evento por clave y ventana.
THROTTLE_WINDOW_SECONDS = 60.0


def utc_timestamp(now: datetime | None = None) -> str:
    """ISO 8601 en UTC con milisegundos y `Z`, como exige el envelope."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def office_label(office: Office) -> str:
    """D6: la oficina en minúsculas (`Valencia` → `valencia`)."""
    return office.value.lower()


def office_currency(office: Office) -> Currency:
    """BRIEFING §6: la moneda es la de la oficina; nunca se convierte."""
    return OFFICE_CURRENCY[office]


def normalize_supplier(text: str) -> str:
    """P9: NFKC, recorte, minúsculas y espacios internos colapsados a uno."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def supplier_key(secret: str, supplier: str) -> str | None:
    """P9: HMAC-SHA256 en hex del proveedor normalizado; `None` sin clave configurada."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), normalize_supplier(supplier).encode("utf-8"), hashlib.sha256).hexdigest()


class Throttle:
    """Throttle en memoria del proceso (plan §7.2; válido con `--workers 1`).

    El primer evento de una clave sale; los que llegan dentro de la ventana se
    cuentan y su recuento viaja en el `suppressed_count` del siguiente que sale.
    """

    def __init__(self, window_seconds: float = THROTTLE_WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self.window_seconds = window_seconds
        self.clock = clock
        self._windows: dict[tuple[str, ...], tuple[float, int]] = {}

    def admit(self, key: tuple[str, ...]) -> int | None:
        """`suppressed_count` si el evento sale ahora; `None` si se descarta."""
        now = self.clock()
        started, suppressed = self._windows.get(key, (float("-inf"), 0))
        if now - started < self.window_seconds:
            self._windows[key] = (started, suppressed + 1)
            return None
        self._windows[key] = (now, 0)
        return suppressed


def emit(
    event_type: str,
    properties: Mapping[str, object],
    *,
    user_id: str | None,
    session_id: str | None,
    request_id: str | None = None,
    sink: Callable[[Mapping[str, object]], None] | None = None,
) -> None:
    """Escribe un evento con el envelope del plan. `requestId` propio si no hay `X-Request-ID` (P5 pendiente)."""
    try:
        event = {
            "eventId": str(uuid4()),
            "timestamp": utc_timestamp(),
            "sessionId": session_id,
            "userId": user_id,
            "event_type": event_type,
            "schemaVersion": SCHEMA_VERSION,
            "requestId": request_id or str(uuid4()),
            "properties": dict(properties),
        }
        log_event(event)
        if sink is not None:
            sink(event)
    except Exception:  # noqa: BLE001 — la telemetría nunca rompe la petición
        return
