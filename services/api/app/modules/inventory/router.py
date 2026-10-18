"""Capa HTTP del inventario (Hito 5): `APIRouter(prefix="/inventory")`.

Equivale a `routers/inventory.py` del enunciado. Cada ruta recibe su propia
sesión con `Depends(get_db)` y responde con un schema de `schemas.py`
(`response_model` en todas), nunca con un modelo ORM. La lógica vive en
`service.py`. El JWT lo exige `create_app` al registrar el router, como en
el resto de la API.

F3a: productos (activos). Las órdenes de entrada y salida llegan en F3b.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from . import service
from .database import get_db
from .schemas import AssetCreate, AssetRead

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
