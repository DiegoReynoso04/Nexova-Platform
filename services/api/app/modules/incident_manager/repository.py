"""Acceso a TinyDB del gestor centralizado de incidencias.

Un único archivo JSON (`Settings.incidents_db_path`, por defecto
`services/api/data/incidents.json`, ignorado por git) con dos tablas:

- `incidents`: las incidencias. `id` es un UUID v4 propio (no el `doc_id` de
  TinyDB); `created_at` y `updated_at` los genera este repositorio en UTC.
- `seed_keys`: una fila por registro del CSV histórico ya cargado, con el
  SHA-256 de su clave de origen y el `id` de la incidencia creada. Solo sirve
  para que el seed sea idempotente; no forma parte del modelo `Incident` y el
  `ticket_id` nunca se guarda en claro (el CONTEXT dice que no se almacena).

Mismo patrón que proveedores y usuarios: `threading.Lock`, la base se abre y
se cierra en cada operación y la API se ejecuta con un único worker. Las
lecturas no crean el archivo: sin base, devuelven una lista vacía y totales a
cero.

Solo recibe datos ya validados por `nexova_shared.incidents` (`IncidentDraft`,
`SeedIncident`): no reimplementa ninguna regla del modelo.
"""

import threading
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

from nexova_shared.incidents import (
    Branch,
    FieldError,
    IncidentCategory,
    IncidentDraft,
    IncidentOrigin,
    IncidentStatus,
    SeedIncident,
    check_transition,
)
from tinydb import TinyDB
from tinydb.table import Document, Table

from .models import Incident, IncidentSummary

INCIDENTS_TABLE = "incidents"
SEED_KEYS_TABLE = "seed_keys"

_Value = TypeVar("_Value", bound=StrEnum)


def utc_now() -> datetime:
    return datetime.now(UTC)


class InvalidStatusTransitionError(ValueError):
    """La transición pedida no está en el ciclo de vida. `error` identifica el campo y el motivo."""

    def __init__(self, error: FieldError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True, slots=True)
class SeedResult:
    inserted: int
    # Registros cuya clave de origen ya estaba cargada (ejecuciones anteriores).
    existing: int
    # Incidencias en la base después del seed (incluidas las creadas por la API).
    total: int


class IncidentRepository:
    def __init__(self, path: Path, clock: Callable[[], datetime] = utc_now) -> None:
        self.path = path
        self._clock = clock
        self._lock = threading.Lock()

    @contextmanager
    def _db(self) -> Iterator[TinyDB]:
        with self._lock, TinyDB(self.path, create_dirs=True, encoding="utf-8", indent=2) as db:
            yield db

    def _documents(self) -> list[Document]:
        """Todas las incidencias, sin crear el archivo si aún no existe."""
        with self._lock:
            if not self.path.exists():
                return []
            with TinyDB(self.path, encoding="utf-8") as db:
                return db.table(INCIDENTS_TABLE).all()

    def find(
        self,
        *,
        status: IncidentStatus | None = None,
        origin: IncidentOrigin | None = None,
        branch: Branch | None = None,
        category: IncidentCategory | None = None,
    ) -> list[Incident]:
        """Incidencias que cumplen todos los filtros indicados (AND), de la más reciente a la más antigua."""
        incidents = [
            incident
            for incident in map(_to_incident, self._documents())
            if (status is None or incident.status == status)
            and (origin is None or incident.origin == origin)
            and (branch is None or incident.branch == branch)
            and (category is None or incident.category == category)
        ]
        # `id` desempata: el orden es estable aunque varias compartan fecha (el seed usa medianoche).
        return sorted(incidents, key=lambda incident: (incident.created_at, str(incident.id)), reverse=True)

    def get(self, incident_id: UUID) -> Incident | None:
        for document in self._documents():
            if document["id"] == str(incident_id):
                return _to_incident(document)
        return None

    def create(self, draft: IncidentDraft) -> Incident:
        now = self._clock()
        incident = _build(draft, created_at=now, updated_at=now)
        with self._db() as db:
            db.table(INCIDENTS_TABLE).insert(_to_document(incident))
        return incident

    def change_status(self, incident_id: UUID, target: IncidentStatus) -> Incident | None:
        """Aplica una transición del ciclo de vida y actualiza `updated_at`.

        `None` si la incidencia no existe; `InvalidStatusTransitionError` si la
        transición no está permitida (no se modifica nada).
        """
        with self._db() as db:
            table = db.table(INCIDENTS_TABLE)
            document = _find_document(table, incident_id)
            if document is None:
                return None
            current = _to_incident(document)
            error = check_transition(current.status, target)
            if error is not None:
                raise InvalidStatusTransitionError(error)
            updated = current.model_copy(update={"status": target, "updated_at": self._clock()})
            table.update(_to_document(updated), doc_ids=[document.doc_id])
        return updated

    def summary(self) -> IncidentSummary:
        incidents = [_to_incident(document) for document in self._documents()]
        return IncidentSummary(
            total=len(incidents),
            by_status=_count(IncidentStatus, (incident.status for incident in incidents)),
            by_category=_count(IncidentCategory, (incident.category for incident in incidents)),
            by_origin=_count(IncidentOrigin, (incident.origin for incident in incidents)),
            by_branch=_count(Branch, (incident.branch for incident in incidents)),
        )

    def seed(self, incidents: Iterable[SeedIncident]) -> SeedResult:
        """Inserta los registros históricos cuya clave de origen aún no está cargada. Idempotente.

        `created_at` viene del CSV y `updated_at` es igual al insertar (CONTEXT).
        Todo ocurre en una sola operación bajo el lock.
        """
        new_incidents: list[dict[str, Any]] = []
        new_keys: list[dict[str, Any]] = []
        existing = 0
        with self._db() as db:
            incidents_table = db.table(INCIDENTS_TABLE)
            keys_table = db.table(SEED_KEYS_TABLE)
            loaded = {document["key_sha256"] for document in keys_table.all()}
            for seed_incident in incidents:
                if seed_incident.source_key in loaded:
                    existing += 1
                    continue
                incident = _build(
                    seed_incident.draft, created_at=seed_incident.created_at, updated_at=seed_incident.created_at
                )
                loaded.add(seed_incident.source_key)
                new_incidents.append(_to_document(incident))
                new_keys.append({"key_sha256": seed_incident.source_key, "incident_id": str(incident.id)})
            incidents_table.insert_multiple(new_incidents)
            keys_table.insert_multiple(new_keys)
            total = len(incidents_table)
        return SeedResult(inserted=len(new_incidents), existing=existing, total=total)


def _build(draft: IncidentDraft, *, created_at: datetime, updated_at: datetime) -> Incident:
    return Incident(
        id=uuid4(),
        title=draft.title,
        description=draft.description,
        category=draft.category,
        status=draft.status,
        origin=draft.origin,
        branch=draft.branch,
        created_at=created_at,
        updated_at=updated_at,
    )


def _find_document(table: Table, incident_id: UUID) -> Document | None:
    for document in table.all():
        if document["id"] == str(incident_id):
            return document
    return None


def _to_document(incident: Incident) -> dict[str, Any]:
    return incident.model_dump(mode="json")


def _to_incident(document: Document) -> Incident:
    return Incident.model_validate(dict(document))


def _count(values: type[_Value], found: Iterable[_Value]) -> dict[_Value, int]:
    counts = Counter(found)
    return {value: counts[value] for value in values}
