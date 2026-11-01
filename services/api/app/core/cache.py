"""Caché en memoria con TTL e invalidación por espacio de nombres (ticket de caching, F1).

Decisiones D2–D4 de docs/caching-analysis.md:

- **Diccionario en proceso**, sin dependencias. Una instancia por app en
  `app.state.response_cache` (cada `create_app()`, y por tanto cada test, empieza
  vacía). Solo es coherente con un único proceso: uvicorn arranca con
  `--workers 1`. Con más workers, cada uno tendría su copia y una escritura
  solo invalidaría la del proceso que la recibe (ver SPECS.md).
- **Espacios de nombres** (`inventory`, `incidents`): una escritura limpia el
  suyo entero. Cada espacio guarda como máximo `max_entries` entradas; al
  pasarse, sale la más antigua.
- **Todo valor caduca** (`ttl` obligatorio) con el reloj inyectable
  (`time.monotonic` por defecto; los tests pasan uno propio, sin `sleep`).
- **Generación por espacio:** `get_or_set` anota la generación antes de calcular
  y solo guarda si no ha cambiado. Así, un cálculo que empezó antes de una
  invalidación no puede guardar un valor viejo después de ella.
- **Sin datos personales en claves compartidas:** solo se cachean respuestas que
  son iguales para todo usuario autenticado. La caché se consulta dentro del
  handler, después de `get_current_user`: un acierto nunca se salta el 401.

Los valores se guardan tal cual (los modelos de respuesta) y se tratan como de
solo lectura: quien los obtiene no los modifica.
"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Depends, Request

DEFAULT_MAX_ENTRIES = 64

Value = TypeVar("Value")


@dataclass(slots=True)
class _Entry:
    expires_at: float
    value: object


class ResponseCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._clock = clock
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._spaces: dict[str, OrderedDict[Hashable, _Entry]] = {}
        self._generations: dict[str, int] = {}

    def get_or_set(self, namespace: str, key: Hashable, ttl: float, compute: Callable[[], Value]) -> Value:
        """Valor vigente de `(namespace, key)`; si no lo hay, lo calcula con `compute` y lo guarda `ttl` segundos.

        `compute` se ejecuta fuera del lock: dos fallos simultáneos pueden
        calcular los dos (se queda el último), pero ninguna petición espera a otra.
        Si `compute` lanza una excepción, no se guarda nada.
        """
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        with self._lock:
            entry = self._live_entry(namespace, key)
            if entry is not None:
                return entry.value  # type: ignore[return-value]
            generation = self._generations.get(namespace, 0)
        value = compute()
        with self._lock:
            if self._generations.get(namespace, 0) == generation:
                space = self._spaces.setdefault(namespace, OrderedDict())
                space.pop(key, None)
                space[key] = _Entry(expires_at=self._clock() + ttl, value=value)
                while len(space) > self._max_entries:
                    space.popitem(last=False)
        return value

    def invalidate(self, namespace: str) -> None:
        """Borra todas las entradas del espacio y descarta los cálculos que estaban en curso."""
        with self._lock:
            self._spaces.pop(namespace, None)
            self._generations[namespace] = self._generations.get(namespace, 0) + 1

    def size(self, namespace: str) -> int:
        """Entradas guardadas en el espacio, incluidas las caducadas que aún no se han leído."""
        with self._lock:
            return len(self._spaces.get(namespace, ()))

    def _live_entry(self, namespace: str, key: Hashable) -> _Entry | None:
        space = self._spaces.get(namespace)
        if space is None:
            return None
        entry = space.get(key)
        if entry is None:
            return None
        if self._clock() >= entry.expires_at:
            del space[key]
            return None
        return entry


def get_response_cache(request: Request) -> ResponseCache:
    cache = request.app.state.response_cache
    assert isinstance(cache, ResponseCache)
    return cache


CacheDep = Annotated[ResponseCache, Depends(get_response_cache)]
