"""Pipeline de desempeño de negocio: «Reporte Semanal de Desempeño por Oficina y Programa».

Un flow de Prefect 3 que, por semana ISO (UTC), consolida en
`reporting.weekly_office_program_performance` los 4 KPI del BRIEFING a partir
de los 4 eventos de negocio de `telemetry_events`, y deja cada corrida en
`reporting.pipeline_runs`. Diseño: `PIPELINE_DESIGN.md`; decisiones D1–D16:
`docs/reporting/implementation-analysis.md`.

Uso, desde la raíz del repo y con el venv de `data/pipelines` (ver README.md):

    data\\pipelines\\.venv\\Scripts\\python data\\pipelines\\pipeline.py                         # Windows
    data/pipelines/.venv/bin/python data/pipelines/pipeline.py                                 # Linux/macOS
    ... pipeline.py --week-start 2026-11-02      # una semana concreta (lunes)
    ... pipeline.py --from 2026-11-02 [--to ...] # backfill, una corrida por semana

Sin `PREFECT_API_URL`, Prefect arranca un servidor efímero en un subproceso
(estado en `~/.prefect`, fuera del repo). La base: `DATABASE_URL` de la
terminal o, si falta, del `.env` de la raíz (D5); se imprime solo el host.

Códigos de salida: 0 corrida(s) completada(s); 1 alguna corrida falló;
2 configuración, argumentos o esquema `reporting` ausente (con el comando de la
migración, sin traza).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

PIPELINES_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINES_DIR.parents[1]
# Intermedios del pipeline: la caché de `transform_weekly_rows` (D6) y los
# snapshots de validación (D7). Las dos carpetas están en .gitignore.
RAW_DIR = REPO_ROOT / "data" / "raw" / "business_performance"
EVAL_DIR = REPO_ROOT / "data" / "eval" / "business_performance"

# Antes de importar Prefect: dónde guarda los resultados cacheados (si no viene
# ya del entorno, como en el worker).
os.environ.setdefault("PREFECT_LOCAL_STORAGE_PATH", str(RAW_DIR / "prefect-results"))

if str(PIPELINES_DIR) not in sys.path:  # al importarlo desde los tests o desde otra carpeta
    sys.path.insert(0, str(PIPELINES_DIR))

# Antes de Prefect: analítica desactivada (servidor y cliente) y rutas del monorepo.
from business_performance import _bootstrap  # noqa: E402,F401
from business_performance.config import (  # noqa: E402
    SECRET_BLOCK_NAME,
    ConfigError,
    DatabaseTarget,
    resolve_database_target,
    target_from_url,
)
from business_performance.repository import PostgresRepository, RunInProgressError, build_engine  # noqa: E402
from nexova_shared.reporting import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    PIPELINE_NAME,
    RunPhase,
    RunStatus,
    RunTrigger,
)
from prefect import flow, get_run_logger, task  # noqa: E402
from prefect.cache_policies import NO_CACHE  # noqa: E402
from prefect.states import Failed  # noqa: E402
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError  # noqa: E402
from weekly_performance import (  # noqa: E402
    TRANSFORM_VERSION,
    DataQualityError,
    ExtractedEvent,
    QualityCounts,
    TransformResult,
    WeekSelectionError,
    check_weeks,
    requested_weeks,
    transform,
    weeks_between,
    window_of,
)

CONFIG_EXIT = 2
RUN_FAILED_EXIT = 1

# --- Repositorio de E/S ------------------------------------------------------
#
# Las tasks no reciben el repositorio como parámetro (no es serializable ni
# forma parte de ninguna clave de caché): lo piden aquí. `main` lo fija con la
# URL ya resuelta; el worker lo crea desde el block. Los tests lo sustituyen.

_repository: PostgresRepository | None = None


def set_repository(repository: PostgresRepository | None) -> None:
    global _repository
    _repository = repository


def get_repository() -> PostgresRepository:
    global _repository
    if _repository is None:
        _repository = PostgresRepository(build_engine(_database_target().url))
    return _repository


def _database_target() -> DatabaseTarget:
    """Con servidor de Prefect (el worker), el block `Secret`; sin él, el entorno o el `.env` (D5)."""
    if os.environ.get("PREFECT_API_URL"):
        from prefect.blocks.system import Secret  # noqa: PLC0415

        return target_from_url(Secret.load(SECRET_BLOCK_NAME).get(), "block de Prefect")
    return resolve_database_target()


def _now() -> datetime:
    return datetime.now(UTC)


# --- Reintentos (D9) ---------------------------------------------------------

# Errores que un reintento no arregla: los datos, las semanas, otra corrida en
# marcha o una SQL que la base rechaza. Reintentarlos solo retrasa el fallo.
_PERMANENT_ERRORS = (
    DataQualityError,
    WeekSelectionError,
    RunInProgressError,
    IntegrityError,
    ProgrammingError,
    DataError,
)


def _retry_transient_only(task_, task_run, state) -> bool:
    error = state.result(raise_on_failure=False)
    return not isinstance(error, _PERMANENT_ERRORS)


# Tasks que leen o escriben en la base: 2 reintentos, 10 s entre ellos. Cubren
# los cortes transitorios del pooler de Supabase (3 intentos en ~20 s) sin
# colgar minutos una corrida manual. Solo errores transitorios (arriba).
DB_RETRIES = 2
DB_RETRY_DELAY_SECONDS = 10
# La carga: 2 reintentos, 30 s entre ellos (como el diseño). Su transacción se
# deshace entera y conviene dar tiempo a que se libere el lock o la conexión;
# 3 intentos en ~1 min caben de sobra en las 4 h de margen del cron.
LOAD_RETRIES = 2
LOAD_RETRY_DELAY_SECONDS = 30

_db_task = {
    "retries": DB_RETRIES,
    "retry_delay_seconds": DB_RETRY_DELAY_SECONDS,
    "retry_condition_fn": _retry_transient_only,
    # Sin caché: leer o escribir en la base tiene que pasar cada vez.
    "cache_policy": NO_CACHE,
}


# --- Tasks -------------------------------------------------------------------


@task(name="start_run", **_db_task)
def start_run(
    run_id: UUID,
    trigger: str,
    requested_by: UUID | None,
    prefect_flow_run_id: UUID | None,
    week_from: date,
    week_to: date,
) -> UUID:
    """Cierra las corridas abandonadas (> 30 min) y abre la fila `running` (idempotente: D9)."""
    get_repository().start_run(run_id, trigger, requested_by, prefect_flow_run_id, week_from, week_to)
    return run_id


# Determinista (sin E/S): reintentar daría el mismo error.
@task(name="resolve_weeks", retries=0, cache_policy=NO_CACHE)
def resolve_weeks(week_from: date, week_to: date, now: datetime) -> tuple[date, date]:
    """Comprueba las semanas pedidas: lunes, cerradas y dentro de la guarda de retención (§3.4)."""
    check_weeks(week_from, week_to, now)
    return week_from, week_to


@task(name="extract_business_events", **_db_task)
def extract_business_events(week_from: date, week_to: date) -> list[ExtractedEvent]:
    """Los 4 eventos de negocio de la ventana (§2.3), solo las claves de `tags` que hacen falta."""
    return get_repository().extract_business_events(*window_of(week_from, week_to))


@task(name="extract_quality_counts", **_db_task)
def extract_quality_counts(week_from: date, week_to: date) -> QualityCounts:
    """Conteos técnicos y del inventario para la conciliación (no cambian ningún KPI)."""
    return get_repository().extract_quality_counts(*window_of(week_from, week_to))


@task(name="mark_phase", **_db_task)
def mark_phase(run_id: UUID, phase: str) -> None:
    """Checkpoint en `pipeline_runs.phase`, en una transacción corta, al entrar en cada fase."""
    get_repository().mark_phase(run_id, phase)


def transform_cache_key(context, parameters) -> str:
    """Clave de la caché de `transform_weekly_rows` (D6).

    SHA-256 de la versión de las reglas, las semanas, **cada evento extraído
    completo** (ordenados por `event_id`) y los conteos de calidad. La clave
    cambia en cuanto cambia un solo evento o un conteo, así que la caché nunca
    sirve un resultado viejo: es exacta, no una aproximación por número de
    filas. Subir `TRANSFORM_VERSION` la invalida si cambian las reglas.
    """
    events: Sequence[ExtractedEvent] = parameters["events"]
    quality: QualityCounts = parameters["quality"]
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            [TRANSFORM_VERSION, str(parameters["week_from"]), str(parameters["week_to"])], separators=(",", ":")
        ).encode()
    )
    for item in sorted(events, key=lambda event: event.event_id):
        digest.update(
            json.dumps(
                [
                    item.event_id,
                    item.event_type,
                    item.timestamp.isoformat(),
                    item.office,
                    item.programme_id,
                    item.currency,
                    item.quantity,
                    item.unit_cost,
                    item.order_id,
                ],
                separators=(",", ":"),
            ).encode()
        )
    digest.update(
        json.dumps(
            [
                sorted(quality.technical.items()),
                sorted((list(key), value) for key, value in quality.inventory_entries_with_cost.items()),
                sorted((list(key), value) for key, value in quality.inventory_exits.items()),
            ],
            separators=(",", ":"),
        ).encode()
    )
    return f"{PIPELINE_NAME}-transform-{digest.hexdigest()}"


@task(
    name="transform_weekly_rows",
    # Caché de una hora (lo que pide el enunciado): una corrida repetida en la
    # misma hora con los mismos eventos (p. ej. un reintento manual tras un
    # fallo en la carga, §3.2 del diseño) no recalcula: Prefect devuelve el
    # resultado guardado (estado `Cached`). Es la única task cacheada: su
    # resultado son agregados sin identificadores (se guarda en
    # data/raw/business_performance/prefect-results, ignorado por git), y la
    # clave depende del contenido exacto de la extracción (ver arriba).
    # Cachear la extracción serviría eventos viejos; cachear la carga se
    # saltaría escrituras.
    cache_key_fn=transform_cache_key,
    cache_expiration=timedelta(hours=1),
    persist_result=True,
    # Determinista (sin E/S): reintentar daría el mismo error.
    retries=0,
)
def transform_weekly_rows(
    events: list[ExtractedEvent], quality: QualityCounts, week_from: date, week_to: date
) -> TransformResult:
    """Tipado, `_unassigned`, `week_start` UTC, dedup por orden y agregación (§2.5)."""
    return transform(events, quality, week_from, week_to)


@task(name="load_weekly_rows", retries=LOAD_RETRIES, retry_delay_seconds=LOAD_RETRY_DELAY_SECONDS,
      retry_condition_fn=_retry_transient_only, cache_policy=NO_CACHE)
def load_weekly_rows(result: TransformResult, week_from: date, week_to: date, run_id: UUID) -> tuple[int, int]:
    """La transacción de §3.1: lock, borrar huérfanas y upsert. Devuelve (`upserted`, `deleted`)."""
    return get_repository().load_weekly_rows(result.rows, week_from, week_to, run_id)


@task(name="finish_run", **_db_task)
def finish_run(
    run_id: UUID,
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
    """Cierra la fila: `completed`/`failed`, fase, contadores, `quality` y `error_class`."""
    get_repository().finish_run(
        run_id,
        status=status,
        phase=phase,
        week_from=week_from,
        week_to=week_to,
        source_rows_read=source_rows_read,
        rows_rejected=rows_rejected,
        duplicates_collapsed=duplicates_collapsed,
        rows_upserted=rows_upserted,
        rows_deleted=rows_deleted,
        quality=quality,
        error_class=error_class,
    )


# Opcional (D7): disco local, sin servicios externos; reintentar daría el mismo error.
@task(name="write_eval_snapshot", retries=0, cache_policy=NO_CACHE)
def write_eval_snapshot(output_dir: str, run_id: UUID, week_from: date, week_to: date,
                        result: TransformResult, upserted: int, deleted: int) -> str:
    """Copia de validación de la corrida en `data/eval/business_performance/` (sin identificadores ni URL)."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{week_from.isoformat()}_{run_id}.json"
    snapshot = {
        "pipeline_name": PIPELINE_NAME,
        "run_id": str(run_id),
        "week_from": week_from.isoformat(),
        "week_to": week_to.isoformat(),
        "schema_version": EVENT_SCHEMA_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "stats": {
            "source_rows_read": result.stats.source_rows_read,
            "rows_rejected": result.stats.rows_rejected,
            "duplicates_collapsed": result.stats.duplicates_collapsed,
            "rows_upserted": upserted,
            "rows_deleted": deleted,
        },
        "rows": [
            {
                "office": row.office,
                "programme_id": row.programme_id,
                "week_start": row.week_start.isoformat(),
                "total_material_cost": str(row.total_material_cost),
                "kits_delivered_count": row.kits_delivered_count,
                "shortage_events_count": row.shortage_events_count,
                "cost_variance_events_count": row.cost_variance_events_count,
                "currency": row.currency,
            }
            for row in result.rows
        ],
        "quality": result.quality,
    }
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return path.name


