"""Worker del perfil `pipelines` de Compose: sirve el deployment `manual` del flow (§4.4 del diseño).

    python -m business_performance.serve      # desde data/pipelines (en la imagen, el comando del servicio)

- `weekly_office_program_performance/manual`: sin programación; lo dispara
  `POST /reporting/pipeline-runs` (por `trigger.py`) con `trigger = 'manual'`.

**Ya no hay deployment programado (DEV-53, 2026-11-16).** El cron semanal
(`weekly`, lunes 06:00 `Europe/Madrid`) se quitó: la programación pasó al job
nocturno `scripts/nightly_export.py` (perfil `nightly` de Compose), que lanza este
mismo pipeline cada noche y es el único disparador programado. Motivo: el
nocturno recalcula la misma semana con datos más frescos y no depende de este
servidor de Prefect; dos disparadores del mismo cálculo se habrían pisado.
Ver `docs/telemetry/nightly-export-analysis.md` (A.4, M5).

Concurrencia 1 en el deployment; manda además el índice único parcial de
`pipeline_runs` (una sola corrida `running`). Necesita `PREFECT_API_URL` (el
servidor de Compose) y el block `Secret` `nexova-supabase-database-url`
(`python -m business_performance.secret`).
"""

from . import _bootstrap  # noqa: F401  (antes de Prefect: analítica desactivada y rutas)

import os
import sys

from nexova_shared.reporting import RunTrigger
from prefect import serve

import pipeline

from .trigger import FLOW_NAME, MANUAL_DEPLOYMENT


def build_deployments():
    flow = pipeline.weekly_office_program_performance
    assert flow.name == FLOW_NAME
    manual = flow.to_deployment(
        name=MANUAL_DEPLOYMENT,
        parameters={"trigger": RunTrigger.MANUAL.value},
        concurrency_limit=1,
        description="Disparo manual (POST /reporting/pipeline-runs).",
    )
    return (manual,)


def main() -> None:
    if not os.environ.get("PREFECT_API_URL"):
        print("Error: PREFECT_API_URL is required (the Prefect server of the pipelines profile).", file=sys.stderr)
        sys.exit(2)
    serve(*build_deployments())


if __name__ == "__main__":
    main()
