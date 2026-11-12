"""Crea el esquema `reporting` del pipeline de desempeño de negocio (D11 del análisis).

Ejecución (desde `data/pipelines`, con su venv):

    python -m business_performance.migrate --dry-run   # imprime la SQL pendiente, no escribe
    python -m business_performance.migrate             # la aplica, en una transacción

- **Guarda (D5):** con un host que no es local (`localhost`, `127.0.0.1`, `::1`)
  se niega salvo con `--allow-demo`, que solo se usa con la confirmación del
  usuario. Es DDL: la corrida del ETL no tiene esta guarda.
- **Nunca al arrancar** nada: ni el pipeline ni la API la ejecutan solos.
- **DDL:** la tabla del BRIEFING intacta + `run_id` y `CHECK` aditivos, y
  `pipeline_runs` (§2.7 y §3.3 del diseño). `gen_random_uuid()` es nativa en
  PostgreSQL >= 13.
- **Acceso:** RLS sin políticas en las dos tablas (cierra la Data API de
  Supabase) y `REVOKE ALL` sobre el esquema y las tablas a `PUBLIC` y a los
  roles de Supabase que existan (`anon`, `authenticated`, `service_role`), que
  en Supabase reciben privilegios por defecto en cada tabla nueva. Antes de
  confirmar se comprueba que ninguno conserva privilegios.
- **Idempotente:** solo emite lo que falta; la segunda ejecución dice «Nada que migrar».
- Códigos de salida como `services/api/app/modules/telemetry/migrate.py`: 0 bien;
  1 configuración o rechazo; 2 base no disponible. Los mensajes nunca llevan la
  URL, el usuario ni la contraseña: solo de dónde salió la URL y el host.
"""

from __future__ import annotations

from . import _bootstrap  # noqa: F401  (rutas de packages/shared y data/process)

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from nexova_shared.reporting import QUALIFIED_RUNS_TABLE, QUALIFIED_WEEKLY_TABLE, RUNS_TABLE, SCHEMA, WEEKLY_TABLE
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import ConfigError, DatabaseTarget, resolve_database_target
from .repository import ONE_RUNNING_INDEX, build_engine

CONFIG_ERROR_EXIT = 1
DATABASE_UNAVAILABLE_EXIT = 2

SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLES = (QUALIFIED_RUNS_TABLE, QUALIFIED_WEEKLY_TABLE)
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
SCHEMA_PRIVILEGES = ("USAGE", "CREATE")
LATEST_INDEX = "ix_pipeline_runs_latest"

CREATE_SCHEMA = f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"

# §3.3: va antes, porque la FK aditiva de la tabla del reporte apunta a ella.
CREATE_RUNS_TABLE = f"""CREATE TABLE IF NOT EXISTS {QUALIFIED_RUNS_TABLE} (
  run_id uuid primary key default gen_random_uuid(),
  pipeline_name text not null,
  trigger text not null check (trigger in ('schedule', 'manual', 'backfill')),
  requested_by uuid,
  prefect_flow_run_id uuid,
  status text not null check (status in ('running', 'completed', 'failed')),
  phase text not null check (phase in ('extract', 'transform', 'load', 'done')),
  week_from date not null,
  week_to date not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  source_rows_read integer not null default 0,
  rows_rejected integer not null default 0,
  duplicates_collapsed integer not null default 0,
  rows_upserted integer not null default 0,
  rows_deleted integer not null default 0,
  quality jsonb not null default '{{}}',
  error_class text,
  schema_version text not null,
  check (week_from <= week_to)
)"""

# §2.7: la DDL del BRIEFING sin cambios, más lo marcado como ADITIVO.
CREATE_WEEKLY_TABLE = f"""CREATE TABLE IF NOT EXISTS {QUALIFIED_WEEKLY_TABLE} (
  id uuid primary key default gen_random_uuid(),
  office text not null,
  programme_id text not null,
  week_start date not null,
  total_material_cost numeric not null default 0,
  kits_delivered_count integer not null default 0,
  shortage_events_count integer not null default 0,
  cost_variance_events_count integer not null default 0,
  currency text not null,
  computed_at timestamptz not null default now(),
  unique (office, programme_id, week_start),
  run_id uuid not null references {QUALIFIED_RUNS_TABLE} (run_id),
  constraint ck_wopp_office check (office in ('valencia', 'miami')),
  constraint ck_wopp_currency check (
    (office = 'valencia' and currency = 'EUR') or (office = 'miami' and currency = 'USD')),
  constraint ck_wopp_programme check (
    programme_id = '_unassigned' or programme_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  constraint ck_wopp_week_start_monday check (extract(isodow from week_start) = 1),
  constraint ck_wopp_non_negative check (
    total_material_cost >= 0 and kits_delivered_count >= 0
    and shortage_events_count >= 0 and cost_variance_events_count >= 0)
)"""

# Una sola corrida activa por pipeline; y la última, rápida.
INDEXES = {
    ONE_RUNNING_INDEX: (
        f"CREATE UNIQUE INDEX IF NOT EXISTS {ONE_RUNNING_INDEX} ON {QUALIFIED_RUNS_TABLE} (pipeline_name) "
        "WHERE status = 'running'"
    ),
    LATEST_INDEX: (
        f"CREATE INDEX IF NOT EXISTS {LATEST_INDEX} ON {QUALIFIED_RUNS_TABLE} (pipeline_name, started_at DESC)"
    ),
}


class StillGrantedError(Exception):
    """Tras el `REVOKE`, algún rol conserva privilegios. Se deshace todo."""


@dataclass(frozen=True, slots=True)
class DatabaseState:
    schema_exists: bool
    tables: frozenset[str]
    indexes: frozenset[str]
    rls_tables: frozenset[str]
    granted: bool
    supabase_roles: tuple[str, ...]


