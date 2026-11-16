# Carpeta `scripts`

Esta carpeta contiene **scripts auxiliares** del monorepo: automatizaciones de desarrollo, utilidades de mantenimiento, tareas repetitivas (setup, lint, migraciones, generación de datos, etc.) y tooling interno.

- **Propósito principal**: agrupar herramientas de soporte que no pertenecen a una app/agente/pipeline específico, pero facilitan el trabajo del equipo.
- **Recomendación**: documenta cada script (qué hace, parámetros, requisitos, ejemplos de uso) y procura que sean reproducibles (y seguros) en distintos entornos.

## Scripts de esta carpeta

| Script | Qué hace | Documentación |
|---|---|---|
| `analyze.py` | CLI del analizador de incidentes de Nexova (validación, métricas, exportación `results.csv`) | [`packages/incident-analyzer/README.md`](../packages/incident-analyzer/README.md) |
| `seed_incidents.py` | Carga el CSV de incidentes del helpdesk en el gestor centralizado de incidencias (idempotente; se ejecuta con el venv de `services/api`) | [`services/api/README.md`](../services/api/README.md#seed-de-datos-históricos-scriptsseed_incidentspy) |
| `seed_volume.py` | Seed de volumen sintético (miles de incidencias, cientos de proveedores, activos con cientos de órdenes) **solo para bases de prueba**: determinista, idempotente; rechaza los datos de la demo y un PostgreSQL no local | [`docs/caching-analysis.md`](../docs/caching-analysis.md) §2 |
| `bench_reads.py` | Ráfagas de GET idénticos contra la API (primera petición, p50/p95, respuestas idénticas, igual para otra cuenta); solo librería estándar, solo lectura, credenciales por variables de entorno | [`docs/caching-analysis.md`](../docs/caching-analysis.md) §2 |
| `validate_event_schemas.py` | Valida `docs/telemetry/event-schemas.json` (subconjunto cerrado de JSON Schema draft-07) y su coherencia con `docs/telemetry/telemetry-plan.md`: mismos eventos, metadatos y allowlists, y que todo ejemplo JSON del plan valida; solo librería estándar. `--dump-examples <carpeta>` escribe los ejemplos para `ajv-cli` | [`docs/telemetry/telemetry-plan.md`](../docs/telemetry/telemetry-plan.md) §9 |
| `nightly_export.py` | Job nocturno de telemetría (DEV-53): exporta el día anterior (UTC) de `telemetry_events` a `data/raw/telemetry_YYYY-MM-DD.csv` (proyección sin identificadores, lista blanca de claves de `tags`, escritura atómica, nunca se sobrescribe) y lanza el pipeline como subproceso, bajo la máquina de estados de `ops.job_runs` (`processing` es el lock; idempotente por día). Independiente de la API. Se ejecuta con el entorno de `data/pipelines` (necesita Prefect); `TARGET_DATE=YYYY-MM-DD` cambia el día; salida 0 completed/skipped/locked, 1 failed, 2 configuración (sin fila). Lo programa el perfil `nightly` de Compose (supercronic, `0 2 * * *` UTC) | [`docs/telemetry/nightly-export-review.md`](../docs/telemetry/nightly-export-review.md), [`services/job_runner/README.md`](../services/job_runner/README.md) |
