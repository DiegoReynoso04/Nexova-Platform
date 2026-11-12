# Carpeta `data/process`

Esta carpeta contiene **datos procesados/intermedios** y/o artefactos derivados de los pipelines (por ejemplo: datasets limpios, features, agregados, tablas intermedias o resultados de transformaciones).

- **Propósito principal**: separar claramente los datos “raw” de los datos listos para análisis/modelado/consumo por apps.
- **Recomendación**: documenta qué pipeline genera cada artefacto, su esquema, periodicidad, y cómo se valida su calidad (checks, constraints, tests de datos).

## Pipeline de desempeño de negocio: `weekly_performance.py`

La **transformación pura** del «Reporte Semanal de Desempeño por Oficina y Programa» (§2.5 de [`data/pipelines/PIPELINE_DESIGN.md`](../pipelines/PIPELINE_DESIGN.md)). La llama la task `transform_weekly_rows` de [`data/pipelines/pipeline.py`](../pipelines/pipeline.py). Aquí no hay E/S, ni Prefect, ni Pandas: solo librería estándar y `nexova_shared.reporting`.

- **Qué hace:**
  1. Tipa y valida cada evento extraído: oficina, moneda de la oficina, cantidad, coste e id de orden.
  2. Pone `_unassigned` si `programme_id` es nulo.
  3. Calcula `week_start` (lunes ISO en UTC).
  4. Cuenta una sola vez cada orden por semana (`duplicates_collapsed`).
  5. Agrega los 4 KPI por oficina, programa y semana.

  Nunca mezcla monedas (`DataQualityError`) ni inventa filas a 0.
- **Calidad:** la conciliación con el inventario y los eventos técnicos va a `pipeline_runs.quality`; no cambia ningún KPI.
- **Semanas:** las reglas (lunes, semana cerrada, retención) están en `nexova_shared.reporting.weeks` y se reexportan aquí. La API las usa para validar el disparo manual.
- **Artefacto:** el resultado no se guarda en esta carpeta, sino en la tabla `reporting.weekly_office_program_performance` (PostgreSQL), con la DDL del BRIEFING (§2.7 del diseño). No hay archivos de datos en git.
- **Intermedios:** la caché de Prefect va a `data/raw/business_performance/` y los snapshots de validación a `data/eval/business_performance/`. Las dos carpetas están ignoradas por git.
- **Versión:** `TRANSFORM_VERSION` forma parte de la clave de la caché de `transform_weekly_rows`: súbela al cambiar cualquier regla.
- **Tests:** `python -m unittest discover -s data/process/tests -t data/process`, desde la raíz y con cualquier Python ≥ 3.11. Un cambio aquí se valida también con los tests de `data/pipelines` y se cuadra con `docs/reporting/pipeline-check.sql` en un Postgres efímero (`docs/reporting/implementation-review.md` §2).

