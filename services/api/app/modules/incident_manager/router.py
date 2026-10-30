"""Capa HTTP del gestor centralizado de incidencias: request → reglas de nexova_shared → repositorio → respuesta.

Contrato: SPECS.md Parte E. Sin reglas propias: la validación de campos,
filtros y transiciones es de `nexova_shared.incidents`.

Errores de este router (y solo de este): toda validación responde 400
`{"code": "validation_error", "detail": [{field, error, message}]}`, también
cuando FastAPI no puede leer el cuerpo (no es JSON o no es un objeto). Para
eso las rutas usan `IncidentManagerRoute`, que traduce `RequestValidationError`
antes de que llegue al handler global del 422 (proveedores y auth no cambian).

OpenAPI (auditoría de serialización, D6 y D8): las escrituras publican su
contrato de entrada (`IncidentCreateRequest`, `IncidentStatusChangeRequest`)
con `openapi_extra`, sin dejar de validar con `nexova_shared`; cada ruta
documenta sus errores reales con `responses=`, y
`drop_native_validation_responses` quita el 422 que FastAPI añade por defecto
y que este router nunca responde.
"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute, iter_route_contexts
from nexova_shared.incidents import (
    FINAL_STATUSES,
    INITIAL_STATUS,
    Branch,
    FieldError,
    FieldErrorCode,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
    IncidentValidationError,
    check_transition,
    validate_filters,
    validate_incident_fields,
    validate_status_change,
)
from pydantic import BaseModel

from app.core.errors import (
    ApiError,
    FieldErrorDetail,
    IncidentFieldsError,
    IncidentNotFoundError,
    InvalidStatusTransitionApiError,
    NotAuthenticatedError,
    StorageUnavailableError,
)

from .models import (
    IncidentCreateRequest,
    IncidentErrorResponse,
    IncidentListItem,
    IncidentRead,
    IncidentStatusChangeRequest,
    IncidentSummary,
    IncidentValidationErrorResponse,
)
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
# El contrato que ve el cliente lo publican los modelos de entrada (`_request_body`).
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


def _request_body(model: type[BaseModel]) -> dict[str, Any]:
    """Cuerpo de la petición en OpenAPI a partir del contrato publicado (solo documentación).

    FastAPI lo combina con el esquema del `JsonObject` del handler: se conservan
    los ejemplos y el modelo aporta propiedades, obligatorios y
    `additionalProperties: false`. Las referencias internas (`$defs`) se
    resuelven en el sitio para que el esquema no dependa de otros componentes.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            reference = node.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/$defs/"):
                return resolve(definitions[reference.removeprefix("#/$defs/")])
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return {"requestBody": {"required": True, "content": {"application/json": {"schema": resolve(schema)}}}}


def _field_errors(errors: Iterable[FieldError]) -> list[FieldErrorDetail]:
    return [{"field": error.field, "error": error.error.value, "message": error.message} for error in errors]


def _example(summary: str, error: ApiError) -> dict[str, Any]:
    """Ejemplo de OpenAPI construido con el error real (mismo `detail` y `code`)."""
    return {"summary": summary, "value": {"detail": error.detail, "code": error.code}}


def _documented(model: type[BaseModel], description: str, *examples: dict[str, Any]) -> dict[str, Any]:
    content = {"examples": {example["summary"]: example for example in examples}}
    return {"model": model, "description": description, "content": {"application/json": content}}


def _validation_example() -> IncidentFieldsError:
    """Errores reales de nexova_shared: un alta vacía (cada obligatorio, `missing`)."""
    try:
        validate_incident_fields({})
    except IncidentValidationError as error:
        return IncidentFieldsError(_field_errors(error.errors))
    raise AssertionError("an empty incident must be invalid")


def _transition_example() -> InvalidStatusTransitionApiError:
    """Error real de nexova_shared: volver al estado inicial desde un estado final."""
    error = check_transition(sorted(FINAL_STATUSES)[0], INITIAL_STATUS)
    assert error is not None
    return InvalidStatusTransitionApiError(_field_errors([error]))


# Un id que no es un UUID no coincide con la ruta: 404 genérico de la API (P4-3).
_NOT_FOUND_EXAMPLE = {"summary": "not_found", "value": {"detail": "Not Found", "code": "not_found"}}

COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _documented(IncidentErrorResponse, "Sin token válido", _example("not_authenticated", NotAuthenticatedError())),
    503: _documented(
        IncidentErrorResponse,
        "incidents.json (o auth.json, al validar el token) no se puede leer o escribir",
        _example("storage_unavailable", StorageUnavailableError()),
    ),
}
VALIDATION_ERROR = _documented(
    IncidentValidationErrorResponse,
    "Campos, filtros o cuerpo no válidos: un elemento por problema (SPECS §31)",
    _example("validation_error", _validation_example()),
)
NOT_FOUND = _documented(
    IncidentErrorResponse,
    "La incidencia no existe, o el id no es un UUID",
    _example("incident_not_found", IncidentNotFoundError()),
    _NOT_FOUND_EXAMPLE,
)


@router.post(
    "",
    status_code=201,
    response_model=IncidentRead,
    responses={**COMMON_ERRORS, 400: VALIDATION_ERROR},
    openapi_extra=_request_body(IncidentCreateRequest),
)
def create_incident(
    payload: Annotated[JsonObject, Body(examples=[_CREATE_EXAMPLE])],
    repository: RepositoryDep,
) -> IncidentRead:
    try:
        draft = validate_incident_fields(payload)
    except IncidentValidationError as error:
        raise IncidentFieldsError(_field_errors(error.errors)) from None
    return repository.create(draft).public()


@router.get("", response_model=list[IncidentListItem], responses={**COMMON_ERRORS, 400: VALIDATION_ERROR})
def list_incidents(
    repository: RepositoryDep,
    status: Annotated[str | None, _filter(IncidentStatus, "Filter by status")] = None,
    origin: Annotated[str | None, _filter(IncidentOrigin, "Filter by origin")] = None,
    branch: Annotated[str | None, _filter(Branch, "Filter by branch")] = None,
    category: Annotated[str | None, _filter(IncidentCategory, "Filter by category")] = None,
) -> list[IncidentListItem]:
    try:
        filters = validate_filters({"status": status, "origin": origin, "branch": branch, "category": category})
    except IncidentValidationError as error:
        raise IncidentFieldsError(_field_errors(error.errors)) from None
    incidents = repository.find(
        status=filters.status, origin=filters.origin, branch=filters.branch, category=filters.category
    )
    return [incident.list_item() for incident in incidents]


# Antes que /{incident_id}: aunque el convertidor uuid ya impide que "summary"
# coincida con un id, el orden deja clara la intención.
@router.get("/summary", response_model=IncidentSummary, responses=COMMON_ERRORS)
def incident_summary(repository: RepositoryDep) -> IncidentSummary:
    return repository.summary()


# `:uuid` (convertidor de Starlette): un segmento que no es un UUID no coincide
# con esta ruta, así que `GET /api/incidents/analyze` sigue respondiendo 405 y
# cualquier otro id mal formado, 404.
@router.get("/{incident_id:uuid}", response_model=IncidentRead, responses={**COMMON_ERRORS, 404: NOT_FOUND})
def get_incident(incident_id: UUID, repository: RepositoryDep) -> IncidentRead:
    incident = repository.get(incident_id)
    if incident is None:
        raise IncidentNotFoundError()
    return incident.public()


@router.patch(
    "/{incident_id:uuid}/status",
    response_model=IncidentRead,
    responses={
        **COMMON_ERRORS,
        400: _documented(
            IncidentValidationErrorResponse,
            "Cuerpo no válido, o transición no permitida por el ciclo de vida",
            _example("validation_error", _validation_example()),
            _example("invalid_status_transition", _transition_example()),
        ),
        404: NOT_FOUND,
    },
    openapi_extra=_request_body(IncidentStatusChangeRequest),
)
def change_incident_status(
    incident_id: UUID,
    payload: Annotated[JsonObject, Body(examples=[{"status": IncidentStatus.IN_PROGRESS.value}])],
    repository: RepositoryDep,
) -> IncidentRead:
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
    return incident.public()


def drop_native_validation_responses(openapi_schema: dict[str, Any], routes: Iterable[Any]) -> None:
    """Quita de OpenAPI el 422 que FastAPI añade a las rutas de este router.

    Nunca lo responden: `IncidentManagerRoute` convierte la validación en el 400
    propio, que cada ruta documenta con `responses=`. FastAPI no permite
    quitarlo desde el decorador.
    """
    # `iter_route_contexts`: FastAPI guarda los routers incluidos sin aplanar
    # (`app.routes` no contiene sus rutas); da cada ruta con su prefijo.
    for route in iter_route_contexts(list(routes)):
        if isinstance(route.original_route, IncidentManagerRoute) and route.path_format and route.methods:
            operations = openapi_schema["paths"].get(route.path_format, {})
            for method in route.methods:
                operations.get(method.lower(), {}).get("responses", {}).pop("422", None)


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
