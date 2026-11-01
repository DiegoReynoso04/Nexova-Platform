import logging

# Sin esto, cada petición de la suite imprimiría su línea de timing en stderr
# (app/core/timing.py solo pone su StreamHandler si el logger no tiene ninguno).
# Los registros siguen llegando al raíz, así que capture_logs los ve.
logging.getLogger("api.timing").addHandler(logging.NullHandler())
