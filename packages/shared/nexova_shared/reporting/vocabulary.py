"""Nombres del esquema `reporting` y del pipeline de desempeño de negocio.

Fuente única para el pipeline (`data/pipelines`, `data/process`) y, en el
disparo manual, para las lecturas de la API (`services/reporting`). Diseño en
`data/pipelines/PIPELINE_DESIGN.md` (§2.2, §2.7, §3.3); los valores de oficina
y moneda son los del contrato de eventos (`docs/telemetry/event-schemas.json`).
"""

import re
from enum import StrEnum

SCHEMA = "reporting"
WEEKLY_TABLE = "weekly_office_program_performance"
RUNS_TABLE = "pipeline_runs"
QUALIFIED_WEEKLY_TABLE = f"{SCHEMA}.{WEEKLY_TABLE}"
QUALIFIED_RUNS_TABLE = f"{SCHEMA}.{RUNS_TABLE}"

# `pipeline_runs.pipeline_name` y nombre del flow de Prefect.
PIPELINE_NAME = "weekly_office_program_performance"

# Versión del contrato de eventos con la que se calcula (`pipeline_runs.schema_version`).
EVENT_SCHEMA_VERSION = "1.0.0"

# `programme_id` nulo en el evento (P1 pendiente). No cumple el patrón slug, así
# que nunca coincide con un programa real (D1 del diseño).
UNASSIGNED_PROGRAMME = "_unassigned"
PROGRAMME_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Una corrida `running` más antigua se cierra como abandonada (§3.4).
ABANDONED_AFTER_MINUTES = 30
# Ninguna semana pedida puede empezar antes de hoy menos estos días: 90 de
# retención de los eventos en bruto, menos una semana de margen (§3.4).
RETENTION_GUARD_DAYS = 84
# `error_class` de una corrida cerrada por plazo.
ABANDONED_ERROR_CLASS = "Abandoned"


class Office(StrEnum):
    VALENCIA = "valencia"
    MIAMI = "miami"


class Currency(StrEnum):
    EUR = "EUR"
    USD = "USD"


# La moneda de cada oficina. Nunca se convierte ni se suma entre oficinas.
OFFICE_CURRENCY: dict[Office, Currency] = {Office.VALENCIA: Currency.EUR, Office.MIAMI: Currency.USD}


class BusinessEvent(StrEnum):
    """Los 4 eventos de negocio que alimentan los KPI (§2.2)."""

    INBOUND_ORDER_CREATED = "inbound_order_created"
    OUTBOUND_ORDER_CREATED = "outbound_order_created"
    STOCK_THRESHOLD_TRIGGERED = "stock_threshold_triggered"
    KIT_COST_VARIANCE_DETECTED = "kit_cost_variance_detected"


BUSINESS_EVENT_TYPES: tuple[str, ...] = tuple(member.value for member in BusinessEvent)


class RunTrigger(StrEnum):
    SCHEDULE = "schedule"
    MANUAL = "manual"
    BACKFILL = "backfill"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunPhase(StrEnum):
    EXTRACT = "extract"
    TRANSFORM = "transform"
    LOAD = "load"
    DONE = "done"


# Columnas de KPI de la tabla del BRIEFING, en su orden.
KPI_COLUMNS: tuple[str, ...] = (
    "total_material_cost",
    "kits_delivered_count",
    "shortage_events_count",
    "cost_variance_events_count",
)
