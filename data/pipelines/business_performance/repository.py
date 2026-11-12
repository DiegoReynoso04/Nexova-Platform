"""SQL del pipeline (§2.3, §3.1 y §3.3 del diseño) sobre PostgreSQL.

Cada método abre **su propia transacción**: así un fallo en la carga no se
lleva el log por delante (`finish_run` escribe en otra) y un reintento de
Prefect repite una transacción completa.

Lectura: `telemetry_events`, `asset_entries` y `asset_exits`, **solo** las
columnas y claves de §2.3 (nunca `user_id`, `session_id`, `supplier_key`,
`assigned_to`, `supplier` ni `user_uuid`). Escritura: **solo** el esquema `reporting`.
"""

from __future__ import annotations

from . import _bootstrap  # noqa: F401  (rutas de packages/shared y data/process)

import json
from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from nexova_shared.reporting import (
    ABANDONED_AFTER_MINUTES,
    ABANDONED_ERROR_CLASS,
    BUSINESS_EVENT_TYPES,
    EVENT_SCHEMA_VERSION,
    PIPELINE_NAME,
    QUALIFIED_RUNS_TABLE,
    QUALIFIED_WEEKLY_TABLE,
    RunPhase,
    RunStatus,
)
from sqlalchemy import Engine, bindparam, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from weekly_performance import ExtractedEvent, QualityCounts, WeeklyRow

ONE_RUNNING_INDEX = "ux_pipeline_runs_one_running"
# Un solo número para todos los procesos que cargan este reporte (§3.1).
LOAD_LOCK_KEY = PIPELINE_NAME


class RunInProgressError(Exception):
    """Ya hay otra corrida `running` de este pipeline (índice único parcial)."""


def build_engine(url: str) -> Engine:
    # NullPool: con el Transaction pooler de Supabase cada transacción puede ir
    # por otra conexión; mantener un pool propio no aporta nada en un batch.
    return create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 10})


_BUSINESS_EVENTS_SQL = text(
    """
    SELECT event_id::text            AS event_id,
           event_type,
           "timestamp",
           tags->>'office'           AS office,
           tags->>'programme_id'     AS programme_id,
           tags->>'currency'         AS currency,
           tags->>'quantity'         AS quantity,
           tags->>'unit_cost'        AS unit_cost,
           COALESCE(tags->>'inbound_order_id', tags->>'outbound_order_id') AS order_id
    FROM telemetry_events
    WHERE event_type IN :event_types
      AND "timestamp" >= :window_start
      AND "timestamp" <  :window_end
    ORDER BY "timestamp", event_id
    """
).bindparams(bindparam("event_types", expanding=True))

_TECHNICAL_COUNTS_SQL = text(
    """
    SELECT (date_trunc('week', "timestamp" AT TIME ZONE 'UTC'))::date AS week_start, count(*) AS events
    FROM telemetry_events
    WHERE event_type NOT IN :event_types
      AND "timestamp" >= :window_start
      AND "timestamp" <  :window_end
    GROUP BY 1
    """
).bindparams(bindparam("event_types", expanding=True))

_ENTRIES_WITH_COST_SQL = text(
    """
    SELECT (date_trunc('week', created_at AT TIME ZONE 'UTC'))::date AS week_start, lower(office) AS office, count(*) AS rows
    FROM asset_entries
    WHERE unit_cost IS NOT NULL
      AND created_at >= :window_start
      AND created_at <  :window_end
    GROUP BY 1, 2
    """
)

_EXITS_SQL = text(
    """
    SELECT (date_trunc('week', created_at AT TIME ZONE 'UTC'))::date AS week_start, lower(office) AS office, count(*) AS rows
    FROM asset_exits
    WHERE created_at >= :window_start
      AND created_at <  :window_end
    GROUP BY 1, 2
    """
)

_SCHEMA_READY_SQL = text(
    f"SELECT to_regclass('{QUALIFIED_RUNS_TABLE}') IS NOT NULL AND to_regclass('{QUALIFIED_WEEKLY_TABLE}') IS NOT NULL"
)

_CLOSE_ABANDONED_SQL = text(
    f"""
    UPDATE {QUALIFIED_RUNS_TABLE}
    SET status = '{RunStatus.FAILED}', error_class = '{ABANDONED_ERROR_CLASS}', finished_at = now()
    WHERE pipeline_name = :pipeline_name
      AND status = '{RunStatus.RUNNING}'
      AND started_at < now() - make_interval(mins => {ABANDONED_AFTER_MINUTES})
    """
)

