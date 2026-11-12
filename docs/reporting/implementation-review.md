# Pipeline de desempeño de negocio: guía de revisión (F1)

Guía para repetir la verificación del ticket «Data Pipelines — Parte 2». Decisiones en [`implementation-analysis.md`](./implementation-analysis.md); diseño en [`data/pipelines/PIPELINE_DESIGN.md`](../../data/pipelines/PIPELINE_DESIGN.md). Cubre la **parada 2** (el pipeline en un Postgres efímero, §2), la **parada 3** (el disparo manual de punta a punta, §4) y el **plan de la parada 4** (la demo, §6: solo con la confirmación del usuario).

> **Analítica de Prefect (corrección tras la parada 2).** La primera corrida del usuario mostró el aviso «Prefect collects anonymous usage data… set PREFECT_SERVER_ANALYTICS_ENABLED=false on the server, or DO_NOT_TRACK=1 in the client». La causa es que Prefect 3.9.2 tiene **dos interruptores**. `PREFECT_SERVER_ANALYTICS_ENABLED=false` ya estaba puesto, pero solo apaga la del servidor. La del cliente (SDK) solo se apaga con `DO_NOT_TRACK=1`, y su aviso sale al importar Prefect en una terminal interactiva, antes de comprobar el ajuste del servidor (`prefect/_internal/analytics/__init__.py`). Por ese mismo código, el evento de esa primera corrida se descarta porque el ajuste local del servidor estaba en `false`; no se ha verificado a nivel de red.
>
> **Ahora están desactivadas en todos los modos:**
> - **Código:** `business_performance/_bootstrap.py` **fuerza** las dos variables (no `setdefault`) antes de importar Prefect. Lo importan `pipeline.py`, `serve.py`, `secret.py`, `repository.py`, `migrate.py` y la suite.
> - **Imagen y Compose:** `data/Dockerfile` y los servicios `prefect-server` y `pipeline-worker` fijan las mismas dos.
> - **Test:** [`tests/test_analytics_off.py`](../../data/pipelines/tests/test_analytics_off.py) comprueba los dos interruptores en el proceso. También comprueba un subproceso que arranca con `DO_NOT_TRACK=0` y la analítica del servidor en `true`: los dos quedan apagados y no aparece el aviso. Y comprueba la imagen y los dos servicios.
>
> El aviso de la primera vez dejó una marca en `~/.prefect/.sdk_telemetry/notice_shown`, fuera del repo; no se ha tocado.

## 1. Qué hay en la parada 2

| Pieza | Dónde |
|---|---|
| Flow `weekly_office_program_performance`, backfill y 9 tasks | [`data/pipelines/pipeline.py`](../../data/pipelines/pipeline.py) |
| Transformación pura (§2.5) y semanas | [`data/process/weekly_performance.py`](../../data/process/weekly_performance.py) |
| SQL de extracción, carga y log | [`data/pipelines/business_performance/repository.py`](../../data/pipelines/business_performance/repository.py) |
| Origen de `DATABASE_URL` (entorno → `.env`, solo el host en pantalla) | [`business_performance/config.py`](../../data/pipelines/business_performance/config.py) |
| Migración del esquema `reporting`, con `--allow-demo` | [`business_performance/migrate.py`](../../data/pipelines/business_performance/migrate.py) |
| Nombres compartidos | [`packages/shared/nexova_shared/reporting/`](../../packages/shared/nexova_shared/reporting/vocabulary.py) |
| Seed ficticio y SQL de cuadre | [`pipeline-seed-ephemeral.sql`](./pipeline-seed-ephemeral.sql), [`pipeline-check.sql`](./pipeline-check.sql) |

**Los cuatro puntos que se evalúan:**

| Punto | En el código | Prueba |
|---|---|---|
| Tarea opcional con `return_state=True` que falla y el flow sigue | `write_eval_snapshot` y el bloque «Paso opcional (D7)» del flow | `tests/test_flow.py` → `OptionalStepTests` (el directorio de salida es un fichero): flow `Completed`, corrida `completed`, `quality.optional_steps.eval_snapshot = failed` |
| Caché de `transform_weekly_rows` con su comentario | `transform_cache_key` y el decorador de `transform_weekly_rows` | `CacheTests`: dos corridas → la transformación se ejecuta **una** vez; un evento más → otra vez. En el efímero, la segunda corrida muestra `Cached(type=COMPLETED)` |
| Retries con su comentario | `DB_RETRIES`/`DB_RETRY_DELAY_SECONDS` (2 × 10 s), `LOAD_RETRIES`/`LOAD_RETRY_DELAY_SECONDS` (2 × 30 s), `_retry_transient_only` | `RetryTests`: declarados; un `OperationalError` se reintenta; un `IntegrityError` no |
| Segunda corrida sobre las mismas semanas sin duplicados | Upsert sobre `unique (office, programme_id, week_start)` + borrado de huérfanas (`repository.py`) | `SuccessfulRunTests` y `test_repository_postgres.py`; en el efímero, `duplicated_cells = 0` tras repetir la semana |

Además, el **fallo manejado** de la carga (`return_state=True` en `load_weekly_rows`): `HandledFailureTests`, que termina el flow en `Failed` y la corrida en `failed`/`load`/`OperationalError`, sin tocar la tabla.

## 2. Verificación en el efímero (parada 2)

**Todo en PowerShell, desde la raíz del repo, en la misma terminal** (las variables `$env:` solo viven en ella). Nada contra la demo: el Postgres es de usar y tirar, escucha solo en `127.0.0.1` y el seed se niega a correr fuera de `nexova_test`.

### 2.1 Stack normal fuera de la demo durante la prueba

La API del stack normal apunta a la demo. Se para mientras dura la prueba:

```powershell
docker compose stop
```

