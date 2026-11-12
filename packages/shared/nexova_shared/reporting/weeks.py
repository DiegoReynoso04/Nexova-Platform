"""Semanas del reporte: lunes ISO en UTC, semanas cerradas y guarda de retención.

Las usan el pipeline (`data/process/weekly_performance.py`, que las reexporta)
y la API (validación del `week_start` de `POST /reporting/pipeline-runs`), para
que las dos apliquen exactamente las mismas reglas. Solo librería estándar.
Los mensajes de error no repiten valores recibidos.
"""

from datetime import UTC, date, datetime, timedelta

from .vocabulary import RETENTION_GUARD_DAYS, RunTrigger

_ONE_WEEK = timedelta(days=7)


class WeekSelectionError(ValueError):
    """Semanas pedidas no válidas: no son lunes, están en curso o en el futuro, o salen de la retención."""



def week_start_of(moment: datetime) -> date:
    """Lunes de la semana ISO de `moment`, en UTC (equivale a `date_trunc('week', ts AT TIME ZONE 'UTC')`)."""
    if moment.tzinfo is None:
        raise ValueError("timestamp without time zone")
    day = moment.astimezone(UTC).date()
    return day - timedelta(days=day.weekday())


def last_closed_week(now: datetime) -> date:
    """El lunes de la última semana cerrada: la anterior a la semana en curso (UTC)."""
    return week_start_of(now) - _ONE_WEEK


def weeks_between(week_from: date, week_to: date) -> list[date]:
    """Los lunes de `week_from` a `week_to`, ambos incluidos."""
    weeks: list[date] = []
    current = week_from
    while current <= week_to:
        weeks.append(current)
        current += _ONE_WEEK
    return weeks


def check_weeks(week_from: date, week_to: date, now: datetime) -> None:
    """Lanza `WeekSelectionError` si las semanas no se pueden calcular ahora."""
    for label, week in (("week_from", week_from), ("week_to", week_to)):
        if week.weekday() != 0:
            raise WeekSelectionError(f"{label} must be a Monday")
    if week_from > week_to:
        raise WeekSelectionError("week_from must not be after week_to")
    if week_to > last_closed_week(now):
        raise WeekSelectionError("only closed weeks can be computed (not the current week or a future one)")
    # Guarda de retención (§3.4): sin eventos en bruto, recalcular pondría la semana a cero.
    oldest_allowed = (now.astimezone(UTC) - timedelta(days=RETENTION_GUARD_DAYS)).date()
    if week_from < oldest_allowed:
        raise WeekSelectionError(f"weeks before {RETENTION_GUARD_DAYS} days ago are outside the retention guard")


def requested_weeks(trigger: str, week_start: date | None, now: datetime) -> tuple[date, date]:
    """Semanas que pide una corrida (§4.1), sin comprobarlas.

    - `schedule`: la última semana cerrada y la anterior (D5 del diseño).
    - `manual` / `backfill`: la pedida o, sin ella, la última cerrada.

    El flow las anota en `pipeline_runs` al abrir la corrida y después las
    comprueba (`resolve_weeks`): así un rechazo también queda en el log.
    """
    closed = last_closed_week(now)
    if trigger == RunTrigger.SCHEDULE:
        return closed - _ONE_WEEK, closed
    week = week_start if week_start is not None else closed
    return week, week


def resolve_weeks(trigger: str, week_start: date | None, now: datetime) -> tuple[date, date]:
    """`requested_weeks` + `check_weeks`: lanza `WeekSelectionError` si no se pueden calcular."""
    week_from, week_to = requested_weeks(trigger, week_start, now)
    check_weeks(week_from, week_to, now)
    return week_from, week_to


def window_of(week_from: date, week_to: date) -> tuple[datetime, datetime]:
    """Ventana de extracción en UTC: de `week_from` 00:00 a `week_to + 7 días` (exclusivo)."""
    start = datetime(week_from.year, week_from.month, week_from.day, tzinfo=UTC)
    end = datetime(week_to.year, week_to.month, week_to.day, tzinfo=UTC) + _ONE_WEEK
    return start, end


