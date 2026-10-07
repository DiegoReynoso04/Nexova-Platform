"""Las 7 reglas de registros inválidos del documento de contexto.

Solo estas reglas deciden si una fila es inválida (decisión D3): `ticket_id`,
`date` y `status` fuera de formato no invalidan. El resultado de validar una
fila son códigos de regla, nunca valores de la fila.
"""

from dataclasses import dataclass

from .schema import (
    AGENT_ID_PATTERN,
    MIN_DESCRIPTION_LENGTH,
    SCORE_MAX,
    SCORE_MIN,
    SCORE_PATTERN,
    Category,
    IncidentRow,
    Rule,
    Status,
)

_VALID_CATEGORIES = frozenset(category.value for category in Category)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Número de fila + reglas activadas. Sin valores: seguro de registrar."""

    row_number: int
    violations: frozenset[Rule]

    @property
    def is_valid(self) -> bool:
        return not self.violations


def parse_score(raw: str) -> int | None:
    """`None` si el campo está vacío; el entero si está entre 1 y 5.

    Lanza `ValueError` (con un mensaje que no incluye el valor) si hay algo
    que no es un entero 1–5: "4.5", "abc", "0", "6", "-1"...
    """
    if not raw:
        return None
    if SCORE_PATTERN.fullmatch(raw):
        score = int(raw)
        if SCORE_MIN <= score <= SCORE_MAX:
            return score
    raise ValueError("satisfaction_score is not an integer between 1 and 5")


def validate_row(row: IncidentRow) -> ValidationResult:
    violations: set[Rule] = set()

    if not row.client_company:
        violations.add(Rule.MISSING_CLIENT_COMPANY)
    if row.category not in _VALID_CATEGORIES:
        violations.add(Rule.INVALID_CATEGORY)
    if len(row.description) < MIN_DESCRIPTION_LENGTH:
        violations.add(Rule.INVALID_DESCRIPTION)
    if not AGENT_ID_PATTERN.fullmatch(row.agent_id):
        violations.add(Rule.INVALID_AGENT_ID)
    if not row.customer_email or "@" not in row.customer_email:
        violations.add(Rule.INVALID_EMAIL)

    try:
        score = parse_score(row.satisfaction_score)
    except ValueError:
        violations.add(Rule.SCORE_OUT_OF_RANGE)
    else:
        if score is None and row.status == Status.CLOSED:
            violations.add(Rule.CLOSED_WITHOUT_SCORE)

    return ValidationResult(row_number=row.row_number, violations=frozenset(violations))
