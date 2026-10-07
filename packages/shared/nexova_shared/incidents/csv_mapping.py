"""Transformación del CSV del helpdesk al modelo `Incident` (seed de datos históricos).

Fuente: docs/centralized-incident-manager.md ("Datos históricos — seed desde
CSV": mapeo directo de campos, mapeo de estados y de categorías, campo
identificador para idempotencia).

Cada fila pasa primero por las 7 reglas del analizador (`incident_csv`) y
después por las reglas del modelo (`rules`): nunca se inserta una fila del CSV
tal cual. Ninguna estructura de este módulo expone en `repr` valores de la
fila, y `customer_email`, `client_company`, `agent_id` y `satisfaction_score`
no pasan al modelo.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from ..incident_csv import Category, IncidentRow, Status, ValidationResult, read_rows, validate_row
from .rules import IncidentDraft, IncidentValidationError, validate_incident_fields
from .vocabulary import TITLE_MAX_LENGTH, Branch, IncidentCategory, IncidentOrigin, IncidentStatus

STATUS_MAP: Final[Mapping[Status, IncidentStatus]] = MappingProxyType(
    {
        Status.OPEN: IncidentStatus.OPEN,
        Status.CLOSED: IncidentStatus.RESOLVED,
        Status.DISCARDED: IncidentStatus.DISCARDED,
    }
)
CATEGORY_MAP: Final[Mapping[Category, IncidentCategory]] = MappingProxyType(
    {
        Category.TECHNICAL: IncidentCategory.TECHNICAL_FAILURE,
        Category.BILLING: IncidentCategory.PROCESS_ERROR,
        Category.ACCESS: IncidentCategory.TECHNICAL_FAILURE,
        Category.HR_QUERY: IncidentCategory.PROCESS_ERROR,
        Category.COMPLAINT: IncidentCategory.CLIENT_COMPLAINT,
    }
)
# Todas las filas del histórico son quejas de clientes corporativos, y el CSV
# no tiene campo de oficina.
SEED_ORIGIN: Final = IncidentOrigin.CUSTOMER
SEED_BRANCH: Final = Branch.CENTRAL

# `YYYY-MM-DD` exacto: `date.fromisoformat` acepta además otras formas ISO
# (`20260801`, `2026-W31-6`) que el CONTEXT no contempla.
_CSV_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
_TICKET_ID_KEY = "ticket_id"
_FALLBACK_KEY = "title_created_at"


class MappingIssue(StrEnum):
    """Por qué una fila que cumple las 7 reglas del analizador no se puede cargar."""

    UNMAPPED_STATUS = "unmapped_status"
    UNMAPPED_CATEGORY = "unmapped_category"
    INVALID_DATE = "invalid_date"
    EMPTY_TITLE = "empty_title"
    INVALID_FIELDS = "invalid_fields"


@dataclass(frozen=True, slots=True, repr=False)
class SeedIncident:
    """Una fila ya transformada, lista para insertar. `updated_at` = `created_at` al insertar."""

    row_number: int
    source_key: str
    draft: IncidentDraft
    created_at: datetime

    def __repr__(self) -> str:
        return f"SeedIncident(row_number={self.row_number})"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class RowIssue:
    """Número de fila + motivos. Sin valores: seguro de mostrar en consola."""

    row_number: int
    issues: frozenset[MappingIssue]


@dataclass(frozen=True, slots=True)
class SeedBatch:
    """Resultado de preparar un CSV completo. Cada fila acaba en una sola de las cuatro listas."""

    total_rows: int
    incidents: tuple[SeedIncident, ...]
    invalid: tuple[ValidationResult, ...]
    unmapped: tuple[RowIssue, ...]
    # Filas cuyo identificador ya apareció antes en el mismo archivo.
    duplicates: tuple[int, ...]


def derive_title(description: str) -> str:
    """Primeros 120 caracteres de `description`, recortados (puede quedar vacío)."""
    return description[:TITLE_MAX_LENGTH].strip()


def parse_csv_date(raw: str) -> datetime | None:
    """`YYYY-MM-DD` como medianoche UTC; `None` si el formato o la fecha no son válidos."""
    if not _CSV_DATE.fullmatch(raw):
        return None
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        return None
    return datetime.combine(day, time.min, tzinfo=UTC)


def source_key(ticket_id: str, title: str, created_at: datetime) -> str:
    """Identificador del registro de origen para la idempotencia del seed.

    `ticket_id` si viene informado; si no, `title + created_at`. El título va
    resumido con SHA-256 porque la clave se guarda y puede acabar en consola.
    """
    if ticket_id:
        return f"{_TICKET_ID_KEY}:{ticket_id}"
    digest = hashlib.sha256(f"{title}\n{created_at.isoformat()}".encode()).hexdigest()
    return f"{_FALLBACK_KEY}:{digest}"


def map_csv_row(row: IncidentRow) -> SeedIncident | RowIssue:
    """Aplica el mapeo del CONTEXT a una fila. No comprueba las 7 reglas del analizador."""
    issues: set[MappingIssue] = set()
    # Los miembros de un StrEnum son `str`: se buscan directamente por el valor del CSV.
    status = STATUS_MAP.get(row.status)
    if status is None:
        issues.add(MappingIssue.UNMAPPED_STATUS)
    category = CATEGORY_MAP.get(row.category)
    if category is None:
        issues.add(MappingIssue.UNMAPPED_CATEGORY)
    created_at = parse_csv_date(row.date)
    if created_at is None:
        issues.add(MappingIssue.INVALID_DATE)
    title = derive_title(row.description)
    if not title:
        issues.add(MappingIssue.EMPTY_TITLE)
    if issues:
        return RowIssue(row.row_number, frozenset(issues))
    assert created_at is not None

    try:
        draft = validate_incident_fields(
            {
                "title": title,
                "description": row.description,
                "category": category,
                "status": status,
                "origin": SEED_ORIGIN,
                "branch": SEED_BRANCH,
            },
            allowed_statuses=tuple(IncidentStatus),
        )
    except IncidentValidationError:
        return RowIssue(row.row_number, frozenset({MappingIssue.INVALID_FIELDS}))
    return SeedIncident(row.row_number, source_key(row.ticket_id, title, created_at), draft, created_at)


def prepare_seed_batch(lines: Iterable[str]) -> SeedBatch:
    """Lee el CSV (mismo esquema y lector que el analizador), valida y transforma cada fila.

    Espera líneas ya decodificadas y abiertas con `newline=""`. Lanza
    `IncidentFileError` si el archivo no se puede leer (cabecera incompleta,
    CSV malformado), igual que el analizador.
    """
    incidents: list[SeedIncident] = []
    invalid: list[ValidationResult] = []
    unmapped: list[RowIssue] = []
    duplicates: list[int] = []
    seen_keys: set[str] = set()
    total_rows = 0

    for row in read_rows(lines):
        total_rows += 1
        validation = validate_row(row)
        if not validation.is_valid:
            invalid.append(validation)
            continue
        mapped = map_csv_row(row)
        if isinstance(mapped, RowIssue):
            unmapped.append(mapped)
        elif mapped.source_key in seen_keys:
            duplicates.append(mapped.row_number)
        else:
            seen_keys.add(mapped.source_key)
            incidents.append(mapped)

    return SeedBatch(total_rows, tuple(incidents), tuple(invalid), tuple(unmapped), tuple(duplicates))
