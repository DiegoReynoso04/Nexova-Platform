"""Modelos ORM (SQLModel, `table=True`) del inventario de Nexova: activos, entradas y salidas.

Nombres y campos: docs/context-nexova-gestion-inventario-hito-5.md; el
vocabulario y los límites, en `vocabulary.py` (compartido con `schemas.py`).
Viven en la base PostgreSQL de Supabase; los usuarios siguen en TinyDB, así que
`user_uuid` es una cadena sin FK y aquí no hay ningún modelo de usuario.

Estos modelos nunca salen de la API: las rutas responden con los schemas
Pydantic de `schemas.py`. `current_stock` no es una columna: se calcula a partir
de las entradas y las salidas.

Decisiones de esquema (Hito 5, aprobadas por el usuario):

- `category`, `office` y `exit_type` se guardan como VARCHAR (`sa_type=String`),
  no como ENUM nativo de PostgreSQL. El vocabulario lo fijan los `CHECK`.
- `created_at` es `TIMESTAMP WITH TIME ZONE` y lo pone la aplicación en UTC.
- `asset_id` lleva índice explícito: PostgreSQL no indexa las FK por sí solo.
- `CHECK` en la base, como segunda barrera tras los schemas: `quantity > 0`, el
  vocabulario cerrado y la coherencia de `assigned_to` con `exit_type`.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ColumnElement, DateTime, String, and_, column, or_
from sqlmodel import Field, SQLModel

from .vocabulary import TEXT_MAX_LENGTH, USER_UUID_LENGTH, AssetCategory, ExitType, Office

# Ancho de las columnas de vocabulario: holgado sobre el valor más largo.
VOCABULARY_MAX_LENGTH = 32


def utc_now() -> datetime:
    return datetime.now(UTC)


def _one_of(name: str, vocabulary: type[StrEnum]) -> ColumnElement[bool]:
    return column(name).in_([member.value for member in vocabulary])


def _positive_quantity(table: str) -> CheckConstraint:
    return CheckConstraint(column("quantity") > 0, name=f"ck_{table}_quantity_positive")


def _known_office(table: str) -> CheckConstraint:
    return CheckConstraint(_one_of("office", Office), name=f"ck_{table}_office")


class Asset(SQLModel, table=True):
    """Equivale a `Product` del enunciado. El SKU es único en toda la base."""

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(_one_of("category", AssetCategory), name="ck_assets_category"),
        _known_office("assets"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=TEXT_MAX_LENGTH)
    sku: str = Field(max_length=TEXT_MAX_LENGTH, unique=True)
    category: AssetCategory = Field(sa_type=String(VOCABULARY_MAX_LENGTH))
    office: Office = Field(sa_type=String(VOCABULARY_MAX_LENGTH))


class AssetEntry(SQLModel, table=True):
    """Equivale a `InboundOrder`: una compra o entrega recibida por Nexova."""

    __tablename__ = "asset_entries"
    __table_args__ = (_positive_quantity("asset_entries"), _known_office("asset_entries"))

    id: int | None = Field(default=None, primary_key=True)
    asset_id: int = Field(foreign_key="assets.id", index=True)
    quantity: int
    supplier: str = Field(max_length=TEXT_MAX_LENGTH)
    office: Office = Field(sa_type=String(VOCABULARY_MAX_LENGTH))
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True), index=True)
    user_uuid: str = Field(max_length=USER_UUID_LENGTH)


class AssetExit(SQLModel, table=True):
    """Equivale a `OutboundOrder`: una asignación a un empleado o un consumo."""

    __tablename__ = "asset_exits"
    __table_args__ = (
        _positive_quantity("asset_exits"),
        _known_office("asset_exits"),
        CheckConstraint(_one_of("exit_type", ExitType), name="ck_asset_exits_exit_type"),
        # `allocation` exige `assigned_to`; `consumption` lo exige nulo.
        CheckConstraint(
            or_(
                and_(column("exit_type") == ExitType.ALLOCATION.value, column("assigned_to").is_not(None)),
                and_(column("exit_type") == ExitType.CONSUMPTION.value, column("assigned_to").is_(None)),
            ),
            name="ck_asset_exits_assigned_to",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    asset_id: int = Field(foreign_key="assets.id", index=True)
    quantity: int
    exit_type: ExitType = Field(sa_type=String(VOCABULARY_MAX_LENGTH))
    assigned_to: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    office: Office = Field(sa_type=String(VOCABULARY_MAX_LENGTH))
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True), index=True)
    user_uuid: str = Field(max_length=USER_UUID_LENGTH)


# Tablas del inventario, en orden de creación (las de órdenes dependen de `assets`).
INVENTORY_TABLES = (Asset.__table__, AssetEntry.__table__, AssetExit.__table__)
