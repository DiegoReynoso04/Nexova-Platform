# `task_queue`

Asynchronous task queue for Nexova (ticket DEV-55): Celery, with Redis as both broker and result backend. It is a **library**, like `services/job_runner` and `services/telemetry`: the API imports it to enqueue tasks and read their state, and the `worker` Compose service runs it as a separate process (`celery -A task_queue.celery_app worker`). It never imports FastAPI, the API's `app` package or Prefect (`tests/test_architecture.py`). It reuses `job_runner` for error redaction and the `DATABASE_URL` rules. Analysis and decisions A1–A16: [`docs/async-tasks/analysis.md`](../../docs/async-tasks/analysis.md).

> **Status (F1, stop 2):** Redis, worker and Flower run in Docker; every task gets retries with backoff, the dead letter queue and one log line per execution. The converted endpoint (`GET /telemetry/report`) comes in stop 3.

| Module | What it does |
|---|---|
| `config.py` | `REDIS_URL` (broker on its database, results on the next one; never repeated in an error or `repr`), the Celery settings of A7 and the constants of A8/A9 |
| `celery_app.py` | `create_app(settings)` (no I/O) and the module-level `app` used by the worker and Flower. `task_cls` is `base.ReliableTask` |
| `base.py` | `ReliableTask`: logs `started`; on a transient error (`errors.RETRYABLE_EXCEPTIONS`: SQLAlchemy `OperationalError`, `InterfaceError`, `TimeoutError`) retries with `retries.backoff_countdown`; otherwise, or after `max_retries=3` (4 executions), logs `dead_letter`, records the row and raises `TaskFailedError` (redacted). `DeadLetterRequest` records hard time limits from the worker's main process |
| `retries.py` | `base · 2^n + uniform(0, base)`, base 2 s: 2–4, 4–6 and 8–10 s. Never below `base · 2^n` (Celery's own full jitter can return 0 s) |
| `dead_letters.py` | `ops.task_dead_letters` (`attempt` = `retries` + 1, unique `task_id`), `DeadLetterRepository` and `record_dead_letter`: one short retry, then an `ERROR` line with every field (`status=dead_letter_not_stored`) if the database is down or the table is missing |
| `redaction.py` | `describe_failure` (SQLAlchemy errors: classes only; others: `Class: message` without URLs or secret values, ≤ 2000 chars) and the logging filter on `celery.app.trace`, `celery.worker.request` and `task_queue` |
| `database.py` | `DATABASE_URL` from the environment only, one `NullPool` engine per process, `SET LOCAL statement_timeout` per transaction |
| `logs.py` | `task_id=… task=… attempt=2/4 status=retry duration_ms=… countdown_s=… error="…"` |
| `migrate.py` | `python -m task_queue.migrate [--dry-run] [--allow-demo]` (from `services/`) |
| `tasks.py` | Tasks, registered with explicit names. Today only `task_queue.ping` → `"pong"` |

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

**The worker's `DATABASE_URL` comes from the root `.env`: the demo, like the API.** It only writes to `ops.task_dead_letters`, which does not exist in the demo until the user migrates it; until then a final failure stays in the log only.

## Migration

Never at startup. Against a local test database (never the demo without the user's confirmation):

```bash
cd services
python -m task_queue.migrate --dry-run   # prints the pending SQL
python -m task_queue.migrate             # applies it in one transaction; the second time, "Nada que migrar"
```

It creates `ops` only if missing and shares it with `job_runner.migrate` (either order works). RLS without policies and `REVOKE ALL` from `PUBLIC` and Supabase's roles. A non-local database needs `--allow-demo`.

## Tests

With the `services/api` environment, from the root:

```bash
services/api/.venv/bin/python -m unittest discover -s services/task_queue/tests -t services   # Windows: services\api\.venv\Scripts\python
```

Without more variables, only the unit tests run (no Redis, no PostgreSQL). With `TASK_QUEUE_TEST_DATABASE_URL` (local PostgreSQL whose database ends in `_test`; **drops and recreates `ops`**) and `TASK_QUEUE_TEST_REDIS_URL` (local Redis; flushes the two databases it uses), the integration tests run too: the migration against PostgreSQL in both orders with `job_runner`, and a real `prefork` worker (`tests/integration_app.py`, test-only tasks that never reach the image) that checks the backoff against the log timestamps, the DLQ row and the time limits. They need Linux (prefork): run them in the image, with PostgreSQL and Redis sharing a network namespace so both are `127.0.0.1` (recipe in `docs/async-tasks/analysis.md`, stop 2).

> _Spanish version: [README.es.md](./README.es.md)._
