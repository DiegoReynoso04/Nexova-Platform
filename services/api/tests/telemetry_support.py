"""Utilidades de los tests de telemetría: el contrato (`docs/telemetry/`) y su validador.

El validador de draft-07 es el del repositorio (`scripts/validate_event_schemas.py`,
librería estándar): los tests comprueban los eventos con el mismo código que el
plan, sin añadir `jsonschema` como dependencia.
"""

import importlib.util
import json
from functools import cache
from types import ModuleType
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.modules.telemetry.models import TelemetryEventRecord

from .support import REPO_ROOT, make_client

SCHEMA_PATH = REPO_ROOT / "docs" / "telemetry" / "event-schemas.json"
PLAN_PATH = REPO_ROOT / "docs" / "telemetry" / "telemetry-plan.md"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_event_schemas.py"


@cache
def contract() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema


@cache
def validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_event_schemas", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract_errors(event: dict[str, Any]) -> list[str]:
    """Errores del evento contra `event-schemas.json` (raíz y su propia definición)."""
    schema = contract()
    errors: list[str] = validator().validate(event, schema, schema)
    definition = schema["definitions"].get(event.get("event_type"))
    if definition is not None:
        errors += validator().validate(event, definition, schema)
    return errors


def plan_examples() -> list[dict[str, Any]]:
    """Los bloques JSON del plan (52 ejemplos de las fichas + el de §5.2)."""
    plan = PLAN_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    problems, examples = validator().check_plan(plan, contract(), [])
    return [example for example in examples if isinstance(example, dict)]


def envelope(event_type: str = "page_viewed", **overrides: Any) -> dict[str, Any]:
    """Un evento de `page_viewed` válido del frontend, con ids nuevos."""
    event: dict[str, Any] = {
        "eventId": str(uuid4()),
        "timestamp": "2026-11-03T10:00:00.000Z",
        "sessionId": str(uuid4()),
        "userId": str(uuid4()),
        "event_type": event_type,
        "schemaVersion": "1.0.0",
        "requestId": str(uuid4()),
        "properties": {"route_template": "/inventory/products", "previous_route_template": None, "entry": "initial_load"},
    }
    event.update(overrides)
    return event


def storage_client(*, authenticated: bool = False) -> TestClient:
    """Un cliente con `telemetry_events` creada: `init_db` no la crea (D3) y aquí no corre la migración."""
    client = make_client(authenticated=authenticated)
    TelemetryEventRecord.__table__.create(client.app.state.inventory_engine)  # type: ignore[attr-defined]
    return client
