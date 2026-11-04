# Plan de Telemetría — Nexova

Respuesta al RFI de gestión: qué datos capturar en la plataforma de Nexova, para qué decisión, con qué forma, por qué canal y qué no se captura. **Es un documento de diseño: no hay código de instrumentación.** Lo tiene que poder instrumentar otro desarrollador sin preguntar nada. Si algo no está aquí, es un hueco del plan y no una decisión implícita.

- **Esquemas:** [`event-schemas.json`](./event-schemas.json) (JSON Schema draft-07), consistente al 100 % con este documento. Lo comprueba `scripts/validate_event_schemas.py` (§9).
- **Análisis previo:** [`analysis.md`](./analysis.md) (inventario de puntos, desajustes M0–M11 y decisiones D1–D14 con sus opciones).
- **Código de referencia:** `main` en `390d3aa`. Las líneas citadas son de ese commit; si el código se mueve, manda el nombre de la función citada junto a la línea.

**Cifras: 52 eventos.** 5 son obligatorios (BRIEFING) y 47, oportunidades identificadas, en 10 categorías: inventario 9, autenticación 16, navegación 2, flujos 4, errores 3, salud técnica 3, rendimiento 2, proveedores 5, gestor de incidencias 5 y análisis de incidentes 3. 38 los emite la API y 14 el frontend. 13 van por stream y 39 por batch.

---

## 1. Alcance, fuentes y equivalencias

### 1.1 Alcance

- **Dentro:**
  - la API (`services/api`), que emite lo de seguridad y salud técnica, el resto de eventos de negocio y `direct_stock_edit_rejected`;
  - el backoffice (`uis/backoffice`), que emite navegación, flujos, rendimiento percibido, errores de render y, desde el ticket de captura, 4 de los 5 obligatorios con lo que le devuelve la API (§1.5).
- **Fuera (D10):**
  - el Talent Pipeline Tracker (`uis/talent-pipeline-tracker`): fuera de Docker, con su propio `SPECS.md` y sin ninguna métrica del BRIEFING;
  - el website público (`uis/website`): sin autenticación ni sesión, así que ni `userId` ni `sessionId`, y su analítica de marketing es otro encargo.
  - Lo que hagan contra la API sí queda medido, porque lo emite la API.
- **Fuera por diseño:**
  - los seeds y scripts (`seed-inventory`, `scripts/seed_incidents.py`, `scripts/seed_volume.py`): escriben sin pasar por las rutas y **no emiten eventos**, porque no son actividad de negocio (§8.4);
  - el SQL directo en Supabase: invisible para la API.

### 1.2 Fuentes

| Fuente | Qué aporta |
|---|---|
| [BRIEFING de telemetría](../proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md) | Las 5 métricas obligatorias (nombres exactos), los campos mínimos de inventario y sus valores, la regla de no incluir nombres de candidatos, clientes ni consultores, y las restricciones de §6 (moneda por oficina, stock solo por órdenes, idioma ≠ oficina) |
| [CONTEXT del Hito 5](../context-nexova-gestion-inventario-hito-5.md) y `services/api/SPECS.md` Parte F | Entidades, vocabulario y reglas reales del inventario |
| `services/api/SPECS.md` Partes C, D, E, G y §4–§5 | Auth, contraseñas, gestor de incidencias, caché, errores y privacidad |
| `uis/backoffice/CLAUDE.md` | Arquitectura y reglas del frontend (único `fetch`, el error no se lee, token solo en `lib/auth-token.ts`) |
| [`README.md`](../../README.md) raíz | Briefing de Nexova (responsables: Elena, Patricia, Roberto, Laura, Sergio) |

### 1.3 Equivalencias BRIEFING ↔ Hito 5 (desajustes M0–M11)

| # | BRIEFING | Modelo real | Cómo lo resuelve este plan |
|---|---|---|---|
| M0 | Inventario de material de formación y kits de incorporación, por programa | Inventario de hardware y material de IT y operaciones (Hito 5) | Se conserva el modelo del Hito 5 y se le añaden los campos del BRIEFING (P1–P3). Los eventos usan los identificadores del BRIEFING |
| M1 | `product_category` ∈ `training_kit` / `certification` / `onboarding_equipment` | `Asset.category` ∈ `hardware` / `peripherals` / `office_supplies` / `training_materials` | Columna nueva `Asset.product_category`, nullable (D1 B). `null` para lo que no es formación ni incorporación (D1-a); nunca un cuarto valor. La categoría del Hito 5 viaja aparte como `asset_category` |
| M2 | `office` ∈ `valencia` / `miami` | `Valencia` / `Miami` | Minúsculas al construir el evento (D6), sin tocar el modelo |
| M3 | `programme_id` | No existe | Columna `Asset.programme_id`, slug nullable (D2 A). Sin catálogo cerrado en el schema: lo valida un patrón |
| M4 | coste y `currency` | `AssetEntry` sin coste ni moneda; `supplier` en texto libre | `AssetEntry.unit_cost` y `AssetEntry.currency` derivada de la oficina (D3); proveedor normalizado y seudonimizado (P9) |
| M5 | «mínimo configurado» | Solo `LOW_STOCK_MAX = 5` en el frontend, para pintar | Columna `Asset.min_stock` (por defecto 5) y detección por cruce en la API (D4) |
| M6 | `direct_stock_edit_rejected` | No hay endpoint de edición; 405 antes de autenticar y 422 `extra_forbidden` | Definición operativa D5 (ficha del evento y P7) |
| M7 | `product_id` | `Asset.id` / `Asset.sku` | `product_id` = `Asset.id` (D6) |
| M8 | `quantity` | `quantity` | Igual |
| M9 | `InboundOrder` / `OutboundOrder` | `AssetEntry` / `AssetExit` | Los eventos usan los nombres del BRIEFING; equivalencia en SPECS §36 |
| M10 | Destinatario (cliente, candidato, consultor o agente) | Solo `exit_type` y `assigned_to` (texto libre, PII) | Solo `exit_type`; `assigned_to` no se emite nunca. El tipo de destinatario no está modelado (§8.1) |
| M11 | Matrículas por programa y tasa de finalización (dashboard de Elena) | No hay datos de matrículas en el repositorio | Excluido (§8.1): el inventario no lo puede medir |

### 1.4 Decisiones (tomadas por el usuario el 2026-11-02)

| ID | Decisión |
|---|---|
| D1 | `product_category` como **campo nuevo** de `Asset` (B). D1-a: `null` para lo que no es formación ni incorporación; el schema admite `null` y nunca un cuarto valor. D1-b: en este ticket no se clasifica ningún activo; es un prerrequisito del ticket de captura, junto con los datos semilla del BRIEFING §5 |
| D2 | `programme_id` en `Asset` (A), validado solo por el patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. `ventas-b2b` y `liderazgo-basico` son ejemplos del BRIEFING. El catálogo es un prerrequisito de negocio |
| D3 | `unit_cost` en `AssetEntry` (A); `currency` derivada de la oficina y presente en **todos** los eventos de inventario; proveedor normalizado (A). Parámetros configurables: umbral de variación **10 %** (el ejemplo del BRIEFING) y referencia = **media de las 3 entradas anteriores** del mismo par. Se detectan subidas y bajadas (`direction`) |
| D4 | `min_stock` por activo, **5 por defecto** y configurable. Se dispara por cruce con `<` (literal del BRIEFING) y nunca en el alta. El indicador «Bajo» del frontend se alinea en el ticket de captura |
| D5 | Intento de editar el stock = 405 de un método de escritura sobre el activo (con o sin token) o 422 `extra_forbidden` en `current_stock`. El token se decodifica de forma opcional; `office` y `product_id` pueden ser `null` |
| D6 | `office` en minúsculas; `product_id` = `Asset.id` (entero); `branch` del gestor de incidencias no se traduce a `office` |
| D7 | `sessionId` = claim `sid` (UUID v4) del JWT, creado en el login; `null` en los eventos anónimos |
| D8 | `requestId` = `X-Request-ID` (UUID v4) generado en el cliente y validado en el servidor (o generado si falta o no es válido); devuelto en la respuesta y añadido al log de timing |
| D9 | Nada de texto libre ni de emails o IP; `userId` en claro (seudónimo). Proveedor como clave **HMAC** + `inbound_order_id` en `kit_cost_variance_detected` (la renegociación se resuelve desde la base, con control de acceso). **Retención:** eventos en bruto con `userId`, 90 días; agregados sin `userId`, sin límite |
| D10 | La API emite lo de negocio y seguridad; el frontend, solo lo que la API no ve, por un colector propio `POST /telemetry/events`. Tracker y website fuera. **Modificada en el ticket de captura** para 4 obligatorios (§1.5) |
| D11 | JSON Schema draft-07 + validación con la librería estándar comiteada (A) + una ejecución puntual de `ajv-cli` con versión fija (B) |
| D12 | Stream si la decisión tiene un responsable que actúa el mismo día o si detectar tarde aumenta el daño; el resto, batch. Throttle y agregados en §7 |
| D13 | Taxonomía `entidad_accion`, verbos cerrados (§5.3) |
| D14 | Los cambios de modelo e infraestructura son **prerrequisitos** documentados aquí (§2); no se implementan en este ticket |

### 1.5 Cambios del ticket de captura (decididos por el usuario el 2026-11-03)

Análisis y opciones: [`capture-analysis.md`](./capture-analysis.md). Guía de revisión: [`capture-review.md`](./capture-review.md).

- **D1 «A ligera» — la API calcula y el frontend emite:** el enunciado de la captura evalúa que los obligatorios pasen por `track()` y se vean en la pestaña Network.
  - **Emisor:** `inbound_order_created`, `outbound_order_created`, `stock_threshold_triggered` y `kit_cost_variance_detected` pasan de API a **frontend**.
  - **Respuestas 201:** las de alta devuelven lo que solo sabe la API: el stock antes y después (bajo `FOR UPDATE`), el mínimo, la moneda, `supplier_key` y la variación de coste (SPECS Parte F, §37). Los hooks de los formularios de Entrada y Salida los emiten sin calcular nada.
  - **Riesgo aceptado:** un evento de negocio se pierde si la pestaña se cierra entre el 201 y el envío y el beacon tampoco sale (§8.4).
- **Excepción:** `direct_stock_edit_rejected` sigue siendo de la API (P7), porque la interfaz no tiene forma de provocarlo (D5). Emisor mínimo: una línea JSON en `nexova.telemetry`.
- **Prerrequisitos reducidos:**
  - **P1** (clasificación) y **P2** (mínimo por activo) quedan para más adelante. Hasta entonces, `product_category` y `programme_id` van en `null` (el esquema lo admite, D1-a) y `min_stock` sale de `INVENTORY_DEFAULT_MIN_STOCK` (5, D4), igual para todos los activos.
  - **P3** (coste y moneda, con migración aditiva), **P4** (`sid`), **P7**, **P8** (colector y `lib/telemetry.ts`), **P9** y **P10** están hechos.
  - **P5** (`X-Request-ID`) y el emisor completo de **P6** (allowlist, agregados) siguen pendientes: `requestId` es un UUID propio de cada evento.
- **Colector, fase stub:** `200 {"received": N}`, acepta cualquier evento del catálogo y no persiste (§2.4).
- **Versión:** cambiar el emisor y los prerrequisitos son metadatos (`$comment`), no propiedades: según §5.4, **`1.0.0` no cambia**.

### 1.6 Cambios del ticket de almacenamiento (decididos por el usuario el 2026-11-04)

Análisis y opciones: [`storage-analysis.md`](./storage-analysis.md). Guía de revisión: [`storage-review.md`](./storage-review.md).

- **Colector definitivo:** §2.4 pasa de `202 {accepted, rejected}` a `200 {received, stored, rejected}`, que es lo que pide el enunciado. Cualquier arreglo `events` es parseable, también vacío o de más de 50 items.
- **Allowlist:** el plan decía dos cosas. Se unifica en la regla de P6: la clave de más se quita y el valor inválido rechaza el evento.
- **Almacén:** tabla `telemetry_events`, inmutable para la API, creada con una migración explícita. Su esquema es decisión nuestra, porque el enunciado no lo incluye.
- **Riesgos aceptados:** eventos de negocio falsificables y cupo anónimo compartido (§8.4).
- **Versión:** son cambios de texto y de transporte, no de esquema: **`1.0.0` no cambia**.

---

## 2. Prerrequisitos (D14)

Nada se puede emitir hoy: no hay emisor. Los prerrequisitos se dividen en dos bloques:

- **infraestructura (P4–P6, P8):** desbloquea los 43 eventos que no dependen del modelo;
- **modelo del inventario (P1–P3, P7, P9, P10):** lo esperan los 9 eventos de inventario.

### 2.1 Lista

| ID | Qué | Dónde | Detalle |
|---|---|---|---|
| **P1** | Clasificación de activos | `services/api/app/modules/inventory/` (`models.py`, `schemas.py`, `vocabulary.py`) | En `Asset`, dos columnas nullable: `product_category VARCHAR(32)`, con `CHECK` en `training_kit` / `certification` / `onboarding_equipment`, y `programme_id VARCHAR(64)`, con el patrón slug validado en Pydantic. Las dos son opcionales en `AssetCreate` y van siempre en `AssetRead`. Los activos existentes quedan en `null` (D1-b): la clasificación es del ticket de captura. **`create_all` no altera tablas existentes**: hace falta una migración (`ALTER TABLE assets ADD COLUMN …`), fuera de la base de la demo sin confirmación |
| **P2** | Umbral mínimo | ídem | `Asset.min_stock INTEGER NOT NULL DEFAULT 5`, `CHECK (min_stock >= 0)`. El 5 sale de `INVENTORY_DEFAULT_MIN_STOCK` (por defecto 5). Opcional en `AssetCreate` y presente en `AssetRead`. Para ajustarlo (la decisión del BRIEFING): ruta nueva `PATCH /inventory/products/{id}/min-stock` con `{"min_stock": n}`. **Cambia el umbral, no el stock**, y no entra en la definición de `direct_stock_edit_rejected` (que solo mira `/inventory/products` y `/inventory/products/{id}`) |
| **P3** | Coste y moneda de las entradas | ídem + `service.py` | `AssetEntry.unit_cost NUMERIC(12,2)`, `CHECK (unit_cost > 0)`, obligatorio en `InboundOrderCreate` (`Decimal`, 2 decimales como máximo); nullable solo en las filas antiguas. `AssetEntry.currency VARCHAR(3)` con `CHECK` `EUR`/`USD`, rellenada por la API con `office_currency(office)` (`Valencia` → `EUR`, `Miami` → `USD`, BRIEFING §6). Nunca la escribe el cliente: un `currency` en el body → 422 por `extra="forbid"` |
| **P4** | Claim `sid` | `services/api/app/auth/security.py:74` (`create_access_token`) y `:84` (`decode_access_token`) | `sid = str(uuid4())` en cada login, junto a `sub`, `iat` y `exp`; `Token` no cambia. Una función `read_token_claims(settings, token, *, verify_exp=True)` devuelve `sub`, `sid`, `iat` y `exp`, o `None`. Con `verify_exp=False` (firma y algoritmo siempre verificados) clasifica `session_expired` frente a `auth_token_rejected`. Los tokens anteriores al despliegue no tienen `sid`: `sessionId` = `null` hasta que caduquen |
| **P5** | `X-Request-ID` | `services/api/app/core/` (middleware nuevo, registrado junto al de timing en `services/api/app/main.py:121-125`) y `uis/backoffice/lib/api-client.ts:212-221` | El cliente añade `X-Request-ID: crypto.randomUUID()` a cada petición. El middleware lo acepta si cumple el patrón UUID v4 en minúsculas; si no, genera uno (nunca se registra texto arbitrario). Lo guarda en `request.state.request_id`, lo devuelve en la respuesta y lo añade a la línea de `api.timing`. CORS (`main.py:111-120`): añadir `X-Request-ID` a `allow_headers` y `expose_headers` (lo necesita el tracker en el 3002; el backoffice va por `/backend`, del mismo origen) |
| **P6** | Emisor de la API | módulo nuevo `services/api/app/core/telemetry.py` | Ver §2.2 |
| **P7** | Detección del intento de editar el stock | `services/api/app/core/errors.py:207-217` y `:230-233` | Ver §2.3 |
| **P8** | Colector y emisor del frontend | ruta nueva `POST /telemetry/events` en la API + `uis/backoffice/lib/telemetry.ts` | Ver §2.4 |
| **P9** | Proveedor seudónimo | `services/api/app/core/telemetry.py` + variable `TELEMETRY_SUPPLIER_KEY` | `normalize_supplier(text)`: NFKC, recorte, minúsculas y espacios internos colapsados a uno. `supplier_key = HMAC-SHA256(TELEMETRY_SUPPLIER_KEY, normalize_supplier(supplier)).hexdigest()`. La clave (≥ 32 caracteres) solo va en el `.env` de la raíz, con `repr=False`, como `JWT_SECRET_KEY`; sin ella, los eventos que llevan `supplier_key` no se emiten y se registra la clase del error una vez |
| **P10** | Parámetros de la variación de coste | `services/api/app/core/config.py` | `TELEMETRY_COST_VARIANCE_THRESHOLD_PCT` (por defecto `10`, > 0) y `TELEMETRY_COST_VARIANCE_WINDOW` (por defecto `3`, entero de 1 a 100). Validados al arrancar (`ConfigError` si no son válidos) |

### 2.2 P6 — emisor de la API

- **API:** `emit(event_type, properties, *, request=None)`.
- **Qué rellena:**
  - `eventId` (`uuid4`) y `timestamp` (`datetime.now(UTC)`, ISO con milisegundos y `Z`);
  - `schemaVersion` (`"1.0.0"`);
  - `requestId` (de `request.state.request_id`);
  - `userId` y `sessionId` (del usuario autenticado de la petición, o de `read_token_claims` cuando la ficha lo dice).
- **Allowlist en tiempo de ejecución:** una tabla generada desde `event-schemas.json` con las claves permitidas, el tipo y los enums de cada evento.
  - Una clave fuera de la allowlist **se descarta** antes de emitir.
  - Un valor fuera de su tipo o enum **anula el evento**.
  - En los dos casos se registra solo `telemetry event dropped: <event_type> <motivo>`, sin valores.
- **Salida:**
  - una línea JSON por evento en el logger `nexova.telemetry` (stdout, como `api.timing`);
  - el almacenamiento y la separación stream/batch son del ticket de almacenamiento (§7.3);
  - sin dependencias nuevas.
- **Nunca rompe la petición:** cualquier excepción dentro de `emit` se captura y se registra solo su clase. Los eventos de negocio se emiten **después del commit**: un evento nunca describe algo que no ha ocurrido.
- **Helpers del módulo:**
  - `route_template(request)`: `request.scope["route"].path` o `"unmatched"`, sin query string;
  - `office_label(Office)`: minúsculas;
  - `office_currency(Office)`;
  - la función de P9;
  - el agregador de ventanas de 60 s de `api_latency_recorded` y `cache_lookup_recorded`;
  - el throttle de §7.2.

  Todo en memoria del proceso (§8.4, «un solo proceso»).

### 2.3 P7 — detección de `direct_stock_edit_rejected`

1. **405** en `_http_exception_handler`, si el método es `PUT`, `PATCH` o `DELETE` y el path coincide con `^/inventory/products/?$` o `^/inventory/products/([^/]+)$`:
   - `product_id`: el segmento si son solo dígitos (y caben en `int4`); si no, `null`.
   - `authenticated` / `userId` / `sessionId`: con `read_token_claims` sobre la cabecera `Authorization` (sin consultar TinyDB). Si no es válido, `false` / `null` / `null`.
   - `office`, `product_category` y `programme_id`: con un `product_id`, una lectura del activo con una sesión propia del motor del inventario. Si no existe o la base falla, `null` y el evento se emite igualmente.
   - `quantity`: `null` (el body no se lee).
