"""Contrato del CSV de incidentes de Nexova.

El esquema (campos, categorías, estados, las 7 reglas, `IncidentRow`) vive en
`nexova_shared.incident_csv.schema` (`packages/shared`), compartido con el seed
del gestor de incidencias; aquí se reexporta para que `incident_analyzer.schema`
siga funcionando. Solo las etiquetas de puntuación, que son del reporte y no de
la validación, se definen en este módulo.

Fuente: docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md.
"""

from typing import Final

from nexova_shared.incident_csv.schema import (
    AGENT_ID_PATTERN,
    FIELDS,
    MIN_DESCRIPTION_LENGTH,
    SCORE_MAX,
    SCORE_MIN,
    SCORE_PATTERN,
    Category,
    IncidentRow,
    Rule,
    Status,
)

SCORE_LABELS: Final[dict[int, str]] = {
    1: "Very dissatisfied",
    2: "Dissatisfied",
    3: "Neutral",
    4: "Satisfied",
    5: "Very satisfied",
}

__all__ = [
    "AGENT_ID_PATTERN",
    "FIELDS",
    "MIN_DESCRIPTION_LENGTH",
    "SCORE_LABELS",
    "SCORE_MAX",
    "SCORE_MIN",
    "SCORE_PATTERN",
    "Category",
    "IncidentRow",
    "Rule",
    "Status",
]
