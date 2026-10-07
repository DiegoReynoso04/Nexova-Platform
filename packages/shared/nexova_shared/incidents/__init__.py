"""Modelo del gestor centralizado de incidencias de Nexova: vocabulario, reglas y mapeo del CSV.

Contexto funcional: docs/centralized-incident-manager.md.
"""

from .csv_mapping import (
    CATEGORY_MAP,
    SEED_BRANCH,
    SEED_ORIGIN,
    STATUS_MAP,
    MappingIssue,
    RowIssue,
    SeedBatch,
    SeedIncident,
    derive_title,
    map_csv_row,
    parse_csv_date,
    prepare_seed_batch,
    source_key,
)
from .rules import (
    ALLOWED_TRANSITIONS,
    FINAL_STATUSES,
    INITIAL_STATUS,
    INPUT_FIELDS,
    FieldError,
    FieldErrorCode,
    IncidentDraft,
    IncidentValidationError,
    can_transition,
    check_transition,
    validate_incident_fields,
)
from .vocabulary import BRANCH_LABELS, TITLE_MAX_LENGTH, Branch, IncidentCategory, IncidentOrigin, IncidentStatus

__all__ = [
    "ALLOWED_TRANSITIONS",
    "BRANCH_LABELS",
    "CATEGORY_MAP",
    "FINAL_STATUSES",
    "INITIAL_STATUS",
    "INPUT_FIELDS",
    "SEED_BRANCH",
    "SEED_ORIGIN",
    "STATUS_MAP",
    "TITLE_MAX_LENGTH",
    "Branch",
    "FieldError",
    "FieldErrorCode",
    "IncidentCategory",
    "IncidentDraft",
    "IncidentOrigin",
    "IncidentStatus",
    "IncidentValidationError",
    "MappingIssue",
    "RowIssue",
    "SeedBatch",
    "SeedIncident",
    "can_transition",
    "check_transition",
    "derive_title",
    "map_csv_row",
    "parse_csv_date",
    "prepare_seed_batch",
    "source_key",
    "validate_incident_fields",
]
