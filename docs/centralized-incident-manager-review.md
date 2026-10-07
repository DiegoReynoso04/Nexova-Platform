# Gestor centralizado de incidencias — guía de revisión

Documento para revisar el proyecto: cómo levantarlo, qué salida esperar, qué cubre cada test y qué **no** está verificado.

- Contexto de negocio (enumerados, mapeos y conteos esperados): [`centralized-incident-manager.md`](./centralized-incident-manager.md).
- Contrato HTTP y decisiones P4-1…P4-13: [`services/api/SPECS.md`](../services/api/SPECS.md) Parte E (§28–§33).
- Reglas de la UI: [`uis/backoffice/CLAUDE.md`](../uis/backoffice/CLAUDE.md), sección "Gestor centralizado de incidencias".
- Historial por fases (F1–F6) y validaciones ejecutadas: [`memory-bank/progress.md`](../memory-bank/progress.md).

> Las decisiones P4-1…P4-13 las tomó **el usuario** al aprobar el plan (2026-10-07). No han sido revisadas ni aprobadas por el tech lead ni por la CTO.

## Qué se construyó

| Pieza | Dónde | Qué hace |
|---|---|---|
| Validación compartida | `packages/shared/` (paquete Python `nexova_shared`) | `incident_csv`: esquema, lector y las 7 reglas del CSV, extraídos del analizador (que los reexporta). `incidents`: vocabulario, reglas de campos, ciclo de vida y mapeo CSV → modelo |
| Modelo y repositorio | `services/api/app/modules/incident_manager/` (`models.py`, `repository.py`) | TinyDB en `INCIDENTS_DB_PATH`; id UUID v4; `created_at`/`updated_at` UTC; filtros; transiciones; resumen; tabla `seed_keys` (solo SHA-256 de la clave de origen) |
| Seed | `scripts/seed_incidents.py` | Carga el CSV histórico (`origin = customer`, `branch = central`), idempotente, con informe sin contenido de filas |
| API | `services/api/app/modules/incident_manager/router.py` | `POST`/`GET /api/incidents`, `GET /api/incidents/summary`, `GET /api/incidents/{id}`, `PATCH /api/incidents/{id}/status`; JWT; validación con 400 propio |
| UI | `uis/backoffice` → `/incident-manager`, `/incident-manager/new` | Resumen, listado filtrable con cambio de estado optimista y formulario de registro |

## Cómo revisar este proyecto (Windows PowerShell)

