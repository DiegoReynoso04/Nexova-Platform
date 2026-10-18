"""Lógica del inventario sobre una sesión SQLModel: activos con su stock calculado.

Recibe la sesión de la petición (`get_db`) y nunca la crea: no hay sesión
global. Devuelve schemas (`AssetRead`), nunca objetos ORM.

`current_stock = SUMA(entradas) − SUMA(salidas)` (regla 1 del CONTEXT). Se
calcula en la misma consulta que lee los activos: cada lado se agrega primero
en su propia subconsulta y luego se une con LEFT JOIN. Unir las dos tablas de
órdenes antes de sumar multiplicaría las filas (cada entrada por cada salida).
"""

from sqlalchemy import ColumnElement, Select, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.errors import AssetNotFoundError, SkuAlreadyExistsError

from .models import Asset, AssetEntry, AssetExit
from .schemas import AssetCreate, AssetRead


def _assets_with_stock() -> Select[tuple[Asset, int]]:
    entries = (
        select(AssetEntry.asset_id, func.sum(AssetEntry.quantity).label("total"))
        .group_by(AssetEntry.asset_id)
        .subquery()
    )
    exits = (
        select(AssetExit.asset_id, func.sum(AssetExit.quantity).label("total"))
        .group_by(AssetExit.asset_id)
        .subquery()
    )
    stock: ColumnElement[int] = (func.coalesce(entries.c.total, 0) - func.coalesce(exits.c.total, 0)).label(
        "current_stock"
    )
    return (
        select(Asset, stock)
        .outerjoin(entries, entries.c.asset_id == Asset.id)
        .outerjoin(exits, exits.c.asset_id == Asset.id)
    )


def _read(asset: Asset, current_stock: int) -> AssetRead:
    return AssetRead(
        id=asset.id,
        name=asset.name,
        sku=asset.sku,
        category=asset.category,
        office=asset.office,
        current_stock=current_stock,
    )


def list_assets(session: Session) -> list[AssetRead]:
    """Todos los activos con su stock, ordenados por `id`. Una sola consulta."""
    rows = session.exec(_assets_with_stock().order_by(Asset.id)).all()
    return [_read(asset, current_stock) for asset, current_stock in rows]


def get_asset(session: Session, asset_id: int) -> AssetRead:
    row = session.exec(_assets_with_stock().where(Asset.id == asset_id)).first()
    if row is None:
        raise AssetNotFoundError()
    asset, current_stock = row
    return _read(asset, current_stock)


def _sku_taken(session: Session, sku: str) -> bool:
    return session.exec(select(Asset.id).where(Asset.sku == sku)).first() is not None


def create_asset(session: Session, payload: AssetCreate) -> AssetRead:
    """Registra un activo con stock 0. SKU repetido → 409, también en una carrera.

    La comprobación previa cubre el caso normal. Si otra petición inserta el
    mismo SKU entre esa comprobación y el commit, el `UNIQUE` de la base lanza
    `IntegrityError`; tras el rollback se confirma que el SKU ya existe y se
    responde 409. Cualquier otro `IntegrityError` se relanza (500 opaco).
    """
    if _sku_taken(session, payload.sku):
        raise SkuAlreadyExistsError()
    asset = Asset(**payload.model_dump())
    session.add(asset)
    conflict: IntegrityError | None = None
    try:
        session.commit()
    except IntegrityError as error:
        conflict = error
    if conflict is not None:
        session.rollback()
        if _sku_taken(session, payload.sku):
            raise SkuAlreadyExistsError()
        raise conflict
    session.refresh(asset)
    return _read(asset, 0)