_INSERT_RUN_SQL = text(
    f"""
    INSERT INTO {QUALIFIED_RUNS_TABLE}
      (run_id, pipeline_name, trigger, requested_by, prefect_flow_run_id, status, phase,
       week_from, week_to, schema_version)
    VALUES
      (:run_id, :pipeline_name, :trigger, :requested_by, :prefect_flow_run_id, '{RunStatus.RUNNING}',
       '{RunPhase.EXTRACT}', :week_from, :week_to, :schema_version)
    ON CONFLICT (run_id) DO NOTHING
    """
)

_RUN_EXISTS_SQL = text(f"SELECT status FROM {QUALIFIED_RUNS_TABLE} WHERE run_id = :run_id")

_MARK_PHASE_SQL = text(
    f"UPDATE {QUALIFIED_RUNS_TABLE} SET phase = :phase WHERE run_id = :run_id AND status = '{RunStatus.RUNNING}'"
)

_FINISH_RUN_SQL = text(
    f"""
    UPDATE {QUALIFIED_RUNS_TABLE}
    SET status = :status, phase = :phase, finished_at = now(),
        week_from = :week_from, week_to = :week_to,
        source_rows_read = :source_rows_read, rows_rejected = :rows_rejected,
        duplicates_collapsed = :duplicates_collapsed, rows_upserted = :rows_upserted,
        rows_deleted = :rows_deleted, quality = CAST(:quality AS jsonb), error_class = :error_class
    WHERE run_id = :run_id AND status = '{RunStatus.RUNNING}'
    """
)

_LOAD_STATEMENTS = (
    # Una sola carga a la vez (válido con el Transaction pooler: es de transacción).
    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
    text(
        """
        CREATE TEMP TABLE new_cells (
          office text, programme_id text, week_start date,
          total_material_cost numeric, kits_delivered_count integer,
          shortage_events_count integer, cost_variance_events_count integer, currency text
        ) ON COMMIT DROP
        """
    ),
)

_INSERT_NEW_CELLS_SQL = text(
    """
    INSERT INTO new_cells VALUES (:office, :programme_id, :week_start, :total_material_cost,
      :kits_delivered_count, :shortage_events_count, :cost_variance_events_count, :currency)
    """
)

# Filas de las semanas recalculadas que ya no salen (NOT EXISTS vale con 0 filas).
_DELETE_ORPHANS_SQL = text(
    f"""
    DELETE FROM {QUALIFIED_WEEKLY_TABLE} AS w
    WHERE w.week_start BETWEEN :week_from AND :week_to
      AND NOT EXISTS (
        SELECT 1 FROM new_cells AS n
        WHERE n.office = w.office AND n.programme_id = w.programme_id AND n.week_start = w.week_start)
    """
)

_UPSERT_SQL = text(
    f"""
    INSERT INTO {QUALIFIED_WEEKLY_TABLE}
      (office, programme_id, week_start, total_material_cost, kits_delivered_count,
       shortage_events_count, cost_variance_events_count, currency, run_id)
    SELECT office, programme_id, week_start, total_material_cost, kits_delivered_count,
           shortage_events_count, cost_variance_events_count, currency, :run_id
    FROM new_cells
    ON CONFLICT (office, programme_id, week_start) DO UPDATE SET
      total_material_cost        = EXCLUDED.total_material_cost,
      kits_delivered_count       = EXCLUDED.kits_delivered_count,
      shortage_events_count      = EXCLUDED.shortage_events_count,
      cost_variance_events_count = EXCLUDED.cost_variance_events_count,
      currency                   = EXCLUDED.currency,
      computed_at                = now(),
      run_id                     = EXCLUDED.run_id
    """
)


