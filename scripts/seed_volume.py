"""Seed de volumen SINTÉTICO para medir el coste de las lecturas (ticket de caching, F0).

Solo para bases de prueba: nunca la demo. Llena, con datos variados y
coherentes con el vocabulario real, las colecciones que alimentan las lecturas
más pesadas de la API:

- `incidents`: miles de incidencias del gestor (TinyDB, `INCIDENTS_DB_PATH`),
  con categoría, origen, sede, estado y fecha repartidos.
- `suppliers`: cientos de proveedores (TinyDB, `SUPPLIERS_DB_PATH`), con país,
  moneda del país, categorías, tarifa y renovación coherentes.
- `inventory`: activos con cientos de entradas y salidas cada uno (PostgreSQL,
  `DATABASE_URL`), con el stock nunca negativo, a nombre de un usuario de
  `AUTH_DB_PATH` (`--email`, como `seed-inventory`).

Todo es reconocible como sintético: títulos con «[SINTÉTICO]», proveedores
«Proveedor sintético NNN», SKU `SYN-…`, empleados `EMPLEADO-SINTETICO-NNN` y
emails en `example.invalid`. Ningún nombre, cifra ni persona es de Nexova.

- **Determinista:** semilla fija (`SEED`) y fecha de referencia fija
  (`REFERENCE`), no la hora actual: dos bases sembradas con los mismos
  argumentos tienen el mismo contenido. Los identificadores (UUID de las
  incidencias, `doc_id` de TinyDB, `id` de PostgreSQL) los asigna cada almacén.
- **Idempotente:** incidencias por su clave de origen (`seed_keys`, como el seed
  del CSV); proveedores por `name` (`SupplierRepository.seed`); activos por
  `sku`, y las órdenes de un activo solo si aún no tiene ninguna (como
  `seed-inventory`). Una segunda ejecución inserta 0.
- **Mismas reglas que la API:** las incidencias pasan por
  `nexova_shared.incidents.validate_incident_fields`, los proveedores por
  `SupplierCreate` y las órdenes por `InboundOrderCreate`/`OutboundOrderCreate`.
  Las órdenes se insertan en bloque (no una a una con `FOR UPDATE`), pero el
  generador lleva el stock y nunca saca más de lo que hay.
- **Protecciones:** se niega a escribir en los archivos TinyDB de
  `services/api/data` (los de la demo) y en cualquier PostgreSQL que no esté en
  `localhost`, `127.0.0.1` o el nombre del contenedor de prueba
  (`--allow-db-host`). Las rutas de TinyDB son obligatorias para lo que se siembre.

Uso (en el contenedor de medición, con las variables de las bases de prueba;
ver docs/caching-analysis.md §3):

    python scripts/seed_volume.py incidents suppliers inventory --email <cuenta de prueba>

Códigos de salida: 0 bien; 1 configuración o protección (base de la demo,
variable ausente, usuario inexistente); 2 base no disponible.
"""

import argparse
import hashlib
import importlib.util
import os
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DATA_DIR = REPO_ROOT / "services" / "api" / "data"

for module, folder in (("nexova_shared", REPO_ROOT / "packages" / "shared"), ("app", REPO_ROOT / "services" / "api")):
    if importlib.util.find_spec(module) is None:
        sys.path.insert(0, str(folder))

try:
    from nexova_shared.incidents import (
        Branch,
        IncidentCategory,
        IncidentOrigin,
        IncidentStatus,
        SeedIncident,
        validate_incident_fields,
    )
    from sqlalchemy import func
    from sqlalchemy.engine import make_url
    from sqlmodel import Session, select

    from app.auth.models import normalize_email
    from app.auth.repository import AuthRepository
    from app.core.config import ConfigError, Settings
    from app.core.errors import DATABASE_UNAVAILABLE_ERRORS, StorageUnavailableError
    from app.database import SupplierRepository
    from app.models import CURRENCY_BY_COUNTRY, Country, SupplierCategory, SupplierCreate, SupplierStatus
    from app.modules.incident_manager.repository import IncidentRepository
    from app.modules.inventory.database import InventoryStartupError, build_engine, init_db
    from app.modules.inventory.models import Asset, AssetEntry, AssetExit
    from app.modules.inventory.schemas import AssetCreate, InboundOrderCreate, OutboundOrderCreate
    from app.modules.inventory.vocabulary import AssetCategory, ExitType, Office
