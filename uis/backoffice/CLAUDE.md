# Backoffice — restricciones permanentes

Fuente de verdad de negocio: `contexts/CONTEXT.md` si existe en tu checkout (carpeta local, no viaja con el repositorio — ver `.gitignore` raíz), o [`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md) si no. Fuente de verdad de decisión técnica: [`memory-bank/techContext.md`](../../memory-bank/techContext.md).

## Alcance actual

El backoffice tiene cuatro piezas de negocio, y **solo estas cuatro**, protegidas por la autenticación de AUTH-02 (sección propia abajo):

1. **Vista de entrada (`/`)** — ficha de empresa y roadmap. Se mantiene tal cual.
2. **Análisis de incidentes de soporte (`/incidents`)** — capacidad de negocio **autorizada** por el tech lead como Fase 3 del procesador de incidentes de Nexova (rama `feature/incident-analyzer`). Ver sección propia abajo.
3. **Directorio de proveedores (`/suppliers`)** — autorizado por el tech lead (Sergio Molina) para el encargo de Patricia Solís (rama `api-con-almacenamiento-ligero`). Ver sección propia abajo.
4. **Gestor centralizado de incidencias (`/incident-manager`, `/incident-manager/new`)** — autorizado por el usuario el 2026-10-07 (rama `feature/centralized-incident-manager`, fase F5). Distinto de `/incidents`. Ver sección propia abajo.

Cualquier otra capacidad de negocio (gestión de personas, operaciones, comunicación interna…) sigue **prohibida** sin un contexto de hito propio que la respalde — mismo criterio que `uis/talent-pipeline-tracker` (que tiene su `SPECS.md`).

## Datos mostrados

- `lib/company.ts` es la única fuente de datos de la vista de entrada. Cada campo de `NEXOVA_COMPANY` y de `PENDING_INTERNAL_AREAS` está citado desde `contexts/CONTEXT.md` (local) / `memory-bank/projectbrief.md` (versionado).
- No editar `lib/company.ts` con datos que no tengan respaldo literal en esas fuentes. Si falta un dato, preguntar — no inventarlo. La funcionalidad de incidentes **no** se añade a `lib/company.ts` ni cambia la portada.
- Los datos de `/incidents` vienen **exclusivamente** de la API de análisis (`services/api`); el frontend no genera cifras propias.

## Análisis de incidentes (`/incidents`)

Fuentes de verdad, por orden:

- Requisitos funcionales (CSV, reglas, métricas, privacidad): [`docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`](../../docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md). Ese documento describe un script: **no define ninguna interfaz web**; la UI es una decisión del tech lead.
- Contrato HTTP: [`services/api/SPECS.md`](../../services/api/SPECS.md) (`POST /api/incidents/analyze`, `GET /api/incidents/results/export`). Prohibido inventar campos, endpoints o formas de respuesta que no estén ahí; si falta algo, preguntar.

Reglas específicas:

- **Consume la API propia** del procesador de incidentes directamente desde el navegador (CORS configurado en la API). Sin Server Actions, Route Handlers ni proxy: el CSV no debe pasar por el servidor de Next.
- **URL de la API** solo desde `NEXT_PUBLIC_API_URL` (ver `.env.example`; valor local `http://localhost:8000`). Nunca literal en el código. Validación **perezosa**: si falta, la UI muestra un error de configuración en el momento de usarla; **`npm run build` no debe fallar** por ausencia de `.env.local`. `NEXT_PUBLIC_*` se fija en tiempo de build (guía de Next 16 `environment-variables`).
- **Sin reglas de negocio en el frontend.** La validación del contenido del CSV (las 7 reglas, categorías, estados, scores) es del backend (`packages/incident-analyzer`). La única prevalidación permitida en cliente es de UX: extensión `.csv` y un tamaño máximo con **4 KiB de margen** bajo 1 MiB. Ese margen **no es el límite real**: el límite es técnico, de la API, se aplica al **body HTTP completo** (1 MiB por defecto, configurable en el servidor) y el 413 del servidor es siempre la fuente de verdad (`services/api/SPECS.md` §3.1).
- **Idioma:** interfaz en español; las etiquetas de métricas (`label` de reglas y puntuaciones, `code` de categorías y estados) se muestran **tal como las devuelve la API, en inglés**. No duplicar ni traducir el vocabulario del dominio en el frontend.
- **Frontera de confianza:** `services/normalizers.ts` es el único lugar con `unknown` de red. Los componentes nunca hacen HTTP: toda petición pasa por `services/` y `lib/api-client.ts`.
- **Privacidad (obligatoria):** `customer_email` y cualquier dato de las filas del CSV no pueden aparecer en la UI, el estado, logs ni mensajes de error. El contenido del archivo **no se lee en JavaScript** (sin `FileReader`, `file.text()` ni vista previa): el `File` va directo a `FormData`. Prohibido `console.*` con datos de respuestas o errores, y persistir resultados en `localStorage`/`sessionStorage`/IndexedDB (la única excepción es el token de sesión de AUTH-02, ver "Autenticación"). Los mensajes de error mostrados se eligen por `code` de la API, no copiando texto crudo de respuestas.
- **Arquitectura de `/incidents`:** `app/incidents/page.tsx` es un Server Component (exporta la metadata) que renderiza `components/incidents/incident-analysis-view.tsx` (`'use client'`). La vista solo interactúa a través de `hooks/use-incident-analysis.ts`, que es la frontera de interacción: únicamente él llama a `services/incidents.service.ts`, gestiona cancelación/carreras y hace la descarga (el Blob nunca llega a los componentes ni al estado). Los demás componentes son presentacionales.
- **Navegación:** enlace "Análisis de incidentes" en la cabecera del layout (`components/ui/nav-link.tsx`, con `aria-current`); la portada no se modifica.
- **Tests:** módulos puros (normalizadores, cliente, servicio, estado/sesión del hook) y revisión estática del código de producción con el runner nativo de Node 24, **sin añadir dependencias**. Comando exacto en el `README.md` (sección Validación). Los componentes se validan con `tsc` + `lint` + `build` y verificación manual en el navegador.
- **Primitivas de UI** (botón, spinner, alerta): se reescriben localmente siguiendo el patrón de `uis/talent-pipeline-tracker/components/ui/`; no hay paquete compartido.

## Directorio de proveedores (`/suppliers`)

Fuentes de verdad, por orden:

- Requisitos funcionales y vocabulario: [`docs/ligthweight-storage-api.md`](../../docs/ligthweight-storage-api.md) ("Lo que verá Patricia en el frontend").
- Contrato HTTP: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte B (`GET/POST /suppliers`, `PATCH /suppliers/{id}/rate`, `PATCH /suppliers/{id}/status`). Mismas reglas que `/incidents` para no inventar campos ni endpoints.

Reglas específicas (lo no citado aquí sigue las reglas de `/incidents`: URL de la API, frontera de confianza, capas, tests, sin `console.*` ni persistencia en el navegador):

- **Sin botón ni llamada de borrado.** `DELETE /suppliers/{id}` existe en la API, pero la UI solo activa o suspende ("suspensión controlada"; SPECS §10). `tests/production-source.test.mjs` lo comprueba.
- **Vocabulario en el frontend (excepción a la regla de `/incidents`):** `types/suppliers.ts` define países, monedas, las 9 categorías y los 2 estados, porque los filtros y el formulario deben ofrecerlos y la API no los publica. Se muestran tal cual (en inglés) y `tests/suppliers-contract.test.mjs` exige que coincidan con el CONTEXT. No se traducen ni se amplían.
- **Validación en cliente:** solo campos requeridos y tarifa > 0 (`validateSupplierForm`, `parseRate`). La coherencia país/moneda, la fecha y el resto las valida la API; sus **422 se muestran por campo** con el `msg` de la API (no contiene datos personales: son reglas del modelo).
- **Renovaciones:** `lib/supplier-renewal.ts` destaca las fechas dentro de los próximos 60 días según la fecha local del navegador. Es presentación, no una regla de la API.
- **JSON de salida:** el único `JSON.stringify` permitido es el de `lib/api-client.ts` (`postJson`/`patchJson`), sobre bodies que el servicio construye campo a campo.
- **Arquitectura:** `app/suppliers/page.tsx` (Server Component, metadata) → `components/suppliers/supplier-directory-view.tsx` (`'use client'`) → `hooks/use-supplier-directory.ts` (única frontera de interacción: carreras, cancelación, recarga tras cambios) → `services/suppliers.service.ts` → `lib/api-client.ts`. `unknown` solo en `services/normalizers.ts`.
- **Navegación:** enlace "Proveedores" en la cabecera del layout.

## Gestor centralizado de incidencias (`/incident-manager`, `/incident-manager/new`)

Autorizado por el usuario el 2026-10-07 (fase F5 del gestor; decisiones P4-1…P4-13 en `services/api/SPECS.md` Parte E). **No confundir con `/incidents`**, el analizador del CSV, que no se toca.

Fuentes de verdad, por orden:

- Requisitos: el enunciado del proyecto (no versionado; resumido en `memory-bank/progress.md`) y [`docs/centralized-incident-manager.md`](../../docs/centralized-incident-manager.md) (vocabulario, etiquetas de sede, ciclo de vida).
- Contrato HTTP: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte E (`POST`/`GET /api/incidents`, `GET /api/incidents/summary`, `GET /api/incidents/{id}`, `PATCH /api/incidents/{id}/status`). Mismas reglas que `/incidents` para no inventar campos ni endpoints.

Reglas específicas (lo no citado sigue las de `/incidents`: URL de la API, frontera de confianza, capas, sin `console.*` ni persistencia en el navegador):

- **Vocabulario en el frontend (excepción, como en `/suppliers`):** `types/incident-manager.ts` define estados, orígenes, categorías, sedes, las etiquetas de sede (`BRANCH_LABELS`), la tabla de transiciones (`INCIDENT_TRANSITIONS`) y el máximo del título (120). `tests/incident-manager-contract.test.mjs` exige que coincidan con el CONTEXT. Se muestran los valores literales; **solo `branch` usa etiquetas** (las del CONTEXT). No se traducen ni se amplían.
- **Formulario:** `title`, `description`, `category`, `origin`, `branch` (siempre visible y obligatorio) y `status` en solo lectura (`open`). Validación en cliente antes de enviar (obligatorios y título ≤ 120): si no pasa, **no hay petición de red**. Con `origin = branch` el campo `branch` se resalta con borde, fondo **y un texto de ayuda** (no solo color). Durante el envío: spinner y botón deshabilitado. Tras el éxito, confirmación y formulario limpio (se vuelve a montar con `key = formKey`).
- **Errores de la API:** la API responde 400 `{code, detail: [{field, error, message}]}`. **El `message` del servidor nunca se muestra**: `normalizeIncidentApiError` lo descarta y `services/incident-manager.service.ts` elige un texto propio en español por `code`, `field` y `error`. Si hay `field`, el mensaje aparece junto a ese campo. `tests/production-source.test.mjs` comprueba que el normalizador no lee `message`.
- **Listado:** filtros `status`, `origin` y `branch` enviados a la API. Cuatro estados exclusivos (`boardView`): cargando, error con «Reintentar», vacío con mensaje (sin tabla) y con datos. Cambio de estado por fila **solo con transiciones válidas** (`INCIDENT_TRANSITIONS`; los estados finales muestran «Estado final», sin selector), **optimista**: si la API falla, la fila vuelve al estado anterior y muestra el aviso. Tras un cambio correcto se recarga el resumen.
- **Resumen:** hook propio (`use-incident-summary`), con carga y error propios: si falla, el listado sigue funcionando (y al revés).
- **Arquitectura:** `app/incident-manager/page.tsx` y `app/incident-manager/new/page.tsx` (Server Components, metadata) → `components/incident-manager/incident-board-view.tsx` / `incident-form-view.tsx` (`'use client'`) → `hooks/use-incident-board.ts`, `use-incident-summary.ts`, `use-incident-form.ts` (reducer puro + sesión sin React + hook) → `services/incident-manager.service.ts` → `lib/api-client.ts`. `unknown` solo en `services/normalizers.ts`. Rutas en `lib/incident-manager-routes.ts`.
- **Navegación:** enlaces «Incidencias» (`/incident-manager`) y «Registrar incidencia» (`/incident-manager/new`) en la cabecera.

## Autenticación (AUTH-02)

Autorizada por el ticket AUTH-02 ([`docs/auth-frontend.md`](../../docs/auth-frontend.md)). Contrato HTTP: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte C (`POST /auth/login`, `POST /users`, `GET /auth/me`, `PUT /profiles/me`). Mismas reglas que `/incidents` para no inventar campos ni endpoints.

- **Vistas:** `/login` y `/register` (públicas), `/account/profile` (protegida). Server Components con metadata que renderizan vistas cliente de `components/auth/`.
- **Token en `localStorage` (excepción a "sin persistencia en el navegador"):** exigido por el ticket. Solo `lib/auth-token.ts` toca `localStorage` y solo guarda el JWT; `tests/production-source.test.mjs` lo comprueba. Nunca se guardan datos de usuario, proveedores ni incidentes.
- **Cliente HTTP:** `lib/api-client.ts` adjunta `Authorization: Bearer <token>` a toda petición salvo las marcadas `skipAuth` (login y registro) y, ante un 401 de una petición protegida, borra el token y lanza `ApiUnauthorizedError` (los servicios lo traducen a `session_expired`). Es el único lugar que construye esa cabecera (test estático). Ninguna vista repite esta lógica.
- **Protección global:** `components/auth/auth-guard.tsx` en el layout raíz, con la sesión de `components/auth/session-provider.tsx` (`hooks/use-auth-session.ts`). Toda ruta es protegida salvo `PUBLIC_PATHS` de `lib/auth-routes.ts`: una vista nueva queda protegida sin tocar nada. La sesión se valida una vez por token con `GET /auth/me`; sin token o tras un 401 se redirige a `/login`. **Prohibido** usar middleware/proxy de Next.js o cookies para esta comprobación.
- **Capas:** vistas → `hooks/use-auth-form.ts` (login y registro comparten hook) / `hooks/use-profile.ts` → `services/auth.service.ts` (login y registro comparten el paso de login: el token solo se guarda si la respuesta es válida) → `lib/api-client.ts`. `unknown` solo en `services/normalizers.ts`.
- **Errores:** mensajes fijos por tipo (`components/auth/auth-error.tsx`); los 422 (y el 409 de email ya registrado) se muestran junto a su campo con el `msg` de la API. Nunca se muestra la contraseña ni el token.
- **Contraseñas (AUTH-03, [`docs/auth-password-reset.md`](../../docs/auth-password-reset.md); contrato en `services/api/SPECS.md` Parte D):** `/forgot-password` (pública), `/reset-password` (abierta: `OPEN_PATHS`, con o sin sesión, porque llega desde el enlace del email) y `/account/change-password` (protegida), más el enlace "¿Olvidaste tu contraseña?" en `/login`. Mismas capas (`hooks/use-auth-form.ts` → `services/auth.service.ts`). `/forgot-password` muestra siempre la misma confirmación tras un 200 y queda desactivado. La confirmación de la contraseña nueva se comprueba en el servicio antes de llamar a la API y nunca se envía. `/reset-password` lee `?token=` una vez, lo quita de la URL y usa `referrer: no-referrer`; el 400 `invalid_reset_token` muestra el error y un enlace a `/forgot-password`. El 400 `incorrect_password` se muestra en el campo de la contraseña actual (no cierra la sesión).

## Stack

- Next.js (App Router), TypeScript estricto, Tailwind CSS v4 (config vía CSS, sin `tailwind.config.ts`) — mismo stack que `uis/talent-pipeline-tracker`, decisión registrada en `memory-bank/techContext.md`.
- Solo hooks nativos de React si se añade estado. Prohibido Redux, Zustand, Recoil, Jotai u otra librería de estado externa.
- No añadir ninguna dependencia nueva sin autorización explícita.
- Prohibido `any`.

## Arquitectura

- Al consumir una API propia (hoy: análisis de incidentes, directorio de proveedores y gestor de incidencias), seguir el mismo patrón de frontera de confianza que `uis/talent-pipeline-tracker`: `services/normalizers.ts` como único lugar con `unknown` de red, errores tipados en `lib/api-client.ts`, y componentes sin HTTP directo.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
