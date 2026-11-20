# `task_queue`

Asynchronous task queue for Nexova (ticket DEV-55): Celery, with Redis as both broker and result backend. It is a **library**, like `services/job_runner` and `services/telemetry`: the API imports it to enqueue tasks and read their state, and the `worker` Compose service runs it as a separate process (`celery -A task_queue.celery_app worker`). It never imports FastAPI, the API's `app` package or Prefect (`tests/test_architecture.py`). Analysis and decisions A1–A16: [`docs/async-tasks/analysis.md`](../../docs/async-tasks/analysis.md).

> **Status (F1, stop 1):** Redis, worker and Flower run in Docker with a trivial task, `task_queue.ping`. The dead letter queue, retries and the converted endpoint (`GET /telemetry/report`) come in the next stops.

| Module | What it does |
|---|---|
| `config.py` | `REDIS_URL` (broker on its database, results on the next one; never repeated in an error or `repr`) and the Celery settings of A7: JSON only, `acks_late` + `reject_on_worker_lost`, 600 s visibility timeout, 120/150 s time limits, prefetch 1, results expire after 1 h, `task_track_started`, events for Flower, fast publish failure |
| `celery_app.py` | `create_app(settings)` (no I/O) and the module-level `app` used by the worker and Flower |
| `tasks.py` | Tasks, registered with explicit names (the API sends them by name). Today only `task_queue.ping` → `"pong"` |

## Running it

With the platform (see [`docs/local-development.md`](../../docs/local-development.md)), from the repository root:

```bash
docker compose up -d                       # redis, worker and flower start with the rest
docker compose logs -f worker              # "Connected to redis://:**@redis:6379/0" and "ready"
docker compose exec worker celery -A task_queue.celery_app call task_queue.ping   # prints a task id
docker compose restart worker              # after changing this package (no auto-reload)
docker compose stop worker                 # warm shutdown: waits for running tasks (up to 160 s)
```

Flower: `http://localhost:5555`, with the user and password of `FLOWER_BASIC_AUTH` (root `.env`). Redis and Flower listen only on `127.0.0.1`.

## Tests

With the `services/api` environment (Celery is a dependency of the API). If Windows blocks the venv, in the image, from the root:

```bash
docker run --rm -v "$(pwd):/repo:ro" -w /repo --entrypoint sh nexova-api:latest -c "python -m unittest discover -s services/task_queue/tests -t services"
```

(In Git Bash, prefix `MSYS_NO_PATHCONV=1` and use `$(pwd -W)`.) No test connects to Redis.

> _Spanish version: [README.es.md](./README.es.md)._
