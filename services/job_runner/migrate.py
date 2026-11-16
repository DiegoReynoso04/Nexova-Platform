"""Crea el esquema `ops` y la tabla `ops.job_runs` (DEV-53, apartado B.1 del análisis).

Ejecución (desde `services/`, con el entorno de `data/pipelines` o el de la API):

    python -m job_runner.migrate --dry-run   # imprime la SQL pendiente, no escribe
    python -m job_runner.migrate             # la aplica, en una transacción

- **Nunca al arrancar** nada: ni el script nocturno, ni la API, ni el contenedor.
- **Guarda:** con un host que no es local (`localhost`, `127.0.0.1`, `::1`) se
  niega salvo con `--allow-demo`, que solo se usa con la confirmación del usuario.
- **Acceso:** RLS sin políticas (cierra la Data API de Supabase) y `REVOKE ALL`
  sobre el esquema y la tabla a `PUBLIC` y a los roles de Supabase que existan.
  Antes de confirmar se comprueba que ninguno conserva privilegios; si no, se
  deshace todo. El esquema `ops` no se añade a los expuestos de la Data API.
- **Idempotente:** solo emite lo que falta; la segunda ejecución dice «Nada que migrar».
- Patrón de `data/pipelines/business_performance/migrate.py` (copiado, para que
  `services/` no dependa de `data/`). Códigos de salida: 0 bien; 1 configuración o
  rechazo; 2 base no disponible. Los mensajes nunca llevan URL, usuario ni contraseña.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import ConfigError, DatabaseTarget, build_engine, resolve_database_target
from .states import (
    DATABASE_MESSAGE_LIMIT,
    ONE_COMPLETED_INDEX,
    ONE_PROCESSING_INDEX,
    QUALIFIED_TABLE,
    SCHEMA,
    TABLE,
    TARGET_INDEX,
    JobStatus,
)

CONFIG_ERROR_EXIT = 1
DATABASE_UNAVAILABLE_EXIT = 2

SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
SCHEMA_PRIVILEGES = ("USAGE", "CREATE")

CREATE_SCHEMA = f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"

CREATE_TABLE = f"""CREATE TABLE IF NOT EXISTS {QUALIFIED_TABLE} (
  id uuid primary key default gen_random_uuid(),
  job_name text not null,
  target_date date not null,
  status text not null check (status in ('pending', 'processing', 'completed', 'failed')),
  started_at timestamptz,
  finished_at timestamptz,
  error_message text,
  created_at timestamptz not null default now(),
  constraint ck_job_runs_finished check ((status in ('completed', 'failed')) = (finished_at is not null)),
  constraint ck_job_runs_error check (error_message is null or status = 'failed'),
  constraint ck_job_runs_message_length check (char_length(error_message) <= {DATABASE_MESSAGE_LIMIT})
)"""


def index_statements(table: str = QUALIFIED_TABLE) -> dict[str, str]:
    """Los tres índices, con la misma sintaxis en PostgreSQL y SQLite (los tests unitarios la reutilizan)."""
    return {
        # El del enunciado: consultas de idempotencia por (job, día).
        TARGET_INDEX: f"CREATE INDEX IF NOT EXISTS {TARGET_INDEX} ON {table} (job_name, target_date)",
        # El lock: a lo sumo una fila `processing` por job. `status` es el lock.
        ONE_PROCESSING_INDEX: (
            f"CREATE UNIQUE INDEX IF NOT EXISTS {ONE_PROCESSING_INDEX} ON {table} (job_name) "
            f"WHERE status = '{JobStatus.PROCESSING}'"
        ),
        # La idempotencia como garantía de base de datos: a lo sumo un `completed` por job y día.
        ONE_COMPLETED_INDEX: (
            f"CREATE UNIQUE INDEX IF NOT EXISTS {ONE_COMPLETED_INDEX} ON {table} (job_name, target_date) "
            f"WHERE status = '{JobStatus.COMPLETED}'"
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
    """La SQL que falta, en orden: esquema, tabla, índices, RLS y permisos."""
    statements: list[str] = []
    if not state.schema_exists:
        statements.append(CREATE_SCHEMA)
    table_missing = TABLE not in state.tables
    if table_missing:
        statements.append(_flat(CREATE_TABLE))
    for name, statement in index_statements().items():
        if name not in state.indexes:
            statements.append(statement)
    if TABLE not in state.rls_tables:
        statements.append(f"ALTER TABLE {QUALIFIED_TABLE} ENABLE ROW LEVEL SECURITY")
    # Una tabla nueva en un esquema que ya existía también puede heredar privilegios por defecto.
    if not state.schema_exists or table_missing or state.granted:
        statements.extend(revoke_statements(state.supabase_roles))
    return statements


def _supabase_roles(connection: Connection) -> tuple[str, ...]:
    rows = connection.execute(
        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(CAST(:roles AS text[])) ORDER BY rolname"),
        {"roles": list(SUPABASE_ROLES)},
    ).scalars()
    return tuple(rows)


def _granted(connection: Connection, roles: Sequence[str]) -> bool:
    """¿`PUBLIC` o algún rol de Supabase tiene algún privilegio en el esquema o en su tabla?"""
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
    table_exists = connection.execute(text("SELECT to_regclass(:table) IS NOT NULL"), {"table": QUALIFIED_TABLE}).scalar_one()
    for role in roles:
        for privilege in SCHEMA_PRIVILEGES:
            if connection.execute(
                text("SELECT has_schema_privilege(:role, :schema, :privilege)"),
                {"role": role, "schema": SCHEMA, "privilege": privilege},
            ).scalar_one():
                return True
        if not table_exists:
            continue
        for privilege in TABLE_PRIVILEGES:
            if connection.execute(
                text("SELECT has_table_privilege(:role, :table, :privilege)"),
                {"role": role, "table": QUALIFIED_TABLE, "privilege": privilege},
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
    tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"), {"schema": SCHEMA}).scalars()
    indexes = connection.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = :schema"), {"schema": SCHEMA}).scalars()
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
        prog="python -m job_runner.migrate",
        description="Crea el esquema ops y la tabla ops.job_runs (job nocturno de telemetría) en la base de DATABASE_URL.",
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
            "Error: la base no es local. La migración del esquema ops en la demo necesita --allow-demo "
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
        refusal = "tras el REVOKE, un rol conserva privilegios en ops. Se ha deshecho todo."
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
        print("Nada que migrar: el esquema ops, su tabla, índices, RLS y permisos ya están.")
        return 0
    print("SQL pendiente (no se ha aplicado):" if args.dry_run else "Aplicado en una transacción:")
    for statement in statements:
        print(f"  {statement};")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
