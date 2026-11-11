# `data/process` folder

This folder contains **processed/intermediate data** and/or artifacts produced by pipelines (for example: clean datasets, features, aggregates, intermediate tables, or transformation outputs).

- **Main purpose**: clearly separate “raw” data from data ready for analysis, modeling, or app consumption.
- **Recommendation**: document which pipeline produces each artifact, its schema, refresh cadence, and how quality is validated (checks, constraints, data tests).

## Business performance pipeline: `weekly_performance.py`

The **pure transformation** of the "Weekly Performance Report by Office and Programme" (§2.5 of [`data/pipelines/PIPELINE_DESIGN.md`](../pipelines/PIPELINE_DESIGN.md)). The `transform_weekly_rows` task of [`data/pipelines/pipeline.py`](../pipelines/pipeline.py) calls it. It uses only the standard library and `nexova_shared.reporting`: no I/O, no Prefect, no Pandas.

- **What it does:** it types and validates the extracted events and maps a null `programme_id` to `_unassigned`. It then computes the ISO `week_start` in UTC, counts each order once per week and aggregates the 4 KPIs per office, programme and week.
- **Output:** nothing is stored in this folder. The result goes to the `reporting.weekly_office_program_performance` table.
- **Tests:** `python -m unittest discover -s data/process/tests -t data/process`, from the repository root.

Details in Spanish in [README.es.md](./README.es.md).

> _Spanish version: [README.es.md](./README.es.md)._
