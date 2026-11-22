"""Metadatos de propiedad de cada tarea (A10) y claves de deduplicación (A4), en Redis.

Celery devuelve `PENDING` para cualquier id, exista o no. Por eso, al encolar, la API
guarda `nexova:task:<id>` → `{owner_id, task_name, enqueued_at}`. `GET /tasks/{id}`
solo responde si esa clave existe y el usuario es su propietario (o admin).

**Que la clave no caduque mientras la tarea está viva (A10).** Al encolar lleva un TTL
de seguridad de 7 días (`METADATA_SAFETY_TTL_SECONDS`), no el del resultado (1 h): si
el worker está parado horas, la tarea sigue en la cola de Redis (AOF) y su clave
sigue ahí. Cuando la tarea **termina** (éxito o fallo definitivo, también por límite
duro), el worker baja el TTL a `RESULT_EXPIRES_SECONDS`, el mismo con el que Celery
guarda el resultado: los dos desaparecen a la vez y, a partir de ahí, `GET /tasks/{id}`
da 404. Un reintento no la toca (la tarea sigue viva). El TTL de seguridad solo acota
una clave huérfana (un mensaje perdido, que `acks_late` + AOF hacen muy improbable).

Se guardan en la base del result backend (la 1 de la `REDIS_URL`), no en la del broker.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from .config import METADATA_SAFETY_TTL_SECONDS, RESULT_EXPIRES_SECONDS, TaskQueueSettings

logger = logging.getLogger("task_queue")

METADATA_PREFIX = "nexova:task:"
DEDUPE_PREFIX = "nexova:dedupe:"


def metadata_key(task_id: str) -> str:
    return f"{METADATA_PREFIX}{task_id}"


def dedupe_key(task_name: str, owner_id: str, scope: str) -> str:
    return f"{DEDUPE_PREFIX}{task_name}:{owner_id}:{scope}"


class KeyValueStore(Protocol):
    """Lo que la cola necesita de Redis. `MemoryStore` (tests) y `RedisStore` lo cumplen."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, *, ttl_seconds: int, only_if_absent: bool = False) -> bool: ...

    def expire(self, key: str, ttl_seconds: int) -> None: ...

    def delete(self, *keys: str) -> None: ...

    def ttl(self, key: str) -> int | None: ...


class RedisStore:
    def __init__(self, client: object) -> None:
        self.client = client

    @classmethod
    def from_settings(cls, settings: TaskQueueSettings) -> RedisStore:
        import redis

        return cls(redis.Redis.from_url(settings.result_backend, socket_connect_timeout=2, socket_timeout=2, decode_responses=True))

    def get(self, key: str) -> str | None:
        return self.client.get(key)  # type: ignore[attr-defined, no-any-return]

    def set(self, key: str, value: str, *, ttl_seconds: int, only_if_absent: bool = False) -> bool:
        return bool(self.client.set(key, value, ex=ttl_seconds, nx=only_if_absent))  # type: ignore[attr-defined]

    def expire(self, key: str, ttl_seconds: int) -> None:
        self.client.expire(key, ttl_seconds)  # type: ignore[attr-defined]

    def delete(self, *keys: str) -> None:
        if keys:
            self.client.delete(*keys)  # type: ignore[attr-defined]

    def ttl(self, key: str) -> int | None:
        value = self.client.ttl(key)  # type: ignore[attr-defined]
        return None if value is None or value < 0 else int(value)


@dataclass(frozen=True, slots=True)
class TaskMetadata:
    owner_id: str
    task_name: str
    enqueued_at: str

    def dumps(self) -> str:
        return json.dumps({"owner_id": self.owner_id, "task_name": self.task_name, "enqueued_at": self.enqueued_at})

    @classmethod
    def loads(cls, text: str) -> TaskMetadata:
        data = json.loads(text)
        return cls(owner_id=str(data["owner_id"]), task_name=str(data["task_name"]), enqueued_at=str(data["enqueued_at"]))

    @classmethod
    def new(cls, owner_id: str, task_name: str) -> TaskMetadata:
        return cls(owner_id=owner_id, task_name=task_name, enqueued_at=datetime.now(UTC).isoformat(timespec="milliseconds"))


def save_metadata(store: KeyValueStore, task_id: str, metadata: TaskMetadata) -> None:
    store.set(metadata_key(task_id), metadata.dumps(), ttl_seconds=METADATA_SAFETY_TTL_SECONDS)


def load_metadata(store: KeyValueStore, task_id: str) -> TaskMetadata | None:
    text = store.get(metadata_key(task_id))
    return None if text is None else TaskMetadata.loads(text)


# --- Lado del worker ---------------------------------------------------------------

_worker_store: KeyValueStore | None = None
_worker_store_pid: int | None = None


def worker_store(environ: Mapping[str, str] | None = None) -> KeyValueStore:
    """El almacén del worker (uno por proceso), desde su `REDIS_URL`."""
    global _worker_store, _worker_store_pid
    if _worker_store is None or _worker_store_pid != os.getpid():
        _worker_store = RedisStore.from_settings(TaskQueueSettings.from_env(environ))
        _worker_store_pid = os.getpid()
    return _worker_store


def finish_metadata(task_id: str, *, store: KeyValueStore | None = None) -> None:
    """Al terminar una tarea: su clave caduca con su resultado. Nunca lanza."""
    try:
        (store if store is not None else worker_store()).expire(metadata_key(task_id), RESULT_EXPIRES_SECONDS)
    except Exception as error:  # Redis caído: la clave conserva el TTL de seguridad
        logger.warning("task_id=%s status=metadata_not_finished cause=%s", task_id, type(error).__name__)