### 2.2 Postgres efímero con un rol sin superusuario

```powershell
$su = [guid]::NewGuid().ToString('N')
$app = [guid]::NewGuid().ToString('N')
docker run -d --name nexova-pipeline-pg -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=$su postgres:17.6-alpine3.22
```

Repite hasta ver `accepting connections`:

```powershell
docker exec nexova-pipeline-pg pg_isready -U postgres -h 127.0.0.1
```

```powershell
docker exec nexova-pipeline-pg psql -q -U postgres -c "CREATE ROLE nexova_app LOGIN NOSUPERUSER PASSWORD '$app'"
docker exec nexova-pipeline-pg psql -q -U postgres -c "CREATE DATABASE nexova_test OWNER nexova_app"
$env:DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:55432/nexova_test"
```

### 2.3 Tablas de origen (con el código de la API)

`telemetry_events` con su migración, y las tablas del inventario con su modelo:

```powershell
Push-Location services\api
.\.venv\Scripts\python -c "import os; from sqlmodel import SQLModel; import app.modules.inventory.models; from app.modules.inventory.database import build_engine; SQLModel.metadata.create_all(build_engine(os.environ['DATABASE_URL']))"
.\.venv\Scripts\python -m app.modules.telemetry.migrate
Pop-Location
```

### 2.4 Migración del esquema `reporting`, dos veces

Esperado: la primera línea dice `DATABASE_URL: entorno, host 127.0.0.1`; `--dry-run` lista la SQL, la primera ejecución la aplica y la segunda dice «Nada que migrar».

```powershell
Push-Location data\pipelines
.\.venv\Scripts\python -m business_performance.migrate --dry-run
.\.venv\Scripts\python -m business_performance.migrate
.\.venv\Scripts\python -m business_performance.migrate
Pop-Location
```

### 2.5 Seed ficticio

Una sola vez (una segunda ejecución falla en la clave primaria y no inserta nada). Esperado: `seeded_events = 22`.

```powershell
Get-Content docs\reporting\pipeline-seed-ephemeral.sql -Raw | docker exec -i nexova-pipeline-pg psql -q -U nexova_app -d nexova_test -v ON_ERROR_STOP=1
```

| Semana | Qué tiene |
|---|---|
| 2026-10-19 | Las dos oficinas; dos entradas en Valencia con coste decimal; una escasez en Miami; eventos técnicos |
| 2026-10-26 | Una variación de coste en Valencia; la misma entrada y la misma salida de Miami con dos `eventId`; una salida de Miami el domingo a las 23:59 UTC; una entrada y una salida del inventario (conciliación) |
| 2026-11-02 | Una salida de Valencia el lunes a las 00:00:00 UTC; una salida duplicada en Valencia; una entrada en Miami |
| 2026-11-09 | Una salida en Valencia (semana en curso el 2026-11-10: no entra por defecto) |

### 2.6 El pipeline

La corrida por defecto (la última semana cerrada: la del 2026-11-02 si lo haces entre el 2026-11-09 y el 2026-11-15). Esperado: código de salida 0 y, al final, la línea JSON `pipeline_run_finished` con `"status": "completed"`.

```powershell
data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py
$LASTEXITCODE
```

**Caché y segunda corrida:** repítela en menos de una hora. Esperado: `transform_weekly_rows … Finished in state Cached(type=COMPLETED)` y, en §2.7, la misma tabla sin duplicados.

```powershell
data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py
```

**Backfill** de las tres semanas cerradas (un subflow por semana; la del 2026-11-02 vuelve a salir de la caché):

```powershell
data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py --from 2026-10-19
$LASTEXITCODE
```

### 2.7 KPI cuadrados con SQL a mano

[`pipeline-check.sql`](./pipeline-check.sql) recalcula los 4 KPI con `GROUP BY` sobre `telemetry_events` (sin código del pipeline) y los compara con la tabla en los dos sentidos. Esperado: `missing_or_different = 0`, `unexpected = 0`, `duplicated_cells = 0`.

```powershell
Get-Content docs\reporting\pipeline-check.sql -Raw | docker exec -i nexova-pipeline-pg psql -q -U nexova_app -d nexova_test
```

Valores esperados, calculados a mano con el seed:

| Semana | Oficina | Coste de material | Kits entregados | Escasez | Variación de coste | Moneda |
|---|---|---|---|---|---|---|
| 2026-10-19 | miami | 0 | 2 | 1 | 0 | USD |
| 2026-10-19 | valencia | 147.05 (10 × 12.50 + 3 × 7.35) | 1 | 0 | 0 | EUR |
| 2026-10-26 | miami | 49.95 (5 × 9.99) | 2 (la orden duplicada cuenta 1 + la del domingo) | 0 | 0 | USD |
| 2026-10-26 | valencia | 60.00 (4 × 15.00; la entrada duplicada cuenta 1) | 1 | 1 | 1 | EUR |
| 2026-11-02 | miami | 40.20 (2 × 20.10) | 0 | 0 | 0 | USD |
| 2026-11-02 | valencia | 0 | 2 (la del lunes 00:00 + la duplicada, que cuenta 1) | 0 | 0 | EUR |

Todas con `programme_id = _unassigned`. En el log: `duplicates_collapsed` 0, 2 y 1 para las tres semanas.

### 2.8 Tests, con la integración contra el efímero

`test_repository_postgres.py` prueba la SQL real (inicio idempotente y exclusivo, upsert y huérfanas, `CHECK` de moneda, corridas abandonadas). Usa una semana sin datos del seed y borra solo sus filas. Esperado: `OK`.

```powershell
$env:PIPELINE_TEST_DATABASE_URL = $env:DATABASE_URL
data\pipelines\.venv\Scripts\python -m unittest discover -s data/pipelines/tests -t data/pipelines
python -m unittest discover -s data/process/tests -t data/process
python -m unittest discover -s packages/shared/tests -t packages/shared
```