except ModuleNotFoundError as missing:
    print(f"error: missing module {missing.name!r}; run it with the services/api environment", file=sys.stderr)
    sys.exit(2)

SEED = 20261031
# Fecha de referencia fija: las fechas se reparten hacia atrás (y las
# renovaciones, alrededor) desde aquí, no desde la hora de la ejecución.
REFERENCE = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

DEFAULT_INCIDENTS = 5000
DEFAULT_SUPPLIERS = 400
DEFAULT_ASSETS = 120
LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1"}

CONFIG_ERROR_EXIT = 1
UNAVAILABLE_EXIT = 2


class GuardError(Exception):
    """Configuración rechazada por las protecciones (base de la demo o desconocida)."""


# --- Incidencias -------------------------------------------------------------

# Pesos: reparto desigual y verosímil (más fallos técnicos y quejas que «otros»).
CATEGORY_WEIGHTS = {
    IncidentCategory.TECHNICAL_FAILURE: 24,
    IncidentCategory.PROCESS_ERROR: 15,
    IncidentCategory.CLIENT_COMPLAINT: 14,
    IncidentCategory.CANDIDATE_ISSUE: 13,
    IncidentCategory.STAFF_ISSUE: 8,
    IncidentCategory.SLA_BREACH: 10,
    IncidentCategory.DATA_QUALITY: 11,
    IncidentCategory.OTHER: 5,
}
ORIGIN_WEIGHTS = {IncidentOrigin.CUSTOMER: 45, IncidentOrigin.BRANCH: 30, IncidentOrigin.INTERNAL: 25}
BRANCH_WEIGHTS = {Branch.CENTRAL: 35, Branch.VALENCIA_OPERATIONS: 30, Branch.MIAMI_OFFICE: 22, Branch.REMOTE: 13}
# Las antiguas están casi todas cerradas; las recientes, abiertas o en curso.
STATUS_WEIGHTS_BY_AGE = (
    (30, {IncidentStatus.OPEN: 45, IncidentStatus.IN_PROGRESS: 35, IncidentStatus.RESOLVED: 15, IncidentStatus.DISCARDED: 5}),
    (120, {IncidentStatus.OPEN: 12, IncidentStatus.IN_PROGRESS: 23, IncidentStatus.RESOLVED: 55, IncidentStatus.DISCARDED: 10}),
    (None, {IncidentStatus.OPEN: 2, IncidentStatus.IN_PROGRESS: 3, IncidentStatus.RESOLVED: 80, IncidentStatus.DISCARDED: 15}),
)
INCIDENT_SUBJECTS = {
    IncidentCategory.TECHNICAL_FAILURE: ("caída de la VPN", "portátil que no arranca", "error del ATS al guardar", "impresora sin conexión"),
    IncidentCategory.PROCESS_ERROR: ("oferta enviada sin aprobación", "proceso duplicado", "paso de validación omitido"),
    IncidentCategory.CLIENT_COMPLAINT: ("retraso en la terna de candidatos", "informe de cierre incompleto", "cambio de interlocutor no avisado"),
    IncidentCategory.CANDIDATE_ISSUE: ("candidato sin respuesta tras la entrevista", "documentación de candidato pendiente", "reprogramación de entrevista"),
    IncidentCategory.STAFF_ISSUE: ("baja no cubierta en el equipo", "acceso de empleado sin revocar", "turno de soporte sin asignar"),
    IncidentCategory.SLA_BREACH: ("SLA de primera respuesta superado", "SLA de resolución superado"),
    IncidentCategory.DATA_QUALITY: ("registro de candidato duplicado", "email de contacto mal formado", "fecha de alta incoherente"),
    IncidentCategory.OTHER: ("consulta general", "petición sin categoría clara"),
}
INCIDENTS_HORIZON_DAYS = 730


def _weighted(rng: random.Random, weights: dict) -> object:  # type: ignore[type-arg]
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _status_for_age(rng: random.Random, age_days: int) -> IncidentStatus:
    for limit, weights in STATUS_WEIGHTS_BY_AGE:
        if limit is None or age_days <= limit:
            return _weighted(rng, weights)  # type: ignore[return-value]
    raise AssertionError("unreachable")