# --- Flows -------------------------------------------------------------------


def _flow_run_id() -> UUID | None:
    from prefect.runtime import flow_run  # noqa: PLC0415

    value = flow_run.id
    return UUID(str(value)) if value else None


def _summary(run_id: UUID, status: str, phase: str, week_from: date, week_to: date, started: datetime,
             result: TransformResult | None = None, upserted: int = 0, deleted: int = 0,
             error_class: str | None = None, optional_steps: dict | None = None) -> dict:
    """Línea JSON de cierre (D10): contadores, sin URL ni identificadores de personas u órdenes."""
    return {
        "event": "pipeline_run_finished",
        "pipeline_name": PIPELINE_NAME,
        "run_id": str(run_id),
        "status": status,
        "phase": phase,
        "week_from": week_from.isoformat(),
        "week_to": week_to.isoformat(),
        "source_rows_read": result.stats.source_rows_read if result else 0,
        "rows_rejected": result.stats.rows_rejected if result else 0,
        "duplicates_collapsed": result.stats.duplicates_collapsed if result else 0,
        "rows_upserted": upserted,
        "rows_deleted": deleted,
        "error_class": error_class,
        "optional_steps": optional_steps or {},
        "duration_seconds": round((_now() - started).total_seconds(), 3),
    }


@flow(name=PIPELINE_NAME, log_prints=False)
def weekly_office_program_performance(
    trigger: str = RunTrigger.MANUAL.value,
    week_start: date | None = None,
    requested_by: UUID | None = None,
):
    """Extracción → transformación → carga de una corrida (§4.1 y D8)."""
    logger = get_run_logger()
    started = _now()
    week_from, week_to = requested_weeks(trigger, week_start, started)
    run_id = uuid4()  # lo genera el flow: `start_run` se puede reintentar (D9)
    # Sin fila no hay nada que cerrar: si `start_run` falla, el flow falla.
    start_run(run_id, trigger, requested_by, _flow_run_id(), week_from, week_to)
    phase = RunPhase.EXTRACT.value
    result: TransformResult | None = None

    def close_failed(error: BaseException) -> dict:
        error_class = type(error).__name__  # solo la clase: el mensaje puede llevar la URL
        finish_run(
            run_id,
            status=RunStatus.FAILED.value,
            phase=phase,
            week_from=week_from,
            week_to=week_to,
            source_rows_read=result.stats.source_rows_read if result else 0,
            rows_rejected=result.stats.rows_rejected if result else 0,
            duplicates_collapsed=result.stats.duplicates_collapsed if result else 0,
            quality=result.quality if result else {},
            error_class=error_class,
        )
        summary = _summary(run_id, RunStatus.FAILED.value, phase, week_from, week_to, started, result,
                           error_class=error_class)
        logger.error(json.dumps(summary, sort_keys=True))
        return summary

    try:
        resolve_weeks(week_from, week_to, started)
        events = extract_business_events(week_from, week_to)
        quality = extract_quality_counts(week_from, week_to)
        mark_phase(run_id, RunPhase.TRANSFORM.value)
        phase = RunPhase.TRANSFORM.value  # solo si mark_phase salió bien
        result = transform_weekly_rows(events, quality, week_from, week_to)
        mark_phase(run_id, RunPhase.LOAD.value)
        phase = RunPhase.LOAD.value

        # Fallo manejado explícitamente (D8): con return_state=True la carga
        # devuelve su State en lugar de lanzar. Si falló (tras sus reintentos),
        # se cierra la corrida como `failed` en la fase `load` y el flow termina
        # en Failed sin un raise.
        load_state = load_weekly_rows(result, week_from, week_to, run_id, return_state=True)
        if load_state.is_failed():
            summary = close_failed(load_state.result(raise_on_failure=False))
            return Failed(message=f"load_weekly_rows failed ({summary['error_class']})", data=summary)
        upserted, deleted = load_state.result()

        # Paso opcional (D7) con return_state=True: si falla, la corrida ya está
        # cargada y termina `completed`; el fallo queda en `quality` y en el log.
        optional_steps: dict[str, str] = {}
        snapshot_state = write_eval_snapshot(
            str(EVAL_DIR), run_id, week_from, week_to, result, upserted, deleted, return_state=True
        )
        if snapshot_state.is_failed():
            error = snapshot_state.result(raise_on_failure=False)
            optional_steps = {"eval_snapshot": "failed", "error_class": type(error).__name__}
            logger.warning("Optional step write_eval_snapshot failed (%s); the run continues", type(error).__name__)
        else:
            optional_steps = {"eval_snapshot": "completed"}

        finish_run(
            run_id,
            status=RunStatus.COMPLETED.value,
            phase=RunPhase.DONE.value,
            week_from=week_from,
            week_to=week_to,
            source_rows_read=result.stats.source_rows_read,
            rows_rejected=result.stats.rows_rejected,
            duplicates_collapsed=result.stats.duplicates_collapsed,
            rows_upserted=upserted,
            rows_deleted=deleted,
            quality={**result.quality, "optional_steps": optional_steps},
        )
    except Exception as error:  # lo que no pasó por return_state (D8)
        close_failed(error)
        raise
    summary = _summary(run_id, RunStatus.COMPLETED.value, RunPhase.DONE.value, week_from, week_to, started,
                       result, upserted, deleted, optional_steps=optional_steps)
    logger.info(json.dumps(summary, sort_keys=True))
    return summary


