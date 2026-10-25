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
   | `uis/website/` | sin build step — verificación manual/visual |
   | `uis/` (servidor del website en Docker: `serve-website.mjs`) | Desde la raíz, con Node 24: `node --test "uis/tests/*.test.mjs"` |
   | Docker (`uis/Dockerfile`, `services/Dockerfile`, los `.dockerignore`, `docker-compose.yml`, `uis/start.sh`, `services/api/requirements.txt`) | Desde la raíz: `docker compose config --quiet` (nunca sin `--quiet`: imprime los secretos) + `docker compose up -d --build` + las comprobaciones del bloque «Docker» de abajo |
   | `packages/shared/` (Python, `nexova_shared`: validación compartida del CSV de incidentes y del gestor de incidencias) | `python -m unittest discover -s packages/shared/tests -t packages/shared` (desde la raíz, cualquier Python ≥ 3.11). Un cambio aquí afecta al analizador: ejecutar también la fila siguiente y la de `services/api/` |
   | `packages/incident-analyzer/` + `scripts/analyze.py` | `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` (desde la raíz) |
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
   - **Documentación:** brief literal en `docs/inventory-frontend-brief.md`; guía de revisión (arranque, recorrido, trazabilidad, decisiones D1–D10 y lo no verificado) en `docs/inventory-frontend-review.md`; reglas en `uis/backoffice/CLAUDE.md` («Inventario»), no se duplican aquí.
   - **Configuración:** `NEXT_PUBLIC_INVENTORY_API_URL` (con Docker, `/backend`, como `NEXT_PUBLIC_API_URL`; sin reserva entre ellas) en el `.env` de la raíz; tras cambiarla, `docker compose up -d ui`. La API, con `DATABASE_URL` y el seed del inventario.
   - **Validación:** la fila de `uis/backoffice` de la tabla (`tsc`, `lint`, `build`, `node:test` y Jest). Una página nueva del inventario necesita `npx next typegen` antes de `tsc` (rutas tipadas de `PageProps`). Ningún test conecta con la API ni con Supabase.
   - **En el navegador**, con la API arrancada: sin sesión, las 4 páginas llevan a `/login`; Activos con el stock y su nivel; Entrada desde la fila (activo preseleccionado, Oficina de solo lectura, formulario vacío sin petición, confirmación y formulario limpio con el activo del enlace); Salida (Stock actual antes de la cantidad y reactivo al cambiar de activo, advertencia que no bloquea, 400 de stock bajo Cantidad, «Asignado a» solo con Asignación, stock leído de nuevo tras el éxito); Historial (insignias distintas, fecha local, `user_uuid`, sin acciones); API parada → error con «Reintentar»; 375 px sin scroll horizontal.
   - **Datos de la demo:** las entradas y salidas de prueba cambian el neto del seed. Restaurarlo (`TRUNCATE assets, asset_entries, asset_exits RESTART IDENTITY CASCADE` + `seed-inventory`) solo con la confirmación del usuario.

   **Gestión de errores (auditoría transversal, rama `feature/error-handling-audit`):** informe, trazabilidad de los criterios del ticket y guía de verificación en `docs/error-handling-audit.md`. Las reglas viven en cada subproyecto: el 503 `storage_unavailable` en `services/api/SPECS.md` §4–§5, los límites de error y los textos en `uis/backoffice/CLAUDE.md` y en `uis/talent-pipeline-tracker/CLAUDE.md` («Errores»). Un cambio en la gestión de errores de cualquier capa se verifica también con los casos de error de ese documento (§7.4).

   **Directorio de proveedores de Nexova (`services/api` → `/suppliers`, `uis/backoffice` → `/suppliers`):** contexto en `docs/ligthweight-storage-api.md`; contrato en `services/api/SPECS.md` Parte B. La validación de `services/api` de la tabla cubre también los tests de proveedores; además, `docker compose exec api python -m app.seed` debe ejecutarse sin errores y ser idempotente. Un cambio en `/suppliers` se verifica también en el navegador (filtros, alta con 422, tarifa, estado).

2. **Revisar el diff real antes de comitear:** `git status --short` y `git diff --stat`. Confirmar que no se incluyen archivos generados (`node_modules/`, `.next/`, `*.log`, `*.tsbuildinfo`) ni dependencias no autorizadas en ningún `package.json` tocado.

3. **Confirmar fidelidad al contexto de negocio:** ningún dato nuevo sobre Nexova (nombre, cifra, responsable, proceso) queda sin respaldo en `contexts/CONTEXT.md` (si existe localmente), el `README.md` raíz, un documento de contexto de `docs/` o `memory-bank/projectbrief.md` — ver `.agents/rules/nexova-context.md`.

4. **Sincronizar el banco de memoria:** aplicar la skill [`memory-bank-sync`](./.agents/skills/memory-bank-sync/SKILL.md) — actualizar `progress.md` (y `techContext.md`/`projectbrief.md` si corresponde). Sin esto, el banco de memoria queda desactualizado en días y la siguiente sesión de agente vuelve a empezar de cero.

5. **Comitear.** El mensaje de commit y la descripción del PR explican el *por qué*, no solo el *qué* — el *qué* ya lo dice el diff.
