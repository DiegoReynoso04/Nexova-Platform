#!/usr/bin/env python
"""Job nocturno de telemetría (ticket DEV-53): exporta el día anterior a CSV y lanza el pipeline.

Un proceso independiente de la API: no importa FastAPI ni `services/api`. Capa fina
sobre `services/job_runner`, que lleva la máquina de estados
`pending → processing → completed | failed` y el lock (el estado `processing`).
Análisis y decisiones M1–M18: `docs/telemetry/nightly-export-analysis.md`.

    python scripts/nightly_export.py            # ayer, en UTC
    TARGET_DATE=2026-10-27 python scripts/nightly_export.py

Se ejecuta con el entorno de `data/pipelines` (su `.venv` o la imagen `nexova-pipeline`):
el pipeline que lanza como subproceso necesita Prefect.

Qué hace, en orden (dentro de `run_job`, que decide si hay que hacerlo):

1. Exporta `telemetry_events` del día (UTC, `[00:00, 24:00)`) a `data/raw/telemetry_YYYY-MM-DD.csv`
   **solo si no existe**, con escritura atómica (`.part` + `os.replace`). Es un backup de
   auditoría y recuperación: el pipeline NO lo lee, lee `telemetry_events` por SQL.
2. Lanza `pipeline.py --week-start <lunes>` con el mismo intérprete, un entorno con lista
   blanca y un timeout de 20 minutos (al vencer se mata el árbol de procesos).

Códigos de salida:

    0  completed, skipped (ya había un completed para ese día) o locked (otra instancia
       procesa: aborta en silencio)
    1  failed: la ejecución falló (la fila queda `failed` con el mensaje)
    2  configuración o entorno, **sin fila**: TARGET_DATE no válida, sin DATABASE_URL, base no
       disponible o esquema `ops` sin migrar (con el comando de la migración)

`TARGET_DATE` (YYYY-MM-DD) es opcional: solo días **cerrados** (anteriores a hoy en UTC) y dentro
de la guarda de retención del pipeline. Sin ella, ayer en UTC.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (REPO_ROOT / "services", REPO_ROOT / "packages" / "shared"):  # no se instalan: van por ruta
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from job_runner import NIGHTLY_EXPORT, JobRunRepository, Outcome, run_job  # noqa: E402
from job_runner.config import ConfigError, build_engine, resolve_database_target  # noqa: E402
from job_runner.logs import JobLogger, configure_logging  # noqa: E402
from job_runner.redact import describe_exception  # noqa: E402
from job_runner.states import QUALIFIED_TABLE, JobStatus  # noqa: E402
from nexova_shared.reporting.weeks import WeekSelectionError, check_weeks, last_closed_week  # noqa: E402
from sqlalchemy import DateTime, bindparam, text  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2

OUTPUT_DIR = REPO_ROOT / "data" / "raw"
PIPELINE_SCRIPT = REPO_ROOT / "data" / "pipelines" / "pipeline.py"
JOB_RUNS_TABLE = QUALIFIED_TABLE
PIPELINE_TIMEOUT_SECONDS = 20 * 60
KILL_GRACE_SECONDS = 10
MIGRATE_COMMAND = "python -m job_runner.migrate (desde services/, con el entorno de data/pipelines)"

# --- CSV: proyección y lista blanca de claves (M10) -------------------------------------------
#
# Sin `user_id` ni `session_id` (seudónimos con 90 días de retención, plan D9: el CSV no tiene
# retención propia). `tags` solo lleva las claves de la lista blanca; una clave que no esté
# aquí no sale nunca. `tests/test_nightly_export_csv.py` exige que esta lista y la de
# exclusiones sean disjuntas y que su unión sea exactamente el conjunto del plan
# (`docs/telemetry/event-schemas.json`).
CSV_COLUMNS = ("event_id", "event_type", "timestamp", "service", "schema_version", "tags")
EXCLUDED_TAG_KEYS = frozenset({"supplier_key", "target_user_id"})
EXPORTABLE_TAG_KEYS = frozenset(
    (
    "account_found", "age_seconds", "analysis_age_seconds", "analysis_id", "api_route_template",
    "asset_category", "attempt_kind", "attempt_number", "authenticated", "available_stock", "boundary",
    "branch", "cache_hit", "categories", "category", "change_pct", "component", "country", "currency",
    "direction", "duration_ms", "entry", "error_class", "error_code", "error_types", "exit_type", "fields",
    "file_size_bucket", "filters", "form", "from_role", "from_status", "had_api_error",
    "had_validation_error", "hits", "http_method", "inbound_order_id", "incident_id", "invalid_records",
    "invalidations", "kind", "last_field", "max_ms", "min_stock", "misses", "namespace", "office",
    "operation", "origin", "outbound_order_id", "outcome", "p50_ms", "p95_ms", "previous_route_template",
    "product_category", "product_id", "programme_id", "quantity", "reason", "reference_unit_cost",
    "reference_window", "request_count", "requested_status", "result_count", "role", "route_template",
    "self_deletion", "session_age_seconds", "status", "status_at_deletion", "status_class", "status_code",
    "stock_after", "stock_before", "store", "supplier_id", "suppressed_count", "threshold_pct", "timeout_ms",
    "to_role", "to_status", "token_ttl_seconds", "total_records", "trigger", "unit_cost", "valid_records",
    "variance_pct", "window_seconds",
    )
)

# --- Subproceso del pipeline (M1–M3) ----------------------------------------------------------
CHILD_ENV_NAMES = frozenset(
    {
        "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "TZ", "LANG", "LC_ALL",
        "PYTHONPATH", "PYTHONUNBUFFERED", "PYTHONIOENCODING", "DO_NOT_TRACK",
    }
)  # + PREFECT_*  + DATABASE_URL (la pone el script: la misma base que el export)
_DATE_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TargetDateError(ValueError):
    """`TARGET_DATE` no válida. Los mensajes no repiten el valor recibido."""


class PipelineError(Exception):
    """El pipeline terminó mal o no terminó. Mensaje fijo: nunca la salida del hijo."""


class TerminatedBySignal(Exception):
    """`SIGTERM` (`docker stop`, reinicio ordenado): la fila debe quedar `failed`."""


def utc_now() -> datetime:
    return datetime.now(UTC)


# --- Fecha objetivo y semana (M2, M16) --------------------------------------------------------


def pipeline_week(target_date: date, now: datetime) -> date:
    """Lunes de la semana que recalcula el pipeline: la de `target_date`, sin pasar de la última cerrada."""
    monday = target_date - timedelta(days=target_date.weekday())
    return min(monday, last_closed_week(now))


def resolve_target_date(raw: str | None, now: datetime) -> date:
    """`TARGET_DATE` validada o, sin ella, ayer en UTC. Lanza `TargetDateError`."""
    today = now.astimezone(UTC).date()
    if raw is None or not raw.strip():
        return today - timedelta(days=1)
    value = raw.strip()
    if not _DATE_FORMAT.match(value):  # `fromisoformat` acepta también 20261015 y 2026-W44-1
        raise TargetDateError("TARGET_DATE must have the format YYYY-MM-DD")
    try:
        target = date.fromisoformat(value)
    except ValueError:
        raise TargetDateError("TARGET_DATE is not a valid calendar date") from None
    if target >= today:
        raise TargetDateError("TARGET_DATE must be a closed day: before today (UTC)")
    week = pipeline_week(target, now)
    try:
        check_weeks(week, week, now)
    except WeekSelectionError:
        raise TargetDateError("TARGET_DATE is outside the retention guard of the pipeline") from None
    return target


# --- CSV (E) ----------------------------------------------------------------------------------


def csv_path(target_date: date, output_dir: Path | None = None) -> Path:
    return (output_dir if output_dir is not None else OUTPUT_DIR) / f"telemetry_{target_date.isoformat()}.csv"


def day_bounds(target_date: date) -> tuple[datetime, datetime]:
    """`[00:00, 24:00)` UTC del día."""
    start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


_EXPORT_SQL = text(
    'SELECT CAST(event_id AS text) AS event_id, event_type, "timestamp", service, schema_version, tags '
    "FROM telemetry_events WHERE \"timestamp\" >= :day_start AND \"timestamp\" < :day_end "
    'ORDER BY "timestamp", event_id'
).bindparams(bindparam("day_start", type_=DateTime(timezone=True)), bindparam("day_end", type_=DateTime(timezone=True)))


def fetch_rows(engine, target_date: date) -> Iterator[Mapping[str, object]]:
    """Las filas del día, de una en una (cursor de servidor): solo `SELECT`, nada se escribe en la base."""
    start, end = day_bounds(target_date)
    with engine.connect().execution_options(stream_results=True) as connection:
        yield from connection.execute(_EXPORT_SQL, {"day_start": start, "day_end": end}).mappings()


def filter_tags(tags: object) -> dict[str, object]:
    """Solo las claves de la lista blanca (nunca una lista negra)."""
    if isinstance(tags, str):
        tags = json.loads(tags)
    if not isinstance(tags, Mapping):
        return {}
    return {key: value for key, value in tags.items() if key in EXPORTABLE_TAG_KEYS}


def csv_record(row: Mapping[str, object]) -> list[str]:
    moment = row["timestamp"]
    if isinstance(moment, datetime):
        moment = (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(UTC).isoformat()
    tags = json.dumps(filter_tags(row["tags"]), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return [str(row["event_id"]), str(row["event_type"]), str(moment), str(row["service"]), str(row["schema_version"]), tags]


def write_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> int:
    """Escribe el CSV completo o nada: `.part` + `fsync` + `os.replace`. Devuelve el número de filas.

    Un fallo a medias deja como mucho el `.part` (que se borra aquí mismo y al empezar el siguiente
    intento): el nombre final no existe hasta que el archivo está completo.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.unlink(missing_ok=True)
    count = 0
    try:
        with part.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(CSV_COLUMNS)
            for row in rows:
                writer.writerow(csv_record(row))
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return count


