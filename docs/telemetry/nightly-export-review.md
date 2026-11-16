# DEV-53 — Job nocturno de telemetría: guía de revisión

Cómo arrancar el entorno de pruebas, reproducir cada caso, qué no está verificado y cómo limpiar. **Todo es contra un Postgres efímero; nada contra la demo.** El porqué de cada decisión está en [`nightly-export-analysis.md`](./nightly-export-analysis.md) (M1–M19); esta guía es el «cómo se comprueba».

## 1. Qué hay y dónde

| Pieza | Ruta |
|---|---|
| Control de estado: `ops.job_runs`, `run_job`, lock, barrido de zombis, migración | [`services/job_runner/`](../../services/job_runner/README.md) |
| El script (CSV, subproceso del pipeline, `TARGET_DATE`, SIGTERM) | [`scripts/nightly_export.py`](../../scripts/nightly_export.py) |
| Disparador: etapa `scheduler` (supercronic v0.2.51, usuario no root) | [`data/Dockerfile`](../../data/Dockerfile), [`data/nightly.crontab`](../../data/nightly.crontab) |
| Servicio `nightly-scheduler` (perfil `nightly`, apagado por defecto) | [`docker-compose.yml`](../../docker-compose.yml) |
| Cron `weekly` de Prefect retirado (M5) | [`serve.py`](../../data/pipelines/business_performance/serve.py), [`PIPELINE_DESIGN.md`](../../data/pipelines/PIPELINE_DESIGN.md) §4.5 |
| Tests (189 + 86) | `services/job_runner/tests/`, `data/pipelines/tests/test_trigger_and_serve.py` |

## 2. Arranque del efímero

Desde la raíz, en PowerShell. Las contraseñas son GUID que no se imprimen ni se guardan en el repo.

```powershell
$su  = [guid]::NewGuid().ToString('N')
$app = [guid]::NewGuid().ToString('N')
docker run -d --name nexova-jobrunner-pg -p 127.0.0.1:55433:5432 -e POSTGRES_PASSWORD=$su postgres:17.6-alpine3.22
docker exec nexova-jobrunner-pg pg_isready -U postgres -h 127.0.0.1          # repetir hasta «accepting connections»
docker exec nexova-jobrunner-pg psql -q -U postgres -c "CREATE ROLE nexova_app LOGIN NOSUPERUSER PASSWORD '$app'"
docker exec nexova-jobrunner-pg psql -q -U postgres -c "CREATE DATABASE nexova_test OWNER nexova_app"
# Roles vacíos de Supabase, para que la comprobación de privilegios sea real:
docker exec nexova-jobrunner-pg psql -q -U postgres -c "CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;"
$env:DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:55433/nexova_test"
```

Tablas de origen y migraciones (con el venv de `services/api`, o con el contenedor si Windows bloquea el venv: `services/api/TESTING.md` §14). Cada migración se prueba con `--dry-run` y dos veces (la segunda dice «Nada que migrar»):

```powershell
Push-Location services\api
.\.venv\Scripts\python -c "import os; from sqlmodel import SQLModel; import app.modules.inventory.models; from app.modules.inventory.database import build_engine; SQLModel.metadata.create_all(build_engine(os.environ['DATABASE_URL']))"
.\.venv\Scripts\python -m app.modules.telemetry.migrate
Pop-Location
Push-Location data\pipelines; ..\..\services\api\.venv\Scripts\python -m business_performance.migrate; Pop-Location
Push-Location services
..\services\api\.venv\Scripts\python -m job_runner.migrate --dry-run   # la SQL real de ops.job_runs
..\services\api\.venv\Scripts\python -m job_runner.migrate
..\services\api\.venv\Scripts\python -m job_runner.migrate             # «Nada que migrar»
Pop-Location
```

Seed ficticio (22 eventos del 2026-10-20 al 2026-11-09; una sola vez) y un evento ficticio con identificadores, para comprobar que no salen en el CSV:

```powershell
Get-Content docs\reporting\pipeline-seed-ephemeral.sql -Raw | docker exec -i nexova-jobrunner-pg psql -q -U nexova_app -d nexova_test -v ON_ERROR_STOP=1
docker exec nexova-jobrunner-pg psql -q -U postgres -d nexova_test -c "INSERT INTO telemetry_events (event_id, event_type, timestamp, service, user_id, session_id, schema_version, tags) VALUES ('00000000-0000-4000-9000-000000000999','user_role_changed','2026-10-27 12:00:00+00','backoffice','11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','1.0.0','{""target_user_id"":""33333333-3333-4333-8333-333333333333"",""from_role"":""user"",""to_role"":""admin"",""supplier_key"":""aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa""}')"
```

