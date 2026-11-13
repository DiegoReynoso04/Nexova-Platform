"""Transformación pura del pipeline de desempeño de negocio (§2.5 del diseño).

Sin E/S, sin Prefect y sin Pandas: solo librería estándar y
`nexova_shared.reporting`. El pipeline (`data/pipelines/pipeline.py`) ejecuta
cada paso como una task; los tests los prueban solos.

- `transform(events, quality, week_from, week_to)` → filas del reporte + estadísticas.
  Es la composición de los pasos con nombre propio (`type_and_validate`,
  `collapse_duplicate_orders`, un cálculo por KPI y `assemble_rows`), que el
  pipeline envuelve en una task cada uno (Parte 3 del hito).
- `resolve_weeks(...)` y `last_closed_week(...)`: qué semanas se calculan.

Ninguna salida lleva identificadores: ni `event_id`, ni ids de orden, ni
usuarios. Por eso el resultado se puede cachear en disco (D6 del análisis).
(Las entradas de `collapse_duplicate_orders` y de los cálculos por KPI sí los
llevan, y esas tasks no persisten su entrada.)
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
# caché de los cálculos por KPI, así que invalida los resultados guardados.
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


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Salida del subflow de extracción: los eventos de negocio y los conteos de calidad."""

    events: tuple[ExtractedEvent, ...]
    quality: QualityCounts


@dataclass(frozen=True, slots=True)
class LoadOutcome:
    """Salida del subflow de carga: filas escritas y huérfanas borradas."""

    rows_upserted: int
    rows_deleted: int


# --- Transformación ----------------------------------------------------------

# (office, programme_id, week_start): el grano del reporte.
CellKey = tuple[str, str, date]


@dataclass(frozen=True, slots=True)
class TypedEvent:
    """Un evento ya tipado y validado (pasos 1–3 de §2.5)."""

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


@dataclass(frozen=True, slots=True)
class TypedEvents:
    items: tuple[TypedEvent, ...]
    rejected: int


@dataclass(frozen=True, slots=True)
class DedupedEvents:
    items: tuple[TypedEvent, ...]
    duplicates_collapsed: int


def cell_key(item: TypedEvent) -> CellKey:
    return (item.office, item.programme_id, item.week_start)


def _positive_int(value: object) -> int | None:
    # Solo texto: un tipo incorrecto (int, float…) es un registro rechazado, no una excepción.
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.isascii() or not text.isdigit():
        return None
    number = int(text)
    return number if number >= 1 else None


def _positive_decimal(value: object) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() and number > 0 else None


