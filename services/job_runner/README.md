# `job_runner`

Control de estado de los jobs nocturnos (ticket DEV-53): la tabla `ops.job_runs`, su
máquina de estados `pending → processing → completed | failed` y el lock. **Biblioteca**
(como `services/telemetry` y `services/reporting`), no un servicio desplegable. Solo
SQLAlchemy y la librería estándar; no importa FastAPI, `services/api`, Prefect ni
`data/pipelines`. Análisis y decisiones: [`docs/telemetry/nightly-export-analysis.md`](../../docs/telemetry/nightly-export-analysis.md).

| Módulo | Qué hace |
|---|---|
| `states.py` | Estados, nombres de tabla e índices y constantes (45 min de zombi, 5 de `pending`, reintentos) |
| `repository.py` | `JobRunRepository`: `create_job_run`, `claim`, `complete`, `fail`, `discard`, `sweep_stale`, `has_processing_lock`, `has_completed_for_date`, `get_job_run`, `list_job_runs`, `schema_ready` |
| `runner.py` | `run_job(repository, job_name, target_date, work)`: el ciclo completo, con la función de trabajo inyectada |
| `redact.py`, `logs.py` | Mensajes de error y log sin secretos; formato `timestamp LEVEL job=… status=… target_date=…` |
| `config.py` | `DATABASE_URL` (entorno y, si falta, solo esa clave del `.env` de la raíz) y el motor |
| `migrate.py` | `python -m job_runner.migrate [--dry-run] [--allow-demo]` (desde `services/`) |

**El lock es el estado `processing`:** `UNIQUE (job_name) WHERE status = 'processing'` hace que la base
rechace a la segunda instancia en el mismo `UPDATE`. `UNIQUE (job_name, target_date) WHERE status = 'completed'`
es la idempotencia por día como garantía de base de datos. La omisión por duplicado y el bloqueo solo se
registran en el log (`status=skipped` / `status=locked`), nunca como fila.

## Quién lo usa

[`scripts/nightly_export.py`](../../scripts/nightly_export.py) (capa fina: `TARGET_DATE`, CSV, subproceso del pipeline) llama a `run_job`. Lo programa supercronic en el servicio `nightly-scheduler` de Compose (perfil `nightly`, apagado por defecto; `0 2 * * *` UTC). Guía de revisión: [`docs/telemetry/nightly-export-review.md`](../../docs/telemetry/nightly-export-review.md).

## Migración

Nunca al arrancar nada. Con la base de pruebas local (nunca la demo sin confirmación del usuario):

```bash
cd services
python -m job_runner.migrate --dry-run   # imprime la SQL pendiente
python -m job_runner.migrate             # la aplica en una transacción; la segunda vez, «Nada que migrar»
```

Una base que no es local exige `--allow-demo`. Crea el esquema `ops` con RLS sin políticas y `REVOKE ALL`
a `PUBLIC` y a los roles de Supabase; el esquema no se expone en la Data API.

## Tests

Con el entorno de `data/pipelines` (su `.venv` o la imagen), desde la raíz:

```bash
data/pipelines/.venv/bin/python -m unittest discover -s services/job_runner/tests -t services
```

(Windows: `data\pipelines\.venv\Scripts\python`.) Sin más variables corren los unitarios sobre SQLite; con
`JOB_RUNNER_TEST_DATABASE_URL` apuntando a un PostgreSQL **local** cuya base termine en `_test`, corren también
la migración, los mismos casos y las carreras reales entre conexiones (se niega con otro host).
