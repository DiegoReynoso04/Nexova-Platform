# Cola de tareas asíncronas (DEV-55): guía de revisión

> **Ticket:** #DEV-55 (enunciado solo local en `contexts/dev-55/`, igual que los briefings de hito).
>
> **Rama:** `feature/async-task-queue`, desde `main` en `5be61d3` (PR #38). Commits:
>
> - F0, `dd2f82b`: análisis y decisiones;
> - parada 1, `d9e585b`: Redis, worker y Flower;
> - parada 2, `e624074`: reintentos, DLQ y migración;
> - parada 3, `fc84b59`: la API encola y `GET /tasks/{id}`;
> - parada 4, `8678323`: `/telemetry` del backoffice;
> - parada 5: documentación y verificación final.
>
> Análisis y decisiones A1–A16: [`analysis.md`](./analysis.md). Contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) §48 y Parte J. Arranque y operación del worker: [`docs/local-development.md`](../local-development.md) §3.1.

## 1. Qué se ha hecho

| Pieza | Dónde | Qué hace |
|---|---|---|
| Broker y backend | Servicio `redis` de Compose | `redis:8.10.3-alpine3.23` fijada por digest, `127.0.0.1:6379`, contraseña fuera de los argumentos del proceso, AOF en un volumen, 128 MB `noeviction`, `restart: unless-stopped` |
| Worker | Servicio `worker` (imagen de la API, otro comando) | `celery -A task_queue.celery_app worker`: proceso aparte de FastAPI, usuario no root, lista blanca de variables (`REDIS_URL`, `DATABASE_URL`, `TZ`) |
| Monitor | Servicio `flower` | `127.0.0.1:5555` con autenticación básica; Flower solo en el target `flower` (fuera de la imagen de la API) |
| Cola | [`services/task_queue/`](../../services/task_queue/README.es.md) | Configuración de A7 (JSON, `acks_late`, `reject_on_worker_lost`, límites de 120/150 s, prefetch 1), `ReliableTask` (reintentos con backoff propio, DLQ, una línea de log por ejecución, errores redactados), `ops.task_dead_letters` y su migración, productor `client.py` y la tarea del reporte |
| Operación convertida | `services/api` → `GET /telemetry/report` | Valida y encola (`start` y `end`), y responde **202 `{task_id}`** con `Location`, sin tocar la base |
| Estado | `services/api` → `GET /tasks/{task_id}` | `pending`, `started`, `success`, `failure`; solo el propietario o un admin; 404 si no |
| Frontend | `uis/backoffice` → `/telemetry` | Encola y sondea; «En cola», «Calculando», resultado y error con «Reintentar» |

**Endpoint elegido y por qué** (§4 del análisis): `GET /telemetry/report`, la única operación de la API cuyo coste es cálculo dentro de su proceso y crece con los datos. Con la ventana por defecto tardaba 0,24 s con 10 k eventos, 1,7 s con 100 k y 8,3 s con 500 k. Con 4 en paralelo tardaba ~30 s cada uno y frenaba a las demás peticiones por el GIL. Además, encaja con las reglas del patrón: dos fechas en el mensaje y ~20 KB de resultado sin datos personales.

## 2. Desviaciones del enunciado, en una línea cada una

- **`services/task_queue/` en vez de `services/celery_app.py`:** la convención del monorepo no admite código suelto en `services/` (cada servicio con su carpeta y README); el comando es `celery -A task_queue.celery_app worker`.
- **`max_retries=3` con 4 ejecuciones:** se tomó literal (A8). En Celery son 1 + 3, y la DLQ guarda `attempt=4` y `retries=3` para que no haya dudas.
- **El worker se documenta en `docs/local-development.md` (§3.1), no en el `README.md` raíz:** el README raíz es el briefing de empresa de Nexova.

## 3. Cómo verificarlo (nunca contra la demo)

**Stack normal:** `docker compose up -d` y `docs/local-development.md` §3.1. Ojo: allí la `DATABASE_URL` es la demo, así que la verificación se hace en un stack aislado.

**Stack aislado de la verificación** (lo usado en las paradas 3 y 4; nada de esto se versiona):