### 2.9 Esquema ausente

En una base vacía del mismo efímero. Esperado: salida 2, el mensaje con el comando de la migración y ninguna traza.

```powershell
docker exec nexova-pipeline-pg psql -q -U postgres -c "CREATE DATABASE nexova_empty OWNER nexova_app"
$env:DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:55432/nexova_empty"
data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py
$LASTEXITCODE
```

### 2.10 Limpieza

```powershell
docker rm -f nexova-pipeline-pg
Remove-Item Env:DATABASE_URL, Env:PIPELINE_TEST_DATABASE_URL
Remove-Item -Recurse -Force data\raw\business_performance, data\eval\business_performance -ErrorAction SilentlyContinue
docker compose up -d
```

> **Sin `$env:DATABASE_URL`, el pipeline lee la `DATABASE_URL` del `.env` de la raíz, que es la demo** (D5: la corrida no se bloquea). Hoy la demo no tiene el esquema `reporting`, así que terminaría con salida 2 sin escribir nada; aun así, comprueba siempre que la primera línea dice `host 127.0.0.1`.

## 3. Qué hay en la parada 3

| Pieza | Dónde |
|---|---|
| Disparo manual por la REST de Prefect (**solo librería estándar**) | [`data/pipelines/business_performance/trigger.py`](../../data/pipelines/business_performance/trigger.py) |
| Deployments `manual` y `weekly` (cron `0 6 * * 1` `Europe/Madrid`, concurrencia 1) | [`business_performance/serve.py`](../../data/pipelines/business_performance/serve.py) |
| Alta del block `Secret` desde el worker (imprime solo el host) | [`business_performance/secret.py`](../../data/pipelines/business_performance/secret.py) |
| `pipeline-worker` en el perfil `pipelines`, sin `DATABASE_URL`; se reinicia solo si el servidor de Prefect se reinicia | [`docker-compose.yml`](../../docker-compose.yml) |
| La API: solo `business_performance/__init__.py` y `trigger.py` en `/pipelines` (imagen y bind mounts) y `services/reporting` en `/app/api/reporting` | [`services/Dockerfile`](../../services/Dockerfile), `docker-compose.yml` |
| Los 3 endpoints | [`services/reporting/`](../../services/reporting/router.py) |
| `PIPELINE_PREFECT_API_URL` (opcional; sin ella, 503) | `services/api/app/core/config.py`, [`.env.example`](../../.env.example) |
| Reglas de semanas compartidas (lunes, cerrada, retención) por el pipeline y el `POST` | `packages/shared/nexova_shared/reporting/weeks.py` |
| Tests | `services/api/tests/test_reporting_api.py` (contrato, 401/403/404/409/422/503), `test_reporting_architecture.py` (AST: `services/reporting` sin `prefect`/`pandas`/flow; `trigger.py` solo librería estándar; la imagen y Compose solo meten el disparo; Prefect fuera del lock de la API), `data/pipelines/tests/test_trigger_and_serve.py` (`trigger.py` contra la REST real de Prefect en `prefect_test_harness`) |
| Override de verificación (sin secretos) | [`compose-ephemeral.yml`](./compose-ephemeral.yml) |

## 4. Verificación de punta a punta (parada 3)

**En PowerShell, desde la raíz.** Nada contra la demo: el override apunta la API al efímero (`nexova-pipeline-pg`, en la red `nexova-net`) y guarda los usuarios en una TinyDB temporal dentro del contenedor (`/tmp`), no en `services/api/data`.

### 4.1 Montar el entorno (si no está montado)

Si ya lo dejé montado (`docker ps` muestra `nexova-pipeline-pg`, `nexova-api-1`, `nexova-prefect-server-1` y `nexova-pipeline-worker-1`), salta a §4.2. Para montarlo desde cero, en la misma terminal:

```powershell
docker compose stop
$su = [guid]::NewGuid().ToString('N'); $app = [guid]::NewGuid().ToString('N')
docker run -d --name nexova-pipeline-pg --network nexova-net -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=$su postgres:17.6-alpine3.22
docker exec nexova-pipeline-pg pg_isready -U postgres -h 127.0.0.1
```

Repite el `pg_isready` hasta `accepting connections`.

```powershell
docker exec nexova-pipeline-pg psql -q -U postgres -c "CREATE ROLE nexova_app LOGIN NOSUPERUSER PASSWORD '$app'"
docker exec nexova-pipeline-pg psql -q -U postgres -c "CREATE DATABASE nexova_test OWNER nexova_app"
$env:EPHEMERAL_DATABASE_URL = "postgresql://nexova_app:$app@nexova-pipeline-pg:5432/nexova_test"
$env:DATABASE_URL = "postgresql://nexova_app:$app@127.0.0.1:55432/nexova_test"
$c = @('-f', 'docker-compose.yml', '-f', 'docs/reporting/compose-ephemeral.yml', '--profile', 'pipelines')
docker compose @c up -d --build
docker compose @c ps
```

**Antes de seguir, comprueba que la API no apunta a la demo.** Esperado: `nexova-pipeline-pg http://prefect-server:4200/api`.

```powershell
docker compose @c exec api python -c "import os; from urllib.parse import urlsplit; print(urlsplit(os.environ['DATABASE_URL']).hostname, os.environ['PIPELINE_PREFECT_API_URL'])"
```

Tablas de origen (la API ya creó las del inventario al arrancar), esquema `reporting` dos veces, seed y block del worker:

