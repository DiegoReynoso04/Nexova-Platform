"""Middleware de timing por petición (ticket de caching, F0; docs/caching-brief.md).

Una línea por petición en el logger `api.timing`: método, path, status y ms.
Solo el path, nunca la query string (puede llevar emails o filtros con datos),
ni cabeceras ni cuerpo.

uvicorn solo configura sus propios loggers (`uvicorn`, `uvicorn.error`,
`uvicorn.access`): sin un handler propio, un `logger.info` de `api.timing` no
sale (el `lastResort` de logging solo emite WARNING o más). `configure_timing_logger`
le pone un `StreamHandler` a stderr, solo si no tiene ya uno (los tests ponen un
`NullHandler` para no llenar su salida). Sigue propagando al raíz, que uvicorn
deja sin handlers: no hay líneas duplicadas.
"""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

logger = logging.getLogger("api.timing")


def configure_timing_logger() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler()
        # Mismo aspecto que las líneas de uvicorn (`INFO:     …`).
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


async def timing_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000  # ms
    logger.info(f"{request.method} {request.url.path} → {response.status_code} | {duration:.1f}ms")
    return response
