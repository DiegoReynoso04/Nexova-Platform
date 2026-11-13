# `data/pipelines` folder

This folder groups **all data pipelines in the monorepo** related to the company: ingestion, ETL/ELT, cleaning, transformation, and loading into analytical or production systems.

Each subfolder or file under `data/pipelines/` should represent **one pipeline or job set** (for example `sales-etl`, `telemetry-stream`, `customer-segmentation`) and include the required configuration (scripts, orchestration, connectors, schemas, etc.).

- **Main purpose**: consolidate in one place the data movement and transformation logic that powers the company’s applications and analytics.
- **Recommendation**: document pipelines as you add them—their goal, data sources and sinks, dependencies, and how to run them in development, testing, and production.

## Business performance pipeline (`pipeline.py`)

The "Weekly Performance Report by Office and Programme": a Prefect 3 flow that aggregates the 4 BRIEFING KPIs per week, office and programme into `reporting.weekly_office_program_performance` and logs every run in `reporting.pipeline_runs`. Design: [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md) (frequency and commands in §4.5); decisions: [`docs/reporting/implementation-analysis.md`](../../docs/reporting/implementation-analysis.md); verification guide: [`docs/reporting/implementation-review.md`](../../docs/reporting/implementation-review.md).

- **Own environment** (Prefect `>=3.9.2,<3.10`; the API never installs it), from `data/pipelines`: `uv venv .venv --python 3.14` and `uv pip install --python .venv --require-hashes -r requirements.txt` (no `uv sync`).
- **Run**, from the repository root: `data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py` (Windows) or `data/pipelines/.venv/bin/python data/pipelines/pipeline.py` (Linux/macOS). No options: the last closed week; `--week-start YYYY-MM-DD` for one week; `--from YYYY-MM-DD [--to …]` to backfill.
- **Database:** `DATABASE_URL` from the terminal or, if missing, that single key from the root `.env` (**the demo**); only the host is printed. Run the migration first (`python -m business_performance.migrate`, from `data/pipelines`); against a non-local host it needs `--allow-demo` (only with the user's confirmation).
- **Docker:** `docker compose --profile pipelines up -d` (Prefect server at `http://localhost:4200` and the worker).

- **Subflows (Part 3):** the main flow `weekly_office_program_performance` calls 4 subflows with explicit inputs and outputs: `extract_telemetry_events`, `transform_weekly_kpis`, `load_weekly_office_program_performance` and the optional `snapshot_weekly_performance`. Each can be called on its own from Python, with the Python of the `data/pipelines` environment (or the `nexova-pipeline` image), never with the one of `services/api`. For example, the transformation needs no database: `import pipeline; pipeline.transform_weekly_kpis(pipeline.EventBatch(events), QualityCounts(), week_from, week_to)`. The load needs a database and a `run_id` that exists in `reporting.pipeline_runs`. Details: [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md) §4.1; what Prefect stores (`EventBatch`): §4.3; known volume limit: §4.6.
- **Tests**, from the repository root and always with the Python of the `data/pipelines` environment (or the image):
  - `python -m unittest discover -s data/pipelines/tests -t data/pipelines` (Prefect test harness; the Postgres integration only with `PIPELINE_TEST_DATABASE_URL` pointing to a local database).
  - `python -m pytest tests/pipelines/test_pipeline.py`: the KPI transformation tasks, called with `.fn` (no Prefect server, no database). It needs pytest, a **development-only** dependency (`requirements-dev.txt`, with hashes): `uv pip install --python data/pipelines/.venv --require-hashes -r data/pipelines/requirements-dev.txt` (no `uv sync`).
  - In the image (no `.env`: only `data/`, `packages/` and `tests/` are mounted), PowerShell from the root: `docker run --rm -v "${PWD}/data:/repo/data" -v "${PWD}/packages:/repo/packages" -v "${PWD}/tests:/repo/tests" -w /repo nexova-pipeline:dev sh -c "uv pip install --system --no-cache --require-hashes -q -r data/pipelines/requirements-dev.txt && python -m pytest tests/pipelines/test_pipeline.py"`. In Git Bash, prefix `MSYS_NO_PATHCONV=1` and use `$(pwd -W)` instead of `${PWD}`.

Full instructions (in Spanish) in [README.es.md](./README.es.md).

> _Spanish version: [README.es.md](./README.es.md)._
