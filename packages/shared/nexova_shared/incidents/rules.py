"""Reglas del modelo `Incident`: campos obligatorios, valores permitidos y ciclo de vida.

Las usan la API (`services/api`, alta y cambio de estado) y el seed
(`scripts/seed_incidents.py`), para que una incidencia sea válida o inválida
por las mismas razones venga de donde venga.

Los errores identifican el campo y la regla (`FieldErrorCode`); sus mensajes
son fijos y nunca repiten el valor recibido.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, TypeVar

from .vocabulary import TITLE_MAX_LENGTH, Branch, IncidentCategory, IncidentOrigin, IncidentStatus

# Ciclo de vida del CONTEXT: open → in_progress | discarded;
# in_progress → resolved | discarded; resolved y discarded son finales.
ALLOWED_TRANSITIONS: Final[Mapping[IncidentStatus, frozenset[IncidentStatus]]] = MappingProxyType(
    {
        IncidentStatus.OPEN: frozenset({IncidentStatus.IN_PROGRESS, IncidentStatus.DISCARDED}),
        IncidentStatus.IN_PROGRESS: frozenset({IncidentStatus.RESOLVED, IncidentStatus.DISCARDED}),
        IncidentStatus.RESOLVED: frozenset(),
        IncidentStatus.DISCARDED: frozenset(),
    }
)
FINAL_STATUSES: Final = frozenset(status for status, targets in ALLOWED_TRANSITIONS.items() if not targets)
# Toda incidencia creada desde la API nace abierta ("Incidencia registrada, sin
# responsable asignado aún"). El seed puede cargar otros estados del histórico.
INITIAL_STATUS: Final = IncidentStatus.OPEN

# Campos que se pueden enviar al crear una incidencia. `id`, `created_at` y
# `updated_at` los genera el sistema.
INPUT_FIELDS: Final[tuple[str, ...]] = ("title", "description", "category", "status", "origin", "branch")
# Filtros del listado y único campo del cambio de estado.
FILTER_FIELDS: Final[tuple[str, ...]] = ("status", "origin", "branch", "category")
STATUS_CHANGE_FIELDS: Final[tuple[str, ...]] = ("status",)


_Choice = TypeVar("_Choice", bound=StrEnum)


class FieldErrorCode(StrEnum):
    MISSING = "missing"
    BLANK = "blank"
    TOO_LONG = "too_long"
    INVALID_TYPE = "invalid_type"
    INVALID_CHOICE = "invalid_choice"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_TRANSITION = "invalid_transition"
    # El cuerpo de la petición no es un objeto JSON (lo detecta la capa HTTP).
    INVALID_BODY = "invalid_body"


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    error: FieldErrorCode
    message: str


class IncidentValidationError(ValueError):
    """Uno o varios campos no cumplen el modelo. `errors` sigue el orden de `INPUT_FIELDS`."""

    def __init__(self, errors: Collection[FieldError]) -> None:
        self.errors = tuple(errors)
        super().__init__("invalid incident fields: " + ", ".join(error.field for error in self.errors))


@dataclass(frozen=True, slots=True, repr=False)
class IncidentDraft:
    """Campos de una incidencia ya validados y normalizados (textos sin espacios en los extremos).

    `__repr__` no muestra valores: la descripción puede contener datos de clientes.
    """

    title: str
    description: str
    category: IncidentCategory
    status: IncidentStatus
    origin: IncidentOrigin
    branch: Branch

    def __repr__(self) -> str:
        return "IncidentDraft(...)"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class IncidentFilters:
    """Filtros opcionales del listado; `None` = sin filtrar por ese campo. Se combinan con AND."""

    status: IncidentStatus | None = None
    origin: IncidentOrigin | None = None
    branch: Branch | None = None
    category: IncidentCategory | None = None


def can_transition(current: IncidentStatus, target: IncidentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def check_transition(current: IncidentStatus, target: IncidentStatus) -> FieldError | None:
    if can_transition(current, target):
        return None
    if current in FINAL_STATUSES:
        message = f"status {current} is final and cannot change"
    else:
        allowed = ", ".join(sorted(ALLOWED_TRANSITIONS[current]))
        message = f"status {current} can only change to: {allowed}"
    return FieldError("status", FieldErrorCode.INVALID_TRANSITION, message)


def validate_incident_fields(
    raw: Mapping[str, object],
    *,
    allowed_statuses: Collection[IncidentStatus] = (INITIAL_STATUS,),
) -> IncidentDraft:
    """Valida los campos de entrada de una incidencia y devuelve el borrador normalizado.

    `status` es opcional (por defecto `INITIAL_STATUS`) y debe estar en
    `allowed_statuses`: la API solo admite `open` al crear; el seed pasa todos.
    Un valor `None` cuenta como ausente. Lanza `IncidentValidationError` con
    todos los errores encontrados, no solo el primero.
    """
    errors = _unknown_fields(raw, INPUT_FIELDS)
    title = _required_text(raw, "title", errors, max_length=TITLE_MAX_LENGTH)
    description = _required_text(raw, "description", errors)
    category = _required_choice(raw, "category", IncidentCategory, errors)
    status = _status(raw, allowed_statuses, errors)
    origin = _required_choice(raw, "origin", IncidentOrigin, errors)
    branch = _required_choice(raw, "branch", Branch, errors)

    if errors:
        errors.sort(key=_error_order)
        raise IncidentValidationError(errors)
    # Sin errores, ningún campo es None (lo garantizan los helpers).
    assert title is not None and description is not None and category is not None
    assert status is not None and origin is not None and branch is not None
    return IncidentDraft(title, description, category, status, origin, branch)


def validate_filters(raw: Mapping[str, str | None]) -> IncidentFilters:
    """Valida los filtros del listado (`None` = ausente). Un valor fuera del vocabulario es un error."""
    errors: list[FieldError] = []
    vocabularies: dict[str, type[StrEnum]] = {
        "status": IncidentStatus,
        "origin": IncidentOrigin,
        "branch": Branch,
        "category": IncidentCategory,
    }
    values = {
        name: None if raw.get(name) is None else _choice(raw.get(name), name, list(vocabularies[name]), errors)
        for name in FILTER_FIELDS
    }
    if errors:
        raise IncidentValidationError(errors)
    return IncidentFilters(**values)  # type: ignore[arg-type]


def validate_status_change(raw: Mapping[str, object]) -> IncidentStatus:
    """Valida el cuerpo de un cambio de estado: solo `status`, obligatorio, uno de los cuatro estados.

    No comprueba la transición (depende del estado actual): ver `check_transition`.
    """
    errors = _unknown_fields(raw, STATUS_CHANGE_FIELDS)
    status = _required_choice(raw, "status", IncidentStatus, errors)
    if errors:
        errors.sort(key=_error_order)
        raise IncidentValidationError(errors)
    assert status is not None
    return status


def _unknown_fields(raw: Mapping[str, object], accepted: tuple[str, ...]) -> list[FieldError]:
    # El mensaje no repite el nombre recibido: ya va en `field`.
    return [
        FieldError(name, FieldErrorCode.UNKNOWN_FIELD, "this field is not accepted")
        for name in sorted(set(raw) - set(accepted))
    ]


def _error_order(error: FieldError) -> int:
    return INPUT_FIELDS.index(error.field) if error.field in INPUT_FIELDS else len(INPUT_FIELDS)


def _required_text(
    raw: Mapping[str, object], name: str, errors: list[FieldError], *, max_length: int | None = None
) -> str | None:
    value = raw.get(name)
    if value is None:
        errors.append(FieldError(name, FieldErrorCode.MISSING, f"{name} is required"))
        return None
    if not isinstance(value, str):
        errors.append(FieldError(name, FieldErrorCode.INVALID_TYPE, f"{name} must be a text"))
        return None
    text = value.strip()
    if not text:
        errors.append(FieldError(name, FieldErrorCode.BLANK, f"{name} must not be empty"))
        return None
    if max_length is not None and len(text) > max_length:
        errors.append(FieldError(name, FieldErrorCode.TOO_LONG, f"{name} must be at most {max_length} characters"))
        return None
    return text


def _required_choice(
    raw: Mapping[str, object], name: str, choices: type[_Choice], errors: list[FieldError]
) -> _Choice | None:
    value = raw.get(name)
    if value is None:
        errors.append(FieldError(name, FieldErrorCode.MISSING, f"{name} is required"))
        return None
    return _choice(value, name, list(choices), errors)


def _status(
    raw: Mapping[str, object], allowed: Collection[IncidentStatus], errors: list[FieldError]
) -> IncidentStatus | None:
    value = raw.get("status")
    if value is None:
        return INITIAL_STATUS
    # Mismo orden que el enum, para que el mensaje sea estable.
    return _choice(value, "status", [status for status in IncidentStatus if status in allowed], errors)


def _choice(value: object, name: str, choices: list[_Choice], errors: list[FieldError]) -> _Choice | None:
    # Valores exactos: el CONTEXT exige "exactamente uno de estos valores"
    # (sin recortar espacios ni ignorar mayúsculas).
    for choice in choices:
        if isinstance(value, str) and value == choice.value:
            return choice
    allowed = ", ".join(choice.value for choice in choices)
    errors.append(FieldError(name, FieldErrorCode.INVALID_CHOICE, f"{name} must be one of: {allowed}"))
    return None
