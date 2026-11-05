"""Crea `telemetry_events` y la hace inmutable (ticket de almacenamiento, D3 y D4).

Ejecución (desde `services/api`, con el venv del servicio o en el contenedor):

    python -m app.modules.telemetry.migrate --dry-run   # imprime la SQL pendiente, no escribe
    python -m app.modules.telemetry.migrate             # la aplica, en una transacción

**Nunca la ejecuta la API sola**, y sobre la base de la demo solo con la
confirmación del usuario. Arrancar la API con la tabla en `init_db` la crearía
en cuanto el stack cargase este código.

- Tabla e índices: el DDL se compila del modelo, para que no diverjan.
- RLS sin políticas, como el inventario: cierra la Data API de Supabase.
- `REVOKE UPDATE, DELETE, TRUNCATE`: RLS no frena a la API, que conecta como
  dueña y, en Supabase, con `BYPASSRLS`. El permiso sí, salvo a un superusuario:
  por eso con un superusuario la migración se niega. Alcanza también a los
  roles de Supabase que existan, que heredan todos los privilegios de una tabla
  nueva. Antes de confirmar se comprueba que el rol ya no puede escribir.
- Retención (plan §8.3): el trabajo de limpieza es de administración. El dueño
  se concede `DELETE`, borra y lo revoca en una transacción.
- Idempotente: solo emite lo que falta. Reversible con `DROP TABLE`, que el
  dueño conserva. Solo PostgreSQL. Códigos de salida como `inventory/migrate.py`:
  0 bien; 1 configuración; 2 base no disponible. Los mensajes nunca llevan la
  URL, el host ni el usuario de la base.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.config import ConfigError, Settings
from app.modules.inventory.database import build_engine

from .models import TELEMETRY_EVENTS_TABLE, TelemetryEventRecord

POSTGRESQL_BACKEND = "postgresql"
QUALIFIED_TABLE = f"public.{TELEMETRY_EVENTS_TABLE}"
REVOKED_PRIVILEGES = ("UPDATE", "DELETE", "TRUNCATE")
# Roles de la Data API de Supabase. En un PostgreSQL normal no existen.
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

CONFIG_ERROR_EXIT = 1
DATABASE_UNAVAILABLE_EXIT = 2

_TABLE = TelemetryEventRecord.__table__  # type: ignore[attr-defined]


class SuperuserError(Exception):
    """El rol es superusuario: `REVOKE` no le afectaría y la tabla no sería inmutable."""


class StillWritableError(Exception):
    """Tras el `REVOKE`, algún rol conserva un permiso de escritura. Se deshace todo."""


@dataclass(frozen=True, slots=True)
class DatabaseState:
    """Lo que ya existe en la base. `writable_roles`: roles con algún privilegio revocable."""

    table_exists: bool
    indexes: frozenset[str]
    row_level_security: bool
    writable_roles: frozenset[str]
    supabase_roles: tuple[str, ...]


def _sql(statement: object) -> str:
    return " ".join(str(statement).split())


def _compiled(element: CreateTable | CreateIndex) -> str:
    return _sql(element.compile(dialect=postgresql.dialect()))


def revoke_statement(supabase_roles: Sequence[str]) -> str:
    grantees = ", ".join(("PUBLIC", "CURRENT_USER", *supabase_roles))
    return f"REVOKE {', '.join(REVOKED_PRIVILEGES)} ON {TELEMETRY_EVENTS_TABLE} FROM {grantees}"


def pending_statements(state: DatabaseState) -> list[str]:
    """La SQL que falta, dado lo que ya existe, en orden: tabla, índices, RLS y permisos."""
    statements: list[str] = []
    if not state.table_exists:
        statements.append(_compiled(CreateTable(_TABLE, if_not_exists=True)))
    for index in sorted(_TABLE.indexes, key=lambda item: item.name):
        if index.name not in state.indexes:
            statements.append(_compiled(CreateIndex(index, if_not_exists=True)))
    if not state.row_level_security:
        statements.append(f"ALTER TABLE {TELEMETRY_EVENTS_TABLE} ENABLE ROW LEVEL SECURITY")
    if not state.table_exists or state.writable_roles:
        statements.append(revoke_statement(state.supabase_roles))
    return statements


def _writable_roles(connection: Connection, roles: Sequence[str]) -> frozenset[str]:
    rows = connection.execute(
        text(
            "SELECT DISTINCT role FROM unnest(CAST(:roles AS text[])) AS role, unnest(CAST(:privileges AS text[])) AS privilege "
            "WHERE has_table_privilege(role, :table, privilege)"
        ),
        {"roles": list(roles), "privileges": list(REVOKED_PRIVILEGES), "table": QUALIFIED_TABLE},
    ).scalars()
    return frozenset(rows)


def _roles(connection: Connection) -> tuple[str, tuple[str, ...]]:
    """El rol de la conexión y los de Supabase que existen. Lanza `SuperuserError` si es superusuario."""
    user, superuser = connection.execute(
        text("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user")
    ).one()
    if superuser:
        raise SuperuserError()
    supabase_roles = connection.execute(
        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(CAST(:roles AS text[])) ORDER BY rolname"),
        {"roles": list(SUPABASE_ROLES)},
    ).scalars()
    return user, tuple(supabase_roles)


def _existing(engine: Engine) -> DatabaseState:
    with engine.connect() as connection:
        user, supabase_roles = _roles(connection)
        exists = connection.execute(text("SELECT to_regclass(:table) IS NOT NULL"), {"table": QUALIFIED_TABLE}).scalar_one()
        if not exists:
            return DatabaseState(False, frozenset(), False, frozenset(), supabase_roles)
        indexes = connection.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :table"),
            {"table": TELEMETRY_EVENTS_TABLE},
        ).scalars()
        row_level_security = connection.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:table)"), {"table": QUALIFIED_TABLE}
        ).scalar_one()
        return DatabaseState(
            True, frozenset(indexes), row_level_security, _writable_roles(connection, (user, *supabase_roles)), supabase_roles
        )


def migrate(engine: Engine, *, dry_run: bool) -> list[str]:
    """Aplica (o, con `dry_run`, solo devuelve) la SQL pendiente, en una sola transacción."""
    state = _existing(engine)
    statements = pending_statements(state)
    if statements and not dry_run:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
            user, supabase_roles = _roles(connection)
            if _writable_roles(connection, (user, *supabase_roles)):
                raise StillWritableError()
    return statements


def run(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-telemetry", description="Crea telemetry_events, inmutable, en la base de DATABASE_URL."
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

    refusal: str | None = None
    failure: str | None = None
    statements: list[str] = []
    try:
        statements = migrate(engine, dry_run=args.dry_run)
    except SuperuserError:
        refusal = "el rol de la conexión es superusuario y REVOKE no le afecta: usa un rol sin superusuario."
    except StillWritableError:
        refusal = "tras el REVOKE, un rol conserva permisos de escritura. Se ha deshecho todo."
    except SQLAlchemyError as error:
        failure = type(error).__name__
    finally:
        engine.dispose()
    if refusal is not None:
        print(f"Error: {refusal}", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    if failure is not None:
        print(f"Error: la base de datos no está disponible o rechazó la operación ({failure}). No se ha cambiado nada.", file=sys.stderr)
        return DATABASE_UNAVAILABLE_EXIT

    if not statements:
        print("Nada que migrar: la tabla, sus índices, RLS y los permisos ya están.")
        return 0
    print("SQL pendiente (no se ha aplicado):" if args.dry_run else "Aplicado en una transacción:")
    for statement in statements:
        print(f"  {statement};")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