```powershell
docker compose @c exec api python -m app.modules.telemetry.migrate
Push-Location data\pipelines
.\.venv\Scripts\python -m business_performance.migrate
.\.venv\Scripts\python -m business_performance.migrate
Pop-Location
Get-Content docs\reporting\pipeline-seed-ephemeral.sql -Raw | docker exec -i nexova-pipeline-pg psql -q -U nexova_app -d nexova_test -v ON_ERROR_STOP=1
docker compose @c exec -e DATABASE_URL=$env:EPHEMERAL_DATABASE_URL pipeline-worker python -m business_performance.secret
```

Esperado en la última: `Block nexova-supabase-database-url guardado. DATABASE_URL: entorno, host nexova-pipeline-pg`.

### 4.2 Usuarios de prueba y tokens

Un admin y un usuario normal, con contraseñas generadas en la terminal (no se escriben ni se ven). Viven en la TinyDB temporal del contenedor de la API.

```powershell
$B = "http://localhost:8000"
$adminPass = [guid]::NewGuid().ToString('N'); $userPass = [guid]::NewGuid().ToString('N')
docker exec -e PW=$adminPass nexova-api-1 python -c "import os, sys; from app.auth import create_admin; sys.exit(create_admin.run(['--email', 'admin-prueba@example.invalid'], read_password=lambda _: os.environ['PW']))"
Invoke-RestMethod -Method Post -Uri "$B/users" -ContentType "application/json" -Body (@{email="usuario-prueba@example.invalid"; password=$userPass} | ConvertTo-Json)
$admin = (Invoke-RestMethod -Method Post -Uri "$B/auth/login" -Body @{username="admin-prueba@example.invalid"; password=$adminPass}).access_token
$user = (Invoke-RestMethod -Method Post -Uri "$B/auth/login" -Body @{username="usuario-prueba@example.invalid"; password=$userPass}).access_token
```

El admin se crea con el mismo `create-admin` de la API, pasándole la contraseña por una variable del `exec` en lugar del `getpass` interactivo (una tubería desde PowerShell 5.1 puede añadir `\r` a la segunda línea y la confirmación no coincidiría). Esperado: `Administrador creado: admin-prueba@example.invalid`. Si ya creaste esos usuarios en este contenedor, el `create` y el `POST` fallan: haz solo los dos `login`, con las contraseñas de entonces.

Una función para ver el código y el cuerpo de cada respuesta, también de los errores (PowerShell 5.1 lanza en los 4xx/5xx):

```powershell
function Call($Method, $Path, $Token, $Body) {
  $p = @{ Method = $Method; Uri = "$B$Path"; UseBasicParsing = $true; Headers = @{} }
  if ($Token) { $p.Headers.Authorization = "Bearer $Token" }
  if ($Body) { $p.Body = ($Body | ConvertTo-Json); $p.ContentType = "application/json" }
  try { $r = Invoke-WebRequest @p; "$($r.StatusCode) $($r.Content)" }
  catch { if ($_.Exception.Response) { "$([int]$_.Exception.Response.StatusCode) $($_.ErrorDetails.Message)" } else { throw } }
}
```

### 4.3 El recorrido

**Disparo:** admin → `POST /reporting/pipeline-runs`. Esperado: `202 {"prefect_flow_run_id": "…", "status": "scheduled"}`.

```powershell
$post = Call POST /reporting/pipeline-runs $admin @{week_start = "2026-11-02"}; $post
```

**El flow run en Prefect:** abre `http://localhost:4200` → *Runs*. Esperado: un flow run de `weekly_office_program_performance`, deployment `manual`, que pasa a `Completed` en unos segundos. Lleva los parámetros `trigger = manual`, `week_start = 2026-11-02` y `requested_by` (el id del admin, que sale del token), y las tasks de §1 en verde.

> **Espera a `Completed` antes de pedir `/latest`.** El `POST` es asíncrono: el 202 solo dice que el flow run está programado. Si pides `/latest` antes de que empiece, devuelve la corrida **anterior** (verificado por el usuario en la parada 3). Este bucle espera al estado final:

```powershell
$id = ($post.Substring(4) | ConvertFrom-Json).prefect_flow_run_id
do { Start-Sleep 2; $state = (Invoke-RestMethod "http://localhost:4200/api/flow_runs/$id").state_type; $state } until ($state -in 'COMPLETED', 'FAILED', 'CRASHED', 'CANCELLED')
(Invoke-RestMethod "http://localhost:4200/api/flow_runs/$id") | Select-Object name, state_type, parameters
```

**La fila en `pipeline_runs` y `GET latest`** (con el flow run ya en `COMPLETED`). Esperado: `200`, `status = completed`, `phase = done`, `trigger = manual`, el mismo `prefect_flow_run_id`, `rows_upserted = 2` y `quality.optional_steps.eval_snapshot = completed`. **Sin `requested_by`.**

```powershell
Call GET /reporting/pipeline-runs/latest $user
docker exec nexova-pipeline-pg psql -U nexova_app -d nexova_test -c "SELECT trigger, status, phase, week_from, prefect_flow_run_id, requested_by IS NOT NULL AS con_requested_by FROM reporting.pipeline_runs ORDER BY started_at"
```

**Los KPI.** Esperado: `200` con el contrato del BRIEFING: `week_start` y `entries`, ordenadas por oficina. En Miami, `40.2` USD y 0 kits; en Valencia, `0` EUR y 2 kits. Las dos con `programme_id = _unassigned`.

```powershell
Call GET "/reporting/weekly-office-program-performance?week_start=2026-11-02" $user
Call GET /reporting/weekly-office-program-performance $user
```

La segunda, sin `week_start`, devuelve la semana calculada más reciente.

### 4.4 Los casos de error

