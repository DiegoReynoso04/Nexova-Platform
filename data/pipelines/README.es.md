# Carpeta `data/pipelines`

Esta carpeta agrupa **todos los pipelines de datos del monorepo** relacionados con la compañía: procesos de ingesta, ETL/ELT, limpieza, transformación y carga hacia sistemas analíticos o de producción.

Cada subcarpeta o archivo dentro de `data/pipelines/` debe representar **un pipeline o conjunto de jobs** (por ejemplo `sales-etl`, `telemetry-stream`, `customer-segmentation`) e incluir la configuración necesaria (scripts, orquestación, conectores, esquemas, etc.).

- **Propósito principal**: unificar en un único lugar la lógica de movimiento y transformación de datos que soporta las aplicaciones y analíticas de la compañía.
- **Recomendación**: documenta aquí los pipelines que vayas añadiendo, describiendo su objetivo, orígenes/destinos de datos, dependencias y cómo ejecutarlos en desarrollo, pruebas y producción.

## Pipeline de desempeño de negocio (`pipeline.py`)

«Reporte Semanal de Desempeño por Oficina y Programa»: un flow de Prefect 3 que consolida, por semana, oficina y programa, los 4 KPI del BRIEFING en `reporting.weekly_office_program_performance` y deja cada corrida en `reporting.pipeline_runs`. Diseño: [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md) (frecuencia y ejecución en §4.5); decisiones: [`docs/reporting/implementation-analysis.md`](../../docs/reporting/implementation-analysis.md); verificación: [`docs/reporting/implementation-review.md`](../../docs/reporting/implementation-review.md).

| Archivo | Qué es |
|---|---|
| `pipeline.py` | El flow, el backfill y sus tasks; el script |
| `business_performance/` | Soporte: configuración, SQL, migración, worker (`serve.py`), block (`secret.py`), consultas de solo lectura (`readonly.py`: `SET TRANSACTION READ ONLY` + `ROLLBACK`, para las fotos de la demo) y disparo manual (`trigger.py`, librería estándar, el único que importa la API) |
| `pyproject.toml`, `uv.lock`, `requirements.txt` | El entorno propio, con Prefect (`>=3.9.2,<3.10`): la API no lo instala |
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
- **Qué deja:** sin servidor, Prefect arranca uno temporal con su estado en `~/.prefect` (fuera del repo); la caché de `transform_weekly_rows` va a `data/raw/business_performance/` y los snapshots a `data/eval/business_performance/` (ignorados por git). La analítica de Prefect está desactivada (servidor y cliente).
- **Con Docker:** `docker compose --profile pipelines up -d` (servidor de Prefect en `http://localhost:4200` y worker); una vez, el block: `docker compose --profile pipelines exec -e DATABASE_URL pipeline-worker python -m business_performance.secret`. Contra la demo, solo con la confirmación del usuario.

