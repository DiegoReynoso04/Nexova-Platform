# Plan de Telemetría — F0: inventario, desajustes y decisiones

**Estado: F0 cerrada, pendiente de que el usuario decida D1–D14.** Documento de trabajo, no el entregable: el plan (`telemetry-plan.md`) y los esquemas (`event-schemas.json`) se escriben en las fases siguientes, con las decisiones tomadas. **No se ha escrito código de instrumentación.**

- **Fuentes, por orden:**
  - BRIEFING de telemetría: [`docs/proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md`](../proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md). Es la fuente de verdad de las métricas obligatorias, las entidades y los identificadores.
  - Enunciado literal: [`telemetry-brief.md`](./telemetry-brief.md).
  - Modelo real: `services/api/SPECS.md` (Partes C, D, F y G) y el código de `services/api` y `uis/backoffice`, leído en `main` en `390d3aa` (PR #27 mergeada).
  - CONTEXT del Hito 5: [`docs/context-nexova-gestion-inventario-hito-5.md`](../context-nexova-gestion-inventario-hito-5.md).
- **Comprobado ejecutando, no solo leyendo:** las respuestas a los intentos de editar el stock (§3, M6). Se usó la app real con SQLite en memoria, con el soporte de los tests (`tests/inventory_support.py`) y un script temporal fuera del repo. No se tocó Supabase ni ninguna base de la demo.
- **Notación:** las rutas de archivo son relativas a la raíz del monorepo; `api/` = `services/api/app/`, `bo/` = `uis/backoffice/`.

---

## 1. Inventario de puntos de instrumentación: flujo de inventario

Recorrido: login → `/inventory/products` → entrada → salida → historial. **Hoy no se emite ningún evento.** Lo único que queda es una línea de timing por petición (`api.timing`), el access log de uvicorn y los logs de error (`nexova.api`, solo la clase de la excepción).

### 1.1 API (`services/api`)

| # | Punto | Archivo:línea | Qué ocurre hoy | Evento candidato |
|---|---|---|---|---|
| I1 | Login correcto | `api/routes/auth.py:46-50` | devuelve el JWT (`sub`, `iat`, `exp`; sin `jti`) | `user_logged_in` |
| I2 | Login fallido | `api/routes/auth.py:39-45` | 401 `invalid_credentials`; mismo error para email desconocido, contraseña incorrecta, email mal formado o usuario inactivo | `login_failed` |
| I3 | Token ausente, mal formado o caducado | `api/auth/dependencies.py:53-64` | 401 `not_authenticated` en cualquier ruta protegida. No distingue «caducado» de «inválido» (`decode_access_token` devuelve `None`, `api/auth/security.py:84`) | `session_expired` (servidor) |
| I4 | Listado de activos | `api/modules/inventory/router.py:84-86` → `service.list_assets` (`service.py:72-75`) | lectura con caché de 60 s (`api/core/cache.py:56-78`: el acierto vuelve en la línea 70; el fallo calcula en la 72) | `cache_lookup_recorded` (técnico) |
| I5 | Detalle de un activo (stock en la Salida) | `router.py:102-105` → `service.get_asset` (`service.py:78-83`; 404 en la 81) | igual que I4; el 404 no se guarda | ídem + `api_error_returned` |
| I6 | Alta de activo | `router.py:89-98` → `service.create_asset` (`service.py:90-113`; 409 en la 99 y la 110) | 201 con `current_stock: 0`; invalida la caché (`router.py:97`) | `product_created` |
| I7 | **Orden de entrada** | `router.py:108-123` → `service.add_inbound_order` (`service.py:161-174`: 404 en la 168, `office_mismatch` en la 170) → commit en `service.py:202` | 201; invalida la caché (`router.py:122`) | **`inbound_order_created`** (después del commit) |
| I8 | **Orden de salida** | `router.py:126-146` → `service.add_outbound_order` (`service.py:177-195`): bloqueo `FOR UPDATE` (184), 404 (186), `office_mismatch` (188), **stock disponible calculado (189)**, `insufficient_stock` (190-191) → commit en `service.py:215` | 201; invalida la caché (`router.py:145`) | **`outbound_order_created`** |
| I9 | **Cruce del umbral mínimo** | **no existe en la API.** El único sitio donde se conocen el stock antes (`available`, `service.py:189`) y después (`available − quantity`) de una salida, dentro de la transacción y bajo `FOR UPDATE`, es `add_outbound_order` | — | **`stock_threshold_triggered`** (M5, D4) |
| I10 | Salida rechazada por stock | `service.py:190-191` (`InsufficientStockError`, 400) | `detail` literal con el **nombre del activo** | `outbound_order_rejected` |
| I11 | Orden rechazada por oficina | `service.py:170` y `service.py:188` (`OfficeMismatchError`) | 400 | `inbound_order_rejected` / `outbound_order_rejected` |
| I12 | Validación fallida (422) | `api/core/errors.py:230-233` (`_validation_exception_handler`) | 422 con `{loc, msg, type}` saneado; sin `input` | `inventory_validation_failed` (solo `loc` y `type`) |
| I13 | **Intento de editar el stock** | `api/core/errors.py:207-217` (405 de Starlette) y `errors.py:230-233` (422 `extra_forbidden`) | ver M6 | **`direct_stock_edit_rejected`** |
| I14 | Historial | `router.py:149-151` → `service.list_orders` (`service.py:220-234`) | sin caché | `order_history_viewed` (mejor en el frontend, F5) |
| I15 | Base del inventario caída | `api/core/errors.py:220-227` (`_database_unavailable_handler`) | 503 `storage_unavailable` + log `storage inventory is unavailable: <Clase>` | `storage_unavailable_detected` |
| I16 | 500 no previsto | `api/core/errors.py:243-271` (`InternalErrorMiddleware`, log en la 271) | 500 opaco | `api_error_returned` (`status = 500`) |
| I17 | Duración de cada petición | `api/core/timing.py:38-45` | log `GET /inventory/products → 200 \| 3.0ms`. **Usa `request.url.path`, no la plantilla de la ruta**: `/users/<uuid>` y `/api/incidents/<uuid>` salen con el id | `api_latency_recorded` |

### 1.2 Frontend (`uis/backoffice`)

| # | Punto | Archivo:línea | Qué ocurre hoy | Evento candidato |
|---|---|---|---|---|
| F1 | Envío del login | `bo/services/auth.service.ts:277` (vía `bo/hooks/use-auth-form.ts:50`) | guarda el token solo si la respuesta es válida | (lo cubre la API: I1/I2) |
| F2 | Redirección sin sesión | `bo/components/auth/auth-guard.tsx:26` | `router.replace('/login')` | `session_expired` (cliente, `reason = redirect`) |
| F3 | **401 global** | `bo/lib/api-client.ts:253-256` | borra el token y lanza `ApiUnauthorizedError`; los servicios lo traducen a `session_expired` (p. ej. `bo/services/inventory.service.ts:254`) | `session_expired` (cliente) |
| F4 | **Único `fetch`** (punto de correlación) | `bo/lib/api-client.ts:205` (transporte), `212-221` (cabeceras), `225-270` (`send`, con timeout y aborto) | no hay cabecera de correlación | origen del `requestId` (D8) |
| F5 | Navegación entre secciones | `bo/components/ui/nav-link.tsx:33-34` (`usePathname`); subnavegación en `bo/components/inventory/inventory-nav.tsx` | sin registro | `page_viewed` |
| F6 | Carga de activos / historial | `bo/hooks/use-inventory-assets.ts:99`, `bo/hooks/use-inventory-orders.ts:99` | estados cargando/error/datos | `page_load_recorded` (tiempo hasta datos) |
| F7 | **Nivel de stock (solo presentación)** | `bo/lib/stock-level.ts:18-26` (`LOW_STOCK_MAX = 5`); pintado en `bo/components/inventory/stock-level-badge.tsx:23`, desde `asset-table.tsx:48` y `outbound-form.tsx:61` | se recalcula en cada render | **no** es el disparador de `stock_threshold_triggered` (M5) |
| F8 | Validación en cliente (sin petición) | `bo/services/inventory.service.ts:289` (entrada) y `:305` (salida) | si falla, no hay red | `inventory_form_validation_failed` |
| F9 | Advertencia «la cantidad supera el stock» | `bo/components/inventory/outbound-form.tsx:95` → `bo/lib/stock-check.ts:11` | aviso que no bloquea | `stock_warning_shown` (debounce, D12) |
| F10 | Envío de la entrada | `bo/hooks/use-inbound-form.ts:102` (inicio), `:107` (éxito), `:110` (fallo) | — | `form_submitted` / `form_abandoned` |
| F11 | Envío de la salida | `bo/hooks/use-outbound-form.ts:204`, `:210`, `:215` | — | ídem |
| F12 | Errores de la API mostrados | `bo/services/inventory.service.ts:216-243` (422 por campo; `api_error` con `code`; `insufficient_stock` → `quantity` en la línea 72) | — | (los cubre la API; el cliente añade el `requestId`) |
| F13 | Límites de error | `bo/app/error.tsx:23`, `bo/app/global-error.tsx:25`, `bo/app/not-found.tsx:9` | texto fijo; el error **no se lee** (regla de `bo/CLAUDE.md`) | `frontend_error_captured`, `page_not_found_viewed` |
| F14 | Logout | `bo/components/auth/account-nav.tsx:46` → `bo/hooks/use-auth-session.ts:210` | borra el token | `user_logged_out` |

**Puntos del flujo de inventario (el enunciado pide al menos 5):** I7, I8, I9, I10–I12 y I13, más F8–F11 del lado del cliente. **El frontend no tiene ninguna vía para editar el stock.** Por eso `direct_stock_edit_rejected` solo lo puede producir quien llame a la API directamente: `/docs`, `curl` o un script.

---

## 2. Inventario de puntos de instrumentación: resto de la aplicación

| Área | Punto | Archivo:línea | Evento candidato |
|---|---|---|---|
| Auth | Registro (`POST /users`: 201, 409, 422) | `api/routes/users.py:21-30` | `user_registered`, `registration_failed` |
| Auth | Validación de sesión (`GET /auth/me`) | `bo/hooks/use-auth-session.ts:158` (`validation_started`) y `:168` | `session_validated` / `session_expired` |
| Auth | Forgot password | `api/routes/auth.py:91-105`; auditoría en `api/auth/service.py:144` (email desconocido) y `:149` | `password_reset_requested` |
| Auth | Reset password (token válido / desconocido / caducado / usado) | `api/routes/auth.py:107-111`; `api/auth/service.py:156` (rechazo con `reason`) y `:158` | `password_reset_completed`, `password_reset_rejected` |
| Auth | Change password (actual incorrecta → 400) | `api/routes/auth.py:114-120`; `api/auth/service.py:163` y `:167` | `password_changed`, `password_change_rejected` |
| Auth | Fallo de envío del email (Resend) | `api/core/errors.py:277-284` (`log_email_delivery_failure`) | `email_delivery_failed` |
| Auth | 403 (permiso por rol o recurso ajeno) | `api/auth/dependencies.py:71-87` | `access_denied` |
| Proveedores | Alta, listado con filtros, tarifa, estado, borrado | `api/routes/suppliers.py:33-72`; formulario `bo/components/suppliers/supplier-create-form.tsx:71`; validación `bo/services/suppliers.service.ts:210` | `supplier_created`, `supplier_rate_updated`, `supplier_status_changed`, `supplier_list_filtered` |
| Gestor de incidencias | Alta (400 propio), listado con filtros, resumen, cambio de estado (transición inválida → 400) | `api/modules/incident_manager/router.py:207-226`, `:228-251`, `:253-258`, `:269-302`; formulario `bo/components/incident-manager/incident-form.tsx:67` | `incident_created`, `incident_status_changed`, `incident_status_change_rejected` |
| Análisis de incidentes (`/incidents`) | Subida del CSV (400, 413, 415, 422) y exportación (404 `no_analysis`) | `api/modules/incidents/router.py:26-51` y `:53-60`; 413 en `api/core/limits.py:41-42`; vista `bo/hooks/use-incident-analysis.ts` | `incident_analysis_completed`, `incident_analysis_rejected`, `incident_results_exported` |
| Navegación | Cabecera y subnavegación | `bo/components/auth/account-nav.tsx`, `bo/components/ui/nav-link.tsx:33` | `page_viewed` |
| Abandono | Formularios de alta de proveedor, entrada, salida, registro de incidencia, registro de usuario | los de arriba + F10/F11 | `form_started`, `form_abandoned` |
| Errores de frontend | Límites de Next | F13 | `frontend_error_captured` |
| Salud técnica | Timing | I17 | `api_latency_recorded` |
| Salud técnica | 503 `storage_unavailable` (TinyDB: `suppliers`, `auth`, `incidents`; PostgreSQL: `inventory`) | `api/core/errors.py:287-294` (`log_storage_failure`) e I15 | `storage_unavailable_detected` |
| Salud técnica | Caché: acierto, fallo e invalidación | `api/core/cache.py:56-78` (acierto en la 70) y `:80` (`invalidate`) | `cache_lookup_recorded` (agregado, D12) |
| Salud técnica | Arranque fallido del inventario | `api/modules/inventory/database.py:44` (`InventoryStartupError`, SPECS F2-4) | `api_startup_failed` |

### 2.1 Qué se puede reutilizar

- **Auditoría de contraseñas (AUTH-03):**
  - `AuditEvent` (`api/auth/models.py:223-230`: `reset_requested`, `reset_completed`, `reset_rejected`, `password_changed`, `password_change_rejected`) en la tabla `password_audit` de `auth.json`.
  - Se pueden reutilizar los **puntos de emisión** (`api/auth/service.py:144-167`) y el vocabulario de `reason` (`unknown_email`, `unknown`, `expired`, `used`).
  - Lo que **no** se puede reutilizar es su almacenamiento: guarda la **IP** y no tiene ni retención ni endpoint de lectura (SPECS §27).
- **Middleware de timing (`api/core/timing.py`):**
  - ya es el más externo y ve también los 500 convertidos: es el sitio natural para `api_latency_recorded` y para asignar el `requestId`;
  - le falta la **plantilla de la ruta** (`request.scope["route"].path`) en lugar del path real.
- **`X-Request-…`:** no existe ninguna cabecera de correlación, ni en la API ni en el frontend (búsqueda sin resultados en `services/api` y `uis/backoffice`).
- **`user_uuid` en las órdenes:** cada `AssetEntry`/`AssetExit` ya guarda el id del usuario de TinyDB (`service.py:171` y `:192`). Es el `userId` del envelope, el mismo valor que el `sub` del JWT.
- **Formato de errores `{detail, code}`:** el `code` es un vocabulario cerrado y estable (SPECS §4). Sirve como propiedad `error_code` sin copiar nunca el `detail`.
- **Reglas de privacidad ya vigentes:** no registrar bodies, query strings ni mensajes de excepción (SPECS §5 y §44), y en el frontend no leer `error.message` (`bo/CLAUDE.md`). La telemetría las hereda.

---

## 3. Desajustes con el BRIEFING

**M0 (de contexto, el que más pesa):** el BRIEFING y el CONTEXT del Hito 5 describen inventarios distintos.

- **BRIEFING:** «material de formación y certificación» y «kits de incorporación (laptops, credenciales, manuales)», organizados por programa.
- **CONTEXT del Hito 5 (lo implementado):** «hardware y material» de IT y operaciones: portátiles, ratones, hubs, papel y un cuaderno de formación.

Las dos fuentes son válidas según `.agents/rules/nexova-context.md`. Los eventos obligatorios deben usar los identificadores del BRIEFING (enunciado: «deben coincidir exactamente»), pero el modelo y los datos son los del Hito 5. Casi todos los desajustes siguientes salen de aquí.

| # | Campo o métrica del BRIEFING | Modelo real (verificado) | Qué falta |
|---|---|---|---|
| M1 | `product_category` ∈ `training_kit` / `certification` / `onboarding_equipment` | `AssetCategory` ∈ `hardware` / `peripherals` / `office_supplies` / `training_materials` (`api/modules/inventory/vocabulary.py:19-23`; `CHECK` en la base, SPECS §39). **Confirmado** | Una correspondencia que no es 1:1. `training_materials` podría ser `training_kit` o `certification` según el ítem; `hardware` y `peripherals` serían `onboarding_equipment` solo si se entregan en una incorporación; `office_supplies` (papel) no encaja en ninguna |
| M2 | `office` ∈ `valencia` / `miami` | `Office` ∈ `Valencia` / `Miami` (`vocabulary.py:26-28`). **Confirmado** | Solo cambia la caja: la correspondencia es 1:1 y sin pérdida |
| M3 | `programme_id` (ej. `ventas-b2b`, `liderazgo-basico`) | **No existe** en el modelo, ni en los schemas ni en la base. **Confirmado**. Tampoco hay catálogo de programas en ninguna fuente: los del BRIEFING son ejemplos («ej.») | Un campo y su catálogo. Los valores no se inventan |
| M4 | coste unitario y `currency` (`EUR`/`USD`), y `kit_cost_variance_detected` | `AssetEntry` = `asset_id`, `quantity`, `supplier` (texto libre), `office`, `created_at`, `user_uuid` (SPECS §39). **Sin coste ni moneda. Confirmado.** Además, `supplier` es texto libre: no referencia el directorio de proveedores (TinyDB), que sí tiene `currency`, pero es la de la tarifa del servicio, no un coste de material | Coste unitario por entrada, moneda, una clave estable «mismo material/proveedor», el umbral de variación (el BRIEFING da «ej. 10%») y la definición del histórico |
| M5 | `stock_threshold_triggered`: «cae por debajo del **mínimo configurado**» | Solo existe `LOW_STOCK_MAX = 5` en el frontend (`bo/lib/stock-level.ts:18`; D6 del plan del frontend, decisión del usuario), aplicado igual a todos los activos, y **solo para pintar**. La API no tiene ningún umbral. **Confirmado** | Un mínimo configurable en el backend, su semántica («por debajo» frente a «Bajo» = 1–5) y el punto de detección |
| M6 | `direct_stock_edit_rejected` | No hay endpoint de edición de stock. Medido con la app real (SQLite en memoria): ver la tabla siguiente | Una definición operativa (D5) |
| M7 | `product_id` | `Asset.id` (entero, PK) y `Asset.sku` (texto, `UNIQUE`). Ninguno de los dos se puede editar | Elegir cuál es el `product_id` (D6) |
| M8 | `quantity` | Existe (entero de 1 a 2 147 483 647) | Nada |
| M9 | `InboundOrder` / `OutboundOrder` | `AssetEntry` / `AssetExit` (SPECS §36) | Nada: los eventos usan los nombres del BRIEFING (`inbound_order_created`…), como ya hace la equivalencia del §36 |
| M10 | Destinatario de la salida («cliente, candidato, consultor o agente de soporte») | Solo `exit_type` (`allocation`/`consumption`) y `assigned_to` (texto libre: «Nombre o ID del empleado», CONTEXT) | El tipo de destinatario no está modelado, y `assigned_to` es PII (D9) |
| M11 | Dashboard de Elena: «matrículas por programa, tasa de finalización» | El repositorio no tiene ningún dato de matrículas ni de finalización | Fuera del alcance de esta telemetría: el inventario no puede medirlo (ir a la sección de exclusiones del plan) |

**M6 — qué responde hoy la API a un intento de fijar el stock** (medido, con y sin token):

| Petición | Respuesta | ¿Antes o después de la autenticación? |
|---|---|---|
| `PUT /inventory/products/{id}` con `{"current_stock": 50}` | **405** `method_not_allowed`, `Allow: GET` | **Antes**: también **sin token** da 405. El router no llega a ejecutar `get_current_user` |
| `PATCH /inventory/products/{id}` | 405, `Allow: GET` | antes |
| `DELETE /inventory/products/{id}` | 405, `Allow: GET` | antes |
| `PUT /inventory/products` | 405, `Allow: GET` | antes. *Hallazgo lateral: la colección admite `GET` y `POST`, pero `Allow` solo dice `GET`. Starlette devuelve los métodos de la primera ruta que coincide, y SPECS §4 dice «con los métodos permitidos». Fuera de este ticket* |
| `POST /inventory/products` con `current_stock` en el body | **422**, `loc: ["body", "current_stock"]`, `type: extra_forbidden` | **después**: sin token, 401 |
| `POST /inventory/orders/inbound` o `/outbound` con `current_stock` | 422 `extra_forbidden` en `current_stock` | después |
| `PATCH /inventory/products/{id}/stock` | 404 `not_found` (la ruta no existe) | antes |
| Entrada con `quantity: -5` («ajuste» negativo) | 422 en `quantity` (`greater_than_equal`) | después. Es una validación fallida, no una edición directa |
| SQL directo en Supabase o la Data API pública | la API no lo ve. La Data API (`anon`/`authenticated`) la bloquea RLS sin políticas (SPECS F2-5) | — |

---

## 4. Decisiones

Cada decisión trae opciones, una recomendación y su porqué. Las que dependen de un dato de negocio que no fija ninguna fuente lo dicen expresamente: ese dato **lo decide el usuario** y no se inventa.

### D1 — `product_category`: correspondencia o vocabulario nuevo

- **A. Tabla de correspondencia en la capa de telemetría** (`AssetCategory` → BRIEFING). No toca el modelo. Pero es una correspondencia con pérdida y ambigua (M1): `training_materials` puede ser dos cosas, `office_supplies` no es ninguna y `hardware` solo cuenta si va a una incorporación. Cualquier regla sería inventada.
- **B. Campo nuevo `product_category` en `Asset`**, con el vocabulario exacto del BRIEFING, junto a `category` (la del Hito 5, que no cambia):
  - cada activo se clasifica una vez, al darlo de alta;
  - prerrequisito de modelo: columna `VARCHAR` con `CHECK`, en `AssetCreate` y en `AssetRead`;
  - quien instrumente lee el valor; no lo deduce.
- **C. Sustituir `AssetCategory` por el vocabulario del BRIEFING.** Rompe el contrato del Hito 5: el CONTEXT dice «usa estos nombres exactamente» y el evaluador del Hito 5 lo comprueba.
- **D. Emitir la `category` actual.** Incumple «exactamente».

**Recomendación: B.** Es la única que cumple el BRIEFING sin inventar una regla de clasificación ni romper el Hito 5.

Sub-decisiones para el usuario:

- **D1-a.** Qué hacer con los activos que no son material de formación ni de incorporación (`office_supplies`; quizá `peripherals`). Recomendación: `product_category` **nulo** y fuera de las métricas obligatorias; siguen en los eventos genéricos de inventario. El schema admitiría `null` solo en esos casos y nunca un cuarto valor.
- **D1-b.** Cómo se clasifican los 6 activos sembrados del Hito 5, si se clasifican. Es un dato de negocio: lo decide el usuario o el responsable (Elena para L&D, Patricia para incorporación).

### D2 — Origen de `programme_id`

- **A. En `Asset`.** El BRIEFING dice: «cada producto… pertenece a un programa o área». Las órdenes lo heredan del activo y se agrega por programa sin tocar las órdenes.
- **B. En cada orden.** Permite que un mismo kit sirva a varios programas, pero el BRIEFING no lo pide y obliga a escribirlo en cada entrega.
- **C. Tabla `programmes` (catálogo) + FK desde `Asset`.** Lo más robusto, pero añade una entidad que ningún contexto define.
- **D. Nulo hasta que exista el catálogo.** No cumple la métrica obligatoria.

**Recomendación: A**, con el slug del BRIEFING (minúsculas y guiones, como en `ventas-b2b`) y validado contra un catálogo cerrado en el vocabulario del inventario.

- **El catálogo es un prerrequisito de negocio.** Ninguna fuente lo da: `ventas-b2b` y `liderazgo-basico` son ejemplos. Lo proporciona el usuario o Elena; no se inventa.
- **El «área»** de los kits de incorporación (Patricia; agentes de Roberto) también necesita su identificador en el mismo campo. Lo decide el usuario.

### D3 — Coste unitario, `currency` y `kit_cost_variance_detected`

- **Coste:**
  - **A.** `unit_cost` (`NUMERIC(12,2)`, > 0) en `AssetEntry`, obligatorio en las entradas nuevas.
  - **B.** Sacarlo del directorio de proveedores. No vale: su tarifa es de un servicio, no el coste de un material, y `AssetEntry.supplier` no lo referencia.

  **Recomendación: A.**
- **`currency`:** la regla está en el BRIEFING §6: `EUR` para Valencia y `USD` para Miami, sin convertir. Recomendación: **derivarla de la oficina en la API** y guardarla en la entrada, para que el histórico no dependa de que la regla siga igual; nunca la escribe el usuario. En los eventos sin importe (salidas, umbral, rechazos), `currency` va igualmente, derivada de la oficina, porque el BRIEFING la pone entre los campos mínimos de **todos** los eventos de inventario. *Alternativa: omitirla donde no hay importe. Decide el usuario.*
- **«Mismo material/proveedor»:** `supplier` es texto libre, así que «Office Depot Miami» y «office depot miami» serían proveedores distintos.
  - **A.** Normalizar el texto (recortar, minúsculas, espacios).
  - **B.** `supplier_id` hacia el directorio. Está en otra base (TinyDB, ids enteros) y obliga a que todo proveedor de material esté dado de alta.

  **Recomendación: A** para F0–F1, documentando el riesgo; B como mejora futura.
- **Umbral de variación y histórico (dato de negocio, lo decide el usuario):** el BRIEFING solo da «ej. 10%».
  - Propuesta de definición: variación = |coste nuevo − referencia| / referencia, con referencia = **media de las N entradas anteriores** del mismo par (activo, proveedor normalizado). Sin historial, no se evalúa.
  - El usuario fija el umbral, N y si cuentan solo las subidas o también las bajadas (la decisión del BRIEFING habla de «sube precios»).
- **Dónde se detecta:** en la API, al crear la entrada (después del commit de `service.py:202`), en el mismo punto que `inbound_order_created`.

### D4 — Umbral mínimo de `stock_threshold_triggered`

- **Origen:**
  - **A.** Constante global en el backend (el 5 de hoy, movido).
  - **B.** Columna `min_stock` por activo.
  - **C.** Umbral por categoría o programa.

  **Recomendación: B.** La decisión que habilita el BRIEFING es «**ajustar el umbral mínimo** de ese material», lo que supone un umbral por ítem. Sin un valor por ítem, la decisión no se puede tomar.
- **Valor por defecto (dato de negocio, lo decide el usuario):** reutilizar la decisión D6 del frontend es coherente (hoy «Bajo» = 1–5). El usuario confirma el valor.
- **Semántica:** «cae por debajo del mínimo» → se dispara cuando `stock_antes ≥ min_stock` y `stock_después < min_stock`. Es **por cruce**: no se repite en cada salida mientras siga por debajo y se rearma cuando una entrada lo devuelve a `≥ min_stock`. Para que el indicador del frontend y el evento digan lo mismo, «Bajo» pasaría a ser `0 < stock < min_stock`. *Alternativa: `≤ min_stock` y conservar el 5 tal cual. Decide el usuario; lo importante es que sea una sola regla.*
- **Dónde se detecta:** solo en la API, en `add_outbound_order` (`service.py:189-195`), que ya conoce `available` y `quantity` dentro de la transacción y bajo `FOR UPDATE`. Se emite tras el commit (`service.py:215`). **Nunca en el frontend:** `StockLevelBadge` se renderiza en cada visita, no es la autoridad y dispararía por cada render.
- **Caso adicional:** un activo nuevo nace con stock 0, por debajo de cualquier mínimo, sin haber cruzado nada. Recomendación: no disparar en el alta. Se dispara solo con una salida que cruza el umbral.

### D5 — Definición operativa de `direct_stock_edit_rejected`

Cuenta como intento rechazado de editar el stock directamente:

1. **Un método de escritura sobre el recurso activo:** `PUT`, `PATCH` o `DELETE` sobre `/inventory/products` o `/inventory/products/{id}` → 405. Se detecta en `_http_exception_handler` (`api/core/errors.py:207-217`) cuando el status es 405 y el path coincide con esas dos plantillas.
2. **Un campo de stock en el body de una escritura del inventario:** `POST` a `/inventory/products`, `/inventory/orders/inbound` o `/inventory/orders/outbound` con un error `extra_forbidden` cuyo `loc` acaba en `current_stock` → 422. Se detecta en `_validation_exception_handler` (`errors.py:230-233`).
   - *Opción B:* ampliar a una lista cerrada (`current_stock`, `stock`).
   - **Recomendación:** solo `current_stock`, el único nombre que publica la API.

**No cuentan:** el 404 de una ruta inventada (`/products/{id}/stock`: no se distingue de una errata); el 422 de una cantidad negativa (es `inventory_validation_failed`); y el SQL directo o la Data API de Supabase (invisibles para la API; ir a exclusiones).

**El problema de identidad:** el caso 1 ocurre **antes de autenticar**.

- **Opciones:**
  - **A.** Decodificar el token en el handler, de forma opcional y sin fallar (`decode_access_token`, `api/auth/security.py:84`, devuelve `None` si no es válido). Con token válido, `userId` es el usuario; si no, `null` y `authenticated = false`.
  - **B.** Contar solo los intentos autenticados.
  - **C.** Hacer que el 405 exija token antes (cambia el contrato de errores).
- **Recomendación: A.** El evento lleva `authenticated` y `attempt_kind` (`method_not_allowed` / `stock_field_in_body`).
- **`office` y `product_id`:** con un id entero válido, se leen del activo (una lectura en una ruta que ya ha fallado; el evento es raro, con throttle en D12). Sin id, o si el activo no existe, van como `null`. La decisión de Patricia («en la oficina donde ocurre») solo se puede tomar con los intentos que tienen oficina: el plan lo dirá así.
- **Por qué esta definición:** el intento de editar el stock tiene que ser **inequívoco**. Un 405 sobre el recurso con el stock o un `current_stock` en el body solo se explican así; un 404 o una cantidad mal escrita, no.

### D6 — Correspondencias deterministas: `office`, `product_id` y nombres

- **`office`:** `Valencia` → `valencia` y `Miami` → `miami`, en la función que construye el evento (1:1). **Recomendado**, sin cambiar el modelo.
- **No se confunde con `branch`:** el gestor de incidencias usa `central`, `valencia_operations`, `miami_office` y `remote`, que es otro vocabulario (sedes). Sus eventos llevan `branch` tal cual; no se traduce a `office`.
- **Idioma y oficina:** el BRIEFING §6 pide no mezclar el idioma de la interfaz con la oficina. El backoffice está solo en español, así que no se captura ninguna dimensión de idioma y nunca se deduce la oficina del idioma.
- **`product_id`:**
  - **A.** `Asset.id` (entero).
  - **B.** `sku`.

  **Recomendación: A**, emitido como entero. Es la PK, la FK de las órdenes y el `asset_id` de la API. `sku` no está en la allowlist mínima del BRIEFING y añadirlo sería redundante.

### D7 — `sessionId`

Hoy no hay sesiones de servidor: hay un JWT sin estado en `localStorage` (`bo/lib/auth-token.ts`), sin `jti`.

- **A. Claim `sid` (UUID v4) en el JWT**, creado en el login (`create_access_token`, `api/auth/security.py:74`):
  - `sessionId` = `sid` = la vida del token;
  - la API lo lee del token en cada evento autenticado;
  - el frontend **no necesita decodificarlo** si sus eventos pasan por la API (D10).
- **B. UUID generado por el frontend al hacer login**, guardado junto al token. Choca con la regla de que `lib/auth-token.ts` solo guarda el JWT, y la API no lo conocería.
- **C. Hash del token.** Estable y no reversible, pero ata el identificador al secreto y a la firma.

**Recomendación: A.** Es un prerrequisito pequeño en el backend (el claim no cambia el contrato de `Token`).

- **Eventos anónimos** (login fallido, registro, forgot/reset password, 405 sin token): `sessionId = null`, documentado en el envelope. La correlación la da el `requestId`.

### D8 — `requestId` (frontend → backend → logs)

- **A. Generado en el cliente, validado en el servidor:**
  - `lib/api-client.ts` (el único `fetch`, F4) añade `X-Request-ID` (UUID v4) a cada petición;
  - un middleware de la API (junto al de timing) lo acepta si es un UUID v4 válido y, si no, genera uno; así nunca se registra texto arbitrario (inyección en logs);
  - lo devuelve en la respuesta y lo añade a la línea de `api.timing` y a cada evento.
- **B. Solo el servidor lo genera** y lo devuelve; el frontend lo lee de la respuesta para sus propios eventos. Las peticiones que no llegan a la API (timeout, red) se quedan sin `requestId`.

**Recomendación: A** con la generación de B como reserva. Prerrequisitos:

- `X-Request-ID` en `allow_headers` y `expose_headers` del CORS (`api/main.py:111-120`) para el tracker (3002). Con Docker no hace falta, porque `/backend` es del mismo origen y el rewrite reenvía las cabeceras.
- Los eventos del frontend que no corresponden a una petición (`page_viewed`, `form_abandoned`) generan su propio UUID.

### D9 — PII

Regla del BRIEFING: nunca nombres de candidatos, clientes ni consultores. Como regla general, **nada de texto libre en `properties`**, solo identificadores y vocabulario cerrado. Propuesta por dato:

| Dato | Dónde está | Propuesta |
|---|---|---|
| Email (login, registro, forgot password, `contact_email` de proveedores, `customer_email` del CSV) | formularios, TinyDB, CSV | **Nunca**: ni en claro ni con hash (un hash de email se revierte por diccionario). Los fallos de login se cuentan sin identificar la cuenta |
| IP | `password_audit.ip` | **Nunca en la telemetría.** Ninguna decisión del catálogo la necesita, y la auditoría ya la guarda (con su residual de SPECS §27) |
| `user_uuid` / `sub` | órdenes, JWT | **En claro como `userId`.** Es seudónimo, ya está en las órdenes y hacerle hash rompería el cruce con ellas. Se trata como dato personal seudonimizado: acceso restringido y retención limitada (la duración la decide el usuario) |
| `assigned_to` (nombre o ID del empleado) | `AssetExit` | **Nunca.** Solo `exit_type` |
| `supplier` (texto libre) | `AssetEntry` | **No en `properties`.** Para la variación de coste, el par se compara en la API con el texto normalizado, y el evento lleva `product_id` y una **clave seudónima del proveedor** (HMAC con una clave del servidor), no el nombre. *Alternativa: el nombre en claro, porque es una empresa. Decide el usuario: un proveedor puede ser un autónomo con nombre propio* |
| `detail` de los errores (el de `insufficient_stock` lleva el **nombre del activo**) | respuestas de la API | **Nunca el `detail`**; solo `error_code` y cifras (`available`, `requested`) |
| `msg`/`input` de los 422 | — | Solo el nombre del campo (`loc`) y el `type`. Nunca `msg` ni el valor |
| Texto libre: título y descripción de incidencias, `notes` y nombre de proveedores, perfil (`name`, `phone`, `address`) | TinyDB | **Nunca.** Como mucho, longitudes o booleanos (`has_notes`) si una decisión lo justifica |
| URLs | navegación | Solo la **plantilla de ruta** (`/inventory/orders/outbound`, `/users/{id}`), **sin query string**. `?token=` de `/reset-password` es un secreto y `?asset_id=` no aporta |
| Contenido del CSV | `/incidents` | Solo conteos que ya devuelve la API (`AnalysisResult`) y el tamaño en bytes por tramos |
| Token, contraseñas y `hashed_password` | — | Nunca |

### D10 — Quién emite cada evento y por dónde viajan

- **Emisor autoritativo:**
  - **API:** todo lo de negocio y de seguridad (órdenes, umbral, variación, rechazos, auth, 503 y latencia). No se puede esquivar y conoce el resultado real; el frontend no ve, por ejemplo, el 405 de `curl`.
  - **Frontend:** solo lo que la API no ve: navegación, tiempos de carga, validación en cliente, abandono y límites de error.
- **Transporte de los eventos del frontend:**
  - **A.** Un endpoint propio `POST /telemetry/events` en la API (con lote, allowlist validada en el servidor y el `sid` sacado del token).
  - **B.** Un servicio de terceros. Implica un SDK, una dependencia y datos fuera.

  **Recomendación: A**, que se diseñará en el plan y se construirá en la fase de captura (no hoy).
- **`timestamp`:** ISO 8601 en UTC con `Z`. En los eventos del frontend, la hora del cliente en el envelope, y la de recepción la añade el colector (fuera del envelope).
- **Alcance:** backoffice + API. El tracker (`uis/talent-pipeline-tracker`) y el website quedan fuera de esta versión (exclusión justificada en el plan).

### D11 — Formato de `event-schemas.json` y cómo validarlo

- **Formato: JSON Schema draft-07** (recomendado por el enunciado):
  - un único archivo con `definitions.envelope` y una definición por evento (`allOf` del envelope + `properties` propias);
  - **`additionalProperties: false`** en `properties`: es la allowlist;
  - `event_type` con `const` y `schemaVersion` con `const` (semver, `"1.0.0"`);
  - enums literales del BRIEFING (`office`, `product_category`, `currency`).
- **Validación, sin añadir dependencias al repo** (no está `jsonschema` en el venv de `services/api`):
  - **A. Script con la librería estándar** (`scripts/validate_event_schemas.py` o un test de `unittest`). Comprueba:
    - que el JSON se puede leer;
    - que cada evento usa el envelope, lleva `additionalProperties: false` y sus `required` están en sus `properties`;
    - el patrón `^[a-z]+(_[a-z]+)+$` del `event_type`;
    - los enums literales del BRIEFING;
    - y que la lista de eventos coincide con las tablas de `telemetry-plan.md`.

    No valida el metaesquema draft-07 completo.
  - **B. Validador puntual con `npx` y versión fija** (p. ej. `ajv-cli@5.0.0` con `--spec=draft7`) para el metaesquema y los ejemplos del plan. No toca ningún `package.json`, pero descarga código en cada ejecución.
  - **Recomendación: A comiteado + B ejecutado una vez** y anotado en el plan (comando, versión y salida). Mismo criterio que en tickets anteriores: la comprobación permanente con la librería estándar. *Si el usuario prefiere no ejecutar nada descargado, solo A.*

### D12 — Stream frente a batch (criterios) y throttle

**Criterio** (el del enunciado: urgencia de la decisión, no preferencia técnica). **Stream** si se cumple al menos una:

1. La decisión tiene un responsable que actúa **el mismo día**: reponer, alertar o renegociar.
2. Detectar tarde **aumenta el daño**: seguridad, caída, pérdida de datos.

Todo lo que alimenta tendencias, planificación o el informe semanal de Laura va en **batch** (diario, o semanal en el informe).

Propuesta inicial para los obligatorios (se justifica uno a uno en el plan):

| Evento | Entrega | Porqué |
|---|---|---|
| `inbound_order_created` | batch diario | alimenta la planificación de producción de Elena (decisión de semanas) |
| `outbound_order_created` | batch diario | ritmo de consumo por programa. La urgencia de reponer la cubre el umbral |
| `stock_threshold_triggered` | **stream** | «acelerar la reimpresión»: cada hora sin material retrasa una entrega |
| `direct_stock_edit_rejected` | batch diario + alerta stream solo si hay ráfaga | la decisión de Patricia (capacitación o permisos) no es del mismo día, pero una ráfaga es un posible abuso de la API |
| `kit_cost_variance_detected` | **stream** | alertar a Elena y a Laura antes de comprometer más compras al precio nuevo |

**Throttle y debounce** (para los eventos de alta frecuencia):

- `api_latency_recorded`: una línea por petición, agregada en el emisor por (ruta, método, status) en ventanas de 60 s (conteo y p50/p95/máx); se emite el agregado, no cada petición.
- `cache_lookup_recorded`: igual, aciertos y fallos por espacio y ventana.
- `page_viewed`: uno por cambio de ruta, ignorando los rebotes de menos de 1 s.
- `stock_warning_shown`: debounce de 1 s sobre la cantidad escrita.
- `direct_stock_edit_rejected` y `login_failed`: tope por (ruta, `userId` o anónimo) y minuto, con un contador de los suprimidos, para que un escáner no inunde el flujo.

Los valores exactos se fijan en el plan.

### D13 — Taxonomía `entidad_accion`

- **Nombres fijos:** los cinco obligatorios llevan el nombre exacto del BRIEFING.
- **Verbos del resto** (cerrados, en participio inglés como los del BRIEFING):
  - `created`, `updated`, `changed` (estado);
  - `rejected` (lo rechaza una regla de negocio o un permiso);
  - `failed` (fallo técnico o de credenciales);
  - `triggered` (umbral), `detected` (anomalía);
  - `viewed`, `started`, `submitted`, `abandoned`;
  - `recorded` (medida técnica), `captured` (error de frontend).
- **Formato:** `snake_case`, entidad en singular y sin prefijos de capa (`api_`/`ui_`), salvo cuando la entidad es la propia capa (`api_latency_recorded`).

### D14 — Prerrequisitos de modelo: dónde quedan

Lo que piden D1–D5 y D7–D8 (columnas `product_category`, `programme_id`, `unit_cost`, `currency` y `min_stock`; claim `sid`; cabecera `X-Request-ID`; detección en los handlers) **no se implementa en este ticket**, que es solo de diseño.

- **A.** El plan los lista como **prerrequisitos** del equipo que instrumente, con su migración y su orden.
- **B.** Abrir ya un ticket aparte.

**Recomendación: A.** El plan dirá también qué eventos se pueden emitir **sin** prerrequisitos (los técnicos, de auth y de navegación) y cuáles esperan a la migración (los cinco obligatorios dependen de al menos uno). Los datos semilla del BRIEFING §5 (6–8 ítems, 3 programas, 12–15 entradas y salidas, 2 umbrales y 1 variación) solo se pueden generar después de esa migración y nunca sobre la base de la demo sin confirmación.

---

## 5. Lo que no se ha verificado

- El comportamiento contra Supabase. Se midió con SQLite en memoria; los códigos 405 y 422 no dependen de la base.
- El volumen real de peticiones por día, necesario para dimensionar los agregados de D12. No hay telemetría ni access log persistente del que sacarlo.
- Que el rewrite `/backend` de Next reenvíe `X-Request-ID`: los rewrites reenvían las cabeceras de la petición, pero no se ha probado.

## 6. Siguiente paso

Cuando el usuario decida D1–D14: `telemetry-plan.md` (catálogo completo con la frase de cada evento, envelope, allowlists, PII, stream/batch, throttle, prerrequisitos, riesgos y exclusiones) y `event-schemas.json`, más su validación (D11).
