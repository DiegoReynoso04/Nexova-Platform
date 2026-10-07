"""Contrato del CSV de incidentes de Nexova (el que exporta el helpdesk).

Fuente: docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md ("Estructura del CSV",
"Categorías válidas", "Reglas de registros inválidos"). Todo literal de este
módulo sale de ese documento; no añadir valores que no aparezcan allí.

Lo comparten el analizador (`packages/incident-analyzer`) y el seed del gestor
de incidencias (`scripts/seed_incidents.py`).
"""

import re
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Final

FIELDS: Final[tuple[str, ...]] = (
    "ticket_id",
    "date",
    "client_company",
    "category",
    "description",
    "agent_id",
    "status",
    "customer_email",
    "satisfaction_score",
)


class Category(StrEnum):
    TECHNICAL = "TECHNICAL"
    BILLING = "BILLING"
    ACCESS = "ACCESS"
    HR_QUERY = "HR_QUERY"
    COMPLAINT = "COMPLAINT"


class Status(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    DISCARDED = "DISCARDED"


class Rule(Enum):
    """Las 7 reglas de invalidación, en el orden del documento.

    `code` es el identificador estable (exportación); `label` es el texto de
    consola. Ninguno de los dos contiene datos de la fila.
    """

    MISSING_CLIENT_COMPANY = ("missing_client_company", "Missing client_company")
    INVALID_CATEGORY = ("invalid_category", "Invalid or missing category")
    INVALID_DESCRIPTION = ("invalid_description", "Invalid or missing description")
    INVALID_AGENT_ID = ("invalid_agent_id", "Invalid or missing agent_id")
    INVALID_EMAIL = ("invalid_email", "Invalid or missing email")
    CLOSED_WITHOUT_SCORE = ("closed_without_score", "Closed ticket, no score")
    SCORE_OUT_OF_RANGE = ("score_out_of_range", "Score out of range")

    def __init__(self, code: str, label: str) -> None:
        self.code = code
        self.label = label


MIN_DESCRIPTION_LENGTH: Final = 5
SCORE_MIN: Final = 1
SCORE_MAX: Final = 5
# fullmatch + ASCII: `$` aceptaría un salto de línea final y `\d` dígitos no ASCII.
AGENT_ID_PATTERN: Final = re.compile(r"AGT-\d{2}", re.ASCII)
SCORE_PATTERN: Final = re.compile(r"\d+", re.ASCII)


@dataclass(frozen=True, slots=True, repr=False)
class IncidentRow:
    """Una fila del CSV, con cada valor ya pasado por `strip()`.

    `__repr__` está redefinido para que imprimir o registrar una fila por
    accidente nunca exponga `customer_email` ni ningún otro valor.
    """

    row_number: int
    ticket_id: str
    date: str
    client_company: str
    category: str
    description: str
    agent_id: str
    status: str
    customer_email: str
    satisfaction_score: str

    def __repr__(self) -> str:
        return f"IncidentRow(row_number={self.row_number})"

    __str__ = __repr__
