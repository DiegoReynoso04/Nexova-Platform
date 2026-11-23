"""La base del worker: `DATABASE_URL` solo del entorno y un motor por proceso.

El worker no lee el `.env` (en Compose no lo tiene; su lista blanca le pasa
`DATABASE_URL`). Las reglas de la URL (esquemas, host, nunca repetirla) son las de
`job_runner.config`. `NullPool`, como `job_runner` y la API: con el Transaction
pooler de Supabase cada transacción puede ir por otra conexión.

Cada transacción fija su `statement_timeout` con `SET LOCAL`, que el pooler de
Supabase respeta (la opción `-c statement_timeout` de la conexión, no siempre).
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from job_runner.config import DATABASE_URL_VARIABLE, ConfigError, DatabaseTarget, target_from_url
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.pool import NullPool

from .config import DATABASE_CONNECT_TIMEOUT_SECONDS

__all__ = ["ConfigError", "get_engine", "reset_engine", "transaction", "worker_database_target"]

_engine: Engine | None = None
_engine_pid: int | None = None


def worker_database_target(environ: Mapping[str, str] | None = None) -> DatabaseTarget:
    environ = os.environ if environ is None else environ
    value = (environ.get(DATABASE_URL_VARIABLE) or "").strip()
    if not value:
        raise ConfigError(f"{DATABASE_URL_VARIABLE} is not set in the worker environment")
    return target_from_url(value, "entorno")


def build_engine(url: str) -> Engine:
    return create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS})


def get_engine() -> Engine:
    """Un motor por proceso: con `prefork`, cada hijo crea el suyo al primer uso."""
    global _engine, _engine_pid
    if _engine is None or _engine_pid != os.getpid():
        _engine = build_engine(worker_database_target().url)
        _engine_pid = os.getpid()
    return _engine


def reset_engine() -> None:
    global _engine, _engine_pid
    if _engine is not None and _engine_pid == os.getpid():
        _engine.dispose()
    _engine, _engine_pid = None, None


@contextmanager
def transaction(engine: Engine, statement_timeout_ms: int) -> Iterator[Connection]:
    """Una transacción con su `statement_timeout` (solo PostgreSQL; SQLite no lo tiene)."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}"))
        yield connection
