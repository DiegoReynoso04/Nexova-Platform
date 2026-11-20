# `task_queue`

Cola de tareas asíncronas de Nexova (ticket DEV-55): Celery, con Redis como broker y como result backend. Es una **biblioteca**, como `services/job_runner` y `services/telemetry`: la API la importa para encolar tareas y leer su estado, y el servicio `worker` de Compose la ejecuta como un proceso aparte (`celery -A task_queue.celery_app worker`). Nunca importa FastAPI, el paquete `app` de la API ni Prefect (`tests/test_architecture.py`). Análisis y decisiones A1–A16: [`docs/async-tasks/analysis.md`](../../docs/async-tasks/analysis.md).

> **Estado (F1, parada 1):** Redis, el worker y Flower corren en Docker con una tarea trivial, `task_queue.ping`. La dead letter queue, los reintentos y el endpoint convertido (`GET /telemetry/report`) llegan en las paradas siguientes.

| Módulo | Qué hace |
|---|---|
| `config.py` | `REDIS_URL` (el broker en su base y los resultados en la siguiente; nunca se repite en un error ni en `repr`) y los ajustes de Celery de A7: solo JSON, `acks_late` + `reject_on_worker_lost`, visibilidad de 600 s, límites de 120/150 s, prefetch 1, resultados que caducan a la hora, `task_track_started`, eventos para Flower y fallo rápido al publicar |
| `celery_app.py` | `create_app(settings)` (sin E/S) y la instancia `app` del módulo, la que usan el worker y Flower |
| `tasks.py` | Las tareas, registradas con nombre explícito (la API las envía por nombre). Hoy solo `task_queue.ping` → `"pong"` |

## Arranque

Con la plataforma (ver [`docs/local-development.md`](../../docs/local-development.md)), desde la raíz del repositorio:

```bash
docker compose up -d                       # redis, worker y flower arrancan con el resto
docker compose logs -f worker              # «Connected to redis://:**@redis:6379/0» y «ready»
docker compose exec worker celery -A task_queue.celery_app call task_queue.ping   # imprime el id de la tarea
docker compose restart worker              # tras cambiar este paquete (no recarga solo)
docker compose stop worker                 # parada en caliente: espera a las tareas en curso (hasta 160 s)
```

Flower: `http://localhost:5555`, con el usuario y la contraseña de `FLOWER_BASIC_AUTH` (`.env` de la raíz). Redis y Flower solo escuchan en `127.0.0.1`.

## Tests

Con el entorno de `services/api` (Celery es una dependencia de la API). Si Windows bloquea el venv, en la imagen, desde la raíz:

```bash
docker run --rm -v "$(pwd):/repo:ro" -w /repo --entrypoint sh nexova-api:latest -c "python -m unittest discover -s services/task_queue/tests -t services"
```

(En Git Bash, con `MSYS_NO_PATHCONV=1` delante y `$(pwd -W)`.) Ningún test conecta con Redis.

> _Versión en inglés: [README.md](./README.md)._
