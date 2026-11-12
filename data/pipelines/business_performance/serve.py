"""Worker del perfil `pipelines` de Compose: sirve los dos deployments del flow (§4.4 del diseño).

    python -m business_performance.serve      # desde data/pipelines (en la imagen, el comando del servicio)

- `weekly_office_program_performance/manual`: sin programación; lo dispara
  `POST /reporting/pipeline-runs` (por `trigger.py`) con `trigger = 'manual'`.
- `weekly_office_program_performance/weekly`: cron `0 6 * * 1` en
  `Europe/Madrid` (lunes a las 06:00; D5 del diseño), `trigger = 'schedule'`:
  la última semana cerrada y la anterior.

Concurrencia 1 en cada deployment; entre los dos, manda el índice único parcial
de `pipeline_runs` (una sola corrida `running`). Necesita `PREFECT_API_URL` (el
servidor de Compose) y el block `Secret` `nexova-supabase-database-url`
(`python -m business_performance.secret`).
"""

from . import _bootstrap  # noqa: F401  (antes de Prefect: analítica desactivada y rutas)

import os
import sys

from nexova_shared.reporting import RunTrigger
from prefect import serve
from prefect.schedules import Cron

import pipeline

from .trigger import FLOW_NAME, MANUAL_DEPLOYMENT

WEEKLY_DEPLOYMENT = "weekly"
WEEKLY_CRON = "0 6 * * 1"
WEEKLY_TIMEZONE = "Europe/Madrid"


def build_deployments():
    flow = pipeline.weekly_office_program_performance
    assert flow.name == FLOW_NAME
    manual = flow.to_deployment(
        name=MANUAL_DEPLOYMENT,
        parameters={"trigger": RunTrigger.MANUAL.value},
        concurrency_limit=1,
        description="Disparo manual (POST /reporting/pipeline-runs).",
    )
    weekly = flow.to_deployment(
        name=WEEKLY_DEPLOYMENT,
        schedule=Cron(WEEKLY_CRON, timezone=WEEKLY_TIMEZONE),
        parameters={"trigger": RunTrigger.SCHEDULE.value},
        concurrency_limit=1,
        description="Lunes 06:00 Europe/Madrid: la última semana cerrada y la anterior.",
    )
    return manual, weekly


def main() -> None:
    if not os.environ.get("PREFECT_API_URL"):
        print("Error: PREFECT_API_URL is required (the Prefect server of the pipelines profile).", file=sys.stderr)
        sys.exit(2)
    serve(*build_deployments())


if __name__ == "__main__":
    main()
