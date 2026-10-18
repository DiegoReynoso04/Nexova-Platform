"""Schemas Pydantic de request y response del inventario.

Son `BaseModel` de Pydantic, no SQLModel, y no importan `models.py`: ninguna
ruta devuelve un objeto ORM. Su forma tampoco coincide con la de las tablas:
`AssetCreate` no tiene `id` y `AssetRead` añade `current_stock`, que no se
guarda (se calcula con las entradas y las salidas, ver `service.py`).
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from .vocabulary import TEXT_MAX_LENGTH, AssetCategory, Office

# Texto libre: sin espacios en los extremos, no vacío y con el tope técnico.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TEXT_MAX_LENGTH)]

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