def build_incidents(count: int) -> list[SeedIncident]:
    rng = random.Random(f"{SEED}:incidents")
    incidents = []
    for number in range(1, count + 1):
        category = _weighted(rng, CATEGORY_WEIGHTS)
        subject = rng.choice(INCIDENT_SUBJECTS[category])  # type: ignore[index]
        # Más densidad reciente: la edad sigue una distribución sesgada hacia 0.
        age_days = min(int(rng.expovariate(1 / 180)), INCIDENTS_HORIZON_DAYS)
        created_at = REFERENCE - timedelta(days=age_days, minutes=rng.randrange(0, 24 * 60))
        draft = validate_incident_fields(
            {
                "title": f"[SINTÉTICO] {subject.capitalize()} #{number:05d}",
                "description": (
                    f"Incidencia sintética {number:05d} generada para pruebas de volumen: {subject}. "
                    "No corresponde a ningún cliente, candidato ni empleado real."
                ),
                "category": category,
                "status": _status_for_age(rng, age_days),
                "origin": _weighted(rng, ORIGIN_WEIGHTS),
                "branch": _weighted(rng, BRANCH_WEIGHTS),
            },
            allowed_statuses=tuple(IncidentStatus),
        )
        key = hashlib.sha256(f"volume_seed:incident:{number}".encode()).hexdigest()
        incidents.append(SeedIncident(row_number=number, source_key=key, draft=draft, created_at=created_at))
    return incidents


# --- Proveedores -------------------------------------------------------------

# Tarifa mensual orientativa por categoría (en la moneda del país), sintética.
RATE_RANGES = {
    SupplierCategory.JOB_BOARDS: (300, 4000),
    SupplierCategory.ATS_SOFTWARE: (500, 6000),
    SupplierCategory.ASSESSMENT_TOOLS: (200, 2500),
    SupplierCategory.TRAINING_PLATFORMS: (150, 3000),
    SupplierCategory.PAYROLL_AND_HR_SOFTWARE: (400, 5000),
    SupplierCategory.VIDEO_INTERVIEW: (100, 1500),
    SupplierCategory.BACKGROUND_CHECK: (250, 3500),
    SupplierCategory.OFFICE_AND_FACILITIES: (80, 2500),
    SupplierCategory.IT_AND_SOFTWARE_LICENSES: (100, 8000),
}
COUNTRY_WEIGHTS = {Country.SPAIN: 60, Country.USA: 40}
SUPPLIER_NOTES = (
    None,
    None,
    "Proveedor sintético para pruebas de volumen.",
    "Revisar condiciones antes de la renovación (dato sintético).",
    "Tarifa negociada en el último ciclo (dato sintético).",
)


def build_suppliers(count: int) -> list[SupplierCreate]:
    rng = random.Random(f"{SEED}:suppliers")
    suppliers = []
    categories = list(SupplierCategory)
    for number in range(1, count + 1):
        country = _weighted(rng, COUNTRY_WEIGHTS)
        chosen = rng.sample(categories, k=rng.choices((1, 2, 3), weights=(60, 30, 10), k=1)[0])
        low, high = RATE_RANGES[chosen[0]]
        renewal: str | None = None
        if rng.random() < 0.8:
            # Entre 3 meses atrás y 18 meses adelante: una parte cae en los 60 días de «renovación próxima».
            renewal = (REFERENCE.date() + timedelta(days=rng.randrange(-90, 540))).isoformat()
        suppliers.append(
            SupplierCreate(
                name=f"Proveedor sintético {number:03d} ({chosen[0].value})",
                country=country,  # type: ignore[arg-type]
                categories=chosen,
                monthly_rate=float(round(rng.uniform(low, high), 2)),
                currency=CURRENCY_BY_COUNTRY[country],  # type: ignore[index]
                status=SupplierStatus.SUSPENDED if rng.random() < 0.15 else SupplierStatus.ACTIVE,
                contract_renewal_date=renewal,
                contact_email=f"contacto-{number:03d}@proveedor-sintetico.example.invalid" if rng.random() < 0.7 else None,
                notes=rng.choice(SUPPLIER_NOTES),
            )
        )
    return suppliers


# --- Inventario --------------------------------------------------------------

