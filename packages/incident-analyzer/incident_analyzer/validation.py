"""Las 7 reglas de registros inválidos del documento de contexto.

Viven en `nexova_shared.incident_csv.validation` (`packages/shared`),
compartidas con el seed del gestor de incidencias; aquí solo se reexportan.
"""

from nexova_shared.incident_csv.validation import ValidationResult, parse_score, validate_row

__all__ = ["ValidationResult", "parse_score", "validate_row"]
