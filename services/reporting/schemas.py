"""Contrato de `/reporting` (§5 de `data/pipelines/PIPELINE_DESIGN.md`; filas de KPI: el del BRIEFING)."""

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from nexova_shared.reporting import check_weeks
from pydantic import AfterValidator, BaseModel, ConfigDict, field_validator


def _monday(value: date) -> date:
    if value.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    return value


MondayDate = Annotated[date, AfterValidator(_monday)]


class WeeklyPerformanceEntry(BaseModel):
    """Una combinación oficina/programa de la semana. Cada oficina con su moneda; nunca un total entre oficinas."""

    office: str
    programme_id: str
    # Número JSON, sin redondear en la API (BRIEFING).
    total_material_cost: float
    kits_delivered_count: int
    shortage_events_count: int
    cost_variance_events_count: int
    currency: str


class WeeklyPerformance(BaseModel):
    week_start: date
    entries: list[WeeklyPerformanceEntry]


class PipelineRunRead(BaseModel):
    """La última corrida (`reporting.pipeline_runs`). Sin `requested_by` (seudónimo del usuario)."""

    run_id: UUID
    pipeline_name: str
    trigger: str
    prefect_flow_run_id: UUID | None
    status: str
    phase: str
    week_from: date
    week_to: date
    started_at: datetime
    finished_at: datetime | None
    source_rows_read: int
    rows_rejected: int
    duplicates_collapsed: int
    rows_upserted: int
    rows_deleted: int
    quality: dict[str, Any]
    error_class: str | None
    schema_version: str


class ManualRunRequest(BaseModel):
    """Cuerpo opcional de `POST /reporting/pipeline-runs`. Sin semana: la última cerrada."""

    model_config = ConfigDict(extra="forbid")

    week_start: date | None = None

    @field_validator("week_start")
    @classmethod
    def _closed_week_within_retention(cls, value: date | None) -> date | None:
        if value is not None:
            # Las mismas reglas que el pipeline (nexova_shared.reporting.weeks):
            # lunes, semana cerrada y dentro de la guarda de retención. El lunes,
            # antes, para que el mensaje nombre este campo.
            check_weeks(_monday(value), value, datetime.now(UTC))
        return value


class ManualRunAccepted(BaseModel):
    prefect_flow_run_id: UUID
    status: Literal["scheduled"]
