"""Comando `uv run seed-inventory --email <usuario>`: datos semilla del inventario en Supabase.

Ejecución (desde `services/api`):

    uv run --env-file .env seed-inventory --email usuario@example.com

Sin uv, con el venv del servicio: `python -m app.modules.inventory.seed --email ...`.

- Activos, entradas y salidas de docs/context-nexova-gestion-inventario-hito-5.md
  ("Datos Semilla"): los 6 activos literales; las cantidades y proveedores que
  el CONTEXT deja abiertos los aprobó el usuario (Hito 5, plan de F4).
- Las órdenes se registran a nombre del usuario indicado: su `id` de TinyDB
  (`AUTH_DB_PATH`) es el `user_uuid`. Debe existir y estar activo.
- Idempotente: los activos se buscan por `sku` y no se tocan si ya existen; las
  órdenes de un activo solo se insertan si ese activo no tiene ninguna. Una
  segunda ejecución inserta 0.
- Una sola transacción: o se carga todo o nada. Las órdenes pasan por la misma
  validación (schemas) y las mismas reglas que la API (`service.add_*_order`,
  sin commit por orden), incluida la regla del stock.
- Códigos de salida: 0 bien; 1 error de configuración (`DATABASE_URL` u otra
  variable, o falta `--email`), usuario inexistente o inactivo, o datos
  semilla que la API rechazaría; 2 una base no disponible (Supabase o el
  archivo TinyDB de usuarios). Los mensajes van a stderr, sin traceback, sin
  URL, host, usuario de la base ni el email.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import ValidationError
from sqlalchemy import Engine, func
from sqlmodel import Session, select

from app.auth.models import normalize_email
from app.auth.repository import AuthRepository
from app.core.config import ConfigError, Settings
from app.core.errors import DATABASE_UNAVAILABLE_ERRORS, ApiError, StorageUnavailableError

from . import service
from .database import InventoryStartupError, build_engine, init_db
from .models import Asset, AssetEntry, AssetExit
from .schemas import AssetCreate, InboundOrderCreate, OutboundOrderCreate

# Los 6 activos del CONTEXT, literales.
SEED_ASSETS: list[dict[str, str]] = [
    {"name": 'Portátil 14" Business', "sku": "NXV-IT-001", "category": "hardware", "office": "Valencia"},
    {"name": 'Portátil 14" Business', "sku": "NXV-IT-002", "category": "hardware", "office": "Miami"},
    {"name": "Ratón ergonómico", "sku": "NXV-PER-001", "category": "peripherals", "office": "Valencia"},
    {"name": "Hub USB-C", "sku": "NXV-PER-002", "category": "peripherals", "office": "Miami"},
    {"name": "Resma de papel A4", "sku": "NXV-OFF-001", "category": "office_supplies", "office": "Valencia"},
    {"name": "Cuaderno de formación en liderazgo", "sku": "NXV-TRN-001", "category": "training_materials", "office": "Valencia"},
]

# Entradas: las dos de NXV-IT-001 (10 y 5) las da el CONTEXT; el resto y los
# proveedores (nombres del CONTEXT) los aprobó el usuario. La oficina de cada
# orden es la del activo.
SEED_ENTRIES: list[dict[str, object]] = [
    {"sku": "NXV-IT-001", "quantity": 10, "supplier": "TechDistrib Valencia S.L."},
    {"sku": "NXV-IT-001", "quantity": 5, "supplier": "TechDistrib Valencia S.L."},
    {"sku": "NXV-PER-002", "quantity": 8, "supplier": "Office Depot Miami"},
    {"sku": "NXV-OFF-001", "quantity": 20, "supplier": "TechDistrib Valencia S.L."},
]

# Salidas: al menos una `allocation` y una `consumption` (CONTEXT). Los
# `EMPLEADO-FICTICIO-*` son identificadores FICTICIOS: el CONTEXT no da
# empleados de Nexova, así que no corresponden a ninguna persona real.
SEED_EXITS: list[dict[str, object]] = [
    {"sku": "NXV-IT-001", "quantity": 2, "exit_type": "allocation", "assigned_to": "EMPLEADO-FICTICIO-01"},
    {"sku": "NXV-OFF-001", "quantity": 5, "exit_type": "consumption", "assigned_to": None},
    {"sku": "NXV-PER-002", "quantity": 1, "exit_type": "allocation", "assigned_to": "EMPLEADO-FICTICIO-02"},
]

CONFIG_ERROR_EXIT = 1
DATABASE_UNAVAILABLE_EXIT = 2

Payload = TypeVar("Payload", InboundOrderCreate, OutboundOrderCreate)


class SeedDataError(Exception):
    """Un dato semilla que la API rechazaría (validación o regla de negocio). Nada se escribe."""


@dataclass
class SeedResult:
    assets_inserted: int = 0
    assets_existing: int = 0
    entries_inserted: int = 0
    exits_inserted: int = 0
    # Activos que ya tenían órdenes: las suyas del seed no se insertan.
    assets_with_orders: int = 0
    stock: dict[str, int] = field(default_factory=dict)


def _has_orders(session: Session, asset_id: int) -> bool:
    entries = session.exec(select(func.count()).select_from(AssetEntry).where(AssetEntry.asset_id == asset_id)).one()
    exits = session.exec(select(func.count()).select_from(AssetExit).where(AssetExit.asset_id == asset_id)).one()
    return entries + exits > 0


def seed(session: Session, user_uuid: str) -> SeedResult:
    """Añade los datos semilla a la transacción de `session`, sin commit.

    Lanza `SeedDataError` si un dato no pasa la validación o las reglas de la
    API (por ejemplo, una salida que dejaría el stock en negativo).
    """
    result = SeedResult()
    assets: dict[str, Asset] = {}
    for values in SEED_ASSETS:
        existing = session.exec(select(Asset).where(Asset.sku == values["sku"])).first()
        if existing is not None:
            assets[existing.sku] = existing
            result.assets_existing += 1
            continue
        try:
            asset = Asset(**AssetCreate(**values).model_dump())
        except ValidationError:
            raise SeedDataError(f"activo {values['sku']}: no pasa la validación de la API") from None
        session.add(asset)
        session.flush()
        assets[asset.sku] = asset
        result.assets_inserted += 1

    seeded_skus = list(dict.fromkeys(str(order["sku"]) for order in [*SEED_ENTRIES, *SEED_EXITS]))
    for sku in seeded_skus:
        asset = assets[sku]
        assert asset.id is not None
        if _has_orders(session, asset.id):
            result.assets_with_orders += 1
            continue
        # Entradas antes que salidas: las salidas se comprueban contra ese stock.
        for order in _orders_of(SEED_ENTRIES, sku):
            payload = _payload(InboundOrderCreate, sku, asset, order)
            _apply(sku, service.add_inbound_order, session, payload, user_uuid)
            result.entries_inserted += 1
        for order in _orders_of(SEED_EXITS, sku):
            payload = _payload(OutboundOrderCreate, sku, asset, order)
            _apply(sku, service.add_outbound_order, session, payload, user_uuid)
            result.exits_inserted += 1

    result.stock = {item.sku: item.current_stock for item in service.list_assets(session) if item.sku in assets}
    return result


def _orders_of(orders: list[dict[str, object]], sku: str) -> list[dict[str, object]]:
    return [{key: value for key, value in order.items() if key != "sku"} for order in orders if order["sku"] == sku]


def _payload(schema: type[Payload], sku: str, asset: Asset, values: dict[str, object]) -> Payload:
    """La orden del seed como request de la API (misma validación); la oficina es la del activo."""
    try:
        return schema.model_validate({"asset_id": asset.id, "office": asset.office, **values})
    except ValidationError:
        raise SeedDataError(f"orden de {sku}: no pasa la validación de la API") from None


def _apply(sku: str, add: Callable[[Session, Payload, str], object], session: Session, payload: Payload, user_uuid: str) -> None:
    """Añade la orden con la lógica de la API (sin commit); un rechazo de la API pasa a `SeedDataError`."""
    message: str | None = None
    try:
        add(session, payload, user_uuid)
    except ApiError as error:
        # Sin el punto final: el mensaje de la CLI añade el suyo.
        message = f"orden de {sku}: {str(error.detail).rstrip('.')}"
    if message is not None:
        raise SeedDataError(message)


def _seed_database(engine: Engine, user_uuid: str) -> SeedResult:
    init_db(engine)
    with Session(engine) as session:
        result = seed(session, user_uuid)
        session.commit()
    return result


def run(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed-inventory", description="Carga los datos semilla del inventario (Hito 5) en la base de DATABASE_URL."
    )
    parser.add_argument("--email", required=True, help="Email de un usuario existente: las órdenes van a su nombre")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        # argparse sale con 2 ante un argumento inválido; aquí 2 es «base no
        # disponible», así que un uso incorrecto es un error de configuración.
        return CONFIG_ERROR_EXIT if exit_request.code else 0

    if settings is None:
        try:
            settings = Settings.from_env()
        except ConfigError as error:
            # Los mensajes de ConfigError son fijos: nombran la variable, nunca su valor.
            print(f"Error de configuración: {error}", file=sys.stderr)
            return CONFIG_ERROR_EXIT
    try:
        settings.require_database()
        engine = build_engine(settings.database_url)
    except ConfigError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return CONFIG_ERROR_EXIT

    try:
        email = normalize_email(args.email)
    except ValueError:
        email = None
    user = None
    users_unavailable = False
    if email is not None:
        try:
            user = AuthRepository(settings.auth_db_path).get_user_by_email(email)
        except StorageUnavailableError:
            users_unavailable = True
    if users_unavailable:
        print(
            f"Error: no se pudo leer la base de usuarios ({settings.auth_db_path.name}). "
            "Revisa AUTH_DB_PATH, los permisos y que sea un archivo TinyDB válido.",
            file=sys.stderr,
        )
        return DATABASE_UNAVAILABLE_EXIT
    if user is None or not user.is_active:
        # Sin repetir el email recibido.
        print("Error: no existe ningún usuario activo con ese email en la base de usuarios. No se ha cargado nada.", file=sys.stderr)
        return CONFIG_ERROR_EXIT

    failure: str | None = None
    data_error: str | None = None
    try:
        result = _seed_database(engine, str(user.id))
    except InventoryStartupError as error:
        failure = error.error_class
    except DATABASE_UNAVAILABLE_ERRORS as error:
        failure = type(error).__name__
    except SeedDataError as error:
        data_error = str(error)
    finally:
        engine.dispose()
    if failure is not None:
        print(
            f"Error: la base de datos del inventario no está disponible ({failure}). No se ha cargado nada.",
            file=sys.stderr,
        )
        return DATABASE_UNAVAILABLE_EXIT
    if data_error is not None:
        print(f"Error en los datos semilla: {data_error}. No se ha cargado nada.", file=sys.stderr)
        return CONFIG_ERROR_EXIT

    print(f"Órdenes a nombre del usuario {user.id}")
    print(f"Activos insertados: {result.assets_inserted}")
    print(f"Activos ya existentes (omitidos): {result.assets_existing}")
    print(f"Entradas insertadas: {result.entries_inserted}")
    print(f"Salidas insertadas: {result.exits_inserted}")
    if result.assets_with_orders:
        print(f"Activos que ya tenían órdenes (no se les añade ninguna): {result.assets_with_orders}")
    print("Stock por SKU:")
    for sku, stock in result.stock.items():
        print(f"  {sku}: {stock}")
    return 0


def main() -> None:
    """Punto de entrada de `uv run seed-inventory` (`[project.scripts]` en pyproject.toml)."""
    sys.exit(run())


if __name__ == "__main__":
    main()
