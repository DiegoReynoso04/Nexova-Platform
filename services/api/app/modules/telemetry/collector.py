"""Colector de telemetría: de un item crudo a una fila de `telemetry_events`.

`TelemetryEvent` solo valida el envelope (no se modifica). Lo que el plan pide
al colector es un paso posterior, aquí (docs/telemetry/storage-analysis.md, C2):

1. envelope (`TelemetryEvent.model_validate`);
2. emisor frontend (plan §2.4), solo en lo que llega por HTTP;
3. fecha real: el patrón deja pasar `2026-13-45T99:99:99.000Z` (C4);
4. `userId` y `sessionId`, los del token si la petición trae uno válido;
5. allowlist: una clave de más se quita y un valor inválido rechaza el evento
   (D6). Además de la privacidad, protege el lote: `NaN` o `\\u0000` harían
   fallar el único insert y con él a todos los demás eventos (C4);
6. `timestamp`: el del cliente a ±5 min de la recepción; si no, el de recepción.

Un evento rechazado no cancela el lote y nunca se registra su contenido. Si la
base falla, la excepción sigue su camino: 503 `storage_unavailable` y el
frontend reintenta (D10). La tabla no se actualiza ni se borra desde aquí.
"""

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, JsonValue, StrictBool, TypeAdapter, ValidationError
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlmodel import Session

from app.auth.security import TokenClaims
from app.core.telemetry import log_batch_stored, log_event_not_stored
from app.modules.telemetry.allowlists import EVENT_ALLOWLISTS, EventAllowlist
from app.modules.telemetry.catalog import FRONTEND_EVENT_TYPES
from app.modules.telemetry.models import TelemetryEventRecord, TelemetryService
from app.modules.telemetry.schemas import MAX_EVENTS_PER_BATCH, TelemetryBatchResult, TelemetryEvent, UuidV4

# Plan §2.4: desviación máxima del reloj del cliente.
TIMESTAMP_MAX_DRIFT = timedelta(minutes=5)
# Plan §7.2: eventos por minuto, por token o en total para los anónimos.
EVENTS_PER_WINDOW = 120
RATE_WINDOW_SECONDS = 60.0
ANONYMOUS_KEY = "anonymous"

_TABLE = TelemetryEventRecord.__table__  # type: ignore[attr-defined]
_UUID_V4 = TypeAdapter(UuidV4)

Row = dict[str, object]


