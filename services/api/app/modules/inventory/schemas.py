"""Schemas Pydantic de request y response del inventario.

Son `BaseModel` de Pydantic, no SQLModel, y no importan `models.py`: ninguna
ruta devuelve un objeto ORM. Su forma tampoco coincide con la de las tablas:
`AssetCreate` no tiene `id`, `AssetRead` añade `current_stock`, que no se
guarda (se calcula con las entradas y las salidas, ver `service.py`), y las
órdenes llevan el activo embebido (`AssetSummary`) en vez de `asset_id`.

Ningún request acepta `user_uuid` (`extra="forbid"`): lo pone la API con el
usuario del token. Tampoco `currency` (P3 del plan de telemetría): la deriva la
API de la oficina.

Ticket de captura de telemetría (D1 «A ligera»): las respuestas de alta de
entradas y salidas (`InboundOrderCreated`, `OutboundOrderCreated`) añaden lo que
solo sabe la API, para que el frontend emita los eventos obligatorios con
`track()` sin calcular nada: el stock antes y después y el mínimo en la salida,
y la clave seudónima del proveedor y la variación de coste en la entrada. El
listado (`GET /inventory/orders`) no lleva esos campos: son del momento del alta.
"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, field_validator

from .vocabulary import (
    QUANTITY_MAX,
    TEXT_MAX_LENGTH,
    UNIT_COST_DECIMAL_PLACES,
    UNIT_COST_MAX_DIGITS,
    AssetCategory,
    Currency,
    ExitType,
    Office,
)

# Texto libre: sin espacios en los extremos, no vacío y con el tope técnico.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TEXT_MAX_LENGTH)]
# Enteros estrictos: ni "5" ni `true` ni 5.0 pasan por una cantidad o un id.
Quantity = Annotated[int, Field(strict=True, ge=1, le=QUANTITY_MAX)]
AssetId = Annotated[int, Field(strict=True)]
# P3: coste unitario positivo, con 2 decimales como máximo (NUMERIC(12,2)).
UnitCost = Annotated[Decimal, Field(gt=0, max_digits=UNIT_COST_MAX_DIGITS, decimal_places=UNIT_COST_DECIMAL_PLACES)]

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


class InboundOrderFields(BaseModel):
    """Campos comunes de una entrada. Sin coste: así entran las del seed, que el CONTEXT da sin coste."""

    model_config = ConfigDict(extra="forbid")

    asset_id: AssetId
    quantity: Quantity
    supplier: Text
    office: Office


class InboundOrderCreate(InboundOrderFields):
    """`POST /inventory/orders/inbound`: una compra o entrega recibida (`AssetEntry`), con su coste unitario."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "asset_id": 1,
                    "quantity": 10,
                    "supplier": "TechDistrib Valencia S.L.",
                    "office": Office.VALENCIA.value,
                    "unit_cost": 18.5,
                }
            ]
        },
    )

    unit_cost: UnitCost


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
    # P3: `null` en las entradas anteriores al coste (y en las del seed).
    unit_cost: float | None
    currency: Currency | None


class CostVariance(BaseModel):
    """Variación del coste unitario frente a la referencia del mismo activo y proveedor (P10)."""

    model_config = ConfigDict(frozen=True)

    reference_unit_cost: float
    variance_pct: float
    direction: Literal["increase", "decrease"]
    threshold_pct: float
    reference_window: int


class InboundOrderCreated(InboundOrderRead):
    """Respuesta 201 de `POST /inventory/orders/inbound`: la entrada y lo que el frontend emite con ella."""

    # P9: HMAC-SHA256 del proveedor normalizado; `null` sin `TELEMETRY_SUPPLIER_KEY`.
    supplier_key: str | None
    # P10: `null` si no se desvía más del umbral o no hay bastantes entradas anteriores con coste.
    cost_variance: CostVariance | None


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


class OutboundOrderCreated(OutboundOrderRead):
    """Respuesta 201 de `POST /inventory/orders/outbound`: la salida y el stock que calculó la API bajo `FOR UPDATE`."""

    stock_before: int
    stock_after: int
    # `INVENTORY_DEFAULT_MIN_STOCK` (5 por defecto): aún no hay mínimo por activo (P2 pendiente).
    min_stock: int
    currency: Currency


# `GET /inventory/orders`: entradas y salidas en una sola lista, distinguidas por `type`.
OrderRead = Annotated[InboundOrderRead | OutboundOrderRead, Field(discriminator="type")]


class ErrorResponse(BaseModel):
    """Forma de los errores de la API (`{detail, code}`, `app/core/errors.py`). Solo documenta OpenAPI."""

    detail: str
    code: str
