# `data/process` folder

This folder contains **processed/intermediate data** and/or artifacts produced by pipelines (for example: clean datasets, features, aggregates, intermediate tables, or transformation outputs).

- **Main purpose**: clearly separate “raw” data from data ready for analysis, modeling, or app consumption.
- **Recommendation**: document which pipeline produces each artifact, its schema, refresh cadence, and how quality is validated (checks, constraints, data tests).

## Business performance pipeline: `weekly_performance.py`

The **pure transformation** of the "Weekly Performance Report by Office and Programme" (§2.5 of [`data/pipelines/PIPELINE_DESIGN.md`](../pipelines/PIPELINE_DESIGN.md)). The tasks of the `transform_weekly_kpis` subflow in [`data/pipelines/pipeline.py`](../pipelines/pipeline.py) wrap its functions, one line each. It uses only the standard library and `nexova_shared.reporting`: no I/O, no Prefect, no Pandas.

- **Steps, each a pure function** (`transform()` is their composition): `type_and_validate` (types and validates events, maps a null `programme_id` to `_unassigned`, ISO `week_start` in UTC), `collapse_duplicate_orders` (each order counts once per week), one function per KPI (`total_material_cost_by_cell`, `kits_delivered_by_cell`, `shortage_events_by_cell`, `cost_variance_events_by_cell`) and `assemble_rows` (one currency per cell, reconciliation).
- **Defensive typing:** a field that is not text (or not a `datetime` for `timestamp`) is rejected and counted in `rows_rejected`; it never raises. Real extraction data is always text, so only inputs that used to fail the run change.
- **Output:** nothing is stored in this folder. The result goes to the `reporting.weekly_office_program_performance` table.
- **Tests**, from the repository root and with any Python ≥ 3.11 (standard library and `packages/shared` only): `PYTHONPATH=packages/shared python -m unittest discover -s data/process/tests -t data/process` (on Windows, `$env:PYTHONPATH = "packages/shared"` first). In the `nexova-pipeline` image, where the time zone data is present, nothing is skipped: `docker run --rm -v "${PWD}/data:/repo/data" -v "${PWD}/packages:/repo/packages" -w /repo -e PYTHONPATH=/repo/data/process:/repo/packages/shared nexova-pipeline:dev python -m unittest discover -s data/process/tests -t data/process`. The KPI **tasks** are tested by [`tests/pipelines/test_pipeline.py`](../../tests/pipelines/test_pipeline.py) (see [`data/pipelines/README.md`](../pipelines/README.md)).

Details in Spanish in [README.es.md](./README.es.md).

> _Spanish version: [README.es.md](./README.es.md)._
