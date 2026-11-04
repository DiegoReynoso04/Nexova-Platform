"""Tabla `telemetry_events` (ticket de almacenamiento): un evento por fila, inmutable.

El enunciado fija `event_type`, `timestamp`, `service` y `tags`; el resto del
esquema es decisión nuestra (D1 de docs/telemetry/storage-analysis.md). Mapeo
desde el envelope (`TelemetryEvent`, camelCase) a las columnas (snake_case):

- `eventId` → `event_id` (clave primaria: deduplica los reintentos);
- `event_type` → `event_type`;
- `timestamp` → `timestamp`, tras la regla de ±5 min del colector;
- `userId` → `user_id` y `sessionId` → `session_id`, o los del token;
- `schemaVersion` → `schema_version`;
- `properties` → `tags`, filtrado por la allowlist del evento.

`service` no está en el envelope: lo pone siempre el servidor (D2). `requestId`
no se guarda: hoy es un UUID aleatorio por evento (P5 pendiente).

**No entra en `init_db`:** la crea `app/modules/telemetry/migrate.py`, a mano,
para que arrancar la API contra la demo no la cree sin confirmación (D3).
`JSON().with_variant` deja crear la misma tabla en SQLite en los tests.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

TELEMETRY_EVENTS_TABLE = "telemetry_events"
SERVICE_CHECK = "ck_telemetry_events_service"
TAGS_INDEX = "ix_telemetry_events_tags"
# Holgados sobre el valor más largo: 31 caracteres en `event_type`, 10 en `service`.
EVENT_TYPE_MAX_LENGTH = 64
SERVICE_MAX_LENGTH = 16
SCHEMA_VERSION_MAX_LENGTH = 16


class TelemetryService(StrEnum):
    """Quién emitió el evento: por dónde entró a la API, nunca lo que diga el cliente."""

    BACKOFFICE = "backoffice"
    API = "api"


class TelemetryEventRecord(SQLModel, table=True):
    __tablename__ = TELEMETRY_EVENTS_TABLE
    __table_args__ = (
        CheckConstraint(column("service").in_([member.value for member in TelemetryService]), name=SERVICE_CHECK),
        Index(TAGS_INDEX, "tags", postgresql_using="gin"),
    )

    event_id: UUID = Field(primary_key=True)
    event_type: str = Field(max_length=EVENT_TYPE_MAX_LENGTH, index=True)
    timestamp: datetime = Field(sa_type=DateTime(timezone=True), index=True)
    service: TelemetryService = Field(sa_type=String(SERVICE_MAX_LENGTH))
    user_id: UUID | None = Field(default=None)
    session_id: UUID | None = Field(default=None)
    schema_version: str = Field(max_length=SCHEMA_VERSION_MAX_LENGTH)
    tags: dict[str, Any] = Field(sa_type=JSON().with_variant(JSONB(), "postgresql"))
