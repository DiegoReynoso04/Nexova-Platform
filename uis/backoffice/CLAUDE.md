# Backoffice — restricciones permanentes

Fuente de verdad de negocio: `contexts/CONTEXT.md` si existe en tu checkout (carpeta local, no viaja con el repositorio — ver `.gitignore` raíz), o [`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md) si no. Fuente de verdad de decisión técnica: [`memory-bank/techContext.md`](../../memory-bank/techContext.md).

## Alcance actual

El backoffice tiene cinco piezas de negocio, y **solo estas cinco**, protegidas por la autenticación de AUTH-02 (sección propia abajo):

1. **Vista de entrada (`/`)** — ficha de empresa y roadmap. Se mantiene tal cual.
2. **Análisis de incidentes de soporte (`/incidents`)** — capacidad de negocio **autorizada** por el tech lead como Fase 3 del procesador de incidentes de Nexova (rama `feature/incident-analyzer`). Ver sección propia abajo.
3. **Directorio de proveedores (`/suppliers`)** — autorizado por el tech lead (Sergio Molina) para el encargo de Patricia Solís (rama `api-con-almacenamiento-ligero`). Ver sección propia abajo.
4. **Gestor centralizado de incidencias (`/incident-manager`, `/incident-manager/new`)** — autorizado por el usuario el 2026-10-07 (rama `feature/centralized-incident-manager`, fase F5). Distinto de `/incidents`. Ver sección propia abajo.
5. **Inventario de equipos y materiales (`/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`)** — autorizado por el usuario el 2026-10-19 (frontend del Hito 5, rama `feature/inventory-frontend`) sobre la API de `services/api` (SPECS Parte F). Ver sección propia abajo.

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
  - **Conflicto pendiente de decisión del usuario (#infra-40):** con Docker, el navegador llama a `/backend/…` y el rewrite de `next.config.ts` (sección «Docker») reenvía la petición a la API, así que la subida del CSV **sí pasa por el servidor de Next**, como proxy: en streaming, sin guardarse en disco ni registrarse su contenido. Hasta que se decida si se acepta como excepción o se cambia el diseño, esta regla no se cumple en Docker.
- **URL de la API** solo desde `NEXT_PUBLIC_API_URL` (con Docker, `/backend`, en el `.env` de la raíz; ver la sección «Docker»). Nunca literal en el código. Validación **perezosa**: si falta, la UI muestra un error de configuración en el momento de usarla; **`npm run build` no debe fallar** por ausencia de `.env.local`. `NEXT_PUBLIC_*` se fija en tiempo de build (guía de Next 16 `environment-variables`).
- **Sin reglas de negocio en el frontend.** La validación del contenido del CSV (las 7 reglas, categorías, estados, scores) es del backend (`packages/incident-analyzer`). La única prevalidación permitida en cliente es de UX: extensión `.csv` y un tamaño máximo con **4 KiB de margen** bajo 1 MiB. Ese margen **no es el límite real**: el límite es técnico, de la API, se aplica al **body HTTP completo** (1 MiB por defecto, configurable en el servidor) y el 413 del servidor es siempre la fuente de verdad (`services/api/SPECS.md` §3.1).
- **Idioma:** interfaz en español; las etiquetas de métricas (`label` de reglas y puntuaciones, `code` de categorías y estados) se muestran **tal como las devuelve la API, en inglés**. No duplicar ni traducir el vocabulario del dominio en el frontend.
- **Frontera de confianza:** `services/normalizers.ts` es el único lugar con `unknown` de red. Los componentes nunca hacen HTTP: toda petición pasa por `services/` y `lib/api-client.ts`.
- **Privacidad (obligatoria):** `customer_email` y cualquier dato de las filas del CSV no pueden aparecer en la UI, el estado, logs ni mensajes de error. El contenido del archivo **no se lee en JavaScript** (sin `FileReader`, `file.text()` ni vista previa): el `File` va directo a `FormData`. Prohibido `console.*` con datos de respuestas o errores, y persistir resultados en `localStorage`/`sessionStorage`/IndexedDB (la única excepción es el token de sesión de AUTH-02, ver "Autenticación"). Los mensajes de error mostrados se eligen por `code` de la API, no copiando texto crudo de respuestas.
- **Arquitectura de `/incidents`:** `app/incidents/page.tsx` es un Server Component (exporta la metadata) que renderiza `components/incidents/incident-analysis-view.tsx` (`'use client'`). La vista solo interactúa a través de `hooks/use-incident-analysis.ts`, que es la frontera de interacción: únicamente él llama a `services/incidents.service.ts`, gestiona cancelación/carreras y hace la descarga (el Blob nunca llega a los componentes ni al estado). Los demás componentes son presentacionales.
- **Navegación:** enlace "Análisis de incidentes" en la cabecera del layout (`components/ui/nav-link.tsx`, con `aria-current`); la portada no se modifica.
- **Tests:** módulos puros (normalizadores, cliente, servicio, estado/sesión del hook) y revisión estática del código de producción con el runner nativo de Node 24, **sin añadir dependencias** (la única excepción es Jest, de AUTH-088; ver «Stack»). Comando exacto en el `README.md` (sección Validación). Los componentes se validan con `tsc` + `lint` + `build` y verificación manual en el navegador.
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

## Inventario (`/inventory/*`)

Autorizado por el usuario el 2026-10-19 (frontend del inventario del Hito 5, rama `feature/inventory-frontend`). Lo usa el personal de operaciones: claridad y velocidad antes que acabado visual.

Fuentes de verdad, por orden:

- Requisitos: el brief literal del frontend del inventario, [`docs/inventory-frontend-brief.md`](../../docs/inventory-frontend-brief.md) (con la nota de equivalencias: su «BRIEFING.md» son el `README.md` raíz y el CONTEXT, y sus rutas `/backoffice/inventory/...` son `/inventory/...`), y [`docs/context-nexova-gestion-inventario-hito-5.md`](../../docs/context-nexova-gestion-inventario-hito-5.md) (entidades, campos, vocabulario y reglas). El briefing de empresa es el [`README.md`](../../README.md) raíz.
- Contrato HTTP: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte F (§37–§38) y `services/api/app/modules/inventory/schemas.py`. Mismas reglas que `/incidents` para no inventar campos ni endpoints.
- Guía de revisión de la API: [`docs/inventory-review.md`](../../docs/inventory-review.md); guía de revisión del frontend (arranque, recorrido de las 4 páginas, trazabilidad con el brief, decisiones D1–D10 y lo no verificado): [`docs/inventory-frontend-review.md`](../../docs/inventory-frontend-review.md).

Reglas específicas (lo no citado sigue las de `/incidents`: frontera de confianza, capas, sin `console.*` ni persistencia en el navegador):

- **Páginas** (las del brief, protegidas por el guard global; no están en `PUBLIC_PATHS` ni en `OPEN_PATHS`): `/inventory/products` (Activos), `/inventory/orders/inbound` (Entrada de activos), `/inventory/orders/outbound` (Salida de activos) e `/inventory/orders` (Historial). `/inventory` redirige a `/inventory/products`. Rutas en `lib/inventory-routes.ts`.
- **Navegación:** un solo enlace «Inventario» en la cabecera (`components/auth/account-nav.tsx`) → `/inventory/products`, marcado en todo `/inventory` (`NavLink` con `activePrefix`), y una subnavegación común a las 4 páginas (Activos · Entrada de activos · Salida de activos · Historial) con la página activa marcada (`aria-current`), en `app/inventory/layout.tsx` + `components/inventory/inventory-nav.tsx`.
- **URL de la API:** `NEXT_PUBLIC_INVENTORY_API_URL` (con Docker, `/backend`, en el `.env` de la raíz; el servicio añade `/inventory/...`). Validación perezosa, como `NEXT_PUBLIC_API_URL`: si falta, error de configuración en la UI, sin romper el build. **Sin reserva** a `NEXT_PUBLIC_API_URL`.
- **Integración:** `services/inventory.service.ts` es el único módulo que llama a `/inventory`, a través de `lib/inventory-api-client.ts`: el mismo `createApiClient` de `lib/api-client.ts` con otra base URL. Por eso siguen valiendo el único `fetch`, el `Authorization: Bearer` en toda petición y el 401 → sesión caducada. Tipos en `types/inventory.ts`; `unknown` solo en `services/normalizers.ts`.
- **Vocabulario en el frontend (excepción, como en `/suppliers`):** `types/inventory.ts` define categorías, oficinas, tipos de salida, `QUANTITY_MAX` y `TEXT_MAX_LENGTH`. `tests/inventory-contract.test.mjs` exige que coincidan con el CONTEXT y con `services/api/app/modules/inventory/vocabulary.py`. Los valores (`hardware`, `Valencia`, `allocation`…) se muestran tal como los devuelve la API. Títulos y etiquetas usan los términos del CONTEXT: «Activos» (no «productos»), «Entrada de activos», «Salida de activos», «Asignación», «Consumo», «Oficina», «Proveedor», «Asignado a», «Stock actual».
- **Formularios:**
  - el selector es `components/inventory/asset-select.tsx`, compartido: muestra «nombre — SKU (oficina)» (`assetOptionLabel`), nunca un id;
  - la **oficina** es la del activo elegido y es la que se envía. Se muestra como **valor de solo lectura** (`components/inventory/read-only-field.tsx`: un `<output>` asociado a su etiqueta, con fondo atenuado y sin borde de campo), nunca como un `<input>`;
  - `asset_id` y `quantity` se envían como **números** (la API usa enteros estrictos);
  - el activo puede llegar preseleccionado con `?asset_id=` desde Activos (`lib/asset-preselection.ts`); si no existe, aviso visible y selector vacío;
  - validación en cliente antes de enviar (activo, cantidad entera de 1 a `QUANTITY_MAX`, proveedor, tipo de salida y «Asignado a» con una asignación): si no pasa, no hay petición;
  - un envío a la vez (el segundo se ignora), con el botón deshabilitado y spinner;
  - tras el éxito, confirmación («Entrada registrada: N × nombre (SKU)» / «Salida registrada: …») y formulario limpio (`key = formKey`) **con el activo del enlace** (`formInitialAssetId`); sin `?asset_id=`, el selector vuelve a estar vacío;
  - el reparto de errores entre los campos y el aviso general está en `lib/inventory-form-errors.ts`.
- **Salida de activos:**
  - orden de los campos: Activo, **Stock actual** (solo lectura, antes de la cantidad), Oficina (solo lectura), Tipo de salida («Asignación» / «Consumo», que envían `allocation` / `consumption`), Asignado a y Cantidad;
  - el activo elegido y su stock viven en `hooks/use-outbound-form.ts`: al elegirlo se lee su `current_stock` (`GET /inventory/products/{id}`), abortando la lectura anterior y descartando las respuestas tardías (contador; también con A → B → A);
  - **Cantidad** queda deshabilitada hasta conocer el stock (`quantityEnabled`); si la lectura falla, se habilita con el aviso «No se pudo consultar el stock»;
  - una cantidad mayor que el stock (`lib/stock-check.ts` → `exceedsStock`) muestra una advertencia en un contenedor `aria-live` que **no bloquea** el envío (la API es la autoridad);
  - «Asignado a» solo es visible y obligatorio con una asignación (con un consumo se envía `null`; si llegase un error de ese campo, va al aviso general);
  - el 400 `insufficient_stock` va bajo Cantidad con el `detail` de la API y `role="alert"` (`FieldMessages` con `alert`);
  - tras una salida correcta se vuelve a leer el stock del activo con el que se monta el formulario, y tras un 400 de stock, el del activo elegido (sin vaciar el valor mostrado).
- **Errores (excepción acotada a `/inventory` a la regla de textos fijos):**
  - **4xx (salvo 401 y 422) o 5xx con un cuerpo `{detail, code}` legible:** un título en español y el `detail` de la API, como **texto plano**, en un elemento visible. `insufficient_stock` va **junto al campo Cantidad**. Si `detail` no es un texto (objeto, lista, vacío), se descarta y se usa el texto fijo.
  - **Sin cuerpo legible** (red, timeout, respuesta que no es JSON o fuera de contrato): los textos fijos en español del backoffice, sin código HTTP ni detalles técnicos.
  - **422:** junto a cada campo (según `loc`), un texto propio en español y, debajo, en texto secundario plano, el `msg` de la API (sin el prefijo `Value error, `, solo si es texto no vacío de hasta 300 caracteres; si no, solo el texto propio). Opción 3, elegida por el usuario para cumplir el brief («extrae el mensaje de error del cuerpo»).
  - **401:** el flujo de sesión caducada de siempre.
  - Lo cubre `tests/inventory.service.test.mjs` (500 y 503 con `detail` → visible; 500 sin JSON y `detail` de tipo objeto → texto fijo).
- **Nivel de stock:** 0 = «Agotado», de 1 a 5 = «Bajo», más de 5 = «Suficiente», con texto o icono además del color; umbrales en una función pura documentada.
- **Historial:** solo lectura (sin botones, enlaces, formularios ni textos de editar o borrar), en el orden de la API (la más reciente primero). Columnas: Tipo (`order-type-badge.tsx`: «↓ Entrada» y «↑ Salida», con icono, texto y color distintos), Activo (nombre y SKU), Cantidad, Oficina, Detalle («Proveedor: …», «Asignación → …» o «Consumo»), Fecha (`Intl.DateTimeFormat('es-ES')` en la zona del navegador, dentro de `<time dateTime>` con el ISO completo) y Usuario (el `user_uuid` completo, en monoespaciada y con `break-all`). Formato en `lib/order-format.ts`.
- **Arquitectura:** cada página es un Server Component (metadata) que renderiza una vista `'use client'` de `components/inventory/`, que solo interactúa con su hook de `hooks/` (reducer puro + sesión sin React + hook, como `/incident-manager`) → `services/inventory.service.ts` → `lib/inventory-api-client.ts`:
  - Activos: `asset-list-view.tsx` → `use-inventory-assets.ts` (también da la lista del selector);
  - Entrada: `inbound-form-view.tsx` → `use-inbound-form.ts` + `use-inventory-assets.ts`;
  - Salida: `outbound-form-view.tsx` → `use-outbound-form.ts` + `use-inventory-assets.ts`;
  - Historial: `order-history-view.tsx` → `use-inventory-orders.ts`.
  - Las páginas de Entrada y Salida son asíncronas: leen `?asset_id=` de `searchParams` (una promesa en Next 16, `PageProps<'/…'>`) y son dinámicas. Una ruta nueva necesita `npx next typegen` antes de `tsc`.
- **Tests:** `tests/inventory-*.test.mjs`, `tests/use-inventory*.test.mjs` y las reglas del inventario de `tests/production-source.test.mjs` (una ruta `/inventory/...` solo en el servicio y en `lib/inventory-routes.ts`; el argumento de `PageProps<'…'>`/`LayoutProps<'…'>` no cuenta). Jest: `__tests__/utils/{inventory.service,stock-level,stock-check,order-format}.test.ts`. Los componentes se validan con `tsc`, `lint`, `build` y el navegador.

## Autenticación (AUTH-02)

Autorizada por el ticket AUTH-02 ([`docs/auth-frontend.md`](../../docs/auth-frontend.md)). Contrato HTTP: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte C (`POST /auth/login`, `POST /users`, `GET /auth/me`, `PUT /profiles/me`). Mismas reglas que `/incidents` para no inventar campos ni endpoints.

- **Vistas:** `/login` y `/register` (públicas), `/account/profile` (protegida). Server Components con metadata que renderizan vistas cliente de `components/auth/`.
- **Token en `localStorage` (excepción a "sin persistencia en el navegador"):** exigido por el ticket. Solo `lib/auth-token.ts` toca `localStorage` y solo guarda el JWT; `tests/production-source.test.mjs` lo comprueba. Nunca se guardan datos de usuario, proveedores ni incidentes.
- **Cliente HTTP:** `lib/api-client.ts` adjunta `Authorization: Bearer <token>` a toda petición salvo las marcadas `skipAuth` (login y registro) y, ante un 401 de una petición protegida, borra el token y lanza `ApiUnauthorizedError` (los servicios lo traducen a `session_expired`). Es el único lugar que construye esa cabecera (test estático). Ninguna vista repite esta lógica.
- **Protección global:** `components/auth/auth-guard.tsx` en el layout raíz, con la sesión de `components/auth/session-provider.tsx` (`hooks/use-auth-session.ts`). Toda ruta es protegida salvo `PUBLIC_PATHS` de `lib/auth-routes.ts`: una vista nueva queda protegida sin tocar nada. La sesión se valida una vez por token con `GET /auth/me`; sin token o tras un 401 se redirige a `/login`. Si la validación falla por otro motivo (red, timeout, servidor, configuración o respuesta inesperada), el guard muestra un texto según el tipo de error (`sessionErrorCopy`), con «Reintentar» y «Cerrar sesión». Al reintentar, el estado pasa a `retrying` (acción `validation_started`), el aviso se mantiene y el botón muestra la carga. **Prohibido** usar middleware/proxy de Next.js o cookies para esta comprobación.
- **Capas:** vistas → `hooks/use-auth-form.ts` (login y registro comparten hook) / `hooks/use-profile.ts` → `services/auth.service.ts` (login y registro comparten el paso de login: el token solo se guarda si la respuesta es válida) → `lib/api-client.ts`. `unknown` solo en `services/normalizers.ts`.
- **Errores:** mensajes fijos por tipo (`components/auth/auth-error.tsx`); los 422 (y el 409 de email ya registrado) se muestran junto a su campo con el `msg` de la API. Nunca se muestra la contraseña ni el token.
- **Contraseñas (AUTH-03, [`docs/auth-password-reset.md`](../../docs/auth-password-reset.md); contrato en `services/api/SPECS.md` Parte D):** `/forgot-password` (pública), `/reset-password` (abierta: `OPEN_PATHS`, con o sin sesión, porque llega desde el enlace del email) y `/account/change-password` (protegida), más el enlace "¿Olvidaste tu contraseña?" en `/login`. Mismas capas (`hooks/use-auth-form.ts` → `services/auth.service.ts`). `/forgot-password` muestra siempre la misma confirmación tras un 200 y queda desactivado. La confirmación de la contraseña nueva se comprueba en el servicio antes de llamar a la API y nunca se envía. `/reset-password` lee `?token=` una vez, lo quita de la URL y usa `referrer: no-referrer`; el 400 `invalid_reset_token` muestra el error y un enlace a `/forgot-password`. El 400 `incorrect_password` se muestra en el campo de la contraseña actual (no cierra la sesión).

## Docker (#infra-40)

Desde el ticket #infra-40, el backoffice se arranca **solo con Docker**, en el contenedor de interfaces (`uis/Dockerfile`, `uis/start.sh`), en el **puerto 3001** (el 3000 es del website). Guía: [`docs/local-development.md`](../../docs/local-development.md); revisión: [`docs/infra-40-review.md`](../../docs/infra-40-review.md).

- **Rewrite `/backend`:** `next.config.ts` reenvía `/backend/:path*` a `API_INTERNAL_URL` (`http://api:8000`, el nombre del servicio en la red de Docker), solo si esa variable existe; sin ella, `rewrites()` devuelve `[]`. El navegador usa `NEXT_PUBLIC_API_URL=/backend` y `NEXT_PUBLIC_INVENTORY_API_URL=/backend`: mismo origen, sin CORS. `lib/api-client.ts` no cambia: concatena la base (también relativa) y la ruta.
- **`API_INTERNAL_URL` es solo de servidor:** sin el prefijo `NEXT_PUBLIC_`, nunca llega al JavaScript del navegador. Se lee al arrancar `next dev`; con `next start`, los rewrites salen del `routes-manifest.json` de `next build`, así que en un build de producción tendría que estar definida al construir.
- **Variables:** el contenedor `ui` solo recibe `API_INTERNAL_URL`, las dos `NEXT_PUBLIC_*` y `WATCHPACK_POLLING`, desde el `.env` de la raíz (ningún secreto de la API). Un `.env.local` del host montado en el contenedor lo carga Next, pero pierde ante el entorno del proceso (`process.env` va primero): no usarlo.
- **`next dev --webpack`** (en `uis/start.sh`): dentro del contenedor, Turbopack no aplica los cambios del código montado; webpack con **`WATCHPACK_POLLING=true`** recarga en unos 2 s. Por eso `next.config.ts` no lleva `watchOptions`.
- **`node_modules` y `.next`** van en volúmenes anónimos del contenedor (los del host son de Windows). Tras cambiar `package-lock.json`: `docker compose up -d --build -V`.
- **Tests:** siguen en el host (fila de `uis/backoffice` de `AGENTS.md` §4). `tests/next-config.test.mjs` cubre el rewrite y que no vuelva `watchOptions`.

## Stack

- Next.js (App Router), TypeScript estricto, Tailwind CSS v4 (config vía CSS, sin `tailwind.config.ts`) — mismo stack que `uis/talent-pipeline-tracker`, decisión registrada en `memory-bank/techContext.md`.
- Solo hooks nativos de React si se añade estado. Prohibido Redux, Zustand, Recoil, Jotai u otra librería de estado externa.
- No añadir ninguna dependencia nueva sin autorización explícita.
- **Excepción autorizada por AUTH-088:** `jest`, `ts-jest` y `@types/jest` (solo `devDependencies`), para los tests de Jest de la lógica TypeScript (`__tests__/**/*.test.ts`, configuración en `jest.config.mjs`, `npm run test:jest`). Nada más: ni `jest-environment-jsdom` ni `ts-node`. Los tests de `node:test` siguen en `tests/*.test.mjs`, y Jest no los recoge. Las utilidades del frontend que se prueben con Jest van en `__tests__/`. Plan y cobertura: `services/api/TESTING.md` §10.
- Prohibido `any`.

## Arquitectura

- Al consumir una API propia (hoy: análisis de incidentes, directorio de proveedores, gestor de incidencias e inventario), seguir el mismo patrón de frontera de confianza que `uis/talent-pipeline-tracker`: `services/normalizers.ts` como único lugar con `unknown` de red, errores tipados en `lib/api-client.ts`, y componentes sin HTTP directo.
- **Límites de error (Next 16):**
  - `app/error.tsx` se muestra dentro del layout raíz, así que la cabecera, la sesión y el guard siguen activos. `app/global-error.tsx` solo actúa si falla el propio layout raíz: tiene su propio `<html>`/`<body>`, importa `globals.css` y no puede usar la sesión ni el guard. `app/not-found.tsx` cubre las rutas inexistentes.
  - Los tres usan textos fijos en español y llevan enlace a `/`. Los dos límites de error son Client Components con «Reintentar», que llama a `retry()`. Firma de props de Next 16.3: `{ error: Error & { digest?: string }; retry: () => void }`; `reset` existe, pero la documentación recomienda `retry`.
  - **El error no se lee:** ni `console.*`, ni `error.message`, `digest` o `stack`.
  - React sigue registrando en la consola del navegador los errores que capturan los límites, con su mensaje. Por eso ningún error lanzado en el código de producción puede llevar datos de la API o del usuario en su mensaje.
  - `tests/production-source.test.mjs` lo comprueba.
- **Textos de error sin detalles técnicos:** ningún texto de `components/` ni `app/` muestra variables de entorno (`NEXT_PUBLIC_*`), rutas del repositorio (`services/api`) ni códigos HTTP entre paréntesis. (Única excepción acotada: `/inventory` muestra el `detail` de texto de la API en sus 4xx/5xx; ver su sección.) Los avisos usan textos neutros con una acción («Inténtalo de nuevo», «Avisa al equipo técnico») y mantienen la distinción por tipo de error. No hay contacto de soporte porque el contexto no define ninguno: no se inventa. Lo comprueba `tests/production-source.test.mjs`.
- **Contenedores con scroll horizontal:** todo `overflow-x-auto` de `components/` lleva también `relative`. Así los elementos `position: absolute` de dentro (p. ej. `sr-only`) quedan recortados y no ensanchan la página; sin él, `/incident-manager` tenía scroll horizontal a 375 px. Lo comprueba `tests/production-source.test.mjs`, con una lista explícita de excepciones pendientes (`/suppliers`, `/incidents`).

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
