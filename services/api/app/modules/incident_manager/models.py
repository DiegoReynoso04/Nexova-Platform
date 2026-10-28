"""Modelos del gestor centralizado de incidencias: documento, respuestas y contrato de entrada.

El vocabulario (estados, orígenes, categorías, sedes) y las reglas vienen de
`nexova_shared.incidents` (packages/shared): aquí no se repite ningún valor.
Contexto: docs/centralized-incident-manager.md.

Auditoría de serialización (docs/serialization-audit.md, D4–D6 y D8):

- `Incident` es el documento de TinyDB; las rutas responden `IncidentRead`
  (detalle, alta y cambio de estado) o `IncidentListItem` (listado, sin
  `updated_at`, que la tabla no usa).
- `IncidentCreateRequest` e `IncidentStatusChangeRequest` son el **contrato
  publicado** de las escrituras en OpenAPI. **No validan**: la autoridad es
  `nexova_shared` (`validate_incident_fields`, `validate_status_change`), que
  produce los códigos del 400 de la Parte E (`missing`, `blank`, `too_long`,
  `invalid_type`, `invalid_choice`, `unknown_field`), los mismos que usa el
  seed. Validar con Pydantic cambiaría esos códigos (opción C descartada). Un
  test comprueba que los dos describen los mismos campos.
"""

from typing import Annotated, Literal
from uuid import UUID

from nexova_shared.incidents import (
    TITLE_MAX_LENGTH,
    Branch,
    FieldErrorCode,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
)
from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints


class Incident(BaseModel):
    """Una incidencia tal como se guarda. `id` y fechas los genera el repositorio. Uso interno."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    description: str
    category: IncidentCategory
    status: IncidentStatus
    origin: IncidentOrigin
    branch: Branch
    created_at: AwareDatetime
    updated_at: AwareDatetime

    def public(self) -> "IncidentRead":
        return IncidentRead(
            id=self.id,
            title=self.title,
            description=self.description,
            category=self.category,
            status=self.status,
            origin=self.origin,
            branch=self.branch,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def list_item(self) -> "IncidentListItem":
        return IncidentListItem(
            id=self.id,
            title=self.title,
            description=self.description,
            category=self.category,
            status=self.status,
            origin=self.origin,
            branch=self.branch,
            created_at=self.created_at,
        )


class IncidentRead(BaseModel):
    """Respuesta de `GET /api/incidents/{id}`, `POST /api/incidents` y `PATCH …/status`."""

    id: UUID
    title: str
    description: str
    category: IncidentCategory
    status: IncidentStatus
    origin: IncidentOrigin
    branch: Branch
    created_at: AwareDatetime
    updated_at: AwareDatetime


class IncidentListItem(BaseModel):
    """Una fila de `GET /api/incidents`: lo que muestra la tabla, sin `updated_at` (D5)."""

    id: UUID
    title: str
    description: str
    category: IncidentCategory
    status: IncidentStatus
    origin: IncidentOrigin
    branch: Branch
    created_at: AwareDatetime


class IncidentCreateRequest(BaseModel):
    """Contrato publicado de `POST /api/incidents`. Solo documenta: valida `nexova_shared`."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(min_length=1, max_length=TITLE_MAX_LENGTH)]
    description: Annotated[str, StringConstraints(min_length=1)]
    category: IncidentCategory
    origin: IncidentOrigin
    branch: Branch
    # Opcional; al crear solo se admite el estado inicial (P4-8).
    status: Literal[IncidentStatus.OPEN] | None = None


class IncidentStatusChangeRequest(BaseModel):
    """Contrato publicado de `PATCH /api/incidents/{id}/status`. Solo documenta: valida `nexova_shared`."""

    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus


class IncidentFieldError(BaseModel):
    """Un problema de un campo en el 400 del gestor (SPECS §31). `message` nunca repite el valor."""

    field: str
    error: FieldErrorCode
    message: str


class IncidentValidationErrorResponse(BaseModel):
    """400 `validation_error` o `invalid_status_transition`. Solo documenta OpenAPI."""

    detail: list[IncidentFieldError]
    code: str


class IncidentErrorResponse(BaseModel):
    """Resto de errores del gestor (`{detail, code}`: 401, 404, 503). Solo documenta OpenAPI."""

    detail: str
    code: str


class IncidentSummary(BaseModel):
    """Totales por estado, categoría, origen y sede.

    Cada diccionario tiene siempre todas las claves de su enumerado, en el
    orden del CONTEXT, aunque valgan 0 (también con la base vacía).
    """

    model_config = ConfigDict(frozen=True)

    total: int
    by_status: dict[IncidentStatus, int]
    by_category: dict[IncidentCategory, int]
    by_origin: dict[IncidentOrigin, int]
    by_branch: dict[Branch, int]
