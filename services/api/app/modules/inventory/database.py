"""Conexión SQLModel del inventario: motor, tablas + RLS al arrancar y una sesión por petición.

Dos bases a propósito: los usuarios siguen en TinyDB (`get_current_user`, que no
se mueve de app/auth/) y los activos y las órdenes van a la base PostgreSQL de
Supabase (`DATABASE_URL`).

- `build_engine`: un motor por app, creado en `create_app` y guardado en
  `app.state.inventory_engine` (sin conectar todavía). No hay motor ni sesión a
  nivel de módulo.
- `inventory_lifespan`: al arrancar, `create_all` y RLS en las tres tablas. Si
  falla, lanza `InventoryStartupError`, que solo lleva la clase del error.
- `get_db`: dependencia de FastAPI; abre una `Session` por petición y la cierra
  al terminar.

Supabase se usa a través del Transaction pooler (puerto 6543): el pooler ya
reparte las conexiones, así que el motor no guarda ninguna (`NullPool`).
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import NullPool, StaticPool
from sqlmodel import Session, SQLModel
from starlette.concurrency import run_in_threadpool

from app.core.config import ConfigError

from .models import INVENTORY_TABLES

# SQLAlchemy 2.1 resuelve `postgresql://` con psycopg (v3), que no está
# instalado: el driver autorizado por el enunciado es psycopg2.
POSTGRES_BACKEND = "postgresql"
POSTGRES_DRIVER = "postgresql+psycopg2"
SQLITE_BACKEND = "sqlite"
# Segundos para abrir la conexión: con Supabase caído la petición responde 503
# en vez de quedarse colgada.
CONNECT_TIMEOUT_SECONDS = 5


class InventoryStartupError(RuntimeError):
    """La base del inventario falló al arrancar (conexión, `create_all` o RLS).

    Solo lleva el nombre de la clase del error original: su mensaje incluye el
    host, el usuario y a veces la SQL, y uvicorn imprime la traza de lo que
    falla en el lifespan. Se lanza fuera del `except`, sin `__cause__` ni
    `__context__` (mismo patrón que `GuardedJSONStorage`, hallazgo A2).
    """

    def __init__(self, error_class: str) -> None:
        super().__init__(f"inventory database is unavailable at startup: {error_class}")
        self.error_class = error_class


def build_engine(database_url: str) -> Engine:
    """Motor del inventario. No conecta: la primera conexión la abre el lifespan.

    - PostgreSQL (Supabase): `NullPool`, `connect_timeout` y driver psycopg2.
    - SQLite (solo tests, inyectado en `Settings`): una única conexión en
      memoria compartida entre hilos (`StaticPool`) y claves foráneas activadas,
      que SQLite ignora por defecto.

    `hide_parameters`: los errores de SQLAlchemy no incluyen los valores de la consulta.
    """
    invalid = False
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        # El mensaje de SQLAlchemy repite la URL (con la contraseña).
        invalid = True
    if invalid:
        raise ConfigError("DATABASE_URL is not a valid database URL (see services/api/.env.example)")
    if url.get_backend_name() == SQLITE_BACKEND:
        engine = create_engine(
            url, poolclass=StaticPool, connect_args={"check_same_thread": False}, hide_parameters=True
        )
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        return engine
    if url.drivername == POSTGRES_BACKEND:
        url = url.set(drivername=POSTGRES_DRIVER)
    return create_engine(
        url,
        poolclass=NullPool,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
        hide_parameters=True,
    )


def _enable_sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db(engine: Engine) -> None:
    """Crea las tablas que falten y activa RLS, en una sola transacción. Idempotente.

    Cualquier fallo se convierte en `InventoryStartupError` (solo la clase).
    """
    failure: str | None = None
    try:
        with engine.begin() as connection:
            SQLModel.metadata.create_all(connection, tables=list(INVENTORY_TABLES))
            enable_row_level_security(connection)
    except Exception as exc:  # noqa: BLE001 — frontera del arranque: solo se conserva la clase
        failure = type(exc).__name__
    if failure is not None:
        raise InventoryStartupError(failure)


def enable_row_level_security(connection: Connection) -> None:
    """RLS sin políticas en las tres tablas (solo PostgreSQL).

    Así la Data API pública de Supabase (roles `anon` y `authenticated`) no
    puede leerlas ni escribirlas. La API conecta como el dueño de las tablas,
    al que RLS no se aplica (no se usa `FORCE`). `ENABLE` es idempotente: se
    repite en cada arranque y también cubre tablas creadas antes.
    """
    if connection.dialect.name != POSTGRES_BACKEND:
        return
    quote = connection.dialect.identifier_preparer.quote
    for table in INVENTORY_TABLES:
        connection.execute(text(f"ALTER TABLE {quote(table.name)} ENABLE ROW LEVEL SECURITY"))


@asynccontextmanager
async def inventory_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Arranque de la app: tablas y RLS en la base del inventario antes de aceptar peticiones.

    Si falla, `InventoryStartupError` hace que uvicorn no arranque.
    """
    engine = app.state.inventory_engine
    assert isinstance(engine, Engine)
    await run_in_threadpool(init_db, engine)
    yield


def get_db(request: Request) -> Iterator[Session]:
    """Una `Session` nueva por petición, cerrada al terminar (también si la ruta falla)."""
    engine = request.app.state.inventory_engine
    assert isinstance(engine, Engine)
    with Session(engine) as session:
        yield session
