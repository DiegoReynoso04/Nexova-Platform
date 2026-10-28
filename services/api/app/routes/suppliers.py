"""Endpoints del directorio de proveedores: request → TinyDB → respuesta.

Las validaciones las hace Pydantic (`app/models.py`) antes de llegar aquí; una
entrada inválida responde 422 y nunca toca la base de datos.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.errors import SupplierNotFoundError
from app.database import SupplierRepository
from app.models import Country, RateUpdate, StatusUpdate, Supplier, SupplierCategory, SupplierCreate, SupplierRead

router = APIRouter(tags=["suppliers"])


def get_repository(request: Request) -> SupplierRepository:
    repository = request.app.state.supplier_repository
    assert isinstance(repository, SupplierRepository)
    return repository


RepositoryDep = Annotated[SupplierRepository, Depends(get_repository)]


def _found(supplier: Supplier | None) -> SupplierRead:
    if supplier is None:
        raise SupplierNotFoundError()
    return supplier.public()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SupplierRead)
def create_supplier(payload: SupplierCreate, repository: RepositoryDep) -> SupplierRead:
    return repository.create(payload).public()


@router.get("", response_model=list[SupplierRead])
def list_suppliers(
    repository: RepositoryDep,
    country: Country | None = None,
    category: SupplierCategory | None = None,
) -> list[SupplierRead]:
    """Todos los proveedores; `country` y `category` son opcionales y combinables."""
    return [supplier.public() for supplier in repository.find(country=country, category=category)]


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: int, repository: RepositoryDep) -> SupplierRead:
    return _found(repository.get(supplier_id))


@router.patch("/{supplier_id}/rate", response_model=SupplierRead)
def update_supplier_rate(supplier_id: int, payload: RateUpdate, repository: RepositoryDep) -> SupplierRead:
    """Actualiza `monthly_rate` y registra `updated_at` con la hora del cambio (UTC)."""
    return _found(repository.update_rate(supplier_id, payload.monthly_rate))


@router.patch("/{supplier_id}/status", response_model=SupplierRead)
def update_supplier_status(supplier_id: int, payload: StatusUpdate, repository: RepositoryDep) -> SupplierRead:
    return _found(repository.update_status(supplier_id, payload.status))


@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # Sin cuerpo: `response_model=None` declarado (auditoría de serialización, D7).
    response_model=None,
    response_class=Response,
    responses={204: {"description": "Proveedor eliminado, sin cuerpo"}},
)
def delete_supplier(supplier_id: int, repository: RepositoryDep) -> Response:
    """Elimina el proveedor. Lo exige el brief; la UI no lo expone (ver SPECS.md)."""
    if not repository.delete(supplier_id):
        raise SupplierNotFoundError()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
