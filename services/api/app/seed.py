"""Seeder del directorio de proveedores: carga `SUPPLIERS_SEED` en TinyDB.

Ejecución (desde `services/api`): `uv run seed`. Equivalente sin uv, con el
venv del servicio: `python -m app.seed`.

- Los datos son exactamente los de docs/ligthweight-storage-api.md
  ("Datos iniciales del seeder").
- Idempotente: antes de insertar comprueba si ya existe un proveedor con el
  mismo `name`; los existentes no se tocan ni se duplican.
- Cada registro pasa por `SupplierCreate` (misma validación que la API).
- Usa la misma base que la API (`SUPPLIERS_DB_PATH` o services/api/data/suppliers.json).
  La API no ejecuta el seeder por sí sola: la carga es siempre explícita.
- Errores de configuración o una base que no se puede abrir, escribir o está
  corrupta: mensaje en stderr y código de salida 1, sin traceback.
"""

import sys
from typing import Any

from app.core.config import ConfigError, Settings
from app.core.errors import StorageUnavailableError
from app.database import SeedResult, SupplierRepository
from app.models import SupplierCreate

SUPPLIERS_SEED: list[dict[str, Any]] = [
    {
        "name": "LinkedIn Talent Solutions",
        "country": "Spain",
        "categories": ["job_boards"],
        "monthly_rate": 1200.0,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2025-03-31",
        "contact_email": "account@linkedin.com",
        "notes": "Licencia corporativa para publicación de ofertas y búsqueda de candidatos.",
    },
    {
        "name": "InfoJobs Premium",
        "country": "Spain",
        "categories": ["job_boards"],
        "monthly_rate": 490.0,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2025-06-30",
        "contact_email": "empresas@infojobs.net",
    },
    {
        "name": "Indeed Sponsored",
        "country": "USA",
        "categories": ["job_boards"],
        "monthly_rate": 850.0,
        "currency": "USD",
        "status": "active",
        "contact_email": "sales@indeed.com",
        "notes": "Campañas de pago por clic para perfiles de customer support en Miami.",
    },
    {
        "name": "Workable",
        "country": "Spain",
        "categories": ["ats_software"],
        "monthly_rate": 299.0,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2025-09-15",
        "contact_email": "support@workable.com",
        "notes": "ATS principal para el equipo de selección de Valencia.",
    },
    {
        "name": "Greenhouse",
        "country": "USA",
        "categories": ["ats_software"],
        "monthly_rate": 620.0,
        "currency": "USD",
        "status": "suspended",
        "contact_email": "accounts@greenhouse.io",
        "notes": "Suspendido tras no renovar. Sergio está evaluando si migrar todo a Workable.",
    },
    {
        "name": "Thomas International",
        "country": "Spain",
        "categories": ["assessment_tools"],
        "monthly_rate": 380.0,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2025-12-01",
        "contact_email": "clientes@thomas.es",
        "notes": "Tests de personalidad y aptitud para procesos de mandos intermedios.",
    },
    {
        "name": "HireVue",
        "country": "USA",
        "categories": ["video_interview"],
        "monthly_rate": 540.0,
        "currency": "USD",
        "status": "active",
        "contract_renewal_date": "2025-08-31",
        "contact_email": "support@hirevue.com",
    },
    {
        "name": "Udemy Business",
        "country": "Spain",
        "categories": ["training_platforms"],
        "monthly_rate": 420.0,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2026-01-15",
        "contact_email": "business@udemy.com",
        "notes": "Licencias para el equipo interno. Gestionado por Elena Vargas.",
    },
    {
        "name": "Coursera for Teams",
        "country": "USA",
        "categories": ["training_platforms"],
        "monthly_rate": 399.0,
        "currency": "USD",
        "status": "suspended",
        "contact_email": "teams@coursera.com",
        "notes": "Suspendido por bajo uso. Revisar antes de Q4.",
    },
    {
        "name": "Sage HR",
        "country": "Spain",
        "categories": ["payroll_and_hr_software"],
        "monthly_rate": 310.0,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2025-10-01",
        "contact_email": "soporte@sage.com",
        "notes": "Software de nóminas y gestión de personal para la sede de Valencia.",
    },
    {
        "name": "Gusto",
        "country": "USA",
        "categories": ["payroll_and_hr_software"],
        "monthly_rate": 280.0,
        "currency": "USD",
        "status": "active",
        "contact_email": "support@gusto.com",
        "notes": "Gestión de nóminas para los empleados de la oficina de Miami.",
    },
    {
        "name": "Checkr",
        "country": "USA",
        "categories": ["background_check"],
        "monthly_rate": 195.0,
        "currency": "USD",
        "status": "active",
        "contract_renewal_date": "2025-11-30",
        "contact_email": "sales@checkr.com",
    },
    {
        "name": "Microsoft 365 Business",
        "country": "Spain",
        "categories": ["it_and_software_licenses"],
        "monthly_rate": 760.0,
        "currency": "EUR",
        "status": "active",
        "contact_email": "enterprise@microsoft.com",
        "notes": "Licencias para toda la plantilla de Valencia y Miami.",
    },
    {
        "name": "Regus Valencia",
        "country": "Spain",
        "categories": ["office_and_facilities"],
        "monthly_rate": 2400.0,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2025-07-01",
        "contact_email": "valencia@regus.com",
        "notes": "Alquiler de la oficina principal en Valencia. Incluye sala de reuniones.",
    },
    {
        "name": "WeWork Miami",
        "country": "USA",
        "categories": ["office_and_facilities"],
        "monthly_rate": 3100.0,
        "currency": "USD",
        "status": "active",
        "contract_renewal_date": "2025-09-30",
        "contact_email": "miami@wework.com",
    },
]


def run_seed(repository: SupplierRepository) -> SeedResult:
    return repository.seed(SupplierCreate.model_validate(record) for record in SUPPLIERS_SEED)


def main() -> None:
    """Punto de entrada de `uv run seed` (`[project.scripts]` en pyproject.toml)."""
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        # Los mensajes de ConfigError son fijos: nombran la variable, nunca su valor.
        print(f"Error de configuración: {error}", file=sys.stderr)
        sys.exit(1)
    try:
        result = run_seed(SupplierRepository(settings.suppliers_db_path))
    except StorageUnavailableError:
        # El repositorio ya registró el almacén y la clase del error; aquí solo
        # el nombre del archivo, nunca la ruta completa ni el mensaje original.
        print(
            f"Error: no se pudo abrir o escribir la base de proveedores ({settings.suppliers_db_path.name}). "
            "Revisa SUPPLIERS_DB_PATH, los permisos y que sea un archivo TinyDB válido.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Base de datos: {settings.suppliers_db_path}")
    print(f"Proveedores insertados: {result.inserted}")
    print(f"Ya existentes (omitidos): {result.skipped}")
    print(f"Total en el directorio: {result.total}")


if __name__ == "__main__":
    main()
