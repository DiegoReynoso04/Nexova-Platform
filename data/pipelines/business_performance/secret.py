"""Guarda la URL de la base en el block `Secret` del servidor de Prefect (§4.3 del diseño, D5).

Exige `PREFECT_API_URL` (sin servidor, el block iría a la SQLite efímera). La
URL sale como en el script (D5): `DATABASE_URL` del entorno o, si falta, esa
sola clave del `.env` de la raíz. Imprime solo de dónde salió y el host.

- **Desde el host** (la demo: la URL se queda en el `.env`, nunca en la terminal),
  desde `data/pipelines` con su venv y el servidor del perfil publicado en el 4200:

      $env:PREFECT_API_URL = "http://localhost:4200/api"; .\\.venv\\Scripts\\python -m business_performance.secret

- **Dentro del worker** (el efímero de la guía), pasándole la URL con `-e`:

      docker compose --profile pipelines exec -e DATABASE_URL=… pipeline-worker python -m business_performance.secret

El worker solo usa este block (`pipeline.py`, con `PREFECT_API_URL`).
"""

from . import _bootstrap  # noqa: F401  (antes de Prefect: analítica desactivada)

import os
import sys

from .config import SECRET_BLOCK_NAME, ConfigError, resolve_database_target


def main() -> int:
    if not os.environ.get("PREFECT_API_URL"):
        print("Error: PREFECT_API_URL is required: the block is saved in the Prefect server.", file=sys.stderr)
        return 2
    try:
        target = resolve_database_target()
    except ConfigError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    from prefect.blocks.system import Secret  # noqa: PLC0415

    Secret(value=target.url).save(SECRET_BLOCK_NAME, overwrite=True)
    print(f"Block {SECRET_BLOCK_NAME} guardado. {target.describe()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
