"""Métricas técnicas de `telemetry_events` con Pandas (ticket del reporte técnico).

Cada métrica es una función independiente y sin efectos secundarios, con la misma
fórmula, marcada con un comentario por paso:

    1. cargar (SQL)   el rango de `timestamp` y `event_type`; nunca la tabla entera
    2. refinar        las dimensiones de `tags`, sin los nulos
    3. convertir      `pd.to_datetime(..., utc=True)` antes de cualquier `groupby`
    4. agrupar
    5. agregar
    6. servir         una lista de dicts lista para JSON

`start` (inclusivo) y `end` (exclusivo) llegan resueltos y en UTC: aquí no hay
ventana propia. Los días son días UTC. No se usa ningún bucle: solo operaciones de
Pandas, y lo comprueba `tests/test_telemetry_analysis.py`.

Sin redondeo: la API devuelve las tasas con todos sus decimales y formatea quien
presenta (D11 de docs/telemetry/report-analysis.md).

Solo técnico: ninguna función lee una dimensión de negocio de `tags` (`office`,
`product_id`, `quantity`, `currency`…) ni carga `user_id`, `session_id` o `event_id`.
Los eventos de negocio cuentan como filas en `events_per_day` y en
`dominant_event_types`, y sus `tags` ni se cargan (D7).
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import Column, Connection, select

from app.modules.telemetry.models import TelemetryEventRecord, TelemetryService

EVENTS = TelemetryEventRecord.__table__.c  # type: ignore[attr-defined]
SERVICES = list(map(str, TelemetryService))
DAY_FORMAT = "%Y-%m-%d"

# Los 15 eventos que llegan a la tabla menos los 4 de negocio del frontend.
TECHNICAL_EVENT_TYPES = (
    "client_request_failed",
    "direct_stock_edit_rejected",
    "form_abandoned",
    "form_started",
    "form_submitted",
    "form_validation_failed",
    "frontend_error_captured",
    "page_load_recorded",
    "page_not_found_viewed",
    "page_viewed",
    "user_logged_out",
)
# Eventos en los que el error depende de `tags.outcome`.
OUTCOME_EVENT_TYPES = ("form_submitted", "page_load_recorded")
# `system`: falló la plataforma. `rejected`: el sistema funcionó y dijo que no (D3).
ERROR_CLASSES: Mapping[str, str] = {
    "client_request_failed": "system",
    "frontend_error_captured": "system",
    "page_load_recorded:error": "system",
    "form_submitted:network_error": "system",
    "form_submitted:server_error": "system",
    "form_submitted:api_rejected": "rejected",
    "form_submitted:validation_error": "rejected",
    "form_submitted:session_expired": "rejected",
    "form_validation_failed": "rejected",
    "page_not_found_viewed": "rejected",
    "direct_stock_edit_rejected": "rejected",
}
LOGIN_FORM = "login"
LOGIN_FAILED = "api_rejected"
LOGIN_SUCCEEDED = "success"


def _load(
    connection: Connection,
    start: datetime,
    end: datetime,
    *columns: Column[Any],
    event_types: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Las columnas pedidas de la ventana. `select` tipado: `tags` llega como `dict` en las dos bases."""
    statement = select(*columns).where(EVENTS.timestamp >= start, EVENTS.timestamp < end)
    if event_types is not None:
        statement = statement.where(EVENTS.event_type.in_(event_types))
    return pd.read_sql(statement, connection)


def _with_tags(frame: pd.DataFrame, *keys: str) -> pd.DataFrame:
    """`frame` sin `tags` y con esas claves como columnas. `reindex`: existen aunque no haya filas."""
    tags = pd.DataFrame(frame["tags"].tolist(), index=frame.index).reindex(columns=list(keys))
    return frame.drop(columns="tags").join(tags)