2. **422** en `_validation_exception_handler`, si la ruta es uno de los tres `POST` del inventario y algún error tiene `type == "extra_forbidden"` y `loc == ("body", "current_stock")`:
   - `quantity`: el `input` de ese error, solo si es `int` (no `bool`) entre 1 y `int4`; si no, `null`. Es la única lectura de `input` permitida y nunca se registra en un log.
   - `product_id`: `asset_id` del body si es entero; si no, `null`.
   - `office`: la del activo, o la del body en el alta si está en el vocabulario.
   - Para esa petición **no** se emite `inventory_validation_failed`.

### 2.4 P8 — colector y emisor del frontend

**Colector `POST /telemetry/events`** (API):

- **Colector definitivo (ticket de almacenamiento, implementado):** sustituye al stub de la captura; el frontend no cambia, porque solo mira si la respuesta es 2xx. Decisiones en [`storage-analysis.md`](./storage-analysis.md); contrato en SPECS Parte H.
- **Petición:** body `{"events": [...]}`, ≤ 64 KiB (por debajo del límite general). Se admite cualquier arreglo: 422 solo si el body no es JSON, no tiene `events`, `events` no es una lista o hay claves extra junto a él. Se procesan los 50 primeros items; el resto cuenta como rechazado.
- **Cada evento:** el envelope completo (§5), validado uno a uno. **`userId` y `sessionId` no se confían del cliente**: el cliente los rellena con los claims `sub` y `sid` del JWT, y el colector los sustituye por los del token cuando la petición trae uno válido. Un beacon no lleva token: sus ids son los declarados por el cliente.
- **Qué acepta:**
  - solo los `event_type` de emisor *frontend* (§4; 14 desde el ticket de captura). Un evento de la API enviado por el cliente se rechaza: el frontend no puede fabricar intentos de edición del stock (los 4 obligatorios que sí emite se pueden falsificar, §8.4);
  - cada evento se valida contra su allowlist, como en P6: una clave de más se quita y el evento se guarda; un valor fuera de su tipo o enum, o una clave que falta, rechaza el evento. Los inválidos se descartan uno a uno y no cancelan el lote.
- **`timestamp`:** el del cliente si está a ±5 min de la recepción; si no, la hora de recepción. Una fecha imposible con el patrón correcto rechaza el evento.
- **Respuesta:** `200 {"received": n, "stored": m, "rejected": r}`, siempre con `received = stored + rejected`. Un duplicado cuenta como `stored`: un reintento recibe la misma respuesta. También responde 200 **sin token** (página de login, error global), sin 401, para que el cliente no cierre la sesión por la telemetría. Si la base falla, `503 storage_unavailable` y el frontend reintenta.
- **Throttle:** 120 eventos/min por token, o en total para los anónimos; el exceso cuenta como `rejected`.

**Emisor `lib/telemetry.ts`** (backoffice):

- **API:** `track(event_type, properties)`.
- **Envelope:** genera `eventId`, `timestamp`, `requestId` (un UUID propio mientras no exista `X-Request-ID`, P5), y `userId`/`sessionId` desde los claims del JWT (`sub`, `sid`), sin guardar nada en el navegador.
- **Cola en memoria:** se envía cada 10 s o al llegar a 20 eventos. En `pagehide` / `visibilitychange: hidden`, lo pendiente sale con `navigator.sendBeacon`, que no lleva `Authorization`.
- **Transporte:** a través de `lib/api-client.ts` (el único `fetch`), con dos opciones nuevas:
  - `keepalive: true`;
  - `ignoreUnauthorized: true`: un 401 de la telemetría **no** borra el token.
- **Si falla el envío** (ticket de captura): hasta 3 reintentos, con esperas de 1, 2 y 4 s, solo ante red, timeout, 5xx o 429. Un 4xx no se reintenta. Después se descarta, sin mostrar nada. `sendBeacon` no se reintenta. La deduplicación por `eventId` (§7.3) absorbe un reintento de un lote que sí había llegado.
- **Prohibido:** `console.*`, `localStorage` y `sessionStorage`, según las reglas de `uis/backoffice/CLAUDE.md`.
- `tests/production-source.test.mjs` tendrá que admitir `lib/telemetry.ts` como cliente de `api-client`.

### 2.5 Orden y qué espera a qué

| Paso | Prerrequisito | Desbloquea |
|---|---|---|
| 1 | P6 (emisor) | `api_latency_recorded`, `cache_lookup_recorded`, `api_startup_failed`, `password_reset_email_failed` |
| 2 | P5 (`X-Request-ID`) | el resto de eventos anónimos de la API (`login_failed`, `user_registered`, `registration_failed`, `auth_token_rejected`, la recuperación de contraseña, `server_error_returned`, `storage_unavailable_detected`) |
| 3 | P4 (`sid`) | todos los eventos autenticados de la API que no son de inventario: `user_logged_in`, `session_expired`, `access_denied`, `password_changed`, `password_change_rejected`, `user_role_changed`, `user_deleted`, proveedores, gestor y análisis de incidentes |
| 4 | P8 (colector + `lib/telemetry.ts`) | los 10 eventos del frontend |
| 5 | P1 (+ la migración) | `inbound_order_rejected`, `outbound_order_rejected` e `inventory_validation_failed` |
| 6 | P7 | `direct_stock_edit_rejected` (hecho en el ticket de captura) |
| 7 | P2 | `product_created`, y el mínimo por activo de `stock_threshold_triggered` |
| 8 | P3 + P9 + P10 | `inbound_order_created` y `kit_cost_variance_detected` (hechos en el ticket de captura) |

**Sin prerrequisitos de modelo (pasos 1–4): 43 eventos. Esperan a la migración del inventario (pasos 5–8): los 9 de inventario.**

- **Antes del ticket de captura:** ningún evento se emitía «a medias», y un evento de inventario no se activaba hasta que existía la columna de la que salen sus campos mínimos.
- **Desde el ticket de captura (§1.5):** los 5 obligatorios se emiten ya, sin P1 ni P2:
  - `product_category` y `programme_id` van en `null` mientras no se clasifiquen los activos (D1-b): un valor válido y documentado;
  - `min_stock` es el de la configuración.

  Los demás de inventario siguen esperando a P1.

---

## 3. Flujo de inventario de punta a punta

El recorrido real de un operador, con cada punto de instrumentación (archivo y línea en `390d3aa`). Los eventos marcados ★ son obligatorios.

| Paso | Qué hace el operador | Punto | Evento |
|---|---|---|---|
| 1 | Entra en `/login` y envía el formulario | `uis/backoffice/services/auth.service.ts:277` → `POST /auth/login` → `services/api/app/routes/auth.py:46` (éxito) / `:42` y `:45` (fallo) | `user_logged_in` / `login_failed`; `page_viewed` (`/login`) |
| 2 | El guard valida la sesión y abre `/inventory/products` | `uis/backoffice/components/auth/auth-guard.tsx:26`; `GET /inventory/products` → `services/api/app/modules/inventory/router.py:84-86` (caché, `services/api/app/core/cache.py:70` / `:72`) | `page_viewed`, `page_load_recorded`, `cache_lookup_recorded`, `api_latency_recorded` |
| 3 | Ve el nivel de stock de cada activo | `uis/backoffice/lib/stock-level.ts:18-26` (solo presentación) | — (el umbral lo detecta la API en el paso 7, nunca el indicador) |
| 4 | Abre «Entrada de activos» y la rellena; la validación en cliente bloquea un campo vacío | `uis/backoffice/services/inventory.service.ts:289` | `form_started`, `form_validation_failed` (`inbound_order`) |
| 5 | Envía la entrada | `POST /inventory/orders/inbound` → `services/api/app/modules/inventory/router.py:108-123` → `service.py:161-174` → commit en `service.py:202` | ★ `inbound_order_created`, ★ `kit_cost_variance_detected` (si se desvía), `inbound_order_rejected` (404 o `office_mismatch`), `inventory_validation_failed` (422); `form_submitted` (`uis/backoffice/hooks/use-inbound-form.ts:107` / `:110`) |
| 6 | Abre «Salida de activos», elige el activo (lectura de su stock) y escribe la cantidad | `uis/backoffice/hooks/use-outbound-form.ts` (`GET /inventory/products/{id}`, `router.py:102-105`); aviso en `uis/backoffice/components/inventory/outbound-form.tsx:95` | `form_started`; `form_validation_failed` (`uis/backoffice/services/inventory.service.ts:305`) |
| 7 | Envía la salida | `POST /inventory/orders/outbound` → `router.py:126-146` → `service.py:177-195`: `FOR UPDATE` (184), 404 (186), oficina (188), **stock disponible (189)**, `insufficient_stock` (190-191); commit en `service.py:215` | ★ `outbound_order_created`, ★ `stock_threshold_triggered` (si cruza el mínimo), `outbound_order_rejected` (stock, oficina o 404), `inventory_validation_failed` (422, p. ej. `allocation` sin `assigned_to`); `form_submitted` (`uis/backoffice/hooks/use-outbound-form.ts:210` / `:215`) |
| 8 | Abandona un formulario a medias o cambia de sección | `hooks/use-form-telemetry.ts` (nuevo) | `form_abandoned`, `page_viewed` |
| 9 | Consulta el Historial | `GET /inventory/orders` → `router.py:149-151` | `page_viewed`, `page_load_recorded` (`uis/backoffice/hooks/use-inventory-orders.ts:99`), `api_latency_recorded` |
| 10 | Alguien intenta fijar el stock por la API (`/docs`, `curl`): no hay botón en la interfaz | 405 en `services/api/app/core/errors.py:207-217` (antes de autenticar) o 422 `extra_forbidden` en `errors.py:230-233` | ★ `direct_stock_edit_rejected` |
| 11 | El token caduca mientras trabaja | `services/api/app/auth/dependencies.py:56-58`; el cliente borra el token en `uis/backoffice/lib/api-client.ts:253-256` | `session_expired` |
| 12 | Supabase no responde | `services/api/app/core/errors.py:220-227` | `storage_unavailable_detected` (`store = inventory`) |

Los pasos 5, 7 y 10 cubren los obligatorios; 4–7 cubren las validaciones fallidas (en cliente y en la API); 7 cubre el umbral mínimo; y 10, los intentos de editar el stock directamente.

---

## 4. Catálogo

Una fila por evento, con la clasificación pedida (**obligatorio**: viene del BRIEFING; **oportunidad**: identificada en este plan), su categoría, el emisor, la entrega y los prerrequisitos. Cada evento tiene su ficha en §6, con la frase «Capturamos… porque necesitamos saber…, lo que nos permite tomar la decisión de…», el punto exacto, la justificación de la entrega, la allowlist, la PII y un ejemplo. Los que no superaron la frase están en §8.1.

<!-- CATALOG -->
| # | `event_type` | Clasificación | Categoría | Emisor | Entrega | Prerrequisitos |
|---|---|---|---|---|---|---|
| 1 | `inbound_order_created` | obligatorio | inventario | frontend | batch | P3, P4, P8, P9 |
| 2 | `outbound_order_created` | obligatorio | inventario | frontend | batch | P4, P8 |
| 3 | `stock_threshold_triggered` | obligatorio | inventario | frontend | stream | P4, P8 |
| 4 | `direct_stock_edit_rejected` | obligatorio | inventario | API | batch | P4, P6, P7 |
| 5 | `kit_cost_variance_detected` | obligatorio | inventario | frontend | stream | P3, P4, P8, P9, P10 |
| 6 | `product_created` | oportunidad | inventario | API | batch | P1, P2, P4, P5, P6 |
| 7 | `inbound_order_rejected` | oportunidad | inventario | API | batch | P1, P4, P5, P6 |
| 8 | `outbound_order_rejected` | oportunidad | inventario | API | stream | P1, P4, P5, P6 |
| 9 | `inventory_validation_failed` | oportunidad | inventario | API | batch | P1, P4, P5, P6 |
| 10 | `user_logged_in` | oportunidad | autenticación | API | batch | P4, P5, P6 |
| 11 | `login_failed` | oportunidad | autenticación | API | stream | P5, P6 |
| 12 | `user_registered` | oportunidad | autenticación | API | batch | P5, P6 |
| 13 | `registration_failed` | oportunidad | autenticación | API | batch | P5, P6 |
| 14 | `session_expired` | oportunidad | autenticación | API | batch | P4, P5, P6 |
| 15 | `auth_token_rejected` | oportunidad | autenticación | API | stream | P5, P6 |
| 16 | `user_logged_out` | oportunidad | autenticación | frontend | batch | P4, P8 |
| 17 | `password_reset_requested` | oportunidad | autenticación | API | batch | P5, P6 |
| 18 | `password_reset_completed` | oportunidad | autenticación | API | batch | P5, P6 |
| 19 | `password_reset_rejected` | oportunidad | autenticación | API | batch | P5, P6 |
| 20 | `password_changed` | oportunidad | autenticación | API | batch | P4, P5, P6 |
| 21 | `password_change_rejected` | oportunidad | autenticación | API | batch | P4, P5, P6 |
| 22 | `password_reset_email_failed` | oportunidad | autenticación | API | stream | P6 |
| 23 | `access_denied` | oportunidad | autenticación | API | batch | P4, P5, P6 |
| 24 | `user_role_changed` | oportunidad | autenticación | API | stream | P4, P5, P6 |
| 25 | `user_deleted` | oportunidad | autenticación | API | batch | P4, P5, P6 |
| 26 | `page_viewed` | oportunidad | navegación | frontend | batch | P4, P8 |
| 27 | `page_not_found_viewed` | oportunidad | navegación | frontend | batch | P4, P8 |
| 28 | `form_started` | oportunidad | flujos | frontend | batch | P4, P8 |
| 29 | `form_submitted` | oportunidad | flujos | frontend | batch | P4, P8 |
| 30 | `form_abandoned` | oportunidad | flujos | frontend | batch | P4, P8 |
| 31 | `form_validation_failed` | oportunidad | flujos | frontend | batch | P4, P8 |
| 32 | `frontend_error_captured` | oportunidad | errores | frontend | stream | P4, P8 |
| 33 | `client_request_failed` | oportunidad | errores | frontend | stream | P4, P5, P8 |
| 34 | `server_error_returned` | oportunidad | errores | API | stream | P5, P6 |
| 35 | `storage_unavailable_detected` | oportunidad | salud técnica | API | stream | P5, P6 |
| 36 | `api_startup_failed` | oportunidad | salud técnica | API | stream | P6 |
| 37 | `cache_lookup_recorded` | oportunidad | salud técnica | API | batch | P6 |
| 38 | `api_latency_recorded` | oportunidad | rendimiento | API | batch | P6 |
| 39 | `page_load_recorded` | oportunidad | rendimiento | frontend | batch | P4, P8 |
| 40 | `supplier_created` | oportunidad | proveedores | API | batch | P4, P5, P6 |
| 41 | `supplier_rate_updated` | oportunidad | proveedores | API | batch | P4, P5, P6 |
| 42 | `supplier_status_changed` | oportunidad | proveedores | API | batch | P4, P5, P6 |
| 43 | `supplier_deleted` | oportunidad | proveedores | API | batch | P4, P5, P6 |
| 44 | `supplier_list_filtered` | oportunidad | proveedores | API | batch | P4, P5, P6 |
| 45 | `incident_created` | oportunidad | gestor de incidencias | API | stream | P4, P5, P6 |
| 46 | `incident_status_changed` | oportunidad | gestor de incidencias | API | batch | P4, P5, P6 |
| 47 | `incident_status_change_rejected` | oportunidad | gestor de incidencias | API | batch | P4, P5, P6 |
| 48 | `incident_validation_failed` | oportunidad | gestor de incidencias | API | batch | P4, P5, P6 |
| 49 | `incident_list_filtered` | oportunidad | gestor de incidencias | API | batch | P4, P5, P6 |
| 50 | `incident_analysis_completed` | oportunidad | análisis de incidentes | API | batch | P4, P5, P6 |
| 51 | `incident_analysis_rejected` | oportunidad | análisis de incidentes | API | batch | P4, P5, P6 |
| 52 | `incident_results_exported` | oportunidad | análisis de incidentes | API | batch | P4, P5, P6 |
<!-- /CATALOG -->

---

## 5. Event Envelope

Todo evento, lo emita quien lo emita, es un objeto JSON con **exactamente** estas 8 claves (ni una más: `additionalProperties: false` en `definitions.envelope`):

| Campo | Tipo | Obligatorio | Cuándo es `null` | De dónde sale |
|---|---|---|---|---|
| `eventId` | string, UUID v4 | sí | nunca | `uuid4()` del emisor (API: P6; frontend: `lib/telemetry.ts`). Sirve para deduplicar reenvíos |
| `timestamp` | string ISO 8601 UTC, `AAAA-MM-DDTHH:MM:SS.mmmZ` | sí | nunca | Instante del hecho: en la API, al emitir (tras el commit si es una escritura); en el frontend, el del navegador, corregido por el colector si se desvía más de ±5 min (§2.4). Los agregados llevan el **cierre** de su ventana |
| `sessionId` | string UUID v4 \| `null` | sí | eventos anónimos (`login_failed`, registro, recuperación de contraseña…), del sistema (agregados, arranque) y con un token sin `sid` (anterior a P4) | Claim `sid` del JWT (D7, P4). En `user_logged_in`, el `sid` del token recién emitido. En el frontend lo declara el cliente desde el JWT y el colector lo sustituye por el del token si hay uno válido (§2.4) |
| `userId` | string UUID v4 \| `null` | sí | igual que `sessionId`; además, en los eventos con identidad opcional cuando no hay un token válido | `sub` del JWT = `User.id` de TinyDB = el `user_uuid` de las órdenes. En la recuperación de contraseña, la cuenta afectada si se conoce |
| `event_type` | string `^[a-z]+(_[a-z]+)+$` | sí | nunca | `entidad_accion` (§5.3); cada esquema fija su valor con `const` |
| `schemaVersion` | string semver | sí | nunca | `"1.0.0"` en todos los eventos de este plan; las reglas de cambio, en §5.4 |
| `requestId` | string UUID v4 \| `null` | sí | eventos sin petición: agregados, arranque y el email de restablecimiento (tarea en segundo plano) | `X-Request-ID` de la petición (D8, P5); en el frontend, el de la petición asociada o uno propio |
| `properties` | objeto | sí | nunca (como mínimo `{}`) | Payload del evento, **solo** con las claves de su allowlist (§6) |

### 5.1 Identidad por evento

Cada ficha dice cuál de estos modos aplica. El esquema lo comprueba: por ejemplo, en `login_failed`, `sessionId` y `userId` tienen que ser `null`.

| Modo | `userId` | `sessionId` |
|---|---|---|
| autenticado | siempre presente | siempre presente |
| anónimo / sistema | siempre `null` | siempre `null` |
| cuenta afectada | la cuenta, si se conoce | siempre `null` |
| opcional | si hay un token válido | si hay un token válido |

### 5.2 Ejemplo completo

```json
{
  "eventId": "5c1e7a2b-3d4f-4a6b-8c9d-0e1f2a3b4c5d",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "outbound_order_created",
  "schemaVersion": "1.0.0",
  "requestId": "7d9f1b3c-5e7a-4c2e-a4b6-8d0f2a4c6e8a",
  "properties": {"office": "valencia", "product_id": 7, "product_category": "training_kit", "programme_id": "ventas-b2b", "quantity": 3, "currency": "EUR", "outbound_order_id": 88, "exit_type": "allocation", "stock_after": 6, "asset_category": "training_materials"}
}
```

### 5.3 Taxonomía (D13)