class EventRateLimiter:
    """Ventana fija por clave, en memoria del proceso (plan §8.4: `--workers 1`).

    `Throttle` de `emitter.py` no sirve: deja pasar uno por ventana y aquí se
    cuentan eventos. Las claves son `sub` de tokens firmados o `anonymous`: un
    cliente no puede crear claves nuevas. La ruta corre en el threadpool: lleva lock.
    """

    def __init__(
        self,
        limit: int = EVENTS_PER_WINDOW,
        window_seconds: float = RATE_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def take(self, key: str, wanted: int) -> int:
        """Cuántos de los `wanted` eventos caben en la ventana actual; los gasta."""
        with self._lock:
            now = self.clock()
            started, used = self._windows.get(key, (now, 0))
            if now - started >= self.window_seconds:
                started, used = now, 0
            granted = max(0, min(wanted, self.limit - used))
            self._windows[key] = (started, used + granted)
            return granted


def _unique(values: list[object]) -> list[object]:
    if len(set(map(repr, values))) != len(values):
        raise ValueError("repeated items")
    return values


def _annotation(spec: Mapping[str, object]) -> object:
    """El esquema JSON de una propiedad como tipo de Pydantic (los patrones, sin `re`)."""
    enum = spec.get("enum")
    if isinstance(enum, list):
        return Literal[tuple(enum)]  # type: ignore[valid-type]
    declared = spec["type"]
    names = declared if isinstance(declared, list) else [declared]
    limits: dict[str, object] = {}
    for keyword, name in (("minimum", "ge"), ("maximum", "le"), ("exclusiveMinimum", "gt"), ("maxLength", "max_length"), ("pattern", "pattern")):
        if keyword in spec:
            limits[name] = spec[keyword]
    base: object
    if "integer" in names:
        base = Annotated[int, Field(strict=True, **limits)]  # type: ignore[arg-type]
    elif "number" in names:
        base = Annotated[float, Field(strict=True, allow_inf_nan=False, **limits)]  # type: ignore[arg-type]
    elif "string" in names:
        base = Annotated[str, Field(strict=True, **limits)]  # type: ignore[arg-type]
    elif "boolean" in names:
        base = StrictBool
    else:
        items = spec["items"]
        assert isinstance(items, Mapping)
        base = Annotated[list[_annotation(items)], Field(max_length=spec["maxItems"]), AfterValidator(_unique)]  # type: ignore[misc]
    return base | None if "null" in names else base  # type: ignore[operator]


_ADAPTERS: Mapping[str, Mapping[str, TypeAdapter[object]]] = {
    event_type: {key: TypeAdapter(_annotation(spec)) for key, spec in allowlist.properties.items()}
    for event_type, allowlist in EVENT_ALLOWLISTS.items()
}


def _allowed_properties(event: TelemetryEvent, allowlist: EventAllowlist) -> dict[str, JsonValue] | None:
    """`properties` solo con las claves de la allowlist, o `None` si falta una o un valor no vale."""
    allowed: dict[str, JsonValue] = {}
    for key, adapter in _ADAPTERS[event.event_type].items():
        if key not in event.properties:
            return None
        try:
            adapter.validate_python(event.properties[key])
        except ValidationError:
            return None
        allowed[key] = event.properties[key]
    if allowlist.office_currency and (allowed["office"], allowed["currency"]) not in allowlist.office_currency:
        return None
    return allowed


def _trusted(value: str | None) -> str | None:
    """Un id del token solo si cumple el patrón del envelope (va a una columna `UUID`)."""
    try:
        return _UUID_V4.validate_python(value)
    except ValidationError:
        return None


def _timestamp(event: TelemetryEvent, received_at: datetime) -> datetime | None:
    try:
        moment = datetime.fromisoformat(event.timestamp)
    except ValueError:
        return None
    return moment if abs(moment - received_at) <= TIMESTAMP_MAX_DRIFT else received_at


def build_row(event: TelemetryEvent, service: TelemetryService, received_at: datetime, claims: TokenClaims | None = None) -> Row | None:
    """La fila de un evento con el envelope válido, o `None` si hay que rechazarlo."""
    allowlist = EVENT_ALLOWLISTS.get(event.event_type)
    if allowlist is None or event.requestId is None:
        return None
    moment = _timestamp(event, received_at)
    if moment is None:
        return None
    user_id, session_id = event.userId, event.sessionId
    if claims is not None and _trusted(claims.sub) is not None:
        user_id, session_id = claims.sub, _trusted(claims.sid)
    if allowlist.identity_required and (user_id is None or session_id is None):
        return None
    tags = _allowed_properties(event, allowlist)
    if tags is None:
        return None
    return {
        "event_id": UUID(event.eventId),
        "event_type": event.event_type,
        "timestamp": moment,
        "service": service.value,
        "user_id": UUID(user_id) if user_id is not None else None,
        "session_id": UUID(session_id) if session_id is not None else None,
        "schema_version": event.schemaVersion,
        "tags": tags,
    }


def _frontend_row(raw: JsonValue, received_at: datetime, claims: TokenClaims | None) -> tuple[Row, int] | None:
    """La fila de un item del lote y cuántas claves se le quitaron, o `None` si se rechaza."""
    try:
        event = TelemetryEvent.model_validate(raw)
    except ValidationError:
        return None
    if event.event_type not in FRONTEND_EVENT_TYPES:
        return None
    row = build_row(event, TelemetryService.BACKOFFICE, received_at, claims)
    if row is None:
        return None
    tags = row["tags"]
    assert isinstance(tags, dict)
    return row, len(event.properties) - len(tags)


def insert_statement(rows: Sequence[Row]) -> Insert:
    """Un único `INSERT` de varias filas. `ON CONFLICT DO NOTHING` absorbe los reintentos.

    Se usa `values(rows)` y no `execute(insert, rows)`, que sería un `executemany`.
    La misma sentencia compila en SQLite, así que los tests prueban este camino.
    """
    return insert(_TABLE).values(list(rows)).on_conflict_do_nothing(index_elements=["event_id"])


def store_rows(session: Session, rows: Sequence[Row]) -> int:
    """Una sola sentencia por lote. Devuelve las filas nuevas (sin los duplicados).

    `session.connection()`: `Session.execute` está en desuso en SQLModel.
    """
    inserted = session.connection().execute(insert_statement(rows)).rowcount
    session.commit()
    return inserted


def collect(
    events: Sequence[JsonValue],
    *,
    session: Session,
    limiter: EventRateLimiter,
    claims: TokenClaims | None,
    received_at: datetime | None = None,
) -> TelemetryBatchResult:
    """Valida cada item por separado y guarda los válidos con un solo insert.

    Se procesan los `MAX_EVENTS_PER_BATCH` primeros; el resto cuenta como rechazado (D11).
    """
    moment = received_at or datetime.now(UTC)
    prepared = [item for raw in events[:MAX_EVENTS_PER_BATCH] if (item := _frontend_row(raw, moment, claims)) is not None]
    granted = limiter.take(claims.sub if claims is not None else ANONYMOUS_KEY, len(prepared))
    accepted = prepared[:granted]
    rows = [row for row, _ in accepted]
    inserted = store_rows(session, rows) if rows else 0
    log_batch_stored(
        received=len(events),
        stored=len(rows),
        rejected=len(events) - len(rows),
        duplicates=len(rows) - inserted,
        dropped_keys=sum(dropped for _, dropped in accepted),
        event_types=[str(row["event_type"]) for row in rows],
    )
    return TelemetryBatchResult(received=len(events), stored=len(rows), rejected=len(events) - len(rows))


def store_api_event(engine: Engine, event: Mapping[str, object]) -> None:
    """Guarda un evento que emite la propia API (D8). Nunca lanza ni cambia la respuesta.

    Misma validación y misma función de guardado que el colector. Si falla, el
    evento queda solo en la línea de `nexova.telemetry`, ya escrita.
    """
    try:
        now = datetime.now(UTC)
        row = build_row(TelemetryEvent.model_validate(event), TelemetryService.API, now)
        if row is None:
            log_event_not_stored("invalid event")
            return
        with Session(engine) as session:
            store_rows(session, [row])
    except Exception as exc:  # noqa: BLE001 — la telemetría nunca rompe la petición
        log_event_not_stored(type(exc).__name__)
