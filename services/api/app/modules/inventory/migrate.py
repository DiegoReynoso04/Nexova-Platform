"""Migración P3 del plan de telemetría: coste y moneda de las entradas (`asset_entries`).

Ejecución (desde `services/api`, con el venv del servicio o en el contenedor):

    python -m app.modules.inventory.migrate --dry-run   # imprime la SQL pendiente, no escribe
    python -m app.modules.inventory.migrate             # la aplica, en una transacción

`create_all` (al arrancar la API) crea las columnas en una base nueva, pero no
altera tablas existentes: una base ya creada (como la de la demo) necesita esta
migración. **Nunca la ejecuta la API sola**, y sobre la base de la demo solo con
la confirmación del usuario.

- Solo P3: `unit_cost NUMERIC(12,2)` y `currency VARCHAR(3)`, nullable, con sus
  `CHECK` (`unit_cost > 0`; `currency` en `EUR`/`USD`). Nada más.
- Aditiva y sin pérdida: las filas existentes quedan con `NULL`, que los `CHECK`
  aceptan; no se rellena ningún valor. Reversible con `DROP CONSTRAINT` y
  `DROP COLUMN` (solo se pierde lo escrito después en esas columnas).
- Idempotente: mira `information_schema.columns` y `pg_constraint` y solo emite
  lo que falta (`ADD CONSTRAINT` no admite `IF NOT EXISTS`). Una segunda
  ejecución no hace nada.
- Solo PostgreSQL. Códigos de salida como el seed: 0 bien; 1 configuración (sin
  `DATABASE_URL`, otra base o la tabla aún no existe); 2 base no disponible. Los
  mensajes nunca llevan la URL, el host ni el usuario de la base.
"""

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy import Engine, text

from app.core.config import ConfigError, Settings
from app.core.errors import DATABASE_UNAVAILABLE_ERRORS

from .database import build_engine
from .models import CURRENCY_CHECK, UNIT_COST_CHECK

TABLE = "asset_entries"
POSTGRESQL_BACKEND = "postgresql"

# (nombre, SQL) en orden: primero las columnas, después sus `CHECK`.
COLUMNS = (
    ("unit_cost", f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(12, 2) NULL"),
    ("currency", f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NULL"),
)
CONSTRAINTS = (
    (UNIT_COST_CHECK, f"ALTER TABLE {TABLE} ADD CONSTRAINT {UNIT_COST_CHECK} CHECK (unit_cost > 0)"),
    (CURRENCY_CHECK, f"ALTER TABLE {TABLE} ADD CONSTRAINT {CURRENCY_CHECK} CHECK (currency IN ('EUR', 'USD'))"),
)

CONFIG_ERROR_EXIT = 1
DATABASE_UNAVAILABLE_EXIT = 2


class MissingTableError(Exception):
    """`asset_entries` no existe: la API no ha arrancado nunca contra esta base."""


def pending_statements(columns: set[str], constraints: set[str]) -> list[str]:
    """La SQL que falta, dado lo que ya existe en la tabla."""
    return [sql for name, sql in COLUMNS if name not in columns] + [
        sql for name, sql in CONSTRAINTS if name not in constraints
    ]


def _existing(engine: Engine) -> tuple[set[str], set[str]]:
    with engine.connect() as connection:
        exists = connection.execute(text("SELECT to_regclass(:table) IS NOT NULL"), {"table": f"public.{TABLE}"}).scalar_one()
        if not exists:
            raise MissingTableError()
        columns = connection.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table"),
            {"table": TABLE},
        ).scalars()
        constraints = connection.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = to_regclass(:table)"), {"table": f"public.{TABLE}"}
        ).scalars()
        return set(columns), set(constraints)


def migrate(engine: Engine, *, dry_run: bool) -> list[str]:
    """Aplica (o, con `dry_run`, solo devuelve) la SQL pendiente, en una sola transacción."""
    columns, constraints = _existing(engine)
    statements = pending_statements(columns, constraints)
    if statements and not dry_run:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
    return statements


def run(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-inventory", description="Migración P3 (coste y moneda de las entradas) en la base de DATABASE_URL."
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime la SQL pendiente; no escribe nada")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return CONFIG_ERROR_EXIT if exit_request.code else 0

    try:
        settings = settings if settings is not None else Settings.from_env()
        settings.require_database()
        engine = build_engine(settings.database_url)
    except ConfigError as error:
        # Los mensajes de ConfigError nombran la variable, nunca su valor.
        print(f"Error de configuración: {error}", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    if engine.dialect.name != POSTGRESQL_BACKEND:
        engine.dispose()
        print("Error de configuración: la migración solo se aplica a PostgreSQL.", file=sys.stderr)
        return CONFIG_ERROR_EXIT

    failure: str | None = None
    missing_table = False
    statements: list[str] = []
    try:
        statements = migrate(engine, dry_run=args.dry_run)
    except MissingTableError:
        missing_table = True
    except DATABASE_UNAVAILABLE_ERRORS as error:
        failure = type(error).__name__
    finally:
        engine.dispose()
    if missing_table:
        print(f"Error: la tabla {TABLE} no existe. Arranca la API una vez contra esta base y repite.", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    if failure is not None:
        print(f"Error: la base de datos del inventario no está disponible ({failure}). No se ha cambiado nada.", file=sys.stderr)
        return DATABASE_UNAVAILABLE_EXIT

    if not statements:
        print("Nada que migrar: las columnas y los CHECK de P3 ya existen.")
        return 0
    print("SQL pendiente (no se ha aplicado):" if args.dry_run else "Aplicado en una transacción:")
    for statement in statements:
        print(f"  {statement};")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