1. **Postgres efímero** con un rol sin superusuario y una base `nexova_test`. Por ejemplo `docker run -d --name nexova-dev55-pg -e POSTGRES_PASSWORD=… postgres:17.6-alpine3.22`, y en él `CREATE ROLE nexova_app LOGIN NOSUPERUSER PASSWORD '…'` y `CREATE DATABASE nexova_test OWNER nexova_app`.
2. **Proyecto de Compose aparte** (`name: nexova-dev55`) con un override en una carpeta temporal:
   - `api` y `worker` con `DATABASE_URL` al efímero;
   - TinyDB de la API en un volumen propio (nunca `services/api/data`);
   - puertos solo en `127.0.0.1` y distintos (8100, 6380, 5556, 3101);
   - red `nexova-dev55-net`;
   - sin `--reload` en la API.

   Después, `docker network connect nexova-dev55-net nexova-dev55-pg`.
3. **Esquemas en el efímero:**
   - `python -m app.modules.telemetry.migrate` (en el contenedor `api`);
   - `python -m task_queue.migrate` y `python -m job_runner.migrate`, desde un contenedor con `--network container:nexova-dev55-pg`, porque la guarda solo acepta `localhost`.
4. **Datos:** `docs/telemetry/report-seed-ephemeral.sql` y copias sintéticas de sus filas, con fecha aleatoria dentro de los últimos 7 días, hasta ~500 000 eventos en la ventana.
5. **Cuentas de prueba** en la TinyDB del contenedor (`create_admin` y `POST /users`), con `@example.invalid`. Para medir la primera petición, un token generado dentro del contenedor.
6. **Tests de integración de `task_queue`:** un Redis de prueba con `--network container:nexova-dev55-pg --bind 127.0.0.1` y, en la imagen de la API: `docker run --rm --network container:nexova-dev55-pg -v "<repo>:/repo:ro" -w /repo -e PYTHONPATH=/repo/services -e TASK_QUEUE_TEST_DATABASE_URL=postgresql://nexova_app:<pw>@127.0.0.1:5432/nexova_test -e TASK_QUEUE_TEST_REDIS_URL=redis://:<pw>@127.0.0.1:6379/10 --entrypoint python nexova-api:latest -m unittest discover -s services/task_queue/tests -t services`.
7. **Fallo controlado (A13):**
   - `TASK_QUEUE_STATEMENT_TIMEOUT_MS=5000 docker compose … up -d --force-recreate worker` (solo en el stack aislado);
   - en `psql`: `BEGIN; LOCK TABLE telemetry_events IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(75); COMMIT;`;
   - pedir el reporte. Al terminar, recrear el worker sin la variable.
8. **Navegador:** entrar por `http://localhost:3101`; por `127.0.0.1`, `next dev` bloquea sus recursos (`allowedDevOrigins`).

## 4. Criterios de evaluación del ticket y sus evidencias

Las evidencias (logs, sondeos, mediciones y capturas) están en `contexts/dev-55/evidencias/`, solo en local. Aquí van las cifras.

| Criterio (resumen propio) | Cómo se comprobó | Resultado |
|---|---|---|
| Redis en Docker; workers conectados sin errores de configuración | `docker compose ps` y el log de arranque del worker | `redis`, `worker` y `flower` `healthy`. «Connected to `redis://:**@redis:6379/0`» y «ready», sin avisos. `task_queue.ping` termina en `SUCCESS` |
| 202 con `task_id` en < 200 ms, sea cual sea la duración de la tarea | Ráfagas contra el stack aislado con ~500 k eventos y reportes de 8–50 s en curso, más `api.timing` | **p95 de 32,9 ms** en cliente y **30,0 ms** en `api.timing` (50 peticiones con dos reportes en curso, 2026-11-20). **p95 de 10,3 ms** en otra ráfaga de 200 (2026-11-22). La primera petición del proceso, 48–100 ms; un caso de 4,8 s con la máquina lenta, explicado en `analysis.md` (A11). La ruta no abre conexión con la base (test) |
| `GET /tasks/{id}` correcto en cada fase | Sondeo cada 250–1000 ms y tests del mapeo | `pending → started → success` y `pending → started → failure`. `RETRY` → `started`. 404 para un id inventado, uno mal formado o una tarea ajena (200 al admin). Los metadatos duran 7 días mientras la tarea vive y 1 h al terminar (A10) |
| Reintentos con backoff, nunca inmediatos | Marcas de tiempo del log del worker y test del mínimo | Esperas entre intentos de 2,19, 5,12 y 9,35 s (mínimos 2, 4 y 8) en A13; de 3,24, 5,37 y 8,52 s en la integración. El jitter de Celery podía dar 0 s (comprobado en su código): se usa uno propio |
| Tras agotar los reintentos, en la DLQ con `task_id`, intento y error | Fila en `ops.task_dead_letters` (Postgres efímero) | `attempt=4`, `retries=3`, `max_retries=3`, `reason=retries_exhausted`, `error_message=OperationalError (QueryCanceled)`. Si la base no responde o falta la tabla, una línea `dead_letter_not_stored` con todos los campos |
| El worker es un proceso aparte: parar la API no lo para ni pierde mensajes | `docker compose stop api` con 5 mensajes en cola; Redis reiniciado; `kill -9` de un hijo | Con la API parada, el worker terminó los 5 (cola a 0). Tras `restart redis` con AOF, la cola pasó de 5 a 5. Tras el `kill -9` de un hijo a mitad de tarea, `WorkerLostError` y el mensaje se reentregó y terminó en `success` |
| Mensajes con solo identificadores o referencias | `LRANGE nexova.tasks` con el worker parado | Mensajes de 1 117 bytes con `kwargs` = `{start, end}`. Ningún dato. Lo comprueba también un test |
| Flower muestra al menos una tarea completada y una fallida | Captura de Flower contra el stack aislado | Lista con una `SUCCESS` y una `FAILURE` (la de A13, con `Retries 3` y `TaskFailedError(... QueryCanceled)`), y su fila en la DLQ |

