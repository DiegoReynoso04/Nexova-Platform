"""Envelope de telemetría (plan §5) y lote del colector (plan §2.4).

`TelemetryEvent` tiene exactamente las 8 claves del envelope, con los mismos
patrones que `definitions.envelope` de `docs/telemetry/event-schemas.json`
(los nombres van en camelCase, como en el JSON). Se reutiliza sin cambios en
el colector definitivo: la allowlist de cada evento (`properties`) es un paso
posterior al envelope, no parte de él.

Fase del stub: `userId` y `sessionId` llegan del cliente y no se verifican
(un `sendBeacon` no lleva `Authorization`); el colector definitivo los
sustituirá por los del token cuando la petición traiga uno válido.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.modules.telemetry.catalog import EVENT_TYPES, SCHEMA_VERSION

# Mismos patrones que el envelope del JSON (UUID v4 en minúsculas, ISO con ms y `Z`).
# `[0-9]` en lugar del `\d` del JSON: la API no lleva `\d` en sus literales
# (tests/test_architecture.py), y en Pydantic `\d` admitiría dígitos Unicode.
UUID_V4_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
TIMESTAMP_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"
EVENT_TYPE_PATTERN = r"^[a-z]+(_[a-z]+)+$"
# Plan §2.4: de 1 a 50 eventos por lote.
MAX_EVENTS_PER_BATCH = 50

UuidV4 = Annotated[str, Field(pattern=UUID_V4_PATTERN)]

_EVENT_TYPES = frozenset(EVENT_TYPES)
_EXAMPLE_EVENT = {
    "eventId": "7735fc60-41a3-44d8-83a6-35daa9f5353f",
    "timestamp": "2026-11-02T09:15:42.318Z",
    "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
    "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
    "event_type": "page_viewed",
    "schemaVersion": SCHEMA_VERSION,
    "requestId": "d3b44331-fd6b-4796-8798-0b6d0edd1bb3",
    "properties": {"route_template": "/inventory/products", "previous_route_template": "/", "entry": "in_app_navigation"},
}


class TelemetryEvent(BaseModel):
    """Un evento con el envelope del plan (§5): las 8 claves, ni una más."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    eventId: UuidV4
    timestamp: Annotated[str, Field(pattern=TIMESTAMP_PATTERN)]
    sessionId: UuidV4 | None
    userId: UuidV4 | None
    event_type: Annotated[str, Field(pattern=EVENT_TYPE_PATTERN)]
    # Igual que `catalog.SCHEMA_VERSION` (lo comprueba la suite).
    schemaVersion: Literal["1.0.0"]
    requestId: UuidV4 | None
    properties: dict[str, JsonValue]

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, value: str) -> str:
        # Fase del stub: cualquier evento del catálogo. El colector definitivo
        # solo aceptará los de emisor frontend (plan §2.4).
        if value not in _EVENT_TYPES:
            raise ValueError("event_type is not in the telemetry catalog")
        return value


class TelemetryBatch(BaseModel):
    """`POST /telemetry/events`: un lote de 1 a 50 eventos."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"events": [_EXAMPLE_EVENT]}]})

    events: list[TelemetryEvent] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)


class TelemetryBatchReceived(BaseModel):
    """Respuesta del stub: cuántos eventos traía el lote."""

    model_config = ConfigDict(frozen=True)

    received: int