def _constraint_name(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


class PostgresRepository:
    """E/S del pipeline. `engine` lo crea quien llama (`build_engine`)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def schema_ready(self) -> bool:
        with self.engine.connect() as connection:
            return bool(connection.execute(_SCHEMA_READY_SQL).scalar_one())

    def start_run(
        self,
        run_id: UUID,
        trigger: str,
        requested_by: UUID | None,
        prefect_flow_run_id: UUID | None,
        week_from: date,
        week_to: date,
    ) -> None:
        """Cierra las abandonadas e inserta la fila `running`.

        Idempotente (D9): si un reintento llega tras un `COMMIT` cuya respuesta se
        perdió, `ON CONFLICT (run_id) DO NOTHING` no choca con su propia fila.
        """
        params = {
            "run_id": run_id,
            "pipeline_name": PIPELINE_NAME,
            "trigger": trigger,
            "requested_by": requested_by,
            "prefect_flow_run_id": prefect_flow_run_id,
            "week_from": week_from,
            "week_to": week_to,
            "schema_version": EVENT_SCHEMA_VERSION,
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(_CLOSE_ABANDONED_SQL, {"pipeline_name": PIPELINE_NAME})
                connection.execute(_INSERT_RUN_SQL, params)
                status = connection.execute(_RUN_EXISTS_SQL, {"run_id": run_id}).scalar_one_or_none()
        except IntegrityError as error:
            if _constraint_name(error) == ONE_RUNNING_INDEX:
                raise RunInProgressError() from None
            raise
        if status != RunStatus.RUNNING:
            # La fila existe pero ya se cerró: no se reabre una corrida terminada.
            raise RunInProgressError()

    def mark_phase(self, run_id: UUID, phase: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(_MARK_PHASE_SQL, {"run_id": run_id, "phase": phase})

    def finish_run(
        self,
        run_id: UUID,
        *,
        status: str,
        phase: str,
        week_from: date,
        week_to: date,
        source_rows_read: int = 0,
        rows_rejected: int = 0,
        duplicates_collapsed: int = 0,
        rows_upserted: int = 0,
        rows_deleted: int = 0,
        quality: dict | None = None,
        error_class: str | None = None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                _FINISH_RUN_SQL,
                {
                    "run_id": run_id,
                    "status": status,
                    "phase": phase,
                    "week_from": week_from,
                    "week_to": week_to,
                    "source_rows_read": source_rows_read,
                    "rows_rejected": rows_rejected,
                    "duplicates_collapsed": duplicates_collapsed,
                    "rows_upserted": rows_upserted,
                    "rows_deleted": rows_deleted,
                    "quality": json.dumps(quality or {}, sort_keys=True),
                    "error_class": error_class,
                },
            )

    def extract_business_events(self, window_start: datetime, window_end: datetime) -> list[ExtractedEvent]:
        params = {"event_types": list(BUSINESS_EVENT_TYPES), "window_start": window_start, "window_end": window_end}
        with self.engine.connect() as connection:
            result = connection.execute(_BUSINESS_EVENTS_SQL, params).mappings()
            return [ExtractedEvent(**row) for row in result]

    def extract_quality_counts(self, window_start: datetime, window_end: datetime) -> QualityCounts:
        window = {"window_start": window_start, "window_end": window_end}
        with self.engine.connect() as connection:
            technical = connection.execute(
                _TECHNICAL_COUNTS_SQL, {**window, "event_types": list(BUSINESS_EVENT_TYPES)}
            ).all()
            entries = connection.execute(_ENTRIES_WITH_COST_SQL, window).all()
            exits = connection.execute(_EXITS_SQL, window).all()
        return QualityCounts(
            technical={week.isoformat(): count for week, count in technical},
            inventory_entries_with_cost={(week.isoformat(), office): count for week, office, count in entries},
            inventory_exits={(week.isoformat(), office): count for week, office, count in exits},
        )

    def load_weekly_rows(
        self, rows: Sequence[WeeklyRow], week_from: date, week_to: date, run_id: UUID
    ) -> tuple[int, int]:
        """La transacción de §3.1. Devuelve (`rows_upserted`, `rows_deleted`)."""
        with self.engine.begin() as connection:
            connection.execute(_LOAD_STATEMENTS[0], {"lock_key": LOAD_LOCK_KEY})
            connection.execute(_LOAD_STATEMENTS[1])
            if rows:
                connection.execute(
                    _INSERT_NEW_CELLS_SQL,
                    [
                        {
                            "office": row.office,
                            "programme_id": row.programme_id,
                            "week_start": row.week_start,
                            "total_material_cost": row.total_material_cost,
                            "kits_delivered_count": row.kits_delivered_count,
                            "shortage_events_count": row.shortage_events_count,
                            "cost_variance_events_count": row.cost_variance_events_count,
                            "currency": row.currency,
                        }
                        for row in rows
                    ],
                )
            deleted = connection.execute(_DELETE_ORPHANS_SQL, {"week_from": week_from, "week_to": week_to}).rowcount
            upserted = connection.execute(_UPSERT_SQL, {"run_id": run_id}).rowcount
        return int(upserted), int(deleted)