Eventos por día UTC del seed (para elegir fechas): 10-20 (3), 10-21 (2), 10-22 (1), 10-23 (2), **10-27 (3 + 1 ficticio)**, 10-28 (1), 10-29 (2), 10-30 (2), 11-01 (1), 11-02 (1), 11-04 (2), 11-05 (1), 11-10 (1). **Sin eventos:** 10-24, 10-25, 10-26, 10-31, 11-03.

### Ejecutar el script como lo hace el contenedor

El script corre en la imagen `nexova-pipeline:dev` (la que tiene Prefect), **sin `.env`**, compartiendo la red del Postgres (así el host es `127.0.0.1`, como en las guías de la Parte 3). Una función de ayuda:

```powershell
$raw = "$env:TEMP\nightly-raw"; New-Item -ItemType Directory -Force $raw | Out-Null
function Invoke-Nightly($name, $date) {
  $env:DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:5432/nexova_test"   # dentro de la red compartida
  $env:TARGET_DATE  = $date
  docker run --rm --name $name --network container:nexova-jobrunner-pg -e DATABASE_URL -e TARGET_DATE `
    -v "${PWD}/scripts/nightly_export.py:/scripts/nightly_export.py:ro" -v "${PWD}/services/job_runner:/services/job_runner:ro" `
    -v "${raw}:/data/raw" -w / nexova-pipeline:dev python /scripts/nightly_export.py
}
$q = { param($sql) docker exec nexova-jobrunner-pg psql -U postgres -d nexova_test -c $sql }
```

## 3. Reproducir cada caso

Salidas del script: **0** completed, skipped o locked; **1** failed; **2** configuración o entorno (sin fila). Cada línea de log: `timestamp LEVEL job=… status=… target_date=…`.

| Caso | Cómo | Qué debe verse |
|---|---|---|
| **a) Corrida correcta** | `Invoke-Nightly nx-a 2026-10-27` | Log `pending → processing → csv written rows=4 → pipeline start week=2026-10-26 → completed`, salida 0. `& $q "select * from ops.job_runs"`: una fila `completed`. `reporting.pipeline_runs`: una corrida `completed` de la semana 2026-10-26. El CSV (`$raw\telemetry_2026-10-27.csv`) tiene 4 filas de datos = `select count(*) from telemetry_events where "timestamp" >= '2026-10-27 00:00+00' and "timestamp" < '2026-10-28 00:00+00'`. **No** aparecen `supplier_key`, `target_user_id`, `user_id`, `session_id` ni sus valores (`Select-String` de cada uno: 0 coincidencias; la tabla sí los tiene) |
| **b) Misma fecha** | `Invoke-Nightly nx-b 2026-10-27` | `status=skipped … already_completed`, salida 0; sin fila nueva, sin corrida nueva en `pipeline_runs`, CSV con el mismo `LastWriteTime` y el mismo hash |
| **c) Dos a la vez** | Dos `Start-Job` o dos terminales que llamen a `Invoke-Nightly` con `2026-10-22` a la vez | Una instancia completa; la otra pierde el claim, borra su fila `pending` y sale con `status=locked … another_instance_processing`, salida 0. Una sola fila `completed` y una sola corrida del pipeline |
| **d) Fallo real** | `& $q "REVOKE INSERT, UPDATE ON reporting.pipeline_runs FROM nexova_app"` y `Invoke-Nightly nx-d 2026-10-23`; después `& $q "GRANT INSERT, UPDATE ON reporting.pipeline_runs TO nexova_app"` | El pipeline falla con `permission denied` (~20 s por los reintentos de `start_run`); log ERROR `status=failed … PipelineError: pipeline exited with code 1`, salida 1; la fila queda `failed` con ese mensaje y **ninguna** `processing`. Tras restaurar, el reintento de la misma fecha completa y omite el CSV ya escrito |
| **e) Zombi real** | `Invoke-Nightly` con `docker run -d` (sin `--rm`) para `2026-10-28`; en cuanto la fila esté `processing` y pasen ~4 s, `docker kill -s KILL nx-e`. Después: `& $q "UPDATE ops.job_runs SET started_at = started_at - interval '50 minutes' WHERE status='processing'"` y otra corrida | La fila queda `processing` (salida 137 del contenedor). Con menos de 45 min, la siguiente corrida sale `locked`. Con 50 min, el barrido la pasa a `failed` (`Abandoned: processing for more than 45 minutes…`) y la corrida nueva completa. Borrar el contenedor: `docker rm nx-e` |
| **f) Día sin eventos** | `Invoke-Nightly nx-f 2026-10-31` | CSV con **solo la cabecera** (1 línea), `rows=0`, `completed` |
| **g) `TARGET_DATE` inválida** | `2026-13-01`, `20261015`, `2026-W44-1`, hoy, mañana, `2099-01-01`, `2026-06-01`, `garbage` | Salida 2 en todas, mensaje fijo a stderr (sin repetir el valor) y una línea `status=rejected target_date=-`; **ninguna fila nueva** y sin conectar a la base |
| **Sin `TARGET_DATE`** | `$env:TARGET_DATE=''` | Toma ayer en UTC; el 2026-11-16 fue `2026-11-15`, semana `2026-11-09` |

