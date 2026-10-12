"""Directorio de proveedores: las decisiones de negocio, sin HTTP.

Unidades: las funciones de ruta de `app/routes/suppliers.py`, llamadas con el
repositorio ya resuelto; `SupplierRepository` (`app/database.py`) con una
TinyDB temporal y un reloj inyectado, y las reglas de entrada de
`app/models.py`. Contexto: docs/ligthweight-storage-api.md y SPECS.md Parte B.

`test_suppliers_api.py` ya cubre el contrato HTTP (422, 404, CORS). Aquí se
fijan las reglas en la lógica, con el reloj controlado: `updated_at` es la
traza de la tarifa (cambia con ella y no con el estado), los filtros, el 404
de cada operación y el seed idempotente por `name`.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.errors import SupplierNotFoundError
from app.database import SupplierRepository
from app.models import Country, RateUpdate, StatusUpdate, SupplierCategory, SupplierCreate, SupplierStatus
from app.routes import suppliers as routes

from .conftest import FakeClock


def _supplier(**changes: Any) -> SupplierCreate:
    values: dict[str, Any] = {
        "name": "Synthetic Supplier",
        "country": "Spain",
        "categories": ["job_boards"],
        "monthly_rate": 100.0,
        "currency": "EUR",
        "status": "active",
    }
    values.update(changes)
    return SupplierCreate.model_validate(values)


def _rejected_fields(data: dict[str, Any]) -> set[str]:
    base: dict[str, Any] = {
        "name": "Synthetic Supplier",
        "country": "Spain",
        "categories": ["job_boards"],
        "monthly_rate": 100.0,
        "currency": "EUR",
        "status": "active",
    }
    with pytest.raises(ValidationError) as exc:
        SupplierCreate.model_validate({**base, **data})
    # Un error del validador de modelo (moneda/país) no tiene campo: se marca como "model".
    return {str(error["loc"][0]) if error["loc"] else "model" for error in exc.value.errors()}


# --- POST /suppliers ---


def test_created_supplier_gets_an_id_and_the_creation_time_as_updated_at(
    supplier_repo: SupplierRepository, clock: FakeClock
) -> None:
    created = routes.create_supplier(_supplier(name="  Synthetic Supplier  "), supplier_repo)

    assert created.id == 1
    assert created.updated_at == clock.now
    assert created.name == "Synthetic Supplier"
    assert supplier_repo.get(created.id) == created


@pytest.mark.parametrize(
    ("changes", "accepted"),
    [
        pytest.param({"monthly_rate": 0.01}, True, id="tarifa mínima positiva"),
        pytest.param({"monthly_rate": 1200}, True, id="tarifa entera"),
        pytest.param({"contract_renewal_date": "2028-02-29"}, True, id="29 de febrero bisiesto"),
        pytest.param({"categories": list(SupplierCategory)}, True, id="las 9 categorías"),
        pytest.param({"monthly_rate": 0}, False, id="tarifa 0"),
        pytest.param({"contract_renewal_date": "2026-02-29"}, False, id="29 de febrero no bisiesto"),
        pytest.param({"contract_renewal_date": "2026-3-1"}, False, id="fecha sin ceros"),
    ],
)
def test_rate_and_renewal_date_limits(changes: dict[str, Any], accepted: bool) -> None:
    # Tarifa > 0 y fecha real en formato YYYY-MM-DD canónico (Restricciones de negocio del CONTEXT).
    if accepted:
        _supplier(**changes)
    else:
        assert _rejected_fields(changes) == {next(iter(changes))}


@pytest.mark.parametrize(
    ("data", "field"),
    [
        pytest.param({"currency": "USD"}, "model", id="moneda de otro país"),
        pytest.param({"country": "France", "currency": "EUR"}, "country", id="país fuera de Spain/USA"),
        pytest.param({"categories": []}, "categories", id="sin categorías"),
        pytest.param({"categories": ["catering"]}, "categories", id="categoría desconocida"),
        pytest.param({"status": "deleted"}, "status", id="estado desconocido"),
        pytest.param({"monthly_rate": "1200"}, "monthly_rate", id="tarifa como texto"),
        pytest.param({"monthly_rate": float("inf")}, "monthly_rate", id="tarifa infinita"),
        pytest.param({"name": "   "}, "name", id="nombre en blanco"),
        pytest.param({"id": 7}, "id", id="id del cliente"),
        pytest.param({"updated_at": "2026-01-01T00:00:00Z"}, "updated_at", id="updated_at del cliente"),
    ],
)
def test_supplier_outside_the_context_rules_is_rejected(data: dict[str, Any], field: str) -> None:
    # Spain → EUR y USA → USD; enumeraciones cerradas; `id` y `updated_at` los fija el sistema.
    assert _rejected_fields(data) == {field}


# --- GET /suppliers ---


@pytest.fixture
def directory(supplier_repo: SupplierRepository) -> dict[str, int]:
    rows = {
        "spain_boards": _supplier(name="A", categories=["job_boards", "ats_software"]),
        "spain_training": _supplier(name="B", categories=["training_platforms"]),
        "usa_boards": _supplier(name="C", country="USA", currency="USD", categories=["job_boards"]),
    }
    return {key: supplier_repo.create(row).id for key, row in rows.items()}


def _ids(suppliers: list[Any]) -> set[int]:
    return {supplier.id for supplier in suppliers}


def test_list_without_filters_returns_every_supplier(supplier_repo: SupplierRepository, directory: dict[str, int]) -> None:
    assert _ids(routes.list_suppliers(supplier_repo)) == set(directory.values())


def test_category_filter_matches_any_of_the_supplier_categories(
    supplier_repo: SupplierRepository, directory: dict[str, int]
) -> None:
    # Un proveedor con varias categorías aparece al filtrar por cualquiera de ellas.
    found = routes.list_suppliers(supplier_repo, category=SupplierCategory.ATS_SOFTWARE)
    assert _ids(found) == {directory["spain_boards"]}


def test_country_and_category_filters_combine_with_and(supplier_repo: SupplierRepository, directory: dict[str, int]) -> None:
    found = routes.list_suppliers(supplier_repo, country=Country.USA, category=SupplierCategory.JOB_BOARDS)
    assert _ids(found) == {directory["usa_boards"]}
    assert routes.list_suppliers(supplier_repo, country=Country.USA, category=SupplierCategory.TRAINING_PLATFORMS) == []


def test_empty_directory_lists_nothing(supplier_repo: SupplierRepository) -> None:
    assert routes.list_suppliers(supplier_repo) == []


# --- GET /suppliers/{id}, PATCH rate, PATCH status, DELETE: el 404 ---


@pytest.mark.parametrize("operation", ["get", "rate", "status", "delete"])
def test_every_operation_on_a_missing_supplier_is_not_found_and_writes_nothing(
    supplier_repo: SupplierRepository, directory: dict[str, int], operation: str
) -> None:
    before = supplier_repo.find()
    calls = {
        "get": lambda: routes.get_supplier(999, supplier_repo),
        "rate": lambda: routes.update_supplier_rate(999, RateUpdate(monthly_rate=50.0), supplier_repo),
        "status": lambda: routes.update_supplier_status(999, StatusUpdate(status=SupplierStatus.SUSPENDED), supplier_repo),
        "delete": lambda: routes.delete_supplier(999, supplier_repo),
    }
    with pytest.raises(SupplierNotFoundError):
        calls[operation]()
    assert supplier_repo.find() == before


def test_get_returns_the_supplier(supplier_repo: SupplierRepository, directory: dict[str, int]) -> None:
    assert routes.get_supplier(directory["spain_training"], supplier_repo).name == "B"


# --- PATCH /suppliers/{id}/rate ---


def test_rate_change_records_the_time_of_the_change(
    supplier_repo: SupplierRepository, clock: FakeClock, directory: dict[str, int]
) -> None:
    # `updated_at` es la trazabilidad de tarifas: la hora del último cambio de tarifa.
    clock.advance(days=3, minutes=5)

    updated = routes.update_supplier_rate(directory["spain_boards"], RateUpdate(monthly_rate=150.5), supplier_repo)

    assert (updated.monthly_rate, updated.updated_at) == (150.5, clock.now)
    assert supplier_repo.get(directory["spain_boards"]) == updated


@pytest.mark.parametrize("rate", [0, -10.0, "150", float("nan")])
def test_invalid_rate_update_is_rejected(rate: object) -> None:
    with pytest.raises(ValidationError):
        RateUpdate.model_validate({"monthly_rate": rate})


# --- PATCH /suppliers/{id}/status ---


def test_status_change_does_not_touch_updated_at(
    supplier_repo: SupplierRepository, clock: FakeClock, directory: dict[str, int]
) -> None:
    # Suspender o reactivar no es un cambio de tarifa: `updated_at` se conserva.
    supplier_id = directory["spain_boards"]
    stored = supplier_repo.get(supplier_id)
    assert stored is not None
    created_at = stored.updated_at
    clock.advance(days=10)

    suspended = routes.update_supplier_status(supplier_id, StatusUpdate(status=SupplierStatus.SUSPENDED), supplier_repo)
    clock.advance(days=1)
    reactivated = routes.update_supplier_status(supplier_id, StatusUpdate(status=SupplierStatus.ACTIVE), supplier_repo)

    assert suspended.status == SupplierStatus.SUSPENDED
    assert reactivated.status == SupplierStatus.ACTIVE
    assert suspended.updated_at == reactivated.updated_at == created_at


def test_status_outside_the_context_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StatusUpdate.model_validate({"status": "deleted"})


# --- DELETE /suppliers/{id} ---


def test_delete_removes_only_that_supplier_and_a_second_delete_is_not_found(
    supplier_repo: SupplierRepository, directory: dict[str, int]
) -> None:
    target = directory["spain_training"]

    routes.delete_supplier(target, supplier_repo)

    assert supplier_repo.get(target) is None
    assert _ids(supplier_repo.find()) == {directory["spain_boards"], directory["usa_boards"]}
    with pytest.raises(SupplierNotFoundError):
        routes.delete_supplier(target, supplier_repo)


# --- Seed ---


def test_seed_inserts_only_names_not_yet_present_and_never_overwrites(
    supplier_repo: SupplierRepository, clock: FakeClock
) -> None:
    # Idempotente por `name`: un proveedor ya cargado (aunque se haya editado) no se pisa.
    existing = supplier_repo.create(_supplier(name="A", monthly_rate=999.0))
    clock.advance(days=1)

    first = supplier_repo.seed([_supplier(name="A"), _supplier(name="B")])
    second = supplier_repo.seed([_supplier(name="A"), _supplier(name="B")])

    assert (first.inserted, first.skipped, first.total) == (1, 1, 2)
    assert (second.inserted, second.skipped, second.total) == (0, 2, 2)
    assert supplier_repo.get(existing.id) == existing
