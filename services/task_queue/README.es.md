# `task_queue`

Cola de tareas asíncronas de Nexova (ticket DEV-55): Celery, con Redis como broker y como result backend. Es una **biblioteca**, como `services/job_runner` y `services/telemetry`: la API la importa para encolar tareas y leer su estado, y el servicio `worker` de Compose la ejecuta como un proceso aparte (`celery -A task_queue.celery_app worker`). Nunca importa FastAPI, el paquete `app` de la API ni Prefect (`tests/test_architecture.py`). Reutiliza `job_runner` para la redacción de errores y las reglas de `DATABASE_URL`. Análisis y decisiones A1–A16: [`docs/async-tasks/analysis.md`](../../docs/async-tasks/analysis.md).

> **Estado (F1, parada 3):** `GET /telemetry/report` encola `task_queue.telemetry_report` y responde `202`; `GET /tasks/{task_id}` da su estado y su resultado (`services/api/SPECS.md` Parte J). Toda tarea tiene reintentos con backoff, la dead letter queue y una línea de log por ejecución. La página `/telemetry` del backoffice se adapta en la parada 4.

| Módulo | Qué hace |
|---|---|
| `config.py` | `REDIS_URL` (el broker en su base y los resultados en la siguiente; nunca se repite en un error ni en `repr`), los ajustes de Celery de A7 y las constantes de A8/A9 |
| `factory.py` | `create_app(settings)` (sin E/S, `task_cls` = `base.ReliableTask`) |
| `celery_app.py` | La instancia `app` del módulo, la del worker y Flower (lee `REDIS_URL` al importarse). La API nunca lo importa |
| `client.py` | **La única puerta de la API a la cola** (productor): `TaskQueueClient.submit` (deduplicación por usuario durante 60 s, metadatos guardados antes de publicar y un mensaje con solo las referencias recibidas) y `status` (propietario o admin, si no `None`; los 6 estados de Celery a `pending`/`started`/`success`/`failure`, `RETRY` → `started`). Redis o el broker caídos → `TaskQueueUnavailableError`. `from_redis_url` carga los módulos perezosos de Celery sin conectar |
| `metadata.py` | `nexova:task:<id>` (propietario, tarea, hora) y `nexova:dedupe:…` en Redis. Los metadatos llevan un TTL de seguridad de 7 días mientras la tarea está en cola o en curso; al terminar, el worker lo baja a los 3600 s del resultado (A10) |
| `names.py` | Los nombres de las tareas, compartidos por la API y el worker |
| `reports.py` | `build_telemetry_report(engine, start, end)`: las 5 métricas de `services/telemetry/analysis.py` de `[start, end)`, en una transacción con `SET LOCAL statement_timeout` (`TASK_QUEUE_STATEMENT_TIMEOUT_MS`, 110 000 por defecto) |
| `memory.py` | Dobles en memoria para los tests (`MemoryStore`, `EagerBackend`); no los usa producción |
| `base.py` | `ReliableTask`: registra `started`; ante un error transitorio (`errors.RETRYABLE_EXCEPTIONS`: `OperationalError`, `InterfaceError` y `TimeoutError` de SQLAlchemy) reintenta con `retries.backoff_countdown`; si no, o tras `max_retries=3` (4 ejecuciones), registra `dead_letter`, guarda la fila y lanza `TaskFailedError` (redactada). `DeadLetterRequest` registra los límites duros de tiempo desde el proceso principal del worker |
| `retries.py` | `base · 2^n + uniforme(0, base)`, con base 2 s: 2–4, 4–6 y 8–10 s. Nunca por debajo de `base · 2^n` (el jitter completo de Celery puede dar 0 s) |
| `dead_letters.py` | `ops.task_dead_letters` (`attempt` = `retries` + 1, `task_id` único), `DeadLetterRepository` y `record_dead_letter`: un reintento corto y, si la base no responde o la tabla no existe, una línea `ERROR` con todos los campos (`status=dead_letter_not_stored`) |
| `redaction.py` | `describe_failure` (errores de SQLAlchemy: solo las clases; el resto: `Clase: mensaje` sin URL ni valores secretos, ≤ 2000 caracteres) y el filtro de logging en `celery.app.trace`, `celery.worker.request` y `task_queue` |
| `database.py` | `DATABASE_URL` solo del entorno, un motor `NullPool` por proceso y `SET LOCAL statement_timeout` por transacción |
| `logs.py` | `task_id=… task=… attempt=2/4 status=retry duration_ms=… countdown_s=… error="…"` |
| `migrate.py` | `python -m task_queue.migrate [--dry-run] [--allow-demo]` (desde `services/`) |
| `tasks.py` | Las tareas, registradas con nombre explícito: `task_queue.ping` → `"pong"` y `task_queue.telemetry_report(start, end)` → `{"period", "metrics"}` |
| `errors.py` | Errores reintentables (también envueltos, p. ej. por `pandas.read_sql`), `TaskFailedError` y los motivos de la DLQ |

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

**La `DATABASE_URL` del worker sale del `.env` de la raíz: la demo, como la de la API.** Solo escribe en `ops.task_dead_letters`, que no existe en la demo hasta que el usuario la migre; hasta entonces, un fallo definitivo queda solo en el log.

## Migración

Nunca al arrancar. Contra una base de pruebas local (nunca la demo sin la confirmación del usuario):

```bash
cd services
python -m task_queue.migrate --dry-run   # imprime la SQL pendiente
python -m task_queue.migrate             # la aplica en una transacción; la segunda vez, «Nada que migrar»
```

Crea `ops` solo si falta y lo comparte con `job_runner.migrate` (funcionan en cualquier orden). RLS sin políticas y `REVOKE ALL` a `PUBLIC` y a los roles de Supabase. Una base que no es local exige `--allow-demo`.

## Tests

Con el entorno de `services/api`, desde la raíz:

```bash
services/api/.venv/bin/python -m unittest discover -s services/task_queue/tests -t services   # Windows: services\api\.venv\Scripts\python
```

Sin más variables corren solo los unitarios (sin Redis ni PostgreSQL). Con `TASK_QUEUE_TEST_DATABASE_URL` (PostgreSQL local cuya base termine en `_test`; **borra y recrea `ops`**) y `TASK_QUEUE_TEST_REDIS_URL` (Redis local; vacía las dos bases que usa) corren también los de integración: la migración contra PostgreSQL en los dos órdenes con `job_runner` y un worker `prefork` de verdad (`tests/integration_app.py`, con tareas solo de test que nunca entran en la imagen), que comprueba el backoff con las marcas de tiempo del log, la fila de la DLQ y los límites de tiempo. Necesitan Linux (prefork): se ejecutan en la imagen, con PostgreSQL y Redis en el mismo espacio de red para que los dos sean `127.0.0.1` (receta en `docs/async-tasks/analysis.md`, parada 2).

> _Versión en inglés: [README.md](./README.md)._