ASSET_KINDS = {
    AssetCategory.HARDWARE: ("HW", ("Portátil sintético", "Monitor sintético", "Docking sintético")),
    AssetCategory.PERIPHERALS: ("PER", ("Ratón sintético", "Teclado sintético", "Auriculares sintéticos")),
    AssetCategory.OFFICE_SUPPLIES: ("OFF", ("Resma sintética", "Tóner sintético", "Archivador sintético")),
    AssetCategory.TRAINING_MATERIALS: ("TRN", ("Manual sintético", "Cuaderno sintético")),
}
INVENTORY_SUPPLIERS = {
    Office.VALENCIA: ("Distribuidor sintético Valencia A", "Distribuidor sintético Valencia B"),
    Office.MIAMI: ("Synthetic Distributor Miami A", "Synthetic Distributor Miami B"),
}
INVENTORY_HORIZON_DAYS = 540


@dataclass
class InventoryResult:
    assets_inserted: int = 0
    assets_existing: int = 0
    assets_with_orders: int = 0
    entries_inserted: int = 0
    exits_inserted: int = 0


def build_assets(count: int) -> list[AssetCreate]:
    rng = random.Random(f"{SEED}:assets")
    assets = []
    kinds = list(ASSET_KINDS)
    for number in range(1, count + 1):
        category = kinds[(number - 1) % len(kinds)]
        prefix, names = ASSET_KINDS[category]
        office = Office.VALENCIA if rng.random() < 0.6 else Office.MIAMI
        assets.append(
            AssetCreate(
                name=f"{rng.choice(names)} {number:03d}",
                sku=f"SYN-{prefix}-{number:04d}",
                category=category,
                office=office,
            )
        )
    return assets


def build_orders(
    asset: Asset, rng: random.Random, user_uuid: str
) -> tuple[list[AssetEntry], list[AssetExit]]:
    """Historial cronológico de un activo: entradas y salidas sin dejar nunca el stock en negativo."""
    assert asset.id is not None
    consumable = asset.category in {AssetCategory.OFFICE_SUPPLIES, AssetCategory.TRAINING_MATERIALS}
    events = rng.randrange(80, 400)
    moment = REFERENCE - timedelta(days=INVENTORY_HORIZON_DAYS)
    step = timedelta(days=INVENTORY_HORIZON_DAYS) / events
    stock = 0
    entries: list[AssetEntry] = []
    exits: list[AssetExit] = []
    for _ in range(events):
        moment += step * rng.uniform(0.5, 1.5)
        if stock < 5 or rng.random() < 0.4:
            payload = InboundOrderCreate(
                asset_id=asset.id,
                quantity=rng.randrange(5, 60 if consumable else 20),
                supplier=rng.choice(INVENTORY_SUPPLIERS[asset.office]),
                office=asset.office,
            )
            stock += payload.quantity
            entries.append(AssetEntry(**payload.model_dump(), created_at=moment, user_uuid=user_uuid))
        else:
            exit_type = ExitType.CONSUMPTION if consumable and rng.random() < 0.8 else ExitType.ALLOCATION
            payload_out = OutboundOrderCreate(
                asset_id=asset.id,
                quantity=rng.randrange(1, min(stock, 10) + 1),
                exit_type=exit_type,
                assigned_to=f"EMPLEADO-SINTETICO-{rng.randrange(1, 121):03d}" if exit_type == ExitType.ALLOCATION else None,
                office=asset.office,
            )
            stock -= payload_out.quantity
            exits.append(AssetExit(**payload_out.model_dump(), created_at=moment, user_uuid=user_uuid))
    return entries, exits


def seed_inventory(session: Session, count: int, user_uuid: str) -> InventoryResult:
    """Añade activos y órdenes a la transacción de `session`, sin commit."""
    result = InventoryResult()
    rng = random.Random(f"{SEED}:orders")
    for values in build_assets(count):
        asset = session.exec(select(Asset).where(Asset.sku == values.sku)).first()
        if asset is None:
            asset = Asset(**values.model_dump())
            session.add(asset)
            session.flush()
            result.assets_inserted += 1
        else:
            result.assets_existing += 1
        # El generador avanza igual con o sin órdenes previas: el resultado no
        # depende de qué activos se sembraron antes.
        entries, exits = build_orders(asset, rng, user_uuid)
        assert asset.id is not None
        has_orders = (
            session.exec(select(func.count()).select_from(AssetEntry).where(AssetEntry.asset_id == asset.id)).one()
            + session.exec(select(func.count()).select_from(AssetExit).where(AssetExit.asset_id == asset.id)).one()
        ) > 0
        if has_orders:
            result.assets_with_orders += 1
            continue
        session.add_all(entries)
        session.add_all(exits)
        result.entries_inserted += len(entries)
        result.exits_inserted += len(exits)
    return result


