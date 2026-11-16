# DEV-53 — Script nocturno de telemetría: análisis y decisiones (F0)

**Estado: F0, solo análisis. Nada de código.** Rama `feature/nightly-telemetry-export`, desde `main` en `f88e3a4` (PR #35). Las decisiones de la sección M están **pendientes de tu respuesta**; hasta entonces F1 no empieza.

**Decisiones (2026-11-15): M1–M18 aprobadas tal como se recomendaban, con cuatro precisiones del usuario** (recogidas en las secciones correspondientes y en la sección M):

- **M10:** además de quitar `user_id` y `session_id`, las claves de `tags` que se exportan salen de una **lista blanca explícita** (no de una lista negra). Ver E.2.1.
- **M5:** se quita el cron de `weekly`; hay que dejar trazado en `PIPELINE_DESIGN.md` §4.5 y en el README del pipeline que la programación pasó al job nocturno (DEV-53), con fecha y motivo, y ajustar el test de `serve.py` sin debilitarlo.
- **M13:** supercronic autorizado con condiciones: versión exacta, SHA-256 verificado en el `Dockerfile` (el build falla si no coincide), descarga solo en el build, contenedor con usuario no root, y versión y checksum documentados aquí y en la PR. Ninguna otra dependencia nueva.
- **M14:** el perfil `nightly` sigue apagado por defecto; arrancarlo contra la demo es decisión aparte del usuario. `data/raw/telemetry_*.csv` entra en `.gitignore` en la parada 2.

El documento sigue el orden A–L de tu encargo. Cada punto lleva una recomendación y su porqué. Lo que no he podido comprobar está marcado como **(verificar)** y se comprueba en F1.

## 0. Punto de partida (verificado en el repo)

| Hecho | Dónde se comprobó |
|---|---|
| El comando de referencia del enunciado (`python -m data.pipelines.telemetry_kpi_daily.run --no-prefect`) **no existe**. Nuestro entry point es `python data/pipelines/pipeline.py` (Prefect 3.9, con servidor efímero si no hay `PREFECT_API_URL`). Sin opciones recalcula la última semana cerrada. | `data/pipelines/pipeline.py` (`main`), `PIPELINE_DESIGN.md` §4.5 |
| El pipeline es **semanal**: `check_weeks` rechaza la semana en curso y las anteriores a hoy − 84 días (`RETENTION_GUARD_DAYS`). Códigos de salida: 0 completada, 1 corrida fallida, 2 configuración, argumentos o esquema ausente. | `packages/shared/nexova_shared/reporting/weeks.py`, `vocabulary.py` |
| El pipeline lee `telemetry_events` **por SQL** (nunca un CSV) y ya tiene su propio log, `reporting.pipeline_runs`, con un índice único parcial (`status = 'running'`) y cierre de abandonadas a los 30 min (`Abandoned`). | `business_performance/repository.py`, `migrate.py` |
| Hay un deployment cron semanal (`weekly`, lunes 06:00 `Europe/Madrid`) que solo existe con el perfil `pipelines` (servidor de Prefect + worker). El worker **no** tiene `DATABASE_URL`: la lee de un block `Secret`. | `business_performance/serve.py`, `docker-compose.yml` |
| `telemetry_events`: `event_id`, `event_type`, `timestamp` (timestamptz), `service`, `user_id`, `session_id`, `schema_version`, `tags` (JSONB), inmutable (sin `UPDATE`/`DELETE`). Retención de los eventos en bruto con `userId`: **90 días** (D9 del plan). | `services/api/app/modules/telemetry/models.py`, `docs/telemetry/telemetry-plan.md` |
| La imagen `nexova-pipeline` ya trae Python 3.14.6, Prefect, SQLAlchemy 2.1 y `psycopg2-binary`: **ni el script ni `job_runner` necesitan dependencias nuevas**. No lleva `services/` ni `scripts/`; el contexto `data/` excluye `raw` y `eval`. | `data/Dockerfile`, `data/.dockerignore`, `data/pipelines/pyproject.toml` |
| `main.py` de la API usa `lifespan=inventory_lifespan` (crea las tablas del inventario): es legítimo y **no** es un planificador. Ningún `APScheduler`/`repeat_every` en `services/api/app`. | `grep` en `services/api/app` |
| `data/raw/telemetry_*.csv` **no** está en `.gitignore` hoy. | `git check-ignore` |
| **Docker Desktop no está en marcha ahora** (el motor no responde por la tubería `dockerDesktopLinuxEngine`). F0 no lo necesita; F1 sí (Postgres efímero). No lo he tocado: lo arrancas tú cuando toque. | `docker version` |

## A. Qué lanza el script como subproceso

### A.1 Comando

`[sys.executable, "<repo>/data/pipelines/pipeline.py", "--week-start", "<lunes>"]`, con la raíz del repo como `cwd`.

- **Mismo intérprete que el script.** Todo el job corre con el entorno de `data/pipelines` (su `.venv` en el host, la imagen `nexova-pipeline` en Docker), que ya tiene Prefect y SQLAlchemy. Con el venv de `services/api` el hijo fallaría por falta de Prefect; el job lo registraría como `failed` con un mensaje claro (código de salida 1), no como un fallo silencioso.
- **El pipeline no se toca para esto.** No hace falta un entry point nuevo ni `--no-prefect`: el servidor efímero de Prefect ya es el modo sin servidor del pipeline.
- **Misma base que el hijo.** El script resuelve `DATABASE_URL` con `business_performance.config.resolve_database_target` (entorno y, si falta, solo esa clave del `.env` de la raíz). Así el export y el pipeline no pueden apuntar a bases distintas. `job_runner` no importa `data/pipelines`: recibe el `Engine` inyectado.

### A.2 Qué semana se pasa cada noche, y relación con `TARGET_DATE`

El problema: «ayer» solo cierra semana si es domingo; el resto de noches `check_weeks` rechazaría la semana de ayer.

**Recomendación:** `week = min(lunes_de(target_date), última_semana_cerrada(ahora))`, y se pasa siempre explícita con `--week-start`.

| Noche (UTC) | `target_date` (ayer) | Semana que recalcula el pipeline |
|---|---|---|
| Lunes → ayer = domingo | domingo | **La semana que acaba de cerrarse**, ya con los datos del domingo. Es la noche que importa. |
| Martes a domingo | lunes a sábado | La última cerrada (la misma de siempre): recálculo idempotente, sin cambios si no hay eventos tardíos. |
| `TARGET_DATE` pasado | ese día | La semana de ese día, si cumple `check_weeks`. Una prueba con fecha arbitraria ejercita de verdad la semana correspondiente. |

Por qué así:

- Cumple «lanzar el pipeline» **cada noche** sin tocarlo. El upsert por `(office, programme_id, week_start)` es idempotente (carga bajo `pg_advisory_xact_lock`).
- **Autosanación:** si falla la noche del lunes, la del martes recalcula la misma semana.
- Alternativa descartada: lanzar el pipeline solo cuando `target_date` cierra semana. Dejaría 6 de cada 7 noches sin lanzarlo y contradiría el enunciado.
- Se usa `nexova_shared.reporting.weeks` (solo librería estándar), sin duplicar las reglas.
- **Pequeño defecto conocido:** `pipeline.py` sin `--trigger` registra `trigger = 'manual'` en `pipeline_runs`, también para estas corridas nocturnas. La orquestación queda en `job_runs`; no se cambia el pipeline por esto (ver M4).

### A.3 Códigos de salida, mensaje de error, timeout

| Salida del hijo | `job_runs` | `error_message` (texto fijo, sin salida del hijo) |
|---|---|---|
| 0 | sigue → `completed` | — |
| 1 | `failed` | `pipeline exited with code 1 (run failed; see pipeline_runs and the logs)` |
| 2 | `failed` | `pipeline exited with code 2 (configuration, arguments or reporting schema)` |
| otro / señal | `failed` | `pipeline exited with code N` |
| timeout | `failed` | `pipeline timed out after 1200 s and was killed` |

- **Qué va a `error_message`:** nunca stdout/stderr del hijo (una traza de SQLAlchemy puede llevar host o usuario). Para excepciones propias (la exportación, la base): `Clase: mensaje` pasado por un filtro `redact()` (URLs `postgres…://`, el valor de `DATABASE_URL` y su contraseña) y truncado a 500 caracteres. Para `SQLAlchemyError`, **solo la clase** y la de su `orig` (el mensaje incluye SQL y datos de conexión). La excepción completa va al log solo si pasó por `redact()`.
- **El hijo hereda stdout y stderr:** su salida sigue a los logs del contenedor, como ya hace el pipeline, y no entra en la base.
- **Entorno del hijo con lista blanca:** `PATH`, `DATABASE_URL`, `PREFECT_*`, `DO_NOT_TRACK`, `HOME`/`USERPROFILE`, `SYSTEMROOT` (Windows), `PYTHONPATH`, `TZ`. Nunca `JWT_SECRET_KEY`, `TELEMETRY_SUPPLIER_KEY`, `RESEND_API_KEY`. Lo comprueba un test.
- **Timeout: 20 min.** El pipeline mide 21 s con 10 000 eventos y 129 s con 50 000 (`PIPELINE_DESIGN.md` §4.6), más ~30 s de arranque del Prefect efímero. Al vencer se mata **el árbol de procesos** (Prefect lanza su servidor como nieto): en POSIX, `start_new_session=True` + `os.killpg`; en Windows, `taskkill /T /F` **(verificar en F1)**. Un hijo matado deja una fila `running` en `pipeline_runs` que el siguiente `start_run` cierra a los 30 min; un reintento manual dentro de esa media hora fallará una vez con `RunInProgressError`. Documentado, aceptado.

### A.4 El deployment cron semanal de Prefect

Hoy habría dos disparadores del mismo cálculo: `weekly` (lunes 06:00 Madrid) y el nocturno. Se solapan: el nocturno del lunes (02:00 UTC) ya recalcula la semana cerrada con los datos del domingo, y además mantiene la franja de «frescura» del dashboard `/reporting` al día **sin** perfil `pipelines` (hoy, con el perfil apagado, la demo muestra «desactualizado» pasada una semana).

**Recomendación (M5): quitar el cron de `weekly` y dejar solo `manual`.** El nocturno pasa a ser el único disparador programado; `POST /reporting/pipeline-runs` sigue siendo el disparo a demanda.

- Coste: tocar `serve.py`, `test_trigger_and_serve.py` y `PIPELINE_DESIGN.md` (§4.4, §4.5), que ya están en `main`. Es lo único del pipeline que F1 tocaría.
- Pérdida: el cron semanal recalculaba también «la anterior» (dos semanas). El nocturno recalcula una; con la retención de 90 días y eventos tardíos de minutos, no aporta nada que el nocturno no cubra.
- A verificar en F1: si `serve()` de Prefect retira el deployment `weekly` ya registrado en el servidor o lo deja con su programación (habría que borrarlo en la UI/API del servidor).
- **Alternativa (cero cambios de código):** mantener `weekly`. Riesgo: si coincidieran, uno de los dos fallaría con `RunInProgressError`. Con el nocturno a las 02:00 UTC y el semanal a las 04:00/05:00 UTC no coinciden en la práctica, pero seguirían siendo dos disparadores sin dueño claro.

## B. Modelo `job_runs`

### B.1 Esquema, migración y acceso

**Recomendación (M6): esquema nuevo `ops`, tabla `ops.job_runs`.** Razones: el enunciado la separa de `pipeline_runs` (otra capa), y meterla en `reporting` acoplaría la orquestación al esquema de los reportes y a su migración (`TABLES`, `_granted`). Sin FK ni columnas compartidas con `pipeline_runs`: **no se fusionan**; se correlacionan por `target_date` ↔ `week_from/week_to` y por hora.

Migración propia `python -m job_runner.migrate [--dry-run] [--allow-demo]` (desde `services/`, con el venv/imagen de `data/pipelines`), copiando el **patrón** de `business_performance/migrate.py`:

- `--dry-run` imprime la SQL pendiente y no escribe; sin él, una sola transacción.
- **Nunca al arrancar** nada: ni el script, ni la API, ni el contenedor la ejecutan solos. Si falta la tabla, el script sale con 2 y el comando de la migración.
- Base no local → se niega salvo `--allow-demo`, que solo uso con tu confirmación en el momento.
- Idempotente: solo emite lo que falta («Nada que migrar» la segunda vez).
- **RLS sin políticas** y `REVOKE ALL` sobre el esquema y la tabla a `PUBLIC`, `anon`, `authenticated` y `service_role` (los que existan), con la comprobación final de que ninguno conserva privilegios (si no, se deshace todo). El esquema `ops` no se añade a los esquemas expuestos de la Data API.
- Códigos de salida como `business_performance.migrate`: 0 bien; 1 configuración o rechazo; 2 base no disponible. Los mensajes nunca llevan URL, usuario ni contraseña.
- Se **copia** el patrón (~150 líneas) en lugar de importarlo, para que `services/` no dependa de `data/pipelines`.

### B.2 Campos y tipos (boceto de la DDL; se escribe en F1)

```sql
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.job_runs (
  id            uuid primary key default gen_random_uuid(),
  job_name      text not null,
  target_date   date not null,
  status        text not null check (status in ('pending','processing','completed','failed')),
  started_at    timestamptz,                 -- al pasar a processing
  finished_at   timestamptz,                 -- al pasar a completed o failed
  error_message text,
  created_at    timestamptz not null default now(),
  constraint ck_job_runs_finished check ((status in ('completed','failed')) = (finished_at is not null)),
  constraint ck_job_runs_error    check (error_message is null or status = 'failed'),
  constraint ck_job_runs_msg_len  check (char_length(error_message) <= 1000)
);
CREATE INDEX IF NOT EXISTS ix_job_runs_job_target ON ops.job_runs (job_name, target_date);
-- el lock (C.2):
CREATE UNIQUE INDEX IF NOT EXISTS ux_job_runs_one_processing
  ON ops.job_runs (job_name) WHERE status = 'processing';
-- la idempotencia como garantía de base de datos (D):
CREATE UNIQUE INDEX IF NOT EXISTS ux_job_runs_one_completed_per_day
  ON ops.job_runs (job_name, target_date) WHERE status = 'completed';
```

- Los campos mínimos del enunciado están todos (`id`, `job_name`, `target_date`, `status`, `started_at`, `finished_at`, `error_message`, `created_at`); no añado más.
- El índice `(job_name, target_date)` que pide el enunciado es `ix_job_runs_job_target`.
- **Las marcas de tiempo las pone Python** (`:now` en UTC), no `now()` de la base: así el mismo SQL se prueba en SQLite sin cambios y los tests controlan el reloj. `default now()` queda como red de seguridad.
- **Una fila por intento, no una por día (M7).** Con una por día, un reintento tras un fallo tendría que reescribir la fila y se perdería el historial de fallos (la evidencia que pide el enunciado: «en caso de error, el mensaje»). Por intento se conserva cada fallo y cada reintento; la unicidad de `completed` por día hace que «una por día» siga valiendo para lo que cuenta. El índice único parcial es la garantía de base de datos; `has_completed_for_date` es la lectura rápida.

## C. Máquina de estados y lock

```
 INSERT            claim (UPDATE condicional)          fin
  ──► pending ───────────────────────────► processing ─────► completed
         │  (índice único parcial perdido)        │
         ▼                                        └────────► failed
   la fila se borra: nunca llegó a ejecutar
```

### C.1 Una ejecución, paso a paso

1. Validar `TARGET_DATE` (sección I). Si no vale: salida 2, **sin fila**.
2. Resolver la base y comprobar que `ops.job_runs` existe (si no, salida 2 con el comando de migración).
3. **Barrer zombis** (C.3).
4. ¿`has_completed_for_date`? → INFO «omitido por duplicado», salida 0, sin fila (C.4).
5. ¿`has_processing_lock`? → INFO «bloqueado», salida 0. Es solo una vía rápida: la garantía está en el paso 7.
6. `INSERT` de la fila `pending` (commit propio, visible).
7. **Claim atómico:** `UPDATE … SET status='processing', started_at=:now WHERE id=:id AND status='pending'`. Si choca con `ux_job_runs_one_processing` → otra instancia tiene el lock: se borra la fila propia (`DELETE … WHERE id=:id AND status='pending'`), INFO «bloqueado», salida 0.
8. **Re-comprobar `completed` tras el claim.** Hay una ventana real: A termina (`processing → completed`) justo mientras B ejecuta el paso 7 y B ve la fila vieja de A; el índice único ya no estorba y B obtendría el lock sobre un día ya hecho. Si hay un `completed` para ese día, B borra su fila, INFO «omitido por duplicado», salida 0. Si aun así llegara a completar, `ux_job_runs_one_completed_per_day` lo impide.
9. `try`: exportar el CSV (si no existe) → lanzar el pipeline → `UPDATE … SET status='completed', finished_at=:now WHERE id=:id AND status='processing'`.
10. `except BaseException` (incluye `KeyboardInterrupt`, `SystemExit` y el `SIGTERM` convertido en excepción): `UPDATE … status='failed', finished_at, error_message WHERE id=:id AND status='processing'`, log ERROR y relanza el código de salida 1.

Todas las transiciones son **compare-and-set sobre `status`** con comprobación de `rowcount`: si una escritura final afecta a 0 filas (la fila fue barrida como zombi mientras el proceso seguía vivo), el script lo registra como ERROR («lock perdido») y **no** marca `completed`.

### C.2 Por qué el índice único parcial sigue siendo «el estado `processing` es el lock»

El enunciado prohíbe «un segundo mecanismo de bloqueo»: ni tabla, ni columna, ni flag aparte. El índice `UNIQUE (job_name) WHERE status = 'processing'` **no es un mecanismo nuevo**: es la propia columna `status` más una restricción sobre ella. No hay otra cosa que adquirir ni liberar: el lock se toma pasando la fila a `processing` y se libera al pasar a `completed` o `failed`. Comprobar «¿hay alguna `processing`?» y después insertar no es atómico (dos instancias pueden comprobar a la vez y ver «libre»); la restricción hace que **la base** rechace a la segunda en el mismo `UPDATE`. Es lo mismo que ya hace `pipeline_runs` (`ux_pipeline_runs_one_running`). `has_processing_lock` queda como consulta informativa y para el paso 5.

Sin `pg_advisory_lock` (sería un segundo mecanismo, y con el Transaction pooler de Supabase un lock de sesión no es fiable).

### C.3 Filas zombi que el `try/finally` no cubre

`kill -9`, reinicio o `docker stop` con SIGKILL, caída de la base a mitad de corrida.

- **Barrido al inicio de cada ejecución**, antes de mirar el lock: `UPDATE … SET status='failed', finished_at=:now, error_message='Abandoned: processing for more than 45 minutes without finishing (process presumed dead)' WHERE job_name=:j AND status='processing' AND started_at < :now − 45 min`. Mismo criterio que `pipeline_runs` (`Abandoned` a los 30 min).
- **N = 45 min.** El máximo legítimo es export (segundos) + timeout del hijo (20 min) + cierre (<1 min) ≈ 21 min; 45 min deja más del doble de margen para que **nunca** se barra un proceso vivo. Con el cron a 24 h el zombi se limpia en la siguiente noche; un reintento manual puede esperar ≤ 45 min.
- **`pending` huérfanas:** una `pending` con más de 5 min (`created_at`) pasa a `failed` con `Abandoned: pending…`. Solo puede ocurrir si el proceso muere entre el `INSERT` y el claim (milisegundos).
- **`SIGTERM`** (`docker stop`, reinicio ordenado): el script lo convierte en una excepción para que el `except` marque `failed` («terminated by signal») y mate el árbol del hijo. Con `SIGKILL` solo queda el barrido.
- Sin heartbeat (columna que se actualiza cada minuto): añadiría escritura y un campo que el enunciado no pide; con 45 min fijos alcanza.

### C.4 Cancelación por lock y omisión por duplicado con solo 4 estados

**Recomendación (M8): solo log, sin fila.** El enunciado pide «registra la cancelación» y «registra omisión» en el apartado de observabilidad (INFO). Cada alternativa con fila tiene un coste:

- Fila `completed` de omisión: dejaría de significar «se exportó y se lanzó el pipeline», y `ux_job_runs_one_completed_per_day` ni siquiera la admitiría.
- Fila `failed` de cancelación: contaminaría el historial de fallos (alertas, recuentos) con algo que no lo es.
- Columna nueva (`outcome`/`note`) o un quinto estado: el enunciado fija los cuatro estados y dice «al menos» solo para los campos; un estado nuevo es otra cosa.

Con solo log, la tabla describe **ejecuciones reales** y el log describe **intentos**. La instancia que pierde el lock borra su propia fila `pending` (que nunca ejecutó nada); ese `DELETE` es el único borrado del job y solo toca una fila propia en `pending`.

Para que el log sea también «estado resultante» (apartado H), las líneas de omisión y bloqueo llevan `status=skipped` y `status=locked`: valores **solo de log**, no estados de la base.

### C.5 Si falla la propia escritura de `failed`

La garantía es **eventual, no inmediata**; una base caída no se puede escribir:

1. La escritura se reintenta 3 veces (esperas de 1, 2 y 4 s, conexión nueva cada vez).
2. Si sigue fallando: log ERROR con la excepción original y la del fallo de escritura (ambas por `redact()`), salida 1, y la fila queda `processing`.
3. Esa fila **no es un zombi permanente**: el barrido de C.3 la pasa a `failed` en la siguiente ejecución una vez superados los 45 min, y mientras tanto el lock está retenido (correcto: no sabemos si el proceso murió).

## D. Idempotencia por `target_date`

| Situación | Comportamiento |
|---|---|
| Existe `completed` para `(nightly_export, target_date)` | No se exporta, no se lanza el pipeline, **INFO «omitido por duplicado»** con el `target_date`. Salida 0. |
| Existe `failed` (o ninguna) | Se reintenta el mismo día: nueva fila, nuevo intento. |
| El job falló **después** de exportar (p. ej. el pipeline) | El reintento ve el CSV ya escrito y lo **omite**, y relanza solo el pipeline. |
| Dos instancias a la vez | Una gana el lock; la otra sale (C.1). |

**CSV atómico y sin sobrescribir:**

1. Si `data/raw/telemetry_YYYY-MM-DD.csv` existe → no se escribe (INFO «CSV ya existe»).
2. Se escribe en `telemetry_YYYY-MM-DD.csv.part` (misma carpeta) por streaming, `flush` + `fsync`, y después `os.replace` al nombre final. Un fallo a medias deja como mucho un `.part`, que **nunca** se da por bueno (el nombre final no existe) y que el siguiente intento borra antes de empezar.
3. Un CSV con nombre final es siempre completo. Solo se exportan **días cerrados** (`target_date` < hoy UTC), de modo que un CSV nunca representa un día a medias.

## E. CSV

### E.1 Ruta, rango, orden

- Ruta: `data/raw/telemetry_YYYY-MM-DD.csv` (en Docker, `/data/raw/…` en un volumen con nombre `nightly-raw`; **no** se monta `data/raw` entero del host, que contiene los incidentes con emails de clientes).
- `.gitignore`: añadir `data/raw/telemetry_*.csv` y `data/raw/telemetry_*.csv.part`. Ningún CSV va al repo (la guía de `data/raw` ya lo pide).
- Rango en UTC `[00:00, 24:00)`: `"timestamp" >= :day_start AND "timestamp" < :day_end` (usa el índice de `timestamp`).
- Orden estable: `ORDER BY "timestamp", event_id`.
- **Solo lectura:** un `SELECT`; nada escribe en `telemetry_events` ni se toca `services/telemetry/analysis.py`.

### E.2 Columnas: completas o proyección

`user_id` y `session_id` son identificadores seudónimos. El plan (D9) limita los eventos en bruto con `userId` a **90 días**; `tags` ya está filtrado por la allowlist (sin PII; `supplier_key` es un HMAC).

| Opción | Pros | Contras |
|---|---|---|
| **(a) Todas las columnas** | Copia fiel; recuperación exacta | El CSV es una segunda copia del seudónimo que **sobrevive a los 90 días** de la base si nadie lo purga; contradice D9 |
| **(b) Proyección: `event_id, event_type, timestamp, service, schema_version, tags`** | Auditoría y recuperación de todo lo que usan el pipeline y el reporte técnico (que no leen `user_id` ni `session_id`); sin retención propia que gestionar | Una restauración dejaría `user_id`/`session_id` en `NULL` (las columnas ya admiten `NULL`) |

**Recomendación (M10): (b).** Es privacidad por diseño y no pierde nada que el pipeline use. Si quieres (a), la condición es decidir una retención de 90 días para los CSV (M10).

### E.2.1 Lista blanca de claves de `tags` (precisión del usuario sobre M10)

El plan define **90 claves distintas** de `tags` entre sus 52 eventos (`docs/telemetry/event-schemas.json`); hoy la API guarda 15 de esos eventos (`allowlists.py`), y el resto llegará según se vayan emitiendo. Revisadas una a una:

| Grupo | Claves | ¿Se exporta? |
|---|---|---|
| **Pseudónimo de proveedor** | `supplier_key` (HMAC-SHA256 del nombre; está en `inbound_order_created` y `kit_cost_variance_detected`) | **No.** El nombre del proveedor puede ser un autónomo con nombre propio; la clave solo protege mientras `TELEMETRY_SUPPLIER_KEY` no salga del servidor, y un CSV es una copia fuera de la base. Sigue en la base |
| **Pseudónimo de usuario** | `target_user_id` (`user_role_changed`, `user_deleted`), mismo seudónimo y retención de 90 días que `userId` (plan D9) | **No** |
| `assigned_to` | **No es una clave de `tags`.** Solo aparece como *nombre de campo* dentro del valor de `fields` (p. ej. `["quantity", "assigned_to"]`), que el plan define como «nombres de campo, nunca valores». El texto libre de `assigned_to`, `supplier` o un email no entra nunca en `tags` | Sí (como nombre de campo) |
| Identificadores internos de registro | `product_id`, `inbound_order_id`, `outbound_order_id`, `supplier_id`, `incident_id`, `analysis_id` | Sí: opacos, sin datos personales, y el pipeline necesita los de orden para deduplicar |
| Dimensiones y medidas de negocio | `office`, `programme_id`, `currency`, `quantity`, `unit_cost`, `reference_unit_cost`, `variance_pct`, `min_stock`, `stock_*`, … | Sí: son la entrada del pipeline |
| Técnicas (rutas, errores, duraciones, contadores) | `route_template`, `error_class`, `duration_ms`, `p95_ms`, `suppressed_count`, … | Sí |
| Resto (roles, motivos, resultados, booleanos) | `role`, `from_role`, `to_role`, `reason`, `outcome`, `account_found`, … | Sí: valores de un conjunto cerrado, sin identidad |

**Mecanismo: lista blanca, no lista negra.** El exportador lleva una constante con las **88 claves exportables, escritas una a una** (las 90 del plan menos `supplier_key` y `target_user_id`), y el campo `tags` del CSV contiene **solo** esas claves. Una clave que no esté en la lista no sale nunca, tampoco si aparece una nueva en la base. Para que la lista no envejezca en silencio, un test compara las claves del JSON del plan con dos conjuntos explícitos, `EXPORTABLE_TAG_KEYS` y `EXCLUDED_TAG_KEYS`: deben ser **disjuntos y su unión debe ser exactamente el conjunto del plan**. Si alguien añade una clave al plan, el test falla hasta que se decide a cuál de los dos conjuntos pertenece. Otro test comprueba que `supplier_key` y `target_user_id` no salen aunque la fila los lleve. La implementación llega en la parada 2.

Formato: UTF-8 sin BOM, `\n`, cabecera siempre; `timestamp` en ISO 8601 UTC (`2026-10-27T09:00:00+00:00`); UUID en texto; `tags` como JSON compacto con claves ordenadas (siempre empieza por `{`, así no hay riesgo de inyección de fórmulas en una hoja de cálculo).

### E.3 Día sin eventos y volumen

- **Día sin eventos:** el CSV existe con **solo la cabecera** (el fichero marca «día exportado, 0 filas»; sin él, el reintento volvería a consultar). INFO con `rows=0`.
- **Volumen:** unas 1 400 filas de negocio al día en el supuesto de 10 000 por semana (`PIPELINE_DESIGN.md` §4.6), más los técnicos. Se lee con cursor de servidor (`stream_results` + `yield_per`) y se escribe fila a fila: memoria constante.
- **El pipeline NO lee el CSV.** Su única fuente es `telemetry_events` por SQL (`repository.py`). Lo comprueba un test estático: nada bajo `data/pipelines/` ni `data/process/` referencia `data/raw/telemetry_` ni abre un `.csv` de telemetría.

### E.4 Retención de los CSV (parte de M10)

Hoy no hay borrado automático de nada en `data/raw`. **Recomendación:** no automatizarlo en DEV-53 (un borrado es destructivo y es decisión tuya); documentarlo en el README. Con la proyección (b) no hace falta para cumplir D9.

## F. Dónde va el código

| Pieza | Ruta | Contenido |
|---|---|---|
| Control de estado | `services/job_runner/` (biblioteca, como `services/telemetry/` y `services/reporting/`; con su `README.md`) | `states.py` (constantes y estados), `repository.py` (`create_job_run`, `update_job_run` por transición, `get_job_run`, `has_processing_lock`, `has_completed_for_date`, `sweep_stale`), `runner.py` (`run_job(engine, job_name, target_date, work)`: el ciclo de C.1, genérico), `redact.py`, `migrate.py` |
| Script | `scripts/nightly_export.py` | Capa fina, como `analyze.py` y `seed_incidents.py`: `TARGET_DATE`, base, logging, la función de trabajo (exportar CSV + lanzar el pipeline), códigos de salida. Ejecutable con `python scripts/nightly_export.py` |
| Migración | `services/job_runner/migrate.py` | B.1 |

- `run_job` recibe la función de trabajo: la máquina de estados se prueba con una función falsa, sin Prefect ni subprocesos.
- **Sin dependencias nuevas:** SQLAlchemy, `psycopg2` y Prefect ya están en `data/pipelines`; `nexova_shared` es solo librería estándar. `job_runner` usa `text()` con SQL portable (sin ORM, sin SQLModel).
- **Entorno de ejecución y de tests:** el de `data/pipelines` (su `.venv` o la imagen). Las pruebas unitarias corren sobre SQLite (admite índices únicos parciales) y la integración sobre un Postgres **local**.
- **No importan FastAPI ni la API.** Dos pruebas:
  1. *Dinámica:* `python -I -c "import job_runner, nightly_export; import sys; bad = {'fastapi','starlette','uvicorn','sqlmodel','app'} & {m.split('.')[0] for m in sys.modules}; assert not bad"` en un subproceso limpio.
  2. *Estática (AST):* ningún `import`/`from` de `fastapi`, `starlette`, `app` ni `app.main` en `scripts/nightly_export.py` y `services/job_runner/`.
- **Nada de planificador en la API:** un test busca `apscheduler`, `repeat_every`, `BackgroundScheduler`, `AsyncIOScheduler` y `schedule` en `services/api/app` (sin tocar `services/api`: el test vive en `services/job_runner/tests`). `lifespan=inventory_lifespan` es legítimo y no se marca.

## G. Disparador

En Windows no hay `crontab`. Tres opciones del encargo y una cuarta de reserva:

| | (1) Cron de Debian en un contenedor | (2) **supercronic** en un contenedor | (3) Deployment de Prefect en el worker | (4) Bucle propio en Python |
|---|---|---|---|---|
| Dependencias nuevas (**requieren tu autorización**) | Paquete apt `cron` | Un binario de GitHub (`aptible/supercronic`), versión fijada y **SHA-256 verificado en el `Dockerfile`** | Ninguna | Ninguna |
| `DATABASE_URL` y `TARGET_DATE` | **No llegan**: cron arranca los trabajos con un entorno mínimo; hay que volcarlas a un archivo en el arranque (secreto en disco) | Heredan el entorno del contenedor | `DATABASE_URL` **no está** en el worker (usa un block `Secret`): habría que leerlo del block | Heredan |
| Logs | Cron no escribe a stdout; hay que redirigir a `/proc/1/fd/1` | **stdout directo** (`docker compose logs`) | Logs de Prefect, aparte | stdout |
| Reinicios | Proceso `cron -f`, `restart: unless-stopped` | `restart: unless-stopped`, maneja `SIGTERM` | Depende del servidor + worker (perfil `pipelines`) | Propio: reinventar catch-up y señales |
| Otros | Corre como root; PID 1 sin reaper | Un solo proceso, sin demonio | Dos máquinas de estado (Prefect y `job_runs`) y acopla el nocturno al servidor de Prefect; obliga a tocar `serve.py` | Reimplementa un cron mal |

**Recomendación (M13): (2) supercronic**, con la versión y el checksum que fijaré en F1 **tras tu autorización** (no los invento aquí) y verificando (verificar) que por defecto no solapa ejecuciones. **Si no autorizas el binario**, la opción (4) es la única sin dependencias; (1) exige apt y arrastra el problema del entorno; (3) ata el nocturno al perfil `pipelines` y a un servidor de Prefect que no necesita.

Diseño del contenedor:

- Servicio `nightly-scheduler`, **perfil de Compose `nightly`** (apagado por defecto; `docker compose up` normal no lo arranca). Arrancarlo contra la demo es una decisión tuya aparte, en el momento.
- Imagen derivada de `nexova-pipeline:dev` + el binario (un `Dockerfile` nuevo, por ejemplo `data/Dockerfile.scheduler`, que no modifica el de la imagen del pipeline), `TZ=UTC`.
- **Entorno mínimo:** solo `DATABASE_URL: ${DATABASE_URL:?…}` (de la raíz `.env`, por interpolación de Compose), `TARGET_DATE` vacío y las variables de Prefect y de analítica desactivada. **Sin `env_file`:** el resto del `.env` (JWT, Resend, `TELEMETRY_SUPPLIER_KEY`) no entra en el contenedor.
- Código por bind mount de solo lectura, como el worker (`scripts/nightly_export.py` → `/scripts/`, `services/job_runner` → `/services/job_runner`, `PYTHONPATH` ampliado): no se reconstruye la imagen a cada cambio. Con la raíz del repo en `/`, el script resuelve `/data/raw` (volumen `nightly-raw`) y `/data/pipelines/pipeline.py` como en el worker.
- Prefect efímero dentro del contenedor, **sin** depender del perfil `pipelines`.
- Nada dentro del proceso de FastAPI: ni `APScheduler`, ni `repeat_every`, ni el `lifespan`.

**Expresión cron (UTC):**

```
0 2 * * *   python /scripts/nightly_export.py
```

02:00 UTC cada día = 03:00/04:00 en Valencia y 21:00/22:00 del día anterior en Miami. Deja **2 h de margen** tras el cierre del día UTC para eventos tardíos (reintentos del beacon del frontend y lotes pendientes) y queda 2–3 h antes del cron semanal actual, por si se mantuviera (M5).

## H. Observabilidad

Una sola línea por evento, a stdout, con marca de tiempo UTC, nivel, job, estado y fecha objetivo:

```
2026-11-16T02:00:00Z INFO job=nightly_export status=pending target_date=2026-11-15 run=3f2a… created
2026-11-16T02:00:00Z INFO job=nightly_export status=processing target_date=2026-11-15 run=3f2a… lock acquired
2026-11-16T02:00:01Z INFO job=nightly_export status=processing target_date=2026-11-15 run=3f2a… csv written rows=1423 file=telemetry_2026-11-15.csv
2026-11-16T02:00:01Z INFO job=nightly_export status=processing target_date=2026-11-15 run=3f2a… pipeline start week=2026-11-09
2026-11-16T02:00:34Z INFO job=nightly_export status=completed target_date=2026-11-15 run=3f2a… finished in 34.2s
2026-11-16T02:00:00Z INFO job=nightly_export status=skipped target_date=2026-11-15 reason=already_completed
2026-11-16T02:00:00Z INFO job=nightly_export status=locked  target_date=2026-11-15 reason=another_instance_processing
2026-11-16T02:00:12Z ERROR job=nightly_export status=failed target_date=2026-11-15 run=3f2a… PipelineFailed: pipeline exited with code 1 …
```

- **INFO:** inicio, fin, omisión, bloqueo y cada transición. **ERROR:** excepciones, con el mensaje ya redactado.
- `status` es el estado resultante (`pending`/`processing`/`completed`/`failed`) o, solo en el log, `skipped`/`locked` (C.4).
- **Sin credenciales:** el formateador pasa todo por `redact()`; se imprime como mucho la fuente y el host de la base (precedente de `pipeline.py`), nunca la URL, ni el entorno, ni `TELEMETRY_SUPPLIER_KEY`. Un test comprueba que un secreto inyectado en una excepción no aparece en el log ni en `error_message`, y que cada línea cumple el patrón.

## I. `TARGET_DATE`

| Entrada | Resultado |
|---|---|
| Sin definir o vacía (Compose pasa cadenas vacías) | Ayer UTC: `datetime.now(timezone.utc).date() - timedelta(days=1)` |
| Formato distinto de `YYYY-MM-DD` | Salida 2. Validación estricta por regex **antes** de `fromisoformat` (en Python 3.11+ `fromisoformat` acepta también `20261115` y `2026-W46-7`) |
| Fecha inexistente (`2026-02-30`) | Salida 2 |
| Hoy o futura | Salida 2: solo se exportan días **cerrados** (un CSV de un día a medias contradiría la idempotencia) |
| Más antigua que la retención | Salida 2: se calcula la semana de la fecha y se aplica `check_weeks` (la guarda de 84 días del pipeline), para no fallar después con el código 2 del pipeline |

**Comportamiento:** mensaje fijo a stderr y al log (ERROR; no repite el valor), salida **2** y **ninguna fila** en `job_runs`: una entrada inválida no es una ejecución.

## J. Plan de verificación (solo contra el Postgres efímero)

Montaje (F1): el recorrido de `docs/reporting/implementation-review.md` §3 (`nexova-pipeline-pg`, `postgres:17.6`, rol `nexova_app` sin superusuario, base `nexova_test`) + `docs/reporting/pipeline-seed-ephemeral.sql` (**datos ficticios**: eventos del 2026-10-20 al 2026-11-09, p. ej. 3 de negocio y 2 técnicos el 2026-10-21 y 2026-10-20) + `job_runner.migrate`. **Nunca la demo**; la contraseña del efímero solo en la terminal.

| # | Caso | Cómo | Esperado |
|---|---|---|---|
| 1 | Corrida correcta | `TARGET_DATE=2026-10-27` | Salida 0; fila `completed` con `target_date`, `started_at`, `finished_at`; `data/raw/telemetry_2026-10-27.csv` con las filas ficticias del día; `pipeline_runs` con una corrida `completed` de la semana 2026-10-26 |
| 2 | Segunda corrida del mismo día | Repetir el comando | Salida 0; **INFO omitido por duplicado**; sin fila nueva; sin CSV nuevo (misma marca de tiempo del archivo); `pipeline_runs` sin corrida nueva |
| 3 | Dos instancias a la vez | Dos procesos lanzados juntos con otra fecha (`2026-10-22`) | Una `completed`; la otra sale en silencio (INFO bloqueado); una sola fila y una sola corrida del pipeline |
| 4 | Fallo forzado | `DATABASE_URL` válida pero con el esquema `reporting` retirado en el efímero (o el pipeline con un `PYTHONPATH` roto) | Fila `failed` con `error_message` redactado; **ninguna** fila `processing`; salida 1; luego el reintento tras restaurar es `completed` (caso «failed no bloquea») |
| 5 | Zombi simulado | `UPDATE` directo en el efímero: una fila `processing` con `started_at` de hace 2 h; ejecutar | El barrido la pasa a `failed` con `Abandoned…`; la corrida nueva sigue y completa |
| 6 | Lock vivo no se barre | Fila `processing` de hace 5 min | Salida 0 «bloqueado»; la fila sigue `processing` |
| 7 | `TARGET_DATE` arbitraria | `2026-10-25` (domingo) y `2026-10-21` | Semana 2026-10-19 y fila con cada `target_date`; fecha de hoy, futura, `2026-13-01` y `20261015` → salida 2 sin fila |
| 8 | CSV | Primeras filas del CSV del caso 1 | Cabecera + filas ordenadas; sin `user_id`/`session_id`; solo datos ficticios del seed |
| 9 | Logs para la PR | Capturar el correcto (caso 1), el fallido (4) y el bloqueado (3) | Formato de H, sin credenciales |
| 10 | Aislamiento del contenedor | `docker compose --profile nightly config --quiet` y comprobación presente/ausente de variables en el contenedor | Solo `DATABASE_URL` (+ Prefect/analítica); sin JWT, Resend ni `TELEMETRY_SUPPLIER_KEY` |
| 11 | Disparador | Contenedor con el cron temporalmente adelantado en el **efímero** (el crontab real queda `0 2 * * *`) | Se ejecuta a la hora, el log sale por `docker compose logs`; reinicio del contenedor y la siguiente ejecución sigue |
| 12 | Idempotencia de la migración | `--dry-run`, aplicar, repetir | «Nada que migrar»; RLS activo y sin privilegios para `PUBLIC`/Supabase |

### Tests unitarios (SQLite, sin Docker ni Prefect)

- **Máquina de estados** (`runner`, con función falsa): `completed`; trabajo que lanza → `failed` con el mensaje; `KeyboardInterrupt`/`SystemExit` → `failed`; fallo al escribir `failed` (3 reintentos, la fila queda `processing`); lock perdido (fila barrida) → no se marca `completed`; omisión por duplicado (la función de trabajo **no** se llama); bloqueo (no se llama y se borra la `pending` propia); **carrera A termina / B reclama** simulada con un gancho entre el claim y la re-comprobación.
- **Repositorio:** `create`/`update` por transición (solo las legales; un `UPDATE` sobre un estado equivocado afecta a 0 filas), `has_processing_lock`, `has_completed_for_date`, índice único de `processing` y de `completed`, `sweep_stale` (45 y 5 min, con el reloj inyectado).
- **`redact()`:** URLs, el valor de `DATABASE_URL`, su contraseña, truncado a 500, clase sola para `SQLAlchemyError`.
- **`TARGET_DATE`:** la tabla de I (incluidos `20261015`, `2026-W46-7`, hoy, mañana, límite de retención exacto y un día más).
- **Semana a pasar:** domingo → su semana; martes → la última cerrada; fecha antigua → su semana; el límite de retención.
- **CSV:** límites `23:59:59.999999` dentro y `00:00:00` del día siguiente fuera; orden; cabecera sola en día vacío; sin `user_id`/`session_id`; `tags` compacto; fallo a medias → sin archivo final y sin `.part`; no sobrescribe.
- **Subproceso:** códigos 0/1/2/otro con un hijo falso; timeout mata el hijo **y su nieto**; entorno con lista blanca (el hijo no recibe `JWT_SECRET_KEY`, `RESEND_API_KEY`, `TELEMETRY_SUPPLIER_KEY`).
- **Arquitectura:** las pruebas de F (sin FastAPI, sin planificador en la API), el pipeline no lee el CSV, formato de las líneas de log.

### Tests de integración (Postgres **local**; se niegan con otro host, como `PIPELINE_TEST_DATABASE_URL`)

Variable propia `JOB_RUNNER_TEST_DATABASE_URL`: migración (idempotencia, RLS, `REVOKE`, esquema `ops`), **dos claims reales concurrentes con hilos y barrera → exactamente uno gana**, `ux_job_runs_one_completed_per_day`, y el `DELETE` del perdedor. Se omiten (con motivo) sin esa variable.

## K. Lo que NO se toca, y validación por subproyecto (AGENTS.md §4)

**No se toca:** `telemetry_events` (solo `SELECT`), `services/telemetry/analysis.py`, `services/api`, `uis/`, el `.env` de cualquier usuario, el esquema `reporting`, `packages/shared`, `data/process`, `services/reporting`. Del pipeline, **solo** lo decidido en A: `serve.py` (cron semanal) y su test y documentación, si aceptas M5.

| Subproyecto afectado en F1 | Validación |
|---|---|
| `services/job_runner/` + `scripts/nightly_export.py` (fila nueva en la tabla de §4) | Desde la raíz, con el venv de `data/pipelines`: `data\pipelines\.venv\Scripts\python -m unittest discover -s services/job_runner/tests -t services` (Windows) o `data/pipelines/.venv/bin/python …` (Linux/macOS). **Nota (parada 1):** `-t services`, no `-t services/job_runner`, para que `job_runner` sea importable. Con `JOB_RUNNER_TEST_DATABASE_URL` en un Postgres local corre también la integración |
| `data/pipelines/` (si M5 = quitar el cron) | La fila existente: `python -m unittest discover -s data/pipelines/tests -t data/pipelines` en el venv de `data/pipelines` |
| Docker (`docker-compose.yml`, nuevo `Dockerfile` del programador) | La fila «Docker»: `docker compose config --quiet` (nunca sin `--quiet`) + `docker compose up -d --build` + las comprobaciones del bloque, y el caso 10 de J. Con Docker Desktop en marcha |
| `.gitignore` | `git check-ignore -v data/raw/telemetry_2026-10-27.csv` |
| `docs/telemetry/` | `python scripts/validate_event_schemas.py` solo si se tocan el plan o los esquemas (no se tocan) |
| `services/api/` | Sin cambios; no hay que ejecutar su suite (se confirma con `git diff --stat`) |

Se añade a `AGENTS.md` §4 una fila para el job nocturno, y una entrada breve en `scripts/README.md` y `services/README.md`.

## L. Plan de F1, con paradas

1. **Parada 1 — migración y `job_runner`.** `services/job_runner/` (estados, repositorio, `run_job`, `redact`, `migrate`), sus tests unitarios y de integración (efímero), `.gitignore`. Verificación del caso 12 y de las carreras de C. *Para y espero tu OK.*
2. **Parada 2 — script y CSV.** `scripts/nightly_export.py` (`TARGET_DATE`, base, logging, CSV atómico, subproceso del pipeline) y sus tests; casos 1 a 9 de J contra el efímero con el seed ficticio. *Para.*
3. **Parada 3 — disparador.** `docker-compose.yml` (perfil `nightly`), `Dockerfile` del programador con el binario fijado, crontab, y, si aceptas M5, `serve.py`. Casos 10 y 11. Contra la demo, nada. *Para.*
4. **Parada 4 — cierre.** Documentación (`README.md` de `job_runner`, §4 de `AGENTS.md`, guía de revisión `docs/telemetry/nightly-export-review.md`), `memory-bank-sync`, **un solo commit** y el borrador del cuerpo de la PR (método elegido y su justificación, expresión cron, logs correcto/fallido/bloqueado, primeras filas del CSV ficticio). Sin push ni PR hasta tu OK.

- **Mensaje de commit.** El enunciado no fija uno. Propongo Conventional Commits, en inglés como los anteriores, sin pie de atribución: `feat: add nightly telemetry export job with job_runs state machine` (cuerpo: el porqué: disparador único programado, lock por estado, idempotencia por día).
- **PR:** hacia `main`, con la etiqueta **`cronjob`** antes de pasarla a revisión (si la etiqueta no existe en el repo, la creo solo con tu confirmación). Merge con «Create a merge commit».

## Lo no verificado (se comprueba en F1)

- Versión y SHA-256 de supercronic y su comportamiento por defecto con ejecuciones solapadas.
- Si `serve()` retira de Prefect el deployment `weekly` al quitarle el cron.
- Matar el árbol de procesos del hijo en Windows (`taskkill /T`); en Linux, `killpg`.
- Que SQLite acepte el SQL portable con el mismo comportamiento de los índices únicos parciales que PostgreSQL (se contrasta con la integración).
- Tiempo real del pipeline con eventos nocturnos en el efímero (el diseño mide 21 s con 10 000 eventos).

## M. Decisiones pendientes

Cada una con mi recomendación en primer lugar. Responde con «M1 sí, M5 mantener…» o «todas las recomendadas».

| # | Decisión | Recomendación | Alternativa |
|---|---|---|---|
| **M1** | Qué lanza el subproceso | `sys.executable data/pipelines/pipeline.py --week-start <lunes>`, mismo intérprete (entorno de `data/pipelines`); el pipeline no se toca | Un entry point nuevo `--no-prefect` (no existe y no hace falta) |
| **M2** | Qué semana pasa cada noche | `min(lunes de target_date, última cerrada)`, siempre explícita | Solo lanzar el pipeline los lunes (contradice «cada noche») |
| **M3** | Salida y errores | Mapeo 0/1/2/otro/timeout de A.3; `error_message` con texto fijo y `redact()`, sin salida del hijo; entorno del hijo con lista blanca; **timeout 20 min** con muerte del árbol | Guardar la salida del hijo (riesgo de fugas) |
| **M4** | `trigger = 'manual'` de las corridas nocturnas | Dejarlo y documentarlo (no tocar el pipeline por esto) | Añadir `--trigger` a `pipeline.py` |
| **M5** | Cron semanal de Prefect | **Quitar el cron de `weekly`** y dejar solo `manual`; el nocturno es el único disparador programado. **Con la precisión del usuario:** trazar el cambio (DEV-53, fecha y motivo) en `PIPELINE_DESIGN.md` §4.5 y en el README del pipeline, y ajustar el test de `serve.py` sin debilitarlo | Mantenerlo (cero cambios, dos disparadores) |
| **M6** | Dónde vive `job_runs` | Esquema nuevo `ops`, migración propia `job_runner.migrate` con `--dry-run`/`--allow-demo`, RLS y `REVOKE` como `reporting` | Dentro de `reporting` |
| **M7** | Fila por intento o por día | **Por intento**, índice `(job_name, target_date)` + único parcial de `completed` por día | Una por día (se pierde el historial de fallos) |
| **M8** | Lock y registro de omisión/bloqueo | `UNIQUE (job_name) WHERE status = 'processing'` (el estado es el lock); re-comprobación de `completed` tras el claim; omisión y bloqueo **solo en el log** (`status=skipped`/`locked`) y el perdedor borra su `pending` | Fila `failed`/`completed` de cancelación (ensucia el historial) o un quinto estado |
| **M9** | Zombis y fallo al escribir `failed` | Barrido al inicio: `processing` > **45 min** y `pending` > 5 min → `failed` `Abandoned`; `SIGTERM` → `failed`; 3 reintentos al escribir `failed` y garantía eventual | Heartbeat |
| **M10** | Columnas del CSV y su retención | **Proyección sin `user_id`/`session_id`** y `tags` filtrado por una **lista blanca explícita de 88 claves** (sin `supplier_key` ni `target_user_id`; E.2.1); sin purga automática (documentar) | Todas las columnas + retención de 90 días de los CSV |
| **M11** | Formato y atomicidad del CSV | `.part` + `os.replace`, sin sobrescribir, solo días cerrados, día vacío = cabecera, UTF-8, orden `timestamp, event_id`, streaming | Escribir directo (deja archivos parciales) |
| **M12** | Código | `services/job_runner/` (biblioteca) + `scripts/nightly_export.py` (capa fina); sin dependencias nuevas; tests en el venv de `data/pipelines` | Todo dentro de `scripts/` |
| **M13** | Disparador | **supercronic** en un contenedor `nightly-scheduler` con checksum fijado **AUTORIZADO** con condiciones: versión exacta, SHA-256 verificado en el `Dockerfile` (el build falla si no coincide), descarga solo en el build, usuario no root, versión y checksum documentados aquí y en la PR | Bucle propio en Python (sin dependencias) |
| **M14** | Cron y perfil | `0 2 * * *` UTC; perfil de Compose `nightly`, apagado por defecto; solo `DATABASE_URL` en el entorno del contenedor; contra la demo, decisión tuya aparte | Otra hora |
| **M15** | Observabilidad | Formato de H en stdout; INFO/ERROR; `redact()` | — |
| **M16** | `TARGET_DATE` | Validación de I: regex estricta, solo días cerrados, límite de retención, salida 2 sin fila | Aceptar el día en curso |
| **M17** | Ubicación del análisis y de la guía | `docs/telemetry/nightly-export-analysis.md` (esta carpeta ya agrupa los análisis de telemetría) y `nightly-export-review.md` en F1 | `docs/ops/` |
| **M18** | Commit y PR | Un commit `feat: add nightly telemetry export job with job_runs state machine`, sin pie de atribución; PR con la etiqueta `cronjob`; merge con «Create a merge commit» | — |

## N. Parada 3: el disparador, tal como quedó (2026-11-16)

**supercronic fijado (M13, autorizado con condiciones):**

| | |
|---|---|
| Versión | `v0.2.51` (publicada el 2026-10-21; `github.com/aptible/supercronic/releases/tag/v0.2.51`) |
| SHA-256 `supercronic-linux-amd64` | `cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123` |
| SHA-256 `supercronic-linux-arm64` | `4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94` |
| Origen del checksum | El `digest` que GitHub publica para cada asset **y** el SHA-256 que calculé al descargar el binario en un contenedor desechable: coinciden en las dos arquitecturas |
| Dónde se verifica | `data/Dockerfile`, etapa `supercronic`: `sha256sum -c` tras la descarga; si no coincide, **el build falla** (probado: `/supercronic: FAILED`, salida 1 y ninguna imagen creada). La descarga solo ocurre ahí, en el build |

**Piezas:**

- `data/Dockerfile` pasa a tres etapas que comparten una `base` (Python, dependencias con hashes, `nexova_shared` y el código): `scheduler` (base + supercronic + el script + `job_runner`, usuario no root `nexova`, uid 10001) y `pipeline` (la última, por tanto la de por defecto: el servidor de Prefect y el worker se construyen igual que antes; comprobado con un `docker build` sin `--target`).
- La imagen copia **solo** `scripts/nightly_export.py` y los `.py` de `services/job_runner` (sin tests ni README), por contextos adicionales de build (`scripts`, `services`). No lleva `docs/` ni lee nada de `docs/` en ejecución: la lista blanca de tags está en el código; el test que la compara con `docs/telemetry/event-schemas.json` sigue en la suite y no está en la imagen.
- `data/nightly.crontab`: `CRON_TZ=UTC` y `0 2 * * * python /scripts/nightly_export.py`. supercronic lo valida (`-test`) y confirma «processes will be spawned using TZ: UTC».
- Servicio `nightly-scheduler` en `docker-compose.yml`, perfil `nightly`: sin puertos, `restart: unless-stopped`, `init: true` (Prefect lanza su servidor efímero como hijo), `stop_grace_period: 30s`. Entorno mínimo (M14): solo `DATABASE_URL` (y `TZ`, y las dos variables que desactivan la analítica de Prefect); sin `env_file`, sin `TARGET_DATE`. Volumen `./data/raw:/data/raw` para que los CSV queden en el host.
- `docker compose config --quiet` pasa; sin perfil, `docker compose config --services` solo lista `api` y `ui`, y `docker compose --dry-run up -d` no incluye el scheduler. Con `--profile nightly` aparece.

**Decisión nueva (M19): `-overlapping`.** El comando de la imagen es `supercronic -overlapping …`. Sin él, supercronic **no** lanzaría el segundo disparo mientras el primero siga en marcha, y esa omisión sería un segundo mecanismo de exclusión, que el ticket prohíbe («el distributed lock es el estado `processing`, no un segundo mecanismo»). Con `-overlapping` el segundo disparo arranca y es el lock de la base el que lo aborta en silencio, como describe el ticket. Es seguro: la base garantiza una sola instancia en `processing`. supercronic registra además un aviso («overlapping jobs: job is still running since …»).

**Aviso sobre el montaje de `data/raw`:** `./data/raw` también contiene `data/raw/incidents/` (datos reales con emails, ignorados por git), que queda visible dentro del contenedor aunque el job solo escribe sus CSV y su caché. Se montó así por indicación del usuario; la alternativa, una subcarpeta propia, obligaría a cambiar la ruta `data/raw/telemetry_YYYY-MM-DD.csv` que fija el enunciado. En Linux, el uid 10001 del contenedor debe poder escribir en `data/raw` del host.

**`SIGTERM`:** `docker stop` llega a supercronic, que responde «waiting for jobs to finish» y sale con 0. Con `stop_grace_period: 30s` una corrida normal (~20 s) termina; si no, Docker envía `SIGKILL` y la fila queda `processing` hasta el barrido de 45 min (C.3).

**Cómo se probó (solo contra el efímero; el override no se versiona):** `docker run` de la imagen `nexova-nightly-scheduler:dev` (con su `CMD` real) con `DATABASE_URL` del efímero, `TARGET_DATE` fija y un crontab de prueba montado encima, `* * * * *`. Para que una corrida durase más que un minuto, de forma realista, un escritor retuvo `LOCK TABLE reporting.weekly_office_program_performance` unos 135 s y la carga del pipeline esperó. Resultado, en los logs de supercronic: 18:37:00 disparo 0 → `completed` (79,8 s); 18:38:00 disparo 1, con el 0 aún en marcha → aviso de solapamiento y `status=locked`; 18:39:00 disparo 2 → `status=skipped … already_completed`. Una fila `completed`, un CSV y una corrida del pipeline para esa fecha.

## O. Criterios de «Qué evaluaremos» y su cumplimiento

| # | Criterio del enunciado | Dónde se cumple | Prueba |
|---|---|---|---|
| 1 | El script es un proceso independiente: no importa ni ejecuta FastAPI ni el `main` de la app | `scripts/nightly_export.py` y `services/job_runner/` sin ningún import de `fastapi`, `starlette`, `uvicorn`, `sqlmodel` ni `app`; servicio de Compose propio, sin puertos | `test_architecture.py`: importar el paquete y el script en un proceso limpio (`-I`) no carga `fastapi`, `starlette`, `uvicorn`, `sqlmodel`, `app` ni `app.main` (tampoco Prefect), análisis AST, y la API sin `apscheduler`/`repeat_every`; evidencias `log_a.txt` (corre en su propia imagen) |
| 2 | Máquina de estados `pending → processing → completed \| failed` y filas con el estado real y `target_date` | `services/job_runner/runner.py`, `repository.py` (transiciones *compare-and-set*), DDL en `migrate.py` | `cases.py` (SQLite y PostgreSQL), `test_nightly_export_main.py`; estado final de `ops.job_runs` (8 filas) en el informe de la parada 2 |
| 3 | `processing` como lock distribuido, sin mecanismo aparte; dos instancias a la vez | Índice único parcial `ux_job_runs_one_processing` (`UNIQUE (job_name) WHERE status = 'processing'`): es la propia columna `status` con una restricción | `test_two_simultaneous_claims_exactly_one_wins_the_lock` (25 rondas, dos conexiones) y `test_two_simultaneous_instances_one_completes_and_the_other_aborts`; caso c en procesos reales (`log_c_1.txt`, `log_c_2.txt`); disparo `locked` de supercronic (`log_scheduler.txt`) |
| 4 | Idempotente por `target_date`: dos ejecuciones el mismo día = una, sin duplicar CSV ni pipeline | `has_completed_for_date`, re-comprobación tras el claim, `ux_job_runs_one_completed_per_day`, CSV que no se sobrescribe | Caso b (mismo hash y `mtime`, sin corrida nueva), disparo `skipped`; tests de omisión y de la carrera «completa justo antes del claim» |
| 5 | Ningún registro queda `processing` tras un fallo | `run_job`: `except BaseException` → `failed`; `SIGTERM` convertido en excepción; barrido a los 45 min para lo que ningún `finally` cubre | Casos d y e; `test_no_row_is_left_processing_after_any_failure`, `KeyboardInterrupt`/`SystemExit`, `test_sigterm_leaves_the_row_failed`, fallo al escribir `failed` con reintentos y barrido |
| 6 | CSV en `data/raw/` con nombre correcto y datos de `telemetry_events`; el pipeline lee de la BD | `export_csv` → `data/raw/telemetry_YYYY-MM-DD.csv` (UTC, `[00:00, 24:00)`, `.part` + `os.replace`); el pipeline lee `telemetry_events` por SQL | Caso a (4 filas = `COUNT`), caso f (cabecera sola), tests de límites, orden y atomicidad, `test_the_pipeline_never_reads_the_csv_export` |
| 7 | `job_runs` y `pipeline_runs` coexisten sin duplicar responsabilidades | Esquemas distintos (`ops` y `reporting`), sin FK ni columnas compartidas; una registra la orquestación y la otra las fases del ETL | Estado final de ambas tablas tras los casos (8 filas de `job_runs`, corridas de `pipeline_runs` por semana); análisis B.1 |
| 8 | Logs con timestamp, nombre del job y estado en cada evento relevante | `services/job_runner/logs.py`: `timestamp LEVEL job=… status=… target_date=…`, siempre redactado | `LINE` (regex) aplicada a cada línea en `cases.py` y `test_nightly_export_main.py`; logs de las evidencias |
| 9 | Disparador configurado y expresión cron documentada | `data/nightly.crontab` (`CRON_TZ=UTC`, `0 2 * * *`), `nightly-scheduler` en `docker-compose.yml` (perfil `nightly`), supercronic v0.2.51 con SHA-256 verificado | `supercronic -test`; disparos reales cada minuto; build con checksum incorrecto que falla; cuerpo de la PR |
| 10 | `TARGET_DATE` permite fechas arbitrarias sin cambiar código | `resolve_target_date` (regex estricta, días cerrados, retención) | `test_nightly_export_target_date.py`; casos a (10-27), b, c, d, e, f (fechas distintas) y g (inválidas, salida 2 sin fila) |

Guía de revisión (cómo reproducir cada caso, lo no verificado y la limpieza): [`nightly-export-review.md`](./nightly-export-review.md).