def _typed(event: ExtractedEvent) -> TypedEvent | None:
    """Paso 1 y 2 de §2.5: tipar, validar y poner el centinela. `None` = rechazado."""
    if not isinstance(event.event_type, str) or event.event_type not in BUSINESS_EVENT_TYPES:
        return None
    try:
        office = Office(event.office)
    except ValueError:
        return None
    if event.currency != OFFICE_CURRENCY[office]:
        return None
    quantity = _positive_int(event.quantity)
    order_id = _positive_int(event.order_id)
    if (
        quantity is None
        or order_id is None
        or not isinstance(event.timestamp, datetime)
        or event.timestamp.tzinfo is None
    ):
        return None
    unit_cost: Decimal | None = None
    if event.event_type == BusinessEvent.INBOUND_ORDER_CREATED:
        unit_cost = _positive_decimal(event.unit_cost)
        if unit_cost is None:
            return None
    programme = event.programme_id
    if programme is None:
        programme = UNASSIGNED_PROGRAMME
    elif not isinstance(programme, str) or not PROGRAMME_SLUG_PATTERN.fullmatch(programme):
        return None
    return TypedEvent(
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


def type_and_validate(events: Iterable[ExtractedEvent], week_from: date, week_to: date) -> TypedEvents:
    """Pasos 1–3 de §2.5: tipar, `_unassigned`, `week_start` UTC. Lo que no cumple (o cae fuera de la ventana) se rechaza."""
    typed: list[TypedEvent] = []
    rejected = 0
    for event in events:
        item = _typed(event)
        if item is None or not week_from <= item.week_start <= week_to:
            rejected += 1
            continue
        typed.append(item)
    return TypedEvents(items=tuple(typed), rejected=rejected)


def collapse_duplicate_orders(items: Iterable[TypedEvent]) -> DedupedEvents:
    """Paso 4: una orden cuenta una vez por semana; se queda la primera por (timestamp, event_id)."""
    ordered = sorted(items, key=lambda item: (item.timestamp, item.event_id))
    seen: set[tuple[str, str, date, int]] = set()
    kept: list[TypedEvent] = []
    for item in ordered:
        key = (item.event_type, item.office, item.week_start, item.order_id)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return DedupedEvents(items=tuple(kept), duplicates_collapsed=len(ordered) - len(kept))


# --- Un cálculo por KPI (BRIEFING §4). Reciben los eventos ya deduplicados. ---


def total_material_cost_by_cell(kept: Iterable[TypedEvent]) -> dict[CellKey, Decimal]:
    """Costo de material por oficina/programa: Σ `unit_cost × quantity` de las entradas, en la moneda de la oficina."""
    totals: dict[CellKey, Decimal] = {}
    for item in kept:
        if item.event_type != BusinessEvent.INBOUND_ORDER_CREATED:
            continue
        assert item.unit_cost is not None
        key = cell_key(item)
        totals[key] = totals.get(key, Decimal("0")) + item.unit_cost * item.quantity
    return totals


def _count_by_cell(kept: Iterable[TypedEvent], event_type: BusinessEvent) -> dict[CellKey, int]:
    counts: dict[CellKey, int] = {}
    for item in kept:
        if item.event_type == event_type:
            key = cell_key(item)
            counts[key] = counts.get(key, 0) + 1
    return counts


def kits_delivered_by_cell(kept: Iterable[TypedEvent]) -> dict[CellKey, int]:
    """Kits entregados: conteo de `outbound_order_created` (órdenes, no unidades: D4)."""
    return _count_by_cell(kept, BusinessEvent.OUTBOUND_ORDER_CREATED)


def shortage_events_by_cell(kept: Iterable[TypedEvent]) -> dict[CellKey, int]:
    """Frecuencia de escasez: conteo de `stock_threshold_triggered`."""
    return _count_by_cell(kept, BusinessEvent.STOCK_THRESHOLD_TRIGGERED)


def cost_variance_events_by_cell(kept: Iterable[TypedEvent]) -> dict[CellKey, int]:
    """Frecuencia de variación de costo: conteo de `kit_cost_variance_detected`."""
    return _count_by_cell(kept, BusinessEvent.KIT_COST_VARIANCE_DETECTED)


def assemble_rows(
    kept: Iterable[TypedEvent],
    *,
    total_material_cost: Mapping[CellKey, Decimal],
    kits_delivered_count: Mapping[CellKey, int],
    shortage_events_count: Mapping[CellKey, int],
    cost_variance_events_count: Mapping[CellKey, int],
    stats: TransformStats,
    quality: QualityCounts,
    week_from: date,
    week_to: date,
) -> TransformResult:
    """Pasos 5–7: una fila por celda con al menos un evento, una moneda por celda y la conciliación.

    El universo de celdas sale de los eventos, no de los KPI: una celda que solo
    tuvo escasez sigue saliendo, con costo 0.
    """
    currencies: dict[CellKey, set[str]] = {}
    business_by_week_office: dict[tuple[str, str], dict[str, int]] = {}
    for item in kept:
        currencies.setdefault(cell_key(item), set()).add(item.currency)
        counts = business_by_week_office.setdefault((item.week_start.isoformat(), item.office), {})
        counts[item.event_type] = counts.get(item.event_type, 0) + 1

    rows: list[WeeklyRow] = []
    for key in sorted(currencies):
        if len(currencies[key]) != 1:
            # Nunca se mezclan monedas en una celda (§2.5, paso 5).
            raise DataQualityError("a report cell has more than one currency")
        office, programme_id, week_start = key
        rows.append(
            WeeklyRow(
                office=office,
                programme_id=programme_id,
                week_start=week_start,
                total_material_cost=total_material_cost.get(key, Decimal("0")),
                kits_delivered_count=kits_delivered_count.get(key, 0),
                shortage_events_count=shortage_events_count.get(key, 0),
                cost_variance_events_count=cost_variance_events_count.get(key, 0),
                currency=next(iter(currencies[key])),
            )
        )
    return TransformResult(
        rows=tuple(rows), stats=stats, quality=reconcile(quality, business_by_week_office, week_from, week_to)
    )


def transform(
    events: Iterable[ExtractedEvent], quality: QualityCounts, week_from: date, week_to: date
) -> TransformResult:
    """Las reglas de §2.5. Determinista: los mismos eventos dan siempre el mismo resultado.

    Composición de los pasos de arriba. El pipeline ejecuta esos mismos pasos
    como tasks y los dos caminos dan el mismo resultado (los tests lo comparan).
    """
    events = list(events)
    typed = type_and_validate(events, week_from, week_to)
    deduped = collapse_duplicate_orders(typed.items)
    kept = deduped.items
    return assemble_rows(
        kept,
        total_material_cost=total_material_cost_by_cell(kept),
        kits_delivered_count=kits_delivered_by_cell(kept),
        shortage_events_count=shortage_events_by_cell(kept),
        cost_variance_events_count=cost_variance_events_by_cell(kept),
        stats=TransformStats(
            source_rows_read=len(events), rows_rejected=typed.rejected, duplicates_collapsed=deduped.duplicates_collapsed
        ),
        quality=quality,
        week_from=week_from,
        week_to=week_to,
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
