"""Registro de la telemetría (ticket de captura).

- `api.telemetry`: una línea por lote recibido en `POST /telemetry/events`
  (stub), con el número de eventos y sus `event_type`. Nunca `properties`, ids
  ni el cuerpo: solo vocabulario cerrado del catálogo, ya validado.

Mismo patrón que `core/timing.py`: uvicorn no configura estos loggers, así que
`configure_telemetry_logger` les pone un `StreamHandler` a stderr, solo si no
tienen ya uno (los tests capturan desde el raíz).
"""

import logging
from collections.abc import Sequence

collector_logger = logging.getLogger("api.telemetry")


def configure_telemetry_logger() -> None:
    if not collector_logger.handlers:
        handler = logging.StreamHandler()
        # Mismo aspecto que las líneas de uvicorn y de `api.timing`.
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        collector_logger.addHandler(handler)
    collector_logger.setLevel(logging.INFO)


def log_batch_received(event_types: Sequence[str]) -> None:
    """`event_types` ya está validado contra el catálogo: no puede llevar texto del cliente."""
    collector_logger.info(f"batch received: {len(event_types)} events [{', '.join(event_types)}]")