@flow(name=f"backfill_{PIPELINE_NAME}")
def backfill_weekly_office_program_performance(week_from: date, week_to: date):
    """Backfill: el flow principal como subflow, una vez por semana y en orden (§4.1).

    Cada semana deja su propia fila en el log. Se para en la primera que falle.
    """
    summaries = []
    for week in weeks_between(week_from, week_to):
        state = weekly_office_program_performance(
            trigger=RunTrigger.BACKFILL.value, week_start=week, return_state=True
        )
        if not state.is_completed():
            return Failed(message=f"backfill stopped at week {week.isoformat()}", data=summaries)
        summaries.append(state.result())
    return summaries


# --- CLI ---------------------------------------------------------------------


def _monday(value: str) -> date:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a date YYYY-MM-DD") from None
    if day.weekday() != 0:
        raise argparse.ArgumentTypeError("the week must start on a Monday")
    return day


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline.py",
        description="Reporte semanal de desempeño por oficina y programa (Prefect). "
        "Sin opciones: la última semana cerrada.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--week-start", type=_monday, help="Una semana concreta (lunes, YYYY-MM-DD)")
    group.add_argument("--from", dest="week_from", type=_monday, help="Backfill: primera semana (lunes)")
    parser.add_argument("--to", dest="week_to", type=_monday,
                        help="Backfill: última semana (lunes; por defecto, la última cerrada)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return CONFIG_EXIT if exit_request.code else 0
    if args.week_to is not None and args.week_from is None:
        print("Error: --to needs --from.", file=sys.stderr)
        return CONFIG_EXIT

    now = _now()
    if args.week_from is not None:
        weeks = (args.week_from, args.week_to or requested_weeks(RunTrigger.MANUAL, None, now)[1])
    else:
        weeks = requested_weeks(RunTrigger.MANUAL, args.week_start, now)
    try:
        check_weeks(*weeks, now)
    except WeekSelectionError as error:
        print(f"Error: {error}.", file=sys.stderr)
        return CONFIG_EXIT

    try:
        target = resolve_database_target()
    except ConfigError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return CONFIG_EXIT
    print(target.describe())
    repository = PostgresRepository(build_engine(target.url))
    try:
        ready = repository.schema_ready()
    except Exception as error:  # noqa: BLE001  (sin traza: puede llevar la URL)
        print(f"Error: la base de datos no está disponible ({type(error).__name__}).", file=sys.stderr)
        return CONFIG_EXIT
    if not ready:
        print(
            "Error: falta el esquema reporting. Ejecuta antes la migración, desde data/pipelines: "
            "python -m business_performance.migrate (con el venv de data/pipelines).",
            file=sys.stderr,
        )
        return CONFIG_EXIT
    set_repository(repository)

    if args.week_from is not None:
        state = backfill_weekly_office_program_performance(weeks[0], weeks[1], return_state=True)
    else:
        state = weekly_office_program_performance(
            trigger=RunTrigger.MANUAL.value, week_start=weeks[0], return_state=True
        )
    return 0 if state.is_completed() else RUN_FAILED_EXIT


if __name__ == "__main__":
    sys.exit(main())