def export_csv(engine, target_date: date, output_dir: Path | None = None) -> tuple[Path, int | None]:
    """`(ruta, filas)`; `filas` es `None` si el archivo ya existía y no se tocó."""
    path = csv_path(target_date, output_dir)
    if path.exists():
        return path, None
    return path, write_csv(path, fetch_rows(engine, target_date))


# --- Subproceso del pipeline (A.3) ------------------------------------------------------------


def child_environment(database_url: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Lista blanca: nunca `JWT_SECRET_KEY`, `RESEND_API_KEY` ni `TELEMETRY_SUPPLIER_KEY`."""
    source = os.environ if environ is None else environ
    env = {name: value for name, value in source.items() if name in CHILD_ENV_NAMES or name.startswith("PREFECT_")}
    env["DATABASE_URL"] = database_url  # la misma base que el export, aunque saliera del `.env`
    return env


def kill_tree(process: subprocess.Popen) -> None:
    """Mata al hijo **y a sus descendientes** (Prefect lanza su servidor como nieto)."""
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    else:  # el hijo ya salió: puede quedar algún nieto en su grupo
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    try:
        process.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def run_pipeline(week: date, database_url: str, *, timeout: float = PIPELINE_TIMEOUT_SECONDS) -> None:
    """`python pipeline.py --week-start <lunes>` con el mismo intérprete. Lanza `PipelineError` si no sale con 0."""
    command = [sys.executable, str(PIPELINE_SCRIPT), "--week-start", week.isoformat()]
    options: dict[str, object] = {"cwd": str(REPO_ROOT), "env": child_environment(database_url)}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True  # su propio grupo: `killpg` alcanza a los nietos
    process = subprocess.Popen(command, **options)  # stdout y stderr heredados: van al log del contenedor
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        raise PipelineError(f"pipeline timed out after {int(timeout)} s and was killed") from None
    except BaseException:  # SIGTERM convertido en excepción, Ctrl+C
        kill_tree(process)
        raise
    kill_tree(process)  # por si dejó nietos
    if code == 0:
        return
    if code == 1:
        raise PipelineError("pipeline exited with code 1 (run failed; see pipeline_runs and the logs)")
    if code == 2:
        raise PipelineError("pipeline exited with code 2 (configuration, arguments or reporting schema)")
    raise PipelineError(f"pipeline exited with code {code}")


# --- Orquestación -----------------------------------------------------------------------------


def _on_sigterm(signum, frame):  # noqa: ARG001
    raise TerminatedBySignal("terminated by SIGTERM")


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="nightly_export.py",
        description="Exporta la telemetría del día anterior a CSV y lanza el pipeline (DEV-53). "
        "Sin opciones; la fecha se cambia con TARGET_DATE=YYYY-MM-DD.",
        epilog="Salida: 0 completed/skipped/locked; 1 failed; 2 configuración o entorno (sin fila).",
    )


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    try:
        build_parser().parse_args(argv)
    except SystemExit as request:
        return EXIT_CONFIG if request.code else EXIT_OK
    env = os.environ if environ is None else environ
    logger = configure_logging(sys.stdout)
    config_log = JobLogger(logger, NIGHTLY_EXPORT, None)

    now = utc_now()
    try:
        target_date = resolve_target_date(env.get("TARGET_DATE"), now)
    except TargetDateError as error:
        print(f"Error: {error}.", file=sys.stderr)
        config_log.error("rejected", str(error))
        return EXIT_CONFIG
    log = JobLogger(logger, NIGHTLY_EXPORT, target_date)

    try:
        target = resolve_database_target(env)
    except ConfigError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        log.error("rejected", f"configuration error: {error}")
        return EXIT_CONFIG
    log.info("starting", "database", target=target.describe().replace(" ", "_"))

    engine = build_engine(target.url)
    repository = JobRunRepository(engine, JOB_RUNS_TABLE)
    previous_handler = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        try:
            ready = repository.schema_ready()
        except SQLAlchemyError as error:
            print(f"Error: la base de datos no está disponible ({type(error).__name__}).", file=sys.stderr)
            log.error("rejected", f"database unavailable: {describe_exception(error)}")
            return EXIT_CONFIG
        if not ready:
            print(f"Error: falta el esquema ops. Ejecuta antes la migración: {MIGRATE_COMMAND}.", file=sys.stderr)
            log.error("rejected", "schema ops is missing: run the migration first")
            return EXIT_CONFIG

        week = pipeline_week(target_date, now)
        work_log = JobLogger(logger, NIGHTLY_EXPORT, target_date)

        def work() -> None:
            path, rows = export_csv(engine, target_date)
            if rows is None:
                work_log.info(JobStatus.PROCESSING, "csv already exists, export skipped", file=path.name)
            else:
                work_log.info(JobStatus.PROCESSING, "csv written", file=path.name, rows=rows)
            work_log.info(JobStatus.PROCESSING, "pipeline start", week=week.isoformat())
            run_pipeline(week, target.url)
            work_log.info(JobStatus.PROCESSING, "pipeline finished", week=week.isoformat())

        try:
            result = run_job(repository, NIGHTLY_EXPORT, target_date, work, logger=logger)
        except SQLAlchemyError as error:
            log.error("rejected", f"database error before the run could start: {describe_exception(error)}")
            return EXIT_CONFIG
        except KeyboardInterrupt:
            return EXIT_FAILED  # la fila ya quedó `failed`
        return EXIT_FAILED if result.outcome is Outcome.FAILED else EXIT_OK
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
