# Cola de tareas asíncronas (DEV-55) — F0: análisis y decisiones

> **Ticket:** #DEV-55 (enunciado solo local en `contexts/dev-55/`, igual que los briefings de hito).
>
> **Estado al cerrar F0 (2026-11-18):** solo análisis. Sin código, sin dependencias nuevas, sin cambios en `docker-compose.yml` y sin ninguna conexión a la demo. Rama `feature/async-task-queue`, desde `main` en `5be61d3` (merge de la PR #38). Las decisiones A1–A16 (§5) son del usuario; F1 empieza cuando estén tomadas.
>
> **Actualización (2026-11-20):** el usuario decidió A1–A16 (cada una lleva su estado en §5, con los añadidos de A10 y A15). Además: la captura de Flower va solo en la PR (no se versiona); H14 queda fuera de este ticket, anotado como pendiente en `memory-bank/progress.md`; y los tests actuales del contrato síncrono de `/telemetry/report` (API y backoffice) se **adaptan** al contrato nuevo, nunca se borran sin más, y cada parada dice cuáles cambian y por qué.

## 1. Qué pide el ticket, en resumen

Resumen propio de los criterios que condicionan el diseño (no es el enunciado):

| # | Criterio | Cómo lo leo |
|---|---|---|
| C1 | Redis como broker en Docker; API y workers contra el mismo Redis, por `REDIS_URL` | Servicio `redis` en Compose, imagen oficial, puerto 6379, `noeviction` |
| C2 | Convertir en tarea Celery la operación existente **más lenta** | Hay que medir y justificar la elección (§3 y §4) |
| C3 | El endpoint convertido responde `202 Accepted` con `{"task_id"}` en **menos de 200 ms** | Antes del 202 no se puede tocar Supabase (~400 ms solo de conexión) |
| C4 | `GET /tasks/{task_id}` → `{"task_id", "status", "result"}`, con `status` ∈ `pending`, `started`, `success`, `failure` | Hay que mapear los 6 estados reales de Celery a 4 |
| C5 | Reintentos automáticos con `max_retries=3` y backoff exponencial (nunca un reintento inmediato) | Ambigüedad «3 intentos» frente a «1 + 3» (A8) |
| C6 | Tras agotar los reintentos, una DLQ en **base de datos** con `task_id`, intento, error y fecha | Tabla propia (A9) |
| C7 | Worker en un proceso separado de FastAPI; parar la API no para el worker ni pierde mensajes | Contenedor propio, `acks_late`, Redis con persistencia |
| C8 | Mensajes ligeros: solo identificadores o referencias | Nada de blobs en el mensaje |
| C9 | Log por tarea: `task_id`, intento, estado y duración; en los fallos, el mensaje de error | Tensión con la redacción ya existente (A12) |
| C10 | Flower accesible en el 5555, con al menos una tarea completada y una fallida en la demostración | Servicio `flower` (A5) y fallo controlado (A13) |
| C11 | Documentar cómo levantar y detener el worker en el README del monorepo | El `README.md` raíz es el briefing de Nexova (A15) |
| C12 | Entrega: PR con la justificación del endpoint, captura de Flower (una completada y una en la DLQ), log con un reintento y la etiqueta `async-tasks` | §8 |

## 2. Hallazgos verificados

Todos comprobados en esta sesión (lectura del código o medición). Las suposiciones van aparte, en §6.

| # | Hallazgo | Fuente |
|---|---|---|
| H1 | `GET /telemetry/report` crece **linealmente** con los eventos de la ventana: 61 ms con 50 eventos, 240 ms con 10 049, **1,7 s con 100 049 y 8,3 s con 500 049** (p50, sin caché). Es CPU en el proceso de la API: Pandas sobre `telemetry_events` | §3.2 |
| H2 | Mientras corre un reporte grande, el resto de la API se degrada: con 1 reporte de 500 k eventos, `/auth/me` pasa de 34 a 49 ms de p50 con picos de 745 ms; **con 4 reportes en paralelo cada uno tarda ~30 s** (frente a 8 s solo) y `/auth/me` llega a 3,2 s. Un solo proceso (`--workers 1`) y el GIL: es exactamente el problema que describe el ticket | §3.3 |
| H3 | El backoffice corta el reporte a los **15 s** (`REPORT_TIMEOUT_MS` en `uis/backoffice/services/telemetry-report.service.ts`): con 4 reportes simultáneos de 500 k eventos, los cuatro fallarían por timeout | código + H2 |
| H4 | `POST /reporting/pipeline-runs` **ya es asíncrono**: responde `202` con el `prefect_flow_run_id` en 35–84 ms y el flow lo ejecuta el `pipeline-worker` de Prefect, fuera de la API (`SPECS.md` §51.3, `trigger.py`). Convertirlo a Celery duplicaría el orquestador | §3.2 + código |
| H5 | `POST /api/incidents/analyze` está acotado por `MAX_UPLOAD_BYTES` (1 MiB de body): el CSV más grande admitido (9 115 filas sintéticas) tarda **81 ms**. Nunca puede ser lento sin cambiar ese límite | §3.2 |
| H6 | `GET /inventory/orders` cuesta 894 ms con 30 403 órdenes, pero por el **tamaño de la respuesta** (8,7 MB sin paginar), no por cálculo. F0 de caching ya lo atribuyó a la falta de paginación (D10 de `docs/caching-analysis.md`) | §3.2 + caching F0 |
| H7 | `LastResultStore` (último análisis de CSV) y `ResponseCache` (`app/core/cache.py`, incluido el espacio `telemetry_report` de 60 s) viven en la memoria del proceso de la API: un worker separado no los ve ni los puede invalidar | código, `SPECS.md` §6 y §41 |
| H8 | `POST /auth/forgot-password` ya envía el email fuera del ciclo de la respuesta, con `BackgroundTasks` de FastAPI (en el mismo proceso) | `app/routes/auth.py` |
| H9 | `get_current_user` solo lee la TinyDB de usuarios (`auth.json`); no toca Supabase. La `Session` de `get_db` es perezosa: sin consulta no abre conexión. Un endpoint que valida fechas, encola y responde puede hacerlo sin pasar por Supabase | `app/auth/dependencies.py`, SQLAlchemy |
| H10 | En Compose, `api` recibe el `.env` entero (`env_file`): un `REDIS_URL` en el `.env` le llega solo. `ui` tiene una lista blanca (`environment:`), así que no lo recibiría. Un worker con `env_file` recibiría también `JWT_SECRET_KEY`, `RESEND_API_KEY` y la `DATABASE_URL` de la demo | `docker-compose.yml` |
| H11 | La imagen de la API (`nexova-api`) ya tiene Pandas, SQLAlchemy y psycopg2: el worker puede salir de la misma imagen, con otro comando. Prefect sigue solo en `data/pipelines` y no hace falta | `services/Dockerfile`, `requirements.txt` |
| H12 | Versiones publicadas hoy en PyPI (`pip index versions`, 2026-11-18): **celery 5.7.0, kombu 5.7.0, redis 8.1.0, flower 2.2.0** | consulta a PyPI |
| H13 | La etiqueta `async-tasks` **no existe** todavía en el repositorio de GitHub (hay `cronjob`) | `gh label list` |
| H14 | Colateral: **`scripts/seed_volume.py inventory` ya no funciona**. Falla con `ValidationError: unit_cost Field required` en `InboundOrderCreate`, porque `unit_cost` pasó a ser obligatorio con la telemetría. En F0 el volumen de órdenes se sembró con SQL directa en el efímero. Arreglarlo queda fuera de este ticket | ejecución |
| H15 | La migración del esquema `reporting` solo acepta `localhost` como base local; en el efímero se ejecutó compartiendo la red del contenedor de Postgres (`--network container:…`) | `business_performance/migrate.py` |
| H16 | `ops.job_runs` no está migrado en la demo (banco de memoria, 2026-11-18): el esquema `ops` **no existe** allí | `memory-bank/progress.md` |

## 3. Medición

### 3.1 Montaje (nunca la demo)

Receta de `docs/caching-analysis.md` §2.4, adaptada. Todo en una red propia (`nexova-dev55-net`), sin publicar ningún puerto en el host, y sin tocar el stack del usuario (`nexova-api-1` y `nexova-ui-1` siguieron en marcha contra la demo, sin cambios).

- **Postgres efímero:** `postgres:17.6-alpine3.22`, contenedor `nexova-dev55-pg`, base `nexova_test` con un rol propietario **sin superusuario** (`nexova_app`), como exige la migración de telemetría. Esquemas: inventario (por el lifespan de la API), `telemetry_events` (`python -m app.modules.telemetry.migrate`) y `reporting` (`python -m business_performance.migrate`, ver H15).
- **API de medición:** `nexova-api:latest` con el código del árbol en solo lectura, TinyDB de prueba en el scratchpad de la sesión (bind mount de Windows, como la demo), `--workers 1` y sin `--reload`. Cuenta temporal `dev55-admin@example.invalid` creada con `create_admin` en esa TinyDB.
- **Prefect aislado:** `nexova-pipeline:dev` como servidor (`nexova-dev55-prefect`) y como `serve` del deployment `manual` (`nexova-dev55-worker`), sin block `Secret`: cada flow run falla en `start_run` tras sus 2 reintentos de Prefect, lo que basta para medir el disparo.
- **Datos sintéticos:**
  - **Inventario:** el seed (6 activos) más 12 208 entradas y 18 195 salidas por SQL (`Proveedor sintetico DEV55`, `EMPLEADO-SINTETICO-NNN`), el mismo orden de magnitud que F0 de caching (30 393), porque `seed_volume.py` falla (H14).
  - **Telemetría:** `docs/telemetry/report-seed-ephemeral.sql` (50 eventos ficticios) y después copias de esas 50 filas con `event_id` aleatorio y fecha aleatoria dentro de los últimos 7 días, hasta 500 049 eventos en la ventana por defecto.
  - **CSV:** generado en memoria por el script, con emails `userN@example.invalid`, al límite del body (1 048 287 bytes).
- **Cliente:** un script de un solo uso con `http.client` (fuera del repositorio, en el scratchpad), ejecutado en un contenedor `python:3.14.6-slim` de la misma red, como `ui` → `api`. Calentamiento de 1–2 peticiones; después N = 20 (N = 10 en las de más volumen). Para medir el reporte **sin caché**, cada petición lleva un `end_date` distinto (la clave de la caché es lo recibido, `SPECS.md` §48).

### 3.2 Resultados (p50 / p95 en ms, en cliente)

| Endpoint | Volumen | p50 / p95 | Bytes | Notas |
|---|---|---|---|---|
| `GET /telemetry/report` (fallo de caché) | 49 eventos en la ventana | 61 / 71 | 5 KB | |
| | 249 | 70 / 85 | 5 KB | |
| | 2 049 | 102 / 123 | 5 KB | |
| | 10 049 | **240 / 278** | 20 KB | |
| | 100 049 | **1 722 / 1 864** | 21 KB | |
| | 500 049 | **8 277 / 10 298** | 21 KB | ~17 µs por evento |
| `GET /telemetry/report` (acierto de caché) | cualquiera | 14 / 20 | 5 KB | caché de 60 s en memoria de la API |
| `GET /inventory/orders` | 30 403 órdenes | **894 / 925** | **8,7 MB** | F0 de caching: 657–674 ms en local y 452 ms contra Supabase con 10 órdenes |
| `POST /api/incidents/analyze` | 94 filas (10,7 KB) | 15 / 21 | 1,6 KB | |
| | 9 115 filas (1 048 287 B, el máximo) | **81 / 100** | 1,6 KB | acotado por `MAX_UPLOAD_BYTES` |
| `POST /reporting/pipeline-runs` | — | 49 / 84 (35–84) | 84 B | 6 disparos: `202` y `409` (el flow anterior seguía en sus reintentos); **ya asíncrono** (H4) |

El coste fijo de la autenticación está incluido: con la TinyDB en un bind mount de Windows, `/auth/me` cuesta aquí ~30 ms (F0 de caching midió 7 ms con bind mount y 1,8 ms con volumen; esta máquina iba más lenta).

### 3.3 Concurrencia (H2)

Un hilo pide el reporte de 500 049 eventos sin caché; otro pide `GET /auth/me` cada 50 ms hasta que el reporte termina.

| Reportes en paralelo | Duración de cada reporte | `/auth/me` antes | `/auth/me` durante (p50 / máx.) |
|---|---|---|---|
| 1 | 7,9 s | 34 ms | 49 / 745 ms |
| 4 | 29,8–29,9 s | 29 ms | 32 / **3 182 ms** |

FastAPI ejecuta las rutas `def` en su pool de hilos, así que la API no se bloquea del todo, pero el cálculo de Pandas compite por el GIL del único proceso: cuatro reportes tardan lo que cuatro seguidos, y las demás peticiones sufren picos de segundos.

### 3.4 Lo que no se ha medido

- **El volumen real de `telemetry_events` en la demo** (no se consulta la demo en F0). El plan de telemetría solo da un orden de magnitud sin medir: decenas de operadores, decenas a cientos de eventos de negocio al día más `page_viewed` (`docs/telemetry/telemetry-plan.md` §8). Con ese volumen, la ventana por defecto (7 días) está en los miles de eventos: **unos 100–250 ms más los ~400 ms de conexión a Supabase**. El reporte admite ventanas de hasta 90 días (13 veces más eventos).
- **El tiempo de encolar** (publicar en Redis): no hay Redis ni Celery instalados (prohibido en F0). Se mide en la parada 3 (§7).
- **Las rutas no candidatas** ya medidas en F0 de caching (`docs/caching-analysis.md` §3 y §4): ninguna supera los 110 ms salvo `/inventory/orders` y las lecturas contra Supabase (~400 ms fijos de red, que una tarea no elimina: solo los mueve al worker).

## 4. Elección de la operación (para el cuerpo de la PR)

| Candidato | (a) ¿Mensaje con solo una referencia? | (b) ¿Dónde queda el resultado? | (c) Frontend que lo consume y qué se rompe | (d) ¿202 en < 200 ms? | Veredicto |
|---|---|---|---|---|---|
| **`GET /telemetry/report`** | **Sí.** El mensaje lleva `start` y `end` (dos fechas ISO); el worker lee `telemetry_events` de PostgreSQL por su cuenta | Result backend de Redis: ~20 KB de agregados técnicos, sin `user_id`, `session_id`, `event_id` ni dimensiones de negocio (`SPECS.md` §48), con caducidad. La caché de 60 s en memoria de la API deja de servir (H7) y se sustituye (A4) | `/telemetry` (`hooks/use-telemetry-report.ts` → `services/telemetry-report.service.ts`). Pasa de una petición a una petición + sondeo de `/tasks/{id}`; el timeout de 15 s desaparece; el normalizador del reporte se reutiliza para el `result` | **Sí.** Validar las fechas (puro), `get_current_user` (TinyDB, H9) y publicar en Redis. Sin `get_db` en la ruta | **Recomendado** |
| `POST /api/incidents/analyze` | **No.** Habría que guardar el CSV subido (en disco, en Redis o en la base) para pasar su ruta: el CSV lleva `customer_email`, y hoy está garantizado que **nunca toca disco** (`SPECS.md` §5, test de privacidad). Habría que decidir quién lo borra y cuándo | `LastResultStore` está en la memoria de la API (H7): haría falta persistirlo, y la exportación `GET /results/export` dejaría de funcionar tal cual | `/incidents` (`use-incident-analysis.ts`): el flujo de análisis y exportación entero | Sí (si el archivo se guarda deprisa) | **Descartado:** nunca pasa de 81 ms (H5) y convertirlo empeora la privacidad |
| `GET /inventory/orders` | Sí (sin parámetros) | **8,7 MB por resultado en Redis**, con `noeviction`: una sola tarea ocuparía decenas de veces lo que el resto | `/inventory/orders` (`use-inventory-orders.ts`): su coste dominante es el render de 30 k filas (25,5 s, F0 de caching), que la tarea no toca | Sí | **Descartado:** el coste es el tamaño, no el cálculo; lo arregla la paginación (D10 de caching) |
| `POST /reporting/pipeline-runs` | Sí (`week_start`) | `reporting.pipeline_runs`, escrito por el flow | No lo consume (el backoffice solo lee `latest`) | Ya responde 202 en 35–84 ms | **Descartado:** ya es asíncrono con Prefect (H4) |
| `POST /auth/forgot-password` (notificación) | Haría falta el email o el id del usuario y que el worker leyese la TinyDB de usuarios (un archivo con bloqueo por proceso) | — | `/forgot-password` | Ya responde sin esperar al envío (H8) | **Fuera:** no es lento para el cliente; candidato para más adelante |

**Justificación (texto para la PR):** se convierte `GET /telemetry/report`, porque es la única operación de la API cuyo coste es **cálculo en el propio proceso** y crece sin techo: con la ventana por defecto pasa de 0,24 s con 10 k eventos a 1,7 s con 100 k y 8,3 s con 500 k, y la ventana admite hasta 90 días. Mientras calcula, compite por el GIL con el resto de peticiones (4 reportes simultáneos tardan ~30 s cada uno y `/auth/me` sube a picos de 3 s), y el backoffice lo corta a los 15 s. Además encaja con las reglas del patrón: el mensaje solo lleva dos fechas, el worker lee él mismo de PostgreSQL y el resultado son ~20 KB de métricas técnicas sin datos personales. Las otras candidatas se descartan con la medida: `GET /inventory/orders` tarda por el tamaño de la respuesta (8,7 MB) y no por cálculo; `POST /api/incidents/analyze` está acotado a 1 MiB (81 ms como máximo) y obligaría a guardar un CSV con emails de clientes; y `POST /reporting/pipeline-runs` ya es asíncrono con Prefect.

**Límite honesto:** con el volumen que hoy se estima en la demo (miles de eventos en 7 días), el reporte cuesta del orden de 100–250 ms de cálculo más ~400 ms de conexión a Supabase, parecido a `/inventory/orders`. La elección se apoya en la forma del coste (cálculo que crece con los datos y bloquea a los demás) y en el encaje con el patrón, no en que hoy sea el más lento por mucho.

## 5. Decisiones (A1–A16)

### A1 — Operación a convertir

> **Estado: decidida por el usuario el 2026-11-20.** Opción A: `GET /telemetry/report`.

| Opción | Qué |
|---|---|
| **A (recomendada)** | `GET /telemetry/report` (§4) |
| B | `POST /api/incidents/analyze`, guardando el CSV en un volumen temporal compartido y borrándolo al terminar |
| C | `GET /inventory/orders` |

**Por qué A:** §4. B y C se descartan con la medida.

### A2 — Contrato del endpoint convertido

> **Estado: decidida por el usuario el 2026-11-20.** Opción A: el mismo `GET` responde `202` con `Location: /tasks/<id>`.

| Opción | Qué | A favor | En contra |
|---|---|---|---|
| **A (recomendada)** | El mismo `GET /telemetry/report?start_date&end_date` responde `202 {"task_id"}` con `Cache-Control: no-store`; el resultado (la forma actual `{period, metrics}`) llega por `GET /tasks/{id}` | Es literalmente «el endpoint que antes ejecutaba la operación»; mismos parámetros, mismas validaciones (422) y misma autenticación; la diferencia en la PR es evidente | Un GET que crea una tarea: es seguro en sentido HTTP (no cambia datos de negocio), pero consume recursos; se acota con la deduplicación de A4 |
| B | `POST /telemetry/report` (o `/telemetry/report-tasks`) con las fechas en el cuerpo → 202, y `GET /telemetry/report` desaparece (404/405) | REST más ortodoxo: crear un recurso es un POST | Cambia método y forma de los parámetros; el «endpoint modificado» es otro |
| C | B, conservando además el GET síncrono | Compatibilidad | La API seguiría calculando en su proceso: no resuelve H2 |

### A3 — Qué se calcula con qué periodo

> **Estado: decidida por el usuario el 2026-11-20.** Confirmada: el periodo se resuelve en la API antes de encolar y el mensaje lleva `start` y `end` ya resueltos.

`resolve_period` (fechas por defecto, UTC, 90 días, `start < end`) sigue en la API, **antes** de encolar: un 422 nunca crea tarea. El mensaje lleva el periodo **ya resuelto** (`start` y `end` en ISO 8601 UTC, truncados a ms), no lo que pidió el cliente, para que el resultado no dependa de cuándo lo coge el worker. Sin alternativa razonable; se anota para confirmarla.

### A4 — Sustituto de la caché de 60 s (deduplicación)

> **Estado: decidida por el usuario el 2026-11-20.** Opción A: deduplicación por usuario durante 60 s.

La caché `telemetry_report` de la API deja de servir: el resultado lo produce el worker (H7).

| Opción | Qué |
|---|---|
| **A (recomendada)** | Clave en Redis `nexova:dedupe:telemetry_report:<user_id>:<start>:<end>` → `task_id`, con `SET NX EX 60`. Una segunda petición igual en 60 s devuelve el **mismo** `task_id` (otro 202), salvo que esa tarea haya acabado en `failure`. En la ventana por defecto, la clave usa lo que pidió el cliente (`(None, None)`), como hoy |
| B | Sin deduplicación: cada carga de `/telemetry` encola una tarea |
| C | Deduplicación global (sin `user_id`): el reporte es igual para todos (`SPECS.md` §42) |

**Por qué A y no C:** C ahorra más, pero haría que un usuario recibiese el `task_id` de otro, y eso choca con la propiedad de las tareas de A10. La memoria de Redis no es un problema (una clave de ~100 bytes por usuario y minuto).

### A5 — Dónde vive el módulo Celery y qué entorno usa cada proceso

> **Estado: decidida por el usuario el 2026-11-20.** Opción B: paquete `services/task_queue/`.

`.agents/rules/monorepo-structure.md`: cada servicio en su propia subcarpeta con README, **nunca código suelto en la raíz de `services/`**.

| Opción | Qué | En contra |
|---|---|---|
| A | `services/celery_app.py` (la sugerencia del ticket) | Archivo suelto en `services/`: incumple la regla. Para que `celery -A services.celery_app` funcione, `services/` tendría que ser un paquete importable, y en la imagen la API vive en `/app/api` |
| **B (recomendada)** | Paquete `services/task_queue/`, como `services/job_runner/`: `celery_app.py` (instancia y configuración), `tasks.py`, `dead_letters.py` (repositorio de la DLQ), `migrate.py`, `config.py`, `logs.py`, `README.md` y `tests/`. Worker: `celery -A task_queue.celery_app worker` | Se aparta del comando literal del ticket (se explica en la PR) |
| C | Dentro de la API: `services/api/app/tasks/` | El worker importaría el paquete `app` entero (FastAPI, routers, configuración de la API) |

**Importación con B:**

- **Imagen:** `services/Dockerfile` copia `task_queue/` junto a `app/`, `telemetry/` y `reporting/` (en `/app/api/task_queue`), igual que se hizo con `telemetry`. En desarrollo se monta desde el host.
- **La API** solo **envía**: `send_task("task_queue.telemetry_report", kwargs=…)` por nombre, sin importar `tasks.py`, más la lectura de estados (`AsyncResult`). No importa Pandas a través de la tarea.
- **El worker** importa `task_queue.tasks`, que usa `telemetry.analysis.all_metrics` y su propio motor SQLAlchemy desde `DATABASE_URL`. **No importa FastAPI ni `app`** (lo comprueba un test de arquitectura, como `test_reporting_architecture.py`).
- **Entornos:** la API y el worker comparten el entorno de `services/api` (su `pyproject.toml`, `uv.lock` y `requirements.txt`, y la misma imagen). Prefect sigue solo en `data/pipelines`; ni el worker ni la API lo necesitan.

### A6 — Docker

> **Estado: decidida por el usuario el 2026-11-20.** Arranque por defecto (opción A) de `redis`, `worker` y `flower`, con todo lo de la tabla: digest fijado, `127.0.0.1`, contraseña, AOF, 128 MB con `noeviction`, lista blanca sin `env_file` y `REDIS_URL` nunca en `ui`.

| Pieza | Recomendación | Alternativas |
|---|---|---|
| `redis` | Imagen oficial `redis:<8.x>-alpine` **fijada por versión y digest** (se elige en la parada 1). `--maxmemory 128mb --maxmemory-policy noeviction`: sin `maxmemory`, `noeviction` no tiene efecto (no hay tope). **AOF** (`--appendonly yes`, `appendfsync everysec`) en un volumen con nombre `redis-data`: los mensajes sobreviven a un reinicio de Redis, no solo a la caída del worker | Sin persistencia (más simple, pero un `docker compose restart redis` perdería la cola); solo RDB (puede perder los últimos minutos) |
| Puerto | `127.0.0.1:6379:6379`: el ticket pide el 6379 expuesto; ligado solo a localhost para los tests de integración desde el host. Entre contenedores, `redis:6379` | `6379:6379` en todas las interfaces (cualquiera en la red local llegaría al broker) |
| Contraseña | `--requirepass` con `REDIS_PASSWORD` del `.env`; `REDIS_URL=redis://:<contraseña>@redis:6379/0`. El healthcheck usa `REDISCLI_AUTH` (variable), no `-a` en la línea de comandos. Nota: la contraseña en el comando del servidor se ve en `docker inspect`; se acepta en desarrollo, o se monta un `redis.conf` no versionado | Sin contraseña (aceptable solo con el bind a 127.0.0.1 y en desarrollo) |
| `worker` | La imagen de la API con `command: celery -A task_queue.celery_app worker --loglevel=INFO --concurrency=2 --max-tasks-per-child=50`. `init: true`, `stop_grace_period` mayor que `time_limit` (A7), `restart: unless-stopped`. **Sin `env_file`:** lista blanca `DATABASE_URL`, `REDIS_URL`, `TZ=UTC` y las del propio paquete. Sin puertos. Healthcheck: `celery -A task_queue.celery_app inspect ping -d celery@$$HOSTNAME` cada 30 s. Usuario no root. Sin recarga automática: tras un cambio, `docker compose restart worker` | Concurrencia 1 (menos memoria de Pandas, sin paralelismo) |
| `flower` | `celery -A task_queue.celery_app flower --port=5555` en `127.0.0.1:5555`, con `FLOWER_BASIC_AUTH` del `.env` y sin persistencia. Lista blanca: solo `REDIS_URL` y la autenticación (sin `DATABASE_URL`) | Imagen oficial de Flower (`mher/flower`): no sale de `uv`, otra fuente de dependencias |
| `depends_on` | `api` → `redis` (`service_healthy`); `worker` y `flower` → `redis` (`service_healthy`). El worker **no** depende de la API (C7) | — |
| `REDIS_URL` | En `api` (llega por `env_file`, H10), `worker` y `flower` (lista blanca). **Nunca en `ui`** (se añade a la comprobación de aislamiento de `AGENTS.md` §4). En `.env.example` con un valor de desarrollo sin secreto real | — |

**Perfil o arranque por defecto:**

| Opción | Qué |
|---|---|
| **A (recomendada)** | `redis`, `worker` y `flower` arrancan con `docker compose up`, como la API: `/telemetry` depende del worker, y sin él el dashboard se quedaría en `pending` para siempre |
| B | Perfil `tasks`, apagado por defecto (como `nightly`): `docker compose --profile tasks up -d` |
| C | `redis` y `worker` por defecto y `flower` en el perfil `tasks` |

**¿El worker puede acabar apuntando a la demo?** **Sí, igual que la API:** con la `DATABASE_URL` del `.env`, el worker lee `telemetry_events` de la demo, exactamente lo que hoy hace la API al calcular el reporte (solo `SELECT`). La única escritura nueva es la DLQ. Cómo se acota:

- la tabla de la DLQ solo existe en la demo si el usuario la migra con `--allow-demo` (A9). Hasta entonces, un fallo definitivo se registra solo en el log (A9, «base no disponible»);
- la demostración de fallos (A13) se hace siempre contra el Postgres efímero, con un override no versionado;
- el worker no recibe `JWT_SECRET_KEY`, `RESEND_API_KEY` ni `TELEMETRY_SUPPLIER_KEY` (lista blanca).

Si se prefiere que nada nuevo apunte a la demo sin una decisión explícita, la opción B del perfil lo garantiza, a costa de que `/telemetry` no funcione con un `docker compose up` normal.

### A7 — Configuración de Celery

> **Estado: decidida por el usuario el 2026-11-20.** Los valores recomendados de la tabla.

| Ajuste | Valor recomendado | Por qué |
|---|---|---|
| `task_acks_late` | `True` | ACK solo al terminar (regla 2 del patrón). Si el worker muere a mitad, el mensaje vuelve a la cola |
| `task_reject_on_worker_lost` | `True` | Sin esto, con `acks_late` un worker matado (OOM, `kill -9`) marca la tarea como fallida en vez de devolverla. Riesgo: un mensaje que siempre mata al worker se repetiría sin fin; lo acotan `time_limit` y `max-tasks-per-child`, y la tarea es de solo lectura (idempotente) |
| `broker_transport_options.visibility_timeout` | **600 s** | Redis devuelve a la cola un mensaje sin ACK pasado este tiempo. Tiene que superar la ejecución más larga (`time_limit`, 150 s) más la cuenta atrás más larga de un reintento (las ETA las retiene el worker sin ACK). El valor por defecto (1 h) retrasaría una hora la recuperación tras un worker caído |
| `task_soft_time_limit` / `task_time_limit` | **120 s / 150 s** | Regla 3. El soft lanza `SoftTimeLimitExceeded` y deja registrar el fallo; el hard mata el proceso hijo. 120 s cubren unos 7 M de eventos al ritmo medido (~17 µs/evento): la ventana de 90 días con 13 veces el volumen más alto medido |
| Statement timeout en PostgreSQL | `statement_timeout` de 110 s en las conexiones del worker (`connect_args`) | La consulta no sigue en la base cuando la tarea ya se rindió. Además permite el fallo controlado de A13 |
| `worker_prefetch_multiplier` | `1` | Con `acks_late`, un worker no acapara mensajes que otro podría procesar |
| Serialización | `task_serializer = result_serializer = "json"`, `accept_content = ["json"]` | Nada de pickle: un mensaje nunca ejecuta código al deserializarse |
| `result_backend` | El mismo Redis (base 1; el broker en la 0), por la misma `REDIS_URL` con otro índice | El ticket pide Redis como backend |
| `result_expires` | **3600 s** (por defecto, 1 día) | Con `noeviction`, los resultados ocupan memoria hasta caducar; una hora sobra para que el frontend lo recoja. Pasado ese tiempo, `/tasks/{id}` responde 404 (A10) |
| `task_track_started` | `True` | **Imprescindible** para el estado `STARTED`: sin él, Celery pasa de `PENDING` a `SUCCESS` |
| Eventos para Flower | `worker_send_task_events = True`, `task_send_sent_event = True` | Flower muestra las tareas encoladas (enviadas) además de las que están en proceso y las completadas |
| Publicación | `task_publish_retry_policy` con 1 reintento y 0,2 s; `broker_connection_timeout` 2 s | Si Redis no responde, la API responde **503 `task_queue_unavailable`** en lugar de colgarse segundos con la política por defecto |
| `broker_connection_retry_on_startup` | `True` | El worker espera a Redis al arrancar |
| `timezone` / `enable_utc` | `UTC` / `True` | Como el resto del proyecto |

### A8 — Reintentos y backoff

> **Estado: decidida por el usuario el 2026-11-20.** Backoff B (propio, nunca inmediato) e intentos A (`max_retries=3` literal: 4 ejecuciones; la DLQ guarda `attempt` y `retries`). La guía de revisión y la PR lo explican en una línea.

- **Qué se reintenta:** solo errores transitorios. Los de la base que hoy dan `503 storage_unavailable` (`OperationalError`, `InterfaceError`, `TimeoutError` de SQLAlchemy, que incluyen la cancelación por `statement_timeout`). **No se reintenta** un error de programación o de datos (`ProgrammingError` por tabla sin migrar, `ValueError`, `KeyError`…) ni `SoftTimeLimitExceeded` (volvería a pasar), que van **directos a la DLQ** con su motivo (A9).
- **Backoff:**

| Opción | Cuenta atrás (s) para los reintentos 1, 2 y 3 | ¿Puede ser inmediato? |
|---|---|---|
| A | `retry_backoff=2`, `retry_jitter=True` de Celery | **Sí**: el jitter de Celery elige al azar entre 0 y la cuenta atrás (§6, S3), así que un reintento puede salir con 0 s, contra el criterio de evaluación |
| **B (recomendada)** | Propia: `base · 2^n + uniforme(0, base)` con `base = 2` → 2–4, 4–6 y 8–10 s; tope de 60 s | Nunca: el mínimo es `base · 2^n` |
| C | Exponencial pura, sin jitter: 2, 4 y 8 s | Nunca; con muchos workers fallando a la vez, reintentan sincronizados (no es el caso con 1–2 workers) |

- **Ambigüedad del número de intentos (decide el usuario):**

| Opción | Configuración | Ejecuciones antes de la DLQ | Qué se registra |
|---|---|---|---|
| **A (recomendada)** | `max_retries=3`, literal | **4** (1 + 3 reintentos) | `attempt = 4`, `retries = 3` |
| B | `max_retries=2` | 3 | `attempt = 3`, `retries = 2` |

**Por qué A:** el ticket fija `max_retries=3` en la configuración y dice que la DLQ entra «al superar `max_retries`», y eso es 1 + 3 en Celery; el valor se comprueba en el código. «Tres fallos» se lee como tres reintentos fallidos. Para que no haya dudas en la revisión, la DLQ guarda las **dos** cifras (`attempt`, 1-based, y `retries`) y la guía lo explica. Con B, el texto «tres fallos consecutivos» encaja a la letra, pero el código dejaría de mostrar `max_retries=3`.

### A9 — Dead Letter Queue

> **Estado: decidida por el usuario el 2026-11-20.** Opción A: `ops.task_dead_letters`, solo registro, sin cola de Celery. La migración en la demo, solo con la confirmación del usuario; hasta entonces, el fallo definitivo va al log.

| Opción | Dónde | A favor | En contra |
|---|---|---|---|
| **A (recomendada)** | PostgreSQL, tabla **`ops.task_dead_letters`**, junto a `ops.job_runs` | Base de datos de verdad (C6), durable, consultable; mismo esquema, mismo patrón de migración y de permisos que DEV-53 | En la demo, `ops` aún no existe (H16): la primera migración allí crea el esquema |
| B | Una lista de Redis (`nexova:dlq`) | Sin base | Memoria con `noeviction`; no es el registro duradero que piden los criterios |
| C | TinyDB | — | Un archivo con bloqueo por proceso, compartido entre la API y el worker: descartada |

**Tabla propuesta** (DDL definitivo en la parada 2):

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `BIGSERIAL` PK | |
| `task_id` | `UUID NOT NULL UNIQUE` | Registro idempotente (`ON CONFLICT DO NOTHING`): con `acks_late`, un fallo definitivo puede llegar dos veces |
| `task_name` | `VARCHAR(200) NOT NULL` | `task_queue.telemetry_report` |
| `attempt` | `INTEGER NOT NULL CHECK (attempt >= 1)` | Ejecuciones (1-based) |
| `retries` | `INTEGER NOT NULL CHECK (retries >= 0)` | `request.retries` de Celery |
| `max_retries` | `INTEGER NOT NULL` | La configuración con la que falló |
| `reason` | `VARCHAR(32) NOT NULL`, `CHECK` en `retries_exhausted`, `non_retryable`, `time_limit` | |
| `error_class` | `VARCHAR(200) NOT NULL` | |
| `error_message` | `TEXT NOT NULL` | Redactado y truncado (A12) |
| `task_kwargs` | `JSONB NOT NULL` | Solo las referencias del mensaje (las dos fechas). Nunca un payload |
| `queue` / `worker` | `VARCHAR(100)` | Diagnóstico |
| `failed_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

- **Migración propia:** `python -m task_queue.migrate [--dry-run] [--allow-demo]` (desde `services/`), nunca al arrancar. `CREATE SCHEMA IF NOT EXISTS ops`, RLS sin políticas, `REVOKE ALL` a `PUBLIC` y a `anon`, `authenticated` y `service_role`, comprobación posterior de privilegios y todo en una transacción, como `job_runner.migrate`. Las dos migraciones deben poder ejecutarse en cualquier orden sobre el mismo esquema (un test lo comprueba). En una base no local exige `--allow-demo`, solo con la confirmación del usuario.
- **Si la base no está disponible al registrar:** un reintento corto del `INSERT` (1 s) dentro del manejador del fallo definitivo; si vuelve a fallar, una línea `ERROR` en el log con todos los campos de la fila (`dead letter not stored: <Clase>`) y la tarea termina igual en `FAILURE`. Nada se pierde del todo: queda en el log. Lo mismo con la tabla sin migrar (`ProgrammingError`).
- **¿También cola de Celery?**

| Opción | Qué |
|---|---|
| **A (recomendada)** | Solo el registro en la tabla. Reencolar una fila es una operación manual (fuera de este ticket) |
| B | Además, publicar un mensaje ligero (`task_id`, nombre, intento) en una cola `nexova.dead_letter` sin consumidores, que Flower muestra en «Broker» con su longitud | Hace visible la DLQ en la captura de Flower; a cambio, una cola que solo crece, en un Redis con `noeviction` |

### A10 — `GET /tasks/{task_id}`

> **Estado: decidida por el usuario el 2026-11-20.** Como se propone (propietario o admin, 404 en otro caso, `RETRY` → `started`), **con un añadido:** la clave de metadatos no puede caducar mientras la tarea siga en cola o en curso; con el worker caído más de 1 h, `/tasks/{id}` no debe dar 404 de una tarea viva. Cómo (renovarla al empezar o al terminar, o un TTL mayor que el del resultado) se propone en la parada 3.

- **Autenticación:** Bearer, cualquier rol (`get_current_user`). `Cache-Control: no-store`.
- **Propiedad:** al encolar, la API guarda en Redis `nexova:task:<task_id>` → `{owner_id, task_name, enqueued_at}` con la misma caducidad que el resultado (3600 s). Solo el propietario o un `admin` ven la tarea; **a cualquier otro, 404** (no 403: así no se confirma que el id existe).
- **Id inexistente:** Celery devuelve `PENDING` para cualquier id. Con la clave de metadatos, un id que la API no encoló, uno caducado o uno que no es UUID → **404 `task_not_found`**. Sin esa clave, `/tasks/` respondería `pending` para siempre a un id inventado.
- **Mapeo de estados:**

| Celery | `status` | Notas |
|---|---|---|
| `PENDING` (con metadatos) | `pending` | En la cola, aún sin worker |
| `RECEIVED` | `pending` | Solo con eventos activados |
| `STARTED` | `started` | Requiere `task_track_started` (A7) |
| `RETRY` | **`started`** (recomendado) o `pending` | Recomendado `started`: la secuencia que ve el cliente es monótona (`pending → started → success/failure`) y no vuelve atrás entre reintentos |
| `SUCCESS` | `success` | |
| `FAILURE` | `failure` | |
| `REVOKED` | `failure` | No hay revocación desde la API; solo por Flower o la CLI |

- **`result`:** `null` en `pending` y `started`; en `success`, el reporte con su forma actual `{"period", "metrics"}` (validado con `TelemetryReport`, como hoy en §48); en `failure`, un objeto fijo `{"code": "task_failed", "detail": "the task failed"}`, **sin** clase, mensaje ni traza (el detalle está en el log y en la DLQ).
- **Flower y el result backend:** Celery guarda en Redis el tipo y el mensaje de la excepción, y Flower los muestra. Para que ahí no aparezca un host ni una consulta, el fallo definitivo se relanza como una excepción propia con el texto ya redactado (A12).

### A11 — Respuesta del endpoint al encolar

> **Estado: decidida por el usuario el 2026-11-20.** Opción A: `202` con `Location`; `503 task_queue_unavailable` si Redis no responde.

`202 {"task_id": "<uuid>"}` con `Location: /tasks/<uuid>` (recomendado: es lo habitual con 202 y no cambia el cuerpo que pide el ticket). Si Redis no responde: **503 `task_queue_unavailable`**, `detail` fijo y sin la URL. Se añaden a `SPECS.md` §4.

### A12 — Logs y redacción

> **Estado: decidida por el usuario el 2026-11-20.** A y A: la redacción de `job_runner.redact` y un filtro en las trazas de Celery.

- **Línea por ejecución** (señales de Celery: `task_prerun`, `task_postrun`, `task_retry`, `task_failure`), en el logger `task_queue`: `task_id=… task=… attempt=2/4 status=retry duration_ms=… error=OperationalError: …`. Estados: `started`, `success`, `retry`, `failure`, `dead_letter`.
- **«Mensaje de error completo» frente a la redacción:**

| Opción | Qué |
|---|---|
| **A (recomendada)** | Clase y mensaje completos de la excepción, **después** de `redact` (quita URL con esquema y los valores de las variables secretas) y truncados a 2 000 caracteres; de un error de SQLAlchemy, solo las clases, porque su mensaje lleva SQL y datos de conexión. Es lo que ya hace `services/job_runner/redact.py` (`describe_exception`) |
| B | El mensaje sin redactar, solo en el log | El log de la API ya promete no llevar mensajes de excepción (`SPECS.md` §5) |
| C | Solo la clase | No cumple «mensaje completo» |

- **Reutilizar la redacción:** **A (recomendada)** importar `job_runner.redact` (biblioteca sin dependencias de su `config.py`) y copiar `job_runner/` en la imagen de la API; B mover `redact.py` a `packages/shared` y que lo usen los dos (refactor de DEV-53, fuera de alcance); C duplicarlo en `task_queue`.
- **Las trazas de Celery:** `celery.app.trace` registra la excepción con su mensaje y su traza. Un filtro de logging en el worker aplica la misma redacción al mensaje y al texto de la traza antes de emitirlos.

### A13 — Fallos controlados para la demostración

> **Estado: decidida por el usuario el 2026-11-20.** Opción A: lock + `statement_timeout` en el efímero, sin interruptor en el código.

| Opción | Cómo | En producción |
|---|---|---|
| **A (recomendada)** | **Fallo real, sin código:** en el Postgres efímero, una sesión `psql` mantiene `LOCK TABLE telemetry_events IN ACCESS EXCLUSIVE MODE` dentro de una transacción. La consulta del worker espera hasta el `statement_timeout` (en la demo, bajado a ~5 s con una variable del override no versionado) → `QueryCanceled` (una `OperationalError`) → 3 reintentos con su cuenta atrás → DLQ. La tabla de la DLQ no está bloqueada, así que el registro funciona. Al soltar el lock, la siguiente tarea termina en `success` | Ningún interruptor: solo se usa el `statement_timeout`, que sirve también como límite real |
| B | Una tarea de prueba `task_queue.always_fails`, registrada **solo** en los tests y en un worker arrancado con `TASK_QUEUE_DEMO_TASKS=1`; se encola con `celery call` desde dentro del contenedor, sin endpoint HTTP | Variable apagada por defecto, pero el código queda en la imagen |
| C | Variable que hace fallar la tarea real (`FAIL_TELEMETRY_REPORT=1`) | Interruptor peligroso: descartada |

La tarea **completada** de la captura es un reporte normal; la **fallida**, la de A13-A. Se ven las dos en Flower («Tasks», con `SUCCESS` y `FAILURE`) y la fila con `SELECT … FROM ops.task_dead_letters`.

### A14 — Dependencias (necesitan tu autorización explícita)

> **Estado: decidida por el usuario el 2026-11-20.** Autorizadas `celery[redis]>=5.7,<5.8`, `redis` (el rango que admita `kombu` 5.7) y `flower>=2.2,<2.3` en su grupo propio, con `uv lock` (nunca `uv sync`) y requirements con hashes. Si alguna no funciona con Python 3.14.6, se para y se informa: ni se cambia la versión de Python ni se busca otra solución sin el OK del usuario.

| Paquete | Rango propuesto | Dónde | Por qué |
|---|---|---|---|
| `celery[redis]` | `>=5.7,<5.8` | `services/api/pyproject.toml`, dependencias principales | La API envía y lee estados; el worker ejecuta. Trae `kombu` y `billiard` |
| `redis` | el rango que admita `kombu` 5.7 (hoy se publica la 8.1.0) | Principales | La API usa Redis directamente para los metadatos y la deduplicación (A4, A10); el ticket la nombra |
| `flower` | `>=2.2,<2.3` | **Grupo `flower` de uv** (no `dev`) | Solo desarrollo; no entra en la imagen de la API |

- **Exportación:** `requirements.txt` (sin cambios de comando: incluye celery y redis) y un `requirements-flower.txt` nuevo con hashes (`uv export --frozen --no-dev --group flower --no-emit-project`), que instala un target `flower` del `services/Dockerfile`. `tests/test_requirements_lock.py` comprueba los dos archivos y que flower no está en `requirements.txt`.
- **Python 3.14.6** (la imagen): la compatibilidad de las tres con 3.14 no está comprobada (§6, S4). La parada 1 empieza por ahí; si falla, se para y se informa.
- **`uv lock`, nunca `uv sync`** (banco de memoria).

### A15 — Documentación

> **Estado: decidida por el usuario el 2026-11-20.** Como se propone, **con un añadido:** `services/task_queue/` lleva `README.md` y `README.es.md` (como `services/README`), y todo archivo que ya tenga versión `.es.md` se actualiza en los dos idiomas.

- **El worker no va en el `README.md` raíz** (es el briefing de Nexova, `memory-bank/projectbrief.md`). Propuesta:
  - `docs/local-development.md` (solo en español, sin `.es.md`): servicios `redis`, `worker` y `flower` en §3–§4, cómo arrancar (`docker compose up -d worker`), parar (`docker compose stop worker`), ver logs y reiniciar tras un cambio;
  - `services/task_queue/README.md`;
  - fila nueva en `services/README.md` **y** `services/README.es.md`;
  - `services/api/SPECS.md`: Parte J (`/tasks`, 202, 503, estados) y cambios en §41 (sale `telemetry_report`) y §48;
  - `.env.example`: `REDIS_URL`, `REDIS_PASSWORD`, `FLOWER_BASIC_AUTH`.
- **`AGENTS.md` §4:** una fila de validación para `services/task_queue/` (unitarios sin Redis; integración con `TASK_QUEUE_TEST_REDIS_URL` y `TASK_QUEUE_TEST_DATABASE_URL` locales, 0 omitidos), `redis`/`worker`/`flower` en la fila y el bloque «Docker» (aislamiento de `REDIS_URL`), y un bloque «Cola de tareas (DEV-55)» con la documentación, la migración (`--dry-run`, demo solo con confirmación) y la verificación en el navegador de `/telemetry`.
- **Guía de revisión:** `docs/async-tasks/review.md` (arranque del efímero, recorrido, A13, la tabla de §9 con evidencias, lo no verificado y la limpieza).

### A16 — Frontend (`uis/backoffice` → `/telemetry`)

> **Estado: decidida por el usuario el 2026-11-20.** Opción A: sondeo con los estados «En cola» y «Calculando».

| Opción | Qué |
|---|---|
| **A (recomendada)** | El servicio pide `GET /telemetry/report` (202) y sondea `GET /tasks/{id}` con espera creciente (1 s, después 2 s, tope 3 s); cancela al salir; estados de pantalla «En cola», «Calculando» y error con «Reintentar»; deja de sondear a los 10 min (peor caso: 4 ejecuciones de 150 s más las cuentas atrás) con un mensaje propio. El normalizador del reporte se reutiliza para `result`. Reglas en `uis/backoffice/CLAUDE.md` («Telemetría») y tests de `node:test` |
| B | Sin cambio de interfaz: el servicio espera internamente hasta el resultado y la vista no cambia | Más simple, pero no muestra en qué fase está |

## 6. Suposiciones (sin verificar)

| # | Suposición | Cómo se verifica |
|---|---|---|
| S1 | El volumen de `telemetry_events` en la demo está en los miles de eventos por semana (plan §8, sin medir) | Solo con la confirmación del usuario: un `count(*)` de solo lectura con `business_performance.readonly` |
| S2 | Encolar cuesta unos pocos ms (publicar en Redis + una clave de metadatos), así que el 202 queda en 10–40 ms con la autenticación incluida | Parada 3: `api.timing` y el script de ráfagas, con el stack contra el efímero |
| S3 | El jitter de Celery (`retry_jitter=True`) puede dar una cuenta atrás de 0 s (elige al azar entre 0 y la cuenta atrás calculada), por lo que conocemos de su código | Parada 2: leer `get_exponential_backoff_interval` de la versión instalada |
| S4 | celery 5.7, kombu 5.7, redis 8.1 y flower 2.2 funcionan con Python 3.14.6 | Parada 1, en la imagen |
| S5 | En el despliegue real, cada tarea paga además ~400 ms de conexión a Supabase (`NullPool`, F0 de caching) y el registro en la DLQ otros tantos | Fuera de la demo, no se mide; el worker podría usar un pool propio (fuera de alcance) |
| S6 | Flower muestra el estado de las tareas a partir de los eventos y no del result backend, así que hacen falta `worker_send_task_events` y `task_send_sent_event` | Parada 1 |

## 7. Plan de F1 por paradas

Cada parada se verifica por separado y espera tu OK antes de la siguiente. Todo contra el Postgres efímero y un Redis efímero; nunca la demo.

1. **Redis, worker y Flower con una tarea trivial.** Dependencias (si se autorizan, A14), `services/task_queue/` con `celery_app.py`, configuración de A7 y una tarea `task_queue.ping`; `redis`, `worker` y `flower` en Compose; `.env.example`. **Verificación:** `docker compose config --quiet`; `docker compose up -d --build` con todo `healthy`; el log del worker conectado a `redis://redis:6379/0` (sin contraseña en el log); `celery call task_queue.ping` → `SUCCESS` visible en Flower (`127.0.0.1:5555`); `REDIS_URL` ausente en `ui`; `test_requirements_lock.py`; suite de `services/api` en la imagen si Windows bloquea el venv.
2. **Reintentos, DLQ y migración.** Backoff de A8, `ops.task_dead_letters`, `task_queue.migrate`, repositorio, logs y redacción (A12). **Verificación:** unitarios sin Redis (función de backoff, clasificación de excepciones, manejador del fallo definitivo con una base SQLite, redacción, mapeo de estados); migración en el efímero (`--dry-run`, aplicar, segunda vez «nada que migrar», RLS y `REVOKE`, orden indiferente con `job_runner.migrate`); integración con Redis efímero y un worker real (`-P solo`): una tarea de prueba que falla registra 4 intentos con cuentas atrás crecientes (marcas de tiempo del log) y una fila en la DLQ; base caída al registrar → línea de log.
3. **La operación, el 202 y `/tasks`.** Tarea `task_queue.telemetry_report`, `GET /telemetry/report` → 202, `GET /tasks/{id}`, A4, A10 y A11, `SPECS.md`. **Verificación:** tests de contrato (202 sin tocar la base, 422 sin tarea, 401, 404 de un id ajeno o inventado, mapeo de estados, 503 con Redis caído); con el stack aislado contra el efímero (500 k eventos): **202 en < 200 ms** medido con ráfagas y con `api.timing`, ciclo `pending → started → success` sondeado; A13 → log con los reintentos y fila en la DLQ (**fragmento de log para la PR**); con mensajes en cola, `docker compose stop api` no para el worker y los mensajes se procesan; con el worker parado, se encolan N, se reinicia Redis (AOF) y al arrancar el worker se procesan los N; `kill -9` del proceso hijo a mitad de tarea → el mensaje vuelve y termina.
4. **Frontend `/telemetry`** (A16). **Verificación:** la fila de `uis/backoffice` (`typegen`, `tsc`, `lint`, `build`, `node:test`, Jest) y el navegador contra el stack aislado: carga, «En cola»/«Calculando», resultado, fallo (A13), API parada, salir a mitad (sin sondeos colgados) y 375 px sin scroll horizontal.
5. **Documentación y verificación final.** A15, la guía de revisión con la tabla de §9, la **captura de Flower** con una tarea completada y otra fallida (y la fila de la DLQ), todas las filas de validación que toca el cambio, el banco de memoria y el commit con tu OK. La etiqueta `async-tasks` se crea y se añade a la PR solo con tu confirmación (H13).

## 8. Entregables de la PR y dónde se obtienen

| Entregable | Parada | Cómo |
|---|---|---|
| Endpoint elegido y justificación | F0 (este documento, §4) | Texto de §4 |
| Captura de Flower: una tarea completada y una en la DLQ | 5 (con lo montado en la 3) | Flower contra el efímero; la fila de la DLQ con una consulta. Solo en la PR, sin versionar (decidido el 2026-11-20) |
| Fragmento de log con un reintento | 3 | `docker compose logs worker` durante A13, con las líneas `status=retry` y sus cuentas atrás |
| Etiqueta `async-tasks` | 5 | `gh label create` y `gh pr edit --add-label`, con tu confirmación |

## 9. Criterios de evaluación y cómo se comprueban

| Criterio (resumen) | Comprobación | Parada |
|---|---|---|
| Redis en Docker y workers conectados sin errores de configuración | `docker compose ps` (`redis` y `worker` `healthy`), log de arranque del worker, `inspect ping` | 1 |
| El endpoint responde 202 con `task_id` en < 200 ms, sea cual sea la duración de la tarea | Ráfagas contra el stack aislado con 500 k eventos (tarea de ~8 s): p95 del 202 < 200 ms; `api.timing`; test de que la ruta no pide `get_db` | 3 |
| `GET /tasks/{id}` da el estado correcto en cada fase | Sondeo registrado de `pending → started → success` y de `→ failure`; tests del mapeo y del 404 | 3 |
| Reintentos con backoff, nunca inmediatos | Marcas de tiempo del log entre intentos (≥ 2, 4 y 8 s); test de la función de backoff con el mínimo | 2 y 3 |
| Tras agotar los reintentos, la tarea está en la DLQ con `task_id`, intento y error | Fila en `ops.task_dead_letters` (A13); test de integración | 2 y 3 |
| Parar la API no para el worker ni pierde mensajes | `docker compose stop api` con mensajes en cola y una tarea en curso: el worker sigue y termina todo; reinicio de Redis con AOF | 3 |
| Mensajes solo con referencias | Mensaje leído de Redis (`LRANGE` de la cola con el worker parado): solo `start` y `end`; test del cuerpo enviado | 3 |
| Flower muestra al menos una tarea completada y una fallida | Captura | 5 |

## 10. Limpieza al cerrar F0

| Elemento | Estado |
|---|---|
| Contenedores `nexova-dev55-pg`, `nexova-dev55-api`, `nexova-dev55-prefect` y `nexova-dev55-worker`, red `nexova-dev55-net` y el volumen anónimo del Postgres efímero | Borrados al terminar. Quedan otros 19 volúmenes anónimos huérfanos de sesiones anteriores (2026-10-24 a 2026-11-16), que no son de esta y no se han tocado |
| TinyDB de prueba y cuenta `dev55-admin@example.invalid` | Solo existían en el scratchpad de la sesión; borrados con él |
| Stack del usuario (`nexova-api-1`, `nexova-ui-1`) | Sin tocar |
| Demo (Supabase) y `services/api/data` | Sin ninguna conexión ni escritura |
| Imágenes | Ninguna descargada ni construida (se usaron las que ya estaban) |
