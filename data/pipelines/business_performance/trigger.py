"""Disparo manual del pipeline por la API REST de Prefect. **Solo librería estándar.**

La API (`services/reporting`, `POST /reporting/pipeline-runs`) importa
`request_manual_run` de aquí, y no el objeto flow, por dos motivos (D2 del
análisis): Prefect no está instalado en la API (D1: entorno propio de
`data/pipelines`), y un flow ejecutado dentro de la API moriría con cada
recarga de su `--reload` y ocuparía su único worker. Esta función solo **pide**
el flow run al servidor de Prefect; lo ejecuta el `pipeline-worker`
(`serve.py`), fuera de la API.

Pasos: (1) el deployment `weekly_office_program_performance/manual` por nombre;
(2) si ya tiene un flow run activo (`SCHEDULED`, `PENDING` o `RUNNING`) →
`RunAlreadyActiveError`; (3) `POST /deployments/{id}/create_flow_run` con los
parámetros del flow. El flow vuelve a comprobarlo en `start_run` (el índice
único parcial de `pipeline_runs` manda) y el deployment tiene concurrencia 1.

Cualquier fallo de red, de HTTP o de formato → `PipelineUnavailableError`
(la API responde 503 `pipeline_unavailable`). Los mensajes nunca llevan la URL.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

# Deben coincidir con `nexova_shared.reporting.PIPELINE_NAME` y con `serve.py`
# (lo comprueban los tests); aquí van en literal para no importar nada fuera de
# la librería estándar.
FLOW_NAME = "weekly_office_program_performance"
MANUAL_DEPLOYMENT = "manual"
MANUAL_TRIGGER = "manual"
ACTIVE_STATE_TYPES = ("SCHEDULED", "PENDING", "RUNNING")
DEFAULT_TIMEOUT_SECONDS = 5.0

Opener = Callable[..., Any]


class PipelineUnavailableError(Exception):
    """El servidor de Prefect no responde, no tiene el deployment o respondió algo inesperado."""


class RunAlreadyActiveError(Exception):
    """El deployment manual ya tiene un flow run programado, pendiente o en marcha."""


@dataclass(frozen=True, slots=True)
class TriggeredRun:
    prefect_flow_run_id: UUID
    status: str = "scheduled"


def _request(opener: Opener, method: str, url: str, body: dict | None, timeout: float) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    try:
        with opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        # HTTPError es una URLError: 404 (sin deployment), 5xx, etc. Solo la clase.
        raise PipelineUnavailableError(type(error).__name__) from None


def request_manual_run(
    api_url: str,
    *,
    week_start: date | None = None,
    requested_by: UUID | str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    opener: Opener = urllib.request.urlopen,
) -> TriggeredRun:
    """Crea un flow run del deployment manual. Devuelve su id (estado `scheduled`)."""
    base = api_url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise PipelineUnavailableError("invalid Prefect API URL")

    path = f"/deployments/name/{urllib.parse.quote(FLOW_NAME)}/{urllib.parse.quote(MANUAL_DEPLOYMENT)}"
    deployment = _request(opener, "GET", base + path, None, timeout)
    try:
        deployment_id = str(UUID(str(deployment["id"])))
    except (KeyError, TypeError, ValueError):
        raise PipelineUnavailableError("unexpected deployment response") from None

    active_filter = {
        "flow_runs": {
            "deployment_id": {"any_": [deployment_id]},
            "state": {"type": {"any_": list(ACTIVE_STATE_TYPES)}},
        },
        "limit": 1,
    }
    active = _request(opener, "POST", base + "/flow_runs/filter", active_filter, timeout)
    if not isinstance(active, list):
        raise PipelineUnavailableError("unexpected flow run filter response")
    if active:
        raise RunAlreadyActiveError()

    parameters = {
        "trigger": MANUAL_TRIGGER,
        "week_start": week_start.isoformat() if week_start is not None else None,
        "requested_by": str(requested_by) if requested_by is not None else None,
    }
    created = _request(
        opener, "POST", f"{base}/deployments/{deployment_id}/create_flow_run", {"parameters": parameters}, timeout
    )
    try:
        return TriggeredRun(prefect_flow_run_id=UUID(str(created["id"])))
    except (KeyError, TypeError, ValueError):
        raise PipelineUnavailableError("unexpected flow run response") from None