### Si un caso falla con `Timed out while attempting to connect to ephemeral Prefect API server`

Es el arranque del servidor temporal de Prefect (el subproceso del pipeline lo levanta en cada corrida), no el job. Prefect 3.9.2 le da **20 s por defecto** (`PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS`) y en una máquina normal tarda **18–21 s**; en la del usuario, 18,1 / 19,8 / 20,2 / 20,7 s, y una corrida del caso c falló por eso (la fila quedó `failed`, el reintento completó). Desde la corrección del 2026-11-16, `business_performance/_bootstrap.py` fija **90 s** con `setdefault` (una variable ya puesta se respeta), así que **hay que usar una imagen reconstruida**: `docker compose --profile pipelines build` (y `--profile nightly build` para el scheduler), sin `up`. Para comprobarlo: el caso c con la imagen nueva completa la ganadora y la perdedora sale `locked`; con la variable fijada a `20` (`-e PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=20`) y la CPU limitada (`docker run --cpus 0.25 …`), el arranque tarda ~36 s y la corrida falla con ese error. Detalle y tiempos en `data/pipelines/PIPELINE_DESIGN.md` §4.5.

### Los tres disparos (supercronic)

Construir la imagen (solo construye; no arranca nada) y probarla con un crontab de prueba **que no se versiona**, montado encima del real:

```powershell
docker compose --profile nightly build nightly-scheduler
Set-Content "$env:TEMP\test-every-minute.crontab" "CRON_TZ=UTC`n* * * * * python /scripts/nightly_export.py"
$env:DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:5432/nexova_test"
docker run -d --name nx-sched --init --network container:nexova-jobrunner-pg -e DATABASE_URL -e TARGET_DATE=2026-10-30 `
  -v "$env:TEMP\test-every-minute.crontab:/etc/nexova/nightly.crontab:ro" -v "${raw}:/data/raw" nexova-nightly-scheduler:dev
# Para alargar la corrida de forma realista (la carga del pipeline espera este lock):
docker exec nexova-jobrunner-pg psql -q -U postgres -d nexova_test -c "BEGIN; LOCK TABLE reporting.weekly_office_program_performance IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(135); COMMIT;"
docker logs -t nx-sched      # ~3 min después
docker stop nx-sched; docker rm nx-sched
```

Esperado, uno por minuto: disparo 0 → `completed`; disparo 1, con el 0 aún en marcha → aviso `overlapping jobs: job is still running…` y `status=locked`; disparo 2 → `status=skipped … already_completed`. La expresión real, `0 2 * * *`, se valida con `docker run --rm --entrypoint supercronic nexova-nightly-scheduler:dev -test /etc/nexova/nightly.crontab` («crontab is valid», «TZ: UTC»).

Otras comprobaciones: `docker run --rm --entrypoint id nexova-nightly-scheduler:dev` (uid 10001, no root); el build con checksum incorrecto falla: `docker build --target scheduler --build-arg SUPERCRONIC_SHA256_AMD64=0000…0000 --build-context packages=packages --build-context scripts=scripts --build-context services=services data` (`/supercronic: FAILED`, salida 1).

### Estado final esperado de `ops.job_runs` tras los casos de esta guía

Una fila `completed` por fecha (10-22, 10-23, 10-27, 10-28, 10-30, 10-31 y la del día por defecto), más dos `failed` (10-23 con `PipelineError …code 1` y 10-28 con `Abandoned…`), y **ninguna `processing` ni `pending`**.

## 4. Tests

Dentro de la imagen, sin `.env` (los 189 de `job_runner` y el script; los 86 de `data/pipelines` con Postgres, 0 omitidos). Usan una base aparte, `nexova_suite_test`, porque los de integración borran y recrean el esquema `ops`:

