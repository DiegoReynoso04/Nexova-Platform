"""De dónde sale `DATABASE_URL` y qué se imprime de ella.

Mismas reglas que `data/pipelines/business_performance/config.py` (que usa el
pipeline que lanza el script): la **variable de entorno** primero y, si falta,
**solo esa clave** del `.env` de la raíz, con un lector de la librería estándar.
Se copia en lugar de importarlo para que `services/` no dependa de `data/`;
`tests/test_config.py` comprueba que las dos resuelven lo mismo. Nunca se
imprime la URL, el usuario ni la contraseña: solo de dónde salió y el host.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
DATABASE_URL_VARIABLE = "DATABASE_URL"

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_ACCEPTED_SCHEMES = ("postgresql://", "postgresql+psycopg2://")


class ConfigError(Exception):
    """Configuración ausente o no válida. Los mensajes nombran la variable, nunca su valor."""


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    url: str = ""
    source: str = ""  # "entorno" o ".env de la raíz"
    host: str = ""

    def __repr__(self) -> str:  # nunca la URL en una traza ni en un log
        return f"DatabaseTarget(source={self.source!r}, host={self.host!r})"

    @property
    def is_local(self) -> bool:
        return self.host in LOCAL_HOSTS

    def describe(self) -> str:
        return f"DATABASE_URL: {self.source}, host {self.host}"


def read_env_file_value(path: Path, key: str) -> str | None:
    """El valor de `key` en un archivo `.env` (`CLAVE=valor`), o `None`. Lee solo esa clave."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()
        name, separator, value = stripped.partition("=")
        if not separator or name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value
    return None


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(_ACCEPTED_SCHEMES):
        raise ConfigError(f"{DATABASE_URL_VARIABLE} must start with postgresql:// or postgresql+psycopg2://")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def host_of(url: str) -> str:
    try:
        host = urlsplit(url).hostname
    except ValueError as error:
        raise ConfigError(f"{DATABASE_URL_VARIABLE} is not a valid URL") from error
    if not host:
        raise ConfigError(f"{DATABASE_URL_VARIABLE} has no host")
    return host


def target_from_url(url: str, source: str) -> DatabaseTarget:
    normalized = normalize_url(url)
    return DatabaseTarget(url=normalized, source=source, host=host_of(normalized))


def resolve_database_target(environ: Mapping[str, str] = os.environ, env_file: Path = ENV_FILE) -> DatabaseTarget:
    """La URL del entorno o, si falta, la del `.env` de la raíz. Lanza `ConfigError` si no hay ninguna."""
    value = environ.get(DATABASE_URL_VARIABLE, "").strip()
    if value:
        return target_from_url(value, "entorno")
    value = (read_env_file_value(env_file, DATABASE_URL_VARIABLE) or "").strip()
    if value:
        return target_from_url(value, ".env de la raíz")
    raise ConfigError(f"{DATABASE_URL_VARIABLE} is not set (terminal environment or the root .env)")


def build_engine(url: str) -> Engine:
    # NullPool: con el Transaction pooler de Supabase cada transacción puede ir por otra
    # conexión; un job de una sola pasada no necesita pool.
    return create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 10})