- **Formato:** `entidad_accion` en snake_case, con la entidad en singular. Los cinco obligatorios llevan el nombre exacto del BRIEFING.
- **Verbos cerrados**, en participio inglés como los del BRIEFING:

  | Verbo | Se usa para |
  |---|---|
  | `created`, `updated`, `changed`, `deleted`, `registered` | escrituras correctas |
  | `rejected` | lo rechaza una regla del negocio, un permiso o la validación del servidor |
  | `failed` | fallo de credenciales, de validación en cliente o técnico |
  | `triggered` | umbral |
  | `detected` | anomalía |
  | `viewed`, `started`, `submitted`, `abandoned`, `filtered` | navegación y flujos |
  | `recorded` | medida técnica |
  | `captured` | error de frontend |
  | `returned` | respuesta de error de la API |
  | `logged_in`, `logged_out`, `expired`, `completed`, `requested`, `exported` | ciclo de sesión y procesos |

- **Sin prefijos de capa** (`api_`, `ui_`), salvo cuando la entidad es la propia capa (`api_latency_recorded`, `api_startup_failed`).

### 5.4 Versionado de esquemas

- **Versión menor** (`1.1.0`): añadir una propiedad **opcional** o un valor nuevo a un enum.
- **Versión mayor** (`2.0.0`), con un periodo en el que se emiten las dos: quitar o renombrar una propiedad, cambiar su tipo, hacerla obligatoria o quitar un valor de un enum.
- **No cambian la versión:** las correcciones de texto (`description`).
- **Coherencia:** el `schemaVersion` de cada ejemplo de §6 y de `event-schemas.json` es el mismo, y el script de §9 lo comprueba.

---

## 6. Esquemas por evento

**Formato de cada ficha:**

- la línea de metadatos (la misma que el `$comment` del esquema en `event-schemas.json`);
- la frase que justifica el evento;
- cuándo se dispara y el punto exacto de emisión;
- la identidad (§5.1);
- el porqué de la entrega;
- la PII y su sanitización;
- la **allowlist** de `properties`: solo esas claves, con su tipo y si son obligatorias. Una clave que no esté en la tabla no se emite (P6 y el colector, P8, la descartan);
- un ejemplo completo que valida contra su esquema (§9).

**Tipos de la allowlist:**

- `integer`, `number`, `string` (con patrón), `boolean`;
- `enum`: valores listados;
- `array<…>`: sin repetidos y con un máximo de elementos;
- `… | null`: admite `null`.

Todas las propiedades de este plan son **obligatorias**: un dato que no aplica va como `null` cuando su tipo lo admite, nunca omitido. Así, un agregado nunca confunde «no aplica» con «no se envió».

**Campos mínimos de inventario (BRIEFING):** `office`, `product_id`, `product_category`, `programme_id`, `quantity` y `currency` están en los 9 eventos de inventario, con estos valores:

- `office`: `valencia` / `miami`;
- `product_category`: `training_kit` / `certification` / `onboarding_equipment`, o `null` (D1-a);
- `currency`: `EUR` / `USD`.

Los eventos que no son de inventario no los llevan.

**Coherencia oficina–moneda (BRIEFING §6):** el esquema de cada evento de inventario la exige con un `oneOf` en `properties`. Las combinaciones válidas son `valencia` con `EUR`, `miami` con `USD` y, solo en los eventos donde la oficina puede faltar, `null` con `null`. Un `valencia` con `USD` no valida.

### 6.1 Obligatorios (BRIEFING)

#### `inbound_order_created`

- **Clasificación:** obligatorio · **Categoría:** inventario · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P3, P4, P8, P9
- **Descripción:** Se ha registrado una orden de entrada (`AssetEntry`): llega un lote de material desde un proveedor.
- **Frase:** Capturamos `inbound_order_created` porque necesitamos saber cuánto material se produce o compra, para qué programa y con qué coste, lo que nos permite tomar la decisión de planificar la producción de material según la demanda esperada de matrículas (Elena).
- **Se dispara:** `POST /inventory/orders/inbound` responde 201, después del commit.
- **Punto exacto:** desde el ticket de captura (§1.5), el backoffice al recibir el 201: `uis/backoffice/hooks/use-inbound-form.ts` → `lib/inventory-telemetry.ts` (`trackInboundOrder`), con lo que devuelve `create_inbound_order` (`services/api/app/modules/inventory/service.py`, tras `session.commit()`): `unit_cost`, `currency` y `supplier_key`. `asset_category` es la del activo elegido. No se emite si la API no tiene `TELEMETRY_SUPPLIER_KEY` (`supplier_key` nulo).
- **Identidad:** `userId` y `sessionId` de los claims del JWT de la sesión (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Alimenta una planificación de producción que se decide por semanas: un lote diario basta y nadie actúa en minutos sobre una entrada.
- **PII y sanitización:** Ninguna en `properties`. `supplier` (texto libre, puede ser un autónomo con nombre propio) se sustituye por `supplier_key` (D9). `userId` es seudónimo (ver §5).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). Valores: `valencia`, `miami`. |
| `product_id` | `integer` | sí | `Asset.id` del activo (D6). |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer` | sí | Unidades de la orden (`quantity`). |
| `currency` | `enum` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). Valores: `EUR`, `USD`. |
| `inbound_order_id` | `integer` | sí | `AssetEntry.id`. |
| `unit_cost` | `number` | sí | Coste unitario de la entrada (`AssetEntry.unit_cost`, P3), en `currency`, con dos decimales. |
| `supplier_key` | `string` | sí | Clave seudónima del proveedor: HMAC-SHA256 en hex del nombre normalizado (P9). Nunca el nombre. Patrón `^[0-9a-f]{64}$`. |
| `asset_category` | `enum` | sí | Categoría operativa del Hito 5 (`Asset.category`), sin traducir: permite agregar los activos con `product_category` nulo. Valores: `hardware`, `peripherals`, `office_supplies`, `training_materials`. |

```json
{
  "eventId": "51e4476a-0ac6-4710-86d7-daa6e495839c",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "inbound_order_created",
  "schemaVersion": "1.0.0",
  "requestId": "dd518796-7029-4ab0-83d9-8522cebfc79f",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": 12,
    "currency": "EUR",
    "inbound_order_id": 41,
    "unit_cost": 18.5,
    "supplier_key": "4e1f0a9c7b3d2e8f6a5c4b1d0e9f8a7c6b5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f",
    "asset_category": "training_materials"
  }
}
```

#### `outbound_order_created`

- **Clasificación:** obligatorio · **Categoría:** inventario · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** Se ha registrado una orden de salida (`AssetExit`): se entrega un kit o certificado, o se consume material.
- **Frase:** Capturamos `outbound_order_created` porque necesitamos saber qué programas consumen más material y a qué ritmo, lo que nos permite tomar la decisión de anticipar las necesidades de reposición antes de una ola grande de matrículas (Elena).
- **Se dispara:** `POST /inventory/orders/outbound` responde 201, después del commit.
- **Punto exacto:** desde el ticket de captura (§1.5), el backoffice al recibir el 201: `uis/backoffice/hooks/use-outbound-form.ts` → `lib/inventory-telemetry.ts` (`trackOutboundOrder`). `stock_after` viene en la respuesta: la API lo calcula en `create_outbound_order` (`services/api/app/modules/inventory/service.py`) bajo `FOR UPDATE`, en la misma transacción.
- **Identidad:** `userId` y `sessionId` de los claims del JWT de la sesión (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** El ritmo de consumo se lee en tendencias diarias o semanales. La urgencia de reponer la cubre `stock_threshold_triggered`, que sí es stream.
- **PII y sanitización:** `assigned_to` (nombre o ID del empleado, texto libre) **no** se emite nunca: solo `exit_type` (D9, regla del BRIEFING).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). Valores: `valencia`, `miami`. |
| `product_id` | `integer` | sí | `Asset.id` del activo (D6). |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer` | sí | Unidades de la orden (`quantity`). |
| `currency` | `enum` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). Valores: `EUR`, `USD`. |
| `outbound_order_id` | `integer` | sí | `AssetExit.id`. |
| `exit_type` | `enum` | sí | Tipo de salida, tal cual (`allocation` = asignación, `consumption` = consumo). Valores: `allocation`, `consumption`. |
| `stock_after` | `integer` | sí | Stock del activo después de la salida. |
| `asset_category` | `enum` | sí | Categoría operativa del Hito 5 (`Asset.category`), sin traducir: permite agregar los activos con `product_category` nulo. Valores: `hardware`, `peripherals`, `office_supplies`, `training_materials`. |

```json
{
  "eventId": "c9257219-1416-42d6-8a5d-db50f9333d10",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "outbound_order_created",
  "schemaVersion": "1.0.0",
  "requestId": "80e1657d-c457-4bd5-8f6f-d81cbaad4144",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": 3,
    "currency": "EUR",
    "outbound_order_id": 88,
    "exit_type": "allocation",
    "stock_after": 6,
    "asset_category": "training_materials"
  }
}
```

#### `stock_threshold_triggered`

- **Clasificación:** obligatorio · **Categoría:** inventario · **Emisor:** frontend · **Entrega:** stream · **Prerrequisitos:** P4, P8
- **Descripción:** Una salida ha hecho cruzar al stock de un activo su mínimo configurado: antes estaba en `min_stock` o por encima y después queda por debajo (`<`).
- **Frase:** Capturamos `stock_threshold_triggered` porque necesitamos saber con qué frecuencia un programa se queda sin material disponible, lo que nos permite tomar la decisión de ajustar el umbral mínimo o acelerar la reimpresión o reproducción de ese material.
- **Se dispara:** En una salida confirmada con `stock_before >= min_stock` y `stock_after < min_stock` (D4). Por cruce: no se repite mientras siga por debajo y se rearma solo cuando una entrada lo devuelve a `min_stock` o más. Nunca en el alta de un activo (nace con 0). Con `min_stock = 0` no se dispara nunca.
- **Punto exacto:** desde el ticket de captura (§1.5), junto a `outbound_order_created`, en `lib/inventory-telemetry.ts` (`trackOutboundOrder`). Usa `stock_before`, `stock_after` y `min_stock` de la respuesta 201, que la API calcula bajo `FOR UPDATE`; el frontend solo compara. `min_stock` = `INVENTORY_DEFAULT_MIN_STOCK` hasta P2. **Nunca** desde `StockLevelBadge` ni desde una lectura previa del stock.
- **Identidad:** `userId` y `sessionId` de los claims del JWT de la sesión (nunca `null`). `requestId` siempre presente.
- **Por qué stream:** La decisión es acelerar una reimpresión: cada hora que pasa sin aviso retrasa la entrega de kits a matrículas que ya existen.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). Valores: `valencia`, `miami`. |
| `product_id` | `integer` | sí | `Asset.id` del activo (D6). |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer` | sí | Unidades de la salida que provocó el cruce. |
| `currency` | `enum` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). Valores: `EUR`, `USD`. |
| `outbound_order_id` | `integer` | sí | `AssetExit.id` de la salida que provocó el cruce. |
| `stock_before` | `integer` | sí | Stock antes de la salida (`available`). |
| `stock_after` | `integer` | sí | Stock después de la salida. 0 = agotado. |
| `min_stock` | `integer` | sí | Mínimo configurado del activo en ese momento (`Asset.min_stock`, P2; por defecto 5). |
| `asset_category` | `enum` | sí | Categoría operativa del Hito 5 (`Asset.category`), sin traducir: permite agregar los activos con `product_category` nulo. Valores: `hardware`, `peripherals`, `office_supplies`, `training_materials`. |

```json
{
  "eventId": "35d1d5e1-cb41-4b98-840a-beb116ab5f26",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "stock_threshold_triggered",
  "schemaVersion": "1.0.0",
  "requestId": "b6a5271e-7854-4223-8e49-0230366decf9",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": 3,
    "currency": "EUR",
    "outbound_order_id": 88,
    "stock_before": 6,
    "stock_after": 3,
    "min_stock": 5,
    "asset_category": "training_materials"
  }
}
```

#### `direct_stock_edit_rejected`

- **Clasificación:** obligatorio · **Categoría:** inventario · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P6, P7
- **Descripción:** Alguien ha intentado fijar el stock fuera de una orden y la API lo ha rechazado (definición operativa D5).
- **Frase:** Capturamos `direct_stock_edit_rejected` porque necesitamos saber si el personal intenta saltarse el control de trazabilidad del material, lo que nos permite tomar la decisión de reforzar la capacitación o los permisos en la oficina donde esto ocurre con más frecuencia (Patricia).
- **Se dispara:** Exactamente uno de estos dos casos (D5): (1) `PUT`, `PATCH` o `DELETE` sobre `/inventory/products` o `/inventory/products/{id}` → 405, con o sin token; (2) `POST` a `/inventory/products`, `/inventory/orders/inbound` o `/inventory/orders/outbound` con un error `extra_forbidden` en `loc = ["body", "current_stock"]` → 422 (solo con token válido: sin él la API responde antes 401 y no se emite). No cuentan un 404 de ruta inventada, una cantidad negativa ni el SQL directo en Supabase. Si se cumple el caso (2), **no** se emite además `inventory_validation_failed` para esa petición.
- **Punto exacto:** Caso 1: `services/api/app/core/errors.py` (`_http_exception_handler`, status 405). Caso 2: `services/api/app/core/errors.py` (`_validation_exception_handler`). Los dos llaman a `app.state.stock_edit_reporter` (`services/api/app/modules/telemetry/stock_edit.py`, ticket de captura). Detalle de la detección en P7.
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** La decisión de Patricia (formación o permisos) se toma con el recuento por oficina de días o semanas: lote diario. Una ráfaga sí es urgente (posible abuso de la API): la regla de alerta de §7.2 la eleva a stream sin cambiar el evento.
- **PII y sanitización:** Ninguna. Nunca se copia el body ni el `detail`. `userId` es `null` en los intentos anónimos.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum \| null` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). `null` si no se puede saber (ver la ficha). Valores: `valencia`, `miami`; o `null`. |
| `product_id` | `integer \| null` | sí | `Asset.id` del activo (D6). `null` si la petición no identifica un activo. |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer \| null` | sí | Valor de stock intentado si el body lo trae como entero (caso 2); `null` en el caso 1 (el body no se lee) o si no es un entero. |
| `currency` | `enum \| null` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). `null` si `office` es `null`. Valores: `EUR`, `USD`; o `null`. |
| `attempt_kind` | `enum` | sí | Caso 1 (`method_not_allowed`) o caso 2 (`stock_field_in_body`). Valores: `method_not_allowed`, `stock_field_in_body`. |
| `http_method` | `enum` | sí | Método de la petición rechazada. Valores: `PUT`, `PATCH`, `DELETE`, `POST`. |
| `route_template` | `enum` | sí | Plantilla de la ruta, nunca el path con el id. Valores: `/inventory/products`, `/inventory/products/{id}`, `/inventory/orders/inbound`, `/inventory/orders/outbound`. |
| `status_code` | `enum` | sí | Respuesta de la API. Valores: `405`, `422`. |
| `authenticated` | `boolean` | sí | `true` si la petición traía un token válido (en el caso 1 se decodifica de forma opcional, D5). |
| `suppressed_count` | `integer` | sí | Eventos iguales (misma clave de throttle) descartados desde la última emisión (§7.2). 0 si no se descartó ninguno. |

```json
{
  "eventId": "bf97980c-92ed-4661-8d4f-866f8bdb80f2",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "direct_stock_edit_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "9e0c60dd-cb8e-4624-8412-23fc1743167d",
  "properties": {
    "office": "miami",
    "product_id": 3,
    "product_category": "onboarding_equipment",
    "programme_id": null,
    "quantity": null,
    "currency": "USD",
    "attempt_kind": "method_not_allowed",
    "http_method": "PUT",
    "route_template": "/inventory/products/{id}",
    "status_code": 405,
    "authenticated": true,
    "suppressed_count": 0
  }
}
```

#### `kit_cost_variance_detected`

- **Clasificación:** obligatorio · **Categoría:** inventario · **Emisor:** frontend · **Entrega:** stream · **Prerrequisitos:** P3, P4, P8, P9, P10
- **Descripción:** El coste unitario de una entrada se desvía de la referencia del mismo material y proveedor más que el umbral configurado, hacia arriba o hacia abajo.
- **Frase:** Capturamos `kit_cost_variance_detected` porque necesitamos saber cuándo un proveedor de material sube (o baja) precios de forma anómala, lo que nos permite tomar la decisión de alertar a Elena y a Laura para renegociar o buscar un proveedor alternativo.
- **Se dispara:** Tras una entrada confirmada con `unit_cost`: referencia = media de `unit_cost` de las `N` entradas anteriores (por defecto 3) del mismo par (activo, proveedor normalizado), sin contar la actual; `variance_pct = (unit_cost − referencia) / referencia × 100`, redondeado a 2 decimales. Se emite si `|variance_pct| > umbral` (por defecto 10). Con menos de `N` entradas anteriores con coste no se evalúa (D3).
- **Punto exacto:** desde el ticket de captura (§1.5), junto a `inbound_order_created`, en `lib/inventory-telemetry.ts` (`trackInboundOrder`), si la respuesta 201 trae `cost_variance`. La API la calcula en `create_inbound_order`, con una consulta más de las `N` anteriores del par en la misma sesión.
- **Identidad:** `userId` y `sessionId` de los claims del JWT de la sesión (nunca `null`). `requestId` siempre presente.
- **Por qué stream:** Hay que avisar antes de que se comprometan más compras al precio nuevo: esperar al lote del día siguiente puede significar otra entrada al mismo precio.
- **PII y sanitización:** El proveedor va solo como `supplier_key` (HMAC); el nombre se consulta en la base, desde `inbound_order_id`, con control de acceso (D9).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). Valores: `valencia`, `miami`. |
| `product_id` | `integer` | sí | `Asset.id` del activo (D6). |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer` | sí | Unidades de la entrada evaluada. |
| `currency` | `enum` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). Valores: `EUR`, `USD`. |
| `inbound_order_id` | `integer` | sí | `AssetEntry.id` de la entrada evaluada: la renegociación se resuelve desde la base, con control de acceso (D9). |
| `supplier_key` | `string` | sí | Clave seudónima del proveedor (P9). Patrón `^[0-9a-f]{64}$`. |
| `unit_cost` | `number` | sí | Coste unitario de la entrada evaluada, en `currency`. |
| `reference_unit_cost` | `number` | sí | Media de las `N` entradas anteriores del mismo par, en `currency`. |
| `variance_pct` | `number` | sí | Variación porcentual con signo respecto a la referencia, con 2 decimales. |
| `direction` | `enum` | sí | `increase` si `variance_pct > 0`; `decrease` si es negativa. Valores: `increase`, `decrease`. |
| `threshold_pct` | `number` | sí | Umbral vigente (`TELEMETRY_COST_VARIANCE_THRESHOLD_PCT`, por defecto 10). |
| `reference_window` | `integer` | sí | `N` vigente (`TELEMETRY_COST_VARIANCE_WINDOW`, por defecto 3). |
| `asset_category` | `enum` | sí | Categoría operativa del Hito 5 (`Asset.category`), sin traducir: permite agregar los activos con `product_category` nulo. Valores: `hardware`, `peripherals`, `office_supplies`, `training_materials`. |

```json
{
  "eventId": "0cff3151-a91b-452f-8003-78a48ccbd83d",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "kit_cost_variance_detected",
  "schemaVersion": "1.0.0",
  "requestId": "f39518cc-b1f5-4a1e-88c2-9c5fad7a0875",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": 20,
    "currency": "EUR",
    "inbound_order_id": 57,
    "supplier_key": "4e1f0a9c7b3d2e8f6a5c4b1d0e9f8a7c6b5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f",
    "unit_cost": 21.4,
    "reference_unit_cost": 18.5,
    "variance_pct": 15.68,
    "direction": "increase",
    "threshold_pct": 10,
    "reference_window": 3,
    "asset_category": "training_materials"
  }
}
```

### 6.2 Oportunidades — inventario

#### `product_created`

