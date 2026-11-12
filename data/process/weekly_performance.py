"""Transformación pura del pipeline de desempeño de negocio (§2.5 del diseño).

Sin E/S, sin Prefect y sin Pandas: solo librería estándar y
`nexova_shared.reporting`. El pipeline (`data/pipelines/pipeline.py`) la llama
desde la task `transform_weekly_rows`; los tests la prueban sola.

- `transform(events, quality, week_from, week_to)` → filas del reporte + estadísticas.
- `resolve_weeks(...)` y `last_closed_week(...)`: qué semanas se calculan.

Ninguna salida lleva identificadores: ni `event_id`, ni ids de orden, ni
usuarios. Por eso el resultado se puede cachear en disco (D6 del análisis).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from nexova_shared.reporting import (
    BUSINESS_EVENT_TYPES,
    OFFICE_CURRENCY,
    PROGRAMME_SLUG_PATTERN,
    UNASSIGNED_PROGRAMME,
    BusinessEvent,
    Office,
)

# Las semanas viven en nexova_shared.reporting (las usa también la API para
# validar el `week_start` del disparo manual); se reexportan aquí.
from nexova_shared.reporting.weeks import (  # noqa: F401
    WeekSelectionError,
    check_weeks,
    last_closed_week,
    requested_weeks,
    resolve_weeks,
    week_start_of,
    weeks_between,
    window_of,
)

# Sube al cambiar cualquier regla de este módulo: forma parte de la clave de la
# caché de `transform_weekly_rows`, así que invalida los resultados guardados.
TRANSFORM_VERSION = "1"

class DataQualityError(Exception):
    """Los datos no permiten un resultado correcto (p. ej. dos monedas en una celda). La corrida falla."""


@dataclass(frozen=True, slots=True)
class ExtractedEvent:
    """Un registro de `extract_business_events` (§2.3): las claves de `tags`, como texto."""

    event_id: str
    event_type: str
    timestamp: datetime
    office: str | None
    programme_id: str | None
    currency: str | None
    quantity: str | None
    unit_cost: str | None
    order_id: str | None


@dataclass(frozen=True, slots=True)
class WeeklyRow:
    """Una fila de `reporting.weekly_office_program_performance` (sin `id`, `computed_at` ni `run_id`)."""

    office: str
    programme_id: str
    week_start: date
    total_material_cost: Decimal
    kits_delivered_count: int
    shortage_events_count: int
    cost_variance_events_count: int
    currency: str


@dataclass(frozen=True, slots=True)
class TransformStats:
    source_rows_read: int
    rows_rejected: int
    duplicates_collapsed: int


@dataclass(frozen=True, slots=True)
class TransformResult:
    rows: tuple[WeeklyRow, ...]
    stats: TransformStats
    # Conciliación por semana (va a `pipeline_runs.quality`; no cambia ningún KPI).
    quality: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QualityCounts:
    """Conteos de `extract_quality_counts`, por semana (ISO, `YYYY-MM-DD`).

    - `technical`: eventos que no son de negocio, por semana.
    - `inventory_entries_with_cost` / `inventory_exits`: filas del inventario,
      por semana y oficina en minúsculas.
    """

    technical: Mapping[str, int] = field(default_factory=dict)
    inventory_entries_with_cost: Mapping[tuple[str, str], int] = field(default_factory=dict)
    inventory_exits: Mapping[tuple[str, str], int] = field(default_factory=dict)


# --- Transformación ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Typed:
    event_type: str
    timestamp: datetime
    event_id: str
    office: str
    programme_id: str
    currency: str
    quantity: int
    unit_cost: Decimal | None
    order_id: int
    week_start: date


def _positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text.isascii() or not text.isdigit():
        return None
    number = int(text)
    return number if number >= 1 else None


def _positive_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() and number > 0 else None


def _typed(event: ExtractedEvent) -> _Typed | None:
    """Paso 1 y 2 de §2.5: tipar, validar y poner el centinela. `None` = rechazado."""
    if event.event_type not in BUSINESS_EVENT_TYPES:
        return None
    try:
        office = Office(event.office)
    except ValueError:
        return None
    if event.currency != OFFICE_CURRENCY[office]:
        return None
    quantity = _positive_int(event.quantity)
    order_id = _positive_int(event.order_id)
    if quantity is None or order_id is None or event.timestamp.tzinfo is None:
        return None
    unit_cost: Decimal | None = None
    if event.event_type == BusinessEvent.INBOUND_ORDER_CREATED:
        unit_cost = _positive_decimal(event.unit_cost)
        if unit_cost is None:
            return None
    programme = event.programme_id
    if programme is None:
        programme = UNASSIGNED_PROGRAMME
    elif not PROGRAMME_SLUG_PATTERN.fullmatch(programme):
        return None
    return _Typed(
        event_type=event.event_type,
        timestamp=event.timestamp,
        event_id=event.event_id,
        office=office.value,
        programme_id=programme,
        currency=event.currency,
        quantity=quantity,
        unit_cost=unit_cost,
        order_id=order_id,
        week_start=week_start_of(event.timestamp),
    )


@dataclass(slots=True)
class _Cell:
    currencies: set[str] = field(default_factory=set)
    total_material_cost: Decimal = Decimal("0")
    kits_delivered_count: int = 0
    shortage_events_count: int = 0
    cost_variance_events_count: int = 0


def transform(
    events: Iterable[ExtractedEvent], quality: QualityCounts, week_from: date, week_to: date
) -> TransformResult:
    """Las reglas de §2.5. Determinista: los mismos eventos dan siempre el mismo resultado."""
    events = list(events)
    typed: list[_Typed] = []
    rejected = 0
    for event in events:
        item = _typed(event)
        if item is None or not week_from <= item.week_start <= week_to:
            rejected += 1
            continue
        typed.append(item)

    # Paso 4: una orden cuenta una vez por semana; se queda la primera por (timestamp, event_id).
    typed.sort(key=lambda item: (item.timestamp, item.event_id))
    seen: set[tuple[str, str, date, int]] = set()
    kept: list[_Typed] = []
    for item in typed:
        key = (item.event_type, item.office, item.week_start, item.order_id)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    duplicates = len(typed) - len(kept)

    # Paso 5: agregar por (office, programme_id, week_start).
    cells: dict[tuple[str, str, date], _Cell] = {}
    business_by_week_office: dict[tuple[str, str], dict[str, int]] = {}
    for item in kept:
        cell = cells.setdefault((item.office, item.programme_id, item.week_start), _Cell())
        cell.currencies.add(item.currency)
        if item.event_type == BusinessEvent.INBOUND_ORDER_CREATED:
            assert item.unit_cost is not None
            cell.total_material_cost += item.unit_cost * item.quantity
        elif item.event_type == BusinessEvent.OUTBOUND_ORDER_CREATED:
            cell.kits_delivered_count += 1
        elif item.event_type == BusinessEvent.STOCK_THRESHOLD_TRIGGERED:
            cell.shortage_events_count += 1
        else:
            cell.cost_variance_events_count += 1
        counts = business_by_week_office.setdefault((item.week_start.isoformat(), item.office), {})
        counts[item.event_type] = counts.get(item.event_type, 0) + 1

    rows: list[WeeklyRow] = []
    for (office, programme_id, week_start), cell in sorted(cells.items()):
        if len(cell.currencies) != 1:
            # Nunca se mezclan monedas en una celda (§2.5, paso 5).
            raise DataQualityError("a report cell has more than one currency")
        rows.append(
            WeeklyRow(
                office=office,
                programme_id=programme_id,
                week_start=week_start,
                total_material_cost=cell.total_material_cost,
                kits_delivered_count=cell.kits_delivered_count,
                shortage_events_count=cell.shortage_events_count,
                cost_variance_events_count=cell.cost_variance_events_count,
                currency=next(iter(cell.currencies)),
            )
        )

    stats = TransformStats(source_rows_read=len(events), rows_rejected=rejected, duplicates_collapsed=duplicates)
    return TransformResult(
        rows=tuple(rows), stats=stats, quality=reconcile(quality, business_by_week_office, week_from, week_to)
    )


def reconcile(
    quality: QualityCounts, business: Mapping[tuple[str, str], Mapping[str, int]], week_from: date, week_to: date
) -> dict[str, object]:
    """Paso 7 de §2.5: por semana, eventos técnicos; por semana y oficina, inventario frente a eventos.

    Solo conteos (JSON): ningún identificador. No cambia ningún KPI.
    """
    weeks: dict[str, object] = {}
    for week in weeks_between(week_from, week_to):
        key = week.isoformat()
        offices: dict[str, dict[str, int]] = {}
        for office in Office:
            counts = business.get((key, office.value), {})
            offices[office.value] = {
                "inventory_entries_with_cost": int(quality.inventory_entries_with_cost.get((key, office.value), 0)),
                "inbound_events": counts.get(BusinessEvent.INBOUND_ORDER_CREATED, 0),
                "inventory_exits": int(quality.inventory_exits.get((key, office.value), 0)),
                "outbound_events": counts.get(BusinessEvent.OUTBOUND_ORDER_CREATED, 0),
            }
        weeks[key] = {"technical_events": int(quality.technical.get(key, 0)), "offices": offices}
    return {"weeks": weeks}
