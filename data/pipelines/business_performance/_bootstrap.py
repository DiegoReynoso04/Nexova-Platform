"""Arranque común del pipeline: analítica de Prefect desactivada y rutas del monorepo.

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

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 3:
    _REPO_ROOT = _HERE.parents[3]
    for _module, _path in (
        ("nexova_shared", _REPO_ROOT / "packages" / "shared"),
        ("weekly_performance", _REPO_ROOT / "data" / "process"),
    ):
        if importlib.util.find_spec(_module) is None and _path.is_dir():
            sys.path.insert(0, str(_path))
