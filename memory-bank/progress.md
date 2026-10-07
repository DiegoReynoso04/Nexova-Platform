# Progress — Nexova Monorepo

Estado vivo del proyecto. Cada entrada nueva se añade **arriba**, con fecha, y se corrige (no solo se acumula) si contradice el estado actual del repo. Ver skill `.agents/skills/memory-bank-sync/SKILL.md`.

---

## 2026-10-07 — Gestor centralizado de incidencias, F3: seed de datos históricos (`scripts/seed_incidents.py`)

**Estado: hecho, validado y comiteado** (commit de F3), en `feature/centralized-incident-manager`, después de F2 (`959a65b`). Sin rutas HTTP (F4) y sin tocar `uis/`.

**Qué se hizo:**
- **`scripts/seed_incidents.py`**, capa fina:
  - `nexova_shared.incidents.prepare_seed_batch` lee el CSV con el lector y el esquema del analizador, aplica las 7 reglas y el mapeo;
  - `IncidentRepository.seed` inserta solo lo nuevo (idempotente por el SHA-256 de la clave de origen).
- **Argumentos:**
  - el CSV es opcional; por defecto `data/raw/incidents/incidents-nexova.csv`;
  - `--db`, opcional; por defecto `INCIDENTS_DB_PATH` o `services/api/data/incidents.json`.
- **Informe final en español**, como el seeder de proveedores: filas leídas, insertadas, ya existentes, inválidas (fila + códigos de regla), no mapeables (fila + motivo), duplicadas en el archivo (fila) y total en la base. Nunca contenido de las filas.
- **Códigos de salida:** `1` si el CSV no existe, no es UTF-8 o su cabecera no tiene las columnas del analizador (no se crea la base); `2` si fallan los argumentos, la configuración o el entorno (sin el venv).
- **Entorno:** se ejecuta con el venv de `services/api`. Si `nexova_shared` o `app` no están instalados, añade sus carpetas del monorepo a `sys.path`, como `scripts/analyze.py`.
- **Tests:** `services/api/tests/test_incident_manager_seed.py` (14 tests).
- **Docs:**
  - `services/api/README.md`: sección del gestor, con el comando exacto del seed con el fixture sintético (Windows y Linux/macOS, verificado en PowerShell), tabla de tests y estructura;
  - `scripts/README.md` y `README.es.md`: tabla de scripts;
  - `AGENTS.md` §4: párrafo del gestor (el seed se verifica ejecutándolo dos veces sobre una base temporal).

**Validación ejecutada (base temporal fuera del repo, en el scratchpad de la sesión):**
- 1.ª ejecución con el fixture de aceptación: 100 filas; 96 insertadas; 4 inválidas (filas 18 `missing_client_company`, 45 `invalid_category`, 71 `invalid_email`, 93 `closed_without_score`); 0 no mapeables; 0 duplicadas; total 96; exit 0.
- 2.ª ejecución: 0 insertadas, 96 ya existentes, total 96; exit 0.
- Resumen del repositorio: open 27 / in_progress 0 / resolved 56 / discarded 13; technical_failure 49 / process_error 35 / client_complaint 12 y el resto de categorías 0; customer 96 (branch e internal 0); central 96 (resto de sedes 0).
- En el archivo de la base hay 0 apariciones de `@`, `ticket_id`, `NXV-`, `example.invalid` y `AGT-`.
- CSV inexistente → exit 1; cabecera de otro esquema → exit 1 (`missing required columns`).
- Suites: `services/api` 246 OK (232 + 14); `packages/shared` 72; analizador 118 (7 skipped); `src/` 97.

**Aviso:** en Git Bash, con la salida redirigida, las tildes del informe se ven mal, porque Python escribe en cp1252 y la terminal lee UTF-8. En PowerShell se ven bien. No se cambió la codificación de salida.

---

## 2026-10-07 — Gestor centralizado de incidencias, F2: modelo y repositorio TinyDB (`services/api`)

**Estado: hecho, validado y comiteado** (commit de F2), en `feature/centralized-incident-manager`, después del commit de F1 (`164a183`). Sin rutas HTTP todavía (F4) y sin tocar `uis/`.

**Cambio de decisión del usuario sobre P4-5 (2026-10-07):** `seed_keys` guarda el **SHA-256** de la clave de origen, no el `ticket_id` en claro, porque el CONTEXT dice que `ticket_id` no se almacena. Se aplica en `nexova_shared.incidents.source_key`, que ahora devuelve directamente el SHA-256 en hexadecimal de `ticket_id:<id>` o, si falta, de `title_created_at:<title>\n<created_at ISO>`. Así ningún objeto en memoria lleva la clave en claro. Cubierto con 3 tests nuevos en `packages/shared/tests/test_csv_mapping.py` y con uno del repositorio que busca `NXV-`, `ticket_id` y `@` en el archivo de la base.

**Qué se hizo:**
- **`app/modules/incident_manager/`:**
  - `models.py`: `Incident` (id UUID, enums de `nexova_shared`, fechas `AwareDatetime`) e `IncidentSummary` (`total` + `by_status`/`by_category`/`by_origin`/`by_branch` con todas las claves);
  - `repository.py` (`IncidentRepository`), con el mismo patrón que proveedores (lock, abrir y cerrar por operación, un worker):
    - `find` con filtros combinables (AND), de la más reciente a la más antigua (desempate por `id`);
    - `get`;
    - `create`, a partir de un `IncidentDraft` ya validado; `id` UUID v4 y `created_at` = `updated_at` en UTC;
    - `change_status`, que aplica solo transiciones válidas (`check_transition`; si no, `InvalidStatusTransitionError` sin escribir nada) y actualiza `updated_at`;
    - `summary`;
    - `seed`, idempotente por `seed_keys` (`key_sha256` + `incident_id`), con `updated_at` = `created_at` del CSV y todo en una sola operación.
  - Las lecturas **no crean el archivo**: sin base o con la base vacía devuelven `[]` y totales a cero.
- **Configuración:** `INCIDENTS_DB_PATH` (por defecto `services/api/data/incidents.json`, ignorado por git) en `app/core/config.py`, `.env.example`, README y SPECS §7. `app.modules.incident_manager` añadido a `[tool.setuptools] packages`.
- **`tests/test_architecture.py`:** nueva regla que prohíbe en `app/` cualquier literal del vocabulario del gestor (estados, orígenes, categorías, sedes y etiquetas de sede), salvo `"branch"`, que también es nombre de campo.
- **`tests/test_incident_manager_repository.py`** (26 tests): base inexistente o vacía, creación, filtros, resumen, transiciones (válidas, inválidas, finales), seed idempotente, totales del CONTEXT, privacidad del archivo y configuración.

**Validación ejecutada:** `services/api` 232 OK (205 + 26 del repositorio + 1 de arquitectura); `packages/shared` 72 OK (70 + 2 netos del cambio de P4-5); analizador 118 OK (7 skipped); `src/` 97 OK.

---

## 2026-10-07 — Gestor centralizado de incidencias, F1: validación compartida en `packages/shared`

