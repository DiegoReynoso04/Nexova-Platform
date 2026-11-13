# Carpeta `data/pipelines`

Esta carpeta agrupa **todos los pipelines de datos del monorepo** relacionados con la compañía: procesos de ingesta, ETL/ELT, limpieza, transformación y carga hacia sistemas analíticos o de producción.

Cada subcarpeta o archivo dentro de `data/pipelines/` debe representar **un pipeline o conjunto de jobs** (por ejemplo `sales-etl`, `telemetry-stream`, `customer-segmentation`) e incluir la configuración necesaria (scripts, orquestación, conectores, esquemas, etc.).

- **Propósito principal**: unificar en un único lugar la lógica de movimiento y transformación de datos que soporta las aplicaciones y analíticas de la compañía.
- **Recomendación**: documenta aquí los pipelines que vayas añadiendo, describiendo su objetivo, orígenes/destinos de datos, dependencias y cómo ejecutarlos en desarrollo, pruebas y producción.

## Pipeline de desempeño de negocio (`pipeline.py`)

«Reporte Semanal de Desempeño por Oficina y Programa»: un flow de Prefect 3 que consolida, por semana, oficina y programa, los 4 KPI del BRIEFING en `reporting.weekly_office_program_performance` y deja cada corrida en `reporting.pipeline_runs`. Diseño: [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md) (frecuencia y ejecución en §4.5); decisiones: [`docs/reporting/implementation-analysis.md`](../../docs/reporting/implementation-analysis.md); verificación: [`docs/reporting/implementation-review.md`](../../docs/reporting/implementation-review.md).

| Archivo | Qué es |
|---|---|
| `pipeline.py` | El flow, sus 4 subflows y sus tasks, el backfill y el script |
| `business_performance/` | Soporte: configuración, SQL, migración, worker (`serve.py`), block (`secret.py`), consultas de solo lectura (`readonly.py`: `SET TRANSACTION READ ONLY` + `ROLLBACK`, para las fotos de la demo) y disparo manual (`trigger.py`, librería estándar, el único que importa la API) |
| `pyproject.toml`, `uv.lock`, `requirements.txt`, `requirements-dev.txt` | El entorno propio, con Prefect (`>=3.9.2,<3.10`): la API no lo instala. `requirements-dev.txt` (con hashes) solo lleva pytest, y no entra en la imagen |
| `tests/` | Los tests (`prefect_test_harness`; la integración con Postgres, solo con `PIPELINE_TEST_DATABASE_URL` local) |

**Entorno** (una vez, desde `data/pipelines`; sin `uv sync`):

```bash
uv venv .venv --python 3.14
uv pip install --python .venv --require-hashes -r requirements.txt
```

Tras cambiar una dependencia: `uv lock` y `uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt`.

**Ejecutar**, desde la raíz:

| | Windows (PowerShell) | Linux/macOS |
|---|---|---|
| Migración (una vez por base; antes, `--dry-run`) | `cd data\pipelines; .\.venv\Scripts\python -m business_performance.migrate` | `cd data/pipelines && .venv/bin/python -m business_performance.migrate` |
| La última semana cerrada | `data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py` | `data/pipelines/.venv/bin/python data/pipelines/pipeline.py` |
| Una semana concreta | `… pipeline.py --week-start 2026-11-02` | ídem |
| Backfill | `… pipeline.py --from 2026-11-02 [--to 2026-11-09]` | ídem |
| Tests | `data\pipelines\.venv\Scripts\python -m unittest discover -s data/pipelines/tests -t data/pipelines` | `data/pipelines/.venv/bin/python -m unittest discover -s data/pipelines/tests -t data/pipelines` |

- **Qué base:** `DATABASE_URL` de la terminal (`$env:DATABASE_URL = "postgresql://…"` / `export DATABASE_URL=…`) o, si falta, solo esa clave del `.env` de la raíz (**la demo**). La primera línea dice de dónde salió y el host; nunca la URL.
- **Guarda:** la migración se niega con una base que no es local salvo con `--allow-demo` (solo con la confirmación del usuario). La corrida no tiene guarda: solo escribe en `reporting` y es idempotente. Sin el esquema, sale con 2 y dice qué migración ejecutar.
- **Salida:** 0 completada; 1 alguna corrida falló; 2 configuración, argumentos o esquema ausente.
- **Qué deja:** sin servidor, Prefect arranca uno temporal con su estado en `~/.prefect` (fuera del repo); la caché de las tasks `compute_*` va a `data/raw/business_performance/` y los snapshots a `data/eval/business_performance/` (ignorados por git). La analítica de Prefect está desactivada (servidor y cliente).
- **Con Docker:** `docker compose --profile pipelines up -d` (servidor de Prefect en `http://localhost:4200` y worker); una vez, el block: `docker compose --profile pipelines exec -e DATABASE_URL pipeline-worker python -m business_performance.secret`. Contra la demo, solo con la confirmación del usuario.