| Caso | Comando | Esperado |
|---|---|---|
| Sin token | `Call POST /reporting/pipeline-runs $null` | `401` `not_authenticated` |
| No admin | `Call POST /reporting/pipeline-runs $user` | `403` `forbidden` |
| Semana no lunes | `Call POST /reporting/pipeline-runs $admin @{week_start = "2026-11-03"}` | `422` `validation_error` (`week_start must be a Monday`) |
| Semana en curso | `Call POST /reporting/pipeline-runs $admin @{week_start = "2026-11-09"}` (si lo haces entre el 2026-11-09 y el 15) | `422` (`only closed weeks…`) |
| GET con semana no lunes | `Call GET "/reporting/weekly-office-program-performance?week_start=2026-11-03" $user` | `422` |
| Semana no calculada | `Call GET "/reporting/weekly-office-program-performance?week_start=2026-10-19" $user` | `404` `week_not_computed` (salvo que la hayas calculado) |

**Corrida en marcha → 409.** Con el worker parado, el primer disparo se queda `Scheduled` en Prefect y el segundo se rechaza:

```powershell
docker stop nexova-pipeline-worker-1
Call POST /reporting/pipeline-runs $admin
Call POST /reporting/pipeline-runs $admin
docker start nexova-pipeline-worker-1
```

Esperado: `202`, después `409 pipeline_run_in_progress`. Al arrancar el worker, el flow run pendiente se ejecuta (en la UI pasa a `Completed`) y deja su fila en `pipeline_runs` con la última semana cerrada.

**Prefect parado → 503:**

```powershell
docker stop nexova-prefect-server-1
Call POST /reporting/pipeline-runs $admin
Call GET /reporting/pipeline-runs/latest $user
docker start nexova-prefect-server-1
```

Esperado: `503 pipeline_unavailable` en el `POST`, y `200` en el `GET`, que solo lee la base. El log de la API (`docker logs nexova-api-1 --tail 5`) dice `pipeline orchestrator is unavailable: URLError`, sin URL. Al volver el servidor, el worker se reinicia solo en unos segundos (`restart: unless-stopped`; `docker ps` lo muestra `Up`).

**Los KPI cuadrados otra vez**, con todo lo que hayas disparado. Esperado: `missing_or_different = 0`, `unexpected = 0`, `duplicated_cells = 0`.

```powershell
Get-Content docs\reporting\pipeline-check.sql -Raw | docker exec -i nexova-pipeline-pg psql -q -U nexova_app -d nexova_test
```

### 4.5 Limpieza

Vuelve a dejar el stack normal (contra el `.env` de la raíz) y borra el efímero, los volúmenes del perfil y las variables:

```powershell
docker compose --profile pipelines rm -sf prefect-server pipeline-worker
docker rm -f nexova-pipeline-pg
docker volume rm nexova_prefect-data nexova_pipeline-raw nexova_pipeline-eval
Remove-Item Env:EPHEMERAL_DATABASE_URL, Env:DATABASE_URL -ErrorAction SilentlyContinue
docker compose up -d
docker compose ps
```

`docker compose up -d` recrea `api` sin el override: vuelve a la base del `.env` y a sus usuarios de siempre, y los de prueba desaparecen con el contenedor.

## 5. Lo que queda fuera o sin verificar

- **`compose-ephemeral.yml` se versiona:** no lleva secretos (la URL entra por `EPHEMERAL_DATABASE_URL`, con `:?` si falta), lo usan esta guía y `AGENTS.md`, y deja la verificación reproducible sin overrides fuera del repo.
- **Documentación:** `services/api/SPECS.md` Parte I, las filas de `data/process/` y `data/pipelines/` en `AGENTS.md` §4 y el README de `data/process`, ya hechos.
- **Tests en `%TEMP%`:** `prefect_test_harness` deja su SQLite temporal (`prefect-test.db`) en `%TEMP%` en Windows. El `atexit` de Prefect no la puede borrar porque sigue abierta: sale una traza de `PermissionError` después del `OK`, y la suite termina con código 0.
- **Concurrencia entre dos `POST` simultáneos:** los dos podrían pasar la comprobación previa. El segundo flow run falla entonces en `start_run` (`RunInProgressError`, por el índice único parcial) sin tocar la tabla, y además el deployment tiene concurrencia 1. No se ha provocado a mano.
- **Sin verificar:** el cron `weekly` disparándose de verdad un lunes a las 06:00 `Europe/Madrid` (sí está su deployment con esa programación); el tamaño comprimido de las imágenes.

## 6. Plan de la parada 4: la demo (solo con tu «sí»)

**Ejecutado contra la demo el 2026-11-12 con el «sí» del usuario: resultado en §6.7.** Antes, los mismos comandos se ensayaron el 2026-11-11 en un Postgres efímero que imita Supabase. Tenía los roles `anon`, `authenticated` y `service_role` con privilegios por defecto en las tablas nuevas, y salió esto:

- **Fotos:** antes y después, iguales en `telemetry_events` y en el inventario.
- **Migración:** `--dry-run` con las 9 sentencias, aplicada, y la segunda ejecución con «Nada que migrar».
- **Acceso:** los tres roles sin ningún privilegio, 0 grants a `PUBLIC`, RLS activado y 0 políticas.
- **Corrida:** salida 0 y cuadre con 0 diferencias.
- **Escritura forzada:** un `INSERT` lanzado por `readonly` lo rechaza PostgreSQL (salida 2).

**Herramienta de lectura:** `python -m business_performance.readonly` (desde `data/pipelines`) ejecuta un `.sql` en una transacción `SET TRANSACTION READ ONLY` que siempre termina en `ROLLBACK`. Así PostgreSQL rechaza cualquier escritura. Lee la URL del `.env` sin mostrarla.

