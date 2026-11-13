# Carpeta `data/process`

Esta carpeta contiene **datos procesados/intermedios** y/o artefactos derivados de los pipelines (por ejemplo: datasets limpios, features, agregados, tablas intermedias o resultados de transformaciones).

- **Propósito principal**: separar claramente los datos “raw” de los datos listos para análisis/modelado/consumo por apps.
- **Recomendación**: documenta qué pipeline genera cada artefacto, su esquema, periodicidad, y cómo se valida su calidad (checks, constraints, tests de datos).

## Pipeline de desempeño de negocio: `weekly_performance.py`

La **transformación pura** del «Reporte Semanal de Desempeño por Oficina y Programa» (§2.5 de [`data/pipelines/PIPELINE_DESIGN.md`](../pipelines/PIPELINE_DESIGN.md)). Las tasks del subflow `transform_weekly_kpis` de [`data/pipelines/pipeline.py`](../pipelines/pipeline.py) envuelven sus funciones, una línea cada una. Aquí no hay E/S, ni Prefect, ni Pandas: solo librería estándar y `nexova_shared.reporting`.

- **Pasos, cada uno una función pura** (`transform()` es su composición):
  1. `type_and_validate`: tipa y valida cada evento extraído (oficina, moneda de la oficina, cantidad, coste e id de orden), pone `_unassigned` si `programme_id` es nulo y calcula `week_start` (lunes ISO en UTC).
  2. `collapse_duplicate_orders`: cuenta una sola vez cada orden por semana (`duplicates_collapsed`).
  3. Una función por KPI: `total_material_cost_by_cell`, `kits_delivered_by_cell`, `shortage_events_by_cell` y `cost_variance_events_by_cell`.
  4. `assemble_rows`: una fila por celda con eventos, una moneda por celda (`DataQualityError` si no) y la conciliación.

  Nunca mezcla monedas ni inventa filas a 0.
- **Tipado defensivo:** un campo que no sea texto (o un `timestamp` que no sea `datetime`) se rechaza y cuenta en `rows_rejected`; nunca lanza. Los datos reales de la extracción siempre son texto, así que solo cambian entradas que antes hacían fallar la corrida.
- **Calidad:** la conciliación con el inventario y los eventos técnicos va a `pipeline_runs.quality`; no cambia ningún KPI.
- **Semanas:** las reglas (lunes, semana cerrada, retención) están en `nexova_shared.reporting.weeks` y se reexportan aquí. La API las usa para validar el disparo manual.
- **Artefacto:** el resultado no se guarda en esta carpeta, sino en la tabla `reporting.weekly_office_program_performance` (PostgreSQL), con la DDL del BRIEFING (§2.7 del diseño). No hay archivos de datos en git.
- **Intermedios:** la caché de Prefect (las tasks `compute_*`) va a `data/raw/business_performance/` y los snapshots de validación a `data/eval/business_performance/`. Las dos carpetas están ignoradas por git.
- **Versión:** `TRANSFORM_VERSION` forma parte de la clave de la caché de las tasks `compute_*`: súbela al cambiar cualquier regla.
- **Tests**, desde la raíz y con cualquier Python ≥ 3.11 (solo librería estándar y `packages/shared`): `PYTHONPATH=packages/shared python -m unittest discover -s data/process/tests -t data/process` (en Windows, antes `$env:PYTHONPATH = "packages/shared"`). En la imagen `nexova-pipeline`, que sí tiene los datos de zonas horarias, no se omite ninguno: `docker run --rm -v "${PWD}/data:/repo/data" -v "${PWD}/packages:/repo/packages" -w /repo -e PYTHONPATH=/repo/data/process:/repo/packages/shared nexova-pipeline:dev python -m unittest discover -s data/process/tests -t data/process`. Las **tasks** por KPI las prueba [`tests/pipelines/test_pipeline.py`](../../tests/pipelines/test_pipeline.py) (ver [`data/pipelines/README.es.md`](../pipelines/README.es.md)). Un cambio aquí se valida también con los tests de `data/pipelines` y se cuadra con `docs/reporting/pipeline-check.sql` en un Postgres efímero (`docs/reporting/implementation-review.md` §2).
