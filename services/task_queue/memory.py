"""Dobles en memoria para los tests de la API y de task_queue (sin Redis ni worker).

- `MemoryStore`: el `KeyValueStore` de `metadata.py`, con TTL y reloj inyectable.
- `EagerBackend`: «publica» ejecutando en el acto el manejador registrado para esa
  tarea y guarda su estado como lo haría Celery (`SUCCESS` con el resultado o
  `FAILURE`). Con `hold=True`, la tarea se queda en `PENDING` hasta `run(task_id)`,
  y `set_state` fija cualquier otro estado. Guarda cada mensaje enviado para que
  los tests comprueben que solo lleva referencias.

No los usa el código de producción.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class MemoryStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.values: dict[str, tuple[str, float]] = {}

    def _alive(self, key: str) -> tuple[str, float] | None:
        item = self.values.get(key)
        if item is not None and item[1] <= self.clock():
            del self.values[key]
            return None
        return item

    def get(self, key: str) -> str | None:
        item = self._alive(key)
        return None if item is None else item[0]

    def set(self, key: str, value: str, *, ttl_seconds: int, only_if_absent: bool = False) -> bool:
        if only_if_absent and self._alive(key) is not None:
            return False
        self.values[key] = (value, self.clock() + ttl_seconds)
        return True

    def expire(self, key: str, ttl_seconds: int) -> None:
        item = self._alive(key)
        if item is not None:
            self.values[key] = (item[0], self.clock() + ttl_seconds)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)

    def ttl(self, key: str) -> int | None:
        item = self._alive(key)
        return None if item is None else int(item[1] - self.clock())


class EagerBackend:
    def __init__(self, handlers: dict[str, Callable[..., Any]] | None = None, *, hold: bool = False) -> None:
        self.handlers = dict(handlers or {})
        self.hold = hold
        self.sent: list[tuple[str, dict[str, Any], str]] = []
        self.states: dict[str, tuple[str, Any]] = {}
        self.fail_sending: BaseException | None = None
        self.fail_reading: BaseException | None = None

    def send(self, task_name: str, kwargs: dict[str, Any], task_id: str) -> None:
        if self.fail_sending is not None:
            raise self.fail_sending
        self.sent.append((task_name, dict(kwargs), task_id))
        self.states[task_id] = ("PENDING", None)
        if not self.hold:
            self.run(task_id)

    def run(self, task_id: str) -> None:
        task_name, kwargs, _ = next(item for item in self.sent if item[2] == task_id)
        try:
            self.states[task_id] = ("SUCCESS", self.handlers[task_name](**kwargs))
        except Exception as error:
            self.states[task_id] = ("FAILURE", error)

    def set_state(self, task_id: str, state: str, result: Any = None) -> None:
        self.states[task_id] = (state, result)

    def state(self, task_id: str) -> tuple[str, Any]:
        if self.fail_reading is not None:
            raise self.fail_reading
        state, result = self.states.get(task_id, ("PENDING", None))
        return state, (result if state == "SUCCESS" else None)