**Si el Control de aplicaciones de Windows bloquea una DLL de SQLAlchemy** (`ImportError: DLL load failed while importing _collections_cy` o `_util_cy`: «Una directiva de Control de aplicaciones bloqueó este archivo»), no es un fallo del código ni de la base. Primero se reintenta. Si sigue bloqueada, se usa la imagen del pipeline (`nexova-pipeline:dev`), que es Linux y no pasa por ese control. Monta el código del repo y el `.env` en solo lectura, así que la URL tampoco pasa por la terminal. Desde la raíz, en PowerShell:

```powershell
$R = (Get-Location).Path
docker run --rm -v "${R}\.env:/.env:ro" -v "${R}\data\pipelines:/data/pipelines:ro" -v "${R}\data\process:/data/process:ro" -v "${R}\packages\shared:/packages/shared:ro" -v "${R}\docs\reporting:/docs/reporting:ro" nexova-pipeline:dev python -m business_performance.readonly /docs/reporting/pipeline-check.sql
```

Dentro de la imagen, el `.env` de la raíz se busca en `/.env`: es la misma regla de `config.py`, tres carpetas por encima del módulo. Para otro archivo, cambia el último argumento (por ejemplo, `/docs/reporting/demo-reporting-access.sql`).

### 6.0 Antes de empezar

- **Desde la raíz, en PowerShell, sin `$env:DATABASE_URL`:** cada comando dice `DATABASE_URL: .env de la raíz, host …`. **Ese host tiene que ser el de Supabase**; si dice `entorno` o `127.0.0.1`, para.

  ```powershell
  Remove-Item Env:DATABASE_URL, Env:PREFECT_API_URL -ErrorAction SilentlyContinue
  docker compose ps
  ```

  El stack normal (`api` `healthy`, `ui`) va contra la demo, como siempre.
- **Semana:** la última cerrada es la del **2026-11-02** hasta el domingo 2026-11-15 a las 23:59 UTC. A partir de ahí, el script por defecto calcularía la del 2026-11-09.
- **Durante el recorrido, no uses los formularios del inventario del backoffice:** crearían órdenes y eventos reales en la semana en curso. Navegar no cambia nada de lo que se compara, porque la huella de `telemetry_events` cubre hasta hoy a las 00:00 UTC. Haz la foto de antes y la de después **el mismo día UTC**.

### 6.1 Foto de solo lectura, antes

```powershell
New-Item -ItemType Directory -Force data\raw\business_performance | Out-Null
Push-Location data\pipelines
.\.venv\Scripts\python -m business_performance.readonly ..\..\docs\reporting\demo-snapshot.sql | Tee-Object ..\raw\business_performance\demo-before.txt
Pop-Location
```

**Esperado:**

- **Esquema:** `reporting_schema_exists`, `pipeline_runs_exists` y `weekly_table_exists` en `False`.
- **Roles:** `supabase_roles = anon,authenticated,service_role` y `current_role_is_superuser = False`.
- **Huellas:** quedan anotadas las de `telemetry_events`, `assets`, `asset_entries` y `asset_exits`.
- **Eventos de negocio de la semana del 2026-11-02** (según tus datos de la demo): `inbound_order_created` en Valencia, EUR, `quantity` 4 y `unit_cost` 4; `outbound_order_created` en Miami, USD; `stock_threshold_triggered` en Miami; ningún `kit_cost_variance_detected`.

Si no coincide, **para**: los valores esperados de §6.3 salen de aquí.

### 6.2 Migración del esquema `reporting` (DDL, con la guarda)

**Primero, la guarda.** Sin `--allow-demo`, la migración se niega y no llega a conectar (salida 1):

```powershell
Push-Location data\pipelines
.\.venv\Scripts\python -m business_performance.migrate --dry-run
```

**Dry-run, aplicación, segunda ejecución y acceso:**

```powershell
.\.venv\Scripts\python -m business_performance.migrate --dry-run --allow-demo
.\.venv\Scripts\python -m business_performance.migrate --allow-demo
.\.venv\Scripts\python -m business_performance.migrate --allow-demo
.\.venv\Scripts\python -m business_performance.readonly ..\..\docs\reporting\demo-reporting-access.sql
Pop-Location
```

**Esperado en el `--dry-run`:** 9 sentencias, nada aplicado.

1. `CREATE SCHEMA IF NOT EXISTS reporting`
2. `CREATE TABLE IF NOT EXISTS reporting.pipeline_runs (…)`
3. `CREATE TABLE IF NOT EXISTS reporting.weekly_office_program_performance (…)`, con la DDL del BRIEFING + `run_id` y los `CHECK`
4. `CREATE UNIQUE INDEX IF NOT EXISTS ux_pipeline_runs_one_running …`
5. `CREATE INDEX IF NOT EXISTS ix_pipeline_runs_latest …`
6. `ALTER TABLE reporting.pipeline_runs ENABLE ROW LEVEL SECURITY`
7. `ALTER TABLE reporting.weekly_office_program_performance ENABLE ROW LEVEL SECURITY`
8. `REVOKE ALL ON SCHEMA reporting FROM PUBLIC, anon, authenticated, service_role`
9. `REVOKE ALL ON ALL TABLES IN SCHEMA reporting FROM PUBLIC, anon, authenticated, service_role`

**Esperado en el resto:**

- **Aplicación:** «Aplicado en una transacción», con las mismas 9 sentencias. Si algún rol conservara un privilegio, se deshace todo y sale con 1.
- **Segunda ejecución:** «Nada que migrar».
- **Acceso:**
  - `anon`, `authenticated` y `service_role`: todo `False` (`USAGE` y `CREATE` del esquema; lectura y escritura de las dos tablas).
  - `public_grants = 0`.
  - Las dos tablas con `rls_enabled = True`, `policies = 0` y `owned_by_current_role = True`.
  - `authenticator_setting`: los esquemas que expone la Data API, **sin `reporting`**. Si sale `(0 filas)`, compruébalo en el panel de Supabase (*Integrations → Data API → Settings → Exposed schemas*).
  - `pipeline_runs = 0` y `weekly_rows = 0`.

