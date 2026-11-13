"""Fixtures de `tests/pipelines/test_pipeline.py`: rutas del monorepo y datos ficticios con la forma de `telemetry_events`.

Sin `__init__.py` en `tests/` ni en `tests/pipelines/` (a propósito): con él, `tests` sería un
paquete que choca con `data/pipelines/tests` (`from tests.support import ...`) y rompería sus
tests. Sin una configuración de pytest en la raíz, el comando lleva la ruta explícita:

    python -m pytest tests/pipelines/test_pipeline.py

Los tests llaman a las tasks con `.fn`: la función de Python, sin motor, sin servidor de Prefect,
sin base de datos y sin red. Prefect tiene que estar instalado (el venv de `data/pipelines` o la
imagen `nexova-pipeline:dev`), porque `pipeline.py` lo importa.
"""

import sys
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Primero el código del repo: en la imagen, el PYTHONPATH apunta a una copia que puede ser más vieja.
for _path in (ROOT / "packages" / "shared", ROOT / "data" / "process", ROOT / "data" / "pipelines"):
    if str(_path) in sys.path:
        sys.path.remove(str(_path))
    sys.path.insert(0, str(_path))

import pipeline  # noqa: E402
from weekly_performance import ExtractedEvent, QualityCounts, TransformResult, TransformStats  # noqa: E402

CURRENCY = {"valencia": "EUR", "miami": "USD"}
# Solo el inbound y la variación llevan `inbound_order_id`; la salida y la escasez, `outbound_order_id`.
INBOUND_ID_EVENTS = {"inbound_order_created", "kit_cost_variance_detected"}


@pytest.fixture(scope="session", autouse=True)
def code_under_test_is_the_repo() -> None:
    """Falla alto si `pipeline` o `weekly_performance` salen de otra copia (p. ej. la de la imagen)."""
    import weekly_performance  # noqa: PLC0415

    for module in (pipeline, weekly_performance):
        assert Path(module.__file__).resolve().is_relative_to(ROOT), f"{module.__name__} no sale del repositorio"


@pytest.fixture
def telemetry_row() -> Callable[..., dict]:
    """Una fila con las columnas de `telemetry_events` (`event_id`, `event_type`, `timestamp`, `service`,
    `schema_version`, `tags`). Los valores de `tags` van como en el JSONB: números donde la allowlist los
    declara numéricos. Datos ficticios: ningún programa, orden ni persona reales."""

    def build(event_type: str, *, at: datetime, order_id: int, office: str = "valencia",
              programme_id: str | None = None, quantity: int = 1, unit_cost: float | None = None) -> dict:
        tags = {
            "office": office,
            "programme_id": programme_id,
            "currency": CURRENCY[office],
            "quantity": quantity,
            "unit_cost": unit_cost,
            ("inbound_order_id" if event_type in INBOUND_ID_EVENTS else "outbound_order_id"): order_id,
        }
        return {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": at,
            "service": "api",
            "schema_version": "1.0.0",
            "tags": {key: value for key, value in tags.items() if value is not None or key == "programme_id"},
        }

    return build


def _text(value: object) -> str | None:
    return None if value is None else str(value)


@pytest.fixture
def extracted() -> Callable[[Iterable[dict]], list[ExtractedEvent]]:
    """La proyección de `extract_business_events` (§2.3 del diseño): `tags->>'clave'` como texto y
    `COALESCE(tags->>'inbound_order_id', tags->>'outbound_order_id')` como `order_id`."""

    def project(rows: Iterable[dict]) -> list[ExtractedEvent]:
        events = []
        for row in rows:
            tags = row["tags"]
            order_id = tags.get("inbound_order_id", tags.get("outbound_order_id"))
            events.append(ExtractedEvent(
                event_id=row["event_id"],
                event_type=row["event_type"],
                timestamp=row["timestamp"],
                office=_text(tags.get("office")),
                programme_id=_text(tags.get("programme_id")),
                currency=_text(tags.get("currency")),
                quantity=_text(tags.get("quantity")),
                unit_cost=_text(tags.get("unit_cost")),
                order_id=_text(order_id),
            ))
        return events

    return project


@pytest.fixture
def transform_with_tasks() -> Callable[..., TransformResult]:
    """La cadena de `transform_weekly_kpis` con las tasks llamadas por `.fn` (sin servidor de Prefect)."""

    def run(events: list[ExtractedEvent], week_from: date, week_to: date | None = None,
            quality: QualityCounts | None = None) -> TransformResult:
        week_to = week_to or week_from
        typed = pipeline.type_and_validate_events.fn(events, week_from, week_to)
        deduped = pipeline.collapse_duplicate_orders.fn(typed.items)
        kept = deduped.items
        return pipeline.assemble_weekly_rows.fn(
            kept,
            pipeline.compute_total_material_cost.fn(kept),
            pipeline.compute_kits_delivered_count.fn(kept),
            pipeline.compute_shortage_events_count.fn(kept),
            pipeline.compute_cost_variance_events_count.fn(kept),
            TransformStats(len(events), typed.rejected, deduped.duplicates_collapsed),
            quality or QualityCounts(),
            week_from,
            week_to,
        )

    return run