**Subflows (Parte 3).** El flow `weekly_office_program_performance` llama a 4 subflows, con entradas y salidas explícitas, que también se pueden llamar solos desde Python con el Python del entorno de `data/pipelines` (o la imagen `nexova-pipeline`), nunca con el de `services/api`:

| Subflow | Firma | ¿Necesita base? |
|---|---|---|
| `extract_telemetry_events` | `(week_from, week_to) -> ExtractionResult` | Sí (o un repositorio en memoria en los tests) |
| `transform_weekly_kpis` | `(events: EventBatch, quality, week_from, week_to) -> TransformResult` | No: solo Prefect |
| `load_weekly_office_program_performance` | `(result, week_from, week_to, run_id) -> LoadOutcome` | Sí, y un `run_id` que exista en `reporting.pipeline_runs` |
| `snapshot_weekly_performance` (opcional) | `(output_dir, run_id, week_from, week_to, result, outcome) -> str` | No: solo disco |

```python
# Desde data/pipelines. La transformación no necesita base de datos:
import pipeline
from weekly_performance import QualityCounts
result = pipeline.transform_weekly_kpis(pipeline.EventBatch(events), QualityCounts(), week_from, week_to)
```

Los eventos van dentro de un `EventBatch` para que Prefect no guarde sus `event_id` ni `order_id` ni choque con su tope de 512 KiB de parámetros (`PIPELINE_DESIGN.md` §4.3); el límite de volumen conocido, en §4.6.

**Tests de las tasks por KPI** (`tests/pipelines/test_pipeline.py`, en la raíz del monorepo): llaman a las tasks con `.fn`, sin servidor de Prefect, sin base de datos y con datos ficticios con la forma de `telemetry_events`. Hace falta pytest, una dependencia **solo de desarrollo** (`requirements-dev.txt`, con hashes; el grupo `dev` de `pyproject.toml`). Siempre con el Python del entorno de `data/pipelines`, desde la raíz:

| | Comando |
|---|---|
| Instalar pytest en el venv (sin `uv sync`) | `uv pip install --python data/pipelines/.venv --require-hashes -r data/pipelines/requirements-dev.txt` |
| Tests, en el venv (Windows) | `data\pipelines\.venv\Scripts\python -m pytest tests/pipelines/test_pipeline.py` |
| Tests, en el venv (Linux/macOS) | `data/pipelines/.venv/bin/python -m pytest tests/pipelines/test_pipeline.py` |
| Tests, en la imagen (sin `.env`: solo `data/`, `packages/` y `tests/`), PowerShell | `docker run --rm -v "${PWD}/data:/repo/data" -v "${PWD}/packages:/repo/packages" -v "${PWD}/tests:/repo/tests" -w /repo nexova-pipeline:dev sh -c "uv pip install --system --no-cache --require-hashes -q -r data/pipelines/requirements-dev.txt && python -m pytest tests/pipelines/test_pipeline.py"` |

La suite `unittest` de `data/pipelines` se ejecuta con el Python del entorno (en la imagen necesitaría montar también `docs/` y `docker-compose.yml`, que algunos de sus tests leen). En Git Bash, `MSYS_NO_PATHCONV=1` delante y `$(pwd -W)` en lugar de `${PWD}`. Sin `__init__.py` en `tests/` ni en `tests/pipelines/`: con él chocaría con `data/pipelines/tests`. Tras cambiar la dependencia de desarrollo: `uv lock` y `uv export --frozen --only-group dev --no-emit-project --format requirements-txt -o requirements-dev.txt`.

Tras un merge que cambie `data/pipelines` o `data/process`, hay que **reconstruir la imagen** `nexova-pipeline` (el worker monta el código del host, pero la imagen lleva una copia que usan los `docker run` de arriba y el arranque sin montajes): `docker compose --profile pipelines up -d --build`.
