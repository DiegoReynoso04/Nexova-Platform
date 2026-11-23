"""Lo que usa la API para encolar y leer tareas (productor). Única puerta de la API a la cola.

`services/api/app` importa solo este módulo (y `names`), nunca Celery directamente:
así el proceso de FastAPI no contiene ningún planificador ni código del worker
(`services/job_runner/tests/test_architecture.py` lo comprueba sobre `app/`).

- `submit(...)`: deduplica (A4), guarda los metadatos (A10) **antes** de publicar (un
  `GET /tasks/{id}` inmediato nunca da 404) y publica un mensaje con solo las
  referencias que recibe (`kwargs`). No toca PostgreSQL: el 202 no espera a Supabase.
- `status(...)`: propietario o admin; si no, `None` (la API responde 404, no 403).
  Mapea los 6 estados de Celery a los 4 del contrato (A10).
- Cualquier fallo de Redis o del broker → `TaskQueueUnavailableError` (503).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .config import DEDUPE_TTL_SECONDS, TaskQueueSettings
from .metadata import KeyValueStore, RedisStore, TaskMetadata, dedupe_key, load_metadata, metadata_key, save_metadata
from .names import TELEMETRY_REPORT_TASK

__all__ = [
    "TELEMETRY_REPORT_TASK",
    "Submission",
    "TaskQueueClient",
    "TaskQueueUnavailableError",
    "TaskStatus",
    "public_status",
]

PublicStatus = Literal["pending", "started", "success", "failure"]

# A10 (decidido el 2026-11-20). RETRY → started: la secuencia que ve el cliente es
# monótona (pending → started → success/failure) y no vuelve atrás entre reintentos.
STATUS_BY_CELERY_STATE: Mapping[str, PublicStatus] = {
    "PENDING": "pending",
    "RECEIVED": "pending",
    "STARTED": "started",
    "RETRY": "started",
    "SUCCESS": "success",
    "FAILURE": "failure",
    "REVOKED": "failure",
}
FINISHED_FAILED_STATES = frozenset({"FAILURE", "REVOKED"})


def public_status(celery_state: str) -> PublicStatus:
    return STATUS_BY_CELERY_STATE.get(celery_state, "pending")


class TaskQueueUnavailableError(Exception):
    """Redis o el broker no responden. El mensaje es solo la clase del error original."""


class Backend(Protocol):
    """Publicar un mensaje y leer el estado de una tarea. `CeleryBackend` y `memory.EagerBackend`."""

    def send(self, task_name: str, kwargs: dict[str, Any], task_id: str) -> None: ...

    def state(self, task_id: str) -> tuple[str, Any]: ...


class CeleryBackend:
    def __init__(self, celery: Any) -> None:
        self.celery = celery

    def send(self, task_name: str, kwargs: dict[str, Any], task_id: str) -> None:
        self.celery.send_task(task_name, kwargs=kwargs, task_id=task_id)

    def state(self, task_id: str) -> tuple[str, Any]:
        result = self.celery.AsyncResult(task_id)
        state = result.state
        # Solo el resultado de un éxito sale de aquí; el de un fallo es una excepción
        # (`TaskFailedError`) que la API nunca devuelve.
        return state, (result.result if state == "SUCCESS" else None)


@dataclass(frozen=True, slots=True)
class Submission:
    task_id: str
    deduplicated: bool


@dataclass(frozen=True, slots=True)
class TaskStatus:
    task_id: str
    task_name: str
    status: PublicStatus
    result: Any = None


def _unavailable_errors() -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [ConnectionError, TimeoutError, OSError]
    try:
        from redis.exceptions import RedisError

        errors.append(RedisError)
    except ImportError:  # pragma: no cover - redis es una dependencia de la API
        pass
    try:
        from kombu.exceptions import KombuError, OperationalError

        errors += [KombuError, OperationalError]
    except ImportError:  # pragma: no cover
        pass
    return tuple(errors)


UNAVAILABLE_ERRORS = _unavailable_errors()


class TaskQueueClient:
    def __init__(self, *, store: KeyValueStore, backend: Backend, new_id: Any = None) -> None:
        self.store = store
        self.backend = backend
        self.new_id = new_id or (lambda: str(uuid.uuid4()))

    @classmethod
    def from_redis_url(cls, redis_url: str) -> TaskQueueClient:
        """Para la API: su propia instancia de Celery (sin tareas registradas) y su cliente de Redis."""
        from .factory import create_app

        settings = TaskQueueSettings.from_redis_url(redis_url)
        celery = create_app(settings, include=())
        # Sin E/S: carga ya los módulos que Celery importa al primer uso (el transporte de
        # Redis, el backend de resultados y el productor). Sin esto, el primer 202 tras
        # arrancar pagaba esas importaciones (segundos en una máquina lenta).
        celery.backend  # noqa: B018
        celery.amqp.producer_pool  # noqa: B018
        celery.connection_for_write().transport  # noqa: B018
        celery.AsyncResult("00000000-0000-4000-8000-000000000000").backend  # noqa: B018
        return cls(store=RedisStore.from_settings(settings), backend=CeleryBackend(celery))

    def submit(self, task_name: str, kwargs: dict[str, Any], *, owner_id: str, dedupe_scope: str | None = None) -> Submission:
        try:
            return self._submit(task_name, kwargs, owner_id, dedupe_scope)
        except UNAVAILABLE_ERRORS as error:
            raise TaskQueueUnavailableError(type(error).__name__) from None

    def _submit(self, task_name: str, kwargs: dict[str, Any], owner_id: str, dedupe_scope: str | None) -> Submission:
        task_id = self.new_id()
        dedupe = dedupe_key(task_name, owner_id, dedupe_scope) if dedupe_scope is not None else None
        if dedupe is not None and not self.store.set(dedupe, task_id, ttl_seconds=DEDUPE_TTL_SECONDS, only_if_absent=True):
            existing = self.store.get(dedupe)
            if existing is not None and self._reusable(existing):
                return Submission(task_id=existing, deduplicated=True)
            # La anterior falló o ya no existe: esta petición la sustituye.
            self.store.set(dedupe, task_id, ttl_seconds=DEDUPE_TTL_SECONDS)
        save_metadata(self.store, task_id, TaskMetadata.new(owner_id, task_name))
        try:
            self.backend.send(task_name, kwargs, task_id)
        except BaseException:
            # Sin mensaje no hay tarea: ni metadatos ni deduplicación que apunten a ella.
            try:
                self.store.delete(metadata_key(task_id), *([dedupe] if dedupe else []))
            except UNAVAILABLE_ERRORS:
                pass
            raise
        return Submission(task_id=task_id, deduplicated=False)

    def _reusable(self, task_id: str) -> bool:
        if load_metadata(self.store, task_id) is None:
            return False
        state, _ = self.backend.state(task_id)
        return state not in FINISHED_FAILED_STATES

    def status(self, task_id: str, *, viewer_id: str, viewer_is_admin: bool) -> TaskStatus | None:
        """`None` si el id no existe, caducó o es de otro usuario (salvo para un admin)."""
        try:
            metadata = load_metadata(self.store, task_id)
            if metadata is None or (metadata.owner_id != viewer_id and not viewer_is_admin):
                return None
            state, result = self.backend.state(task_id)
        except UNAVAILABLE_ERRORS as error:
            raise TaskQueueUnavailableError(type(error).__name__) from None
        status = public_status(state)
        return TaskStatus(task_id=task_id, task_name=metadata.task_name, status=status, result=result if status == "success" else None)
