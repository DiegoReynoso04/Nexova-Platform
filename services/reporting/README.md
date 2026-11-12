# `services/reporting`

Endpoints del «Reporte Semanal de Desempeño por Oficina y Programa»: leen el esquema `reporting` que escribe el pipeline ([`data/pipelines/pipeline.py`](../../data/pipelines/pipeline.py)) y disparan corridas manuales.

**No es un servicio desplegable.** Es una librería de la API de Nexova ([`services/api`](../api/README.md)), como [`services/telemetry`](../telemetry/README.md): corre dentro de su proceso y `app/main.py` registra su router. Diseño y contrato: Fase 5 de [`PIPELINE_DESIGN.md`](../../data/pipelines/PIPELINE_DESIGN.md).

| Ruta | Auth | Respuestas |
|---|---|---|
| `GET /reporting/weekly-office-program-performance?week_start=` | Bearer, cualquier rol | 200 (contrato del BRIEFING), 404 `week_not_computed`, 422, 401, 503 `storage_unavailable` |
| `GET /reporting/pipeline-runs/latest` | Bearer, cualquier rol | 200 (sin `requested_by`), 404 `pipeline_run_not_found`, 401, 503 |
| `POST /reporting/pipeline-runs` | Bearer, solo `admin` | 202 `{prefect_flow_run_id, status}`, 409 `pipeline_run_in_progress`, 422, 401, 403, 503 `pipeline_unavailable` |

- **Sin ETL:** no importa `prefect`, `pandas`, el flow ni la transformación; de `data/pipelines` solo `business_performance.trigger` (librería estándar). Su SQL solo lee. Lo comprueba `services/api/tests/test_reporting_architecture.py`.
- **Por qué `request_manual_run` y no el flow:** Prefect no está en la API, y un flow dentro de la API moriría con cada recarga de `--reload`. `request_manual_run` solo pide el flow run al servidor de Prefect; lo ejecuta el `pipeline-worker`.
- **Configuración:** `PIPELINE_PREFECT_API_URL` (opcional; con Docker, `http://prefect-server:4200/api`). Sin ella, o con el servidor caído, el `POST` da 503. Las lecturas usan la base de la API (`DATABASE_URL`).
- **Sin caché:** la tabla la escribe otro proceso (el worker), que no puede invalidar la caché en memoria de la API.
- **Dónde corre:** la imagen la copia en `/app/api/reporting` (se importa como `reporting`) y `business_performance/__init__.py` + `trigger.py` en `/pipelines`; Compose monta los mismos archivos para recargar sin reconstruir. Fuera de Docker, uvicorn necesita `services/` y `data/pipelines` en `PYTHONPATH`.
- **Tests:** en `services/api/tests/` (`test_reporting_api.py`, `test_reporting_architecture.py`), con la validación de `services/api` (`AGENTS.md` §4); `tests/__init__.py` pone `services/` y `data/pipelines` en `sys.path`.
- **Revisión:** [`docs/reporting/implementation-review.md`](../../docs/reporting/implementation-review.md) §3–§4.