- **Clasificación:** oportunidad · **Categoría:** inventario · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P1, P2, P4, P5, P6
- **Descripción:** Se ha dado de alta un activo (`POST /inventory/products` → 201).
- **Frase:** Capturamos `product_created` porque necesitamos saber cuántos ítems nuevos de material se crean por programa y oficina, y con qué mínimo, lo que nos permite tomar la decisión de detectar catálogos que crecen sin control (duplicados de SKU entre oficinas) o activos creados sin programa, y pedir su clasificación.
- **Se dispara:** `POST /inventory/products` responde 201.
- **Punto exacto:** `services/api/app/modules/inventory/router.py:96-98` (tras `service.create_asset`, `service.py:112`).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** El alta de un activo no exige acción inmediata: la revisión del catálogo es semanal.
- **PII y sanitización:** Ninguna: ni `name` ni `sku` (texto libre), solo `product_id`.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). Valores: `valencia`, `miami`. |
| `product_id` | `integer` | sí | `Asset.id` del activo (D6). |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer \| null` | sí | Siempre `null`: un activo nace con stock 0 y no tiene cantidad (campo mínimo del BRIEFING presente por coherencia). |
| `currency` | `enum` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). Valores: `EUR`, `USD`. |
| `min_stock` | `integer` | sí | Mínimo con el que nace (P2). |
| `asset_category` | `enum` | sí | Categoría operativa del Hito 5 (`Asset.category`), sin traducir: permite agregar los activos con `product_category` nulo. Valores: `hardware`, `peripherals`, `office_supplies`, `training_materials`. |

```json
{
  "eventId": "fc923d50-ef2f-45ff-890e-4dd881b3f758",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "product_created",
  "schemaVersion": "1.0.0",
  "requestId": "031d0d4c-0c68-46e2-8740-89723e63b003",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": null,
    "currency": "EUR",
    "min_stock": 5,
    "asset_category": "training_materials"
  }
}
```

#### `inbound_order_rejected`

- **Clasificación:** oportunidad · **Categoría:** inventario · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P1, P4, P5, P6
- **Descripción:** Una orden de entrada válida en forma ha sido rechazada por una regla del negocio: activo inexistente (404) u oficina distinta de la del activo (400).
- **Frase:** Capturamos `inbound_order_rejected` porque necesitamos saber qué activos y oficinas acumulan entradas rechazadas y por qué motivo, lo que nos permite tomar la decisión de corregir el formulario o la formación del personal (p. ej. si `office_mismatch` es frecuente, revisar cómo se elige la oficina).
- **Se dispara:** `POST /inventory/orders/inbound` responde 404 `asset_not_found` o 400 `office_mismatch`.
- **Punto exacto:** `services/api/app/modules/inventory/router.py:121`: la ruta captura el `ApiError` de `service.add_inbound_order` (`service.py:168` y `:170`), emite y lo relanza.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** El usuario ya ve el error en pantalla; el patrón se corrige con formación o con la interfaz, en días.
- **PII y sanitización:** Ninguna. `product_id` es el `asset_id` del body; `office`, `product_category` y `programme_id` son los del activo si existe (si no, `null`).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum \| null` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). `null` si no se puede saber (ver la ficha). Valores: `valencia`, `miami`; o `null`. |
| `product_id` | `integer` | sí | `Asset.id` del activo (D6). |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer` | sí | `quantity` del body (ya validado). |
| `currency` | `enum \| null` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). `null` si `office` es `null`. Valores: `EUR`, `USD`; o `null`. |
| `error_code` | `enum` | sí | `code` de la respuesta. Valores: `asset_not_found`, `office_mismatch`. |

```json
{
  "eventId": "55d6f92e-0cb3-42cc-817b-1f00782d8701",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "inbound_order_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "e8d36823-5992-4945-8525-ab8e9a8f6e52",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": 10,
    "currency": "EUR",
    "error_code": "office_mismatch"
  }
}
```

#### `outbound_order_rejected`

- **Clasificación:** oportunidad · **Categoría:** inventario · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P1, P4, P5, P6
- **Descripción:** Una salida válida en forma ha sido rechazada por una regla del negocio: activo inexistente, oficina distinta o stock insuficiente.
- **Frase:** Capturamos `outbound_order_rejected` porque necesitamos saber cuántas entregas no se pueden hacer por falta de stock, de qué material y programa, lo que nos permite tomar la decisión de reponer de inmediato el material que impide entregas reales (una persona está esperando su kit).
- **Se dispara:** `POST /inventory/orders/outbound` responde 404 `asset_not_found`, 400 `office_mismatch` o 400 `insufficient_stock`.
- **Punto exacto:** `services/api/app/modules/inventory/router.py:144`: la ruta captura el `ApiError` de `service.add_outbound_order` (`service.py:186`, `:188` y `:190-191`), emite y lo relanza.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué stream:** Un `insufficient_stock` es una entrega fallida con alguien esperando: la reposición tiene que empezar hoy, no tras el lote nocturno.
- **PII y sanitización:** Ni `assigned_to` ni el `detail` (lleva el nombre del activo): solo `error_code` y cifras.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum \| null` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). `null` si no se puede saber (ver la ficha). Valores: `valencia`, `miami`; o `null`. |
| `product_id` | `integer` | sí | `Asset.id` del activo (D6). |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer` | sí | Unidades pedidas en la salida rechazada. |
| `currency` | `enum \| null` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). `null` si `office` es `null`. Valores: `EUR`, `USD`; o `null`. |
| `error_code` | `enum` | sí | `code` de la respuesta. Valores: `asset_not_found`, `office_mismatch`, `insufficient_stock`. |
| `exit_type` | `enum` | sí | Tipo de salida pedida. Valores: `allocation`, `consumption`. |
| `available_stock` | `integer \| null` | sí | Stock disponible (`available`) si el motivo es `insufficient_stock`; `null` en los demás. |

```json
{
  "eventId": "be7364f8-e825-4a30-82d1-6051cdc03f70",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "outbound_order_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "9a359961-f918-403b-8f83-f44b04ce0415",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": 20,
    "currency": "EUR",
    "error_code": "insufficient_stock",
    "exit_type": "allocation",
    "available_stock": 13
  }
}
```

#### `inventory_validation_failed`

- **Clasificación:** oportunidad · **Categoría:** inventario · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P1, P4, P5, P6
- **Descripción:** Una escritura del inventario ha llegado a la API con el body mal formado (422).
- **Frase:** Capturamos `inventory_validation_failed` porque necesitamos saber qué productos y qué campos acumulan más errores de validación (pregunta literal del tech lead), lo que nos permite tomar la decisión de mejorar la validación en cliente o el texto de ayuda de los campos que más fallan, o detectar integraciones que llaman mal a la API.
- **Se dispara:** 422 en `POST /inventory/products`, `/inventory/orders/inbound` u `/inventory/orders/outbound`, salvo que sea el caso 2 de `direct_stock_edit_rejected`.
- **Punto exacto:** `services/api/app/core/errors.py:230-233` (`_validation_exception_handler`), filtrando por la plantilla de la ruta.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** La persona ya ve el error junto al campo; la mejora de la interfaz se decide sobre semanas de datos.
- **PII y sanitización:** Nunca `msg` ni `input` de los errores. `product_id` y `office` solo si el body los trae válidos (`asset_id` entero; `office` del vocabulario); en el alta de un activo, `product_id` es `null`.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `office` | `enum \| null` | sí | Oficina del activo, en minúsculas (`Valencia` → `valencia`, D6). `null` si no se puede saber (ver la ficha). Valores: `valencia`, `miami`; o `null`. |
| `product_id` | `integer \| null` | sí | `Asset.id` del activo (D6). `null` si la petición no identifica un activo. |
| `product_category` | `enum \| null` | sí | Categoría del BRIEFING (`Asset.product_category`, P1). `null` si el activo no es material de formación ni de incorporación (D1-a), si aún no está clasificado o si no hay activo. Valores: `training_kit`, `certification`, `onboarding_equipment`; o `null`. |
| `programme_id` | `string \| null` | sí | Programa o área del activo (`Asset.programme_id`, P1), slug como `ventas-b2b` o `liderazgo-basico` (ejemplos del BRIEFING). `null` si el activo no tiene programa o no hay activo. Patrón `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `quantity` | `integer \| null` | sí | `quantity` del body si es un entero válido; `null` si no. |
| `currency` | `enum \| null` | sí | Moneda de la oficina (BRIEFING §6: `EUR` en Valencia, `USD` en Miami), derivada en la API, nunca convertida (D3). `null` si `office` es `null`. Valores: `EUR`, `USD`; o `null`. |
| `route_template` | `enum` | sí | Plantilla de la ruta. Valores: `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`. |
| `fields` | `array<string>` | sí | Último elemento de cada `loc` (`quantity`, `assigned_to`, `body`…), sin repetir. Nombres de campo, nunca valores. |
| `error_types` | `array<string>` | sí | `type` de Pydantic de cada error (`greater_than_equal`, `extra_forbidden`…), sin repetir. |

```json
{
  "eventId": "50c2d9cb-17f6-44b3-8a2d-80404e071f83",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "inventory_validation_failed",
  "schemaVersion": "1.0.0",
  "requestId": "39312a69-fa30-4ea9-8e39-e15b4040be6d",
  "properties": {
    "office": "valencia",
    "product_id": 7,
    "product_category": "training_kit",
    "programme_id": "ventas-b2b",
    "quantity": null,
    "currency": "EUR",
    "route_template": "/inventory/orders/outbound",
    "fields": [
      "quantity",
      "assigned_to"
    ],
    "error_types": [
      "greater_than_equal",
      "value_error"
    ]
  }
}
```

### 6.3 Oportunidades — autenticación

#### `user_logged_in`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Login correcto: la API ha emitido un JWT (y con él un `sid` nuevo).
- **Frase:** Capturamos `user_logged_in` porque necesitamos saber cuántas sesiones abren al día los operadores, de qué rol y a qué horas, lo que nos permite tomar la decisión de dimensionar el soporte y planificar ventanas de mantenimiento fuera de las horas de uso.
- **Se dispara:** `POST /auth/login` responde 200.
- **Punto exacto:** `services/api/app/routes/auth.py:46` (antes del `return Token(...)`); `userId` y `sessionId` son el `sub` y el `sid` del token recién creado.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Patrones de uso diarios; ninguna decisión depende del minuto exacto de un login correcto.
- **PII y sanitización:** Nunca el email ni la contraseña.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `role` | `enum` | sí | Rol del usuario. Valores: `admin`, `manager`, `user`. |
| `token_ttl_seconds` | `integer` | sí | Vigencia del token emitido (`expires_in`). |

```json
{
  "eventId": "91c2a0b2-b0a6-4fbd-84e4-90641958338d",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "user_logged_in",
  "schemaVersion": "1.0.0",
  "requestId": "494f82d4-f9e5-4246-8d05-a21b424d7e46",
  "properties": {
    "role": "user",
    "token_ttl_seconds": 3600
  }
}
```

#### `login_failed`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P5, P6
- **Descripción:** Login rechazado (401 `invalid_credentials`).
- **Frase:** Capturamos `login_failed` porque necesitamos saber cuántos intentos de login fallidos hay por día (pregunta literal del tech lead) y si llegan en ráfagas, lo que nos permite tomar la decisión de añadir bloqueo por intentos o rate limiting (hoy no existe, SPECS §22) y detectar ataques de credenciales a tiempo.
- **Se dispara:** `POST /auth/login` responde 401.
- **Punto exacto:** `services/api/app/routes/auth.py:42` (email mal formado) y `:45` (credenciales incorrectas).
- **Identidad:** `userId` y `sessionId` siempre `null` (actor anónimo). `requestId` siempre presente.
- **Por qué stream:** Una ráfaga de fallos es un posible ataque de credenciales: detectarla en minutos permite cortar el origen antes de que acierte.
- **PII y sanitización:** Ni el email ni ningún hash del email (se revierte por diccionario), ni la IP (D9). Por eso no se identifica la cuenta atacada.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `reason` | `enum` | sí | `malformed_email` (línea 42) o `invalid_credentials` (línea 45: email desconocido, contraseña incorrecta o usuario inactivo, sin distinguir, como la API). Valores: `malformed_email`, `invalid_credentials`. |
| `suppressed_count` | `integer` | sí | Eventos iguales (misma clave de throttle) descartados desde la última emisión (§7.2). 0 si no se descartó ninguno. |

```json
{
  "eventId": "d5016e1f-dbf1-438a-8a15-21e9d985820e",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "login_failed",
  "schemaVersion": "1.0.0",
  "requestId": "be0d339e-86f7-4c23-8a05-c1a9b8093754",
  "properties": {
    "reason": "invalid_credentials",
    "suppressed_count": 0
  }
}
```

#### `user_registered`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P5, P6
- **Descripción:** Se ha creado una cuenta con el registro público (`POST /users` → 201).
- **Frase:** Capturamos `user_registered` porque necesitamos saber cuántas cuentas se crean con un registro público que no exige aprobación, lo que nos permite tomar la decisión de mantener el registro abierto o pasar a altas aprobadas por un admin.
- **Se dispara:** `POST /users` responde 201.
- **Punto exacto:** `services/api/app/routes/users.py:21-30` (tras `service.create_user`).
- **Identidad:** `userId` y `sessionId` siempre `null` (actor anónimo). `requestId` siempre presente.
- **Por qué batch:** La decisión (abrir o cerrar el registro) es de política, sobre semanas de datos.
- **PII y sanitización:** Allowlist vacía: ni email, ni perfil, ni el id nuevo (el actor es anónimo).

Allowlist vacía: `properties` es `{}` y cualquier clave se rechaza.

```json
{
  "eventId": "c6e5d382-a838-4a1c-8829-6b010b7190b5",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "user_registered",
  "schemaVersion": "1.0.0",
  "requestId": "58c15c2b-7efc-40f3-8bcc-f4615de14af6",
  "properties": {}
}
```

#### `registration_failed`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P5, P6
- **Descripción:** El registro público ha fallado: email ya registrado (409) o datos no válidos (422).
- **Frase:** Capturamos `registration_failed` porque necesitamos saber si la gente se intenta registrar con emails que ya existen o tropieza con las reglas de contraseña, lo que nos permite tomar la decisión de mejorar los textos del formulario o enlazar a la recuperación de contraseña desde el registro.
- **Se dispara:** `POST /users` responde 409 `email_already_registered` o 422.
- **Punto exacto:** `services/api/app/core/errors.py:207-217` (409) y `:230-233` (422), filtrando `POST /users`.
- **Identidad:** `userId` y `sessionId` siempre `null` (actor anónimo). `requestId` siempre presente.
- **Por qué batch:** Mejora de la interfaz: se decide sobre semanas.
- **PII y sanitización:** Ni el email ni ningún valor enviado.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `reason` | `enum` | sí | Motivo. Valores: `email_already_registered`, `validation_error`. |
| `fields` | `array<string>` | sí | Campos con error del 422 (`password`, `email`…); vacío en el 409. |

```json
{
  "eventId": "7d0c80be-3476-4598-89be-95bfcbff5401",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "registration_failed",
  "schemaVersion": "1.0.0",
  "requestId": "6a196227-ae0d-4444-8dd5-c4264921f8dc",
  "properties": {
    "reason": "validation_error",
    "fields": [
      "password"
    ]
  }
}
```

#### `session_expired`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Una petición ha llegado con un token de firma válida pero caducado: la sesión ha expirado.
- **Frase:** Capturamos `session_expired` porque necesitamos saber si las sesiones caducan en mitad del trabajo (la vigencia de `ACCESS_TOKEN_EXPIRE_MINUTES` es corta para el uso real), lo que nos permite tomar la decisión de ajustar la vigencia del token o priorizar los refresh tokens (mejora futura de SPECS §22).
- **Se dispara:** `get_current_user` rechaza el token y, al decodificarlo de nuevo sin comprobar `exp` (pero sí la firma), resulta válido y caducado. Una vez por `sid` (§7.2).
- **Punto exacto:** `services/api/app/auth/dependencies.py:56-58` (rechazo) + `services/api/app/auth/security.py:84` (`decode_access_token`; P4 añade la decodificación sin `exp` para clasificar el motivo). El cliente reacciona en `uis/backoffice/lib/api-client.ts:253-256`, que no emite nada (lo hace la API).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** La decisión (vigencia del token) se toma con la distribución de varias semanas.
- **PII y sanitización:** Ninguna. `userId` y `sessionId` salen del token caducado (firma válida).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `route_template` | `enum` | sí | Ruta donde caducó. Valores: `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/users`, `/users/{user_id}`, `/profiles/me`, `/suppliers`, `/suppliers/{supplier_id}`, `/suppliers/{supplier_id}/rate`, `/suppliers/{supplier_id}/status`, `/api/incidents/analyze`, `/api/incidents/results/export`, `/api/incidents`, `/api/incidents/summary`, `/api/incidents/{incident_id}`, `/api/incidents/{incident_id}/status`, `/inventory/products`, `/inventory/products/{id}`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`, `/telemetry/events`. |
| `session_age_seconds` | `integer` | sí | Ahora − `iat` del token. |
| `token_ttl_seconds` | `integer` | sí | `exp` − `iat` del token. |

```json
{
  "eventId": "015e212c-b2c7-40d7-80ce-701deb246c57",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "session_expired",
  "schemaVersion": "1.0.0",
  "requestId": "e9a241b4-187a-4267-87e0-7da45602f941",
  "properties": {
    "route_template": "/inventory/orders/outbound",
    "session_age_seconds": 3612,
    "token_ttl_seconds": 3600
  }
}
```

#### `auth_token_rejected`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P5, P6
- **Descripción:** Una petición protegida ha traído un token que no es una sesión caducada: mal formado, con otra firma, sin claims, o de un usuario borrado o inactivo.
- **Frase:** Capturamos `auth_token_rejected` porque necesitamos saber si hay tokens manipulados o firmados con otra clave circulando, o usuarios desactivados que siguen intentando entrar, lo que nos permite tomar la decisión de rotar `JWT_SECRET_KEY`, investigar el origen o confirmar la baja de un usuario.
- **Se dispara:** `get_current_user` responde 401 con un `Authorization: Bearer` presente y el motivo no es la caducidad. Sin cabecera no se emite (ver exclusiones).
- **Punto exacto:** `services/api/app/auth/dependencies.py:56-64`.
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué stream:** Un token con otra firma es un indicio de ataque o de secreto filtrado: hay que actuar en minutos.
- **PII y sanitización:** Nunca el token. `userId` = `sub` solo si la firma es válida (`unknown_user`, `inactive_user`); si no, `null`.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `reason` | `enum` | sí | Motivo del rechazo. Valores: `malformed`, `invalid_signature`, `missing_claims`, `unknown_user`, `inactive_user`. |
| `route_template` | `enum` | sí | Ruta protegida pedida. Valores: `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/users`, `/users/{user_id}`, `/profiles/me`, `/suppliers`, `/suppliers/{supplier_id}`, `/suppliers/{supplier_id}/rate`, `/suppliers/{supplier_id}/status`, `/api/incidents/analyze`, `/api/incidents/results/export`, `/api/incidents`, `/api/incidents/summary`, `/api/incidents/{incident_id}`, `/api/incidents/{incident_id}/status`, `/inventory/products`, `/inventory/products/{id}`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`, `/telemetry/events`. |
| `suppressed_count` | `integer` | sí | Eventos iguales (misma clave de throttle) descartados desde la última emisión (§7.2). 0 si no se descartó ninguno. |

```json
{
  "eventId": "1f36d89b-a6be-4b01-86cb-24c0cd50b9dc",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "auth_token_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "dc193a0b-c9a3-4fae-8092-ed2a3667ca39",
  "properties": {
    "reason": "invalid_signature",
    "route_template": "/inventory/products",
    "suppressed_count": 2
  }
}
```