def events_per_day(connection: Connection, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """¿Llega telemetría cada día, y de quién? Un día a 0 es un colector caído.

    A diferencia del resto, devuelve siempre todos los días del periodo y todos
    los `service`, a 0 si no hay filas: es justo lo que esta métrica vigila.
    """
    # 1. cargar (SQL)
    frame = _load(connection, start, end, EVENTS.timestamp, EVENTS.service)
    # 2. refinar (Pandas)
    frame = frame.dropna(subset=["timestamp", "service"])
    # 3. convertir tipos
    frame["day"] = pd.to_datetime(frame["timestamp"], utc=True).dt.floor("D")
    # 4. agrupar
    grouped = frame.groupby(["day", "service"])
    # 5. agregar
    counts = grouped.size().rename("events")
    # El día de `end` no entra si `end` es justo su medianoche: fin exclusivo.
    days = pd.date_range(pd.Timestamp(start).floor("D"), pd.Timestamp(end), freq="D", inclusive="left")
    period = pd.MultiIndex.from_product([days, SERVICES], names=["day", "service"])
    counts = counts.reindex(period, fill_value=0)
    # 6. servir
    report = counts.reset_index()
    report["day"] = report["day"].dt.strftime(DAY_FORMAT)
    return report.to_dict(orient="records")


def error_rate_by_type(connection: Connection, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """¿Qué falla, cuánto pesa, y es el sistema o el usuario?

    `error_rate` es la proporción de eventos técnicos del día que son ese error,
    no de peticiones: las correctas no se emiten (D4). Una fila con throttle vale
    `1 + suppressed_count` (C17).
    """
    # 1. cargar (SQL)
    frame = _load(connection, start, end, EVENTS.timestamp, EVENTS.event_type, EVENTS.tags, event_types=TECHNICAL_EVENT_TYPES)
    # 2. refinar (Pandas)
    frame = _with_tags(frame, "outcome", "suppressed_count").dropna(subset=["timestamp", "event_type"])
    # 3. convertir tipos
    frame["day"] = pd.to_datetime(frame["timestamp"], utc=True).dt.strftime(DAY_FORMAT)
    frame["occurrences"] = 1 + pd.to_numeric(frame["suppressed_count"]).fillna(0).astype("int64")
    frame["outcome"] = frame["outcome"].astype("string")
    frame["event_type"] = frame["event_type"].astype("string")
    # 4. agrupar
    by_outcome = frame["event_type"].isin(OUTCOME_EVENT_TYPES)
    frame["error_type"] = frame["event_type"].where(~by_outcome, frame["event_type"] + ":" + frame["outcome"])
    frame["error_class"] = frame["error_type"].map(ERROR_CLASSES)
    totals = frame.groupby("day")["occurrences"].sum().rename("total_events")
    grouped = frame.dropna(subset=["error_class"]).groupby(["day", "error_type", "error_class"])["occurrences"]
    # 5. agregar
    errors = grouped.sum().rename("errors")
    # 6. servir
    report = errors.reset_index().join(totals, on="day")
    report["error_rate"] = report["errors"] / report["total_events"]
    return report.to_dict(orient="records")


def page_load_latency_by_route(connection: Connection, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """¿En qué sección esperan más los operadores a ver los datos?

    Mide la espera en el navegador, no la latencia de la API: `api_latency_recorded`
    aún no se emite. `outcome` agrupa para no mezclar el tiempo de un fallo con el
    de una carga correcta.
    """
    # 1. cargar (SQL)
    frame = _load(connection, start, end, EVENTS.timestamp, EVENTS.tags, event_types=("page_load_recorded",))
    # 2. refinar (Pandas)
    frame = _with_tags(frame, "route_template", "duration_ms", "outcome").dropna(subset=["route_template", "duration_ms", "outcome"])
    # 3. convertir tipos
    frame["day"] = pd.to_datetime(frame["timestamp"], utc=True).dt.strftime(DAY_FORMAT)
    frame["duration_ms"] = pd.to_numeric(frame["duration_ms"])
    # 4. agrupar
    grouped = frame.groupby(["day", "route_template", "outcome"])["duration_ms"]
    # 5. agregar
    latency = grouped.agg(loads="count", avg_ms="mean", max_ms="max")
    # 6. servir
    return latency.reset_index().to_dict(orient="records")


def dominant_event_types(connection: Connection, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """¿Qué tipos ocupan la tabla y el cupo del colector? De mayor a menor."""
    # 1. cargar (SQL)
    frame = _load(connection, start, end, EVENTS.timestamp, EVENTS.event_type, EVENTS.service)
    # 2. refinar (Pandas)
    frame = frame.dropna(subset=["timestamp", "event_type", "service"])
    # 3. convertir tipos (la misma conversión que en las demás, aunque aquí el tiempo no agrupa)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    # 4. agrupar
    grouped = frame.groupby(["event_type", "service"])
    # 5. agregar
    counts = grouped.size().rename("events")
    # 6. servir
    report = counts.reset_index()
    report["share"] = report["events"] / report["events"].sum()
    report = report.sort_values(["events", "event_type", "service"], ascending=[False, True, True])
    return report.reset_index(drop=True).to_dict(orient="records")


def auth_failure_rate(connection: Connection, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """¿Cuántos logins fallan al día desde el backoffice?

    `failed / (failed + succeeded)` con `form_submitted`: `login_failed` y
    `user_logged_in` aún no se emiten (D6). Una red o un servidor caídos no son un
    intento: salen en `error_rate_by_type`. Solo ve lo que pasa por el navegador.
    """
    # 1. cargar (SQL)
    frame = _load(connection, start, end, EVENTS.timestamp, EVENTS.tags, event_types=("form_submitted",))
    # 2. refinar (Pandas)
    frame = _with_tags(frame, "form", "outcome").dropna(subset=["form", "outcome"])
    frame = frame[frame["form"].eq(LOGIN_FORM) & frame["outcome"].isin((LOGIN_FAILED, LOGIN_SUCCEEDED))]
    # 3. convertir tipos
    frame = frame.assign(
        day=pd.to_datetime(frame["timestamp"], utc=True).dt.strftime(DAY_FORMAT),
        failed=frame["outcome"].eq(LOGIN_FAILED).astype("int64"),
        succeeded=frame["outcome"].eq(LOGIN_SUCCEEDED).astype("int64"),
    )
    # 4. agrupar
    grouped = frame.groupby("day")
    # 5. agregar
    logins = grouped.agg(failed=("failed", "sum"), succeeded=("succeeded", "sum"), attempts=("outcome", "count"))
    # 6. servir
    report = logins.reset_index()
    report["failure_rate"] = report["failed"] / report["attempts"]
    return report.to_dict(orient="records")


def all_metrics(connection: Connection, start: datetime, end: datetime) -> dict[str, list[dict[str, Any]]]:
    """Las métricas del reporte, todas sobre el mismo periodo."""
    return {
        "events_per_day": events_per_day(connection, start, end),
        "error_rate_by_type": error_rate_by_type(connection, start, end),
        "page_load_latency_by_route": page_load_latency_by_route(connection, start, end),
        "dominant_event_types": dominant_event_types(connection, start, end),
        "auth_failure_rate": auth_failure_rate(connection, start, end),
    }