### 6.3 Corrida del script contra la demo (la última semana cerrada)

```powershell
data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py; $LASTEXITCODE
Push-Location data\pipelines
.\.venv\Scripts\python -m business_performance.readonly ..\..\docs\reporting\pipeline-check.sql
Pop-Location
```

**Esperado en la corrida:** la primera línea con el host de Supabase y salida 0. La línea JSON `pipeline_run_finished` con:

- `status = completed` y semanas `2026-11-02` → `2026-11-02`;
- `source_rows_read = 3`, `rows_rejected = 0` y `duplicates_collapsed = 0`;
- `rows_upserted = 2` y `rows_deleted = 0`.

**Esperado en el cuadre:** `missing_or_different = 0`, `unexpected = 0`, `rows_compared = 2`, `weeks_compared = 1` y `duplicated_cells = 0`. En la tabla:

| `office` | `programme_id` | `total_material_cost` | `kits_delivered_count` | `shortage_events_count` | `cost_variance_events_count` | `currency` |
|---|---|---|---|---|---|---|
| miami | `_unassigned` | 0 | 1 | 1 | 0 | USD |
| valencia | `_unassigned` | 16 (4 × 4) | 0 | 0 | 0 | EUR |

La corrida deja en tu disco, ignorados por git: la caché en `data/raw/business_performance/prefect-results/`, solo con agregados, y el snapshot en `data/eval/business_performance/`. También deja el estado del servidor temporal de Prefect en `~/.prefect`, fuera del repo.

### 6.4 Disparo desde la API contra la demo

**a. Configuración (la haces tú, no yo: el `.env` lleva secretos).** Añade al `.env` de la raíz:

```text
PIPELINE_PREFECT_API_URL=http://prefect-server:4200/api
```

**b. Perfil `pipelines` contra la demo.** El comando recrea `api` con la variable nueva y arranca `prefect-server` y `pipeline-worker`, que todavía no tiene credencial:

```powershell
docker compose --profile pipelines up -d
docker compose --profile pipelines ps
```

**c. Block `Secret` apuntando a la demo, desde el host.** La URL sale del `.env` y nunca pasa por la terminal; el servidor del perfil está publicado en el 4200:

```powershell
$env:PREFECT_API_URL = "http://localhost:4200/api"
Push-Location data\pipelines; .\.venv\Scripts\python -m business_performance.secret; Pop-Location
Remove-Item Env:PREFECT_API_URL
```

Esperado: `Block nexova-supabase-database-url guardado. DATABASE_URL: .env de la raíz, host <Supabase>`.

**d. Tu admin.** Es el que usas en el backoffice, que vive en la TinyDB local (`services/api/data/auth.json`). Yo no tengo ni invento credenciales: las escribes tú en la ventana de PowerShell.

```powershell
$B = "http://localhost:8000"
$cred = Get-Credential -Message "Tu usuario admin del backoffice (email y contraseña)"
$admin = (Invoke-RestMethod -Method Post -Uri "$B/auth/login" -Body @{username = $cred.UserName; password = $cred.GetNetworkCredential().Password}).access_token
```

Si no tienes ningún admin: `docker compose exec api python -m app.auth.create_admin` (interactivo). Ese admin se queda en tu `auth.json`.

**e. Disparo, espera y lecturas.** Define antes la función `Call` de §4.2.

```powershell
$post = Call POST /reporting/pipeline-runs $admin; $post
$id = ($post.Substring(4) | ConvertFrom-Json).prefect_flow_run_id
do { Start-Sleep 2; $state = (Invoke-RestMethod "http://localhost:4200/api/flow_runs/$id").state_type; $state } until ($state -in 'COMPLETED', 'FAILED', 'CRASHED', 'CANCELLED')
Call GET /reporting/pipeline-runs/latest $admin
Call GET "/reporting/weekly-office-program-performance?week_start=2026-11-02" $admin
Push-Location data\pipelines; .\.venv\Scripts\python -m business_performance.readonly ..\..\docs\reporting\pipeline-check.sql; Pop-Location
```

El `POST` va sin cuerpo: calcula la última semana cerrada.

**Esperado:**

- **Disparo:** 202 y el flow run en `COMPLETED`, visible en `http://localhost:4200` → *Runs*.
- **`/latest`, ya con el flow run completado:** `trigger = manual`, `status = completed`, el mismo `prefect_flow_run_id`, `rows_upserted = 2` y sin `requested_by`.
- **KPI:** los de §6.3, con `16.0` y `0.0` como números JSON.
- **Cuadre:** sigue en 0 diferencias.

**f. Apagar el perfil.** El volumen `prefect-data` guarda el block con la credencial de la demo, cifrado con una clave que está en la misma SQLite: se borra.

```powershell
docker compose --profile pipelines rm -sf prefect-server pipeline-worker
docker volume rm nexova_prefect-data nexova_pipeline-raw nexova_pipeline-eval
```

Después, quita la línea `PIPELINE_PREFECT_API_URL` del `.env` (o déjala; sin servidor, el `POST` da 503) y ejecuta `docker compose up -d`. Mientras el worker no esté en marcha, el cron `weekly` (lunes 06:00 Madrid) no corre.

### 6.5 Foto de solo lectura, después

```powershell
Push-Location data\pipelines
.\.venv\Scripts\python -m business_performance.readonly ..\..\docs\reporting\demo-snapshot.sql | Tee-Object ..\raw\business_performance\demo-after.txt
.\.venv\Scripts\python -m business_performance.readonly ..\..\docs\reporting\demo-reporting-access.sql
Pop-Location
Compare-Object (Get-Content data\raw\business_performance\demo-before.txt) (Get-Content data\raw\business_performance\demo-after.txt)
```