**Estado: hecho, validado y comiteado** (commit de F1, tras el visto bueno del usuario), en la rama `feature/centralized-incident-manager` (creada desde `main` en `677e735`, merge de la PR #16). Contexto: [`docs/centralized-incident-manager.md`](../docs/centralized-incident-manager.md) (CONTEXT del proyecto, versionado en esta fase) + enunciado del proyecto (pegado por el usuario; exige `scripts/seed_incidents.py`, `packages/shared/`, endpoints `/api/incidents…` y UI de registro, listado y resumen).

**Decisiones del usuario sobre el plan (2026-10-07):**
- P4-1 (a): mover la validación a `packages/shared` y dejar el analizador como fachada.
- P4-2: 400 solo en las rutas nuevas, con una lista de errores `{field, error, message}`; un JSON mal formado también devuelve 400.
- P4-3: router aparte con id UUID (convertidor `{incident_id:uuid}`), para conservar el 405 de `GET /api/incidents/analyze`.
- P4-4: TinyDB + Pydantic.
- P4-5 (a): tabla `seed_keys` (clave `ticket_id` o `title + created_at`), fuera del modelo.
- P4-6: CSV por argumento, por defecto `data/raw/incidents/incidents-nexova.csv`, ejecutado con el venv de `services/api`; el README tendrá el comando exacto con el fixture sintético.
- P4-7: `/incident-manager` y `/incident-manager/new` en `uis/backoffice`, reutilizando `services/api`; autorizado ampliar el alcance de `uis/backoffice/CLAUDE.md`.
- P4-8: estado en solo lectura como `open`; `title` ≤ 120; `description` sin máximo.
- P4-9: JWT sin roles. P4-10: solo transiciones válidas en el listado. P4-11: valores literales, con etiquetas solo para `branch`. P4-12 y P4-13 aceptadas.

**Qué se hizo:**
- **`packages/shared/` (nuevo paquete Python `nexova_shared`, solo librería estándar):**
  - `incident_csv/`: `schema.py`, `reader.py` y `validation.py` movidos desde el analizador sin cambios de comportamiento (`SCORE_LABELS` se queda en el analizador);
  - `incidents/vocabulary.py`: enums y etiquetas de sede del CONTEXT, `TITLE_MAX_LENGTH` = 120;
  - `incidents/rules.py`: `validate_incident_fields` y ciclo de vida;
  - `incidents/csv_mapping.py`: mapeos, título, fecha a medianoche UTC, `customer`/`central`, clave de idempotencia y `prepare_seed_batch` (cargable / inválida / no mapeable / duplicada);
  - `pyproject.toml` y `README.md` propios.
- **`packages/incident-analyzer`:** `schema.py`, `reader.py` y `validation.py` pasan a reexportar desde `nexova_shared`; `__init__.py` añade `packages/shared` a `sys.path` si no está instalado. **Ningún test del analizador se modificó.**
- **Docs:** `AGENTS.md` §4 (fila nueva de `packages/shared`), README del analizador y de `services/api` (instalación con tres paquetes), `services/api/SPECS.md` §1 (dónde viven esquema y reglas), `techContext.md` (inventario, decisión nueva, comando del venv) y `projectbrief.md` (proyecto nuevo, en curso).
- **Corrección del memory-bank:** las menciones de "PR #16 abierta / sin merge" pasan a "integrada en `main`, merge `677e735` (2026-10-07)", y el estado verificado de `origin/main` pasa de `98c8ad2` a `677e735`.
- Sin dependencias nuevas; `services/api/app` y `uis/` no se tocaron.

**Validación ejecutada:**
- Línea base antes del cambio: analizador 118 tests OK (7 skipped: aceptación con el CSV real, ausente); `services/api` 205 OK; `src/` (`npm run check`) 97 OK.
- Después del cambio: analizador 118 OK (7 skipped), igual; `packages/shared` 70 OK (nuevos); `services/api` 205 OK con `nexova_shared` instalado en el venv; `src/` no se tocó.
- Salida de `scripts/analyze.py` idéntica byte a byte antes y después (reporte del fixture de aceptación y del de 13 filas, y `results.csv` exportado).
- `test_contract.py` lee las tablas del CONTEXT; una mutación de prueba (cambiar una etiqueta de sede) lo hace fallar.
- Con el fixture sintético de aceptación: 96 válidas → open 27 / resolved 56 / discarded 13 y technical_failure 49 / process_error 35 / client_complaint 12, como el CONTEXT.

**Pendiente / no verificado:**
- El CSV real (`incidents-nexova.csv`) no está en el checkout: las cifras se verifican con el fixture sintético.
- El fixture no tiene descripciones de más de 120 caracteres; el recorte se cubre con tests unitarios.
- F2–F6 sin empezar en el momento del commit de F1.

---

## 2026-10-06 — AUTH-03: documentación para revisión (guía para el profesor)

**Estado: hecho** (solo documental, sin impacto técnico en el código), sin commit todavía, en la rama `feature/password-reset` (después del commit `cb9d0d5`). Se comiteó en `2a1926a` dentro de la PR #16, integrada en `main` (merge `677e735`, 2026-10-07).

- **`docs/auth-password-reset.md` es ahora el documento principal de AUTH-03.** Se amplía con:
  - endpoints (propósito, autenticación, request, respuesta, errores y seguridad);
  - funcionamiento técnico;
  - sección propia de **H-1** con prueba manual en PowerShell (datos ficticios);
  - puesta en marcha (API con `uv run --env-file .env uvicorn app.main:create_app --factory`, backoffice en 3000 y tracker en 3001);
  - variables de entorno, sin valores;
  - guía de validación manual paso a paso;
  - Resend sin dominio propio (`onboarding@resend.dev` y el destinatario de pruebas `delivered@resend.dev`);
  - resumen de la auditoría de seguridad;
  - comandos exactos de los tests, verificados;
  - estado de la validación manual y deuda técnica.
- **Enlaces añadidos** desde el README de `services/api` y desde `docs/local-development.md`.
- **Referencias corregidas:** "D-PWD-1…11" pasa a "D-PWD-1…12" en el README de la API, `docs/auth-password-reset.md` y `techContext.md`.
- **Validación manual informada por el usuario,** además de la de la entrada de abajo:
  - integración con Resend usando el destinatario de pruebas;
  - H-1 probado a mano: `PUT /users/{id}` con `password` → 403 y la contraseña no cambió;
  - frontend del backoffice;
  - frontend del tracker: `/forgot-password`, envío a Resend, mensaje genérico, botón desactivado tras enviar y `/reset-password`.
- **Comandos de test comprobados al documentarlos:**
  - `test_password_reset.py`: 33 OK;
  - H-1 con `-k`: 6 OK;
  - `password.service.test.mjs` del backoffice: 15 OK;
  - `password.test.mjs` del tracker: 15 OK.

---

## 2026-10-06 — AUTH-03: validación manual con email real, auditoría de seguridad y corrección H-1

**Estado: hecho** en la rama `feature/password-reset`; se comiteó después en `cb9d0d5` (PR #16). Continúa la entrada del 2026-10-05 de abajo.

- **Validación manual del usuario, de extremo a extremo:**
  - `forgot-password` devuelve 200 sin revelar si el usuario existe;
  - el email real llega por Resend;
  - `reset-password` funciona y el token caduca y es de un solo uso (reutilizarlo da error);
  - `change-password` rechaza una contraseña actual incorrecta y funciona con la correcta.
- **Diagnóstico previo:** un `forgot-password` sin email era correcto, porque el email probado no estaba registrado en `services/api/data/auth.json`. La auditoría lo registró como `reset_requested` / `unknown_email` y por diseño no se llama a Resend.
- **Auditoría de seguridad de AUTH-03 (solo lectura):** sin hallazgos CRITICAL y con un HIGH (**H-1**).
  - H-1: `PUT /users/{id}` permitía a un usuario normal cambiar su `password` sin la contraseña actual, esquivando `POST /auth/change-password`. Venía de AUTH-01 (D-AUTH-13).
  - Hallazgos no bloqueantes, **sin corregir**:
    - M-1: restablecer o cambiar la contraseña no cierra las sesiones JWT abiertas;
    - M-2: diferencia de tiempo en `forgot-password` entre email existente y desconocido;
    - M-3: escrituras sin autenticación ni rate limiting en `auth.json`;
    - L-1…L-6: ver la sección "Decisiones y problemas conocidos".
- **H-1 corregido:**
  - `app/routes/users.py`, `update_user`: si quien no es admin envía `password`, responde 403 `forbidden` y no aplica ningún campo de la petición, igual que con `role`;
  - el cambio de contraseña de los usuarios normales va exclusivamente por `POST /auth/change-password`;
  - un admin conserva la capacidad de AUTH-01 de fijar contraseñas con `PUT /users/{id}`.
- **Tests de `tests/test_auth.py`:**
  - el antiguo [18] (`test_user_updates_own_email_and_password`) pasa a ser `test_user_updates_own_email`, porque exigía justo el comportamiento eliminado;
  - 5 tests nuevos: usuario y manager rechazados, cambio de otro usuario rechazado, admin conserva la capacidad, y `change-password` sigue siendo el camino (400 con la actual incorrecta, 200 con la correcta).
- **Resultado:** `services/api` pasa 205 tests (200 + 5).
- **Docs:** D-AUTH-13, §18 y §21 de `services/api/SPECS.md` actualizados; D-PWD-12 y el riesgo residual en §27 nuevos; tabla de endpoints y sección AUTH-03 del README de la API.

**Pendiente:**
- Revisión de P3-1…P3-6 por el tech lead o la CTO.
- Decisión sobre M-1, M-2 y M-3.
- Riesgo residual de H-1 (SPECS §27): un admin puede fijar contraseñas con `PUT /users/{id}` sin la actual, también la suya; ese cambio no invalida enlaces de reset pendientes ni queda en `password_audit`.
- ~~Commit y PR~~: hecho, commit `cb9d0d5` y PR #16, integrada en `main` (merge `677e735`, 2026-10-07).

---

## 2026-10-05 — AUTH-03: recuperación y cambio de contraseña (`services/api`, `uis/backoffice`, `uis/talent-pipeline-tracker`)

**Estado: hecho y validado automáticamente; validación manual con email real completada el 2026-10-06 (entrada de arriba).** Rama `feature/password-reset` (creada desde `main` en `87a7047`, merge de la PR #15), sin commit todavía. Contexto: ticket AUTH-03 ([`docs/auth-password-reset.md`](../docs/auth-password-reset.md)); contrato en `services/api/SPECS.md` Parte D.

**Decisiones del usuario:** Resend como proveedor, llamado por HTTP con la librería estándar (sin dependencias nuevas); flujos en backoffice y tracker; de los opcionales, solo la auditoría. Las decisiones técnicas son D-PWD-1…11 (SPECS §24); las decisiones de implementación que el ticket no fija son **propuestas pendientes de revisión** P3-1…P3-6 (`docs/auth-password-reset.md` §4).

**Qué se hizo:**
- **`services/api`:** `POST /auth/forgot-password` (siempre 200 con el mismo cuerpo; email en segundo plano), `POST /auth/reset-password` (400 `invalid_reset_token`), `POST /auth/change-password` (protegido; 400 `incorrect_password`). Token opaco de 256 bits guardado solo como SHA-256 en la tabla `password_reset_tokens` de `auth.json`, vigencia 15–60 min (30 por defecto), un solo uso. Auditoría en `password_audit` (evento, `user_id`, IP, motivo, fecha; sin email ni token). Envío con `app/auth/email.py` (Resend por `urllib`). Nuevas variables `RESEND_API_KEY`, `EMAIL_FROM`, `PASSWORD_RESET_URL` (todas o ninguna) y `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`; `.env.example` y README actualizados.
- **Backoffice y tracker:** `/forgot-password` (pública), `/reset-password` (abierta, con o sin sesión), `/account/change-password` (protegida), enlace "¿Olvidaste tu contraseña?" en `/login`, aviso tras `?reset=success` y enlace a cambiar contraseña desde el perfil. Sin dependencias nuevas.
- **Docs:** `docs/auth-password-reset.md` (nuevo); `services/api/SPECS.md` Parte D; READMEs de API, backoffice y tracker; `SPECS.md` §9.4, `CLAUDE.md` de las dos apps; `docs/local-development.md`; `AGENTS.md` §4; `uis/README*.md`; `.agents/rules/app-specific-overrides.md`; `techContext.md`.

**Validación ejecutada:**
- `services/api`: 200 tests OK (167 anteriores + 33 nuevos en `tests/test_password_reset.py`; ninguno llama a Resend). Prueba de humo contra un uvicorn real (puerto 8010, base temporal fuera del repo): 18/18, incluido el preflight CORS desde 3000 y 3001 de las tres rutas.
- `uis/backoffice`: `tsc`, `lint` y `build` OK (rutas nuevas estáticas); 263 tests OK (240 + 23 nuevos en `tests/password.service.test.mjs`; ajustados los tests de rutas y el estático de producción).
- `uis/talent-pipeline-tracker`: `tsc` y `build` OK; 35 tests OK (20 + 15 en `tests/password.test.mjs`); `lint` solo con los 4 errores preexistentes.
- Navegador (servidores de desarrollo del usuario, sin enviar formularios): enlace en `/login` de las dos apps, `/forgot-password`, `/reset-password` sin token (error y enlace) y con token (formulario; el token desaparece de la URL; `referrer: no-referrer`), aviso en `/login?reset=success`. Sin errores de consola.

**Pendiente / no verificado:**
- ~~Email real con Resend~~ y ~~flujo completo en el navegador contra la API nueva~~: **hechos el 2026-10-06** (entrada de arriba).
- Revisión de P3-1…P3-6 por el tech lead o la CTO.
- Fuera de alcance (SPECS §27): cerrar sesiones abiertas al cambiar la contraseña, rate limiting, plantilla HTML, retención de la auditoría.

---

## 2026-10-05 — Validación manual de la exportación autenticada de `/incidents` y deuda de `LastResultStore`

**Estado: hecho** (solo documental, sin impacto técnico en el código). Se registra la validación manual del usuario en el navegador (backoffice en `http://localhost:3000`, API en `http://localhost:8000`): la exportación de `/incidents` con token funciona y una sesión inválida durante la exportación lleva a `/login` (detalle en la entrada de AUTH-02, "Validación ejecutada"). Se retira ese pendiente de AUTH-02. Se registra también como deuda pendiente, **sin corregir**, que `LastResultStore` es global al proceso y no por usuario (ver "Decisiones y problemas conocidos"). Rama `docs/auth02-export-validation`, creada desde `main` en `98c8ad2` (merge de la PR #14).

---

## 2026-10-05 — Memory-bank tras el merge de AUTH-02 (PR #13)

**Estado: hecho** (solo documental, sin impacto técnico en el código). AUTH-02 se integró en `main` con la PR #13 (commit `e2d4cbd`, merge `a4b6369`, 2026-10-05; `git diff e2d4cbd a4b6369` vacío). Se corrigen las menciones de "PR abierto" / "no está en `main`" en `techContext.md` y en la entrada de AUTH-02 de abajo, se retira el pendiente "merge del PR" y se actualiza el próximo paso de AUTH-01 (enviar el token desde el backoffice ya lo resolvió AUTH-02). `docs/auth-frontend.md` §3 deja constancia de que el merge **no** aprueba P-1…P-7: siguen pendientes de revisión del tech lead o la CTO. Rama `chore/memory-bank-auth-frontend-merged`, creada desde `main` en `a4b6369`.

---

## 2026-10-02 / 2026-10-05 — AUTH-02: autenticación en el frontend (`uis/backoffice`, `uis/talent-pipeline-tracker`, CORS de `services/api`)

**Estado: hecho, validado (automático y manual) e integrado en `main`** con la PR #13 (rama `feature/auth-frontend`, creada desde `main` en `7815e26`; commit `e2d4cbd`, merge `a4b6369`, 2026-10-05). Pendiente: revisión de P-1…P-7 por el tech lead o la CTO (el merge no las aprueba). `docs/auth-frontend.md` separa requisitos del ticket, hechos comprobados y **propuestas pendientes de revisión** (P-1…P-7: puerto 3001, `NEXT_PUBLIC_AUTH_API_URL`, validación con `GET /auth/me`, `null` en el perfil, CORS, destino tras login y email en cabecera, sin refresh tokens); ninguna está aprobada por el tech lead ni por la CTO.

**Estado real tras AUTH-02 (hechos comprobados):**
- AUTH-01 (backend) ya existía: `services/api` emite el JWT y lo exige en incidentes, proveedores, `/users`, `/auth/me` y `/profiles/me`.
- Backoffice y tracker integran login, registro, perfil y logout; todas sus vistas salvo `/login` y `/register` exigen sesión mediante un guard en cliente en el layout raíz (sin middleware de Next.js y sin cookies).
- JWT en `localStorage` (`nexova.backoffice.access_token` / `nexova.tracker.access_token`); `Authorization: Bearer` solo en `lib/api-client.ts` de cada app. Un 401 borra el token y lleva a `/login`. Sin refresh tokens.
- Contrato usado: `POST /auth/login` con `application/x-www-form-urlencoded` (`username` = email); `POST /users` sin `role`; `GET /auth/me` valida la sesión (una vez por token); `PUT /profiles/me` edita nombre, teléfono y dirección (`null` borra el dato).
- Tracker: `NEXT_PUBLIC_AUTH_API_URL` apunta a `services/api`; `NEXT_PUBLIC_API_URL` sigue siendo la API de 4Geeks, que **nunca** recibe el JWT. Puerto 3001.
- CORS: la API permite `PUT`; en desarrollo `CORS_ALLOWED_ORIGINS` debe incluir `http://localhost:3001` (documentado en `services/api/.env.example`); el `.env` local con los valores reales **no se versiona**.
- `uis/website` sigue público, sin cambios y fuera del sistema de autenticación.
- Guía de arranque del sistema completo: [`docs/local-development.md`](../docs/local-development.md) (nueva, 2026-10-05).

Contexto: ticket AUTH-02 ([`docs/auth-frontend.md`](../docs/auth-frontend.md)): la API ya exige JWT (AUTH-01) y el frontend debe hacer login/registro, guardar el token en `localStorage`, enviarlo como `Authorization: Bearer`, tener página de perfil y proteger todas las vistas de las apps del monorepo salvo el website público. Termina la rotura temporal de `/incidents` y `/suppliers` (401) de AUTH-01.

**Qué se hizo:**
- **Backoffice:** `/login`, `/register` (`POST /users` + `POST /auth/login`), `/account/profile` (`GET /auth/me` + `PUT /profiles/me`); guard global y sesión en el layout raíz; cabecera con perfil, email y "Cerrar sesión"; cliente HTTP con Bearer y 401 centralizados; `session_expired` en los errores de incidentes y proveedores.
- **Tracker:** mismos flujos contra `services/api` (`authApiClient`); la API de 4Geeks no recibe el token; cabecera nueva; puerto 3001; variable `NEXT_PUBLIC_AUTH_API_URL`.
- **`services/api`:** CORS permite `PUT`; `.env.example` añade el origen `http://localhost:3001`; test de CORS actualizado (+1 test de preflight `PUT /profiles/me`).
- **Docs:** `docs/auth-frontend.md` y `docs/local-development.md` (nuevos); `uis/README.md`/`README.es.md` (estado de las apps y enlace a la guía); `CLAUDE.md`/`README.md` del backoffice; `SPECS.md` §9, `CLAUDE.md` y `README.md` del tracker; `SPECS.md` (D-AUTH-12, §22), `README.md` y `.env.example` de `services/api`; `AGENTS.md` §4; `.agents/rules/app-specific-overrides.md`; `techContext.md`.

**Validación ejecutada:**
- `uis/backoffice`: `tsc`, `lint` y `build` OK (rutas nuevas `/login`, `/register`, `/account/profile`); 240 tests OK (172 anteriores + 68 nuevos). Dos tests existentes ajustados porque el contrato cambió a propósito: el 401 de una petición protegida ya no llega al servicio (se mantiene la comprobación de que no se filtra el cuerpo).
- `uis/talent-pipeline-tracker`: `tsc` y `build` OK; 20 tests nuevos OK (3 de ellos, 2026-10-05, cubren el flujo login → token → `/auth/me` y el caso de respuesta bloqueada por CORS); `lint` con 4 errores `react-hooks/set-state-in-effect` **anteriores** a AUTH-02 (`use-notes`, `use-record-detail`, `use-records`, sin cambios en esta rama).
- `services/api`: 167 tests OK (166 anteriores + 1 nuevo de preflight `PUT`).
- `src/` 97 tests OK y `packages/incident-analyzer` 118 OK (7 omitidos), sin cambios en esta rama.
- Validación manual del usuario (2026-10-05): backoffice (login correcto e incorrecto, registro, perfil GET/PUT, logout, protección de rutas, botón atrás tras logout, token inválido/401); tracker (protección de `/`, login, JWT en `localStorage`, acceso autenticado, candidaturas de 4Geeks); website como HTML estático público.
- Navegador, con la API real (uvicorn, TinyDB temporal fuera del repo, orígenes 3000 y 3001): sin token → `/login`; registro con 422 por campo y después correcto (token + `/`); `/suppliers` (15 filas) e `/incidents` (análisis del CSV sintético) con Bearer; perfil leído y editado con `PUT /profiles/me`; token inválido → 401 → token borrado y `/login`; login incorrecto → mensaje y sin token; `/login` con sesión → `/`; logout → `/login` y vistas protegidas inaccesibles. Tracker: `/` sin sesión → `/login` sin llamar a 4Geeks, login incorrecto/correcto, listado de candidaturas, perfil (borrar teléfono → `null`), logout y `/candidates/[id]` protegido.
- Exportación autenticada de `/incidents` (validación manual del usuario, 2026-10-05, tras el merge): con sesión válida, análisis de `packages/incident-analyzer/tests/fixtures/incidents-acceptance-synthetic.csv` → "Exportar" → `GET /api/incidents/results/export` 200 → descarga de `results.csv` con `total_records,100`, `valid_records,96`, `invalid_records,4` y `satisfaction_average_score,3.84` (las cifras de `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`, que el fixture sintético reproduce; no es una verificación con el CSV real). Con `nexova.backoffice.access_token` sustituido por un valor inválido, la exportación detecta la sesión inválida y la app cierra la sesión y redirige a `/login`.

**Pendiente / no verificado / problemas preexistentes:**
- Revisión de las propuestas P-1…P-7 por el tech lead o la CTO: siguen pendientes después del merge.
- Preexistente (también en `main`): 4 errores de lint `react-hooks/set-state-in-effect` en el tracker (`use-notes.ts:63`, `use-record-detail.ts:58`, `use-records.ts:75` y `:112`); AUTH-02 no los introduce ni los corrige.
- Preexistente: `npx tsc --noEmit` en las apps Next.js falla sin `.next/` (`LayoutProps`/`PageProps` los genera Next); ejecutar antes `npm run build`.
- Registro desde la UI del tracker (mismo servicio y flujo probados en tests y en el backoffice).
- Quien tenga un `services/api/.env` anterior debe añadir `http://localhost:3001` a `CORS_ALLOWED_ORIGINS` para usar el tracker, y el `.env.local` del tracker necesita `NEXT_PUBLIC_AUTH_API_URL`.
  *Confirmado el 2026-10-05:* con el `.env` local solo en `http://localhost:3000`, el login del tracker devolvía 200 en la red pero el navegador bloqueaba la respuesta (petición CORS simple, sin preflight): `fetch` fallaba, el tracker mostraba "No se pudo conectar con el servidor" y no se guardaba el token. Corregido en el `.env` local (no versionado); `tests/auth.test.mjs` del tracker cubre ahora ese caso y el flujo login → token → `/auth/me` → vista autenticada.
- Sin refresh tokens: al expirar el JWT se vuelve a `/login` (fuera de alcance, igual que en AUTH-01).

---

## 2026-09-30 — README de `services/api`: tests con uv y sincronización del venv

**Estado: hecho** (solo documental, sin impacto en el código). El README decía que `uv run` conserva siempre el núcleo `incident-analyzer` instalado con pip, pero `uv run --extra dev …` lo desinstaló al sincronizar el `.venv`. Se corrige la sección del seeder (qué comandos lo conservaron, `--no-sync` y cómo reinstalarlo) y se añade a la sección de tests el comando con uv (`uv run --no-sync python -m unittest discover -s tests -t .`) y la aclaración de que no hay pytest (D-API-3). Mismo ajuste en `techContext.md`. Rama `docs/api-readme-uv-tests`, creada desde `chore/memory-bank-auth-merged` (PR #11) para no chocar en `progress.md`.

---

## 2026-09-30 — Repositorio renombrado a `nexova-platform` y memory-bank tras el merge de AUTH-01

**Estado: hecho** (solo documental, sin impacto técnico en el código). El repositorio de GitHub pasa de `Milestone-0-Elige-tu-empresa` a `nexova-platform` (detalle en `techContext.md`, "Estado real en `main`"); ningún archivo versionado citaba el nombre antiguo. Se actualizan las menciones de AUTH-01 de "pendiente de merge" a integrado con el PR #10. Rama `chore/memory-bank-auth-merged`, creada desde `main` en `09b86f1`.

---

## 2026-09-30 — AUTH-01: autenticación JWT y protección de rutas (`services/api`)

**Estado: hecho — validado por el tech lead (pruebas en `/docs` y desde el origen del backoffice) y commiteado en la rama `feature/auth-api`** (creada desde `api-con-almacenamiento-ligero` en `9988355`, mismo árbol que el merge del PR #9 en `main`). Integrado en `main` con el PR #10 (mergeado el 2026-09-30 21:50 UTC, merge `09b86f1`). El frontend queda fuera de alcance por el propio ticket (se actualizará para enviar el token en una fase posterior).

Contexto: ticket AUTH-01 (`docs/auth-api.md`): la CTO exige que ninguna ruta que modifique o exponga datos sensibles sea accesible sin sesión válida. Decisiones D-AUTH-1…13 en `services/api/SPECS.md` Parte C (§15–§22), fijadas por el tech lead el 2026-09-30.

**Qué se hizo:** paquete `app/auth/` (modelos `User`/`Profile`, `AuthRepository` TinyDB en `AUTH_DB_PATH` con ids UUID, bcrypt con libpass, JWT HS256 con python-jose, `UserService`, `get_current_user`/`require_admin`/`ensure_self_or_admin`, comando `uv run create-admin`); rutas `app/routes/{auth,users,profiles}.py`; las 8 rutas existentes (6 de `/suppliers`, 2 de `/api/incidents`) protegidas a nivel de router; `JWT_SECRET_KEY` (≥ 32 caracteres) y `ACCESS_TOKEN_EXPIRE_MINUTES` obligatorias al arrancar (sin valor por defecto); CORS `allow_headers=["Authorization"]`.
**Archivos añadidos:** `docs/auth-api.md`; `services/api/app/auth/{__init__,models,repository,security,service,dependencies,create_admin}.py`; `services/api/app/routes/{auth,users,profiles}.py`; `services/api/tests/{auth_support,test_auth,test_auth_protection,test_create_admin}.py`.
**Archivos modificados:** `services/api/{app/main.py,app/core/config.py,app/core/errors.py,pyproject.toml,uv.lock,.env.example,README.md,SPECS.md}`; `services/api/tests/{support,suppliers_support,test_architecture}.py` (clientes de test con JWT válido; excepción documentada de `"@"` y `print`); `.gitignore` (`.env.*` salvo `.env.example`); `AGENTS.md` §4; `services/README*.md`; `memory-bank/{progress,techContext}.md`.
**Dependencias:** `libpass[bcrypt]>=1.9.3,<1.10` (bcrypt 5.0.0) y `python-jose[cryptography]>=3.5,<3.6` (3.5.0; arrastra ecdsa, rsa, pyasn1, six y, por el extra, cryptography 50.0.2, cffi, pycparser), autorizadas por el ticket.

**Validación ejecutada:**
- Revisión final (tech lead): `POST /users` ya no acepta `role` (`UserCreate` = `email`, `password`, `name`, `phone`, `address`; `role` → 422) y el backend fija siempre `user`; antes aceptaba `role` y respondía 403 a `admin`/`manager` (no lo exigía ningún contrato). CORS, refresh/revocación de tokens: sin cambios, documentados como fuera de alcance (`SPECS.md` §22).
- `services/api`: 166 tests OK (109 anteriores + 57 de AUTH-01). Mutaciones detectadas: quitar la protección de `/suppliers` (20 fallos) y quitar el control de `role` en `PUT /users/{id}` (4 fallos).
- `packages/incident-analyzer`: sin cambios; ver la validación en el resumen de la tarea.
- Manual con uvicorn real y TinyDB temporal: sin `JWT_SECRET_KEY` la app no arranca (`ConfigError`); flujo registro → login → 401 sin token / token inválido → 200 con token en proveedores e incidentes → `/auth/me` y `/profiles/me` → 403 de A sobre B y al autoelevarse → `create-admin` → admin lista, cambia rol y borra (perfil borrado): 24/24. En `/docs`, el botón *Authorize* hace login en `/auth/login` y `GET /auth/me` responde 200; Swagger marca 15 operaciones protegidas.
- Incidencia durante la validación manual: un `.env` con rutas Windows con `\` no lo interpretó `uv`, y la API usó `services/api/data/` (se añadió un proveedor de prueba y se creó `data/auth.json`); ambos se revirtieron y `.env.example` documenta usar `/` en rutas.

**Pendiente:**
- ~~Revisión del tech lead, commit, PR contra `main` y merge~~ — hecho (PR #10).
- Para ejecutar los tests con uv, desde `services/api`: `uv run --no-sync python -m unittest discover -s tests -t .` (no hay pytest: D-API-3). Sin `--no-sync`, `uv run --extra dev` sincroniza el `.venv` y desinstala el núcleo `incident-analyzer` instalado con pip (se reinstala con `pip install --no-deps -e packages/incident-analyzer`). ~~El README de `services/api` aún dice que `uv run` lo conserva~~ — corregido (entrada "README de `services/api`: tests con uv", 2026-09-30).
- ~~CORS no incluye `PUT`~~ — añadido en AUTH-02 (entrada 2026-10-02).
- ~~El backoffice (`/suppliers`, `/incidents`) responde 401 hasta que envíe el token~~ — resuelto en AUTH-02 (entrada 2026-10-02).
- Sin revocación/refresh de tokens ni forma de desactivar usuarios por API; nada impide que el último admin se degrade o se borre (se recupera con `create-admin`).

---

## 2026-09-29 — Directorio de proveedores: API TinyDB (`services/api`) + vista `/suppliers` (`uis/backoffice`)

**Estado: hecho — revisado por el tech lead y commiteado en la rama `api-con-almacenamiento-ligero` (creada desde `main` tras el PR #7, con `main` fusionado después para incorporar el PR #8). Integrado en `main` con el PR #9 (mergeado el 2026-09-28 23:53 UTC).**

Contexto: `docs/ligthweight-storage-api.md` (Patricia Solís, HR Manager; tech lead Sergio Molina). Sustituir la hoja de cálculo de proveedores por una API con fuente de verdad única. Decisiones D-SUP-1…12 en `services/api/SPECS.md` Parte B (incluida la tensión `DELETE` ↔ suspensión controlada, §10).

**Archivos añadidos:** `docs/ligthweight-storage-api.md` (contexto; solo se actualizaron las 2 líneas de cabecera que citaban el nombre y la ruta antiguos); `services/api/app/{models,database,seed}.py`, `services/api/app/routes/{__init__,suppliers}.py`, `services/api/tests/{suppliers_support,test_suppliers_api,test_suppliers_seed}.py`, `services/api/uv.lock`; `uis/backoffice/app/suppliers/page.tsx`, `components/suppliers/*`, `hooks/use-supplier-directory.ts`, `services/suppliers.service.ts`, `lib/supplier-renewal.ts`, `types/suppliers.ts`, `tests/{suppliers-contract,suppliers.service,use-supplier-directory}.test.mjs`, `tests/support/supplier-fakes.mjs`.
**Archivos modificados:** `services/api/{app/main.py,app/core/config.py,app/core/errors.py,pyproject.toml,README.md,SPECS.md,.env.example,tests/test_architecture.py,tests/test_errors.py}`; `uis/backoffice/{app/layout.tsx,lib/api-client.ts,services/normalizers.ts,tests/production-source.test.mjs,CLAUDE.md,README.md}`; `.gitignore` (`services/api/data/`); `AGENTS.md` §4; `.agents/rules/app-specific-overrides.md`; `services/README*.md`, `uis/README*.md`; `memory-bank/*`.
**Dependencias:** solo `tinydb` (autorizada). Herramienta: uv (instalada en la máquina, no es dependencia del proyecto).

**Validación ejecutada:**
- `services/api`: 109 tests OK (70 de incidentes + 39 de proveedores). `uv run seed` → 15 insertados; segunda ejecución → 0 (también en una copia limpia sin venv).
- `uis/backoffice`: `tsc`, `lint`, `build` (rutas `/`, `/incidents`, `/suppliers`) y 172 tests Node 24 OK. Mutaciones detectadas por los tests (recarga tras cambio de tarifa, 422 por campo).
- Manual en navegador con la API y TinyDB reales: filtros combinados, tarifa 0 bloqueada y 900 guardada con `updated_at` nuevo, suspender sin tocar `updated_at`, alta vacía sin petición, 422 de moneda incoherente, alta con renovación a 20 días destacada, 375 px sin desbordamiento.

**Pendiente:**
- Adjuntar al PR #9 las 3 capturas que pide el brief (`uv run seed`, un filtro en Swagger y el listado filtrado en la UI) — el checklist del PR seguía sin marcar al mergearse. ~~Hacer el merge~~ — hecho el 2026-09-28.
- Desde AUTH-01 (entrada 2026-09-30), `/suppliers` exige JWT; ~~la vista del backoffice recibe 401~~ — resuelto en AUTH-02 (entrada 2026-10-02).
- Ningún proveedor del seed cae en la ventana de 60 días (todas sus fechas ya pasaron): para la demo hay que registrar uno con fecha próxima.
- El 422 de moneda incoherente es un error del proveedor completo (`loc` = `["body"]`): se muestra en el resumen, no marcado en el campo Moneda.

---

## 2026-09-28 — Revisión del memory-bank y de las reglas de agente (sin impacto técnico)

**Estado: hecho** (solo documental: `memory-bank/`, `AGENTS.md`, `CLAUDE.md`, `.agents/`). Se corrigieron afirmaciones desfasadas tras los PRs #4–#7:
- `projectbrief.md`: ya no dice ser el único contexto de negocio versionado (el `README.md` raíz contiene el briefing desde `6807f5e`); la regla de trazabilidad admite también el `README.md` raíz y los documentos de contexto versionados en `docs/`.
- `techContext.md`: "Estado real en `main`" actualizado a PRs #1–#7; origen del backoffice con fecha/PR en vez de "este cambio"; nota del 2026-09-20 marcada como histórica; inventario de `skills/` y `agents/` completado.
- Este archivo: la entrada del fixture sintético indica su merge (PR #7).
- `AGENTS.md` §3 y `.agents/skills/memory-bank-sync/SKILL.md`: la sincronización del memory-bank ya no depende de que haya commit — se aplica al cerrar cualquier tarea que modifique archivos (`progress.md` siempre, `techContext.md`/`projectbrief.md` solo si procede); las tareas de solo lectura no la disparan. Corregida la referencia "`AGENTS.md` (§5)" de la skill (es §4, paso 4). Motivo: una sesión que editaba archivos sin comitear dejaba el memory-bank desfasado.
- `CLAUDE.md` raíz nuevo, con solo `@AGENTS.md`: garantiza que Claude Code cargue `AGENTS.md` en cada sesión sin depender de que lo detecte por su cuenta, y sin duplicar su contenido (mismo patrón que `uis/talent-pipeline-tracker/CLAUDE.md`).

**Verificado al revisar:** núcleo 118 tests OK (7 skipped), API 70 OK, 97 tests en `src/`, versiones de Next/React en ambos `package.json`.

- Resuelto el "Pendiente derivado" de la entrada 2026-09-27: `AGENTS.md` (§1, §3 y §4.3), `.agents/rules/monorepo-structure.md`, `.agents/rules/nexova-context.md` y la skill `memory-bank-sync` ya no remiten a la guía de carpetas del `README.md` raíz ni tratan `projectbrief.md` como única referencia versionada. La convención de carpetas vigente es la tabla de `monorepo-structure.md` (la guía original sigue en `git show fda5125:README.es.md`); las fuentes de negocio son `contexts/CONTEXT.md`, su copia en el `README.md` raíz, los `contexts/hitoN/*.md`, los documentos de contexto de `docs/` y `projectbrief.md`.

---

## 2026-09-27 — Procesador de incidentes: fixture sintético de aceptación

**Estado: hecho, integrado en `main` con el PR #7.** `packages/incident-analyzer/tests/fixtures/incidents-acceptance-synthetic.csv` (100 filas sintéticas, emails `example.invalid`) reproduce exactamente las cifras de `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md` (100/96/4, categorías, estados, satisfacción, media 3.84); lo verifica `tests/test_acceptance_synthetic.py`, que se ejecuta siempre. Documentado en `tests/fixtures/README.md` y en el `README.md` del paquete. **No sustituye** al test con el CSV real (`test_acceptance.py`), que sigue omitido.

**Validación:** `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` → 118 tests OK (7 skipped: aceptación con el CSV real).

---

## 2026-09-27 — `README.md` raíz sustituido por el briefing de Nexova

**Estado: hecho** (cambio del usuario, solo documental). El `README.md` raíz deja de ser la guía de la plantilla de 4Geeks y pasa a ser el briefing de empresa de Nexova (contenido idéntico a `contexts/CONTEXT.md`); se elimina `README.es.md`. Consecuencia: el briefing general ya viaja con el repositorio; `contexts/` sigue ignorado.

**~~Pendiente derivado~~ — resuelto el 2026-09-28 (ver entrada de arriba):** `AGENTS.md` §3 y `.agents/rules/monorepo-structure.md` / `nexova-context.md` aún citan la convención de carpetas o el `CONTEXT.md` "descrito en `README.md` raíz"; la convención sigue en `.agents/rules/monorepo-structure.md` y en el historial (`git show fda5125:README.es.md`).

---

## 2026-09-23 — Procesador de reportes de incidentes, Fase 3: UI `/incidents` en `uis/backoffice`

**Estado: hecha — implementada, validada (pasos 1–6) y aprobada por el tech lead; commiteada en la rama `feature/incident-analyzer` con el mensaje `feat(backoffice): implementa la vista /incidents para el análisis de incidentes Nexova`, sobre la Fase 2 (`4120de5`). Integrada en `main` con el PR #6 (mergeado el 2026-09-23).** Fase 4 (integración) no iniciada.

Contexto: vista web para que Atención al Cliente suba el CSV, vea las métricas y descargue `results.csv`, consumiendo la API de la Fase 2. La UI es decisión del tech lead (H1–H12): el documento de contexto de Nexova describe un script, no una interfaz.

**Pasos:**
1. Preparación: `uis/backoffice/CLAUDE.md` y `README.md` autorizan `/incidents`; `.gitignore` con `!.env.example`; `.env.example` (`NEXT_PUBLIC_API_URL`); tokens semánticos en `globals.css`.
2. Tipos (`types/incidents.ts`) y normalizador (`services/normalizers.ts`, única frontera con `unknown`, whitelist).
3. Cliente HTTP genérico (`lib/api-client.ts`, sin `unknown`: JSON tipado como `JsonValue`) y servicio (`services/incidents.service.ts`).
4. Hook `hooks/use-incident-analysis.ts` (reducer + sesión: cancelación, carreras, exportación ligada al `analysis_id` mostrado).
5. UI: `app/incidents/page.tsx` (Server Component) + `components/incidents/*` + primitivas `components/ui/*` (incl. `nav-link.tsx`) + enlace en la cabecera de `app/layout.tsx`. La portada `app/page.tsx` no cambia.
6. Validación manual en navegador, documentación (`uis/backoffice/README.md`, `CLAUDE.md`, `AGENTS.md` §4, `uis/README*.md`) y este Memory Bank.

**Validación ejecutada:**
- `uis/backoffice`: `npx tsc --noEmit`, `npm run lint`, `npm run build` (rutas `/`, `/_not-found`, `/incidents`, sin `.env.local`) y tests Node 24 (`node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"`) → 115 tests OK. Mutaciones sobre copias en scratchpad detectadas por los tests (privacidad de errores, `unknown`/`any`, carreras del hook, Blob en estado…).
- Manual en navegador, con API local propia y fixture sintético (`example.invalid`), instrumentando `fetch` y `<a>.click()` solo en la página de prueba (sin tocar producción): (A) la descarga se inicia como `results.csv`, contenido `metric,value` que coincide con el análisis mostrado (13 registros, media 3.75), sin `@`, `customer_email` ni datos de filas — el panel del navegador integrado no guarda el archivo en disco, así que el contenido se verificó leyendo el Blob desde el instrumental; (B1) export de A pendiente + análisis B correcto → export abortado, ninguna descarga, se muestra B; (B2) export de A pendiente + B falla → A sigue visible y su export termina y descarga A; (C) salir de `/incidents` con un análisis pendiente → petición abortada antes de enviarse, sin error visible ni descarga. 360 px sin desbordamiento; peticiones solo a `localhost`.
- Hallazgos corregidos durante la validación: botón secundario sin borde visible (clases de color de borde en conflicto) y un segundo landmark `banner` en `/incidents`.

**Pendiente:**
- ~~Push de la rama y PR contra `main`~~ — hecho: PR #6, mergeado el 2026-09-23.
- Fase 4 (integración) no iniciada.
- Test de aceptación con el CSV real (las cifras 100/96/4 siguen sin verificar con datos reales).
- `UiError` no tiene un caso "sin archivo": `analyze()` sin archivo usa `request_invalid` (la UI deshabilita el botón, así que no se alcanza).
- El texto "aproximadamente 1 MiB" de la UI es copy de UX: si se cambia `MAX_UPLOAD_BYTES` en el servidor, hay que actualizarlo (el 413 sigue siendo la fuente de verdad).

---

## 2026-09-23 — Procesador de reportes de incidentes, Fase 2: API HTTP (`services/api/`)

**Estado: hecha — implementada, validada y aprobada por el tech lead tras la code review (veredicto `APROBABLE SIN CAMBIOS`); commiteada en la rama `feature/incident-analyzer` con el mensaje `feat(api): implementa API FastAPI para análisis de incidentes Nexova`, sobre la Fase 1 (`0203023`). Integrada en `main` con el PR #6 (mergeado el 2026-09-23).** Estado de la Fase 3: ver la entrada de arriba.

Contexto: exponer por HTTP el mismo análisis que la CLI para que el backoffice (Fase 3) pueda subir el CSV y descargar la exportación. Diseño aprobado por el tech lead con las decisiones D-API-1…11 (registradas en `services/api/SPECS.md` §2 y en `techContext.md`).

**Contrato:** `POST /api/incidents/analyze` (multipart, campo `file`, `.csv`) → JSON con `analysis_id`, `analyzed_at`, totales, 7 reglas, 5 categorías, 3 estados, satisfacción (decimales como string) e info de exportación; `GET /api/incidents/results/export` → `results.csv` (`metric,value`) del último análisis que terminó correctamente, con `X-Analysis-Id`, 404 `no_analysis` si no hay; ambas respuestas 200 con `Cache-Control: no-store`; `GET /health`. **Procedencia:** las rutas son decisión del tech lead, no del documento de contexto de Nexova (que no define ninguna API).

**Correcciones tras la code review (2026-09-23):**
- El núcleo local ya **no** se declara como dependencia en `services/api/pyproject.toml` (nombre libre en PyPI → riesgo de *dependency confusion*); se instala junto al servicio con `pip install -e packages/incident-analyzer -e "services/api[dev]"` (verificado con un venv recreado desde cero).
- Rangos acotados a lo probado: `fastapi>=0.141,<0.142`, `python-multipart>=0.0.32,<0.1`, `uvicorn>=0.53,<0.54`, `httpx>=0.28,<0.29` (sin lockfile).
- `MAX_UPLOAD_BYTES` (1 MiB) documentado como límite del **body HTTP completo**, no del CSV.
- El handler genérico de `HTTPException` conserva las cabeceras de la excepción: el 405 incluye `Allow`.
- `Cache-Control: no-store` en análisis y exportación.
- Semántica documentada: se guarda "el último análisis que termina correctamente" (sin cambiar la implementación).
- Comando de la suite de la API explícito con el Python del venv (`AGENTS.md` §4 y README); `.agents/rules/app-specific-overrides.md` lista la documentación local de `services/api` y `packages/incident-analyzer`.
- 9 tests nuevos: frontera exacta del body (`MAX` → 200, `MAX+1` → 413, con y sin `Content-Length`), ausencia de volcado a disco (espía de `SpooledTemporaryFile.rollover` + control positivo), A correcto + B fallido por 413 y por 500 → el export sigue siendo A, `Allow` en 405, `Cache-Control` en POST y export.

**Archivos añadidos:** `services/api/` (`README.md`, `SPECS.md`, `.env.example`, `pyproject.toml`, `app/{main,core/{config,errors,limits},modules/incidents/{router,schemas,service,store}}.py` + `__init__.py`, `tests/` con 5 módulos + `support.py`); `packages/incident-analyzer/tests/test_binary_stream.py`.
**Archivos modificados:** `packages/incident-analyzer/incident_analyzer/{analyze,__init__}.py` (nueva `analyze_binary_stream`, D-API-9) y su `README.md`; `.gitignore` (`.venv/`, `*.egg-info/`); `AGENTS.md` §4 (comando de la API con el venv, se mantiene el de la Fase 1); `.agents/rules/app-specific-overrides.md` (tabla de documentación local); `services/README.md` + `README.es.md` (catálogo de servicios); `memory-bank/{progress,techContext,projectbrief}.md`.
**Sin cambios:** `uis/*`, `src/`, `scripts/analyze.py`. Dependencias nuevas solo en `services/api` (las autorizadas: fastapi, python-multipart, uvicorn, httpx).

**Validación ejecutada:**
- Núcleo: `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` → 106 tests, 99 OK + 7 skipped (aceptación con CSV real, sigue PENDIENTE).
- API: `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` → 70 tests OK.
- `pip check` en el venv: sin requisitos rotos. `git diff --check`: limpio.
- Comprobaciones manuales: arranque real con `uvicorn app.main:create_app --factory --workers 1` (health, analyze, export; 413 con 2 MiB, 20 MiB y chunked; el access log no contiene emails); los tests clave detectan fallos si se revierte la corrección (literal de categoría → `test_architecture`; sin middleware de 500 → tests de excepción; sin cabeceras → test de `Allow`; sin `no-store` → tests de caché).

**Pendiente:**
- ~~Push de la rama y PR contra `main`~~ — hecho: PR #6, mergeado el 2026-09-23.
- Fuera de alcance por decisión del tech lead (no corregidos): códigos HTTP no estándar en el handler genérico, `filename=""` (responde 422), nombre de paquete genérico `app`, migración a `httpx2`, lockfile, `/api/v1`.
- ~~Fase 3 (frontend en `uis/backoffice`) y Fase 4 (integración): no iniciadas~~ — corregido: la Fase 3 se implementó, validó y commiteó el 2026-09-23 (entrada de arriba); la Fase 4 sigue sin iniciar.
- Test de aceptación con el CSV real (igual que en la Fase 1).
- `docs/ARCHITECTURE_PROPOSAL.md` sigue pendiente del CTO; esta API no la aprueba implícitamente.

---

## 2026-09-22 — Procesador de reportes de incidentes, Fase 1: núcleo + CLI

**Estado: Fase 1 hecha y commiteada (`0203023`) — aceptación contra el dataset real PENDIENTE (el CSV no está disponible).** Rama de trabajo de todo el proyecto (Fases 1–3): `feature/incident-analyzer`.

Contexto: Roberto Díaz (Customer Support Lead) necesita analizar un mes de tickets del helpdesk legado sin enviar los datos a herramientas de IA externas (el CSV contiene emails reales). Fuente de verdad: `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`. Plan en 4 fases: 1) núcleo + CLI, 2) API, 3) frontend en backoffice, 4) integración. Estado de las siguientes fases: ver entradas posteriores.

**Decisiones fijadas por el tech lead antes de implementar (D1–D9):** `invalid_records` cuenta filas distintas y el desglose cuenta activaciones de regla (D1); la consola muestra las 7 reglas aunque valgan 0 (D2); solo las 7 reglas del contexto invalidan — `ticket_id`/`date`/`status` fuera de formato no, y sin sección de warnings (D3); score presente no entero 1–5 → "fuera de rango", score válido en OPEN/DISCARDED permitido pero fuera del índice (D4); `strip()` + valores exactos, `agent_id` `^AGT-\d{2}$`, email = no vacío y con `@` (D5); `results.csv` en formato `metric,value` sin datos de registros (D6); tests solo con `unittest` (D7); núcleo en `packages/incident-analyzer/`, CLI fina en `scripts/analyze.py` (D8); el documento de contexto se queda en `docs/` (D9).

**Archivos añadidos:** `packages/incident-analyzer/` (`pyproject.toml`, `README.md`, `incident_analyzer/{__init__,schema,reader,validation,metrics,analyze,report,export}.py`, `tests/` con 8 módulos de test + `fixtures/incidents-synthetic.csv`); `scripts/analyze.py`.
**Archivos modificados:** `.gitignore` (Python + `data/raw/incidents/` + `results.csv`); `AGENTS.md` (§4: comando de validación del subproyecto); `memory-bank/{progress,techContext,projectbrief}.md`. Se versiona también `docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md` (fuente funcional, sin PII).
**Sin cambios:** `services/` (no se creó), `uis/*`, `src/`. Ninguna dependencia añadida.

**Validación ejecutada:** `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` → 99 tests, 92 OK + 7 skipped (el test de aceptación `tests/test_acceptance.py`, marcado "PENDING" porque falta el dataset real). CLI ejecutada contra el fixture en modo interactivo (`y` → `results.csv`), `--export`, `--no-export` y con consola cp1252 (variante ASCII). **Los números 100/96/4 del contexto NO están verificados contra datos reales**: solo se comprobó, con un CSV simulado fuera del repo, que el test de aceptación y la aritmética del documento (media 215/56 = 3.84, porcentajes) son coherentes.

**Pendiente:**
- Obtener `incidents-nexova.csv`, colocarlo en `data/raw/incidents/` (ignorado por git) y ejecutar el test de aceptación.
- Criterios derivados de D4/D5 que API y frontend deben heredar sin reimplementar (reutilizando `incident_analyzer`): `+4`/`4.0` → score fuera de rango; `closed` en minúsculas no es `CLOSED` (fila válida, sin regla 6); un status desconocido deja el desglose por estado por debajo del total de válidos.
- ~~Fases 2–4 no iniciadas~~ — corregido: la Fase 2 se implementó el 2026-09-23 y la Fase 3 también (ver entradas de arriba); la Fase 4 sigue sin iniciar.

---

## 2026-09-20 — Propuesta de arquitectura del backend (`docs/ARCHITECTURE_PROPOSAL.md`)

**Estado: hecho (documento redactado y revisado) — pendiente de aprobación del CTO (Sergio Molina).**

Contexto: el CTO pidió una propuesta razonada de arquitectura para el primer backend propio de Nexova **antes** de implementarlo. Entregable exclusivamente documental.

**Archivos añadidos:** `docs/ARCHITECTURE_PROPOSAL.md` (patrón arquitectónico, dominios, estructura de carpetas, capas, routers, versionado, frontend/backend, CORS, persistencia, configuración, testing, riesgos, decisiones propuestas vs pendientes; referencias a documentación oficial de FastAPI, Next.js y MDN).
**Archivos modificados:** `memory-bank/progress.md` (esta entrada) y `memory-bank/techContext.md` (una nota de referencia bajo la decisión "`/services` no se crea", que sigue vigente).
**Sin cambios:** ningún archivo de implementación; `services/api/` **no** se creó; ninguna dependencia añadida; FastAPI **no** instalado; `uis/*` y `src/` intactos. **Sin impacto técnico.**

**Qué contiene la propuesta (resumen, no decisiones aprobadas):** un único servicio FastAPI en `services/api/` como monolito modular por dominios con capas internas (router → service → domain → repository); módulos MVP `candidates`, `vacancies`, `pipeline` (con notas) y `matching` como capacidad interna; versionado `/api/v1`; CORS con orígenes explícitos por entorno; PostgreSQL como motor recomendado; los 97 tests de `src/` como especificación del módulo `matching`. Todo lo anterior es **[PROPUESTA]** hasta que el CTO lo apruebe; las decisiones abiertas (autenticación, ORM, hosting, vocabulario de etapas del pipeline, exposición HTTP de `matching`, revisión de privacidad, integración del website estático) están listadas en la §19 del documento y **no** deben tratarse como resueltas.

**Validación ejecutada:** `docs/` no tiene comando de validación en la tabla de `AGENTS.md` §4 (cambio solo documental). Se verificó manualmente: (a) que todas las rutas del repositorio citadas en el documento y en `memory-bank/` existen; (b) `git status --short` / `git diff --stat` muestran únicamente los archivos listados arriba; (c) fidelidad al contexto: todos los datos de Nexova citados proceden de `contexts/CONTEXT.md` / `memory-bank/projectbrief.md`.

**Siguiente paso si se aprueba:** redactar el contrato de los dominios propuestos (`candidates` y `vacancies` primero) antes de implementarlos, añadiendo su comando de validación a la tabla de `AGENTS.md` §4 en el mismo cambio. *(Corrección 2026-09-23: esta entrada decía "redactar `services/api/SPECS.md`"; ese archivo ya existe y pertenece a la API del procesador de incidentes de Nexova. Si la propuesta se aprueba, habrá que decidir si sus dominios se añaden a ese mismo servicio y documento o van a uno nuevo.)* Ver "Próximos pasos conocidos" abajo.

---

## 2026-09-14 — Monorepo AI Setup: memory-bank, AGENTS.md, .agents/, uis/backoffice

**Estado: hecho.**

Contexto: el tech lead detectó que el repo no tenía contexto persistente para agentes. Se añadió banco de memoria (`memory-bank/`), flujo de entrega obligatorio (`AGENTS.md`), reglas y skill (`.agents/`), y un scaffold real (no solo placeholder) para `uis/backoffice`.

**Archivos añadidos:** `memory-bank/{projectbrief,techContext,progress}.md`; `AGENTS.md` (raíz); `.agents/rules/{monorepo-structure,nexova-context,app-specific-overrides}.md`; `.agents/skills/memory-bank-sync/SKILL.md`; `uis/backoffice/` completo (Next.js 16 + React 19 + TS, `lib/company.ts` con datos reales de Nexova, `app/layout.tsx`, `app/page.tsx`, `app/globals.css`, config estándar, `README.md`, `CLAUDE.md`).
**Archivos modificados:** `uis/README.md` y `uis/README.es.md` (catálogo de apps existentes, incluyendo `backoffice`).
**Sin cambios:** `uis/website/` (cero diff, confirmado); `/services` (no se creó, decisión documentada en `techContext.md`); ninguna rama existente tocada.

**Validación ejecutada:** `npm install`, `npx tsc --noEmit` (limpio), `npm run lint` (limpio), `npm run build` (compila y genera `/` estático) y `npm run dev` + verificación visual en el navegador — la ficha de `NEXOVA_COMPANY` (fundación 2011, CEO Laura Mendoza, sede Valencia + oficina Miami, 120 empleados, ~8.000.000 US$, tres líneas de negocio) se renderiza correctamente, todas dentro de `uis/backoffice/`.

**Hallazgo relevante durante la implementación:** `contexts/` está en `.gitignore` (raíz, línea 8) — nunca ha estado en git (`git ls-files contexts/` vacío). No viaja con el repositorio; solo existe en checkouts locales que ya la tenían. Se ajustó toda la documentación nueva para que `memory-bank/projectbrief.md` sea la referencia de negocio válida para quien clone el repo sin esa carpeta, y para que `contexts/CONTEXT.md` se cite como fuente ampliada "si está disponible localmente", nunca como algo garantizado.

**Desviación respecto a la rama planeada inicialmente:** el plan original (antes de corrección) proponía ramificar desde `feature/talent-pipeline-tracker` y abrir el PR contra esa misma rama, asumiendo que `main` no tenía Hitos 2/3. La inspección real mostró que el `main` **local** estaba desactualizado: `origin/main` ya tenía Hitos 2 y 3 mergeados (PRs #1, #2, #3). Corregido a petición del tech lead: rama `feature/agent-memory-bank` creada desde `origin/main`, PR con base `main` — sin tocar ninguna rama existente.

---

## Hito 3 — Talent Pipeline Tracker (`uis/talent-pipeline-tracker/`)

**Estado: hecho, mergeado a `main`** (PR #2 `Inicializar proyecto...`, PR #3 `feat: completar Talent Pipeline Tracker`).

Panel interno de gestión de candidaturas para Operaciones de Selección (Javier Almeida) / encargo urgente de Elena Vargas (L&D), con copia a Sergio Molina (CTO). Next.js 16 + React 19 + TS estricto, consume directo la API mock externa (`playground.4geeks.com/tracker/api/v1`, CORS verificado, sin proxy). Cinco incógnitas de contrato (`SPECS.md` §0, V-1 a V-5) resueltas empíricamente antes de implementar. Fuera de alcance deliberado: eliminar candidaturas (endpoint existe en la API pero no se expone en la UI).

## Hito 2 — Modelos de dominio y scoring (`src/`)

**Estado: hecho, mergeado a `main`** (PR #1 `feature/domain-models`).

Utilidades TypeScript para el motor de scoring de candidatos y matching de vacantes de Javier Almeida (Operaciones de Selección): `Candidate`, `Vacancy`, `SelectionProcess`, funciones de filtrado/búsqueda/scoring/validación. 97 tests con el runner nativo de Node (`node:test`), sin dependencias de terceros. `npm run check` = typecheck + tests.

## Hito 1 — Sitio web público (`uis/website/`)

**Estado: hecho, desplegado en Netlify.**

Landing corporativa + formulario de registro de talento para Carmen Ruiz (Marketing y Comunicación). HTML estático + Tailwind CSS v4 (Play CDN), Schema.org `Organization` JSON-LD, accesible (skip link, foco visible).

## Hito 0 — Elección de empresa

**Estado: hecho.**

Empresa elegida: **Nexova**. Justificación en `contexts/COMPANY-CHOICE.md` (local, no versionado — ver nota sobre `contexts/` en `techContext.md`); resumen de por qué en `memory-bank/projectbrief.md`.

---

## Decisiones y problemas conocidos

- ~~**`README.md` raíz desactualizado**~~ — resuelto el 2026-09-27: el `README.md` raíz ahora es el briefing de Nexova (ver entrada de arriba).
- **`main` local puede desactualizarse silenciosamente:** al iniciar este cambio, el `main` local estaba 7 commits detrás de `origin/main` (incluía Hitos 2 y 3, ya mergeados vía PR). Cualquier agente debe `git fetch` antes de asumir en qué estado está `main`.
- **`/services` ya no está vacío (2026-09-23):** contiene `services/api/`, la API del procesador de incidentes, creada por decisión del tech lead con contrato propio (`services/api/SPECS.md`). La decisión "`/services` no se crea" está marcada como superada en `techContext.md`. `docs/ARCHITECTURE_PROPOSAL.md` (backend general de Nexova: candidatos, vacantes, pipeline…) **sigue pendiente de aprobación del CTO**; `services/api/` no la adopta (p. ej. no usa `/api/v1`).
- **AUTH-03, auditoría de seguridad (2026-10-06):**
  - **H-1 corregido:** un usuario que no es admin ya no cambia `password` con `PUT /users/{id}`; solo puede hacerlo con `POST /auth/change-password`.
  - **Riesgo residual aceptado (SPECS §27):** un admin sigue pudiendo fijar contraseñas con `PUT /users/{id}`, también la suya, sin la contraseña actual. Ese cambio no invalida enlaces de reset pendientes ni se audita.
  - **No bloqueantes y sin corregir:**
    - M-1: no se cierran las sesiones al cambiar o restablecer la contraseña;
    - M-2: diferencia de tiempo en `forgot-password` según exista el email;
    - M-3: escrituras sin rate limiting en `auth.json`;
    - L-1: bcrypt antes de validar el token;
    - L-2: `PASSWORD_RESET_URL` admite `http://`;
    - L-3: el token aparece en la URL de la primera carga;
    - L-4: `http.client.HTTPException` no se captura en el sender;
    - L-5: retención de las IP de la auditoría;
    - L-6: aviso de éxito oculto si hay otra sesión abierta.
- **Deuda pendiente — `LastResultStore` global al proceso, no por usuario (registrada el 2026-10-05, sin corregir):** `services/api` guarda en memoria un único "último análisis" de incidentes para todo el proceso (`services/api/SPECS.md` §6, D-API-5). Desde AUTH-01/AUTH-02 hay varios usuarios autenticados, así que un usuario puede exportar el último resultado generado por otro. Hoy el resultado solo contiene métricas agregadas (sin filas ni emails) y el frontend descarta una exportación cuyo `X-Analysis-Id` no coincide con el análisis que muestra, pero la API no lo impide. **No se corrige ahora:** es una decisión de arquitectura pendiente del tech lead, a revisar antes de llevar el módulo de incidentes a un uso multiusuario real o a la Fase 4.

## Próximos pasos conocidos (no implementados aquí)

- **Gestor centralizado de incidencias:** F1 (validación compartida en `packages/shared`, `164a183`), F2 (modelo + repositorio TinyDB en `services/api`, `959a65b`) y F3 (`scripts/seed_incidents.py`) hechas y comiteadas en `feature/centralized-incident-manager` (entradas 2026-10-07). Siguen F4 (API `/api/incidents`), F5 (UI `/incident-manager` en `uis/backoffice`) y F6 (docs), una fase por commit y con visto bueno entre fases. Decisiones P4-1…P4-13 en la entrada de F1.
- **Backend general de Nexova:** `docs/ARCHITECTURE_PROPOSAL.md` está pendiente de revisión por el CTO. Si se aprueba, sus dominios (candidatos, vacantes, pipeline, matching) tendrán que decidir cómo convivir con el `services/api/` ya existente del procesador de incidentes (mismo servicio o no, prefijo `/api/v1` o no). Nada de eso se ha iniciado.
- **Procesador de incidentes:** Fases 1, 2 y 3 (`/incidents` en `uis/backoffice`) hechas e integradas en `main` (PR #6). Existe un fixture sintético de aceptación que reproduce las cifras del contexto (entrada 2026-09-27, PR #7). Pendientes: el test de aceptación con el CSV real (las cifras 100/96/4 no están verificadas con datos reales) y la Fase 4 (integración). Antes de la Fase 4 o de un uso multiusuario real, revisar la deuda de `LastResultStore` (ver "Decisiones y problemas conocidos").
- `uis/backoffice` es un punto de entrada — tiene `/incidents` y `/suppliers`; el resto de capacidades (portal de RRHH, ventas, dirección ejecutiva) requieren su propio contexto de hito antes de implementarse.
- **Directorio de proveedores:** hecho e integrado en `main` con el PR #9 (entrada 2026-09-29). Migración futura de TinyDB a Postgres cuando exista el ORM (decisión del tech lead) — `User`/`Profile` de AUTH-01 **no** migran: se quedan en TinyDB y Postgres solo guardará `user_uuid`.
- **AUTH-01:** hecho e integrado en `main` con el PR #10 (entrada 2026-09-30). Su siguiente fase (que el frontend envíe el token y `PUT` en CORS) la cubrió AUTH-02.
- **AUTH-03:** implementado en `feature/password-reset` (entradas 2026-10-05 y 2026-10-06), validado de extremo a extremo con email real y con H-1 de la auditoría corregido. Commits `cb9d0d5` y `2a1926a`, integrados en `main` con la PR #16 (merge `677e735`, 2026-10-07). La guía para revisarlo está en `docs/auth-password-reset.md`. El merge no aprueba las propuestas P3-1…P3-6 ni decide sobre M-1, M-2 y M-3, que siguen pendientes.
- **AUTH-02:** hecho e integrado en `main` con la PR #13 (merge `a4b6369`, entrada 2026-10-02 / 2026-10-05). Pendientes: revisión de las propuestas P-1…P-7 (`docs/auth-frontend.md` §3.3), registro desde la UI del tracker y refresh tokens (fuera de alcance). Los 4 errores de lint `react-hooks/set-state-in-effect` del tracker son anteriores a AUTH-02.