Además, para la PR:

- el fragmento de log con los reintentos (§5);
- el sondeo de estados;
- las mediciones del 202;
- la confirmación de que ni el log, ni el result backend, ni Flower muestran SQL ni parámetros (tras el arreglo del envoltorio de Pandas).

## 5. Fragmento de log con un reintento (A13, 2026-11-20)

```text
attempt=1/4 status=started
attempt=1/4 status=retry duration_ms=7121.87 countdown_s=2.18 error_class=OperationalError error="OperationalError (QueryCanceled)"
attempt=2/4 status=started                                    (2,19 s después)
attempt=2/4 status=retry duration_ms=5009.68 countdown_s=5.12 …
attempt=3/4 status=started                                    (5,12 s después)
attempt=3/4 status=retry duration_ms=5007.37 countdown_s=9.34 …
attempt=4/4 status=started                                    (9,35 s después)
attempt=4/4 status=dead_letter duration_ms=5007.23 reason=retries_exhausted error_class=OperationalError error="OperationalError (QueryCanceled)"
attempt=4/4 status=dead_letter_stored duplicate=False table=ops.task_dead_letters
```

(Las líneas completas, con marca de tiempo y `task_id`, están en `contexts/dev-55/evidencias/log-reintentos-y-dlq.txt`.)

## 6. Validación

Filas de `AGENTS.md` §4 que toca la rama, con el resultado de la verificación final de la parada 5 en `memory-bank/progress.md`:

- **Docker:** `docker compose config --quiet`;
- **`services/api`:** `unittest` y pytest;
- **`services/task_queue`:** 0 omitidos con las dos variables de integración;
- **`services/job_runner`:** su test de planificadores no se modificó y pasa;
- **`uis/backoffice`:** `typegen`, `tsc`, `lint`, `build`, `node:test` y Jest.

## 7. Lo no verificado

- **La demo:** ni se migró `ops.task_dead_letters` en ella ni se ejecutó el worker contra ella. Hasta migrarla (solo con la confirmación del usuario), un fallo definitivo con el stack normal queda solo en el log.
- **El tope de 10 min del sondeo del backoffice:** solo en tests (reloj falso).
- **El límite duro de tiempo (150 s) con la tarea real:** solo en la integración con tiempos cortos (2/4 s).
- **Un despliegue con varios workers o réplicas:** solo se probó con 1 worker de concurrencia 2.
- **El 503 con el servicio `redis` parado tarda ~4 s:** es lo que tarda el DNS de Docker en no resolver el nombre, no la cola.

## 8. Limpieza

Al cerrar la parada 5 se borraron:

- el proyecto aislado `nexova-dev55`: contenedores, red `nexova-dev55-net` y volúmenes `redis-data` y `dev55-tinydb`;
- el Postgres efímero `nexova-dev55-pg` y su volumen;
- el Redis de prueba `nexova-dev55-redis`.

Las evidencias siguen en `contexts/dev-55/` (ignorada por git). El stack normal del usuario no se arrancó.

## 9. Pendientes (fuera de la rama)

- **Migrar `ops.task_dead_letters` en la demo:** `python -m task_queue.migrate --dry-run`, y después `--allow-demo`, solo con la confirmación del usuario.
- **`scripts/seed_volume.py inventory` está roto** (H14: `unit_cost` obligatorio en `InboundOrderCreate`).
- **Un error intermitente de `unittest` de `services/api`** visto una vez el 2026-11-20 y no reproducido en todas las ejecuciones posteriores (no se sabe qué test fue).
