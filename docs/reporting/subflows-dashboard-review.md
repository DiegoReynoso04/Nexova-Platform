# Parte 3 del pipeline de desempeño de negocio: guía de revisión

Subflows, tests y dashboard. Rama `feature/business-pipeline-subflows` (desde `main` en `ec5cdac`, PR #34). Análisis y decisiones: [`subflows-dashboard-analysis.md`](./subflows-dashboard-analysis.md) (D y H1–H9). Diseño actualizado: [`data/pipelines/PIPELINE_DESIGN.md`](../../data/pipelines/PIPELINE_DESIGN.md) (§2.4, §2.5, §4.1, §4.3, §4.6, §6 y §8). Reglas del dashboard: [`uis/backoffice/CLAUDE.md`](../../uis/backoffice/CLAUDE.md) («Reporte semanal»).

> **Todo esto se verifica contra un Postgres efímero, nunca contra la demo.** Ninguna orden de esta guía lee ni escribe en Supabase. La comprobación del dashboard con los datos de la demo la hace el usuario, en solo lectura y con su confirmación (§8).

## 1. Qué cambia

| Fase | Qué | Dónde |
|---|---|---|
| 1. Subflows | El flow principal llama a 4 subflows con entradas y salidas explícitas: `extract_telemetry_events`, `transform_weekly_kpis`, `load_weekly_office_program_performance` y `snapshot_weekly_performance` (opcional, con `return_state=True`). Las tasks de transformación se dividen por KPI (`compute_*`) y envuelven funciones puras | `data/pipelines/pipeline.py`, `data/process/weekly_performance.py` |
| 2. Tests | `tests/pipelines/test_pipeline.py` (12 tests, con `.fn`, sin servidor ni base de datos), más `test_subflows.py` y `test_event_batch.py`. pytest, solo como dependencia de desarrollo | `tests/pipelines/`, `data/pipelines/tests/`, `data/pipelines/requirements-dev.txt` |
| 3. Dashboard | `/reporting` en el backoffice | `uis/backoffice/` |
| 4. Documentación | Diseño, READMEs, `AGENTS.md` §4 y esta guía | — |

**No cambian:** `python data/pipelines/pipeline.py` (con `--week-start`, `--from`/`--to`, los códigos 0/1/2 y §4.5), el esquema `reporting`, `telemetry_events`, `services/telemetry/analysis.py`, `services/reporting`, `services/api`, la imagen de producción (`requirements.txt`) ni los deployments y `trigger.py`.

## 2. Preparar el efímero

Igual que en [`implementation-review.md`](./implementation-review.md) §2 (Postgres 17 con un rol sin superusuario; tablas de origen con el código de la API; migración `python -m business_performance.migrate`; seed ficticio `pipeline-seed-ephemeral.sql`). Resumen, desde la raíz, en PowerShell (contraseñas generadas en la terminal; no se imprimen):

```powershell
docker run -d --name nexova-pipeline-pg --network nexova-net -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=$su postgres:17.6-alpine3.22
docker exec nexova-pipeline-pg psql -q -U postgres -c "CREATE ROLE nexova_app LOGIN NOSUPERUSER PASSWORD '$app'"
docker exec nexova-pipeline-pg psql -q -U postgres -c "CREATE DATABASE nexova_test OWNER nexova_app"
$env:DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:55432/nexova_test"
```

Después, las tablas de origen y la migración (`implementation-review.md` §2.3 y §2.4) y el seed (§2.5). **La primera línea de cada corrida debe decir `DATABASE_URL: entorno, host 127.0.0.1`.** Si dice otro host, para.

## 3. Verificación del pipeline

Con el Python del entorno de `data/pipelines` (`data\pipelines\.venv\Scripts\python` en Windows, `data/pipelines/.venv/bin/python` en Linux/macOS), nunca el de `services/api`:

| Qué | Comando (desde la raíz) | Esperado |
|---|---|---|
| El ETL completo, **sin argumentos** | `python data/pipelines/pipeline.py` (con ese Python) | salida 0; 4 `Beginning subflow run` (`extract_telemetry_events`, `transform_weekly_kpis`, `load_weekly_office_program_performance`, `snapshot_weekly_performance`); línea JSON `pipeline_run_finished` con `"status": "completed"` |
| Segunda corrida, en menos de 1 h | el mismo | `Cached(type=COMPLETED)` en las 4 `compute_*`; el resto, `Completed` |
| Backfill de 2 semanas | `… pipeline.py --from 2026-10-26 --to 2026-11-02` | salida 0; una fila `completed` por semana en `reporting.pipeline_runs` |
| Cuadre a mano | `Get-Content docs\reporting\pipeline-check.sql -Raw \| docker exec -i nexova-pipeline-pg psql -q -U nexova_app -d nexova_test` | `missing_or_different = 0` y `unexpected = 0` |
| Un fallo en la carga | ver abajo | salida 1; la fila queda `failed` / `load`, con `error_class = OperationalError` (la clase original) |

**Un fallo transitorio en la carga, con la base arriba** (así `finish_run` puede escribir el `failed`; con la base apagada, `main()` sale con 2 antes de empezar, porque comprueba el esquema). Como `postgres`: `ALTER ROLE nexova_app SET lock_timeout = '2s'` y, en otra terminal, retener el bloqueo de la carga con `select pg_advisory_lock(hashtext('weekly_office_program_performance')); select pg_sleep(110)`. La corrida reintenta 2 veces (30 s) y sale con 1 a los ~72 s. **Restaurar después:** `ALTER ROLE nexova_app RESET lock_timeout` y cerrar la sesión que retiene el bloqueo; una corrida nueva sale con 0.

## 4. Verificación de los tests

Con el mismo Python (y `requirements-dev.txt` instalado: `uv pip install --python data/pipelines/.venv --require-hashes -r data/pipelines/requirements-dev.txt`, nunca `uv sync`):

| Qué | Comando | Esperado |
|---|---|---|
| Los tests de las tasks por KPI | `python -m pytest tests/pipelines/test_pipeline.py` | **12 passed** |
| Lo mismo, en la imagen (sin `.env`) | el `docker run` de `data/pipelines/README.es.md` | **12 passed** |
| La suite de `data/pipelines` | `python -m unittest discover -s data/pipelines/tests -t data/pipelines` | OK; con `PIPELINE_TEST_DATABASE_URL` apuntando al efímero, **0 omitidos** (los 5 de Postgres corren) |
| La suite de `data/process` | `PYTHONPATH=packages/shared python -m unittest discover -s data/process/tests -t data/process` | OK; en la imagen, **0 omitidos** (en el host se omite 1 por falta de datos de zonas horarias) |
| La suite de `services/api` (no se tocó) | el comando de [`TESTING.md`](../../services/api/TESTING.md) §14 | OK, `test_reporting_architecture` incluido |
| `uis/backoffice` | `npx next typegen`, `npx tsc --noEmit`, `npm run lint`, `npm run build`, `node --test` y `npm run test:jest` (`AGENTS.md` §4) | todo en verde |

**Los tests detectan errores (mutación).** Cambiar temporalmente en `data/process/weekly_performance.py` la suma del costo a `… + item.unit_cost` (sin `* item.quantity`) hace fallar 2 de los 12 de pytest (`test_total_material_cost_sums_unit_cost_times_quantity` y `test_week_report_matches_hand_calculation`) y 2 de `data/process`. Revertido el cambio, el `git diff` del archivo vuelve a ser idéntico.

## 5. Verificación de `EventBatch` y del volumen

`data/pipelines/tests/test_event_batch.py` (con el servidor temporal de Prefect) comprueba que `flow_run.parameters` solo guarda el marcador `"<EventBatch>"` (ningún `event_id` ni `order_id`), que 10 000 eventos pasan por el subflow, que una lista normal sí se guardaría (control negativo) y que el tope de Prefect sigue en 524 288 bytes. Si una versión nueva de Prefect cambia ese comportamiento, el test falla (`PIPELINE_DESIGN.md` §4.3).

**Tiempos medidos** (servidor temporal, eventos ficticios, límite de Prefect por defecto; `PIPELINE_DESIGN.md` §4.6):

| Eventos | `transform_weekly_kpis` | Transformación pura | Flow completo (repositorio en memoria) |
|---|---|---|---|
| 1 000 | 3,4 s | 0,008 s | — |
| 10 000 | 9,9 s | 0,09 s | 21 s |
| 50 000 | 45,5 s | 0,53 s | 129 s |

El perfil de `cProfile` con 10 000 eventos apunta a `collect_task_run_inputs_sync` → `visit_collection` (1,5 millones de llamadas recursivas y 13 millones de `isinstance`): Prefect recorre cada argumento de cada task. **No es la transformación.** Con el límite por defecto y sin `EventBatch`, 10 000 eventos darían un 422 al crear el flow run.

## 6. Verificación del dashboard, en el navegador

**Solo con la API conectada al Postgres efímero.** No uses el stack que lee el `.env` (puertos 3000, 3001 y 8000): lee la demo. Dos formas:

1. **Parar el stack normal** y usar `docker-compose.yml` + [`compose-ephemeral.yml`](./compose-ephemeral.yml) como en `implementation-review.md` §3 (la API apunta al efímero y los usuarios van a una TinyDB temporal del contenedor).
2. **Un proyecto aparte, sin tocar el stack normal** (el que se usó para esta guía): otra red y otros puertos, con un override fuera del repo:

```yaml
# eph-override.yml (en una carpeta temporal; sin secretos)
services:
  api:
    image: nexova-api:latest
    pull_policy: never
    ports: !override ["8100:8000"]
  ui:
    image: nexova-ui:latest
    pull_policy: never
    ports: !override ["3101:3001"]
networks:
  nexova:
    name: nexova-eph-net
```

```powershell
$env:EPHEMERAL_DATABASE_URL = "postgresql://nexova_app:$app@nexova-pipeline-pg:5432/nexova_test"
docker compose -p nexova-eph -f docker-compose.yml -f docs/reporting/compose-ephemeral.yml -f eph-override.yml up -d api ui
docker network connect nexova-eph-net nexova-pipeline-pg   # antes de que la API arranque, o reiníciala
docker exec nexova-eph-api-1 python -c "import os,urllib.parse as u; print(u.urlparse(os.environ['DATABASE_URL']).hostname)"   # debe decir nexova-pipeline-pg
```

Abre `http://localhost:3101/register`, crea un usuario de prueba desechable (por ejemplo `qa@example.test`) y entra. Cualquier rol sirve. Al terminar: `docker network disconnect nexova-eph-net nexova-pipeline-pg` y `docker compose -p nexova-eph -f … down` (el usuario desaparece con el contenedor).

**Recorrido** (en `http://localhost:3101/reporting`, escritorio y 375 px):

| Paso | Cómo | Esperado |
|---|---|---|
| Datos de la última semana | abrir la página | Título «Reporte Semanal…»; franja «Datos actualizados el …» con las semanas calculadas; «Semana del lunes 2 al domingo 8 de noviembre de 2026»; la nota de monedas; los 4 bloques con el nombre y el «qué mide» del BRIEFING; Valencia y Miami lado a lado (con «(EUR)» y «(USD)» solo en la cabecera del bloque del costo); «Sin programa asignado»; la nota de que el material no está clasificado por programa; «Semana siguiente» desactivada |
| Semana anterior y siguiente | los botones | Cambia el período en el encabezado y en cada bloque; en los conteos, barras con escala común; el costo, sin barra |
| Semana sin calcular (404) | «Semana anterior» hasta una semana que ninguna corrida cubrió | «Esta semana todavía no se ha calculado» (informativo, no un error); los botones siguen |
| Semana vacía | calcular una semana sin eventos (`pipeline.py --week-start 2026-10-12`) y navegar a ella | «No hubo actividad registrada en esta semana» |
| Corrida `failed` | la corrida con fallo transitorio de §3 | Franja roja: «La última actualización falló; las cifras pueden ser de una corrida anterior»; sin fase ni `error_class` |
| Desactualizado | en el efímero: `update reporting.pipeline_runs set started_at = started_at - interval '9 days', finished_at = finished_at - interval '9 days'` | «Los datos pueden estar desactualizados…». Restaurar con una corrida nueva |
| 503 | parar `nexova-pipeline-pg`, pulsar «Semana anterior» y esperar ~15 s | «Los datos no están disponibles ahora mismo» con «Reintentar» (sin códigos) |
| API parada | parar `nexova-eph-api-1` y pulsar «Semana anterior» | «Error del servidor» con «Reintentar» |
| Carga | retrasar las peticiones de `/reporting` | Esqueleto con la misma rejilla y «Cargando el reporte…» |
| 375 px | ventana de 375 px | `document.documentElement.scrollWidth` igual a `innerWidth`: sin scroll horizontal |

**Comprobado con los datos reales de la demo, en solo lectura (el usuario, 2026-11-13):** los 4 KPI con su nombre del BRIEFING; «Semana del lunes 2 al domingo 8 de noviembre de 2026»; Valencia con 16,00 € de costo; Miami con 1 kit entregado, 1 escasez, 0,00 US$ de costo y 0 variaciones; «Sin programa asignado» con su nota; franja «Datos actualizados el 12 de noviembre de 2026 a las 21:31» sin aviso de desactualizado; «Semana siguiente» desactivada; EUR y USD sin sumar.

## 7. La demo mostrará «desactualizado»

El perfil `pipelines` de Compose (el servidor de Prefect y el worker con el cron semanal) **no arranca con `docker compose up`**. Con el perfil apagado, nada recalcula el reporte: la última corrida de la demo es la del 2026-11-12, así que **pasados 8 días el dashboard mostrará «Los datos pueden estar desactualizados…»**. **Es el comportamiento esperado**, no un fallo: es la señal que añadió esta Parte (`PIPELINE_DESIGN.md` §6, pregunta 7). Para que deje de salir, hay que levantar el perfil (`docker compose --profile pipelines up -d`) o correr `python data/pipelines/pipeline.py`, **contra la demo solo con la confirmación del usuario**.

**Tras el merge, reconstruir la imagen `nexova-pipeline`** (`docker compose --profile pipelines build`, que solo construye la imagen y no arranca nada): el worker monta el código del host, pero la imagen lleva una copia de `data/pipelines` y de `data/process` que usan los `docker run` de los READMEs. Sin reconstruirla, esas órdenes ejecutan la versión anterior. **Arrancar el perfil `pipelines` contra la demo es una decisión aparte** (con `up` arrancaría Prefect y el worker con el cron activo): ese perfil sigue apagado a propósito, y solo se arranca con la confirmación del usuario.

## 8. Lo no verificado

- **Volúmenes por encima de 50 000 eventos por semana** y la palanca de §4.6 (envolver `kept` de forma opaca), que no está implementada.
- **`EventBatch` con una versión de Prefect distinta de 3.9.** El test de guardia lo detectaría, pero no se ha probado con otra.
- **Un worker real con los subflows** (perfil `pipelines` con servidor propio): los subflows se verificaron con el servidor temporal del script y con `prefect_test_harness`. Hay que reiniciar el worker tras el merge y reconstruir la imagen.
- **Navegadores distintos de Chrome** y el lector de pantalla (los textos de estado usan `role="status"` y `role="alert"`, sin probarlos con uno).
- **El formato de la hora de la franja** (`dateStyle: long`, `timeStyle: short`, `es-ES`) muestra «0:51», no «00:51».
- **Con la base apagada del todo**, el dashboard muestra el 503 de la API; el fallo de la corrida programada sigue constando solo en Prefect, y la señal de «desactualizado» es la que lo delata (§7).

## 9. Limpieza

```powershell
docker rm -f nexova-pipeline-pg
Remove-Item Env:DATABASE_URL, Env:EPHEMERAL_DATABASE_URL, Env:PIPELINE_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

`data/raw/business_performance/` y `data/eval/business_performance/` (caché y snapshots de las corridas) están ignorados por git y se pueden borrar.

## 10. Criterios de «Qué vamos a evaluar»: dónde se cumple cada uno

`company-BRIEFING.md` del enunciado es, en el repo, [`docs/proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md`](../proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md) (el BRIEFING; su copia en inglés se llama `nexova-pipeline-BRIEFING.md`). Los números de línea son los de la rama `feature/business-pipeline-subflows` en el commit de esta Parte.

| # | Criterio | Dónde se cumple |
|---|---|---|
| 1 | El flow principal invoca al menos 3 subflows (`@flow`) en lugar de contener la lógica | El flow `weekly_office_program_performance` ([`pipeline.py:571`](../../data/pipelines/pipeline.py)) llama a **4** subflows: `extract_telemetry_events` (`:608`), `transform_weekly_kpis` (`:611`), `load_weekly_office_program_performance` (`:619`, `return_state=True`) y `snapshot_weekly_performance` (`:629`, `return_state=True`). Los subflows son `@flow` en `:479`, `:487`, `:519` y `:528`. En la ejecución real salen 4 `Beginning subflow run`. Test: `test_subflows.py` → `DeclarationTests` |
| 2 | Cada subflow tiene inputs y outputs explícitos y se puede ejecutar de forma independiente | Firmas tipadas en `pipeline.py:480`, `:488`, `:520` y `:529`; salidas `ExtractionResult` y `LoadOutcome` en [`weekly_performance.py`](../../data/process/weekly_performance.py). La conexión a la base no es un dato (se resuelve dentro, por qué en `PIPELINE_DESIGN.md` §4.1 y §4.3). Independencia, sin pasar por el flow principal ni por `main()`: `test_subflows.py` → `StandaloneTests` (`test_transform_runs_alone_without_a_database`, `test_snapshot_runs_alone_without_a_database`, `test_extract_runs_alone_with_a_repository` y `test_load_runs_alone_with_an_existing_run`) y el ejemplo de `data/pipelines/README.es.md` |
| 3 | `tests/pipelines/test_pipeline.py` existe y tiene al menos 3 tests unitarios de tasks de transformación | [`tests/pipelines/test_pipeline.py`](../../tests/pipelines/test_pipeline.py): 12 tests. Los de una task por KPI: `test_total_material_cost_sums_unit_cost_times_quantity` (`:40`), `test_kits_delivered_counts_orders_not_units` (`:49`), `test_shortage_events_count_counts_threshold_crossings_per_week` (`:59`) y `test_cost_variance_events_count_counts_variations_per_cell` (`:71`) |
| 4 | Los tests corren en aislamiento: fixtures in-memory con forma de telemetría, sin base de datos en vivo ni APIs externas | [`tests/pipelines/conftest.py`](../../tests/pipelines/conftest.py): `telemetry_row` construye filas con las columnas de `telemetry_events` (`event_id`, `event_type`, `timestamp`, `service`, `schema_version`, `tags`) y `extracted` aplica la misma proyección que la SQL de §2.3. Las tasks se llaman con `.fn` (sin motor ni servidor de Prefect). El archivo no importa nada de conexión ni de red; pasa también dentro de la imagen sin red hacia la base |
| 5 | Al menos un test verifica el comportamiento defensivo de una task ante un input inválido | `test_malformed_events_are_rejected_not_crashing` (`:179`: 9 registros mal formados, 0 filas, `rows_rejected == 9`), `test_wrong_types_are_rejected_not_crashing` (`:198`: `quantity` entero, `unit_cost` flotante y `order_id` nulo) y `test_empty_input_means_no_rows` (`:210`). Cambio de comportamiento que lo permite: `PIPELINE_DESIGN.md` §2.5 (H4) |
| 6 | Al menos un test valida el valor de un KPI contra su definición en el BRIEFING | `test_week_report_matches_hand_calculation` (`:92`): el cálculo a mano, con las definiciones del BRIEFING §4 en un comentario (Valencia: 10 × 18,50 + 5 × 20,00 = **285,00 EUR**, 4 kits, 1 escasez, 1 variación; Miami: 3 × 40,00 = **120,00 USD**, 2 kits). También `test_total_material_cost_sums_unit_cost_times_quantity` (4 × 12,50 + 2 × 3,25 = 56,50) |
| 7 | `python -m pytest tests/pipelines/test_pipeline.py` pasa sin errores | **12 passed**, en el venv de `data/pipelines` y en la imagen `nexova-pipeline` (sección 4 de esta guía). Con la fórmula del costo cambiada fallan 2 (la prueba de mutación de la sección 4) |
| 8 | Tras el refactor, `python data/pipelines/pipeline.py` sigue corriendo el ETL completo (entrypoint de la Parte 2 preservado) | `__main__` (`pipeline.py:756`), `main()` (`:705`), los códigos de salida 0/1/2 (`:97` y `:98`) y `--week-start`, `--from` y `--to` (`:698` a `:700`) sin cambios; `PIPELINE_DESIGN.md` §4.5 sigue válido. Ejecución real **sin argumentos** contra el efímero: salida 0, `completed`/`done`, 4 subflows, `pipeline-check.sql` con 0 diferencias. Tests: los 18 de `test_config_and_cli.py` y `test_flow.py` (la Parte 2, con los de caché y reintentos adaptados a las tasks por KPI) |
| 9 | Los nombres de subflows, tasks y tests reflejan el vocabulario de dominio y los KPI del BRIEFING | Subflows: `extract_telemetry_events`, `transform_weekly_kpis`, `load_weekly_office_program_performance` y `snapshot_weekly_performance` (nombres de la tabla de origen y del destino). Tasks: `compute_total_material_cost`, `compute_kits_delivered_count`, `compute_shortage_events_count` y `compute_cost_variance_events_count` (las columnas de BRIEFING §4). Tests con nombres de dominio (`…counts_orders_not_units`, `…never_mixed`, `…unassigned_bucket`). Lo fija `test_subflows.py` → `test_kpi_tasks_are_named_after_the_briefing_columns` |
| 10 | `telemetry_events` y `services/telemetry/analysis.py` no se modifican | `git diff main -- services/telemetry` vacío (0 líneas); `git diff main --stat -- services` vacío. `telemetry_events` se lee solo (`business_performance/repository.py` no se toca) y el seed y las pruebas de escritura solo fueron contra el efímero |
| 11 | Hay un dashboard en `uis/backoffice/` con cada KPI de «KPIs a medir», etiquetado, alimentado desde un endpoint de `services/reporting/` | Página [`app/reporting/page.tsx`](../../uis/backoffice/app/reporting/page.tsx); los 4 KPI con el nombre literal del BRIEFING §2 en [`lib/reporting-format.ts:52`](../../uis/backoffice/lib/reporting-format.ts) (`KPIS`: Costo de material por oficina/programa, Kits entregados, Frecuencia de escasez y Frecuencia de variación de costo), pintados por [`components/reporting/kpi-block.tsx:6`](../../uis/backoffice/components/reporting/kpi-block.tsx). Datos de `GET /reporting/weekly-office-program-performance` ([`services/reporting/router.py:93`](../../services/reporting/router.py)) por [`services/reporting.service.ts:24`](../../uis/backoffice/services/reporting.service.ts). Tests: `reporting-format.test.ts:46` («lleva los cuatro nombres del BRIEFING, en orden») y `tests/reporting.test.mjs` |
| 12 | El dashboard es legible para un stakeholder de negocio no técnico | Frases del BRIEFING como subtítulo de cada KPI, el período («Semana del lunes … al domingo …»), «Sin programa asignado» en lugar de `_unassigned`, Valencia y Miami lado a lado (la moneda, solo en el costo) con la nota de que no se suman, y estados sin jerga (`reportingErrorCopy`, probado: `reporting-format.test.ts:237`, sin códigos, guiones bajos ni números). Reglas estáticas: `production-source.test.mjs:708` (ni centinela, ni fase, ni `error_class` en pantalla). Capturas de escritorio y 375 px del recorrido y la lista de estados en la sección 6 de esta guía; audiencia: Laura (CEO) y Elena (L&D), BRIEFING §1 |
