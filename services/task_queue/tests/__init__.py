"""Tests de task_queue. Sin Redis: nada conecta con el broker.

`task_queue.celery_app` lee `REDIS_URL` al importarse; aquí se fija una URL de
prueba (nunca se usa para conectar) antes de que ningún test lo importe.
"""

import os

os.environ.setdefault("REDIS_URL", "redis://:unit-test-password@localhost:6399/0")
