"""Validación del CSV de incidentes del helpdesk: esquema, lectura y las 7 reglas.

Contexto funcional: docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md. Extraído de
`packages/incident-analyzer` sin cambiar su comportamiento: el analizador lo
reexporta y el seed del gestor de incidencias lo usa directamente.
"""

from .reader import IncidentFileError, read_rows
from .schema import FIELDS, Category, IncidentRow, Rule, Status
from .validation import ValidationResult, parse_score, validate_row

__all__ = [
    "FIELDS",
    "Category",
    "IncidentFileError",
    "IncidentRow",
    "Rule",
    "Status",
    "ValidationResult",
    "parse_score",
    "read_rows",
    "validate_row",
]