#### `user_logged_out`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** El usuario ha cerrado la sesión desde el backoffice.
- **Frase:** Capturamos `user_logged_out` porque necesitamos saber si los operadores cierran sesión o dejan las sesiones abiertas en equipos compartidos de la oficina, lo que nos permite tomar la decisión de acortar la vigencia del token o añadir cierre por inactividad.
- **Se dispara:** Clic en «Cerrar sesión». Se envía **antes** de borrar el token (con `keepalive`), para que el colector lo atribuya.
- **Punto exacto:** `uis/backoffice/components/auth/account-nav.tsx:46` (`header_button`) y `uis/backoffice/components/auth/auth-guard.tsx:45` (`session_error_screen`), antes de `session.logout()` (`uis/backoffice/hooks/use-auth-session.ts:210`).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Hábito de uso; la decisión es de política de sesiones.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `trigger` | `enum` | sí | Desde dónde se cerró. Valores: `header_button`, `session_error_screen`. |

```json
{
  "eventId": "7735fc60-41a3-44d8-83a6-35daa9f5353f",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "user_logged_out",
  "schemaVersion": "1.0.0",
  "requestId": "d3b44331-fd6b-4796-8798-0b6d0edd1bb3",
  "properties": {
    "trigger": "header_button"
  }
}
```

#### `password_reset_requested`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P5, P6
- **Descripción:** Alguien ha pedido un enlace de restablecimiento (`POST /auth/forgot-password`, siempre 200).
- **Frase:** Capturamos `password_reset_requested` porque necesitamos saber cuánta gente olvida la contraseña y si se abusa de un endpoint sin rate limiting (SPECS §27), lo que nos permite tomar la decisión de añadir rate limiting o revisar la política de contraseñas.
- **Se dispara:** `UserService.request_password_reset` registra la auditoría.
- **Punto exacto:** `services/api/app/auth/service.py:144` (email desconocido) y `:149` (cuenta existente), junto al `record_password_event` de AUTH-03.
- **Identidad:** `userId` y `sessionId` siempre `null` (actor anónimo). `requestId` siempre presente.
- **Por qué batch:** Tendencia; una ráfaga la cubre la regla general de throttle y alerta (§7.2).
- **PII y sanitización:** Ni el email ni la IP (la auditoría de AUTH-03 sí la guarda; la telemetría no, D9). El actor es anónimo: `userId` `null`.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `account_found` | `boolean` | sí | `true` si el email corresponde a una cuenta (motivo `unknown_email` de la auditoría si no). No se devuelve al cliente. |

```json
{
  "eventId": "904c6ef0-156a-4373-8fee-79ca0692f89d",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "password_reset_requested",
  "schemaVersion": "1.0.0",
  "requestId": "c126d86b-5bea-418d-8948-a542fa99edab",
  "properties": {
    "account_found": true
  }
}
```

#### `password_reset_completed`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P5, P6
- **Descripción:** Un enlace de restablecimiento se ha usado con éxito.
- **Frase:** Capturamos `password_reset_completed` porque necesitamos saber qué parte de los enlaces pedidos se completa (embudo pedido → completado), lo que nos permite tomar la decisión de revisar el email (texto, entrega con Resend) o la vigencia si el embudo cae.
- **Se dispara:** `UserService.reset_password` termina bien.
- **Punto exacto:** `services/api/app/auth/service.py:158`.
- **Identidad:** `sessionId` siempre `null`; `userId` es la cuenta afectada si se conoce, si no `null`. `requestId` siempre presente.
- **Por qué batch:** Embudo semanal.
- **PII y sanitización:** Allowlist vacía. `userId` es la cuenta restablecida (el actor llega con el enlace); `sessionId` `null`.

Allowlist vacía: `properties` es `{}` y cualquier clave se rechaza.

```json
{
  "eventId": "27028f95-92b7-47e8-8752-20fb2670d9a7",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "password_reset_completed",
  "schemaVersion": "1.0.0",
  "requestId": "60001607-1d11-4538-829b-2abdfc8591d3",
  "properties": {}
}
```

#### `password_reset_rejected`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P5, P6
- **Descripción:** Un enlace de restablecimiento no se ha podido usar (400 `invalid_reset_token`).
- **Frase:** Capturamos `password_reset_rejected` porque necesitamos saber si los enlaces caducan antes de que la gente los use, o si se reutilizan, lo que nos permite tomar la decisión de ajustar `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` dentro de 15–60 o mejorar el texto del email.
- **Se dispara:** `UserService.reset_password` rechaza el token.
- **Punto exacto:** `services/api/app/auth/service.py:156` (el `reason` de la auditoría).
- **Identidad:** `sessionId` siempre `null`; `userId` es la cuenta afectada si se conoce, si no `null`. `requestId` siempre presente.
- **Por qué batch:** Se decide sobre la distribución de motivos de semanas.
- **PII y sanitización:** Nunca el token. `userId` solo si el token era de una cuenta (`expired`, `used`); `null` en `unknown`.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `reason` | `enum` | sí | Motivo de la auditoría de AUTH-03. Valores: `unknown`, `expired`, `used`. |

```json
{
  "eventId": "159549b2-d9cd-4c2a-84c9-fa15683eff3b",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "password_reset_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "4e6d7090-feab-4d4e-85f0-261868af977d",
  "properties": {
    "reason": "expired"
  }
}
```

#### `password_changed`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Un usuario con sesión ha cambiado su contraseña.
- **Frase:** Capturamos `password_changed` porque necesitamos saber con qué frecuencia se cambian las contraseñas por iniciativa propia, lo que nos permite tomar la decisión de implantar o no una política de rotación de contraseñas.
- **Se dispara:** `POST /auth/change-password` responde 200.
- **Punto exacto:** `services/api/app/auth/service.py:167`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Política, sobre meses.
- **PII y sanitización:** Allowlist vacía.

Allowlist vacía: `properties` es `{}` y cualquier clave se rechaza.

```json
{
  "eventId": "4412ef42-43e7-4124-8835-d71dc6c4d70b",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "password_changed",
  "schemaVersion": "1.0.0",
  "requestId": "a320a745-4a60-4e6b-892d-e93f3d019546",
  "properties": {}
}
```

#### `password_change_rejected`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Un cambio de contraseña con sesión ha fallado porque la contraseña actual no coincide (400 `incorrect_password`).
- **Frase:** Capturamos `password_change_rejected` porque necesitamos saber si alguien con una sesión ajena (equipo compartido) intenta cambiar la contraseña, lo que nos permite tomar la decisión de avisar al usuario o forzar el cierre de sesión tras varios intentos.
- **Se dispara:** `UserService.change_password` rechaza la contraseña actual.
- **Punto exacto:** `services/api/app/auth/service.py:163`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Sin volumen que justifique tiempo real; los intentos repetidos los recoge el throttle (§7.2).
- **PII y sanitización:** Ninguna contraseña.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `reason` | `enum` | sí | Único motivo hoy. Valores: `incorrect_password`. |

```json
{
  "eventId": "6bffb384-3f40-4f15-8cba-91470854c138",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "password_change_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "9631a5c9-c311-4c95-88b6-91335efbbd13",
  "properties": {
    "reason": "incorrect_password"
  }
}
```

#### `password_reset_email_failed`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P6
- **Descripción:** El email de restablecimiento no se ha podido entregar (tarea en segundo plano, después de responder).
- **Frase:** Capturamos `password_reset_email_failed` porque necesitamos saber si la gente se queda sin poder recuperar el acceso porque Resend falla o no está configurado, lo que nos permite tomar la decisión de revisar la clave o el dominio de Resend en el momento.
- **Se dispara:** `log_email_delivery_failure` se ejecuta.
- **Punto exacto:** `services/api/app/core/errors.py:277-284` (lo llama la tarea de `services/api/app/routes/auth.py:76-89`).
- **Identidad:** `userId` y `sessionId` siempre `null` (evento del sistema, sin actor). `requestId` siempre `null` (no hay petición).
- **Por qué stream:** Cada fallo es una persona sin acceso: el arreglo (configuración) es inmediato y la petición original ya respondió 200, así que nadie más se enteraría.
- **PII y sanitización:** Nunca el destinatario ni el enlace.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `error_class` | `string` | sí | Nombre de la clase de la excepción (`EmailNotConfiguredError`, `EmailDeliveryError`…), nunca su mensaje. Patrón `^[A-Za-z][A-Za-z0-9]*$`. |

```json
{
  "eventId": "9d24f567-cf94-48f7-864a-c17b789d8dfb",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "password_reset_email_failed",
  "schemaVersion": "1.0.0",
  "requestId": null,
  "properties": {
    "error_class": "EmailNotConfiguredError"
  }
}
```

#### `access_denied`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Un usuario autenticado ha pedido algo para lo que no tiene permiso (403 `forbidden`).
- **Frase:** Capturamos `access_denied` porque necesitamos saber si los roles asignados no encajan con lo que la gente necesita hacer, o si alguien sondea recursos ajenos, lo que nos permite tomar la decisión de ajustar la asignación de roles o investigar un patrón de sondeo.
- **Se dispara:** Cualquier 403 de las rutas de usuarios.
- **Punto exacto:** `services/api/app/auth/dependencies.py:73` (`admin_required`) y `:87` (`not_owner`); `services/api/app/routes/users.py:54` (`role_change_forbidden`) y `:56` (`password_change_forbidden`).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Se revisa con la asignación de roles, no en minutos.
- **PII y sanitización:** Nunca el id del usuario ajeno pedido.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `reason` | `enum` | sí | Motivo. Valores: `admin_required`, `not_owner`, `role_change_forbidden`, `password_change_forbidden`. |
| `route_template` | `enum` | sí | Ruta. Valores: `/users`, `/users/{user_id}`. |
| `http_method` | `enum` | sí | Método. Valores: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. |

```json
{
  "eventId": "b24a6ab2-3d67-496f-8a15-9138102dbe62",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "access_denied",
  "schemaVersion": "1.0.0",
  "requestId": "92f5b23c-0155-4faa-89d1-8fbbed3daacb",
  "properties": {
    "reason": "not_owner",
    "route_template": "/users/{user_id}",
    "http_method": "GET"
  }
}
```

#### `user_role_changed`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Un admin ha cambiado el rol de un usuario (`PUT /users/{id}` con `role`).
- **Frase:** Capturamos `user_role_changed` porque necesitamos saber quién gana privilegios de admin y cuándo, lo que nos permite tomar la decisión de revertir de inmediato una escalada de privilegios no autorizada.
- **Se dispara:** `PUT /users/{user_id}` responde 200 y el rol ha cambiado.
- **Punto exacto:** `services/api/app/routes/users.py:57` (`service.update_user`; el rol anterior se lee antes con `service.get_user_by_id`).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué stream:** Una escalada a admin no autorizada da acceso a todos los usuarios: cada minuto cuenta.
- **PII y sanitización:** `target_user_id` es seudónimo, con la misma retención que `userId` (§8.3).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `target_user_id` | `string` | sí | Id (seudónimo) del usuario afectado. Patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. |
| `from_role` | `enum` | sí | Rol anterior. Valores: `admin`, `manager`, `user`. |
| `to_role` | `enum` | sí | Rol nuevo. Valores: `admin`, `manager`, `user`. |

```json
{
  "eventId": "4c8e005d-dad1-4ad6-8935-51defedfa449",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "user_role_changed",
  "schemaVersion": "1.0.0",
  "requestId": "9d5421dc-6c38-400a-8c52-93bab4104129",
  "properties": {
    "target_user_id": "9c7a5e3b-1d2f-4a6b-8c0e-2f4a6c8e0b1d",
    "from_role": "user",
    "to_role": "admin"
  }
}
```

#### `user_deleted`

- **Clasificación:** oportunidad · **Categoría:** autenticación · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha borrado un usuario (y su perfil).
- **Frase:** Capturamos `user_deleted` porque necesitamos saber cuántas cuentas se borran y si las borra el propio usuario o un admin, lo que nos permite tomar la decisión de sustituir el borrado por la desactivación (`is_active`) para conservar la trazabilidad de las órdenes.
- **Se dispara:** `DELETE /users/{user_id}` responde 204.
- **Punto exacto:** `services/api/app/routes/users.py:71` (tras `service.delete_user`).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Decisión de política.
- **PII y sanitización:** Seudónimo, como `user_role_changed`.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `target_user_id` | `string` | sí | Id del usuario borrado. Sus órdenes conservan el `user_uuid`. Patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. |
| `self_deletion` | `boolean` | sí | `true` si se borró a sí mismo. |

```json
{
  "eventId": "9833cb21-a4f9-4bd9-89ef-cd8fdacbb588",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "user_deleted",
  "schemaVersion": "1.0.0",
  "requestId": "05c1dc43-3797-4499-8982-3fb8624f6f04",
  "properties": {
    "target_user_id": "9c7a5e3b-1d2f-4a6b-8c0e-2f4a6c8e0b1d",
    "self_deletion": false
  }
}
```

### 6.4 Oportunidades — navegación

#### `page_viewed`

- **Clasificación:** oportunidad · **Categoría:** navegación · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** El usuario ha permanecido al menos 1 s en una página del backoffice.
- **Frase:** Capturamos `page_viewed` porque necesitamos saber qué secciones visitan más los operadores (pregunta literal del tech lead) y en qué orden, lo que nos permite tomar la decisión de priorizar las mejoras y la formación en las secciones más usadas, y retirar o rediseñar las que nadie visita.
- **Se dispara:** Cambio de `usePathname()` que se mantiene 1 s (descarta redirecciones como `/inventory` → `/inventory/products` o el guard → `/login`).
- **Punto exacto:** Componente nuevo `components/telemetry/page-view-tracker.tsx` en `uis/backoffice/app/layout.tsx`, con `usePathname` (patrón de `uis/backoffice/components/ui/nav-link.tsx:33-34`).
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Uso agregado por día o semana; nadie decide en tiempo real con una visita.
- **PII y sanitización:** Nunca la query string (`?token=` de `/reset-password` es un secreto) ni el path real.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `route_template` | `enum` | sí | Ruta de la página, sin query string. Valores: `/`, `/login`, `/register`, `/forgot-password`, `/reset-password`, `/account/profile`, `/account/change-password`, `/incidents`, `/suppliers`, `/incident-manager`, `/incident-manager/new`, `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`. |
| `previous_route_template` | `enum \| null` | sí | Página anterior en la misma pestaña; `null` en la primera. Valores: `/`, `/login`, `/register`, `/forgot-password`, `/reset-password`, `/account/profile`, `/account/change-password`, `/incidents`, `/suppliers`, `/incident-manager`, `/incident-manager/new`, `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`; o `null`. |
| `entry` | `enum` | sí | Primera carga de la pestaña o navegación dentro de la app. Valores: `initial_load`, `in_app_navigation`. |

```json
{
  "eventId": "53d93f4c-b066-4763-8de3-04b5f0241872",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "page_viewed",
  "schemaVersion": "1.0.0",
  "requestId": "c0b21901-6832-42b0-87b8-a6971eeee671",
  "properties": {
    "route_template": "/inventory/orders/outbound",
    "previous_route_template": "/inventory/products",
    "entry": "in_app_navigation"
  }
}
```

#### `page_not_found_viewed`

- **Clasificación:** oportunidad · **Categoría:** navegación · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** Se ha mostrado la página 404 del backoffice.
- **Frase:** Capturamos `page_not_found_viewed` porque necesitamos saber si hay enlaces internos rotos (la página anterior era del propio backoffice), lo que nos permite tomar la decisión de corregir el enlace roto de la página de origen.
- **Se dispara:** Montaje de `not-found.tsx`.
- **Punto exacto:** `uis/backoffice/app/not-found.tsx:9`.
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Corrección de enlaces, sin urgencia.
- **PII y sanitización:** Nunca el path pedido (texto arbitrario, puede llevar datos).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `previous_route_template` | `enum \| null` | sí | Página anterior; `null` si se llegó desde fuera. Valores: `/`, `/login`, `/register`, `/forgot-password`, `/reset-password`, `/account/profile`, `/account/change-password`, `/incidents`, `/suppliers`, `/incident-manager`, `/incident-manager/new`, `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`; o `null`. |

```json
{
  "eventId": "53f683b3-8c71-4136-8198-11090a6be3ad",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "page_not_found_viewed",
  "schemaVersion": "1.0.0",
  "requestId": "4d1a642b-38e6-451a-89cd-bf78d4747ae8",
  "properties": {
    "previous_route_template": "/incident-manager"
  }
}
```

### 6.5 Oportunidades — flujos

#### `form_started`

- **Clasificación:** oportunidad · **Categoría:** flujos · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** El usuario ha empezado a rellenar un formulario (primer cambio de un campo).
- **Frase:** Capturamos `form_started` porque necesitamos saber cuántas veces se empieza cada flujo (base del embudo de abandono), lo que nos permite tomar la decisión de priorizar el rediseño del formulario que más se abandona (la tasa sale de comparar `form_started` con `form_submitted` correctos).
- **Se dispara:** Primer `onChange` de cualquier campo desde el montaje o desde el último envío correcto.
- **Punto exacto:** Hook nuevo `hooks/use-form-telemetry.ts`, usado por las vistas de formulario (p. ej. `uis/backoffice/components/inventory/inbound-form.tsx:63` y `outbound-form.tsx:116`).
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Embudo semanal.
- **PII y sanitización:** Ningún valor escrito.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `form` | `enum` | sí | Formulario. Valores: `login`, `register`, `forgot_password`, `reset_password`, `change_password`, `profile`, `supplier_create`, `incident_create`, `incident_analysis_upload`, `inbound_order`, `outbound_order`. |

```json
{
  "eventId": "d3c2a54f-3550-452b-8f17-9b99a2f5143f",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "form_started",
  "schemaVersion": "1.0.0",
  "requestId": "4552390a-c55a-4f5d-8838-ba8b7550cc51",
  "properties": {
    "form": "outbound_order"
  }
}
```

#### `form_submitted`

- **Clasificación:** oportunidad · **Categoría:** flujos · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** Un envío de formulario ha terminado (con éxito o no).
- **Frase:** Capturamos `form_submitted` porque necesitamos saber cuánto se tarda en completar cada flujo y cuántos intentos hacen falta, lo que nos permite tomar la decisión de simplificar los formularios lentos o con muchos reintentos.
- **Se dispara:** Fin de un envío. En el inventario: `uis/backoffice/hooks/use-inbound-form.ts:107` / `:110` y `uis/backoffice/hooks/use-outbound-form.ts:210` / `:215`.
- **Punto exacto:** Los mismos hooks, al despachar `submit_succeeded` o `submit_failed`; `requestId` es el `X-Request-ID` de la petición del envío.
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Mejora de la interfaz con datos de semanas.
- **PII y sanitización:** Ningún valor escrito.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `form` | `enum` | sí | Formulario. Valores: `login`, `register`, `forgot_password`, `reset_password`, `change_password`, `profile`, `supplier_create`, `incident_create`, `incident_analysis_upload`, `inbound_order`, `outbound_order`. |
| `outcome` | `enum` | sí | Resultado según el `kind` del error del servicio. Valores: `success`, `validation_error`, `api_rejected`, `session_expired`, `network_error`, `server_error`. |
| `duration_ms` | `integer` | sí | Tiempo desde `form_started`. |
| `attempt_number` | `integer` | sí | Envíos desde `form_started` (1 = a la primera). |

```json
{
  "eventId": "699cad36-bb80-429b-8571-97fcc80a1b59",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "form_submitted",
  "schemaVersion": "1.0.0",
  "requestId": "e6804271-ee4d-4d2e-8840-c12c3b8954d9",
  "properties": {
    "form": "outbound_order",
    "outcome": "api_rejected",
    "duration_ms": 41250,
    "attempt_number": 1
  }
}
```

#### `form_abandoned`

