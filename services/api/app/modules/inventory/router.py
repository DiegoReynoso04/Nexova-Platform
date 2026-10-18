"""Capa HTTP del inventario (Hito 5): `APIRouter(prefix="/inventory")`.

Equivale a `routers/inventory.py` del enunciado. Cada ruta recibe su propia
sesión con `Depends(get_db)` y responde con un schema de `schemas.py`
(`response_model` en todas), nunca con un modelo ORM. La lógica vive en
`service.py`. El JWT lo exige `create_app` al registrar el router, como en
el resto de la API; las rutas de órdenes declaran además el usuario actual,
porque su `id` (de TinyDB) es el `user_uuid` de cada orden. FastAPI resuelve
`get_current_user` una sola vez por petición.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth.dependencies import CurrentUserDep

from . import service
from .database import get_db
from .schemas import (
    AssetCreate,
    AssetRead,
    InboundOrderCreate,
    InboundOrderRead,
    OrderRead,
    OutboundOrderCreate,
    OutboundOrderRead,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])

SessionDep = Annotated[Session, Depends(get_db)]


@router.get("/products", response_model=list[AssetRead])
def list_products(session: SessionDep) -> list[AssetRead]:
    return service.list_assets(session)


@router.post("/products", status_code=201, response_model=AssetRead)
def create_product(payload: AssetCreate, session: SessionDep) -> AssetRead:
    return service.create_asset(session, payload)


# `{id}`: el nombre que fija el enunciado, también en OpenAPI.
@router.get("/products/{id}", response_model=AssetRead)
def get_product(id: int, session: SessionDep) -> AssetRead:  # noqa: A002 — nombre del enunciado
    return service.get_asset(session, id)


@router.post("/orders/inbound", status_code=201, response_model=InboundOrderRead)
def create_inbound_order(payload: InboundOrderCreate, session: SessionDep, user: CurrentUserDep) -> InboundOrderRead:
    return service.create_inbound_order(session, payload, user_uuid=str(user.id))


@router.post("/orders/outbound", status_code=201, response_model=OutboundOrderRead)
def create_outbound_order(
    payload: OutboundOrderCreate, session: SessionDep, user: CurrentUserDep
) -> OutboundOrderRead:
    return service.create_outbound_order(session, payload, user_uuid=str(user.id))


@router.get("/orders", response_model=list[OrderRead])
def list_orders(session: SessionDep) -> list[OrderRead]:
    return service.list_orders(session)
