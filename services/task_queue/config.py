"""Configuración de la cola: `REDIS_URL` y los ajustes de Celery de A7.

`REDIS_URL` sale solo del entorno (en Compose, del `.env` de la raíz). Es un secreto
(lleva la contraseña de Redis): ningún mensaje de error la repite y `repr` no la
muestra. El broker usa la base de la URL (por defecto la 0) y el result backend la
siguiente, para que las claves de los resultados no se mezclen con las colas.

Los valores de A7 viven aquí como constantes: la configuración, los tests y la
documentación leen los mismos.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDIS_SCHEMES = ("redis", "rediss")
# Redis trae 16 bases (0–15) y el backend usa la siguiente a la del broker.
MAX_BROKER_DB = 14

DEFAULT_QUEUE = "nexova.tasks"

# A7 (decididos por el usuario el 2026-11-20).
SOFT_TIME_LIMIT_SECONDS = 120
TIME_LIMIT_SECONDS = 150
# Mayor que la ejecución más larga (TIME_LIMIT_SECONDS) más la cuenta atrás más
# larga de un reintento: Redis devuelve a la cola un mensaje sin ACK pasado este tiempo.
VISIBILITY_TIMEOUT_SECONDS = 600
RESULT_EXPIRES_SECONDS = 3600
WORKER_CONCURRENCY = 2
WORKER_MAX_TASKS_PER_CHILD = 50
CONNECT_TIMEOUT_SECONDS = 2

# A8 (decididos por el usuario el 2026-11-20): `max_retries=3` literal, es decir,
# 4 ejecuciones antes de la DLQ; cuenta atrás base·2^n + uniforme(0, base), nunca
# por debajo de base·2^n (n = reintentos ya hechos).
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2
BACKOFF_MAX_SECONDS = 60

# A9 y A12: la DLQ y el texto del error.
ERROR_MESSAGE_MAX_CHARS = 2000
DEAD_LETTER_STATEMENT_TIMEOUT_MS = 5000
DEAD_LETTER_RETRY_DELAY_SECONDS = 1.0
DATABASE_CONNECT_TIMEOUT_SECONDS = 5

# A7 y A13: `statement_timeout` de las consultas de las tareas, por debajo del límite
# blando (120 s). Se puede bajar con TASK_QUEUE_STATEMENT_TIMEOUT_MS (en la demostración
# de A13, contra el efímero, a pocos segundos); nunca subir por encima del límite blando.
STATEMENT_TIMEOUT_VARIABLE = "TASK_QUEUE_STATEMENT_TIMEOUT_MS"
DEFAULT_STATEMENT_TIMEOUT_MS = 110_000

# A4 y A10: deduplicación por usuario y metadatos de propiedad de cada tarea.
DEDUPE_TTL_SECONDS = 60
# Mientras la tarea está en cola o en curso, sus metadatos llevan este TTL de seguridad
# (7 días); al terminar, el worker lo baja a RESULT_EXPIRES_SECONDS, el mismo del resultado.
METADATA_SAFETY_TTL_SECONDS = 7 * 24 * 3600


def statement_timeout_ms(environ: Mapping[str, str] | None = None) -> int:
    environ = os.environ if environ is None else environ
    value = (environ.get(STATEMENT_TIMEOUT_VARIABLE) or "").strip()
    if not value:
        return DEFAULT_STATEMENT_TIMEOUT_MS
    if not value.isdigit() or not 1 <= int(value) <= SOFT_TIME_LIMIT_SECONDS * 1000:
        raise ConfigError(f"{STATEMENT_TIMEOUT_VARIABLE} must be an integer between 1 and {SOFT_TIME_LIMIT_SECONDS * 1000}")
    return int(value)


class ConfigError(Exception):
    """Configuración inválida. El mensaje nombra la variable, nunca su valor."""


@dataclass(frozen=True, slots=True)
class TaskQueueSettings:
    broker_url: str = field(repr=False)
    result_backend: str = field(repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> TaskQueueSettings:
        environ = os.environ if environ is None else environ
        return cls.from_redis_url((environ.get("REDIS_URL") or "").strip())

    @classmethod
    def from_redis_url(cls, redis_url: str) -> TaskQueueSettings:
        if not redis_url:
            raise ConfigError("REDIS_URL is required (see .env.example)")
        try:
            parts = urlsplit(redis_url)
            port = parts.port
        except ValueError:
            raise ConfigError("REDIS_URL is not a valid URL") from None
        if parts.scheme not in REDIS_SCHEMES:
            raise ConfigError("REDIS_URL must start with redis:// or rediss://")
        if not parts.hostname or port is None:
            raise ConfigError("REDIS_URL must include a host and a port")
        if parts.query or parts.fragment:
            raise ConfigError("REDIS_URL must not have a query string or a fragment")
        db_text = parts.path.strip("/") or "0"
        if not db_text.isdigit() or int(db_text) > MAX_BROKER_DB:
            raise ConfigError(f"REDIS_URL database must be a number between 0 and {MAX_BROKER_DB}")
        db = int(db_text)
        return cls(broker_url=_with_db(parts, db), result_backend=_with_db(parts, db + 1))


def _with_db(parts: Any, db: int) -> str:
    return urlunsplit((parts.scheme, parts.netloc, f"/{db}", "", ""))


def celery_config(settings: TaskQueueSettings) -> dict[str, Any]:
    """Los ajustes de Celery de A7. Sin E/S: se prueba sin Redis."""
    return {
        "broker_url": settings.broker_url,
        "result_backend": settings.result_backend,
        # Solo JSON: un mensaje nunca ejecuta código al deserializarse (nada de pickle).
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "result_accept_content": ["json"],
        # ACK al terminar; si el proceso muere a mitad, el mensaje vuelve a la cola.
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        # Con acks_late: si se pierde la conexión con el broker, las tareas en curso se
        # cancelan (su mensaje sin ACK vuelve) en vez de terminar y duplicarse.
        "worker_cancel_long_running_tasks_on_connection_loss": True,
        "broker_transport_options": {
            "visibility_timeout": VISIBILITY_TIMEOUT_SECONDS,
            "socket_connect_timeout": CONNECT_TIMEOUT_SECONDS,
        },
        "redis_socket_connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "task_soft_time_limit": SOFT_TIME_LIMIT_SECONDS,
        "task_time_limit": TIME_LIMIT_SECONDS,
        "worker_prefetch_multiplier": 1,
        "worker_concurrency": WORKER_CONCURRENCY,
        "worker_max_tasks_per_child": WORKER_MAX_TASKS_PER_CHILD,
        "result_expires": RESULT_EXPIRES_SECONDS,
        # Sin esto Celery pasa de PENDING a SUCCESS sin STARTED.
        "task_track_started": True,
        # Flower muestra las tareas encoladas, en proceso y terminadas a partir de los eventos.
        "worker_send_task_events": True,
        "task_send_sent_event": True,
        # Con Redis caído, la API responde 503 en lugar de esperar segundos.
        "task_publish_retry": True,
        "task_publish_retry_policy": {"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.2},
        "broker_connection_timeout": CONNECT_TIMEOUT_SECONDS,
        "broker_connection_retry_on_startup": True,
        "task_default_queue": DEFAULT_QUEUE,
        "timezone": "UTC",
        "enable_utc": True,
    }