- **Clasificación:** oportunidad · **Categoría:** flujos · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** Un formulario empezado se ha dejado sin un envío correcto.
- **Frase:** Capturamos `form_abandoned` porque necesitamos saber si hay flujos que se abandonan a la mitad (pregunta literal del tech lead) y en qué campo, lo que nos permite tomar la decisión de rediseñar el paso o el campo donde se abandona.
- **Se dispara:** Desmontaje de la vista o `pagehide` con el formulario empezado y sin `success` desde `form_started`.
- **Punto exacto:** El mismo `hooks/use-form-telemetry.ts`; en `pagehide` se envía con `keepalive`.
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Embudo semanal.
- **PII y sanitización:** Solo el nombre del campo, nunca su valor.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `form` | `enum` | sí | Formulario. Valores: `login`, `register`, `forgot_password`, `reset_password`, `change_password`, `profile`, `supplier_create`, `incident_create`, `incident_analysis_upload`, `inbound_order`, `outbound_order`. |
| `last_field` | `string \| null` | sí | Nombre del último campo tocado; `null` si no se sabe. Patrón `^[a-z_]+$`. |
| `had_validation_error` | `boolean` | sí | Si llegó a ver un error de validación. |
| `had_api_error` | `boolean` | sí | Si llegó a ver un error de la API. |
| `duration_ms` | `integer` | sí | Tiempo desde `form_started`. |

```json
{
  "eventId": "b9811c2d-6c99-45bc-810c-5ba27effa42e",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "form_abandoned",
  "schemaVersion": "1.0.0",
  "requestId": "bc277116-1139-47ce-86c0-db262ea570c2",
  "properties": {
    "form": "outbound_order",
    "last_field": "assigned_to",
    "had_validation_error": true,
    "had_api_error": false,
    "duration_ms": 95000
  }
}
```

#### `form_validation_failed`

- **Clasificación:** oportunidad · **Categoría:** flujos · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** La validación en cliente ha bloqueado un envío (sin petición a la API).
- **Frase:** Capturamos `form_validation_failed` porque necesitamos saber qué campos se rellenan mal antes de llegar a la API, lo que nos permite tomar la decisión de mejorar los textos de ayuda o los valores por defecto de esos campos.
- **Se dispara:** El validador del servicio devuelve errores.
- **Punto exacto:** `uis/backoffice/services/inventory.service.ts:289` y `:305`, `uis/backoffice/services/suppliers.service.ts:210`, `uis/backoffice/services/incident-manager.service.ts:270` y los `validate*Form` de `uis/backoffice/services/auth.service.ts:107-135`.
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Mejora de la interfaz.
- **PII y sanitización:** Solo nombres de campo.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `form` | `enum` | sí | Formulario. Valores: `login`, `register`, `forgot_password`, `reset_password`, `change_password`, `profile`, `supplier_create`, `incident_create`, `incident_analysis_upload`, `inbound_order`, `outbound_order`. |
| `fields` | `array<string>` | sí | Campos con error. |

```json
{
  "eventId": "7d5f052e-7012-404b-8af3-0496f355ee2f",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "form_validation_failed",
  "schemaVersion": "1.0.0",
  "requestId": "ad9fb98f-3a97-461a-832f-b9e425f3966c",
  "properties": {
    "form": "inbound_order",
    "fields": [
      "quantity",
      "supplier"
    ]
  }
}
```

### 6.6 Oportunidades — errores

#### `frontend_error_captured`

- **Clasificación:** oportunidad · **Categoría:** errores · **Emisor:** frontend · **Entrega:** stream · **Prerrequisitos:** P4, P8
- **Descripción:** Un límite de error de Next ha capturado un error de render en el backoffice.
- **Frase:** Capturamos `frontend_error_captured` porque necesitamos saber qué páginas fallan en el navegador y si un despliegue ha introducido un error, lo que nos permite tomar la decisión de revertir o corregir el despliegue que rompe una página.
- **Se dispara:** Montaje de `error.tsx` o `global-error.tsx`.
- **Punto exacto:** `uis/backoffice/app/error.tsx:23` (`route`) y `uis/backoffice/app/global-error.tsx:25` (`global`), en un `useEffect`. **El error no se lee** (regla de `uis/backoffice/CLAUDE.md`).
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué stream:** Una página rota bloquea a los operadores: hay que saberlo en minutos, no al día siguiente.
- **PII y sanitización:** Ni `error.message`, ni `digest`, ni `stack` (pueden llevar datos).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `boundary` | `enum` | sí | Límite que lo capturó. Valores: `route`, `global`. |
| `route_template` | `enum \| null` | sí | Página donde ocurrió; `null` si el path no es una ruta conocida. Valores: `/`, `/login`, `/register`, `/forgot-password`, `/reset-password`, `/account/profile`, `/account/change-password`, `/incidents`, `/suppliers`, `/incident-manager`, `/incident-manager/new`, `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`; o `null`. |
| `suppressed_count` | `integer` | sí | Eventos iguales (misma clave de throttle) descartados desde la última emisión (§7.2). 0 si no se descartó ninguno. |

```json
{
  "eventId": "fd7e72d9-a80c-4bde-8954-991f3e9f330d",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "frontend_error_captured",
  "schemaVersion": "1.0.0",
  "requestId": "852618e7-8daf-428b-8e80-7551cef0edbb",
  "properties": {
    "boundary": "route",
    "route_template": "/suppliers",
    "suppressed_count": 0
  }
}
```

#### `client_request_failed`

- **Clasificación:** oportunidad · **Categoría:** errores · **Emisor:** frontend · **Entrega:** stream · **Prerrequisitos:** P4, P5, P8
- **Descripción:** Una petición del backoffice no ha obtenido respuesta de la API: red, timeout o configuración.
- **Frase:** Capturamos `client_request_failed` porque necesitamos saber si la API es inalcanzable o lenta desde el navegador de los operadores (la API no puede contar sus propias caídas), lo que nos permite tomar la decisión de investigar la red, el contenedor o el timeout del cliente.
- **Se dispara:** `send` lanza `ApiNetworkError`, `ApiTimeoutError` o `ApiConfigError`.
- **Punto exacto:** `uis/backoffice/lib/api-client.ts:227` (`ApiConfigError`) y `:247-251` (timeout y red).
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué stream:** Es la única señal de una caída vista desde fuera: si la API no responde, ningún evento de la API llega.
- **PII y sanitización:** Ni la URL real ni la base URL.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `kind` | `enum` | sí | Tipo de fallo. Valores: `network`, `timeout`, `config`. |
| `http_method` | `enum` | sí | Método. Valores: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. |
| `api_route_template` | `enum` | sí | Ruta de la API normalizada en el cliente: segmentos numéricos o UUID → `{…}` con el nombre de la plantilla, sin query string. Valores: `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/users`, `/users/{user_id}`, `/profiles/me`, `/suppliers`, `/suppliers/{supplier_id}`, `/suppliers/{supplier_id}/rate`, `/suppliers/{supplier_id}/status`, `/api/incidents/analyze`, `/api/incidents/results/export`, `/api/incidents`, `/api/incidents/summary`, `/api/incidents/{incident_id}`, `/api/incidents/{incident_id}/status`, `/inventory/products`, `/inventory/products/{id}`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`, `/telemetry/events`. |
| `timeout_ms` | `integer \| null` | sí | Timeout aplicado si `kind = timeout`; `null` en los demás. |
| `suppressed_count` | `integer` | sí | Eventos iguales (misma clave de throttle) descartados desde la última emisión (§7.2). 0 si no se descartó ninguno. |

```json
{
  "eventId": "2476f60b-9d2e-4d75-8b64-c28876a8db6d",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "client_request_failed",
  "schemaVersion": "1.0.0",
  "requestId": "d85fb934-8162-41c8-8d1c-bd9336a29672",
  "properties": {
    "kind": "timeout",
    "http_method": "GET",
    "api_route_template": "/inventory/products",
    "timeout_ms": 15000,
    "suppressed_count": 0
  }
}
```

#### `server_error_returned`

- **Clasificación:** oportunidad · **Categoría:** errores · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P5, P6
- **Descripción:** La API ha respondido 500 `internal_error` por una excepción no prevista.
- **Frase:** Capturamos `server_error_returned` porque necesitamos saber qué rutas tienen errores no controlados y desde cuándo, lo que nos permite tomar la decisión de corregir el error o revertir el despliegue.
- **Se dispara:** `InternalErrorMiddleware` captura una excepción.
- **Punto exacto:** `services/api/app/core/errors.py:271` (junto al `logger.error` actual).
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué stream:** Un 500 es una operación de negocio perdida: se corrige en el momento.
- **PII y sanitización:** Nunca el mensaje ni la traza.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `http_method` | `enum` | sí | Método. Valores: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. |
| `route_template` | `enum` | sí | Plantilla de la ruta. Valores: `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/users`, `/users/{user_id}`, `/profiles/me`, `/suppliers`, `/suppliers/{supplier_id}`, `/suppliers/{supplier_id}/rate`, `/suppliers/{supplier_id}/status`, `/api/incidents/analyze`, `/api/incidents/results/export`, `/api/incidents`, `/api/incidents/summary`, `/api/incidents/{incident_id}`, `/api/incidents/{incident_id}/status`, `/inventory/products`, `/inventory/products/{id}`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`, `/telemetry/events`, `unmatched`. |
| `error_class` | `string` | sí | Clase de la excepción (lo mismo que ya registra el log). Patrón `^[A-Za-z][A-Za-z0-9]*$`. |
| `suppressed_count` | `integer` | sí | Eventos iguales (misma clave de throttle) descartados desde la última emisión (§7.2). 0 si no se descartó ninguno. |

```json
{
  "eventId": "bb0b9e9f-8bbb-4bb4-8a87-198fb05d201d",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "server_error_returned",
  "schemaVersion": "1.0.0",
  "requestId": "11287052-cda5-4436-82db-0bc8a1e1916c",
  "properties": {
    "http_method": "POST",
    "route_template": "/inventory/orders/inbound",
    "error_class": "IntegrityError",
    "suppressed_count": 0
  }
}
```

### 6.7 Oportunidades — salud técnica

#### `storage_unavailable_detected`

- **Clasificación:** oportunidad · **Categoría:** salud técnica · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P5, P6
- **Descripción:** Un almacén no responde y la API ha devuelto 503 `storage_unavailable`.
- **Frase:** Capturamos `storage_unavailable_detected` porque necesitamos saber cuándo y cuánto tiempo están caídos Supabase o los archivos TinyDB, lo que nos permite tomar la decisión de actuar sobre el almacén (restaurar el archivo, revisar Supabase) y medir su disponibilidad real.
- **Se dispara:** `log_storage_failure` se ejecuta.
- **Punto exacto:** `services/api/app/core/errors.py:287-294` (TinyDB, desde `GuardedJSONStorage`) y `:220-227` (PostgreSQL del inventario).
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué stream:** Con un almacén caído no funciona ninguna operación de su área (con `auth` caído, ninguna ruta protegida).
- **PII y sanitización:** Nunca la ruta del archivo, la URL de la base ni el mensaje.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `store` | `enum` | sí | Almacén. Valores: `suppliers`, `auth`, `incidents`, `inventory`. |
| `error_class` | `string` | sí | Clase de la excepción. Patrón `^[A-Za-z][A-Za-z0-9]*$`. |
| `route_template` | `enum` | sí | Ruta que lo detectó. Valores: `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/users`, `/users/{user_id}`, `/profiles/me`, `/suppliers`, `/suppliers/{supplier_id}`, `/suppliers/{supplier_id}/rate`, `/suppliers/{supplier_id}/status`, `/api/incidents/analyze`, `/api/incidents/results/export`, `/api/incidents`, `/api/incidents/summary`, `/api/incidents/{incident_id}`, `/api/incidents/{incident_id}/status`, `/inventory/products`, `/inventory/products/{id}`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`, `/telemetry/events`, `unmatched`. |
| `suppressed_count` | `integer` | sí | Eventos iguales (misma clave de throttle) descartados desde la última emisión (§7.2). 0 si no se descartó ninguno. |

```json
{
  "eventId": "54ec40b5-4f63-4caf-886a-ea4be0f8423a",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "storage_unavailable_detected",
  "schemaVersion": "1.0.0",
  "requestId": "3473b96a-2a55-4683-847e-e3f1846450eb",
  "properties": {
    "store": "inventory",
    "error_class": "OperationalError",
    "route_template": "/inventory/products",
    "suppressed_count": 14
  }
}
```

#### `api_startup_failed`

- **Clasificación:** oportunidad · **Categoría:** salud técnica · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P6
- **Descripción:** La API no ha podido arrancar porque la base del inventario no respondía.
- **Frase:** Capturamos `api_startup_failed` porque necesitamos saber cuántos arranques fallan por la base (Supabase pausado, credenciales), lo que nos permite tomar la decisión de revisar la configuración o el plan de Supabase.
- **Se dispara:** Se lanza `InventoryStartupError` en el lifespan.
- **Punto exacto:** `services/api/app/modules/inventory/database.py:44` (la clase) y su `raise` en el lifespan; se emite antes de relanzar.
- **Identidad:** `userId` y `sessionId` siempre `null` (evento del sistema, sin actor). `requestId` siempre `null` (no hay petición).
- **Por qué stream:** Sin arranque no hay plataforma: hay que actuar de inmediato.
- **PII y sanitización:** Ni host, ni usuario, ni URL.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `component` | `enum` | sí | Componente que falló. Valores: `inventory_database`. |
| `error_class` | `string` | sí | Clase del error original. Patrón `^[A-Za-z][A-Za-z0-9]*$`. |

```json
{
  "eventId": "020eff79-8b42-41ce-8668-0bdc5740ecf8",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "api_startup_failed",
  "schemaVersion": "1.0.0",
  "requestId": null,
  "properties": {
    "component": "inventory_database",
    "error_class": "OperationalError"
  }
}
```

#### `cache_lookup_recorded`

- **Clasificación:** oportunidad · **Categoría:** salud técnica · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P6
- **Descripción:** Agregado de 60 s de la caché de lecturas de un espacio: aciertos, fallos e invalidaciones.
- **Frase:** Capturamos `cache_lookup_recorded` porque necesitamos saber si los TTL de la caché (60 s inventario, 30 s incidencias) dan una tasa de acierto que compense, lo que nos permite tomar la decisión de ajustar los TTL o retirar la caché de un espacio (Parte G de SPECS).
- **Se dispara:** Cierre de cada ventana de 60 s con alguna operación en el espacio.
- **Punto exacto:** `services/api/app/core/cache.py:70` (acierto), `:72` (fallo: se ejecuta `compute`) y `:80` (`invalidate`), contados en memoria por P6.
- **Identidad:** `userId` y `sessionId` siempre `null` (evento del sistema, sin actor). `requestId` siempre `null` (no hay petición).
- **Por qué batch:** Ajuste de configuración que se decide con días de datos.
- **PII y sanitización:** Ninguna: ni claves ni valores.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `namespace` | `enum` | sí | Espacio de la caché. Valores: `inventory`, `incidents`. |
| `window_seconds` | `enum` | sí | Duración de la ventana. Valores: `60`. |
| `hits` | `integer` | sí | Aciertos. |
| `misses` | `integer` | sí | Fallos. |
| `invalidations` | `integer` | sí | Invalidaciones. |

```json
{
  "eventId": "9ff66701-4f95-4c4a-809a-9f4eb7148577",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "cache_lookup_recorded",
  "schemaVersion": "1.0.0",
  "requestId": null,
  "properties": {
    "namespace": "inventory",
    "window_seconds": 60,
    "hits": 42,
    "misses": 3,
    "invalidations": 2
  }
}
```

### 6.8 Oportunidades — rendimiento

#### `api_latency_recorded`

- **Clasificación:** oportunidad · **Categoría:** rendimiento · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P6
- **Descripción:** Agregado de 60 s de la duración de las peticiones de una ruta, método y clase de estado.
- **Frase:** Capturamos `api_latency_recorded` porque necesitamos saber qué rutas son lentas y cuándo (p. ej. el inventario en Supabase, ~400 ms sin caché), lo que nos permite tomar la decisión de priorizar optimizaciones (paginación, pool de Supabase: D10 del ticket de caching).
- **Se dispara:** Cierre de cada ventana de 60 s, una por (método, plantilla, clase de estado) con peticiones.
- **Punto exacto:** `services/api/app/core/timing.py:38-45`: la duración ya medida se añade al agregador de P6 en vez de (o además de) la línea de log. Excluye `GET /health`, como hoy.
- **Identidad:** `userId` y `sessionId` siempre `null` (evento del sistema, sin actor). `requestId` siempre `null` (no hay petición).
- **Por qué batch:** La optimización se decide con tendencias; los errores urgentes van por `server_error_returned` y `storage_unavailable_detected`.
- **PII y sanitización:** Ninguna: plantillas, no paths con ids.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `http_method` | `enum` | sí | Método. Valores: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. |
| `route_template` | `enum` | sí | Plantilla (`unmatched` en 404/405 sin ruta). Valores: `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/users`, `/users/{user_id}`, `/profiles/me`, `/suppliers`, `/suppliers/{supplier_id}`, `/suppliers/{supplier_id}/rate`, `/suppliers/{supplier_id}/status`, `/api/incidents/analyze`, `/api/incidents/results/export`, `/api/incidents`, `/api/incidents/summary`, `/api/incidents/{incident_id}`, `/api/incidents/{incident_id}/status`, `/inventory/products`, `/inventory/products/{id}`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders`, `/telemetry/events`, `unmatched`. |
| `status_class` | `enum` | sí | Clase de estado. Valores: `2xx`, `3xx`, `4xx`, `5xx`. |
| `window_seconds` | `enum` | sí | Duración de la ventana. Valores: `60`. |
| `request_count` | `integer` | sí | Peticiones. |
| `p50_ms` | `number` | sí | Mediana, en ms con 1 decimal. |
| `p95_ms` | `number` | sí | Percentil 95 (por rango más cercano). |
| `max_ms` | `number` | sí | Máximo. |

```json
{
  "eventId": "c71ce15f-f291-4eb9-86f3-d8378c59d315",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": null,
  "userId": null,
  "event_type": "api_latency_recorded",
  "schemaVersion": "1.0.0",
  "requestId": null,
  "properties": {
    "http_method": "GET",
    "route_template": "/inventory/products",
    "status_class": "2xx",
    "window_seconds": 60,
    "request_count": 38,
    "p50_ms": 3.1,
    "p95_ms": 402.7,
    "max_ms": 455.0
  }
}
```

#### `page_load_recorded`

- **Clasificación:** oportunidad · **Categoría:** rendimiento · **Emisor:** frontend · **Entrega:** batch · **Prerrequisitos:** P4, P8
- **Descripción:** Una página de datos del backoffice ha llegado a su primer estado final (datos, vacío o error).
- **Frase:** Capturamos `page_load_recorded` porque necesitamos saber cuánto esperan los operadores a ver los datos de cada sección, lo que nos permite tomar la decisión de invertir en el rendimiento del frontend o de la API allí donde más esperan los operadores.
- **Se dispara:** Primer estado final del hook principal de la página tras montarla.
- **Punto exacto:** `uis/backoffice/hooks/use-inventory-assets.ts:99` y `uis/backoffice/hooks/use-inventory-orders.ts:99` (`load`), `hooks/use-supplier-directory.ts` y `hooks/use-incident-board.ts` (su primera carga).
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Tendencia de rendimiento; las caídas las cubre `client_request_failed`.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `route_template` | `enum` | sí | Página. Valores: `/suppliers`, `/incident-manager`, `/inventory/products`, `/inventory/orders`. |
| `duration_ms` | `integer` | sí | Del montaje al primer estado final (`performance.now()`). |
| `outcome` | `enum` | sí | Estado final. Valores: `data`, `empty`, `error`. |

```json
{
  "eventId": "1f825605-d5cc-44b2-874d-f65f41631e15",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "page_load_recorded",
  "schemaVersion": "1.0.0",
  "requestId": "5ba8450e-0655-432c-8919-926b40507cce",
  "properties": {
    "route_template": "/inventory/products",
    "duration_ms": 512,
    "outcome": "data"
  }
}
```

### 6.9 Oportunidades — proveedores

#### `supplier_created`

