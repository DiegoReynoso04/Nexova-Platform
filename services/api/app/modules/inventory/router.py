"""Capa HTTP del inventario (Hito 5): `APIRouter(prefix="/inventory")`.

Equivale a `routers/inventory.py` del enunciado. Cada ruta recibe su propia
sesión con `Depends(get_db)` y responde con un schema de `schemas.py`
(`response_model` en todas), nunca con un modelo ORM. La lógica vive en
`service.py`. El JWT lo exige `create_app` al registrar el router, como en
el resto de la API; las rutas de órdenes declaran además el usuario actual,
porque su `id` (de TinyDB) es el `user_uuid` de cada orden. FastAPI resuelve
`get_current_user` una sola vez por petición.

Caché (ticket de caching, docs/caching-analysis.md D1–D4): `GET /products` y
`GET /products/{id}` se guardan 60 s en el espacio `inventory` de la caché de
la app. Es la misma respuesta para cualquier usuario, y se consulta dentro del
handler, después de la autenticación. Las tres escrituras invalidan el espacio
entero, solo si confirman: una que falla (400/404/409/503) lanza antes de
llegar a `invalidate`. Los seeds y los cambios directos en la base no pasan
por aquí; el TTL acota cuánto tardan en verse. Con `NullPool`, un acierto no
abre ninguna conexión: la sesión de `get_db` solo conecta al primer `execute`.

Los `responses=` solo documentan en OpenAPI los errores reales de cada ruta
(`{detail, code}`, con ejemplos); no cambian el comportamiento. El 422 lo
documenta FastAPI.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth.dependencies import CurrentUserDep, SettingsDep
from app.core.cache import CacheDep
from app.core.errors import (
    AssetNotFoundError,
    InsufficientStockError,
    NotAuthenticatedError,
    OfficeMismatchError,
    SkuAlreadyExistsError,
    StorageUnavailableError,
)

from . import service
from .database import get_db
from .schemas import (
    AssetCreate,
    AssetRead,
    ErrorResponse,
    InboundOrderCreate,
    InboundOrderCreated,
    OrderRead,
    OutboundOrderCreate,
    OutboundOrderCreated,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])

SessionDep = Annotated[Session, Depends(get_db)]

CACHE_NAMESPACE = "inventory"
# El stock solo cambia con una orden o un activo nuevo, y esas escrituras
# invalidan al momento. Los 60 s solo acotan los cambios externos a la API (D1).
CACHE_TTL_SECONDS = 60


def _example(error: Any) -> dict[str, Any]:
    """Ejemplo de OpenAPI a partir del error real (mismo `detail` y `code`)."""
    return {"summary": error.code, "value": {"detail": error.detail, "code": error.code}}


def _error(description: str, *errors: Any) -> dict[str, Any]:
    examples = {error.code: _example(error) for error in errors}
    return {"model": ErrorResponse, "description": description, "content": {"application/json": {"examples": examples}}}


# Comunes a las 6 rutas: el JWT (en `create_app`) y la base del inventario.
COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _error("Sin token válido", NotAuthenticatedError()),
    503: _error("La base del inventario no responde", StorageUnavailableError()),
}
ASSET_NOT_FOUND = _error("El activo no existe", AssetNotFoundError())
# Ejemplo con un activo del CONTEXT y el mensaje literal de la regla 2.
INSUFFICIENT_STOCK_EXAMPLE = InsufficientStockError('Portátil 14" Business', 13, 20)


@router.get("/products", response_model=list[AssetRead], responses=COMMON_ERRORS)
def list_products(session: SessionDep, cache: CacheDep) -> list[AssetRead]:
    return cache.get_or_set(CACHE_NAMESPACE, "products", CACHE_TTL_SECONDS, lambda: service.list_assets(session))


@router.post(
    "/products",
    status_code=201,
    response_model=AssetRead,
    responses={**COMMON_ERRORS, 409: _error("Ya existe un activo con ese SKU", SkuAlreadyExistsError())},
)
def create_product(payload: AssetCreate, session: SessionDep, cache: CacheDep) -> AssetRead:
    asset = service.create_asset(session, payload)
    cache.invalidate(CACHE_NAMESPACE)
    return asset


# `{id}`: el nombre que fija el enunciado, también en OpenAPI.
@router.get("/products/{id}", response_model=AssetRead, responses={**COMMON_ERRORS, 404: ASSET_NOT_FOUND})
def get_product(id: int, session: SessionDep, cache: CacheDep) -> AssetRead:  # noqa: A002 — nombre del enunciado
    # Un 404 lanza dentro de `get_or_set`: no se guarda.
    return cache.get_or_set(CACHE_NAMESPACE, ("product", id), CACHE_TTL_SECONDS, lambda: service.get_asset(session, id))


@router.post(
    "/orders/inbound",
    status_code=201,
    response_model=InboundOrderCreated,
    responses={
        **COMMON_ERRORS,
        400: _error("La oficina de la orden no es la del activo", OfficeMismatchError()),
        404: ASSET_NOT_FOUND,
    },
)
def create_inbound_order(
    payload: InboundOrderCreate, session: SessionDep, user: CurrentUserDep, cache: CacheDep, settings: SettingsDep
) -> InboundOrderCreated:
    order = service.create_inbound_order(session, payload, user_uuid=str(user.id), settings=settings)
    cache.invalidate(CACHE_NAMESPACE)
    return order


@router.post(
    "/orders/outbound",
    status_code=201,
    response_model=OutboundOrderCreated,
    responses={
        **COMMON_ERRORS,
        400: _error(
            "La oficina no es la del activo, o la salida supera el stock (no se escribe nada)",
            OfficeMismatchError(),
            INSUFFICIENT_STOCK_EXAMPLE,
        ),
        404: ASSET_NOT_FOUND,
    },
)
def create_outbound_order(
    payload: OutboundOrderCreate, session: SessionDep, user: CurrentUserDep, cache: CacheDep, settings: SettingsDep
) -> OutboundOrderCreated:
    # La regla del stock se comprueba en la base (`FOR UPDATE`), nunca contra la caché.
    order = service.create_outbound_order(session, payload, user_uuid=str(user.id), settings=settings)
    cache.invalidate(CACHE_NAMESPACE)
    return order


@router.get("/orders", response_model=list[OrderRead], responses=COMMON_ERRORS)
def list_orders(session: SessionDep) -> list[OrderRead]:
    return service.list_orders(session)
