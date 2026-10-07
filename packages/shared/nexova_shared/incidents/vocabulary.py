"""Vocabulario del gestor centralizado de incidencias de Nexova.

Fuente: docs/centralized-incident-manager.md ("Oficinas de Nexova", "Categorías
de incidencias", "Estados y ciclo de vida", "Orígenes", "Mapeo directo de
campos"). Todo literal de este módulo sale de ese documento;
`tests/test_contract.py` lo comprueba contra el propio archivo.
"""

from enum import StrEnum
from typing import Final


class IncidentStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISCARDED = "discarded"


class IncidentOrigin(StrEnum):
    CUSTOMER = "customer"
    BRANCH = "branch"
    INTERNAL = "internal"


class IncidentCategory(StrEnum):
    TECHNICAL_FAILURE = "technical_failure"
    PROCESS_ERROR = "process_error"
    CLIENT_COMPLAINT = "client_complaint"
    CANDIDATE_ISSUE = "candidate_issue"
    STAFF_ISSUE = "staff_issue"
    SLA_BREACH = "sla_breach"
    DATA_QUALITY = "data_quality"
    OTHER = "other"


class Branch(StrEnum):
    CENTRAL = "central"
    VALENCIA_OPERATIONS = "valencia_operations"
    MIAMI_OFFICE = "miami_office"
    REMOTE = "remote"


# "Nombre para mostrar" de cada sede, literal del CONTEXT. Solo `branch` tiene
# etiquetas; el resto de valores se muestran tal cual.
BRANCH_LABELS: Final[dict[Branch, str]] = {
    Branch.CENTRAL: "Central — Sede Valencia",
    Branch.VALENCIA_OPERATIONS: "Valencia — Operaciones",
    Branch.MIAMI_OFFICE: "Miami Office",
    Branch.REMOTE: "Remoto (empleado sin sede fija)",
}

# "Primeros 120 caracteres de `description`" (mapeo del seed). Se aplica
# también como máximo del título creado por la API, para que ambos coincidan.
TITLE_MAX_LENGTH: Final = 120
