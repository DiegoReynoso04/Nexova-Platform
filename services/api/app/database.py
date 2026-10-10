"""Inicialización y acceso a TinyDB para el directorio de proveedores.

Un único archivo JSON (`Settings.suppliers_db_path`, por defecto
`services/api/data/suppliers.json`, ignorado por git) con la tabla `suppliers`.
El `id` de cada proveedor es el `doc_id` que asigna TinyDB.

TinyDB no es thread-safe y FastAPI ejecuta los endpoints síncronos en un pool
de hilos: todas las operaciones pasan por un `threading.Lock` y la API debe
ejecutarse con un único worker (igual que el resto del servicio). La base se
abre y se cierra en cada operación: cada escritura queda en disco al terminar
y no queda ningún descriptor abierto entre peticiones.

Solo recibe modelos ya validados por Pydantic (`app/models.py`).
"""

import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tinydb import Query, TinyDB
from tinydb.table import Document, Table

from app.core.storage import GuardedJSONStorage, Store
from app.models import Country, Supplier, SupplierCategory, SupplierCreate, SupplierStatus

SUPPLIERS_TABLE = "suppliers"


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class SeedResult:
    inserted: int
    skipped: int
    total: int


class SupplierRepository:
    def __init__(self, path: Path, clock: Callable[[], datetime] = utc_now) -> None:
        self.path = path
        self._clock = clock
        self._lock = threading.Lock()

    @contextmanager
    def _table(self) -> Iterator[Table]:
        # Un archivo ilegible o corrupto responde 503 (GuardedJSONStorage).
        with self._lock, TinyDB(
            self.path, storage=GuardedJSONStorage, store=Store.SUPPLIERS, create_dirs=True, encoding="utf-8", indent=2
        ) as db:
            yield db.table(SUPPLIERS_TABLE)

    def _record(self, supplier: SupplierCreate) -> dict[str, Any]:
        record = supplier.model_dump(mode="json")
        record["updated_at"] = self._clock().isoformat()
        return record

    def find(
        self, country: Country | None = None, category: SupplierCategory | None = None
    ) -> list[Supplier]:
        with self._table() as table:
            documents = table.all()
        return [
            supplier
            for supplier in map(_to_supplier, documents)
            if (country is None or supplier.country == country)
            and (category is None or category in supplier.categories)
        ]

    def get(self, supplier_id: int) -> Supplier | None:
        with self._table() as table:
            document = table.get(doc_id=supplier_id)
        return _to_supplier(document) if isinstance(document, Document) else None

    def create(self, supplier: SupplierCreate) -> Supplier:
        with self._table() as table:
            supplier_id = table.insert(self._record(supplier))
            document = table.get(doc_id=supplier_id)
        assert isinstance(document, Document)
        return _to_supplier(document)

    def update_rate(self, supplier_id: int, monthly_rate: float) -> Supplier | None:
        """Cambia la tarifa y registra `updated_at` (trazabilidad de tarifas)."""
        return self._update(supplier_id, {"monthly_rate": monthly_rate, "updated_at": self._clock().isoformat()})

    def update_status(self, supplier_id: int, status: SupplierStatus) -> Supplier | None:
        """Activa o suspende. No toca `updated_at`: ese campo es el de la tarifa."""
        return self._update(supplier_id, {"status": status.value})

    def _update(self, supplier_id: int, fields: dict[str, Any]) -> Supplier | None:
        with self._table() as table:
            if not table.contains(doc_id=supplier_id):
                return None
            table.update(fields, doc_ids=[supplier_id])
            document = table.get(doc_id=supplier_id)
        assert isinstance(document, Document)
        return _to_supplier(document)

    def delete(self, supplier_id: int) -> bool:
        with self._table() as table:
            if not table.contains(doc_id=supplier_id):
                return False
            table.remove(doc_ids=[supplier_id])
        return True

    def seed(self, suppliers: Iterable[SupplierCreate]) -> SeedResult:
        """Inserta los proveedores cuyo `name` aún no existe. Idempotente."""
        inserted = skipped = 0
        with self._table() as table:
            for supplier in suppliers:
                if table.contains(Query().name == supplier.name):
                    skipped += 1
                else:
                    table.insert(self._record(supplier))
                    inserted += 1
            total = len(table)
        return SeedResult(inserted=inserted, skipped=skipped, total=total)


def _to_supplier(document: Document) -> Supplier:
    return Supplier.model_validate({**document, "id": document.doc_id})