# --- Protecciones y CLI ------------------------------------------------------


def guard_tinydb_path(path: Path, variable: str, explicit: bool) -> None:
    if not explicit:
        raise GuardError(f"{variable} must be set explicitly to a test file")
    resolved = path.resolve()
    if resolved == DEMO_DATA_DIR.resolve() or DEMO_DATA_DIR.resolve() in resolved.parents:
        raise GuardError(f"{variable} points to services/api/data (the demo data); use a test file")


def guard_database_url(database_url: str, allowed_hosts: Sequence[str]) -> None:
    host = make_url(database_url).host or ""
    if host not in LOCAL_DB_HOSTS and host not in allowed_hosts:
        # Sin repetir el host: puede identificar la base de la demo.
        raise GuardError("DATABASE_URL is not a local test database (see --allow-db-host)")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthetic volume seed for test databases (caching ticket, F0).")
    parser.add_argument("targets", nargs="+", choices=("incidents", "suppliers", "inventory"))
    parser.add_argument("--incidents", type=int, default=DEFAULT_INCIDENTS, help="number of incidents")
    parser.add_argument("--suppliers", type=int, default=DEFAULT_SUPPLIERS, help="number of suppliers")
    parser.add_argument("--assets", type=int, default=DEFAULT_ASSETS, help="number of inventory assets")
    parser.add_argument("--email", help="test user (AUTH_DB_PATH) the inventory orders belong to")
    parser.add_argument(
        "--allow-db-host", action="append", default=[], help="extra PostgreSQL host accepted as a test database"
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    targets = set(args.targets)
    try:
        settings = Settings.from_env()
        if "incidents" in targets:
            guard_tinydb_path(settings.incidents_db_path, "INCIDENTS_DB_PATH", bool(os.environ.get("INCIDENTS_DB_PATH")))
        if "suppliers" in targets:
            guard_tinydb_path(settings.suppliers_db_path, "SUPPLIERS_DB_PATH", bool(os.environ.get("SUPPLIERS_DB_PATH")))
        if "inventory" in targets:
            if not args.email:
                raise GuardError("inventory needs --email")
            guard_tinydb_path(settings.auth_db_path, "AUTH_DB_PATH", bool(os.environ.get("AUTH_DB_PATH")))
            settings.require_database()
            guard_database_url(settings.database_url, args.allow_db_host)
    except (ConfigError, GuardError) as error:
        print(f"error: {error}", file=sys.stderr)
        return CONFIG_ERROR_EXIT

    try:
        if "incidents" in targets:
            result = IncidentRepository(settings.incidents_db_path).seed(build_incidents(args.incidents))
            print(f"incidents: inserted {result.inserted}, existing {result.existing}, total {result.total}")
        if "suppliers" in targets:
            fixed_clock = lambda: REFERENCE  # noqa: E731 — `updated_at` determinista
            supplier_result = SupplierRepository(settings.suppliers_db_path, clock=fixed_clock).seed(
                build_suppliers(args.suppliers)
            )
            print(
                f"suppliers: inserted {supplier_result.inserted}, existing {supplier_result.skipped}, "
                f"total {supplier_result.total}"
            )
        if "inventory" in targets:
            user = AuthRepository(settings.auth_db_path).get_user_by_email(normalize_email(args.email))
            if user is None or not user.is_active:
                print("error: no active user with that email in AUTH_DB_PATH", file=sys.stderr)
                return CONFIG_ERROR_EXIT
            engine = build_engine(settings.database_url)
            try:
                init_db(engine)
                with Session(engine) as session:
                    inventory = seed_inventory(session, args.assets, str(user.id))
                    session.commit()
            finally:
                engine.dispose()
            print(
                f"inventory: assets inserted {inventory.assets_inserted}, existing {inventory.assets_existing}; "
                f"entries {inventory.entries_inserted}, exits {inventory.exits_inserted}; "
                f"assets that already had orders {inventory.assets_with_orders}"
            )
    except StorageUnavailableError:
        print("error: a TinyDB test file could not be opened or written", file=sys.stderr)
        return UNAVAILABLE_EXIT
    except (InventoryStartupError, *DATABASE_UNAVAILABLE_ERRORS) as error:
        print(f"error: the inventory database is not available ({type(error).__name__})", file=sys.stderr)
        return UNAVAILABLE_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(run())
