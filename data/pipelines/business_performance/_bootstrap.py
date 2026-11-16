"""Arranque común del pipeline: analítica de Prefect desactivada, timeout de arranque del servidor efímero y rutas del monorepo.

Lo importan, **antes que Prefect**, `pipeline.py`, `serve.py` y los módulos
que lo necesitan (`repository.py`, `migrate.py`). `trigger.py` no: es lo único
del paquete que importa la API y solo usa la librería estándar.

**Analítica:** Prefect 3.9.2 tiene dos interruptores distintos y los dos se
fuerzan aquí (no `setdefault`: el entorno no puede reactivarlos):

- `PREFECT_SERVER_ANALYTICS_ENABLED=false`: la del servidor (también la del
  servidor temporal que arranca el script, que hereda el entorno).
- `DO_NOT_TRACK=1`: la del cliente (SDK). Sin ella, al importar Prefect en una
  terminal interactiva aparece el aviso «Prefect collects anonymous usage
  data…» antes de que el cliente compruebe el ajuste del servidor
  (`prefect/_internal/analytics/__init__.py`, `initialize_analytics`).

La imagen (`data/Dockerfile`) y Compose fijan las mismas dos variables; lo
comprueba `tests/test_analytics_off.py`.

**Timeout del servidor efímero (`setdefault`, esta sí se respeta):** sin
`PREFECT_API_URL`, Prefect arranca un servidor en un subproceso y espera a que
responda `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS` segundos, **20 por
defecto** (`prefect/settings/models/server/ephemeral.py`; el bucle de espera,
en `prefect/server/api/server.py`, lanza «Timed out while attempting to connect
to ephemeral Prefect API server»). El arranque tarda 18–21 s en una máquina
normal, así que con 20 s el job nocturno fallaba al azar. Aquí se fija a 90 s
solo si el entorno no trae ya la variable. Como este módulo se importa antes
que Prefect en `pipeline.py`, vale a mano, en el subproceso del job nocturno
(la variable pasa su lista blanca de entorno por el prefijo `PREFECT_`) y en
el contenedor `nightly-scheduler`, sin tocar Compose ni la imagen. Lo comprueba
`tests/test_ephemeral_timeout.py`.

**Rutas:** `nexova_shared` (packages/shared) y `weekly_performance`
(data/process) no se instalan (no están publicados). En la imagen entran por
`PYTHONPATH`; desde el host se añaden a `sys.path` si no se importan ya.
"""

import importlib.util
import os
import sys
from pathlib import Path

ANALYTICS_OFF = {"DO_NOT_TRACK": "1", "PREFECT_SERVER_ANALYTICS_ENABLED": "false"}
os.environ.update(ANALYTICS_OFF)

EPHEMERAL_STARTUP_TIMEOUT_VARIABLE = "PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS"
EPHEMERAL_STARTUP_TIMEOUT_SECONDS = "90"
os.environ.setdefault(EPHEMERAL_STARTUP_TIMEOUT_VARIABLE, EPHEMERAL_STARTUP_TIMEOUT_SECONDS)

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 3:
    _REPO_ROOT = _HERE.parents[3]
    for _module, _path in (
        ("nexova_shared", _REPO_ROOT / "packages" / "shared"),
        ("weekly_performance", _REPO_ROOT / "data" / "process"),
    ):
        if importlib.util.find_spec(_module) is None and _path.is_dir():
            sys.path.insert(0, str(_path))
