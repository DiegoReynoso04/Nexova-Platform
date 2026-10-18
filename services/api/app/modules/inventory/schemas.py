"""Schemas Pydantic de request y response del inventario.

Son `BaseModel` de Pydantic, no SQLModel, y no importan `models.py`: ninguna
ruta devuelve un objeto ORM. Su forma tampoco coincide con la de las tablas:
`AssetCreate` no tiene `id`, `AssetRead` añade `current_stock`, que no se
guarda (se calcula con las entradas y las salidas, ver `service.py`), y las
órdenes llevan el activo embebido (`AssetSummary`) en vez de `asset_id`.

Ningún request acepta `user_uuid` (`extra="forbid"`): lo pone la API con el
usuario del token.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, field_validator

from .vocabulary import QUANTITY_MAX, TEXT_MAX_LENGTH, AssetCategory, ExitType, Office

# Texto libre: sin espacios en los extremos, no vacío y con el tope técnico.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TEXT_MAX_LENGTH)]
# Enteros estrictos: ni "5" ni `true` ni 5.0 pasan por una cantidad o un id.
Quantity = Annotated[int, Field(strict=True, ge=1, le=QUANTITY_MAX)]
AssetId = Annotated[int, Field(strict=True)]

_ASSET_EXAMPLE = {
    "name": 'Portátil 14" Business',
    "sku": "NXV-IT-001",
    "category": AssetCategory.HARDWARE.value,
    "office": Office.VALENCIA.value,
}


class AssetCreate(BaseModel):
    """`POST /inventory/products`. Sin stock: un activo nace con 0 y solo crece con entradas."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [_ASSET_EXAMPLE]})

    name: Text
    sku: Text
    category: AssetCategory
    office: Office


class AssetRead(BaseModel):
    """Un activo tal como lo devuelve la API, con su stock calculado."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    sku: str
    category: AssetCategory
    office: Office
    current_stock: int


class InboundOrderCreate(BaseModel):
    """`POST /inventory/orders/inbound`: una compra o entrega recibida (`AssetEntry`)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"asset_id": 1, "quantity": 10, "supplier": "TechDistrib Valencia S.L.", "office": Office.VALENCIA.value}
            ]
        },
    )

    asset_id: AssetId
    quantity: Quantity
    supplier: Text
    office: Office


class OutboundOrderCreate(BaseModel):
    """`POST /inventory/orders/outbound`: una asignación o un consumo (`AssetExit`).

    `exit_type` va antes que `assigned_to`: el validador de `assigned_to` lo lee
    de `info.data`. El error sale con `loc` en `assigned_to` (también cuando el
    campo falta, por `validate_default`), para mostrarlo junto a ese campo.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "asset_id": 1,
                    "quantity": 1,
                    "exit_type": ExitType.ALLOCATION.value,
                    "assigned_to": "Example employee",
                    "office": Office.VALENCIA.value,
                },
                {
                    "asset_id": 5,
                    "quantity": 2,
                    "exit_type": ExitType.CONSUMPTION.value,
                    "assigned_to": None,
                    "office": Office.VALENCIA.value,
                },
            ]
        },
    )

    asset_id: AssetId
    quantity: Quantity
    exit_type: ExitType
    assigned_to: Text | None = Field(default=None, validate_default=True)
    office: Office

    @field_validator("assigned_to")
    @classmethod
    def _assigned_to_matches_exit_type(cls, value: str | None, info: ValidationInfo) -> str | None:
        exit_type = info.data.get("exit_type")
        if exit_type == ExitType.ALLOCATION and value is None:
            raise ValueError("assigned_to is required when exit_type is 'allocation'")
        if exit_type == ExitType.CONSUMPTION and value is not None:
            raise ValueError("assigned_to must be null when exit_type is 'consumption'")
        # Sin `exit_type` válido ya hay un error en ese campo: no se añade otro aquí.
        return value


class AssetSummary(BaseModel):
    """El activo embebido en cada orden."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    sku: str


class InboundOrderRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["inbound"] = "inbound"
    id: int
    asset: AssetSummary
    quantity: int
    supplier: str
    office: Office
    created_at: AwareDatetime
    user_uuid: str


class OutboundOrderRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["outbound"] = "outbound"
    id: int
    asset: AssetSummary
    quantity: int
    exit_type: ExitType
    assigned_to: str | None
    office: Office
    created_at: AwareDatetime
    user_uuid: str


# `GET /inventory/orders`: entradas y salidas en una sola lista, distinguidas por `type`.
OrderRead = Annotated[InboundOrderRead | OutboundOrderRead, Field(discriminator="type")]


class ErrorResponse(BaseModel):
    """Forma de los errores de la API (`{detail, code}`, `app/core/errors.py`). Solo documenta OpenAPI."""

    detail: str
    code: str
