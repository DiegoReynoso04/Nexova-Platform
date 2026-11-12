# AGENTS.md — Nexova Monorepo

Flujo operativo obligatorio para cualquier agente de IA que trabaje en este repositorio. Reglas granulares en [`.agents/rules/`](./.agents/rules/); skills reutilizables en [`.agents/skills/`](./.agents/skills/).

## 1. Antes de tocar nada

Leer, en este orden:

1. [`memory-bank/projectbrief.md`](./memory-bank/projectbrief.md) — quién es Nexova, qué se ha construido, quién lo pidió.
2. [`memory-bank/techContext.md`](./memory-bank/techContext.md) — stacks reales, decisiones de arquitectura vigentes.
3. [`memory-bank/progress.md`](./memory-bank/progress.md) — qué está hecho, qué está en curso, problemas conocidos.

Para el briefing de negocio completo (no el resumen), leer `contexts/CONTEXT.md` **si existe en tu checkout** — esa carpeta está en `.gitignore` y no viaja con el repositorio (ver nota en `techContext.md`). Si no la tienes, el `README.md` raíz contiene ese mismo briefing (copia versionada desde el 2026-09-27). No existe ningún `CONTEXT.md` en la raíz.

## 2. Antes de trabajar en una carpeta concreta

Leer el `README.md` de esa carpeta de primer nivel (`uis/README.md`, `services/README.md`, etc. — ver `.agents/rules/monorepo-structure.md`) y, si el subproyecto tiene su propia documentación (`CLAUDE.md`, `AGENTS.md`, `SPECS.md` — por ejemplo `uis/talent-pipeline-tracker/`), leerla también.

**Las reglas locales de una app priman sobre las de este archivo dentro de su propio árbol** (ver `.agents/rules/app-specific-overrides.md`), nunca al revés.

## 3. Reglas duras (detalle en `.agents/rules/`)

- No inventar datos de negocio sobre Nexova ni campos/endpoints/estructuras de API que no estén documentados o verificados.
- No crear una app, servicio o carpeta fuera del lugar que le corresponde según la convención de carpetas de [`.agents/rules/monorepo-structure.md`](./.agents/rules/monorepo-structure.md) y el `README.md` de la carpeta destino.
- No añadir dependencias nuevas a ningún subproyecto sin autorización explícita.
- No duplicar en `.agents/` ni en `memory-bank/` lo que ya documenta un `SPECS.md`/`CLAUDE.md` propio de una app — referenciar, no copiar.
- Al cerrar cualquier tarea que modifique archivos del repo — **haya commit o no** — aplicar la skill [`memory-bank-sync`](./.agents/skills/memory-bank-sync/SKILL.md): `progress.md` siempre; `techContext.md` solo si cambió algo técnico; `projectbrief.md` solo si cambió algo de negocio. Tareas de solo lectura no tocan `memory-bank/`.

## 4. Flujo antes de commit (obligatorio, en este orden)

Ningún agente commitea código sin completar estos cinco pasos, en orden:

1. **Ejecutar la validación del subproyecto tocado.** Este monorepo **no** tiene un comando único de verificación — cada subproyecto valida el suyo:

   | Subproyecto | Comando |
   |---|---|
   | `src/` (Hito 2 — domain models) | `npm run check` (typecheck + tests) |
   | `uis/talent-pipeline-tracker/` | Desde `uis/talent-pipeline-tracker`: `npx tsc --noEmit` + `npm run lint` (hoy con 4 errores `react-hooks/set-state-in-effect` anteriores a AUTH-02 en `use-notes`/`use-record-detail`/`use-records`) + tests con Node 24: `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"` |
   | `uis/backoffice/` | Desde `uis/backoffice`: `npx tsc --noEmit` + `npm run lint` + `npm run build` + tests con Node 24: `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"` + Jest (AUTH-088, lógica TS de auth en `__tests__/`): `npm run test:jest` (ver `services/api/TESTING.md` §10) |
   | `uis/website/` | sin build en el despliegue — verificación manual/visual. Si cambian las clases del HTML o de `src/js/`, regenerar `src/css/styles.css` con el comando de `uis/website/README.md` y comitearlo |
   | `uis/` (servidor del website en Docker: `serve-website.mjs`) | Desde la raíz, con Node 24: `node --test "uis/tests/*.test.mjs"` |
   | Docker (`uis/Dockerfile`, `services/Dockerfile`, `data/Dockerfile`, los `.dockerignore`, `docker-compose.yml`, `uis/start.sh`, `services/api/requirements.txt`, `data/pipelines/requirements.txt`) | Desde la raíz: `docker compose config --quiet` (nunca sin `--quiet`: imprime los secretos) + `docker compose up -d --build` + las comprobaciones del bloque «Docker» de abajo |
   | `packages/shared/` (Python, `nexova_shared`: validación compartida del CSV de incidentes, del gestor de incidencias y nombres y semanas del esquema `reporting`) | `python -m unittest discover -s packages/shared/tests -t packages/shared` (desde la raíz, cualquier Python ≥ 3.11). Un cambio aquí afecta al analizador: ejecutar también la fila siguiente y la de `services/api/` |
   | `docs/telemetry/` (plan de telemetría y `event-schemas.json`) + `scripts/validate_event_schemas.py` | `python scripts/validate_event_schemas.py` (desde la raíz, librería estándar). Un cambio en el plan o en los esquemas tiene que mantenerlos al 100 % coherentes: mismos eventos, metadatos, allowlists y ejemplos válidos (`telemetry-plan.md` §9) |
   | `packages/incident-analyzer/` + `scripts/analyze.py` | `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` (desde la raíz) |
   | `data/process/` (transformación pura del pipeline de desempeño de negocio) | `python -m unittest discover -s data/process/tests -t data/process` (desde la raíz, cualquier Python ≥ 3.11: solo librería estándar y `packages/shared`). Un cambio aquí afecta al pipeline: ejecutar también la fila de `data/pipelines/` |
   | `data/pipelines/` (pipeline de desempeño de negocio, Prefect) + `docs/reporting/pipeline-*.sql` | **Requiere el venv de `data/pipelines`** (Prefect solo está ahí; nunca en el de `services/api`). Desde la raíz: `data\pipelines\.venv\Scripts\python -m unittest discover -s data/pipelines/tests -t data/pipelines` (Windows) o `data/pipelines/.venv/bin/python …` (Linux/macOS). Con `PIPELINE_TEST_DATABASE_URL` apuntando a un Postgres **local** corre también la integración de la SQL (se niega con otro host). Crear el venv y regenerar `uv.lock`/`requirements.txt`: `data/pipelines/README.es.md` (sin `uv sync`). En Windows, tras el `OK` puede salir un `PermissionError` del `atexit` de `prefect_test_harness` (su SQLite temporal): no cambia el resultado. Un cambio en `business_performance/trigger.py` afecta a `services/api`: ejecutar su fila |
   | `services/api/` | **Requiere el venv del servicio** (con el Python global falla al importar `fastapi`). Desde la raíz, sin activar nada: `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` (Windows) o `services/api/.venv/bin/python -m unittest discover -s services/api/tests -t services/api` (Linux/macOS). Crear/instalar el venv: ver `services/api/README.md`. Además, desde `services/api`, el comando oficial de pytest: `uv run --no-sync python -m pytest`, que ejecuta también la batería de AUTH-088 (estilo pytest, el comando `unittest` no la recoge). `--no-sync` porque una sincronización de uv desinstaló una vez los paquetes del monorepo del venv, y `python -m pytest` porque el Control de aplicaciones de Windows puede bloquear `pytest.exe`. Plan, cobertura y comandos en [`services/api/TESTING.md`](./services/api/TESTING.md). No usar `uv sync` |

   Si el cambio afecta a más de un subproyecto, ejecutar todos los comandos que correspondan.

   **Docker (ticket #infra-40): único modo de arrancar la plataforma en desarrollo.** Un solo `.env` en la raíz (desde `.env.example`; nunca en git), `docker compose up` y los puertos 3000 (website), 3001 (backoffice) y 8000 (API, `/docs`). El tracker queda fuera de Docker, en el 3002. Los tests siguen en el host (tabla de arriba). Guía de arranque en `docs/local-development.md`; revisión del ticket en `docs/infra-40-review.md`. Un cambio en un `Dockerfile`, un `.dockerignore`, `docker-compose.yml`, `uis/start.sh` o `requirements.txt` se verifica, además de con la fila «Docker» de la tabla, así:
   - **Build y arranque:** `docker compose up -d --build` sale con 0; `docker compose ps` muestra `api` `healthy` y `ui` en marcha.
   - **Nombre de servicio:** `docker compose exec ui wget -qO- http://api:8000/health` y `curl localhost:3001/backend/health` → `{"status":"ok"}`; el navegador solo habla con `localhost:3001/backend/…` (nunca con `:8000`).
   - **Aislamiento:** en `ui` solo están `API_INTERNAL_URL`, las `NEXT_PUBLIC_*` y `WATCHPACK_POLLING`; ningún secreto de la API (comprobarlo como presente/ausente, sin imprimir valores).
   - **Imagen:** sin `.env*`, `tests`, `.venv`, `data/`, `node_modules` del host ni `__pycache__`; `docker history --no-trunc` sin secretos.
   - **Recarga:** un cambio en el website, el backoffice, `services/api/app` o `packages/` se ve sin reconstruir. El backoffice usa `next dev --webpack` con `WATCHPACK_POLLING` (con Turbopack no recarga en el contenedor).
   - **`requirements.txt`:** se regenera desde `services/api` con `uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt`; `tests/test_requirements_lock.py` comprueba que sigue a `uv.lock`.

   **Procesador de incidentes de Nexova — Fase 3 (`uis/backoffice`, ruta `/incidents`, implementada):** Server Component que renderiza una vista cliente; la vista solo interactúa mediante el hook `hooks/use-incident-analysis.ts` (frontera de interacción) → `services/incidents.service.ts` → `lib/api-client.ts` (único `fetch`) → `services/api`. `unknown` de red solo en `services/normalizers.ts`. Privacidad: el frontend no lee el contenido del CSV ni muestra `customer_email` o datos de filas. Además de la validación de la tabla, un cambio en `/incidents` se verifica manualmente en el navegador (descarga, exportación obsoleta, cancelación al salir). Reglas completas en `uis/backoffice/CLAUDE.md`; no se duplican aquí.

   **Autenticación AUTH-01 (`services/api` → `/auth`, `/users`, `/profiles`):** contexto en `docs/auth-api.md`; contrato en `services/api/SPECS.md` Parte C. La API no arranca sin `JWT_SECRET_KEY` y `ACCESS_TOKEN_EXPIRE_MINUTES` (en el `.env` de la raíz, ignorado por git; nunca en el código). La suite de `services/api` cubre AUTH-01 y comprueba que las rutas de incidentes y proveedores exigen token; un cambio en auth se verifica también en `/docs` (registro → *Authorize* → ruta protegida; sin token → 401). `User`/`Profile` viven solo en TinyDB.

   **Autenticación en el frontend AUTH-02 (`uis/backoffice` y `uis/talent-pipeline-tracker`; `uis/website` sigue público):** contexto en `docs/auth-frontend.md`. Token en `localStorage` (único módulo `lib/auth-token.ts` por app), `Authorization: Bearer` y 401 solo en `lib/api-client.ts`, guard global en el layout raíz (sin middleware ni cookies). Para probar en local: la plataforma en Docker (backoffice en el 3001, que llama a la API por su mismo origen, `/backend`) y, para el tracker (fuera de Docker, en el 3002), `CORS_ALLOWED_ORIGINS=http://localhost:3002` en el `.env` de la raíz. Un cambio de autenticación se verifica también en el navegador (login correcto/incorrecto, registro con 422, perfil, redirección sin token y tras 401, logout). Reglas en el `CLAUDE.md` de cada app y en `uis/talent-pipeline-tracker/SPECS.md` §9.

   **Recuperación y cambio de contraseña AUTH-03 (`services/api` → `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`; vistas en `uis/backoffice` y `uis/talent-pipeline-tracker`):** contexto en `docs/auth-password-reset.md`; contrato en `services/api/SPECS.md` Parte D. Email con Resend por HTTP de la librería estándar (sin SDK); `RESEND_API_KEY`, `EMAIL_FROM` y `PASSWORD_RESET_URL` solo en el `.env` de la raíz (todas o ninguna; con Docker, el enlace va a `http://localhost:3001/reset-password`). La suite de `services/api` no llama nunca a Resend (sender falso). Un cambio aquí se verifica también en el navegador (enlace en `/login`, confirmación de `/forgot-password`, reset con token válido/usado/sin token, cambio con contraseña actual incorrecta) y, con la clave configurada, recibiendo el email real.

   **Gestor centralizado de incidencias (`packages/shared` → `nexova_shared.incidents`, `services/api` → `app/modules/incident_manager/`, `scripts/seed_incidents.py`, `uis/backoffice` → `/incident-manager`; hecho en F1–F6, integrado en `main` con la PR #17):** contexto en `docs/centralized-incident-manager.md`; guía de revisión en `docs/centralized-incident-manager-review.md`. Vocabulario, reglas y mapeo del CSV solo en `nexova_shared` (`test_architecture.py` prohíbe sus literales en `services/api/app`). Además de las validaciones de `packages/shared/` y `services/api/` de la tabla, un cambio en el seed se verifica ejecutándolo dos veces sobre una base temporal con el fixture de aceptación (96 insertadas y luego 0; comando en `services/api/README.md`). Las rutas `/api/incidents…` (contrato en `services/api/SPECS.md` Parte E) validan con **400** propio, no con el 422 del resto de la API; un cambio en ellas se verifica también en `/docs` (*Authorize* → alta → listado con filtros → cambio de estado válido e inválido → `/summary`). Un cambio en `uis/backoffice` → `/incident-manager` se verifica además en el navegador con la API arrancada: alta (validación en cliente sin petición, resalte de `branch`, carga y botón deshabilitado, confirmación y limpieza), filtros y estado vacío, cambio de estado (correcto y rechazado con reversión) y fallo aislado del resumen y del listado. Reglas en `uis/backoffice/CLAUDE.md`.

   **Inventario (Hito 5) (`services/api` → `app/modules/inventory/`, rutas `/inventory/products*` y `/inventory/orders*`):**
   - **Documentación:** contexto en `docs/context-nexova-gestion-inventario-hito-5.md`; contrato, decisiones y esquema en `services/api/SPECS.md` Parte F; guía de revisión en `docs/inventory-review.md`.
   - **Dos bases a propósito:** los usuarios siguen en TinyDB y los activos y las órdenes van a PostgreSQL (Supabase) con SQLModel.
   - **Configuración:** la API no arranca sin `DATABASE_URL` (solo en el `.env` de la raíz; desde el entorno solo `postgresql://` o `postgresql+psycopg2://`).
   - **Tests:** la suite de `services/api` lo cubre con `tests/test_inventory_*.py`, sobre SQLite en memoria o temporal con `PRAGMA foreign_keys=ON`. **Ningún test conecta con Supabase:** lo propio de PostgreSQL (FK, `UNIQUE`, `TIMESTAMPTZ`, sin ENUM, `CHECK`, `FOR UPDATE`, RLS) se comprueba compilando el DDL y la SQL con su dialecto.
   - **Un cambio en el seed** se verifica ejecutándolo dos veces sobre una base de pruebas, nunca sobre la de la demo (la del `.env` de la raíz): con el venv de `services/api` y la `DATABASE_URL` de la base de pruebas exportada solo en esa terminal, `python -m app.modules.inventory.seed --email <usuario>` desde `services/api`: 6/4/3 insertados y luego 0.
   - **Un cambio en las rutas** se verifica también en `/docs`: *Authorize* → `GET /inventory/products` con el neto del seed → entrada → salida válida → salida mayor que el stock (400 con el mensaje literal) → `allocation` sin `assigned_to` (422 en ese campo) → `GET /inventory/orders`.

   **Inventario — frontend (`uis/backoffice` → `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`):**
   - **Documentación:** guía de revisión (arranque, recorrido, trazabilidad, decisiones D1–D10 y lo no verificado) en `docs/inventory-frontend-review.md`; reglas en `uis/backoffice/CLAUDE.md` («Inventario»), no se duplican aquí.
   - **Configuración:** `NEXT_PUBLIC_INVENTORY_API_URL` (con Docker, `/backend`, como `NEXT_PUBLIC_API_URL`; sin reserva entre ellas) en el `.env` de la raíz; tras cambiarla, `docker compose up -d ui`. La API, con `DATABASE_URL` y el seed del inventario.
   - **Validación:** la fila de `uis/backoffice` de la tabla (`tsc`, `lint`, `build`, `node:test` y Jest). Una página nueva del inventario necesita `npx next typegen` antes de `tsc` (rutas tipadas de `PageProps`). Ningún test conecta con la API ni con Supabase.
   - **En el navegador**, con la API arrancada: sin sesión, las 4 páginas llevan a `/login`; Activos con el stock y su nivel; Entrada desde la fila (activo preseleccionado, Oficina de solo lectura, formulario vacío sin petición, confirmación y formulario limpio con el activo del enlace); Salida (Stock actual antes de la cantidad y reactivo al cambiar de activo, advertencia que no bloquea, 400 de stock bajo Cantidad, «Asignado a» solo con Asignación, stock leído de nuevo tras el éxito); Historial (insignias distintas, fecha local, `user_uuid`, sin acciones); API parada → error con «Reintentar»; 375 px sin scroll horizontal.
   - **Datos de la demo:** las entradas y salidas de prueba cambian el neto del seed. Restaurarlo (`TRUNCATE assets, asset_entries, asset_exits RESTART IDENTITY CASCADE` + `seed-inventory`) solo con la confirmación del usuario.

   **Gestión de errores (auditoría transversal, rama `feature/error-handling-audit`):** informe, trazabilidad de los criterios del ticket y guía de verificación en `docs/error-handling-audit.md`. Las reglas viven en cada subproyecto: el 503 `storage_unavailable` en `services/api/SPECS.md` §4–§5, los límites de error y los textos en `uis/backoffice/CLAUDE.md` y en `uis/talent-pipeline-tracker/CLAUDE.md` («Errores»). Un cambio en la gestión de errores de cualquier capa se verifica también con los casos de error de ese documento (§7.4).

   **Caching y optimización (ticket de caching; `services/api` → `app/core/cache.py`, `app/core/timing.py`; `uis/backoffice` → `/suppliers`, `/incidents`):**
   - **Documentación:** informe en `CACHING_REPORT.md`; medición inicial y decisiones D1–D11 en `docs/caching-analysis.md`; contrato en `services/api/SPECS.md` Parte G.
   - **Qué se cachea:** `GET /inventory/products*` (60 s) y `GET /api/incidents` y `/summary` (30 s). La caché vive en memoria y solo es válida con `--workers 1`. Nunca se cachea nada personal en una clave compartida.
   - **Tests:** los cubre la validación de `services/api` de la tabla.
   - **Un cambio en la caché o en una escritura que invalida** se verifica también midiendo con `scripts/bench_reads.py` contra una API de medición con bases de prueba, nunca contra la demo (receta en `docs/caching-analysis.md` §2.4).
   - **Un cambio en la carga diferida o en el memo del backoffice** se verifica con el build de producción: chunks, ausencia de layout shift al abrir el formulario y al mostrar resultados, y `<Profiler>` temporal sin commitear.

   **Telemetría: captura en el frontend + colector stub (ticket de captura; `services/api` → `POST /telemetry/events` y `app/modules/telemetry/`, `uis/backoffice` → `lib/telemetry.ts`):**
   - **Documentación:** plan y esquemas (el contrato) en `docs/telemetry/`; decisiones en `docs/telemetry/capture-analysis.md`; guía de revisión (qué captura cada pieza, recorrido en Network, migración y lo no verificado) en `docs/telemetry/capture-review.md`; contrato del stub en `services/api/SPECS.md` Parte H. Reglas del frontend en `uis/backoffice/CLAUDE.md` («Telemetría»).
   - **Configuración:** `NEXT_PUBLIC_TELEMETRY_ENDPOINT=/backend/telemetry/events` en el `.env` de la raíz (interpolada en `ui` con `:?`). En la API, opcionales: `TELEMETRY_ENDPOINT` (sin uso), `TELEMETRY_SUPPLIER_KEY` (≥ 32; sin ella no hay `supplier_key` ni eventos de entrada), `INVENTORY_DEFAULT_MIN_STOCK` y `TELEMETRY_COST_VARIANCE_*`.
   - **Validación:** las filas de `services/api/`, `uis/backoffice/` y `docs/telemetry/` de la tabla. Un cambio en el plan o en los esquemas se comprueba además con `tests/telemetry-contract.test.mjs` (backoffice) y `tests/test_telemetry_events.py` (API), que comparan el código con el JSON.
   - **Base de datos:** la columna de P3 en una base existente, solo con `python -m app.modules.inventory.migrate` (`--dry-run` primero). Se prueba en un Postgres efímero; **la demo, solo con la confirmación del usuario**.
   - **En el navegador:** el recorrido de Network de `docs/telemetry/capture-review.md` (lotes en `POST /backend/telemetry/events` → 200, beacon al ocultar la pestaña, reintentos con la API parada, ningún dato personal).

   **Telemetría: almacenamiento (ticket de almacenamiento; `services/api` → `app/modules/telemetry/`, tabla `telemetry_events`):**
   - **Documentación:** decisiones en `docs/telemetry/storage-analysis.md`; guía de revisión y recorrido en `docs/telemetry/storage-review.md`; contrato en `services/api/SPECS.md` Parte H (§45 y §47).
   - **`TelemetryEvent` no se modifica:** las reglas del colector viven en `collector.py`. Cualquier cambio en `schemas.py` va por debajo de la clase; lo comprueba el `diff` de `storage-review.md`.
   - **Base de datos:** la tabla solo con `python -m app.modules.telemetry.migrate` (`--dry-run` primero), nunca al arrancar: el stack apunta a la demo. Se prueba en un Postgres efímero **con un rol sin superusuario**; **la demo, solo con la confirmación del usuario**. En la demo, las filas de prueba no se pueden borrar: el lote mixto de `curl`, nunca ahí.
   - **Validación:** las filas de `services/api/` y `docs/telemetry/` de la tabla. Un cambio en el plan o en los esquemas se comprueba además con `tests/test_telemetry_storage.py` (compara `allowlists.py` y `FRONTEND_EVENT_TYPES` con el JSON).
   - **Un cambio en el colector** se verifica también con la receta de `docs/telemetry/storage-review.md` (recorrido real, lote mixto y consultas SQL).

   **Telemetría: reporte técnico (ticket del reporte; `services/telemetry/analysis.py`, `services/api` → `GET /telemetry/report`):**
   - **Documentación:** decisiones en `docs/telemetry/report-analysis.md`; guía de revisión y recorrido en el efímero en `docs/telemetry/report-review.md`; contrato en `services/api/SPECS.md` Parte H (§48).
   - **Solo técnico:** ninguna métrica lee las dimensiones de negocio de `tags` ni carga identificadores.
   - **`services/telemetry/`** es una librería de la API: la imagen la copia junto a `app/` y se importa como `telemetry`. Sus reglas (sin bucles, los 6 pasos, `utc=True` antes del `groupby`) están en `tests/test_telemetry_analysis.py`, no en `test_architecture.py`, que solo mira `app/`.
   - **Dependencia:** `pandas`. Un cambio en `analysis.py` se valida con la fila de `services/api/`; al cambiar `requirements.txt`, `docker compose up -d --build` antes de cargar el código: con `--reload`, la API no arranca sin Pandas en la imagen.
   - **Un cambio en una métrica** se verifica también cuadrándola con `docs/telemetry/report-check.sql` en un Postgres efímero, con `report-seed-ephemeral.sql`. **El seed, nunca en la demo:** la tabla es inmutable.
   - **Dashboard (`uis/backoffice` → `/telemetry`):** la fila de `uis/backoffice`, `npx next typegen` antes de `tsc`, y el navegador (`report-review.md` §9). Reglas en `uis/backoffice/CLAUDE.md`.

   **Pipeline de desempeño de negocio (Data Pipelines, Parte 2; `data/pipelines/pipeline.py`, `data/process/`, `packages/shared` → `nexova_shared.reporting`, `services/reporting/` → `/reporting`):**
   - **Documentación:** diseño en `data/pipelines/PIPELINE_DESIGN.md` (frecuencia y comando en §4.5); decisiones en `docs/reporting/implementation-analysis.md`; guía de revisión (efímero, recorrido de punta a punta y demo) en `docs/reporting/implementation-review.md`; contrato de la API en `services/api/SPECS.md` Parte I.
   - **Dos entornos a propósito:** Prefect solo en el de `data/pipelines`. La API importa únicamente `business_performance.trigger` (librería estándar), y `test_reporting_architecture.py` lo comprueba.
   - **Base:** el script usa `DATABASE_URL` de la terminal o, si falta, la del `.env` de la raíz (**la demo**), e imprime solo el host. El worker la lee del block `Secret`.
   - **Esquema `reporting`:** solo con `python -m business_performance.migrate` (desde `data/pipelines`; `--dry-run` primero). En una base no local hace falta `--allow-demo`, y **en la demo, solo con la confirmación del usuario**. La corrida no tiene guarda: es idempotente y recalculable.
   - **Verificación:** las filas de `data/process/`, `data/pipelines/` y `services/api/` de la tabla (y la de Docker si cambian la imagen o Compose).
   - **Un cambio en la transformación o en la SQL** se cuadra en un Postgres efímero con `docs/reporting/pipeline-seed-ephemeral.sql` y `pipeline-check.sql` (0 diferencias). El seed, nunca en la demo: `telemetry_events` es inmutable.
   - **Un cambio en el disparo o en `/reporting`** se verifica de punta a punta con `docs/reporting/compose-ephemeral.yml` (stack + perfil `pipelines` contra el efímero; usuarios de prueba en una TinyDB temporal del contenedor). El perfil `pipelines` solo arranca con `--profile pipelines`; contra la demo, solo con la confirmación del usuario en el momento.
   - **La demo:** el plan de la parada 4 (fotos, migración con `--allow-demo`, corrida, disparo y qué queda) está en `docs/reporting/implementation-review.md` §6, y se ejecuta solo con la confirmación del usuario. Las fotos y el cuadre se leen con `python -m business_performance.readonly` (transacción de solo lectura que siempre se deshace), nunca con SQL suelta.
   - **Analítica de Prefect** desactivada en todos los modos (`DO_NOT_TRACK=1` y `PREFECT_SERVER_ANALYTICS_ENABLED=false`, en `business_performance/_bootstrap.py`, la imagen y Compose; `tests/test_analytics_off.py`).

   **Directorio de proveedores de Nexova (`services/api` → `/suppliers`, `uis/backoffice` → `/suppliers`):** contexto en `docs/ligthweight-storage-api.md`; contrato en `services/api/SPECS.md` Parte B. La validación de `services/api` de la tabla cubre también los tests de proveedores; además, `docker compose exec api python -m app.seed` debe ejecutarse sin errores y ser idempotente. Un cambio en `/suppliers` se verifica también en el navegador (filtros, alta con 422, tarifa, estado).

2. **Revisar el diff real antes de comitear:** `git status --short` y `git diff --stat`. Confirmar que no se incluyen archivos generados (`node_modules/`, `.next/`, `*.log`, `*.tsbuildinfo`) ni dependencias no autorizadas en ningún `package.json` tocado.

3. **Confirmar fidelidad al contexto de negocio:** ningún dato nuevo sobre Nexova (nombre, cifra, responsable, proceso) queda sin respaldo en `contexts/CONTEXT.md` (si existe localmente), el `README.md` raíz, un documento de contexto de `docs/` o `memory-bank/projectbrief.md` — ver `.agents/rules/nexova-context.md`.

4. **Sincronizar el banco de memoria:** aplicar la skill [`memory-bank-sync`](./.agents/skills/memory-bank-sync/SKILL.md) — actualizar `progress.md` (y `techContext.md`/`projectbrief.md` si corresponde). Sin esto, el banco de memoria queda desactualizado en días y la siguiente sesión de agente vuelve a empezar de cero.

5. **Comitear.** El mensaje de commit y la descripción del PR explican el *por qué*, no solo el *qué* — el *qué* ya lo dice el diff.
