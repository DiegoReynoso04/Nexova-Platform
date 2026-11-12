"""Tests de data/pipelines. Desde la raíz, con el venv de data/pipelines:

    data\\pipelines\\.venv\\Scripts\\python -m unittest discover -s data/pipelines/tests -t data/pipelines

Los resultados de Prefect de la suite van a una carpeta temporal (nunca a
data/raw) y el servidor es el de `prefect_test_harness` (SQLite temporal).
"""

import os
import sys
import tempfile
from pathlib import Path

PIPELINES_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINES_DIR))

# Antes de que nada importe Prefect o pipeline.py.
_RESULTS_DIR = tempfile.mkdtemp(prefix="nexova-pipeline-test-results-")
os.environ["PREFECT_LOCAL_STORAGE_PATH"] = _RESULTS_DIR
os.environ.pop("PREFECT_API_URL", None)

# Analítica de Prefect desactivada (servidor y cliente) y rutas del monorepo,
# antes de que ningún test importe Prefect (tests/test_analytics_off.py).
from business_performance import _bootstrap  # noqa: E402,F401