Todos los comandos se lanzan **desde la raíz del monorepo** salvo que se indique otra carpeta. Requisitos: Python ≥ 3.11, [uv](https://docs.astral.sh/uv/) (para arrancar la API con su `.env`), Node.js 24 (tests del backoffice; la app funciona con Node ≥ 20).

### 1. Instalar el venv de la API (los tres paquetes editables)

```powershell
python -m venv services\api\.venv
services\api\.venv\Scripts\python -m pip install -e packages\shared -e packages\incident-analyzer -e "services\api[dev]"
```

Los tres en la misma orden: `packages/shared` y `packages/incident-analyzer` no están publicados y no se declaran como dependencias (riesgo de *dependency confusion*; ver `services/api/README.md`).

### 2. Preparar una base de incidencias de revisión y cargar el histórico

La API y el seed deben usar el mismo archivo. Se fija una vez en la sesión de PowerShell (fuera del repositorio, para no tocar `services/api/data/`):

```powershell
$env:INCIDENTS_DB_PATH = "$env:TEMP\nexova-review\incidents.json"
services\api\.venv\Scripts\python scripts\seed_incidents.py packages\incident-analyzer\tests\fixtures\incidents-acceptance-synthetic.csv
```

Salida esperada (primera ejecución; la línea `Base de datos` muestra la ruta de `INCIDENTS_DB_PATH`):

```text
Archivo CSV: incidents-acceptance-synthetic.csv
Base de datos: C:\Users\<usuario>\AppData\Local\Temp\nexova-review\incidents.json
Filas leídas: 100
Insertadas: 96
Ya existentes (omitidas): 0
Inválidas (no insertadas): 4
  - fila 18: missing_client_company
  - fila 45: invalid_category
  - fila 71: invalid_email
  - fila 93: closed_without_score
No mapeables (no insertadas): 0
Duplicadas en el archivo (no insertadas): 0
Total de incidencias en la base: 96
```

Segunda ejecución del mismo comando: `Insertadas: 0`, `Ya existentes (omitidas): 96`, `Total de incidencias en la base: 96` (idempotente). Códigos de salida: `0` correcto; `1` si el CSV no existe o su cabecera no es la del analizador.

> El fixture es **sintético** (100 filas, no son datos de Nexova) y reproduce las cifras del dataset real. El CSV real (`incidents-nexova.csv`) no está en el repositorio: si se tiene, se pasa su ruta en lugar del fixture.

### 3. Arrancar la API

En la **misma** ventana de PowerShell (para heredar `INCIDENTS_DB_PATH`), con la API configurada (`services/api/.env` con `JWT_SECRET_KEY` y `ACCESS_TOKEN_EXPIRE_MINUTES`; ver `services/api/README.md`, sección Arranque):

```powershell
cd services\api
Copy-Item .env.example .env    # solo la primera vez; después rellenar JWT_SECRET_KEY
uv run --no-sync --env-file .env uvicorn app.main:create_app --factory --port 8000 --workers 1
```

`--no-sync` usa el venv tal cual (una sincronización de uv puede desinstalar los paquetes editables del monorepo; ver el README de la API). Swagger: `http://localhost:8000/docs`.

### 4. Arrancar el backoffice

En otra ventana de PowerShell:

```powershell
cd uis\backoffice
npm install
Copy-Item .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Abrir `http://localhost:3000/register`, crear una cuenta y entrar. En la cabecera: **«Incidencias»** (`/incident-manager`) y **«Registrar incidencia»** (`/incident-manager/new`).

### 5. Comprobar `/api/incidents/summary`

Con la API arrancada y el seed cargado (sustituir el email y la contraseña por los de la cuenta creada):

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/login -Body @{ username = "<email>"; password = "<contraseña>" }
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Uri http://localhost:8000/api/incidents/summary -Headers $headers | ConvertTo-Json
```

Valores esperados justo después del seed (antes de crear incidencias o cambiar estados):

| Total | Valor |
|---|---|
| `total` | 96 |
| `by_status` | `open` 27 · `in_progress` 0 · `resolved` 56 · `discarded` 13 |
| `by_category` | `technical_failure` 49 · `process_error` 35 · `client_complaint` 12 · `candidate_issue` 0 · `staff_issue` 0 · `sla_breach` 0 · `data_quality` 0 · `other` 0 |
| `by_origin` | `customer` 96 · `branch` 0 · `internal` 0 |
| `by_branch` | `central` 96 · `valencia_operations` 0 · `miami_office` 0 · `remote` 0 |

Con la base vacía, todas las claves aparecen con 0.

### 6. Suites y totales

| Suite | Comando (desde la raíz) | Total |
|---|---|---|
| `packages/shared` | `python -m unittest discover -s packages/shared/tests -t packages/shared` | 81 OK |
| `packages/incident-analyzer` | `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` | 118 OK (7 skipped: aceptación con el CSV real, ausente) |
| `services/api` | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` | 289 OK (~1,5 min por los hashes bcrypt) |
| `src/` | `npm run check` | 97 OK |

Backoffice (desde `uis\backoffice`):

```powershell
npx tsc --noEmit
npm run lint
npm run build
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"
```

Totales: `tsc` y `lint` sin errores; `build` correcto (incluye `/incident-manager` y `/incident-manager/new`); 331 tests OK.

## Trazabilidad: "Qué evaluaremos" → implementación → test

Los tests de Python se citan como `archivo` → `Clase.test`; los del backoffice, por su descripción en `tests/*.test.mjs`. Los componentes React no tienen tests de renderizado (el backoffice no usa renderizador de DOM, por decisión previa): lo que depende del DOM se verificó a mano en el navegador y se indica como tal.

### Modelo y seed

| Punto | Implementación | Test |
|---|---|---|
| El modelo incluye todos los campos requeridos con sus restricciones de integridad | `packages/shared/nexova_shared/incidents/vocabulary.py`, `rules.py`; `services/api/app/modules/incident_manager/models.py`, `repository.py` | `packages/shared/tests/test_rules.py` → `ValidIncidentTests`, `InvalidIncidentTests`; `test_contract.py` → `VocabularyContractTests`; `services/api/tests/test_incident_manager_repository.py` → `CreateTests.test_stored_document`; `test_incident_manager_api.py` → `CreateTests` |
| El seed carga las incidencias históricas asignando `origin: "customer"` | `scripts/seed_incidents.py`; `nexova_shared/incidents/csv_mapping.py`; `IncidentRepository.seed` | `test_incident_manager_seed.py` → `AcceptanceFixtureTests.test_every_seeded_incident_is_customer_and_central`; `test_csv_mapping.py` → `FieldMappingTests.test_origin_is_always_customer_and_branch_central` |
| Aplica las transformaciones del CONTEXT: estado, categoría, título, fechas y sede | `csv_mapping.py` (`STATUS_MAP`, `CATEGORY_MAP`, `derive_title`, `parse_csv_date`, `SEED_BRANCH`) | `test_csv_mapping.py` → `TitleTests`, `DateTests`, `FieldMappingTests`; `test_contract.py` → `MappingContractTests` (lee las tablas del CONTEXT); `test_incident_manager_repository.py` → `SeedTests.test_seeded_incidents_keep_the_csv_date` |
| Los registros inválidos no se insertan y se reportan | `prepare_seed_batch` (7 reglas del analizador + no mapeables + duplicados); informe de `seed_incidents.py` | `test_incident_manager_seed.py` → `AcceptanceFixtureTests.test_first_run_inserts_96_and_reports_the_4_invalid_rows`, `ReportTests`; `test_csv_mapping.py` → `SeedBatchTests` |
| Ejecutarlo dos veces no duplica datos | `IncidentRepository.seed` + tabla `seed_keys` (SHA-256 de `ticket_id`, o de `title + created_at`) | `test_incident_manager_seed.py` → `AcceptanceFixtureTests.test_second_run_inserts_nothing`; `test_incident_manager_repository.py` → `SeedTests.test_seed_is_idempotent`, `test_status_changes_survive_a_second_seed` |
| Tras el seed, los totales por `status` y `category` de `/summary` coinciden con el CONTEXT | `IncidentRepository.summary`; `GET /api/incidents/summary` | `test_incident_manager_api.py` → `SummaryTests.test_after_the_seed_of_the_acceptance_fixture`; `test_incident_manager_seed.py` → `test_summary_after_the_seed_matches_the_context`; `test_contract.py` → `ExpectedSeedValuesTests` (cifras leídas del CONTEXT). **Solo con el fixture sintético**: ver "No verificado" |

### Backend

| Punto | Implementación | Test |
|---|---|---|
| Todos los endpoints responden con los códigos HTTP correctos en casos felices y de error | `router.py` | `test_incident_manager_api.py` → `CreateTests`, `ListTests`, `SummaryTests`, `DetailTests`, `StatusChangeTests`, `AuthenticationTests` (401), `NoRegressionTests` (405/404/422 existentes) |
| Los errores de validación identifican el campo problemático en la respuesta JSON | `IncidentManagerRoute` (`router.py`); `FieldError` de `nexova_shared` | `test_incident_manager_api.py` → `CreateTests` (cada caso comprueba `field` y `error`), `test_every_error_is_reported_at_once`, `ListTests.test_invalid_filter_values`, `StatusChangeTests.test_body_without_status` |
| Ningún endpoint expone un stack trace | `InternalErrorMiddleware` (`app/core/errors.py`, existente) | `test_incident_manager_api.py` → `UnexpectedErrorTests.test_exception_in_every_new_route_is_an_opaque_500` (respuesta y logs) |
| Las transiciones no permitidas se rechazan con 400 | `check_transition` (`rules.py`); `IncidentRepository.change_status` | `test_incident_manager_api.py` → `StatusChangeTests.test_all_16_transitions`; `test_rules.py` → `TransitionTests`; `test_incident_manager_repository.py` → `ChangeStatusTests` |
| `/summary` devuelve métricas correctas aunque no haya incidencias | `IncidentRepository.summary` (no crea el archivo) | `test_incident_manager_api.py` → `SummaryTests.test_empty_database_has_every_key_at_zero`; `test_incident_manager_repository.py` → `EmptyDatabaseTests` |

### Frontend

| Punto | Implementación | Test |
|---|---|---|
| El formulario valida los obligatorios en el cliente antes de enviar | `validateIncidentForm` (`services/incident-manager.service.ts`); `components/incident-manager/incident-form.tsx` | `incident-manager.service.test.mjs` → "validación en cliente" y "alta inválida en cliente: ninguna petición de red". Que el componente llame a la validación antes de `onSubmit`: **sin test automático**, verificado en el navegador (0 `POST` en el log de la API) |
| Con `origin = branch`, `branch` se resalta y el desplegable muestra las etiquetas del CONTEXT | `incident-form.tsx`; `BRANCH_LABELS` (`types/incident-manager.ts`) | Etiquetas: `incident-manager-contract.test.mjs` → "sedes y sus etiquetas literales, en el mismo orden". **Resalte: sin test automático**, verificado en el navegador |
| Estados de carga visibles y botón deshabilitado durante la petición | `hooks/use-incident-form.ts` (`submitting`); `Button isLoading` | `use-incident-manager.test.mjs` → "envío: cargando y, al terminar, éxito con el formulario limpio", "un segundo envío mientras el primero está en curso se ignora". **Spinner y `disabled` en el DOM: sin test automático**, verificados en el navegador |
| Errores de la API en lenguaje comprensible, nunca texto técnico | `messageForApiError` y `failFromResponse` (servicio); `normalizeIncidentApiError`; `incident-error.tsx` | `incident-manager.service.test.mjs` → "400 de la API: error por campo con texto propio, nunca el del servidor", "cuerpo de error: solo code, field y error…"; `production-source.test.mjs` → "el gestor nunca lee el message de los errores de la API" |
| El listado gestiona cargando, vacío y con datos | `boardView` (`hooks/use-incident-board.ts`); `incident-board-view.tsx` | `use-incident-manager.test.mjs` → "listado: los cuatro estados" (cargando, vacío, error con reintento, datos). Renderizado: verificado en el navegador |
| La actualización de estado revierte visualmente si la petición falla | `incidentBoardReducer` (`status_change_failed`) | `use-incident-manager.test.mjs` → "si la API falla, el estado vuelve al anterior y se notifica en la fila", "también se revierte si falla la red" |
| El panel de resumen no rompe la página si su petición falla | `hooks/use-incident-summary.ts` (independiente); `incident-summary-panel.tsx` | `use-incident-manager.test.mjs` → "si el resumen falla, el listado sigue funcionando". Renderizado: verificado en el navegador |

### Transversal

| Punto | Implementación | Test |
|---|---|---|
| La validación del proyecto anterior está en `packages/shared/` y la reutilizan el script y la API sin duplicación | `nexova_shared.incident_csv` (reexportado por `incident_analyzer`) y `nexova_shared.incidents` (usado por el seed y por el router) | `packages/shared/tests/test_source.py` → `AnalyzerReusesSharedValidationTests`; `services/api/tests/test_architecture.py` → `test_no_core_literals_in_api`, `test_no_incident_manager_vocabulary_in_api` |
| El código está organizado en `scripts/`, `services/`, `uis/` y `packages/shared/` | Estructura del repositorio (ver "Qué se construyó") | **Sin test automático**: es estructural; se comprueba con el árbol del repositorio |

## Verificado por el usuario: viewport móvil

**El usuario probó `/incident-manager` a 375 px y encontró un fallo:** toda la página tenía scroll horizontal (`document.documentElement.scrollWidth` 673 frente a `clientWidth` 375).

- **Causa (diagnosticada por el usuario en el navegador):** en `components/incident-manager/incident-table.tsx`, las etiquetas `<label className="sr-only">` de la columna Estado son `position: absolute`. El contenedor con `overflow-x-auto` no era su bloque contenedor, así que no las recortaba y ensanchaban el documento.
- **Arreglo:** `relative` en ese contenedor. El `min-w` de la tabla y las etiquetas accesibles no cambian.
- **Comprobado después del arreglo, en el navegador:**

  | Ruta | 375 px | 1280 px |
  |---|---|---|
  | `/incident-manager` | scrollWidth 375 = clientWidth 375 | 1265 = 1265 |
  | `/incident-manager/new` | 375 = 375 | 1265 = 1265 |

  - El 1265 corresponde a 1280 px menos la barra de scroll vertical.
  - A 375 px la tabla conserva su scroll horizontal propio (768 de contenido frente a 341 visibles, desplazable).
  - Quitando `relative` desde la consola, el scrollWidth vuelve a 672: la causa queda confirmada.
- **Prevención:** `tests/production-source.test.mjs` exige `relative` en todo contenedor `overflow-x-auto` de `components/`. Hay una lista explícita de excepciones pendientes con el mismo patrón, fuera del alcance de este arreglo:
  - la tabla de `/suppliers` (`<caption className="sr-only">` y la etiqueta `sr-only` del editor de tarifa);
  - las tres tablas de `/incidents` (`<caption className="sr-only">`).

  El test falla si una de ellas se corrige y no se retira de la lista.

## Lo que no está verificado

- **CSV real ausente.** `incidents-nexova.csv` no está en el repositorio (ni en `data/raw/incidents/`): la aceptación de los totales (96 válidas; 27/56/13; 49/35/12) se comprobó **solo con el fixture sintético** de `packages/incident-analyzer/tests/fixtures/`, que reproduce las cifras del CONTEXT. `packages/incident-analyzer/tests/test_acceptance.py` sigue como *skipped (PENDING)*.
- **Revisión visual y con lector de pantalla pendientes.** La comprobación de F5 se hizo con el panel del navegador oculto, interactuando por DOM y JavaScript: no hay capturas ni revisión del diseño, ni prueba con lector de pantalla. El viewport móvil sí se probó (ver la sección anterior), pero solo se midió el ancho de la página, no el aspecto visual.
- **`/suppliers` e `/incidents` a 375 px.** Tienen el mismo patrón (elementos `sr-only` dentro de un `overflow-x-auto` sin `relative`), pero no se han medido ni corregido.
- **Filtros tras un cambio de estado.** Con un filtro activo (p. ej. `status=open`), una incidencia que cambia de estado **sigue en el listado** con su estado nuevo hasta la siguiente carga (cambiar un filtro o «Reintentar»): no desaparece al instante. El resumen sí se recarga. Ninguna fuente fija este comportamiento; es una decisión de implementación.
- **400 con `field` desde la UI real.** La validación en cliente y los desplegables impiden provocarlo desde el formulario: el comportamiento (mensaje en español junto al campo) solo está cubierto por los tests del servicio.
- **Recorrido manual en `/docs`.** La API se probó con `TestClient` y desde el backoffice en el navegador, pero no se hizo el recorrido manual en Swagger (*Authorize* → alta → filtros → cambio de estado → `/summary`) que pide `AGENTS.md` §4.
- **Bilingüe.** El CONTEXT pide respetar el soporte bilingüe "si has implementado soporte bilingüe en hitos anteriores": no existe (el backoffice está solo en español), así que la UI es solo en español.
- **Revisión de decisiones.** P4-1…P4-13 son decisiones del usuario; no las han revisado el tech lead ni la CTO.