**Esperado:**

- **Diferencias:** solo la fila de existencia de `reporting` (ahora `True`) y, si usaste la app, `events_total`.
- **Sin cambios:** `events_before_today`, `fingerprint_before_today` y las tres huellas del inventario. El pipeline solo lee esas tablas.
- **Acceso:** igual que en §6.2, con `pipeline_runs = 2` (la del script y la de la API) y `weekly_rows = 2`.

### 6.6 Qué queda en la demo y qué no

| | ¿Permanente? |
|---|---|
| Esquema `reporting`: 2 tablas, sus índices, RLS sin políticas y sin privilegios para `PUBLIC` ni los roles de Supabase | **Sí.** Reversible por el dueño con `DROP SCHEMA reporting CASCADE`, solo con tu confirmación |
| 2 filas en `weekly_office_program_performance` (2026-11-02, las dos oficinas) | **Sí, recalculables:** otra corrida de la misma semana las sobrescribe (upsert), nunca las duplica |
| 2 filas en `pipeline_runs` | **Sí:** es el log de auditoría. La de la API guarda tu `id` (seudónimo) en `requested_by`, que no sale por la API |
| `telemetry_events`, `assets`, `asset_entries`, `asset_exits` | **Sin cambios:** el pipeline solo los lee (lo confirman las fotos) |
| Estado de Prefect y block `Secret` con la credencial | **No:** se borran con el volumen `prefect-data` (§6.4 f) |
| Caché y snapshot de la corrida, `demo-before.txt` y `demo-after.txt` | **No, locales** e ignorados por git. Solo agregados, conteos y huellas. Bórralos al terminar: `Remove-Item -Recurse data\raw\business_performance, data\eval\business_performance` |
| `PIPELINE_PREFECT_API_URL` en tu `.env` | Lo decides tú (§6.4 f) |
| `~/.prefect` (estado del servidor temporal de las corridas por script, sin la URL) | Fuera del repo; no se toca |

### 6.7 Resultado en la demo (2026-11-12)

Host `aws-0-eu-west-1.pooler.supabase.com`, PostgreSQL 17.11, rol sin superusuario.

- **§6.1, foto antes:** sin `reporting`. `telemetry_events` con 66 eventos, todos anteriores al día UTC, y las tres tablas del inventario con 6 filas cada una. La semana del 2026-11-02, como se esperaba.
- **§6.2, migración:**
  - sin `--allow-demo`, se negó sin llegar a conectar (salida 1);
  - el `--dry-run` mostró las 9 sentencias;
  - se aplicó en una transacción, y la segunda ejecución dijo «Nada que migrar».
  - Acceso: los tres roles en `False`, `public_grants = 0`, RLS activado, 0 políticas y las dos tablas propias del rol.
  - `authenticator_setting` dio `(0 filas)`. El usuario lo comprobó en el panel de Supabase (*Integrations → Data API → Settings → Exposed schemas*): están expuestos `graphql_public` y `public`, y **`reporting` no**.
- **§6.3, corrida del script (yo, desde el host):** salida 0, la semana 2026-11-02, `source_rows_read = 3`, sin rechazos ni duplicados, `rows_upserted = 2`. Sin aviso de analítica. El cuadre dio 0 diferencias en los dos sentidos, `rows_compared = 2` y 0 celdas duplicadas.
- **§6.4, disparo desde la API (el usuario, con su admin):**
  - El `POST` dio 202 con `status = scheduled`. El flow run pasó `SCHEDULED → PENDING → RUNNING → COMPLETED`.
  - `/latest`: `trigger = manual`, `status = completed`, `phase = done`, el mismo `prefect_flow_run_id`, la semana 2026-11-02, `source_rows_read = 3`, `rows_upserted = 2` y sin `requested_by`.
  - La calidad cuadra. Valencia: 1 evento de entrada y 1 entrada con coste. Miami: 1 salida en los eventos y 1 en el inventario.
  - Los KPI coinciden con los de la corrida del script (Miami `0.0` USD, 1 kit y 1 escasez; Valencia `16.0` EUR). El recálculo sobrescribe, no duplica.
  - Perfil y volúmenes borrados, el del block incluido, y el stack `healthy`. `PIPELINE_PREFECT_API_URL` se queda en el `.env`.
- **Después del disparo:**
  - En el venv del usuario, y luego en el mío dos veces, el Control de aplicaciones de Windows bloqueó `_collections_cy` de SQLAlchemy.
  - Las dos lecturas se hicieron con la imagen del pipeline (§6, nota del Control de aplicaciones), en solo lectura.
  - `pipeline-check.sql`: 0 diferencias, `rows_compared = 2`, `weeks_compared = 1` y 0 celdas duplicadas. Hay 2 corridas `manual`, `completed`, con 3 eventos leídos, 2 filas escritas y `eval_snapshot = completed`.
  - `demo-reporting-access.sql`: acceso igual que en §6.2, con `pipeline_runs = 2` y `weekly_rows = 2`.
- **La demo solo ganó el esquema `reporting`.** Las fotos antes y después solo difieren en su existencia: los 66 eventos, su huella y las tres huellas del inventario no cambiaron.
- **Mejora fuera de esta PR:** el proyecto de Supabase tiene activada *Automatically expose new tables*, que da privilegios por defecto a `anon`, `authenticated` y `service_role` en las tablas nuevas. Para `reporting`, la migración lo neutraliza con sus dos `REVOKE` (sentencias 8 y 9 de §6.2), y `demo-reporting-access.sql` lo confirma con todo en `False`. Desactivar esa opción en el proyecto es una decisión aparte, porque afecta a cualquier tabla nueva de `public`.
