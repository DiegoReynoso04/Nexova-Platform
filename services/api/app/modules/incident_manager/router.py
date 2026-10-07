"""Capa HTTP del gestor centralizado de incidencias: request → reglas de nexova_shared → repositorio → respuesta.

Contrato: SPECS.md Parte E. Sin reglas propias: la validación de campos,
filtros y transiciones es de `nexova_shared.incidents`.

Errores de este router (y solo de este): toda validación responde 400
`{"code": "validation_error", "detail": [{field, error, message}]}`, también
cuando FastAPI no puede leer el cuerpo (no es JSON o no es un objeto). Para
eso las rutas usan `IncidentManagerRoute`, que traduce `RequestValidationError`
antes de que llegue al handler global del 422 (proveedores y auth no cambian).
"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from nexova_shared.incidents import (
    Branch,
    FieldError,
    FieldErrorCode,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
    IncidentValidationError,
    validate_filters,
    validate_incident_fields,
    validate_status_change,
)

from app.core.errors import (
    FieldErrorDetail,
    IncidentFieldsError,
    IncidentNotFoundError,
    InvalidStatusTransitionApiError,
)

from .models import Incident, IncidentSummary
from .repository import IncidentRepository, InvalidStatusTransitionError

BODY_FIELD = "body"
INVALID_BODY_MESSAGE = "request body must be a JSON object"


class IncidentManagerRoute(APIRoute):
    """Ruta que convierte los errores de lectura de la petición en el 400 del gestor."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def incident_manager_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                # Sin encadenar: `error` guarda el cuerpo recibido.
                raise IncidentFieldsError(_request_errors(error.errors())) from None

        return incident_manager_handler


router = APIRouter(tags=["incident-manager"], route_class=IncidentManagerRoute)


def get_incident_repository(request: Request) -> IncidentRepository:
    repository = request.app.state.incident_repository
    assert isinstance(repository, IncidentRepository)
    return repository


RepositoryDep = Annotated[IncidentRepository, Depends(get_incident_repository)]
# Objeto JSON libre: las reglas de campos son de nexova_shared, no de Pydantic,
# para que la API y el seed rechacen exactamente lo mismo con los mismos códigos.
JsonObject = dict[str, Any]

_CREATE_EXAMPLE = {
    "title": "Example incident title",
    "description": "Example description of the incident.",
    "category": IncidentCategory.TECHNICAL_FAILURE.value,
    "origin": IncidentOrigin.BRANCH.value,
    "branch": Branch.MIAMI_OFFICE.value,
}


def _filter(vocabulary: Iterable[Any], description: str) -> Any:
    return Query(description=description, json_schema_extra={"enum": [member.value for member in vocabulary]})


@router.post("", status_code=201, response_model=Incident)
def create_incident(
    payload: Annotated[JsonObject, Body(examples=[_CREATE_EXAMPLE])],
    repository: RepositoryDep,
) -> Incident:
    try:
        draft = validate_incident_fields(payload)
    except IncidentValidationError as error:
        raise IncidentFieldsError(_field_errors(error.errors)) from None
    return repository.create(draft)


@router.get("", response_model=list[Incident])
def list_incidents(
    repository: RepositoryDep,
    status: Annotated[str | None, _filter(IncidentStatus, "Filter by status")] = None,
    origin: Annotated[str | None, _filter(IncidentOrigin, "Filter by origin")] = None,
    branch: Annotated[str | None, _filter(Branch, "Filter by branch")] = None,
    category: Annotated[str | None, _filter(IncidentCategory, "Filter by category")] = None,
) -> list[Incident]:
    try:
        filters = validate_filters({"status": status, "origin": origin, "branch": branch, "category": category})
    except IncidentValidationError as error:
        raise IncidentFieldsError(_field_errors(error.errors)) from None
    return repository.find(
        status=filters.status, origin=filters.origin, branch=filters.branch, category=filters.category
    )


# Antes que /{incident_id}: aunque el convertidor uuid ya impide que "summary"
# coincida con un id, el orden deja clara la intención.
@router.get("/summary", response_model=IncidentSummary)
def incident_summary(repository: RepositoryDep) -> IncidentSummary:
    return repository.summary()


# `:uuid` (convertidor de Starlette): un segmento que no es un UUID no coincide
# con esta ruta, así que `GET /api/incidents/analyze` sigue respondiendo 405 y
# cualquier otro id mal formado, 404.
@router.get("/{incident_id:uuid}", response_model=Incident)
def get_incident(incident_id: UUID, repository: RepositoryDep) -> Incident:
    incident = repository.get(incident_id)
    if incident is None:
        raise IncidentNotFoundError()
    return incident


@router.patch("/{incident_id:uuid}/status", response_model=Incident)
def change_incident_status(
    incident_id: UUID,
    payload: Annotated[JsonObject, Body(examples=[{"status": IncidentStatus.IN_PROGRESS.value}])],
    repository: RepositoryDep,
) -> Incident:
    try:
        target = validate_status_change(payload)
    except IncidentValidationError as error:
        raise IncidentFieldsError(_field_errors(error.errors)) from None
    try:
        incident = repository.change_status(incident_id, target)
    except InvalidStatusTransitionError as error:
        raise InvalidStatusTransitionApiError(_field_errors([error.error])) from None
    if incident is None:
        raise IncidentNotFoundError()
    return incident


def _field_errors(errors: Iterable[FieldError]) -> list[FieldErrorDetail]:
    return [{"field": error.field, "error": error.error.value, "message": error.message} for error in errors]


def _request_errors(errors: Iterable[Any]) -> list[FieldErrorDetail]:
    """Errores de FastAPI al leer la petición. Solo se usa la ubicación: nunca `input` ni `msg`."""
    details: list[FieldErrorDetail] = []
    for error in errors:
        location = error.get("loc", ()) if isinstance(error, dict) else ()
        if location and location[0] == BODY_FIELD:
            detail = {"field": BODY_FIELD, "error": FieldErrorCode.INVALID_BODY.value, "message": INVALID_BODY_MESSAGE}
        else:
            field = str(location[-1]) if location else BODY_FIELD
            detail = {"field": field, "error": FieldErrorCode.INVALID_TYPE.value, "message": "invalid value"}
        if detail not in details:
            details.append(detail)
    return details
