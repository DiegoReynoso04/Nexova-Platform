"""`GET /telemetry/report`: el periodo y la clave de caché (ticket del reporte técnico).

Las métricas viven en `services/telemetry/analysis.py`. Aquí solo se decide qué
ventana se analiza, una sola vez por petición:

- sin parámetros, los últimos 7 días; con `end_date` solo, los 7 días anteriores a él;
- una fecha sin zona se toma como UTC, y todo se normaliza a UTC antes del SQL:
  SQLite compara el texto sin la zona, así que otra zona fallaría sin dar error;
- se trunca a milisegundos, para que lo que se muestra sea lo que se filtra;
- `start` es inclusivo y `end`, exclusivo;
- como mucho 90 días, los de la retención: sin tope, un rango amplio cargaría la
  tabla entera.

La clave de caché es lo que pidió el cliente, no el periodo resuelto: con `now`
dentro, la ventana por defecto nunca acertaría (D8 de docs/telemetry/report-analysis.md).
"""

from collections.abc import Hashable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi.exceptions import RequestValidationError

DEFAULT_WINDOW = timedelta(days=7)
MAX_WINDOW = timedelta(days=90)


@dataclass(frozen=True, slots=True)
class ReportPeriod:
    start: datetime
    end: datetime


def to_utc(value: datetime) -> datetime:
    """`value` en UTC y truncado a milisegundos; sin zona, se toma como UTC."""
    moment = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return moment.replace(microsecond=moment.microsecond // 1000 * 1000)


def iso_utc(value: datetime) -> str:
    """Mismo formato que `timestamp` en el envelope: `2026-11-05T12:00:00.000Z`."""
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _invalid(message: str) -> RequestValidationError:
    return RequestValidationError([{"loc": ("query", "start_date"), "msg": message, "type": "value_error"}])


def resolve_period(start_date: datetime | None, end_date: datetime | None, now: datetime) -> ReportPeriod:
    """El periodo de la petición, o 422 `validation_error` si no es válido."""
    end = to_utc(end_date if end_date is not None else now)
    start = to_utc(start_date) if start_date is not None else end - DEFAULT_WINDOW
    if start >= end:
        raise _invalid("start_date must be earlier than end_date")
    if end - start > MAX_WINDOW:
        raise _invalid("the period cannot be longer than 90 days")
    return ReportPeriod(start=start, end=end)


def cache_key(start_date: datetime | None, end_date: datetime | None) -> Hashable:
    """La combinación recibida, en UTC. La ventana por defecto es `(None, None)`."""
    return (
        None if start_date is None else to_utc(start_date),
        None if end_date is None else to_utc(end_date),
    )
