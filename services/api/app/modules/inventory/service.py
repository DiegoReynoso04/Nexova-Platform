"""Lógica del inventario sobre una sesión SQLModel: activos con su stock calculado y órdenes.

Recibe la sesión de la petición (`get_db`) y nunca la crea: no hay sesión
global. Devuelve schemas, nunca objetos ORM.

`current_stock = SUMA(entradas) − SUMA(salidas)` (regla 1 del CONTEXT). En
los listados se calcula en la misma consulta que lee los activos: cada lado se
agrega primero en su propia subconsulta y luego se une con LEFT JOIN. Unir las
dos tablas de órdenes antes de sumar multiplicaría las filas (cada entrada por
cada salida).

Una salida bloquea antes la fila del activo (`SELECT … FOR UPDATE`), calcula
el stock y solo inserta si alcanza, todo en la misma transacción: dos salidas
simultáneas del mismo activo se ejecutan una detrás de otra y la segunda ve el
stock que dejó la primera. En SQLite (tests) `FOR UPDATE` no existe y no se
emite; la regla se prueba allí de forma secuencial.

Ticket de captura de telemetría (D1 «A ligera»): las altas devuelven además lo
que el frontend necesita para emitir los eventos obligatorios sin calcular
nada. En la salida, el stock antes y después (bajo `FOR UPDATE`) y el mínimo
configurado. En la entrada, el coste y la moneda de la oficina (P3), la clave
seudónima del proveedor (P9) y la variación del coste frente a la media de las
`N` entradas anteriores con coste del mismo activo y proveedor normalizado (P10).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.errors import AssetNotFoundError, InsufficientStockError, OfficeMismatchError, SkuAlreadyExistsError
from app.modules.telemetry.emitter import normalize_supplier, supplier_key

from .models import Asset, AssetEntry, AssetExit
from .schemas import (
    AssetCreate,
    AssetRead,
    AssetSummary,
    CostVariance,
    InboundOrderCreate,
    InboundOrderCreated,
    InboundOrderFields,
    InboundOrderRead,
    OrderRead,
    OutboundOrderCreate,
    OutboundOrderCreated,
    OutboundOrderRead,
)
from .vocabulary import OFFICE_CURRENCY, Office

# P10: la variación se acota al máximo del esquema de `kit_cost_variance_detected`.
VARIANCE_PCT_MAX = Decimal(1_000_000)


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


def _summary(asset: Asset) -> AssetSummary:
    return AssetSummary(id=asset.id, name=asset.name, sku=asset.sku)


def _utc(value: datetime) -> datetime:
    """`created_at` siempre con zona UTC: SQLite la pierde al leer y PostgreSQL la devuelve en la de la sesión."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _two_decimals(value: Decimal) -> float:
    """Dos decimales (redondeo bancario de `format`), como número JSON."""
    return float(format(value, ".2f"))


def _inbound_fields(entry: AssetEntry, asset: AssetSummary) -> dict[str, object]:
    return {
        "id": entry.id,
        "asset": asset,
        "quantity": entry.quantity,
        "supplier": entry.supplier,
        "office": entry.office,
        "created_at": _utc(entry.created_at),
        "user_uuid": entry.user_uuid,
        "unit_cost": _two_decimals(Decimal(entry.unit_cost)) if entry.unit_cost is not None else None,
        "currency": entry.currency,
    }


def _inbound_read(entry: AssetEntry, asset: AssetSummary) -> InboundOrderRead:
    return InboundOrderRead.model_validate(_inbound_fields(entry, asset))


def _outbound_read(exit_order: AssetExit, asset: AssetSummary) -> OutboundOrderRead:
    return OutboundOrderRead(
        id=exit_order.id,
        asset=asset,
        quantity=exit_order.quantity,
        exit_type=exit_order.exit_type,
        assigned_to=exit_order.assigned_to,
        office=exit_order.office,
        created_at=_utc(exit_order.created_at),
        user_uuid=exit_order.user_uuid,
    )


def locked_asset_query(asset_id: int) -> Select[tuple[Asset]]:
    """La fila del activo, bloqueada hasta el final de la transacción (`FOR UPDATE`)."""
    return select(Asset).where(Asset.id == asset_id).with_for_update()


def _available_stock(session: Session, asset_id: int) -> int:
    entries = select(func.coalesce(func.sum(AssetEntry.quantity), 0)).where(AssetEntry.asset_id == asset_id)
    exits = select(func.coalesce(func.sum(AssetExit.quantity), 0)).where(AssetExit.asset_id == asset_id)
    return session.exec(select(entries.scalar_subquery() - exits.scalar_subquery())).one()


def add_inbound_order(session: Session, payload: InboundOrderFields, user_uuid: str) -> AssetEntry:
    """Añade una entrada a la transacción en curso, sin commit (la ruta y el seed hacen el suyo).

    404 si el activo no existe; 400 si la oficina no es la del activo. La moneda
    la pone la API (la de la oficina, P3) y el coste, si lo trae el payload
    (`InboundOrderCreate`, la ruta): las entradas del seed van sin coste.
    """
    asset = session.get(Asset, payload.asset_id)
    if asset is None:
        raise AssetNotFoundError()
    if asset.office != payload.office:
        raise OfficeMismatchError()
    entry = AssetEntry(**payload.model_dump(), user_uuid=user_uuid, currency=OFFICE_CURRENCY[Office(payload.office)])
    session.add(entry)
    session.flush()
    return entry


