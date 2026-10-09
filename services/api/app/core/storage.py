"""Storage de TinyDB que traduce los fallos del archivo a `StorageUnavailableError` (503).

Los tres repositorios (`app/database.py`, `app/auth/repository.py` y
`app/modules/incident_manager/repository.py`) abren TinyDB con
`storage=GuardedJSONStorage` y el nombre de su almacén.

Ámbito de la captura: en TinyDB 4.9 el archivo solo se toca en
`JSONStorage.__init__` (crear el directorio y el archivo y abrirlo), `read()`
(`json.load`), `write()` (escribir, `flush`, `fsync`, `truncate`) y `close()`.
Aquí se envuelven exactamente esas cuatro operaciones. El resto del trabajo de
un repositorio (consultas de TinyDB, `model_validate` de Pydantic, reglas de
nexova_shared) ocurre fuera del storage, así que sus excepciones, incluidos
los `ValidationError` de Pydantic (que heredan de `ValueError`), siguen su
camino normal (422, 400 o 500) y nunca se convierten en un 503.

El error nuevo se lanza fuera del bloque `except`: así no lleva la excepción
original ni como `__cause__` ni como `__context__` (un `JSONDecodeError`
guarda en `.doc` el contenido entero del archivo, con emails y hashes).
"""

import json
from enum import StrEnum
from typing import Any

from tinydb.storages import JSONStorage

from app.core.errors import StorageUnavailableError, log_storage_failure


class Store(StrEnum):
    """Nombre de cada almacén en el registro de fallos (nunca la ruta)."""

    SUPPLIERS = "suppliers"
    AUTH = "auth"
    INCIDENTS = "incidents"


class StorageFormatError(Exception):
    """El archivo es JSON válido, pero no tiene la forma de una base TinyDB."""


# Errores al leer el archivo: E/S, JSON inválido o bytes que no son UTF-8.
# Se nombran las subclases de ValueError una a una para no capturar ninguna otra.
_READ_ERRORS = (OSError, json.JSONDecodeError, UnicodeDecodeError)


def _is_database(data: Any) -> bool:
    """`{tabla: {doc_id: documento}}` con objetos en los tres niveles (lo que espera TinyDB)."""
    return isinstance(data, dict) and all(
        isinstance(table, dict) and all(isinstance(document, dict) for document in table.values())
        for table in data.values()
    )


class GuardedJSONStorage(JSONStorage):
    """`JSONStorage` cuyos fallos de archivo responden 503 y quedan registrados por almacén."""

    def __init__(self, path: str, *, store: Store, **kwargs: Any) -> None:
        # `store` no se pasa a JSONStorage: sus kwargs extra van a `json.dumps`.
        self._store = store
        unavailable: StorageUnavailableError | None = None
        try:
            super().__init__(path, **kwargs)
        except OSError as exc:
            unavailable = self._unavailable(exc)
        if unavailable is not None:
            raise unavailable

    def _unavailable(self, exc: BaseException) -> StorageUnavailableError:
        log_storage_failure(self._store, exc)
        return StorageUnavailableError()

    def read(self) -> dict[str, dict[str, Any]] | None:
        try:
            data = super().read()
        except _READ_ERRORS as exc:
            unavailable = self._unavailable(exc)
        else:
            if data is None or _is_database(data):
                return data
            unavailable = self._unavailable(StorageFormatError())
        raise unavailable

    def write(self, data: dict[str, dict[str, Any]]) -> None:
        # Solo OSError: `json.dumps` (TypeError/ValueError) sería un fallo del
        # código, no del archivo, y debe seguir siendo un 500.
        unavailable: StorageUnavailableError | None = None
        try:
            super().write(data)
        except OSError as exc:
            unavailable = self._unavailable(exc)
        if unavailable is not None:
            raise unavailable

    def close(self) -> None:
        unavailable: StorageUnavailableError | None = None
        try:
            super().close()
        except OSError as exc:
            unavailable = self._unavailable(exc)
        if unavailable is not None:
            raise unavailable
