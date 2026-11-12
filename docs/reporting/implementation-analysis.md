# Pipeline de desempeño de negocio: análisis de la implementación (F0)

Documento de trabajo del ticket «Data Pipelines — Parte 2, implementación del pipeline de desempeño de negocio». **F0: análisis y decisiones; no hay código.** Prepara las decisiones de F1; el diseño aprobado sigue siendo [`data/pipelines/PIPELINE_DESIGN.md`](../../data/pipelines/PIPELINE_DESIGN.md) hasta que el usuario decida aquí qué cambia.

> **Decidido por el usuario (2026-11-10): D1–D16 tal como se recomiendan, con cuatro matices** que ya están recogidos en C1, D2, D3, D5, D11, D12 y en el plan de F1 (§5):
>
> - **C1/D1:** `python-dateutil 4.0.0` es transitiva de Pandas, no una versión que fijáramos nosotros. Aun así, **D1-A** (Prefect en un entorno propio de `data/pipelines/`), **por arquitectura**: la API sin Prefect, el flow fuera de su `--reload` y coherencia con D8 (diseño).
> - **D5:** la guarda `--allow-demo` protege **solo la migración** del esquema `reporting` (DDL). La corrida del ETL solo escribe en `reporting`, es idempotente y recalculable: **no se bloquea**. Si el esquema no existe, el script termina con un mensaje que dice qué migración ejecutar (salida ≠ 0, sin traza).
> - **D2-B:** la PR y `PIPELINE_DESIGN.md` explican en dos líneas por qué la API importa `request_manual_run` y no el objeto flow. Sin la URL de Prefect, o con el servidor caído → 503 `pipeline_unavailable`.
> - **D3:** el perfil `pipelines` solo arranca con `--profile pipelines`; contra la demo, solo con la confirmación del usuario **en el momento**.