def add_outbound_order(session: Session, payload: OutboundOrderCreate, user_uuid: str) -> AssetExit:
    """Añade una salida a la transacción en curso si hay stock, sin commit. Si falla, no añade nada.

    Orden: activo (404) → oficina (400 `office_mismatch`) → stock (400
    `insufficient_stock`). El stock incluye lo ya añadido y no confirmado en
    la misma transacción (el seed inserta varias órdenes antes de su commit).
    """
    asset = session.exec(locked_asset_query(payload.asset_id)).first()
    if asset is None:
        raise AssetNotFoundError()
    if asset.office != payload.office:
        raise OfficeMismatchError()
    available = _available_stock(session, payload.asset_id)
    if payload.quantity > available:
        raise InsufficientStockError(asset.name, available, payload.quantity)
    exit_order = AssetExit(**payload.model_dump(), user_uuid=user_uuid)
    session.add(exit_order)
    session.flush()
    return exit_order


def _reference_costs(session: Session, entry: AssetEntry, window: int) -> list[Decimal]:
    """Costes de las `window` entradas anteriores con coste del mismo activo y proveedor normalizado.

    La normalización (NFKC, mayúsculas) no se hace en SQL: se leen las entradas
    con coste del activo, de la más reciente a la más antigua, y se filtran por
    proveedor aquí. Son pocas filas por activo.
    """
    supplier = normalize_supplier(entry.supplier)
    rows = session.exec(
        select(AssetEntry.supplier, AssetEntry.unit_cost)
        .where(AssetEntry.asset_id == entry.asset_id, AssetEntry.id != entry.id, AssetEntry.unit_cost.is_not(None))  # type: ignore[union-attr]
        .order_by(AssetEntry.created_at.desc(), AssetEntry.id.desc())  # type: ignore[union-attr]
    ).all()
    costs = [Decimal(cost) for name, cost in rows if cost is not None and normalize_supplier(name) == supplier]
    return costs[:window]


def cost_variance(costs: list[Decimal], unit_cost: Decimal, settings: Settings) -> CostVariance | None:
    """P10 (D3): variación frente a la media de `costs`; `None` si no hay `window` costes o no supera el umbral."""
    window = settings.cost_variance_window
    if len(costs) < window:
        return None
    reference = sum(costs[:window], Decimal(0)) / window
    variance = min((unit_cost - reference) / reference * 100, VARIANCE_PCT_MAX)
    if abs(variance) <= Decimal(str(settings.cost_variance_threshold_pct)):
        return None
    return CostVariance(
        reference_unit_cost=_two_decimals(reference),
        variance_pct=_two_decimals(variance),
        direction="increase" if variance > 0 else "decrease",
        threshold_pct=settings.cost_variance_threshold_pct,
        reference_window=window,
    )


def create_inbound_order(
    session: Session, payload: InboundOrderCreate, user_uuid: str, settings: Settings
) -> InboundOrderCreated:
    """`POST /inventory/orders/inbound`: añade la entrada con su coste, confirma y calcula los derivados de la telemetría."""
    entry = add_inbound_order(session, payload, user_uuid)
    costs = _reference_costs(session, entry, settings.cost_variance_window)
    summary = _summary(session.get_one(Asset, payload.asset_id))
    session.commit()
    session.refresh(entry)
    return InboundOrderCreated.model_validate(
        _inbound_fields(entry, summary)
        | {
            "supplier_key": supplier_key(settings.telemetry_supplier_key, entry.supplier),
            "cost_variance": cost_variance(costs, payload.unit_cost, settings),
        }
    )


def create_outbound_order(
    session: Session, payload: OutboundOrderCreate, user_uuid: str, settings: Settings
) -> OutboundOrderCreated:
    """`POST /inventory/orders/outbound`: añade la salida y confirma.

    Si `add_outbound_order` lanza un error, no hay commit y `get_db` cierra la
    sesión: la transacción se deshace y el bloqueo de la fila se libera. El
    stock después se lee en la misma transacción, con la fila aún bloqueada.
    """
    exit_order = add_outbound_order(session, payload, user_uuid)
    stock_after = _available_stock(session, payload.asset_id)
    summary = _summary(session.get_one(Asset, payload.asset_id))
    session.commit()
    session.refresh(exit_order)
    return OutboundOrderCreated(
        **_outbound_read(exit_order, summary).model_dump(),
        stock_before=stock_after + payload.quantity,
        stock_after=stock_after,
        min_stock=settings.inventory_default_min_stock,
        currency=OFFICE_CURRENCY[Office(exit_order.office)],
    )


def list_orders(session: Session) -> list[OrderRead]:
    """Entradas y salidas con su activo, de la más reciente a la más antigua.

    Dos consultas con JOIN a `assets` (una por tabla), sea cual sea el número
    de órdenes. A igualdad de `created_at`, salidas antes que entradas y, dentro
    de cada tipo, `id` descendente: el orden es siempre el mismo.
    """
    entries = session.exec(select(AssetEntry, Asset).join(Asset, AssetEntry.asset_id == Asset.id)).all()
    exits = session.exec(select(AssetExit, Asset).join(Asset, AssetExit.asset_id == Asset.id)).all()
    orders: list[InboundOrderRead | OutboundOrderRead] = [
        _inbound_read(entry, _summary(asset)) for entry, asset in entries
    ]
    orders += [_outbound_read(exit_order, _summary(asset)) for exit_order, asset in exits]
    orders.sort(key=lambda order: (order.created_at, order.type, order.id), reverse=True)
    return orders