```powershell
docker exec nexova-jobrunner-pg psql -q -U postgres -c "CREATE DATABASE nexova_suite_test OWNER nexova_app"
$env:JOB_RUNNER_TEST_DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:5432/nexova_suite_test"
docker run --rm --network container:nexova-jobrunner-pg -e JOB_RUNNER_TEST_DATABASE_URL `
  -v "${PWD}/services/job_runner:/services/job_runner:ro" -v "${PWD}/services/api/app:/services/api/app:ro" `
  -v "${PWD}/scripts/nightly_export.py:/scripts/nightly_export.py:ro" -v "${PWD}/docs/telemetry/event-schemas.json:/docs/telemetry/event-schemas.json:ro" -v "${PWD}/.gitignore:/.gitignore:ro" `
  -w /services nexova-pipeline:dev python -m unittest discover -s /services/job_runner/tests -t /services
```

Los de `data/pipelines`: `services/job_runner/tests` no los necesita; ver la fila de `data/pipelines/` de `AGENTS.md` §4 (con `PIPELINE_TEST_DATABASE_URL` apuntando a un Postgres local) y `README.es.md` del pipeline para los montajes en la imagen. Sin esas variables los de Postgres se omiten con su motivo: **la verificación de esta rama es con las dos puestas, 0 omitidos**.

## 5. Criterios de «Qué evaluaremos»

| # | Criterio del enunciado | Dónde se cumple | Prueba |
|---|---|---|---|
| 1 | El script es un proceso independiente: no importa ni ejecuta FastAPI ni el `main` de la app | `scripts/nightly_export.py` y `services/job_runner/` sin ningún import de `fastapi`, `starlette`, `uvicorn`, `sqlmodel` ni `app`; servicio de Compose propio, sin puertos | `test_architecture.py`: importar el paquete y el script en un proceso limpio (`-I`) no carga `fastapi`, `starlette`, `uvicorn`, `sqlmodel`, `app` ni `app.main` (tampoco Prefect), análisis AST, y la API sin `apscheduler`/`repeat_every`; evidencias `log_a.txt` (corre en su propia imagen) |
| 2 | Máquina de estados `pending → processing → completed \| failed` y filas con el estado real y `target_date` | `services/job_runner/runner.py`, `repository.py` (transiciones *compare-and-set*), DDL en `migrate.py` | `cases.py` (SQLite y PostgreSQL), `test_nightly_export_main.py`; estado final de `ops.job_runs` (8 filas) en `nightly-export-review.md` §3 |
| 3 | `processing` como lock distribuido, sin mecanismo aparte; dos instancias a la vez | Índice único parcial `ux_job_runs_one_processing` (`UNIQUE (job_name) WHERE status = 'processing'`): es la propia columna `status` con una restricción | `test_two_simultaneous_claims_exactly_one_wins_the_lock` (25 rondas, dos conexiones) y `test_two_simultaneous_instances_one_completes_and_the_other_aborts`; caso c en procesos reales (`log_c_1.txt`, `log_c_2.txt`); disparo `locked` de supercronic (`log_scheduler.txt`) |
| 4 | Idempotente por `target_date`: dos ejecuciones el mismo día = una, sin duplicar CSV ni pipeline | `has_completed_for_date`, re-comprobación tras el claim, `ux_job_runs_one_completed_per_day`, CSV que no se sobrescribe | Caso b (mismo hash y `mtime`, sin corrida nueva), disparo `skipped`; tests de omisión y de la carrera «completa justo antes del claim» |
| 5 | Ningún registro queda `processing` tras un fallo | `run_job`: `except BaseException` → `failed`; `SIGTERM` convertido en excepción; barrido a los 45 min para lo que ningún `finally` cubre | Casos d y e; `test_no_row_is_left_processing_after_any_failure`, `KeyboardInterrupt`/`SystemExit`, `test_sigterm_leaves_the_row_failed`, fallo al escribir `failed` con reintentos y barrido |
| 6 | CSV en `data/raw/` con nombre correcto y datos de `telemetry_events`; el pipeline lee de la BD | `export_csv` → `data/raw/telemetry_YYYY-MM-DD.csv` (UTC, `[00:00, 24:00)`, `.part` + `os.replace`); el pipeline lee `telemetry_events` por SQL | Caso a (4 filas = `COUNT`), caso f (cabecera sola), tests de límites, orden y atomicidad, `test_the_pipeline_never_reads_the_csv_export` |
| 7 | `job_runs` y `pipeline_runs` coexisten sin duplicar responsabilidades | Esquemas distintos (`ops` y `reporting`), sin FK ni columnas compartidas; una registra la orquestación y la otra las fases del ETL | Estado final de ambas tablas tras los casos (8 filas de `job_runs`, corridas de `pipeline_runs` por semana); análisis B.1 |
| 8 | Logs con timestamp, nombre del job y estado en cada evento relevante | `services/job_runner/logs.py`: `timestamp LEVEL job=… status=… target_date=…`, siempre redactado | `LINE` (regex) aplicada a cada línea en `cases.py` y `test_nightly_export_main.py`; logs de las evidencias |
| 9 | Disparador configurado y expresión cron documentada | `data/nightly.crontab` (`CRON_TZ=UTC`, `0 2 * * *`), `nightly-scheduler` en `docker-compose.yml` (perfil `nightly`), supercronic v0.2.51 con SHA-256 verificado | `supercronic -test`; disparos reales cada minuto; build con checksum incorrecto que falla; cuerpo de la PR |
| 10 | `TARGET_DATE` permite fechas arbitrarias sin cambiar código | `resolve_target_date` (regex estricta, días cerrados, retención) | `test_nightly_export_target_date.py`; casos a (10-27), b, c, d, e, f (fechas distintas) y g (inválidas, salida 2 sin fila) |

## 6. Lo que NO está verificado

- **La demo:** `ops.job_runs` **no está migrado** en la demo, y el perfil `nightly` **no se ha arrancado nunca contra ella**. Cuando se decida, primero `python -m job_runner.migrate --dry-run` y después con `--allow-demo`, solo con la confirmación del usuario.
- **Supabase real:** RLS y `REVOKE` se probaron en un Postgres 17 con los tres roles de Supabase creados y con privilegios por defecto simulados; no contra el Transaction pooler (puerto 6543) ni con los privilegios reales de Supabase.
- **El disparo real a las 02:00 UTC:** la expresión se validó con `supercronic -test` y el mecanismo con un crontab cada minuto; no se esperó a las 02:00.
- **arm64:** el SHA-256 de `supercronic-linux-arm64` coincide con el digest de GitHub y con la descarga, pero la imagen solo se construyó para amd64.
- **Windows como host del script:** todo se ejecutó en Linux (imagen). La muerte del árbol de procesos en Windows (`taskkill /T`) no se ejecutó (el venv de `data/pipelines` está bloqueado por el Control de aplicaciones).
- **`docker stop` durante una corrida:** solo se vio con el scheduler inactivo («waiting for jobs to finish», salida 0); el camino `SIGTERM → failed` del script se probó con tests, no con una parada real a mitad de corrida.
- **Un servidor de Prefect que ya tuviera el deployment `weekly`:** `serve()` ya no lo declara, pero no se comprobó si Prefect lo retira de un servidor donde ya estaba registrado; el de la demo está apagado y habría que borrarlo en su UI si existiera.
- **Linux como host de Compose:** el uid 10001 del contenedor debe poder escribir en `data/raw` del host (en Docker Desktop no hizo falta).
- **PowerShell:** los comandos de esta guía están adaptados desde los ejecutados en Git Bash; la sintaxis PowerShell no se ejecutó literalmente.

## 7. Limpieza

```powershell
docker rm -f nexova-jobrunner-pg nx-sched nx-e 2>$null    # el efímero y los contenedores de prueba
Remove-Item "$env:TEMP\test-every-minute.crontab", "$env:TEMP\nightly-raw" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Variable su, app -ErrorAction SilentlyContinue; Remove-Item Env:DATABASE_URL, Env:TARGET_DATE, Env:JOB_RUNNER_TEST_DATABASE_URL
```

Las bases `nexova_test` y `nexova_suite_test` desaparecen con el contenedor. `docker images` conserva `nexova-nightly-scheduler:dev` (se borra con `docker rmi`).

## 8. Arrancar el perfil `nightly` (decisión aparte, nunca por defecto)

`docker compose up` **no** lo arranca. `DATABASE_URL` sale del `.env` de la raíz, que apunta a la **demo**, así que arrancarlo así es una decisión que se toma en el momento y con confirmación:

```powershell
docker compose --profile nightly up -d nightly-scheduler     # solo con la confirmación del usuario, tras migrar ops en esa base
docker compose --profile nightly logs -f nightly-scheduler
docker compose --profile nightly stop nightly-scheduler
```

Para probarlo contra otra base, un override de Compose o un `docker run` como el de la sección 3, que no se versiona.

## 9. Tras el merge

Reconstruir las imágenes **sin arrancar nada** (con `up` arrancaría Prefect y el worker, o el scheduler, contra la demo):

```powershell
docker compose --profile pipelines build
docker compose --profile nightly build
```
