"""La puerta de la API a la cola: `TaskQueueClient` de `services/task_queue` (productor).

La API nunca importa el framework de colas directamente ni el código del worker:
solo `task_queue.client` y `task_queue.names`. Sin `REDIS_URL`, no hay cliente y las
rutas que encolan o leen tareas responden 503 `task_queue_unavailable` (A11).
"""

from fastapi import Request
from task_queue.client import TaskQueueClient
from task_queue.config import ConfigError as TaskQueueConfigError

from app.core.config import ConfigError, Settings
from app.core.errors import TaskQueueUnavailableError


def build_task_queue(settings: Settings) -> TaskQueueClient | None:
    """Lo llama `create_app`. Sin E/S: no conecta con Redis hasta la primera petición."""
    if not settings.redis_url:
        return None
    try:
        return TaskQueueClient.from_redis_url(settings.redis_url)
    except TaskQueueConfigError as error:
        # El mensaje de task_queue nombra la variable, nunca su valor.
        raise ConfigError(str(error)) from None


def task_queue_client(request: Request) -> TaskQueueClient:
    """El cliente de la app, o 503. Se llama dentro de cada ruta, después de validar la petición."""
    client = getattr(request.app.state, "task_queue", None)
    if client is None:
        raise TaskQueueUnavailableError()
    assert isinstance(client, TaskQueueClient)
    return client