- **Rama:** `feature/business-pipeline`, desde `main` en `9d8b0df` (PR #33; `origin/main` en el mismo commit).
- **Fuentes:** el BRIEFING [`docs/proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md`](../proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md) (manda en KPI, tabla y contrato del endpoint), `PIPELINE_DESIGN.md` y las decisiones D1–D14 de [`pipeline-analysis.md`](./pipeline-analysis.md). Para no confundirlas con las de este documento, se citan como **«D8 (diseño)»**.
- **Cómo leerlo:** **Verificado** es lo comprobado en el código, en la documentación o ejecutado. **Propuesta** es diseño nuestro.

**Qué se ejecutó en F0, además de leer:**

- **Resolución de Prefect en copias temporales** (fuera del repo, en el directorio temporal de la sesión): `uv lock` sobre una copia de `services/api/pyproject.toml` + `uv.lock` con `prefect>=3` añadido; `uv pip compile` de Prefect solo y de un entorno «solo pipeline», para Python 3.14 y Linux (`x86_64-manylinux_2_28`); `uv export` de la copia; instalación con `--target` en carpetas temporales para medir tamaños y leer el código de Prefect 3.9.2; los metadatos de `prefect 3.9.2` en PyPI.
- **Nada en el repo:** ni `uv add`, ni `uv lock`, ni `uv sync`, ni el venv de `services/api` tocados. Ni Supabase, ni Docker, ni ningún Postgres. No se ha ejecutado ningún flow.

---

## 1. Estado verificado

### 1.1 Qué del diseño se puede implementar tal cual

| Pieza del diseño | ¿Tal cual? | Nota |
|---|---|---|
| KPI, grano, centinela `_unassigned`, dedup por orden (§2.2, §2.5) | **Sí** | La transformación es Python puro (`decimal`, `datetime`): no necesita Pandas ni Prefect |
| Extracción (§2.3) y conciliación de solo lectura | **Sí** | SQL de texto con SQLAlchemy + `psycopg2`, como el resto del repo |
| DDL de `reporting` (§2.7, §3.3) y la carga de §3.1 | **Sí** | Con la migración explícita (patrón de `telemetry/migrate.py`), ver D11 |
| Log `reporting.pipeline_runs` | **Sí** | Cubre de sobra los ≥ 5 campos de metadata (inicio, fin, registros, estado, errores) |
| Flow y 8 tasks (§4.1) | **Sí, con otra ubicación** | El enunciado los quiere **en** `data/pipelines/pipeline.py` (C2), no en `business_performance/flows.py` y `tasks.py` |
| Retries de §4.1 | **Sí** | Falta el comentario que justifica cada número (C9) |
| Pseudocódigo con `try/except` global (§4.1) | **No tal cual** | El enunciado pide `return_state=True` para el fallo manejado (C8) |
| Caché | **No existe en el diseño** | El enunciado la pide (C7) |
| Paso opcional | **No existe en el diseño** | El enunciado lo pide (C6) |
| Block `Secret` como única credencial (§4.3) | **No tal cual** | `python data/pipelines/pipeline.py` corre sin servidor (C5) |
| Servidor y worker en un perfil de Compose; API sin Prefect, disparo por REST (D8 (diseño), §4.4) | **Compatible** con D2-B de este documento | El enunciado obliga a importar algo de `data/pipelines/` (C3) |
| Prefect como dependencia | **Choque de versiones** si entra en `services/api` (C1) | Sin choque en un entorno propio de `data/pipelines/` |

### 1.2 Prefect 3, resuelto sin instalar en el repo

| Pregunta | Resultado (verificado) |
|---|---|
| Versión que resuelve `uv` | **`prefect 3.9.2`** (la última 3.x en PyPI hoy) |
| ¿Soporta Python 3.14? | **Sí:** `requires_python = ">=3.11,<3.16"`. Todas las dependencias tienen wheel para `cp314`/`py3` en `manylinux_2_28` (la imagen es `python:3.14.6-slim`, Debian con glibc 2.41) |
| Dependencias | 87 paquetes más sobre los 33 de la API (120 en total en la copia; 126 en `uv.lock` contando los de Windows y los de `dev`). Entre otros: `aiosqlite`, `alembic`, `asyncpg`, `apprise`, `docker`, `httpx`, `pydocket`, `redis`, `cloudpickle`, `whenever`, `rich`, `typer`, `opentelemetry-api` |
| Límites de Prefect sobre lo que fija la API | `fastapi>=0.139.0,<0.151` · `starlette>=1.0.1` · `pydantic>=2.10.1,<3` (sin 2.11.0–2.11.4) · `sqlalchemy[asyncio]>=2.0,<3` · `uvicorn!=0.29.0,>=0.14.0` · `anyio>=4.4.0,<5` · `click>=8.0,<9` · **`python-dateutil>=2.8.2,<3.0.0`** |
| ¿Qué versión fijada de la API cambiaría? | **Solo una: `python-dateutil` `4.0.0` → `2.9.0.post0`** (transitiva de Pandas, D2 del reporte técnico). `fastapi 0.141.1`, `starlette 1.7.0`, `pydantic 2.13.5`, `sqlalchemy 2.1.5`, `uvicorn 0.53.0`, `anyio 4.15.1`, `click 8.5.0`, `pandas 3.1.1` y `numpy` **se quedan igual** (`uv export` de la copia, comparado con `requirements.txt`) |
| Tamaño en la imagen de la API | `site-packages` de **163 MB → 265 MB (+≈ 102 MB** sin comprimir; de ellos, `prefect` 26 MB, con dos UIs de 6 y 11 MB; `asyncpg` 14 MB; `apprise` 8 MB) |
| Tamaño de un entorno solo del pipeline | `prefect` + `sqlalchemy==2.1.5` + `psycopg2-binary` (medido en F0; el lock final tiene 2.1.8, D1): **≈ 161 MB** de `site-packages` (104 paquetes), sin Pandas. Con `python-dateutil 2.9.0.post0`, sin choque: no hay Pandas |

**Modo efímero de Prefect 3.9.2** (leído en el código del paquete):

- **Sí ejecuta un flow sin servidor.** Prefect trae un perfil por defecto `active = "ephemeral"` con `PREFECT_SERVER_EPHEMERAL_ENABLED = "true"` (`prefect/settings/profiles.toml`). Sin `PREFECT_API_URL`, el cliente **arranca un servidor en un subproceso** (`SubprocessASGIServer`, un puerto libre del rango 8000–8999) y lo usa durante la corrida (`client/orchestration/__init__.py:248-256`). Si el perfil lo desactiva, falla con «No Prefect API URL provided».
- **Estado (flow runs, task runs, logs, blocks):** en **`~/.prefect/prefect.db`** (SQLite, `sqlite+aiosqlite:///{PREFECT_HOME}/prefect.db`, `settings/models/_defaults.py:76-77`). `PREFECT_HOME` por defecto es `~/.prefect` (`settings/constants.py:6`).
- **Resultados en caché:** en **`~/.prefect/storage`** (`PREFECT_LOCAL_STORAGE_PATH`, `_defaults.py:52-57`), serializados con `cloudpickle`. La caché sobrevive entre procesos mientras exista esa carpeta.
- **Blocks:** también en `prefect.db`. Sus datos se cifran con una clave Fernet que, sin `PREFECT_SERVER_ENCRYPTION_KEY`, **se guarda en la misma base** (`server/utilities/encryption.py:16-34`): un `Secret` en el modo efímero es legible por quien lea `~/.prefect/prefect.db`.
- **¿Ficheros en el repo?** Por defecto, **no**: todo va al home. Solo irían al repo si se apuntan `PREFECT_HOME` o `PREFECT_LOCAL_STORAGE_PATH` allí (D6).
- **REST para crear un flow run** (para D2): existen `GET /api/deployments/name/{flow_name}/{deployment_name}` y `POST /api/deployments/{id}/create_flow_run` (`server/api/deployments.py:478, 864`).
- **Tests:** existe `prefect.testing.utilities.prefect_test_harness` (`testing/utilities.py:121`): un servidor efímero con SQLite temporal para la suite.
- **Sin verificar:** el tiempo de arranque del servidor efímero en este Windows y en el contenedor (Prefect espera hasta 20 s); `flow.serve` con el cron `Europe/Madrid`; el límite de concurrencia del deployment.

---

## 2. Conflictos

### C1. Versión de lock: `python-dateutil` (resuelto con D1-A)

> **Matiz del usuario:** `python-dateutil 4.0.0` está en el lock de la API como **transitiva de Pandas**; no es una versión que fijáramos nosotros en `pyproject.toml`. El choque no obligaba por sí solo a sacar Prefect de la API: **D1-A se elige por arquitectura** (la API sin Prefect, el flow fuera de su `--reload`, coherencia con D8 (diseño)), y de paso el lock de la API queda intacto.

- **Autorización del ticket:** «Si hay choques de versiones con la API […] para y dímelo antes de proponer cambios en las versiones fijadas».
- **`services/api/requirements.txt`:** `python-dateutil==4.0.0`, transitiva de Pandas (`docs/telemetry/report-analysis.md:148`).
- **`prefect 3.9.2`:** `python-dateutil<3.0.0,>=2.8.2` (metadatos de PyPI). No hay ninguna 3.x de Prefect que acepte `dateutil` 4.

**Hechos:** con Prefect en el mismo `uv.lock` que la API, `uv lock` resuelve sin error **bajando `python-dateutil` a `2.9.0.post0`** (Pandas acepta `>=2.8.2`). Ningún archivo propio del monorepo importa `dateutil` (solo Pandas por dentro). **No verificado:** que la suite del reporte técnico pase con `dateutil 2.9`. Con Prefect en un entorno propio de `data/pipelines/` (sin Pandas) **no hay choque**. Ver D1.

### C2. Ubicación: el flow y ≥ 3 tasks **en** `data/pipelines/pipeline.py`

- **Enunciado, Fase 4:** «`data/pipelines/pipeline.py` ejecutable»; evaluación: «`pipeline.py` con ≥ 1 flow y ≥ 3 tasks».
- **D7 (diseño), `PIPELINE_DESIGN.md:24` y `:458`:** «Código previsto en `data/pipelines/business_performance/` (`flows.py`, `tasks.py`, `migrate.py`, `serve.py`)».
- **Enunciado, carpetas:** `data/process/` para transformaciones reutilizables.
- **`data/pipelines/README.md:5`:** cada subcarpeta o archivo, un pipeline.

**Hechos:** el flow y sus tasks tienen que estar definidos en `pipeline.py`, no importados de `flows.py`/`tasks.py`. El resto (migración, configuración, disparo, `serve`) puede seguir en `business_performance/`. **Importaciones:** si `pipeline.py` se ejecuta como script, `sys.path[0]` es `data/pipelines/`, así que `business_performance` se importa solo; `data/process/` y `packages/shared` no. Precedente: `incident_analyzer` añade `packages/shared` a `sys.path` si `nexova_shared` no está instalado (`packages/shared/README.md`, «Instalación»). **Riesgo de nombres:** un paquete de primer nivel `data` chocaría con `services/api/data/` (TinyDB), que está en el directorio de trabajo de la API (`/app/api`); `process` o `pipeline` son demasiado genéricos. Ver D4.

### C3. Disparo manual: importar desde `data/pipelines/` frente a D8 (diseño)

- **Enunciado, Fase 5:** los 3 endpoints «importando flows o funciones desde `data/pipelines/`, sin duplicar la lógica»; evaluación: «el de disparo importando desde `data/pipelines/`».
- **`PIPELINE_DESIGN.md:526`:** «**La API no ejecuta el flow ni depende de Prefect:** crea el flow run por la API REST del servidor con `urllib`». **`:533`:** `services/reporting/` «no importa `prefect`, `pandas` ni `business_performance`».
- **Compose:** la API corre con `--reload` (`docker-compose.yml:32`) y `--workers 1` (`services/api/SPECS.md:831`).

**Hechos:** «sin importar» (diseño) y «importando» (enunciado) se contradicen en la letra, pero no en el fondo: lo que el diseño evita es **Prefect y el ETL dentro del proceso de la API**. Una función de `data/pipelines/` que solo hace la petición REST (librería estándar) cumple las dos cosas. Comparación de las opciones del ticket:

| | (A) La API importa el flow y lo ejecuta en segundo plano | (B) La API importa una función de `data/pipelines/` que solo crea un flow run en un servidor de Prefect | (C) La API importa una función que lanza `python pipeline.py` en un subproceso |
|---|---|---|---|
| Prefect en la imagen de la API | **Sí** (+≈ 102 MB y C1) | **No**, si la función usa `urllib`; **sí**, si usa el cliente de Prefect o `run_deployment` (y entonces C1) | No en la API, pero el subproceso necesita un intérprete **con** Prefect dentro del contenedor (otro venv en la imagen) |
| `data/` en la imagen | Todo `data/pipelines/` y `data/process/` | Solo el módulo de disparo | Todo |
| `--reload` | Un cambio de código **mata la corrida** a mitad (el hilo muere con el proceso) | Sin efecto: la corrida está en el worker | Depende de cómo se lance; el hijo puede quedar huérfano o morir con el grupo |
| `--workers 1` | La corrida comparte el único proceso: el servidor efímero de Prefect (subproceso) y la extracción compiten con las peticiones | Sin efecto | Sin efecto en el proceso, sí en CPU/memoria del contenedor |
| Recarga a mitad de corrida | Fila `running` sin cerrar → se cierra como `Abandoned` a los 30 min; el `POST` da 409 hasta entonces | No pasa | Como (A) si el hijo muere |
| 202 asíncrono | Sí, con `BackgroundTasks` o un hilo, pero sin `prefect_flow_run_id` hasta que el flow arranca | **Sí**, con el id real del flow run | Sí, sin id de Prefect |
| Servidor de Prefect | Efímero dentro del contenedor de la API (SQLite en `/root/.prefect`, se pierde al recrear) | **Hace falta** el servidor y el worker (C10) | Efímero, como (A) |

Ver D2.

### C4. Dónde se declara Prefect y cómo se instala

- **Enunciado:** `uv add "prefect>=3"`.
- **`AGENTS.md:46`:** en `services/api`, `uv run --no-sync …`, «No usar `uv sync`» (una sincronización desinstaló los paquetes del monorepo del venv). `uv add` sincroniza por defecto.
- **`AGENTS.md:25`:** dependencias nuevas, solo con autorización (dada, sujeta a §1.2).
- **`services/api/tests/test_requirements_lock.py`:** `requirements.txt` debe seguir a `uv.lock`.

**Hechos:** `uv add` no se puede usar tal cual en `services/api` (sincroniza) y, con C1, cambiaría un pin. En un `pyproject.toml` propio de `data/pipelines/`, `uv add` sí sería inocuo, pero el repo fija rangos acotados a mano (`pyproject.toml` de la API, comentario de cabecera), y `prefect>=3` sin techo dejaría entrar una 4.x. Ver D1.

### C5. Ejecución por script sin servidor: credencial y base por defecto

- **`PIPELINE_DESIGN.md:513`:** «La credencial **solo** vive en el block […] Las tasks la cargan con `Secret.load(…)`».
- **Enunciado, Fase 4:** `python data/pipelines/pipeline.py` corre el ETL completo sin errores.
- **`AGENTS.md`, Inventario:** el seed se prueba «nunca sobre la de la demo (la del `.env` de la raíz)», exportando la `DATABASE_URL` de pruebas solo en esa terminal.

**Hechos:** sin servidor, un `Secret` vive en `~/.prefect/prefect.db` con su clave al lado (§1.2): no protege nada y obliga a crearlo a mano en cada máquina. La `DATABASE_URL` del `.env` de la raíz **es la demo**; un script que la cogiera por defecto escribiría en Supabase al primer `python pipeline.py`. Ver D5.

### C6. Paso opcional con `return_state=True`

- **Enunciado, Fase 1:** un paso no crítico «invocado con `return_state=True`: si falla, extract → transform → load sigue».
- **Diseño:** no tiene paso opcional; `quality` va en `pipeline_runs` (`PIPELINE_DESIGN.md:411`).

**Hechos:** de los candidatos, `extract_quality_counts` **ya alimenta la conciliación** y es parte del log; volverlo opcional haría que `quality` pudiese faltar en silencio. Una notificación necesitaría un canal y credenciales (Resend existe en la API, no en el pipeline). Un **snapshot de validación en `data/eval/`** no toca servicios externos ni datos personales. Ver D7.

### C7. Caché de una hora

- **Enunciado:** «si una task ya corrió con éxito en la última hora, no repetirla»; `cache_key_fn` y `cache_expiration` en una transformación costosa, con comentario.
- **Diseño:** `transform_weekly_rows` es pura y determinista (`PIPELINE_DESIGN.md:469`).

**Hechos:** cachear la **extracción** serviría eventos viejos si llegan nuevos en la semana en curso (no en las cerradas, pero el backfill y una corrida manual pueden pedir cualquiera), y guardaría en disco, en `cloudpickle`, filas de `telemetry_events`. Cachear la **carga** saltaría escrituras (si alguien vacía la tabla, la siguiente corrida no la repondría) y dejaría `rows_upserted` mintiendo. Una clave que dependa solo de las semanas pedidas serviría un resultado viejo si la extracción cambia; con una **huella del contenido extraído**, la caché es exacta. Honestidad: con 3 eventos en la demo, la transformación no es costosa; lo es con el volumen de 84 días. Ver D6.

### C8. Fallo manejado: `try/except` del diseño frente a `return_state=True`

- **`PIPELINE_DESIGN.md:473-491`:** un `try/except Exception` alrededor de todo, que llama a `finish_run(failed, phase)` y relanza.
- **Enunciado, Fase 2:** «al menos un fallo manejado explícitamente con `return_state=True`».

**Hechos:** son compatibles. Con `return_state=True`, la task devuelve su `State` en lugar de lanzar; el flow decide: si `state.is_failed()`, llama a `finish_run` con la fase y la clase del error (`state.result(raise_on_failure=False)` devuelve la excepción) y **devuelve un estado `Failed`**, que termina el flow en `Failed` sin un `raise`. El `try/except` sigue haciendo falta para lo que no pase por una task (un error dentro del propio flow). Ver D8.

### C9. Retries y su justificación

- **`PIPELINE_DESIGN.md:462-471`:** 2 reintentos en las tasks de E/S, 30 s en `load_weekly_rows`; 0 en `resolve_weeks` y `transform_weekly_rows`. No dice el `retry_delay_seconds` del resto ni por qué esos números.
- **Enunciado:** `retries` y `retry_delay_seconds` en cada task que toca la base, con un comentario.

**Hecho nuevo:** reintentar `start_run` no es idempotente tal como está diseñado: si el `INSERT` se confirmó y se cortó la respuesta, el reintento chocaría con el índice único parcial **con su propia fila** y la corrida fallaría por «otra en marcha». Ver D9.

### C10. Servidor y worker de Prefect: ¿en esta parte?

- **D8 (diseño), `PIPELINE_DESIGN.md:516-527`:** `prefect-server` + `pipeline-worker` en el perfil `pipelines`; cron `0 6 * * 1` `Europe/Madrid`.
- **Enunciado:** no los pide; pide el `POST` de disparo (202) y que el script corra.

**Hechos:** sin servidor, el `POST` no tiene dónde crear el flow run salvo dentro de la API (C3-A). El cron del lunes es parte del diseño evaluado por coherencia. Ver D3.

### C11. Contexto de build y tests del host

- **`docker-compose.yml:15-18`:** `context: ./services`, `additional_contexts: packages: ./packages`.
- **`services/Dockerfile:35, 50-53`:** `PYTHONPATH=/packages/shared:/packages/incident-analyzer`; `COPY api/app ./app`, `COPY telemetry ./telemetry`.
- **`services/api/tests/__init__.py:8`:** añade `services/` a `sys.path` para importar `telemetry`.

**Hechos:** `data/` está fuera del contexto de la API. Lo que entre (según D2) necesita un contexto adicional nuevo, su `COPY`, su entrada en `PYTHONPATH`, su bind mount (para `--reload`) y su `--reload-dir`, y en los tests del host, su ruta en `tests/__init__.py`. El `.dockerignore` de `services/` no se aplica a un contexto adicional: hay que limpiar `__pycache__` como en la etapa `monorepo-packages` (`Dockerfile:19-22`).

### C12. Migración del esquema `reporting`

- **`PIPELINE_DESIGN.md:294`:** `python -m business_performance.migrate --dry-run`; idempotente, solo PostgreSQL, nunca al arrancar, en la demo solo con confirmación; RLS sin políticas y `REVOKE ALL` a `PUBLIC`, `anon`, `authenticated`, `service_role`.
- **Patrón:** `services/api/app/modules/telemetry/migrate.py` (estado → SQL pendiente → una transacción → comprobación posterior; salidas 0/1/2; mensajes sin URL).

**Hechos:** ese patrón usa `app.core.config.Settings` y `build_engine` de la API; el pipeline no debe importar `app` (sería acoplar el ETL a la API). Hay que replicar la mecánica, no importarla. Nada puede escribir en `reporting` antes de la migración: el pipeline debe fallar con un error claro si el esquema no existe (no crearlo).

### C13. Datos: semanas por defecto y verificación

- **Demo:** 3 eventos de negocio, todos de la semana del 2026-11-02, `programme_id` nulo (`PIPELINE_DESIGN.md:86-95`).
- **Hoy es el lunes 2026-11-09:** la semana del 2026-11-02 está cerrada desde las 00:00 UTC; la del 2026-11-09 está en curso.
- **D5 (diseño):** el cron recalcula la última cerrada y la anterior; la manual, la pedida o la última cerrada.

**Hechos:** `python pipeline.py` sin argumentos, como corrida manual, calcularía **la semana del 2026-11-02** (la única con datos). Como programada calcularía además la del 2026-10-26, sin actividad (0 filas, la corrida lo registra). El backfill desde el 2026-11-02 hoy es esa misma semana. Para verificar los KPI hace falta un seed ficticio en un Postgres efímero; el precedente es `docs/telemetry/report-seed-ephemeral.sql` + `report-check.sql`. Ver D12.

### C14. Endpoints: contrato, auth y caché

- **BRIEFING `:101-121`:** `GET …?week_start`, cuerpo `{"week_start", "entries": [...]}` con las 7 claves de cada entrada; `GET /reporting/pipeline-runs/latest`; `POST /reporting/pipeline-runs`.
- **D12 (diseño):** GET con cualquier rol, POST solo `admin` (`require_admin`, `app/auth/dependencies.py:71-74`), sin caché; códigos de §5 (`PIPELINE_DESIGN.md:535-577`).

**Hechos:** todo se puede implementar tal cual, salvo de dónde sale el 503 `pipeline_unavailable` del `POST`, que depende de D2/D3. El 503 `storage_unavailable` existe (`app/core/errors.py:198, 229`). `services/reporting/` sería una librería de la API como `services/telemetry/` (`services/telemetry/README.md:5`): `COPY`, bind mount y `include_router` en `app/main.py`.

### C15. Tests y base de datos

- **Precedente:** la suite de `services/api` usa SQLite en memoria; lo propio de PostgreSQL se comprueba **compilando** el DDL y la SQL con su dialecto; «ningún test conecta con Supabase» (`AGENTS.md`, Inventario).
- **Lo que SQLite no tiene:** `JSONB`, el operador `~` del `CHECK` de `programme_id`, `extract(isodow …)`, `gen_random_uuid()`, `pg_advisory_xact_lock`. **Sí tiene** `ON CONFLICT … DO UPDATE`, índices únicos parciales y esquemas (con `ATTACH … AS reporting`).
- **`AGENTS.md` §4:** no hay fila para `data/pipelines/` ni `data/process/`.

### C16. Ficheros generados

- **`.gitignore`:** ignora `data/raw/incidents/` y `.venv/`; nada de `data/eval/`, de resultados de Prefect ni de `~/.prefect`.

**Hechos:** si la caché o el snapshot van al repo (D6, D7), hacen falta reglas nuevas antes del primer `python pipeline.py`.

### C17. Entrega: un mensaje de commit fijo

- **Enunciado:** commit «feat: implement resilient business performance pipeline» y push.
- **D14 (diseño), precedente:** varios commits, el evaluado con el mensaje exacto, PR con **merge commit** para que llegue tal cual a `main`; push solo con OK del usuario.
- **Memoria del usuario:** commits sin pie de atribución.

---

## 3. Decisiones

### D1. Dónde vive Prefect — **decidido: A, por arquitectura** (C1)

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Entorno propio de `data/pipelines/`: `pyproject.toml` + `uv.lock` + `requirements.txt` con `prefect>=3.9.2,<3.10`, `sqlalchemy>=2.1.5,<2.2` (**misma serie 2.1 que la API, versión exacta independiente**: el lock de `data/pipelines` resolvió 2.1.8 y la API sigue en 2.1.5) y `psycopg2-binary>=2.9.13,<2.10`. La API **no** instala Prefect | **Ninguna versión fijada de la API cambia**; imagen de la API sin +102 MB; Prefect donde corre el ETL | Dos entornos Python que mantener (venv e imagen); la serie de `sqlalchemy` se revisa a mano si la API cambia de serie |
| **B** Prefect en `services/api/pyproject.toml` | Un solo entorno; la API podría importar el flow (D2-A) | **Baja `python-dateutil` 4.0.0 → 2.9.0.post0** (cambio en una versión fijada: solo si lo decides tú) y +≈ 102 MB; el ETL entra en la imagen de la API |
| **C** Los dos | — | Lo peor de A y B |

**Recomendación: A.** Es la única que no toca ninguna versión fijada (la condición de la autorización) y es coherente con D8 (diseño). El rango acotado `>=3.9.2,<3.10` cumple `prefect>=3` del enunciado y sigue la convención del repo.

**Procedimiento propuesto (A), sin `uv add` ni `uv sync`:**

1. Escribir a mano `data/pipelines/pyproject.toml` (`requires-python = ">=3.11"`, las 3 dependencias de arriba; `nexova_shared` **no** se declara, por el mismo motivo de *dependency confusion* que en la API; grupo `dev` vacío o con `pytest` si se usa).
2. Desde `data/pipelines`: `uv lock` (solo escribe `uv.lock`) y `uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt`.
3. Venv del host: `uv venv .venv --python 3.14` y `uv pip install --python .venv -r requirements.txt` (sin sincronizar nada más).
4. Imagen: la del worker instala `requirements.txt` con `uv pip install --system --no-cache --require-hashes`, como la API.
5. Un test como `test_requirements_lock.py` para el nuevo `requirements.txt`.

**Si eliges B:** a mano en `services/api/pyproject.toml` (`"prefect>=3.9.2,<3.10"` con su comentario de autorización), `uv lock` desde `services/api`, `uv export …` (el comando de `AGENTS.md`), `uv pip install --python .venv -r requirements.txt`, `docker compose up -d --build`, y la suite completa de la API con `dateutil 2.9` (no verificado hoy).

### D2. Disparo manual (frente a D8 (diseño))

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** La API importa el flow y lo ejecuta en segundo plano | Sin servidor de Prefect | Necesita D1-B (C1); `--reload` mata corridas; comparte `--workers 1`; servidor efímero dentro del contenedor de la API; contradice D8 (diseño) |
| **B** La API importa `business_performance.trigger.request_manual_run(...)` desde `data/pipelines/`: **solo librería estándar** (`urllib`), resuelve el deployment `weekly-office-program-performance/manual` por nombre y crea el flow run con `POST /api/deployments/{id}/create_flow_run` | Cumple «importando desde `data/pipelines/`» y D8 (diseño) a la vez; sin Prefect en la API; el 202 lleva el `prefect_flow_run_id` real; `--reload` no afecta | Necesita servidor y worker (D3); un módulo de `data/` entra en la imagen de la API |
| **B'** Como B, pero con el cliente de Prefect o `run_deployment` | Menos código HTTP | Prefect en la API → D1-B |
| **C** Subproceso `python pipeline.py` | — | Otro intérprete con Prefect en la imagen de la API; procesos huérfanos con `--reload` |

**Decidido: B.** Las dos líneas para la PR y para `PIPELINE_DESIGN.md`: *la API importa `request_manual_run` de `data/pipelines/` y no el objeto flow porque Prefect no está en la API (D1) y porque un flow ejecutado dentro de la API moriría con cada recarga de `--reload`; la función solo pide el flow run al servidor de Prefect por REST, y el worker lo ejecuta fuera de la API.* La lógica de disparo vive una sola vez en `data/pipelines/` y la API la importa; un test AST comprueba que `trigger.py` solo usa la librería estándar y que `services/reporting/` no importa `prefect`. Sin `PIPELINE_PREFECT_API_URL` configurada, o con el servidor caído → 503 `pipeline_unavailable` (lo dice el diseño).

### D3. Servidor y worker de Prefect

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Entran en esta parte: perfil `pipelines` de Compose con `prefect-server` (la imagen del pipeline con `prefect server start`, SQLite en un volumen con nombre, UI en el 4200) y `pipeline-worker` (`python -m business_performance.serve`: deployments `manual` y `weekly`, cron `0 6 * * 1` `Europe/Madrid`, concurrencia 1) | El `POST` y el cron funcionan de verdad; coherente con el diseño | Más alcance; una imagen nueva (`data/Dockerfile`); levantar el perfil **escribe en la demo** (el worker usa su base) |
| **B** Se dejan para la Parte 3; el `POST` responde 503 `pipeline_unavailable` hasta entonces | Menos alcance | El endpoint de disparo no se puede demostrar; el cron del diseño queda sin implementar |

**Decidido: A**, con dos guardas: el perfil no arranca con `docker compose up` (solo con `--profile pipelines`), y **levantarlo contra la demo, solo con la confirmación del usuario en el momento** (se verifica antes contra el efímero). El worker no recibe el `.env` entero: solo `PREFECT_API_URL` y lo que necesite (D5).

### D4. Estructura de código e importaciones

**Recomendación:**

| Ruta | Qué | Importa |
|---|---|---|
| `data/pipelines/pipeline.py` | El flow `weekly_office_program_performance`, el subflow de backfill y las tasks (`start_run`, `resolve_weeks`, `extract_business_events`, `extract_quality_counts`, `mark_phase`, `transform_weekly_rows`, `load_weekly_rows`, `finish_run`, `write_eval_snapshot`); `if __name__ == "__main__"` con `argparse` | `prefect`, `business_performance.*`, `weekly_performance`, `nexova_shared.reporting` |
| `data/pipelines/business_performance/` | Paquete de soporte: `config.py` (URL y guarda, D5), `sql.py` (consultas de §2.3 y §3.1, en texto), `migrate.py`, `serve.py`, `trigger.py` (**solo librería estándar**) | `trigger.py`: nada fuera de la librería estándar |
| `data/process/weekly_performance.py` | La transformación pura de §2.5 (tipado, `_unassigned`, `week_start`, dedup, agregación, `DataQualityError`) y el cálculo de semanas | Solo librería estándar + `nexova_shared.reporting` |
| `packages/shared/nexova_shared/reporting/` | Nombres compartidos: esquema, tablas, columnas, estados, fases, triggers, centinela, oficinas y monedas | Solo librería estándar (lo comprueba `tests/test_source.py`) |
| `services/reporting/` | Router y lecturas de la API (librería, como `services/telemetry/`) | `app.*`, `nexova_shared.reporting`, `business_performance.trigger` |

- **Desde el script:** `pipeline.py` añade a `sys.path`, solo si no se importan ya, `data/process` y `packages/shared` (precedente de `incident_analyzer`). `data/pipelines/` ya está por ser la carpeta del script.
- **En la imagen del worker:** `PYTHONPATH=/data/pipelines:/data/process:/packages/shared`.
- **En la imagen de la API:** contexto adicional `pipelines: ./data/pipelines`, un `COPY` **solo** de `business_performance/__init__.py` y `trigger.py` a `/pipelines/business_performance/`, `PYTHONPATH` con `/pipelines`, bind mount y `--reload-dir`. `COPY services/reporting` → `/app/api/reporting` (como `telemetry`).
- **Tests del host:** `services/api/tests/__init__.py` añade `data/pipelines` a `sys.path`; los de `data/pipelines/tests` añaden `data/process` y `packages/shared`.
- **`business_performance/flows.py` y `tasks.py` del diseño desaparecen** (su contenido va a `pipeline.py`).
- Sin paquetes de primer nivel `data`, `process` ni `pipelines` (C2).

### D5. Credencial, base por defecto y guarda de la demo

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Con `PREFECT_API_URL` (servidor real, el worker): block `Secret` `nexova-supabase-database-url`. Sin ella (script, efímero): `DATABASE_URL` **del entorno de la terminal** (el script nunca lee el `.env`). Guarda: si el host de la URL no es local (`localhost`, `127.0.0.1`, `::1`), el script se niega salvo con `--allow-demo` | Diseño intacto para el worker; el script corre sin servidor; imposible escribir en la demo por accidente | Dos caminos de credencial que probar |
| **B** Siempre `DATABASE_URL` del entorno; sin block | Un solo camino | Se aparta de §4.3 del diseño (la Fase 4 del diseño anterior pedía blocks) |
| **C** Siempre block, también en efímero | Literal con §4.3 | El block efímero no protege nada (clave en la misma SQLite) y hay que crearlo en cada máquina |

**Decidido: A, con la guarda movida a la migración** (matiz del usuario). Queda así:

- **Worker (con `PREFECT_API_URL`):** block `Secret` `nexova-supabase-database-url`. El worker no recibe `DATABASE_URL` por `env_file`; la credencial vive solo en el servidor de Prefect, como dice el diseño.
- **Script (sin `PREFECT_API_URL`):** `DATABASE_URL` **de la variable de entorno de la terminal**; si no está, se lee **solo esa clave** del `.env` de la raíz con un lector de la librería estándar (sin `python-dotenv`). El script imprime **de dónde salió y el host**, nunca la URL ni la contraseña (`DATABASE_URL: entorno, host db.example.supabase.co`).
- **Corrida del ETL: sin guarda.** Solo escribe en `reporting`, es idempotente (upsert por clave natural) y recalculable desde `telemetry_events`.
- **Esquema ausente:** antes de `start_run`, el script comprueba que existen `reporting.pipeline_runs` y la tabla de KPI; si no, termina con **salida 2** y un mensaje sin traza que dice qué ejecutar (`Falta el esquema reporting: ejecuta la migración (python -m business_performance.migrate desde data/pipelines)`).
- **Migración (DDL): con guarda.** `migrate.py` se niega con un host no local (`localhost`, `127.0.0.1`, `::1`) salvo con `--allow-demo`, que solo se usa con la confirmación del usuario.
- **Semanas:** por defecto, la última semana cerrada; `--week-start YYYY-MM-DD` para una concreta; `--from YYYY-MM-DD [--to YYYY-MM-DD]` para el backfill (lunes inclusivos; sin `--to`, hasta la última cerrada), excluyente con `--week-start`.
- **Comandos** (los documentan `PIPELINE_DESIGN.md` §4.5 y `data/pipelines/README.md`), desde la raíz:

| | Windows (PowerShell) | Linux/macOS |
|---|---|---|
| Corrida | `data\pipelines\.venv\Scripts\python data\pipelines\pipeline.py` | `data/pipelines/.venv/bin/python data/pipelines/pipeline.py` |
| Semana concreta | `… pipeline.py --week-start 2026-11-02` | ídem |
| Backfill | `… pipeline.py --from 2026-11-02` | ídem |
| Otra base solo en esa terminal | `$env:DATABASE_URL = "postgresql://…"` | `export DATABASE_URL=postgresql://…` |

### D6. Caché de una hora

**Recomendación:**

- **Qué:** solo `transform_weekly_rows`.
- **`cache_key_fn`:** SHA-256 de (versión de la transformación, `week_from`, `week_to`, la lista ordenada de `(event_id, event_type)` extraídos y los conteos de `quality`). Comentario: la clave cambia en cuanto cambia un solo evento o un conteo, así que nunca sirve un resultado viejo; la versión invalida la caché si cambian las reglas. Exacta, no una aproximación con `count` + `max(event_id)` (el `event_id` es un UUID, no crece).
- **`cache_expiration = timedelta(hours=1)`:** lo que pide el enunciado; comentario: una corrida repetida en la misma hora (reintento manual tras un fallo en la carga, §3.2) no recalcula.
- **Dónde:** `PREFECT_LOCAL_STORAGE_PATH` en `data/raw/business_performance/prefect-results/` (intermedios, ignorado por git), que `pipeline.py` fija **solo si no viene ya del entorno**; `PREFECT_HOME` se queda en `~/.prefect` (la SQLite efímera fuera del repo). En el worker, un volumen con nombre.
- **Qué contiene:** las filas agregadas (oficina, programa, semana, contadores, moneda) y los contadores de la corrida: **ningún identificador**. Por eso se cachea la transformación y no la extracción.
- **Ni `extract` ni `load`** (C7).

### D7. Paso opcional

**Recomendación:** `write_eval_snapshot(run_id, weeks, stats, quality)` → `data/eval/business_performance/<week_from>_<run_id>.json` con los contadores, la conciliación y la versión del contrato (sin identificadores ni la URL), invocado con `return_state=True` **después** de la carga y antes de `finish_run`. Si falla:

- el flow sigue y termina `Completed`;
- `finish_run` guarda `quality.optional_steps = {"eval_snapshot": "failed", "error_class": "…"}` (clave nueva dentro de `quality`, **sin cambiar la DDL**);
- un `logger.warning` de Prefect con la clase del error.

Sin reintentos (disco local, no un servicio externo). **Prueba:** el directorio de salida apuntando a un fichero (no a una carpeta) o un `OSError` inyectado; el test comprueba flow `Completed`, `pipeline_runs.status = 'completed'` y el aviso en `quality`.

### D8. Fallo manejado y cierre de la corrida

**Recomendación:**

```text
flow weekly_office_program_performance(trigger, week_start=None, requested_by=None):
    run_id = uuid4()                                   # lo genera el flow (D9)
    start_run(run_id, …)                               # si falla, no hay fila: el flow falla
    phase = "extract"
    try:
        week_from, week_to = resolve_weeks(trigger, week_start)
        events  = extract_business_events(week_from, week_to)
        quality = extract_quality_counts(week_from, week_to)
        mark_phase(run_id, "transform"); phase = "transform"
        rows, stats = transform_weekly_rows(events, quality, week_from, week_to)   # caché (D6)
        mark_phase(run_id, "load"); phase = "load"
        load_state = load_weekly_rows(rows, week_from, week_to, run_id, return_state=True)
        if load_state.is_failed():                    # fallo manejado explícitamente
            error = load_state.result(raise_on_failure=False)
            finish_run(run_id, "failed", phase, error_class=type(error).__name__)
            return load_state                          # el flow termina en Failed
        upserted, deleted = load_state.result()
        snapshot_state = write_eval_snapshot(…, return_state=True)   # opcional (D7)
        finish_run(run_id, "completed", "done", stats, upserted, deleted,
                   optional=snapshot_state)
    except Exception as error:                         # lo que no pasó por return_state
        finish_run(run_id, "failed", phase, error_class=type(error).__name__)
        raise
```

`finish_run` siempre escribe en una transacción propia; si también falla, la fila queda `running` y la siguiente corrida la cierra como `Abandoned` (§3.2 del diseño, sin cambios).

### D9. Retries

**Recomendación** (cada número con su comentario en el código):

| Task | `retries` | `retry_delay_seconds` | Por qué |
|---|---|---|---|
| `start_run`, `mark_phase`, `finish_run`, `extract_business_events`, `extract_quality_counts` | 2 | 10 | Cortes transitorios del pooler de Supabase; 3 intentos en ~20 s; una corrida manual no debe colgarse minutos |
| `load_weekly_rows` | 2 | 30 | Como el diseño: la transacción se deshace entera y conviene dejar que libere el lock o la conexión; 3 intentos en ~1 min, dentro de las 4 h de margen del cron |
| `resolve_weeks`, `transform_weekly_rows`, `write_eval_snapshot` | 0 | — | Deterministas o locales: reintentar daría el mismo error |

**Cambio en `start_run`** (C9): `run_id` lo genera el flow y el `INSERT` es `… ON CONFLICT (run_id) DO NOTHING`, seguido de una lectura de la fila: un reintento tras un `COMMIT` perdido encuentra su propia fila y sigue.

### D10. Metadata

**Recomendación:** `reporting.pipeline_runs` tal cual (§3.3 del diseño: 20 campos, de ellos `started_at`, `finished_at`, `source_rows_read`, `rows_upserted`, `status` y `error_class`, los que pide el enunciado) **más una línea JSON** en stdout al terminar (`event: pipeline_run_finished`, `run_id`, estado, fase, semanas, contadores, duración; sin URL ni identificadores), por el logger de Prefect. Así el script de CLI deja rastro aunque la base no pueda escribir el cierre. El snapshot de D7 es la copia en `data/eval/`. Sin fichero de log aparte.

### D11. Migración

**Recomendación:** `data/pipelines/business_performance/migrate.py` (`python -m business_performance.migrate [--dry-run]`, desde `data/pipelines` con su venv), replicando la mecánica de `telemetry/migrate.py` sin importar `app`: estado actual → SQL pendiente (schema, `pipeline_runs`, la tabla del BRIEFING con lo aditivo, índices, RLS, `REVOKE ALL` a `PUBLIC` y a los roles de Supabase que existan) → una transacción → comprobación de que esos roles no conservan privilegios; salidas 0/1/2; la guarda de host local de D5 (`--allow-demo`) vive **aquí**, no en la corrida. Orden: (1) Postgres efímero con un rol sin superusuario; (2) la demo, **solo con la confirmación del usuario**, antes de la primera corrida contra ella. El pipeline, si no existe el esquema, termina antes de `start_run` con salida 2 y un mensaje que manda a la migración (D5).

### D12. Semanas por defecto, backfill y verificación de los KPI

**Recomendación:**

- `python data/pipelines/pipeline.py` → `trigger = 'manual'`, la **última semana cerrada** (hoy, la del 2026-11-02). Opciones: `--week-start YYYY-MM-DD`, `--from YYYY-MM-DD [--to …]` (subflow por semana, `trigger = 'backfill'`). Sin `--allow-demo` en la corrida (D5).
- Cron (worker): la última cerrada y la anterior (D5 (diseño)).
- **Primera corrida en la demo** (tras la migración y con tu confirmación): backfill desde el 2026-11-02 = esa semana → 2 filas `_unassigned` (Valencia: coste de 1 entrada; Miami: 1 kit, 1 escasez).
- **Verificación en el efímero** (patrón del reporte técnico): `docs/reporting/pipeline-seed-ephemeral.sql` crea `telemetry_events` (con la migración de la API) e inserta eventos **ficticios** con `programme_id` nulo: 3 semanas, las dos oficinas, dos `eventId` con la misma orden, una entrada con coste decimal (para `numeric`), una variación de coste, un evento técnico en una semana sin negocio; y `docs/reporting/pipeline-check.sql` calcula a mano los 4 KPI con `GROUP BY` sobre `telemetry_events` y los compara con `reporting.weekly_office_program_performance` (`EXCEPT` en los dos sentidos = 0 filas). Ningún programa real: en los tests unitarios, un slug marcado como ficticio solo para probar el grano.

### D13. Endpoints

**Recomendación:** como §5 del diseño, con D2-B:

| Ruta | Auth | Respuestas |
|---|---|---|
| `GET /reporting/weekly-office-program-performance?week_start=` | Bearer, cualquier rol | 200 con el contrato **exacto** del BRIEFING (`week_start` + `entries` con las 7 claves, ordenadas por `office`, `programme_id`; `total_material_cost` como número); 404 `week_not_computed`; 422 (no lunes); 401; 503 `storage_unavailable` |
| `GET /reporting/pipeline-runs/latest` | Bearer, cualquier rol | 200 sin `requested_by`; 404 `pipeline_run_not_found`; 401; 503 |
| `POST /reporting/pipeline-runs` | Bearer, `require_admin` | 202 `{"prefect_flow_run_id", "status": "scheduled"}`; 409 `pipeline_run_in_progress`; 422; 401; 403; 503 `pipeline_unavailable` |

- **Sin caché** (D12 (diseño)): la tabla la escribe otro proceso.
- **`requested_by`** = `id` del token, nunca del cuerpo.
- **Configuración de la API:** `PIPELINE_PREFECT_API_URL` (opcional; sin ella, el `POST` da 503). Con Docker, `http://prefect-server:4200/api`.

### D14. Tests y validación

**Recomendación:**

| Dónde | Qué | Base |
|---|---|---|
| `data/process/tests/` | Transformación pura: tipado, rechazos, `_unassigned`, `week_start` UTC (domingo de Miami por la tarde), dedup, `numeric`, monedas, `DataQualityError`, semanas y retención | Ninguna; cualquier Python ≥ 3.11 (solo librería estándar) |
| `data/pipelines/tests/` | Flow con `prefect_test_harness`: éxito, fallo de la carga manejado (`Failed` + `pipeline_runs`), snapshot fallido (`Completed`), caché (segunda corrida sin recalcular; clave distinta con un evento más), retries declarados, guarda `--allow-demo`, `trigger.py` (servidor HTTP falso de la librería estándar), migración (SQL compilada con el dialecto de PostgreSQL), test del `requirements.txt` | Repositorio de E/S sustituible por uno en memoria; SQL compilada; **integración opcional** con `PIPELINE_TEST_DATABASE_URL` a un Postgres **local** (se salta si no está) |
| `services/api/tests/test_reporting_*.py` | Los 3 endpoints (contrato, 401/403/404/409/422/503), privacidad (`requested_by`), arquitectura (AST: `services/reporting` sin `prefect`/`pandas`, `trigger.py` solo librería estándar, ningún `INSERT`/`UPDATE`/`DELETE` en `services/reporting`) | SQLite con `ATTACH … AS reporting` |

**Filas nuevas en `AGENTS.md` §4:** `data/process/` (`python -m unittest discover -s data/process/tests -t data/process`) y `data/pipelines/` (`data\pipelines\.venv\Scripts\python -m unittest discover -s data/pipelines/tests -t data/pipelines`), además de la de `services/api/` y la de Docker si cambian Compose o el Dockerfile.

### D15. Ficheros generados

**Recomendación** (en `.gitignore`, en el primer commit de F1):

```gitignore
# Pipeline de desempeño de negocio: intermedios, caché de Prefect y snapshots
data/raw/business_performance/
data/eval/business_performance/
```

`~/.prefect` queda fuera del repo. El `README` de cada carpeta de `data/` documenta qué deja el pipeline ahí.

### D16. Entrega

**Recomendación** (precedente de D14 (diseño)): en `feature/business-pipeline`, (1) `build(pipelines): …` entorno de `data/pipelines` + `.gitignore`; (2) `feat(reporting): …` migración del esquema `reporting` + `nexova_shared.reporting`; (3) `feat(reporting): …` endpoints + `trigger.py` + imagen y Compose; (4) **`feat: implement resilient business performance pipeline`** con `pipeline.py`, `data/process/`, tests del flow, `PIPELINE_DESIGN.md`, `AGENTS.md` y `progress.md`. Sin pie de atribución. **Push y PR solo con tu OK**, con **merge commit** para que el commit evaluado llegue tal cual a `main`. Alternativa: un solo commit con ese mensaje.

---

## 4. Cambios en `PIPELINE_DESIGN.md` (para que siga coherente con el código)

| Sección | Cambio |
|---|---|
| Cabecera (`:5`) y tabla de decisiones (`:16-29`) | Quitar «solo diseño»; añadir el enlace a este análisis; D7 y D8 actualizadas (D4 y D2/D3 de aquí) |
| §2.4 Mermaid | `write_eval_snapshot` (opcional) tras la carga; la flecha de `P1` → «`trigger.py` (importado) → REST de Prefect → deployment `manual`» |
| §3.3 | `quality.optional_steps` |
| §4.1 | Código en `data/pipelines/pipeline.py`; tabla de tasks con `retry_delay_seconds` y su porqué (D9), la caché (D6), `write_eval_snapshot` (D7); `start_run` idempotente con `run_id` del flow; pseudocódigo de D8 |
| §4.3 | Credencial: block con servidor; sin él, `DATABASE_URL` del entorno o, si falta, del `.env` de la raíz (solo esa clave, imprimiendo solo el host); la corrida no se bloquea; `--allow-demo` solo en la migración; esquema ausente → salida 2 con el comando de la migración (D5) |
| §4.4 | Perfil `pipelines` real (si D3-A): imagen, servicios, variables, volumen |
| **Nueva §4.5 «Frecuencia y ejecución»** | Cron `0 6 * * 1` `Europe/Madrid`; comando exacto en Windows y Linux con el venv de `data/pipelines` (`pipeline.py [--week-start …] [--from … [--to …]]`); de dónde sale `DATABASE_URL`; dónde quedan el estado efímero, la caché y el snapshot; migración previa con su guarda |
| §5 | `services/reporting/` importa `business_performance.trigger.request_manual_run` (solo librería estándar), ya no «no importa `business_performance`»; las dos líneas de por qué no el objeto flow (D2); `PIPELINE_PREFECT_API_URL`; sin ella o con el servidor caído → 503 `pipeline_unavailable` |
| §8 | Lo verificado sale de «sin verificar» (versión de Prefect, REST, efímero); lo que quede, dentro |
| §10 | Filas de los criterios nuevos: retries, `return_state`, caché, metadata, comando |

---

## 5. Plan de F1 (con las paradas del usuario)

| # | Paso | Validación | Parada |
|---|---|---|---|
| 1 | Entorno de `data/pipelines` (D1: `pyproject.toml`, `uv.lock`, `requirements.txt`, venv), `.gitignore` (D15), imagen del pipeline y perfil `pipelines` (D3), contexto adicional de la API (D4) | `uv lock`/`uv export`; test del `requirements.txt`; `git diff services/api/uv.lock` **vacío**; la API sin Prefect; `docker compose config --quiet`; `docker compose up -d --build` (stack por defecto `healthy`, el perfil sin arrancar) | **Parada 1** (si Docker falla, también). **Hecho el 2026-11-10**; el contexto de `trigger.py` en la imagen de la API pasa al paso 3, porque ese archivo aún no existe |
| 2 | `nexova_shared.reporting`, `migrate.py`, `data/process/weekly_performance.py`, `pipeline.py` y sus tests | Suites de `packages/shared`, `data/process`, `data/pipelines` y `services/api`; migración dos veces en un Postgres efímero con un rol sin superusuario; `python data/pipelines/pipeline.py` contra el efímero con un seed ficticio (varias semanas, las dos oficinas, duplicados por orden, una variación de coste); KPI cuadrados con SQL a mano | **Parada 2:** comandos en PowerShell para que lo repita el usuario |
| 3 | `trigger.py`, `serve.py`, `services/reporting/` + registro en `app/main.py`; perfil `pipelines` contra el efímero | Validación de `services/api`; disparo de punta a punta: `POST` → flow run en Prefect → fila en `pipeline_runs` → `GET` latest → `GET` de KPI | **Parada 3:** lo verifica el usuario |
| 4 | Documentación: `PIPELINE_DESIGN.md` (§4 de aquí), READMEs de `data/`, `services/reporting/README.md`, `services/api/SPECS.md`, filas de `AGENTS.md` §4, guía de revisión | Enlaces y comandos comprobados | — |
| 5 | **Demo:** migración (`--allow-demo`), primera corrida (backfill desde 2026-11-02) y el perfil `pipelines` | Solo **con la confirmación del usuario** | **Parada 4: antes de tocar la demo** |
| 6 | `memory-bank-sync` y commits (D16) | `git status --short`, `git diff --stat` | **Push y PR, solo con el OK del usuario** |

---

## 6. Fuera de alcance o sin verificar

- **Fuera:** `services/telemetry/analysis.py`, `GET /telemetry/report`, `telemetry_events` (solo lectura), `uis/`; P1 y P2; conversión de monedas; `kits_delivered_units` (v2); roles separados de base de datos (mejora documentada en el diseño).
- **Sin verificar en F0:**
  - la suite de la API con `python-dateutil 2.9` (solo si eliges D1-B);
  - el arranque del servidor efímero de Prefect en este Windows y en el contenedor, y su tiempo;
  - `flow.serve` con cron y zona horaria, y el límite de concurrencia del deployment;
  - el tamaño **comprimido** de las imágenes (medido: `site-packages` sin comprimir);
  - si la demo ya tiene un esquema `reporting`, su versión de PostgreSQL y sus `DEFAULT PRIVILEGES`;
  - si la API de la demo tiene `TELEMETRY_SUPPLIER_KEY` (de ello depende que lleguen más entradas con coste).

---

## 7. Resumen de lo recomendado

| | Recomendación |
|---|---|
| C1/D1 | **Decidido:** Prefect solo en un entorno propio de `data/pipelines/` (`prefect>=3.9.2,<3.10`), por arquitectura; el lock de la API no cambia |
| C3/D2 | La API importa `business_performance.trigger` (solo librería estándar), que crea el flow run por la REST de Prefect |
| C10/D3 | **Decidido:** servidor y worker en el perfil `pipelines` (solo con `--profile pipelines`); contra la demo, solo con confirmación en el momento |
| C2/D4 | Flow y tasks en `pipeline.py`; transformación pura en `data/process/weekly_performance.py`; nombres en `nexova_shared.reporting`; soporte en `business_performance/` |
| C5/D5 | **Decidido:** block con servidor; sin él, `DATABASE_URL` del entorno o del `.env` (solo el host en pantalla); la corrida no se bloquea; `--allow-demo` solo en la migración |
| C7/D6 | Caché solo en `transform_weekly_rows`, clave con la huella exacta de la extracción, 1 h, resultados en `data/raw/` ignorado |
| C6/D7 | Snapshot en `data/eval/` con `return_state=True`; su fallo, en `quality` y en el log |
| C8/D8 | `return_state=True` en la carga + `try/except` para el resto; `finish_run` en los dos caminos |
| C9/D9 | 2 × 10 s en E/S, 2 × 30 s en la carga, 0 en lo determinista; `start_run` idempotente |
| D10 | `pipeline_runs` + una línea JSON en stdout |
| C12/D11 | Migración propia en `data/pipelines`; primero el efímero, la demo con tu confirmación |
| C13/D12 | Por defecto, la última semana cerrada (2026-11-02); seed y SQL de cuadre en el efímero |
| C14/D13 | Contrato del BRIEFING, GET cualquier rol, POST admin, sin caché |
| C15/D14 | Tests en `data/process`, `data/pipelines` y `services/api`; dos filas nuevas en `AGENTS.md` §4 |
| C16/D15 | `data/raw/business_performance/` y `data/eval/business_performance/` en `.gitignore` |
| C17/D16 | Cuatro commits, el último con el mensaje exacto; merge commit; push con tu OK |
