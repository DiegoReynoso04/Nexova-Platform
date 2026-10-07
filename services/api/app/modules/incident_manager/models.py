"""Modelos de lectura del gestor centralizado de incidencias.

El vocabulario (estados, orígenes, categorías, sedes) y las reglas vienen de
`nexova_shared.incidents` (packages/shared): aquí no se repite ningún valor.
Contexto: docs/centralized-incident-manager.md.
"""

from uuid import UUID

from nexova_shared.incidents import Branch, IncidentCategory, IncidentOrigin, IncidentStatus
from pydantic import AwareDatetime, BaseModel, ConfigDict


class Incident(BaseModel):
    """Una incidencia tal como se guarda y se devuelve. `id` y fechas los genera el repositorio."""

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
