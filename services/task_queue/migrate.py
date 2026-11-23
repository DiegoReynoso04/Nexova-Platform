"""Crea el esquema `ops` (si falta) y la tabla `ops.task_dead_letters` (DEV-55, A9).

Ejecución (desde `services/`, con el entorno de `services/api` o en su imagen):

    python -m task_queue.migrate --dry-run   # imprime la SQL pendiente, no escribe
    python -m task_queue.migrate             # la aplica, en una transacción

- **Nunca al arrancar** nada: ni la API, ni el worker, ni ningún contenedor.
- **Base:** `DATABASE_URL` del entorno o, si falta, solo esa clave del `.env` de la
  raíz (las reglas de `job_runner.config`). Con un host que no es local se niega
  salvo con `--allow-demo`, **que solo se usa con la confirmación del usuario**.
- **Acceso:** RLS sin políticas y `REVOKE ALL` sobre el esquema y sus tablas a
  `PUBLIC` y a los roles de Supabase que existan; antes de confirmar se comprueba
  que ninguno conserva privilegios (si no, se deshace todo). Mismo patrón que
  `job_runner.migrate`: las dos migraciones comparten el esquema `ops` y funcionan
  en cualquier orden (cada una crea el esquema solo si falta y solo su tabla).
- **Idempotente:** la segunda ejecución dice «Nada que migrar».
- Códigos de salida: 0 bien; 1 configuración o rechazo; 2 base no disponible. Los
  mensajes nunca llevan URL, usuario ni contraseña.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from job_runner.config import ConfigError, DatabaseTarget, build_engine, resolve_database_target
from job_runner.migrate import SCHEMA_PRIVILEGES, SUPABASE_ROLES, TABLE_PRIVILEGES, revoke_statements
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import ERROR_MESSAGE_MAX_CHARS
from .dead_letters import FAILED_AT_INDEX, QUALIFIED_TABLE, SCHEMA, TABLE, TASK_ID_UNIQUE

CONFIG_ERROR_EXIT = 1
DATABASE_UNAVAILABLE_EXIT = 2

CREATE_SCHEMA = f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"

CREATE_TABLE = f"""CREATE TABLE IF NOT EXISTS {QUALIFIED_TABLE} (
  id bigserial primary key,
  task_id uuid not null,
  task_name varchar(200) not null,
  attempt integer not null,
  retries integer not null,
  max_retries integer not null,
  reason varchar(32) not null,
  error_class varchar(200) not null,
  error_message text not null,
  task_kwargs jsonb not null default '{{}}'::jsonb,
  queue varchar(100),
  worker varchar(100),
  failed_at timestamptz not null default now(),
  constraint {TASK_ID_UNIQUE} unique (task_id),
  constraint ck_task_dead_letters_attempt_positive check (attempt >= 1),
  constraint ck_task_dead_letters_retries_non_negative check (retries >= 0),
  constraint ck_task_dead_letters_max_retries_non_negative check (max_retries >= 0),
  constraint ck_task_dead_letters_attempt_retries check (attempt = retries + 1),
  constraint ck_task_dead_letters_reason check (reason in ('retries_exhausted', 'non_retryable', 'time_limit')),
  constraint ck_task_dead_letters_message_length check (char_length(error_message) <= {ERROR_MESSAGE_MAX_CHARS})
)"""

CREATE_INDEX = f"CREATE INDEX IF NOT EXISTS {FAILED_AT_INDEX} ON {QUALIFIED_TABLE} (failed_at)"


class StillGrantedError(Exception):
    """Tras el `REVOKE`, algún rol conserva privilegios. Se deshace todo."""


@dataclass(frozen=True, slots=True)
class DatabaseState:
    schema_exists: bool
    table_exists: bool
    index_exists: bool
    rls_enabled: bool
    granted: bool
    supabase_roles: tuple[str, ...]


def _flat(statement: str) -> str:
    return " ".join(statement.split())


def pending_statements(state: DatabaseState) -> list[str]:
    """La SQL que falta, en orden: esquema, tabla, índice, RLS y permisos."""
    statements: list[str] = []
    if not state.schema_exists:
        statements.append(CREATE_SCHEMA)
    if not state.table_exists:
        statements.append(_flat(CREATE_TABLE))
    if not state.index_exists:
        statements.append(CREATE_INDEX)
    if not state.rls_enabled:
        statements.append(f"ALTER TABLE {QUALIFIED_TABLE} ENABLE ROW LEVEL SECURITY")
    # Una tabla nueva en un esquema que ya existía también puede heredar privilegios por defecto.
    if not state.schema_exists or not state.table_exists or state.granted:
        statements.extend(revoke_statements(state.supabase_roles))
    return statements


def _supabase_roles(connection: Connection) -> tuple[str, ...]:
    rows = connection.execute(
        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(CAST(:roles AS text[])) ORDER BY rolname"),
        {"roles": list(SUPABASE_ROLES)},
    ).scalars()
    return tuple(rows)


def _granted(connection: Connection, roles: Sequence[str]) -> bool:
    """¿`PUBLIC` o algún rol de Supabase tiene algún privilegio en el esquema o en esta tabla?"""
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
        return DatabaseState(False, False, False, False, False, roles)
    table_exists = connection.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = :schema AND tablename = :table)"),
        {"schema": SCHEMA, "table": TABLE},
    ).scalar_one()
    index_exists = connection.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = :schema AND indexname = :index)"),
        {"schema": SCHEMA, "index": FAILED_AT_INDEX},
    ).scalar_one()
    rls_enabled = connection.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relname = :table AND c.relkind = 'r' AND c.relrowsecurity)"
        ),
        {"schema": SCHEMA, "table": TABLE},
    ).scalar_one()
    return DatabaseState(True, table_exists, index_exists, rls_enabled, _granted(connection, roles), roles)


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
        prog="python -m task_queue.migrate",
        description="Crea el esquema ops (si falta) y la tabla ops.task_dead_letters (DLQ de la cola) en la base de DATABASE_URL.",
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
            "Error: la base no es local. La migración de ops.task_dead_letters en la demo necesita --allow-demo "
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
        print("Nada que migrar: el esquema ops, ops.task_dead_letters, su índice, RLS y permisos ya están.")
        return 0
    print("SQL pendiente (no se ha aplicado):" if args.dry_run else "Aplicado en una transacción:")
    for statement in statements:
        print(f"  {statement};")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