def _flat(statement: str) -> str:
    return " ".join(statement.split())


def revoke_statements(supabase_roles: Sequence[str]) -> list[str]:
    grantees = ", ".join(("PUBLIC", *supabase_roles))
    return [
        f"REVOKE ALL ON SCHEMA {SCHEMA} FROM {grantees}",
        f"REVOKE ALL ON ALL TABLES IN SCHEMA {SCHEMA} FROM {grantees}",
    ]


def pending_statements(state: DatabaseState) -> list[str]:
    """La SQL que falta, en orden: esquema, tablas, índices, RLS y permisos."""
    statements: list[str] = []
    if not state.schema_exists:
        statements.append(CREATE_SCHEMA)
    if RUNS_TABLE not in state.tables:
        statements.append(_flat(CREATE_RUNS_TABLE))
    if WEEKLY_TABLE not in state.tables:
        statements.append(_flat(CREATE_WEEKLY_TABLE))
    for name, statement in INDEXES.items():
        if name not in state.indexes:
            statements.append(statement)
    for table in (RUNS_TABLE, WEEKLY_TABLE):
        if table not in state.rls_tables:
            statements.append(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
    if not state.schema_exists or state.granted:
        statements.extend(revoke_statements(state.supabase_roles))
    return statements


def _supabase_roles(connection: Connection) -> tuple[str, ...]:
    rows = connection.execute(
        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(CAST(:roles AS text[])) ORDER BY rolname"),
        {"roles": list(SUPABASE_ROLES)},
    ).scalars()
    return tuple(rows)


def _granted(connection: Connection, roles: Sequence[str]) -> bool:
    """¿`PUBLIC` o algún rol de Supabase tiene algún privilegio en el esquema o en sus tablas?"""
    public = connection.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace n, aclexplode(n.nspacl) a WHERE n.nspname = :schema AND a.grantee = 0) "
            "OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a "
            "WHERE n.nspname = :schema AND a.grantee = 0)"
        ),
        {"schema": SCHEMA},
    ).scalar_one()
    if public:
        return True
    for role in roles:
        for privilege in SCHEMA_PRIVILEGES:
            if connection.execute(
                text("SELECT has_schema_privilege(:role, :schema, :privilege)"),
                {"role": role, "schema": SCHEMA, "privilege": privilege},
            ).scalar_one():
                return True
        for table in TABLES:
            exists = connection.execute(text("SELECT to_regclass(:table) IS NOT NULL"), {"table": table}).scalar_one()
            if not exists:
                continue
            for privilege in TABLE_PRIVILEGES:
                if connection.execute(
                    text("SELECT has_table_privilege(:role, :table, :privilege)"),
                    {"role": role, "table": table, "privilege": privilege},
                ).scalar_one():
                    return True
    return False


def _existing(connection: Connection) -> DatabaseState:
    roles = _supabase_roles(connection)
    schema_exists = connection.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"), {"schema": SCHEMA}
    ).scalar_one()
    if not schema_exists:
        return DatabaseState(False, frozenset(), frozenset(), frozenset(), False, roles)
    tables = connection.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"), {"schema": SCHEMA}
    ).scalars()
    indexes = connection.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname = :schema"), {"schema": SCHEMA}
    ).scalars()
    rls = connection.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relkind = 'r' AND c.relrowsecurity"
        ),
        {"schema": SCHEMA},
    ).scalars()
    return DatabaseState(True, frozenset(tables), frozenset(indexes), frozenset(rls), _granted(connection, roles), roles)


def migrate(engine: Engine, *, dry_run: bool) -> list[str]:
    """Aplica (o, con `dry_run`, solo devuelve) la SQL pendiente, en una sola transacción."""
    with engine.connect() as connection:
        statements = pending_statements(_existing(connection))
    if statements and not dry_run:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
            if _granted(connection, _supabase_roles(connection)):
                raise StillGrantedError()
    return statements


def run(argv: Sequence[str] | None = None, target: DatabaseTarget | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m business_performance.migrate",
        description="Crea el esquema reporting (pipeline de desempeño de negocio) en la base de DATABASE_URL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime la SQL pendiente; no escribe nada")
    parser.add_argument(
        "--allow-demo",
        action="store_true",
        help="Permite una base que no es local (la demo). Solo con la confirmación del usuario",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return CONFIG_ERROR_EXIT if exit_request.code else 0

    try:
        target = target if target is not None else resolve_database_target()
    except ConfigError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    print(target.describe())
    if not target.is_local and not args.allow_demo:
        print(
            "Error: la base no es local. La migración del esquema reporting en la demo necesita --allow-demo "
            "(y la confirmación del usuario).",
            file=sys.stderr,
        )
        return CONFIG_ERROR_EXIT

    engine = build_engine(target.url)
    refusal: str | None = None
    failure: str | None = None
    statements: list[str] = []
    try:
        statements = migrate(engine, dry_run=args.dry_run)
    except StillGrantedError:
        refusal = "tras el REVOKE, un rol conserva privilegios en reporting. Se ha deshecho todo."
    except SQLAlchemyError as error:
        failure = type(error).__name__
    finally:
        engine.dispose()
    if refusal is not None:
        print(f"Error: {refusal}", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    if failure is not None:
        print(
            f"Error: la base de datos no está disponible o rechazó la operación ({failure}). No se ha cambiado nada.",
            file=sys.stderr,
        )
        return DATABASE_UNAVAILABLE_EXIT

    if not statements:
        print("Nada que migrar: el esquema reporting, sus tablas, índices, RLS y permisos ya están.")
        return 0
    print("SQL pendiente (no se ha aplicado):" if args.dry_run else "Aplicado en una transacción:")
    for statement in statements:
        print(f"  {statement};")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