- **Clasificación:** oportunidad · **Categoría:** proveedores · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha dado de alta un proveedor en el directorio.
- **Frase:** Capturamos `supplier_created` porque necesitamos saber qué tipos de servicio externo contrata Nexova y en qué país, lo que nos permite tomar la decisión de revisar la concentración de proveedores por categoría (Patricia).
- **Se dispara:** `POST /suppliers` responde 201.
- **Punto exacto:** `services/api/app/routes/suppliers.py:33-35`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Revisión periódica del directorio.
- **PII y sanitización:** Ni `name`, ni `contact_email`, ni `notes` (texto libre).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `supplier_id` | `integer` | sí | Id del proveedor (TinyDB). |
| `country` | `enum` | sí | País, tal cual. Valores: `Spain`, `USA`. |
| `categories` | `array<enum>` | sí | Categorías, tal cual. Valores: `job_boards`, `ats_software`, `assessment_tools`, `training_platforms`, `payroll_and_hr_software`, `video_interview`, `background_check`, `office_and_facilities`, `it_and_software_licenses`. |
| `currency` | `enum` | sí | Moneda de la tarifa. Valores: `EUR`, `USD`. |
| `status` | `enum` | sí | Estado inicial. Valores: `active`, `suspended`. |

```json
{
  "eventId": "8490caac-b0b5-40d3-8baa-e5ee181e35f4",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "supplier_created",
  "schemaVersion": "1.0.0",
  "requestId": "0b555bdc-6e13-4f18-8fd0-7dc1c47b2d8a",
  "properties": {
    "supplier_id": 16,
    "country": "Spain",
    "categories": [
      "training_platforms"
    ],
    "currency": "EUR",
    "status": "active"
  }
}
```

#### `supplier_rate_updated`

- **Clasificación:** oportunidad · **Categoría:** proveedores · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Ha cambiado la tarifa mensual de un proveedor.
- **Frase:** Capturamos `supplier_rate_updated` porque necesitamos saber cuánto y con qué frecuencia suben las tarifas de los servicios contratados, lo que nos permite tomar la decisión de renegociar o comparar alternativas antes de la renovación (Patricia).
- **Se dispara:** `PATCH /suppliers/{supplier_id}/rate` responde 200.
- **Punto exacto:** `services/api/app/routes/suppliers.py:53-57`; la tarifa anterior se lee con `repository.get` antes de `update_rate`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Las renovaciones se preparan con semanas de antelación (aviso de 60 días).
- **PII y sanitización:** Ni el nombre ni las tarifas absolutas.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `supplier_id` | `integer` | sí | Id del proveedor. |
| `currency` | `enum` | sí | Moneda. Valores: `EUR`, `USD`. |
| `change_pct` | `number` | sí | Variación porcentual con signo, 2 decimales. |
| `direction` | `enum` | sí | Sentido. Valores: `increase`, `decrease`, `unchanged`. |

```json
{
  "eventId": "d7e52201-ae21-4f9d-8614-eac1131b7373",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "supplier_rate_updated",
  "schemaVersion": "1.0.0",
  "requestId": "a6ec9a03-8a7b-4e43-8fd5-52f7ea75bfd6",
  "properties": {
    "supplier_id": 4,
    "currency": "USD",
    "change_pct": 8.0,
    "direction": "increase"
  }
}
```

#### `supplier_status_changed`

- **Clasificación:** oportunidad · **Categoría:** proveedores · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Un proveedor se ha activado o suspendido.
- **Frase:** Capturamos `supplier_status_changed` porque necesitamos saber cuántos proveedores se suspenden y si vuelven a activarse, lo que nos permite tomar la decisión de depurar el directorio o revisar la relación con los proveedores problemáticos.
- **Se dispara:** `PATCH /suppliers/{supplier_id}/status` responde 200.
- **Punto exacto:** `services/api/app/routes/suppliers.py:59-62`; el estado anterior se lee antes con `repository.get`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Revisión periódica.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `supplier_id` | `integer` | sí | Id del proveedor. |
| `from_status` | `enum` | sí | Estado anterior. Valores: `active`, `suspended`. |
| `to_status` | `enum` | sí | Estado nuevo. Valores: `active`, `suspended`. |

```json
{
  "eventId": "1ce8c24f-8439-4618-88fe-c900bdb67fc1",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "supplier_status_changed",
  "schemaVersion": "1.0.0",
  "requestId": "dee19719-364f-4837-8ac4-6e6a77a3e2a4",
  "properties": {
    "supplier_id": 4,
    "from_status": "active",
    "to_status": "suspended"
  }
}
```

#### `supplier_deleted`

- **Clasificación:** oportunidad · **Categoría:** proveedores · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha borrado un proveedor por la API (la interfaz no lo permite: solo suspende).
- **Frase:** Capturamos `supplier_deleted` porque necesitamos saber si alguien se salta la «suspensión controlada» borrando proveedores directamente por la API, lo que nos permite tomar la decisión de restringir `DELETE /suppliers/{id}` a admins o retirarlo.
- **Se dispara:** `DELETE /suppliers/{supplier_id}` responde 204.
- **Punto exacto:** `services/api/app/routes/suppliers.py:72-76` (tras `repository.delete`; el estado se lee antes con `repository.get`).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Revisión de permisos; el borrado ya ocurrió.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `supplier_id` | `integer` | sí | Id borrado. |
| `status_at_deletion` | `enum` | sí | Estado que tenía. Valores: `active`, `suspended`. |

```json
{
  "eventId": "dc92ab7d-45c0-4160-890d-90f6bb0db53b",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "supplier_deleted",
  "schemaVersion": "1.0.0",
  "requestId": "defb7638-5538-4f0b-88f6-35c3a6880358",
  "properties": {
    "supplier_id": 9,
    "status_at_deletion": "active"
  }
}
```

#### `supplier_list_filtered`

- **Clasificación:** oportunidad · **Categoría:** proveedores · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha consultado el directorio con al menos un filtro.
- **Frase:** Capturamos `supplier_list_filtered` porque necesitamos saber qué filtros usa Patricia y si las búsquedas devuelven listas vacías, lo que nos permite tomar la decisión de añadir filtros o vistas predefinidas, o completar el directorio donde las búsquedas no encuentran nada.
- **Se dispara:** `GET /suppliers` con `country` o `category`.
- **Punto exacto:** `services/api/app/routes/suppliers.py:38-45`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Mejora de la interfaz.
- **PII y sanitización:** Solo qué filtros, nunca nombres.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `filters` | `array<enum>` | sí | Filtros usados. Valores: `country`, `category`. |
| `result_count` | `integer` | sí | Proveedores devueltos. |

```json
{
  "eventId": "5452314c-7039-4155-8969-62a2b7abb6a9",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "supplier_list_filtered",
  "schemaVersion": "1.0.0",
  "requestId": "24507a7e-e11f-4969-87db-ccd3932d8f37",
  "properties": {
    "filters": [
      "category"
    ],
    "result_count": 0
  }
}
```

### 6.10 Oportunidades — gestor de incidencias

#### `incident_created`

- **Clasificación:** oportunidad · **Categoría:** gestor de incidencias · **Emisor:** API · **Entrega:** stream · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha registrado una incidencia en el gestor centralizado.
- **Frase:** Capturamos `incident_created` porque necesitamos saber qué tipo de incidencias se registran, de qué origen y en qué sede, lo que nos permite tomar la decisión de asignar recursos de soporte a la sede o categoría que se dispara (Roberto, Sergio).
- **Se dispara:** `POST /api/incidents` responde 201.
- **Punto exacto:** `services/api/app/modules/incident_manager/router.py:207-226` (tras crear y antes de devolver).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué stream:** El briefing de Nexova señala que el soporte opera «sin visibilidad en tiempo real» (`README.md` raíz): una incidencia nueva, sobre todo `sla_breach` o `technical_failure`, se atiende el mismo día.
- **PII y sanitización:** Ni `title` ni `description` (texto libre, pueden nombrar clientes o candidatos).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `incident_id` | `string` | sí | Id de la incidencia. Patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. |
| `category` | `enum` | sí | Categoría. Valores: `technical_failure`, `process_error`, `client_complaint`, `candidate_issue`, `staff_issue`, `sla_breach`, `data_quality`, `other`. |
| `origin` | `enum` | sí | Origen. Valores: `customer`, `branch`, `internal`. |
| `branch` | `enum` | sí | Sede (vocabulario propio; no se traduce a `office`, D6). Valores: `central`, `valencia_operations`, `miami_office`, `remote`. |

```json
{
  "eventId": "9105eaf5-e85b-40fc-8c15-aee5dcd81c4f",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_created",
  "schemaVersion": "1.0.0",
  "requestId": "d90b8ae9-be6a-44d4-830f-b789d4248d09",
  "properties": {
    "incident_id": "0c45f843-3f8c-4900-98a3-a3802dee688c",
    "category": "sla_breach",
    "origin": "branch",
    "branch": "miami_office"
  }
}
```

#### `incident_status_changed`

- **Clasificación:** oportunidad · **Categoría:** gestor de incidencias · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Una incidencia ha cambiado de estado.
- **Frase:** Capturamos `incident_status_changed` porque necesitamos saber cuánto se tarda en resolver o descartar las incidencias, por categoría y sede (hoy fuera del alcance de la API, SPECS §33), lo que nos permite tomar la decisión de fijar objetivos de resolución y reforzar las sedes o categorías más lentas.
- **Se dispara:** `PATCH /api/incidents/{incident_id}/status` responde 200.
- **Punto exacto:** `services/api/app/modules/incident_manager/router.py:284-302`; el estado anterior lo conoce `IncidentRepository.change_status` (comprueba con él la transición) y se devuelve junto a la incidencia.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Los tiempos de resolución se miran por semanas.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `incident_id` | `string` | sí | Id. Patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. |
| `from_status` | `enum` | sí | Estado anterior. Valores: `open`, `in_progress`, `resolved`, `discarded`. |
| `to_status` | `enum` | sí | Estado nuevo. Valores: `open`, `in_progress`, `resolved`, `discarded`. |
| `category` | `enum` | sí | Categoría. Valores: `technical_failure`, `process_error`, `client_complaint`, `candidate_issue`, `staff_issue`, `sla_breach`, `data_quality`, `other`. |
| `branch` | `enum` | sí | Sede. Valores: `central`, `valencia_operations`, `miami_office`, `remote`. |
| `age_seconds` | `integer` | sí | Tiempo desde `created_at`. |

```json
{
  "eventId": "216cc75b-1847-4391-8971-90f51c115d0b",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_status_changed",
  "schemaVersion": "1.0.0",
  "requestId": "1a57906c-8c98-4009-880c-f57251c15622",
  "properties": {
    "incident_id": "0c45f843-3f8c-4900-98a3-a3802dee688c",
    "from_status": "in_progress",
    "to_status": "resolved",
    "category": "technical_failure",
    "branch": "central",
    "age_seconds": 172800
  }
}
```

#### `incident_status_change_rejected`

- **Clasificación:** oportunidad · **Categoría:** gestor de incidencias · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha pedido una transición de estado no permitida (400 `invalid_status_transition`).
- **Frase:** Capturamos `incident_status_change_rejected` porque necesitamos saber si hay pantallas desactualizadas o integraciones que piden transiciones imposibles (la interfaz solo ofrece las válidas), lo que nos permite tomar la decisión de recargar la vista tras cada cambio o corregir la integración.
- **Se dispara:** `check_transition` rechaza el cambio.
- **Punto exacto:** `services/api/app/modules/incident_manager/router.py:296-297`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Corrección de la interfaz.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `incident_id` | `string` | sí | Id. Patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. |
| `from_status` | `enum` | sí | Estado actual. Valores: `open`, `in_progress`, `resolved`, `discarded`. |
| `requested_status` | `enum` | sí | Estado pedido. Valores: `open`, `in_progress`, `resolved`, `discarded`. |

```json
{
  "eventId": "08508c5a-5c2a-4095-8985-d0da88e31605",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_status_change_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "da3c823a-23f3-4206-8d7b-5ac05e487b67",
  "properties": {
    "incident_id": "0c45f843-3f8c-4900-98a3-a3802dee688c",
    "from_status": "resolved",
    "requested_status": "open"
  }
}
```

#### `incident_validation_failed`

- **Clasificación:** oportunidad · **Categoría:** gestor de incidencias · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** El gestor de incidencias ha rechazado un alta, un filtro o un cambio de estado por validación (400 `validation_error`).
- **Frase:** Capturamos `incident_validation_failed` porque necesitamos saber qué campos de la incidencia se rellenan mal, lo que nos permite tomar la decisión de mejorar el formulario o el texto de ayuda de esos campos.
- **Se dispara:** `IncidentFieldsError` en el alta, el listado o el cambio de estado.
- **Punto exacto:** `services/api/app/modules/incident_manager/router.py` (`IncidentManagerRoute`, `:83-93`, y las validaciones de `nexova_shared` en cada ruta).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Mejora de la interfaz.
- **PII y sanitización:** Nunca `message` ni valores.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `operation` | `enum` | sí | Operación. Valores: `create`, `list`, `status_change`. |
| `fields` | `array<string>` | sí | Campos con error (`field` del 400). |
| `error_types` | `array<enum>` | sí | Valores de `error` del 400, sin repetir. Valores: `missing`, `blank`, `too_long`, `invalid_type`, `invalid_choice`, `unknown_field`, `invalid_body`. |

```json
{
  "eventId": "bc635cc9-4fc0-4490-8f1b-ce84c83f5a7b",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_validation_failed",
  "schemaVersion": "1.0.0",
  "requestId": "d867f480-072a-4152-816a-76ee5b1a9247",
  "properties": {
    "operation": "create",
    "fields": [
      "branch"
    ],
    "error_types": [
      "missing"
    ]
  }
}
```

#### `incident_list_filtered`

- **Clasificación:** oportunidad · **Categoría:** gestor de incidencias · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha consultado el listado de incidencias con al menos un filtro.
- **Frase:** Capturamos `incident_list_filtered` porque necesitamos saber qué vistas del listado usan los responsables (por estado, sede, categoría), lo que nos permite tomar la decisión de añadir vistas predefinidas o un panel por sede.
- **Se dispara:** `GET /api/incidents` con algún filtro válido.
- **Punto exacto:** `services/api/app/modules/incident_manager/router.py:228-251`.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Mejora de la interfaz.
- **PII y sanitización:** Solo qué filtros.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `filters` | `array<enum>` | sí | Filtros usados. Valores: `status`, `origin`, `branch`, `category`. |
| `result_count` | `integer` | sí | Incidencias devueltas. |
| `cache_hit` | `boolean` | sí | Si la respuesta salió de la caché (Parte G). |

```json
{
  "eventId": "b37a4f44-b324-43a9-81df-b9e344ca4129",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_list_filtered",
  "schemaVersion": "1.0.0",
  "requestId": "05344961-4b6e-4cbe-8a61-224cb13c9503",
  "properties": {
    "filters": [
      "status",
      "branch"
    ],
    "result_count": 12,
    "cache_hit": false
  }
}
```

### 6.11 Oportunidades — análisis de incidentes

#### `incident_analysis_completed`

- **Clasificación:** oportunidad · **Categoría:** análisis de incidentes · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Un CSV del helpdesk se ha analizado correctamente (`POST /api/incidents/analyze` → 200).
- **Frase:** Capturamos `incident_analysis_completed` porque necesitamos saber la calidad de los exports del helpdesk (proporción de filas inválidas) y su tamaño, lo que nos permite tomar la decisión de pedir que se corrija el export del helpdesk o ajustar `MAX_UPLOAD_BYTES`.
- **Se dispara:** `POST /api/incidents/analyze` responde 200.
- **Punto exacto:** `services/api/app/modules/incidents/router.py:33-35` (con `stored`).
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** La calidad del export se revisa por semanas.
- **PII y sanitización:** Solo los conteos que ya devuelve la API: nada de filas ni de `customer_email` (SPECS §5).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `analysis_id` | `string` | sí | `analysis_id`. Patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. |
| `total_records` | `integer` | sí | `totals.total_records`. |
| `valid_records` | `integer` | sí | `totals.valid_records`. |
| `invalid_records` | `integer` | sí | `totals.invalid_records`. |
| `file_size_bucket` | `enum` | sí | Tamaño del archivo por tramos. Valores: `under_64_kib`, `64_to_256_kib`, `256_kib_to_1_mib`, `over_1_mib`. |
| `duration_ms` | `integer` | sí | Duración del análisis. |

```json
{
  "eventId": "1fd72cdb-f15e-41ee-8acd-59766c2998f4",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_analysis_completed",
  "schemaVersion": "1.0.0",
  "requestId": "0aff9cb3-5951-4540-842b-a951f1dc1b23",
  "properties": {
    "analysis_id": "5b8d2f4a-6c1e-4b3a-9d7f-1a3c5e7b9d2f",
    "total_records": 100,
    "valid_records": 96,
    "invalid_records": 4,
    "file_size_bucket": "under_64_kib",
    "duration_ms": 38
  }
}
```

#### `incident_analysis_rejected`

- **Clasificación:** oportunidad · **Categoría:** análisis de incidentes · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Un CSV se ha rechazado antes de analizarse.
- **Frase:** Capturamos `incident_analysis_rejected` porque necesitamos saber por qué fallan las subidas (formato, tamaño, tipo), lo que nos permite tomar la decisión de mejorar las instrucciones de exportación o ajustar el límite de tamaño.
- **Se dispara:** `POST /api/incidents/analyze` responde 400, 413, 415 o 422.
- **Punto exacto:** Handlers de `services/api/app/core/errors.py:207-217` y `:230-233`, filtrando la ruta; el 413 lo lanza `services/api/app/core/limits.py:41-42` y pasa por el mismo handler.
- **Identidad:** `userId` y `sessionId` del token si lo hay y es válido; si no, `null`. `requestId` siempre presente.
- **Por qué batch:** Mejora del proceso.
- **PII y sanitización:** Ni el nombre del archivo ni el `detail` (puede citar filas).

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `status_code` | `enum` | sí | Respuesta. Valores: `400`, `413`, `415`, `422`. |
| `error_code` | `enum` | sí | `code`. Valores: `invalid_csv`, `bad_request`, `file_too_large`, `unsupported_file_type`, `validation_error`. |
| `file_size_bucket` | `enum \| null` | sí | Tamaño por tramos según `Content-Length`; `null` si no se sabe. Valores: `under_64_kib`, `64_to_256_kib`, `256_kib_to_1_mib`, `over_1_mib`; o `null`. |

```json
{
  "eventId": "ed0f261d-103c-460a-8ed1-d48c82a4c571",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_analysis_rejected",
  "schemaVersion": "1.0.0",
  "requestId": "9ffc3251-9fa6-4f89-8f8e-7a3e51d199b5",
  "properties": {
    "status_code": 400,
    "error_code": "invalid_csv",
    "file_size_bucket": "under_64_kib"
  }
}
```

#### `incident_results_exported`

- **Clasificación:** oportunidad · **Categoría:** análisis de incidentes · **Emisor:** API · **Entrega:** batch · **Prerrequisitos:** P4, P5, P6
- **Descripción:** Se ha pedido la exportación del último análisis.
- **Frase:** Capturamos `incident_results_exported` porque necesitamos saber si la exportación se usa y si se pide sin análisis previo, lo que nos permite tomar la decisión de mantener, mejorar o retirar la exportación.
- **Se dispara:** `GET /api/incidents/results/export` responde 200 o 404 `no_analysis`.
- **Punto exacto:** `services/api/app/modules/incidents/router.py:60` y el handler del 404.
- **Identidad:** `userId` y `sessionId` del token de la petición (nunca `null`). `requestId` siempre presente.
- **Por qué batch:** Decisión de producto.
- **PII y sanitización:** Ninguna.

