"""Endpoints del reporte de desempeño de negocio: una librería de la API, como `services/telemetry`.

- `router`: `GET /reporting/weekly-office-program-performance`,
  `GET /reporting/pipeline-runs/latest` y `POST /reporting/pipeline-runs`.
- `reads`: las lecturas del esquema `reporting` (solo `SELECT`).
- `schemas`: el contrato de las respuestas (el del BRIEFING para las filas de KPI).

**Sin ETL:** no importa `prefect`, `pandas`, `pipeline` ni nada de
`business_performance` salvo `trigger` (librería estándar), y no escribe en
`reporting`. Lo comprueba `services/api/tests/test_reporting_architecture.py`.
"""
