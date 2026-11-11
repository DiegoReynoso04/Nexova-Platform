"""Tests de data/process. Se lanzan desde la raíz con cualquier Python >= 3.11:

    python -m unittest discover -s data/process/tests -t data/process

`nexova_shared` (packages/shared) entra por ruta si no está instalado.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if importlib.util.find_spec("nexova_shared") is None:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "shared"))
PROCESS_DIR = str(REPO_ROOT / "data" / "process")
if PROCESS_DIR not in sys.path:
    sys.path.insert(0, PROCESS_DIR)
