import logging
import sys
from pathlib import Path

# services/telemetry (el análisis del reporte) se importa como `telemetry`: en la
# imagen está junto a `app`, y aquí hace falta `services/` en la ruta. Vale para
# unittest y pytest, que importan este paquete antes que cualquier test.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Sin esto, cada petición de la suite imprimiría su línea de timing en stderr
# (app/core/timing.py solo pone su StreamHandler si el logger no tiene ninguno).
# Los registros siguen llegando al raíz, así que capture_logs los ve.
logging.getLogger("api.timing").addHandler(logging.NullHandler())