| Propiedad | Tipo | Obligatoria | Descripción |
|---|---|---|---|
| `outcome` | `enum` | sí | Resultado. Valores: `exported`, `no_analysis`. |
| `analysis_id` | `string \| null` | sí | `X-Analysis-Id` exportado; `null` si no había análisis. Patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. |
| `analysis_age_seconds` | `integer \| null` | sí | Tiempo desde `analyzed_at`; `null` si no había análisis. |

```json
{
  "eventId": "6b8c1bdb-f673-4465-8348-8b3eead6b53c",
  "timestamp": "2026-11-02T09:15:42.318Z",
  "sessionId": "a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e",
  "userId": "3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c",
  "event_type": "incident_results_exported",
  "schemaVersion": "1.0.0",
  "requestId": "5d8f492e-8e3f-4505-8232-92e6afce01f7",
  "properties": {
    "outcome": "exported",
    "analysis_id": "5b8d2f4a-6c1e-4b3a-9d7f-1a3c5e7b9d2f",
    "analysis_age_seconds": 75
  }
}
```
---

## 7. Estrategia de entrega

### 7.1 Stream o batch

**Criterio (D12):** el canal lo decide la urgencia de la decisión que alimenta el evento, no una preferencia técnica.

- **Stream:** el responsable actúa **el mismo día**, o detectar tarde **aumenta el daño** (seguridad, caída, una entrega que no se hace).
- **Batch:** todo lo que alimenta tendencias, planificación, el dashboard de L&D de Elena o el informe semanal de Laura.

Cada ficha de §6 justifica su caso. Resumen:

| Entrega | Eventos | Latencia objetivo | Para qué |
|---|---|---|---|
| **stream** (13) | `stock_threshold_triggered`, `kit_cost_variance_detected`, `outbound_order_rejected`, `login_failed`, `auth_token_rejected`, `password_reset_email_failed`, `user_role_changed`, `frontend_error_captured`, `client_request_failed`, `server_error_returned`, `storage_unavailable_detected`, `api_startup_failed`, `incident_created` | segundos a un minuto desde la emisión | alertas a una persona concreta: Elena (reposición, coste), Laura (coste), el equipo técnico (seguridad, caídas), Roberto (incidencias) |
| **batch diario** (39) | el resto, entre ellos `inbound_order_created`, `outbound_order_created` y `direct_stock_edit_rejected` | un lote cada noche (UTC), con los eventos del día anterior | dashboards de tendencias, el dashboard de L&D (por oficina y programa) y el informe semanal de Laura, que se construye a partir de 7 lotes diarios |

`direct_stock_edit_rejected` es batch, pero una ráfaga se eleva a alerta stream (§7.2) sin cambiar el evento: la decisión de Patricia no es urgente, y un posible abuso de la API sí lo es.

### 7.2 Throttle, debounce y agregados

Todo en memoria del proceso de la API (P6) o de la pestaña del navegador (P8).

- **Throttle:** un evento por **clave** y **ventana**. Los que se descartan se suman a `suppressed_count` del siguiente evento de esa clave que sí se emite.
- **Fin de ventana:** si al cerrarse una ventana quedan descartados sin emitir, se emite un último evento con el `suppressed_count` acumulado y los demás campos del último descartado.

| Evento | Mecanismo | Clave | Valor |
|---|---|---|---|
| `api_latency_recorded` | agregado | (método, plantilla, clase de estado) | ventana de 60 s; un evento por clave con peticiones. Percentiles por rango más cercano sobre las duraciones de la ventana (máx. 10 000 por clave; por encima, se descarta la duración que llega) |
| `cache_lookup_recorded` | agregado | espacio | ventana de 60 s |
| `login_failed` | throttle | (`reason`) | 1 cada 10 s. **Alerta stream** si suman ≥ 20 (emitidos + suprimidos) en 5 min |
| `auth_token_rejected` | throttle | (`reason`, plantilla) | 1 cada 60 s. **Alerta** con cualquier `invalid_signature` |
| `direct_stock_edit_rejected` | throttle | (`userId` o anónimo, plantilla, método) | 1 cada 60 s. **Alerta stream** si suman ≥ 10 en 10 min desde la misma clave |
| `session_expired` | deduplicado | `sessionId` | 1 por `sid` en la vida del proceso (las peticiones en paralelo que llegan con el token caducado dan un solo evento). Conjunto acotado a 10 000 `sid`; sale el más antiguo |
| `storage_unavailable_detected` | throttle | `store` | 1 cada 60 s |
| `server_error_returned` | throttle | (plantilla, `error_class`) | 1 cada 60 s |
| `client_request_failed` | throttle (navegador) | (`kind`, plantilla) | 1 cada 60 s por pestaña |
| `frontend_error_captured` | throttle (navegador) | (`boundary`, `route_template`) | 1 cada 60 s por pestaña |
| `page_viewed` | debounce (navegador) | — | se emite si la ruta se mantiene 1 s (descarta redirecciones) |
| `form_started` | una vez | (formulario, montaje) | solo el primer cambio, hasta el siguiente envío correcto |
| colector (P8) | límite | token o anónimo | 120 eventos/min; el exceso se descarta (cuenta como `rejected`) |

**Volumen esperado** (orden de magnitud; no se ha medido el tráfico real, §8.4): con unas decenas de operadores, la mayor parte la producen `api_latency_recorded` (≤ 1 evento por clave activa y minuto) y `page_viewed`. El resto son eventos de negocio, de decenas a cientos al día.

### 7.3 Del emisor al almacén

- **Este plan fija** la forma y el canal lógico de cada evento.
- **Hecho en el ticket de almacenamiento:** los 14 eventos del frontend y `direct_stock_edit_rejected` llegan a `telemetry_events` (PostgreSQL; esquema en SPECS Parte H). Se valida cada evento antes de guardarlo, se descartan contando los inválidos y se deduplica por `eventId` (`ON CONFLICT DO NOTHING`). `direct_stock_edit_rejected` se guarda desde el proceso de la API, sin leer el log; su línea en `nexova.telemetry` se mantiene como rastro.
- **Pendiente para un ticket posterior:**
  - enviar los eventos stream a una ruta de alertas: hoy no existe ninguna, así que `stock_threshold_triggered` y `kit_cost_variance_detected` se guardan, pero nadie recibe un aviso;
  - consolidar los batch en el lote nocturno y crear los agregados.
- **Orden de llegada:** la tabla no lo conserva; se ordena por `timestamp`.

---

## 8. Riesgos y exclusiones

### 8.1 Eventos considerados y descartados

| Evento considerado | Por qué no |
|---|---|
| Matrículas por programa y tasa de finalización (M11, dashboard de Elena) | El repositorio no tiene ningún dato de matrículas ni de finalización: no hay fuente que instrumentar. La telemetría del inventario da el consumo de material por programa (`outbound_order_created`), que es lo más cercano. Medir las matrículas necesita su propio sistema y su propio contexto |
| Tipo de destinatario de la salida (cliente, candidato, consultor o agente; M10) | No está modelado; solo existe `assigned_to`, en texto libre y con datos personales. Añadirlo sería un campo nuevo (`recipient_type`) que ninguna fuente pide como prerrequisito. Queda como mejora futura, siempre sin nombres |
| `stock_warning_shown` (aviso de «la cantidad supera el stock» en la Salida) | La frase no se completa con una decisión propia: lo que importa es si la salida falla, y eso ya lo mide `outbound_order_rejected` (`insufficient_stock`), en la API, sin depender del render |
| `stock_depleted` (stock a 0) | Lo cubre `stock_threshold_triggered` con `stock_after = 0`; un evento aparte duplicaría las alertas |
| Disparar el umbral desde el indicador del frontend | `StockLevelBadge` se renderiza en cada visita y no es la autoridad del stock: dispararía en cada render (D4) |
| `order_history_viewed`, `incident_summary_viewed`, `supplier_directory_viewed` | Los cubre `page_viewed` con su `route_template` |
| `product_viewed` (`GET /inventory/products/{id}` al elegir un activo en la Salida) | Muchísimo volumen y ninguna decisión propia; su coste ya está en `api_latency_recorded` |
| `user_login_succeeded` en el frontend | Duplicaría `user_logged_in`, que la API emite con más certeza |
| 401 sin cabecera `Authorization` | Ruido (sondeos, el guard antes de tener token); su volumen ya aparece en `api_latency_recorded` (`4xx`). Solo se emiten los 401 con un token presente (`session_expired`, `auth_token_rejected`) |
| `health_checked` (`GET /health`) | El healthcheck de Docker lo llama cada 5 s; ya se excluye del timing (SPECS §44) |
| `profile_updated` | Todos los campos del perfil (`name`, `phone`, `address`) son datos personales y no hay ninguna decisión que dependa de cuántas veces se editan |
| Clics, scroll, movimiento del ratón, grabación de sesiones | Coste y privacidad, sin una decisión que los justifique; el abandono se mide por formulario (`form_abandoned`) |
| Web Vitals (LCP, CLS, INP) | La auditoría de rendimiento ya los midió y corrigió (`AUDIT.md`); `page_load_recorded` cubre el tiempo hasta los datos. Se puede añadir más adelante si reaparece un problema |
| `supplier_viewed` (`GET /suppliers/{id}`) | La interfaz no lo usa |
| Idioma de la interfaz | El backoffice solo está en español; no se captura ningún idioma y nunca se deduce la oficina del idioma (BRIEFING §6) |
| Eventos del tracker y del website | Fuera de alcance (D10, §1.1) |

### 8.2 Datos que no se capturan

| Dato | Motivo |
|---|---|
| Emails, en claro o con hash (login, registro, recuperación, `contact_email`, `customer_email` del CSV) | Datos personales; un hash de email se revierte por diccionario (D9) |
| IP del cliente | Ninguna decisión del catálogo la necesita; la auditoría de AUTH-03 ya la guarda con su propio residual (SPECS §27) |
| Nombres de candidatos, clientes, consultores o empleados (`assigned_to`) | Regla del BRIEFING |
| Texto libre: título y descripción de incidencias, nombre y notas de proveedores, nombre y SKU de activos, `supplier` | Puede contener nombres de personas o datos de clientes. Se usan ids, vocabulario cerrado o la clave HMAC |
| `detail`, `msg` e `input` de los errores (el `detail` de `insufficient_stock` lleva el nombre del activo) | Solo se usan `error_code`, el nombre del campo y las cifras. Única excepción: el `input` entero de `current_stock` (P7) |
| Query strings y paths reales | `?token=` de `/reset-password` es un secreto; los paths llevan ids. Solo plantillas |
| Token, contraseñas, `hashed_password`, `JWT_SECRET_KEY`, `DATABASE_URL` | Secretos |
| `error.message`, `digest` y `stack` del frontend | Regla de `uis/backoffice/CLAUDE.md`: el error no se lee |
| Contenido del CSV | SPECS §5: solo los conteos que ya devuelve la API |
| Importes absolutos de las tarifas de proveedores | Basta el porcentaje de cambio para la decisión |

### 8.3 Retención (D9)

- **Eventos en bruto** (con `userId`, `sessionId`, `target_user_id` o `requestId`): **90 días**. Después se borran o se agregan.
  - **Fecha límite: 2027-02-02** (90 días desde 2026-11-04, cuando se creó el almacén; se ajusta si la tabla de la demo se crea más tarde).
  - **Condición: agregar antes de borrar.** Los agregados aún no existen: borrar sin ellos pierde el histórico del dashboard de L&D y del informe semanal.
  - **Es una operación de administración, fuera de la API y sin automatizar todavía.** `telemetry_events` es inmutable para el rol de la API (`REVOKE UPDATE, DELETE, TRUNCATE`): el trabajo de limpieza se concede `DELETE`, borra por `timestamp` y lo revoca en la misma transacción. Nunca se anonimiza con `UPDATE`.
- **Agregados sin identificadores personales** (conteos por día, oficina, programa, categoría o ruta): **sin límite**. Son los que alimentan el dashboard de L&D y el informe semanal.
- **`userId` es un dato personal seudonimizado:** se conserva en claro para poder cruzarlo con el `user_uuid` de las órdenes, con acceso restringido al equipo técnico y a los responsables que lo necesiten.
- **`supplier_key`** no permite recuperar el nombre sin la clave. El nombre se consulta en la base desde `inbound_order_id`, con su control de acceso.

### 8.4 Riesgos

| Riesgo | Efecto | Mitigación o decisión |
|---|---|---|
| Normalización del proveedor por texto | «Office Depot Miami» y «Office Depot Miami S.L.» son dos proveedores: la referencia de coste se parte y una variación real puede no detectarse | Riesgo aceptado (D3 A). Mejora futura: referenciar el directorio de proveedores (`supplier_id`) |
| La variación de coste necesita historial | Con la ventana de 3, un par necesita 4 entradas con coste para evaluarse; las anteriores a P3 no tienen coste | Documentado. Los datos semilla del ticket de captura deben incluir al menos un par con 4 entradas para el caso del BRIEFING §5 |
| Intentos anónimos sin oficina | Los 405 sin token o sobre un id inexistente tienen `office = null`: no cuentan en la decisión «por oficina» de Patricia | Se emiten igualmente (`authenticated`, `attempt_kind`); el informe separa «con oficina» y «sin oficina» |
| Activos sin clasificar (D1-b) | Hasta que se clasifiquen, `product_category` y `programme_id` son `null` y las métricas por programa salen vacías | La clasificación es un prerrequisito del ticket de captura. Hasta entonces, el agregado usa `asset_category` |
| Un solo proceso | El agregador, el throttle y el deduplicado de `session_expired` viven en memoria: con varios workers o réplicas cada uno tendría los suyos (como la caché, SPECS §43) | Uvicorn arranca con `--workers 1`. Subirlos obliga a revisar P6 |
| Reinicio del proceso | Se pierden las ventanas abiertas (hasta 60 s de agregados) y los contadores de throttle | Aceptado: los agregados son aproximados por diseño |
| Pérdida de eventos del frontend | Sin almacenamiento local: lo pendiente se pierde si fallan los 3 reintentos o si el beacon no sale al cerrar. Desde el ticket de captura incluye 4 obligatorios (§1.5) | Aceptado por el usuario (D1 «A ligera»): reintentos con backoff y beacon; el almacén deduplica por `eventId`. Si la pérdida medida importa, la alternativa es que la API emita también esos 4 |
| Eventos de negocio falsificables | `POST /telemetry/events` es público (un beacon no lleva token) y, desde D1 «A ligera», recibe 4 obligatorios: cualquiera puede inyectar un `outbound_order_created` falso, que queda en una tabla inmutable y alimenta los informes. Sin token, `userId` y `sessionId` son los declarados | Riesgo aceptado por el usuario (C15 de `storage-analysis.md`). Freno: allowlist y throttle. Exigir token perdería los eventos que salen por beacon. Si importa, la alternativa es que la API emita esos 4 |
| Cupo anónimo compartido | Todos los beacons cuentan en el mismo cupo de 120 eventos/min: en un pico, el exceso se pierde sin aviso, también eventos de negocio | Riesgo aceptado por el usuario. Revisar con la primera semana de datos (log `api.telemetry`) |
| Desfase del reloj del navegador | `timestamp` erróneo | El colector lo sustituye si se desvía más de ±5 min (§2.4) |
| El emisor rompe una petición | Una excepción en la telemetría devolvería un 500 | `emit` nunca lanza (P6) y los eventos de negocio se emiten tras el commit |
| Rotación de `TELEMETRY_SUPPLIER_KEY` | Cambia todas las `supplier_key`: se corta la continuidad de las referencias | Rotarla solo con un corte documentado; la referencia de coste se calcula siempre en la API con el texto normalizado, no con la clave |
| Indicador «Bajo» del frontend | Con `<`, «Bajo» debería ser `0 < stock < min_stock`; hoy es 1–5 | Se alinea en el ticket de captura (D4) |
| Seeds y cambios directos | No emiten eventos: un seed no cuenta como entradas ni salidas | Por diseño (§1.1): no son actividad de negocio. Un seed nunca se ejecuta sobre la base de la demo sin confirmación |
| `Allow` incompleto en el 405 | `PUT /inventory/products` responde `Allow: GET`, aunque la colección admite `POST` (hallazgo de F0) | Fuera de este ticket; no afecta a la detección |
| Volumen no medido | Los umbrales de §7.2 son estimaciones | Revisarlos con la primera semana de datos del ticket de captura |

---

## 9. Validación

### 9.1 Script comiteado (librería estándar)

```bash
python scripts/validate_event_schemas.py
```

**Comprueba:**

- que `event-schemas.json` se lee y solo usa las palabras clave de draft-07 que el script implementa (cualquier otra lo hace fallar);
- el envelope de §5: las 8 claves, `additionalProperties: false` y `required`;
- en cada definición de evento:
  - `allOf` con el envelope, `event_type` en `const` igual a su nombre y con el patrón de la taxonomía, y `schemaVersion` en `const`;
  - `additionalProperties: false` en `properties`;
  - `required` ⊆ `properties`;
- los campos mínimos y los enums literales del BRIEFING en los 9 eventos de inventario, la coherencia oficina–moneda (`oneOf`) y que los 5 obligatorios están, con su nombre exacto;
- que el `oneOf` raíz referencia todos los eventos;
- contra este plan:
  - que la lista de eventos del catálogo (§4), la de fichas (§6) y la del JSON son la misma, en el mismo orden;
  - que los metadatos de cada fila y de cada ficha coinciden con el `$comment` del esquema;
  - que las cifras de emisor (API/frontend) y de entrega (stream/batch) de la cabecera son las del catálogo (desde el ticket de captura, que cambió el emisor de 4 eventos);
  - que la tabla de propiedades de cada ficha coincide con su esquema (nombres, tipo y obligatoriedad);
  - que cada ficha tiene su frase y que **cada bloque JSON del plan valida contra el esquema**.

`--dump-examples <dir>` escribe cada ejemplo en un archivo, para validarlos con `ajv` (§9.2).

### 9.2 Ejecución puntual de `ajv-cli` (draft-07)

**Ejecución puntual** (D11 B), el 2026-11-02 y repetida el mismo día tras añadir la coherencia oficina–moneda, con Node 24.18.0 y `ajv-cli` **5.0.0** fijado. `npx` lo descargó en su caché y **no se tocó ningún `package.json`**. Desde la raíz:

```bash
npx --yes ajv-cli@5.0.0 compile --spec=draft7 -s docs/telemetry/event-schemas.json
```

```text
schema docs/telemetry/event-schemas.json is valid
```

```bash
python scripts/validate_event_schemas.py --dump-examples <scratch>/examples
```

```bash
npx --yes ajv-cli@5.0.0 validate --spec=draft7 -s docs/telemetry/event-schemas.json -d "<scratch>/examples/*.json"
```

- **Salida:** 53 líneas `<scratch>/examples/NN-<event_type>.json valid` (los 52 ejemplos de las fichas y el de §5.2) y código de salida 0. Sin avisos de modo estricto.
- **Controles negativos**, los dos con `invalid` y código 1:
  - el ejemplo de `inbound_order_created` con una clave `supplier` añadida en `properties`: la allowlist rechaza el nombre del proveedor;
  - el ejemplo de `outbound_order_created` con `valencia` y `USD`: lo rechaza el `oneOf` de oficina–moneda.

La comprobación permanente es la del script de §9.1. Esta ejecución no se repite en cada cambio, salvo que se añadan palabras clave de draft-07 que el script no implementa.

**Mutaciones del script de §9.1** (copias en memoria, sin tocar los archivos): las 13 se detectan.

- una palabra clave no soportada (`format`);
- `office` con mayúscula;
- un campo mínimo quitado;
- una clave extra en un ejemplo (`email`);
- un tipo distinto en una tabla;
- un evento renombrado en el catálogo;
- la entrega cambiada en una ficha;
- una frase quitada;
- un `sessionId` en un evento anónimo;
- un `timestamp` sin `Z`;
- `valencia` con `USD` en un ejemplo;
- el `oneOf` de oficina–moneda quitado;
- una frase con otro conector en lugar de «lo que nos permite tomar la decisión de».
