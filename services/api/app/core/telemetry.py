"""Registro de la telemetría (ticket de captura).

- `api.telemetry`: una línea por lote recibido en `POST /telemetry/events`, con
  sus contadores y los `event_type` guardados. Nunca `properties`, ids ni el
  cuerpo: solo cifras y vocabulario cerrado del catálogo, ya validado.
- `nexova.telemetry`: una línea JSON por evento que emite la propia API (hoy
  solo `direct_stock_edit_rejected`, P7). El evento ya viene construido por
  `app/modules/telemetry/emitter.py`; aquí solo se escribe. Sigue saliendo
  aunque el evento se guarde en la tabla: si la base falla, queda este rastro.

Mismo patrón que `core/timing.py`: uvicorn no configura estos loggers, así que
`configure_telemetry_logger` les pone un `StreamHandler` a stderr, solo si no
tienen ya uno (los tests capturan desde el raíz).
"""

import json
import logging
from collections.abc import Mapping, Sequence

collector_logger = logging.getLogger("api.telemetry")
event_logger = logging.getLogger("nexova.telemetry")


def configure_telemetry_logger() -> None:
    for logger in (collector_logger, event_logger):
        if not logger.handlers:
            handler = logging.StreamHandler()
            # Mismo aspecto que las líneas de uvicorn y de `api.timing`.
            handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def log_batch_stored(
    *, received: int, stored: int, rejected: int, duplicates: int, dropped_keys: int, event_types: Sequence[str]
) -> None:
    """`event_types` ya está validado contra el catálogo: no puede llevar texto del cliente."""
    collector_logger.info(
        f"batch received: {received} events, stored {stored}, rejected {rejected}, "
        f"duplicates {duplicates}, dropped keys {dropped_keys} [{', '.join(event_types)}]"
    )


def log_event_not_stored(reason: str) -> None:
    """Un evento de la API no llegó a la tabla. `reason` es vocabulario propio o la clase del error."""
    collector_logger.warning(f"telemetry event not stored: {reason}")


def log_event(event: Mapping[str, object]) -> None:
    """Escribe un evento ya validado. Nunca lanza: la telemetría no rompe la petición."""
    try:
        event_logger.info(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    except Exception as exc:  # noqa: BLE001 — la telemetría nunca rompe la petición
        event_logger.warning(f"telemetry event dropped: {exc.__class__.__name__}")
