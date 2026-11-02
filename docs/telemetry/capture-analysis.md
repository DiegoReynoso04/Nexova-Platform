# Captura de telemetría en el frontend + endpoint stub — análisis (F0)

Documento de trabajo del ticket «Telemetría · Captura en el frontend». **F0: análisis y decisiones; no hay código.** Las decisiones D1–D9 de §3 las toma el usuario; hasta entonces no se implementa nada.

- **Rama:** `feature/telemetry-capture`, desde `main` en `8a23d17` (PR #28 mergeada: plan y esquemas aprobados).
- **Contrato:** [`telemetry-plan.md`](./telemetry-plan.md) y [`event-schemas.json`](./event-schemas.json), versión `1.0.0`. El BRIEFING es [`docs/proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md`](../proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md).
- **Enunciado del ticket:** no se versiona; aquí solo se cita lo que choca con el plan.
- **Código de referencia:** las líneas que cita el plan (`390d3aa`) siguen valiendo: entre `390d3aa` y `8a23d17` solo cambió un comentario de `services/api/app/core/timing.py`.

---

## 1. Lo que hay hoy (verificado)

| Pieza | Estado | Dónde |
|---|---|---|
| Emisor de eventos (API o frontend) | No existe ninguno | — |
| Columnas del BRIEFING en el inventario | No existen `product_category`, `programme_id`, `min_stock`, `unit_cost` ni `currency` | `services/api/app/modules/inventory/models.py:50-106` |
| Respuestas de las órdenes | `OutboundOrderRead` no trae `stock_after`, ni categoría, ni moneda; `AssetSummary` solo `id`, `name`, `sku` | `services/api/app/modules/inventory/schemas.py:123-158` |
| Esquema de la base | `create_all` al arrancar (no altera tablas existentes) + RLS; ninguna herramienta de migraciones | `services/api/app/modules/inventory/database.py:106` y `:126` |
| Claim `sid` en el JWT | No existe: solo `sub`, `iat`, `exp` | `services/api/app/auth/security.py:74-81` |
| `X-Request-ID` | No existe; CORS solo permite `Authorization` | `services/api/app/main.py:111-120` |
| Cliente HTTP del backoffice | Único `fetch`; un 401 de una petición protegida **borra el token**; sin `keepalive` | `uis/backoffice/lib/api-client.ts:205`, `:253-256` |
| Patrón «otro cliente, otra base URL» | Ya existe para el inventario (`createApiClient` con `getBaseUrl` propio y validación perezosa) | `uis/backoffice/lib/inventory-api-client.ts` |
| Web Vitals | `next/web-vitals` (`useReportWebVitals`) viene con `next@16.3.2`: **sin dependencia nueva** | `uis/backoffice/node_modules/next/web-vitals.js`; guía local `node_modules/next/dist/docs/01-app/03-api-reference/04-functions/use-report-web-vitals.md` |
| Estructura del backoffice | No hay `src/`: el servicio va en `lib/telemetry.ts` (lo fija el plan, P8), no en `src/services/telemetry.ts` | `uis/backoffice/` |

**Reglas estáticas que el ticket toca** (`uis/backoffice/tests/production-source.test.mjs`), además de las del enunciado del ticket:

| Regla | Línea del test | Choca con |
|---|---|---|
| `fetch(` solo en `lib/api-client.ts` | `:588-593` | el transporte de la telemetría (tiene que pasar por `api-client`) |
| `JSON.stringify` solo en `lib/api-client.ts` | `:552-557` | el cuerpo de `sendBeacon` (hay que serializarlo en `api-client`) |
| `unknown` solo en `services/normalizers.ts` | `:576-581` | la firma literal del enunciado, `track(eventType: string, properties: Record<string, unknown>)` |
| `sessionStorage`, `indexedDB` y `console.` prohibidos en todo el código de producción | `:32-44` | guardar el `sessionId` en el navegador |
| `localStorage` solo en `lib/auth-token.ts` | `:538-543` | ídem |
| `Authorization`/`Bearer` solo en `lib/api-client.ts` | `:545-550` | — (la telemetría no construye cabeceras) |
| Los límites de error no leen el error | `:474-496` | `frontend_error_captured` (solo el hecho, nunca `error.*`) |

---

## 2. Conflictos entre el enunciado y el plan aprobado

Cada uno con lo que dice el plan, lo comprobado en el código y la propuesta. Las propuestas que necesitan una decisión remiten a §3.

### C1. Emisor de los 5 obligatorios

- **Plan:** los 5 son de emisor **API** (§4, filas 1–5; D10). El colector **rechaza** cualquier `event_type` de la API enviado por el cliente: «el frontend no puede fabricar órdenes ni intentos de edición» (§2.4).
- **Enunciado:** capturarlos en el backoffice con `track()`.
- **Código:** la API es la única que tiene los datos fiables:
  - el stock antes y después de una salida, bajo `FOR UPDATE` (`service.py:184-191`): el frontend solo tiene una lectura previa, que puede estar desfasada;
  - la clave HMAC del proveedor (P9), que es un secreto del servidor y no puede estar en el navegador;
  - el historial de costes del par (activo, proveedor) para la variación;
  - los 405 y 422 de `direct_stock_edit_rejected`, que nunca pasan por la UI (C3).
- **Propuesta:** D1.

### C2. Datos que faltan para los obligatorios

Qué falta en cada uno de los 5 si se emite hoy, campo a campo contra `event-schemas.json`:

| Evento | Campo que falta hoy | ¿Válido hoy con `1.0.0`? |
|---|---|---|
| `outbound_order_created` | `product_category` y `programme_id` admiten `null` («aún no está clasificado», D1-a); `currency` se **deriva** de `office` sin columna (BRIEFING §6); `stock_after` lo calcula la API | **Sí, desde la API.** Desde el frontend, solo con `stock_after` calculado sobre una lectura previa (no fiable) |
| `stock_threshold_triggered` | `min_stock` (entero obligatorio, P2) | **Sí, desde la API**, si `min_stock` sale de la configuración (`INVENTORY_DEFAULT_MIN_STOCK = 5`, D4) mientras no exista la columna por activo |
| `direct_stock_edit_rejected` | Todos los campos del BRIEFING admiten `null`; falta solo la detección (P7) | **Sí, desde la API** (C3) |
| `inbound_order_created` | `unit_cost` (número obligatorio, P3) y `supplier_key` (HMAC, P9) | **No.** `supplier_key` se puede calcular hoy desde `supplier` (sin columna, solo con la clave en el `.env`); `unit_cost` necesita la columna, el campo en el formulario y un valor que hoy no existe |
| `kit_cost_variance_detected` | `unit_cost`, `reference_unit_cost`, `variance_pct`, `supplier_key` | **No, y no se puede calcular:** sin costes no hay referencia. Además necesita al menos 4 entradas con coste del mismo par (ventana 3 + la actual, D3) |

- **Matiz del plan:** §2.5 dice «ningún evento se emite a medias: un evento de inventario no se activa hasta que existe la columna de la que salen sus campos mínimos». Con `null` en `product_category`/`programme_id` y `min_stock` de la configuración, los eventos validan el esquema `1.0.0`, pero contradicen esa frase. Emitirlos así exige corregir §2.5 (texto, sin cambio de versión; ver D5).
- **Datos de negocio:** la clasificación de los activos (`product_category`, `programme_id`), el catálogo de programas y los costes unitarios **no tienen fuente en el repositorio**. Si hacen falta valores (semilla o demo), los decide el usuario; este análisis no propone ninguno.

### C3. `direct_stock_edit_rejected`

- **Comprobado:** la UI no tiene ningún botón, ruta ni petición que intente editar el stock:
  - `lib/api-client.ts` no emite `DELETE` y el test estático lo prohíbe en el cliente (`production-source.test.mjs:559-565`);
  - ningún servicio envía `current_stock`;
  - el Historial es de solo lectura.
- **Dónde se ve:** solo en la API, en `services/api/app/core/errors.py:207` (`_http_exception_handler`, 405 **antes** de autenticar) y `:230` (`_validation_exception_handler`, 422 `extra_forbidden`), como define P7.
- **Propuesta:** se emite desde la API o no se emite. Dispararlo desde el frontend obligaría a inventar una acción de la UI que no existe; eso sería una funcionalidad nueva, no telemetría. Va dentro de D1.

### C4. Respuesta del stub: `200 {received: N}` frente a `202 {accepted, rejected}`

- **Plan (§2.4):** `202 {"accepted": n, "rejected": m}`. Los inválidos se descartan uno a uno.
- **Enunciado:** `200 {"received": N}`. Es lo que se evalúa.
- **Propuesta:**
  - el stub responde `200 {"received": N}`, como pide el enunciado;
  - el frontend trata **cualquier 2xx** como éxito y **no lee el cuerpo**: cuando el colector real responda `202 {accepted, rejected}`, el frontend no cambia (es lo que pide el tech lead);
  - se anota en el plan, §2.4: la respuesta `200 {received}` es la del stub y la `202` la del colector definitivo. Es texto del plan, no del esquema: no cambia `schemaVersion`.
- **Lote inválido:** con Pydantic, un evento mal formado da un 422 al lote entero. Para el stub es lo deseable (se ve en Network). El descarte uno a uno queda para el colector real. El frontend **no reintenta** un 4xx (C5).

### C5. Reintentos

- **Plan (§2.4 y §8.4):** sin reintentos: si falla el envío, se descarta.
- **Enunciado:** hasta 3 reintentos con espera exponencial y luego descartar. Se evalúa.
- **Propuesta:** adoptar el del enunciado, acotado:
  - solo ante red, timeout, 5xx y 429; **nunca** ante 4xx (un lote inválido no mejora al repetirlo);
  - esperas de 1 s, 2 s y 4 s; tras el tercer fallo se descarta el lote, sin mostrar nada ni registrar nada;
  - un lote a la vez: mientras uno espera su reintento, los eventos nuevos siguen en la cola;
  - `sendBeacon` no se reintenta: si devuelve `false`, el lote se pierde;
  - la deduplicación por `eventId` (ya prevista para el almacén, §7.3) absorbe un reintento de un lote que sí había llegado;
  - se corrige el texto de §2.4 y la fila «Pérdida de eventos del frontend» de §8.4. Sin cambio de versión.

### C6. `sessionId` y `userId`

- **Plan (D7, §5, §2.4):** `sessionId` = claim `sid` del JWT (P4), creado en el login; `userId` = `sub`. **En el frontend los pone el colector desde el token**, nunca el cliente. Los eventos del frontend son de identidad «opcional», salvo `user_logged_out`, que es «autenticado» (`sessionId` y `userId` obligatorios).
- **Enunciado:** el servicio del frontend los genera y los añade a cada evento; `sessionId` se genera en el login y se guarda «en memoria de sesión».
- **Dónde guardarlo sin romper las reglas:**

  | Opción | Problema |
  |---|---|
  | `sessionStorage` | Prohibido por `uis/backoffice/CLAUDE.md` y por el test estático (`:39`) |
  | `localStorage` | Solo `lib/auth-token.ts`, y solo para el JWT (`:538-543`) |
  | Una variable del módulo, generada en el login | Se pierde al recargar: cada recarga sería otra sesión. No coincide con el `sid` que verá la API (P4), así que no se pueden cruzar los eventos del frontend con los de la API |
  | **Leer `sid` y `sub` del propio JWT** | Nada que guardar: se derivan del token que ya existe, cada vez que se construye un evento. Sobrevive a la recarga y coincide con la API |

- **Propuesta (D8):** P4 (añadir `sid` al JWT) entra en este ticket. El servicio rellena `sessionId` y `userId` desde los claims del token actual. Decodificar el payload del JWT produce `unknown`, así que va en un normalizador nuevo de `services/normalizers.ts`. Ni se verifica la firma ni se guarda nada nuevo: `lib/auth-token.ts` sigue guardando solo el JWT.
  - Sin token, o con un token anterior a P4 (sin `sid`), van como `null`.
  - El colector real (Fase 3) **sobrescribe** los dos con los del token cuando la petición trae uno válido. Es el plan, con una corrección: «no se aceptan del cliente» pasa a «no se confían del cliente».
  - El modelo `TelemetryEvent` lleva las 8 claves del envelope (§5), así que se reutiliza sin cambios en la Fase 3.

### C7. URL del endpoint y variables de entorno

| Enunciado | Repositorio | Propuesta |
|---|---|---|
| `.env.local` del backoffice | Un solo `.env` en la raíz; un `.env.local` montado en el contenedor pierde ante el entorno del proceso (`uis/backoffice/CLAUDE.md`, «Docker») | `NEXT_PUBLIC_TELEMETRY_ENDPOINT` en el `.env` de la raíz y en `.env.example` |
| — | El contenedor `ui` solo recibe las variables listadas en `docker-compose.yml`, con `${VAR:?…}` | Añadirla a `ui.environment` con el mismo `:?`: así falla con un mensaje claro si falta. **Efecto:** cada `.env` existente necesita la línea nueva antes del siguiente `docker compose up`. La comprobación de aislamiento de `AGENTS.md` (solo `API_INTERNAL_URL`, las `NEXT_PUBLIC_*` y `WATCHPACK_POLLING`) sigue valiendo |
| `http://localhost:8000/telemetry/events` | El navegador nunca habla con `:8000`: va por `/backend` (rewrite de `next.config.ts`, mismo origen, sin CORS) | Valor `/backend/telemetry/events`: la URL **completa** del endpoint, como dice el nombre. El cliente la usa como base con ruta vacía, y `sendBeacon` acepta la misma URL relativa |
| Validación | Las demás `NEXT_PUBLIC_*` son perezosas: si faltan, la UI muestra un error de configuración | **Diferencia a propósito:** sin la variable, `track()` no hace nada y no muestra nada. La telemetría nunca bloquea ni avisa al usuario |
| `TELEMETRY_ENDPOINT` en el backend | `Settings` lee y valida todas las variables al arrancar (`app/core/config.py`) | Ver D9 |

### C8. `sendBeacon` sin `Authorization`

- **Hecho:** `navigator.sendBeacon` no admite cabeceras. Un lote enviado al ocultar la pestaña llega **sin token**.
- **Consecuencias:**
  - el stub (y el colector real) **no** puede exigir autenticación: sin dependencia `get_current_user` en el router. Si la tuviera, el 401 haría además que `api-client` borrase el token (C9);
  - con el diseño del plan (ids del token), los eventos del beacon llegarían con `userId`/`sessionId` en `null`, y `user_logged_out` no validaría. Con C6 (ids del cliente) llegan con ids **declarados, no verificados**.
- **Riesgos del endpoint abierto y límites propuestos:**

  | Riesgo | Mitigación |
  |---|---|
  | Eventos falsos | Solo se aceptan los 10 `event_type` de emisor frontend, todos de UX: los de negocio no se pueden fabricar (C1). En la Fase 3, un `sessionId` declarado solo se da por bueno si ya se vio con ese `userId` en un lote autenticado |
  | Cuerpos grandes | Lote de 1 a 50 eventos y ≤ 64 KiB (§2.4), por debajo del límite general de 1 MiB (`BodySizeLimitMiddleware`). El navegador limita además el `keepalive`/beacon a unos 64 KiB en vuelo: el lote de 20 eventos queda muy por debajo. Si `sendBeacon` devuelve `false`, el lote se descarta |
  | Inundación de logs | El stub registra solo el número de eventos y sus `event_type`: nunca `properties`, ids ni el cuerpo |
  | Datos personales inyectados | Envelope estricto (`extra="forbid"`, UUID, ISO con `Z`); `properties` por la allowlist (D7) |
  | Volumen | Throttle de 120 eventos/min por token o en total para los anónimos (§2.4): en el stub o en la Fase 3 (D7) |

- **Alternativa del plan:** `fetch` con `keepalive: true` sí lleva `Authorization` y también sobrevive al cierre. El enunciado exige `sendBeacon` y se evalúa: la propuesta es `sendBeacon` en `visibilitychange: hidden` (y `pagehide`) y `fetch keepalive` en los envíos normales.

### C9. Un solo `fetch`

- **Plan (§2.4):** el transporte va por `lib/api-client.ts`, con `keepalive: true` e `ignoreUnauthorized: true`, para que un 401 de la telemetría no cierre la sesión.
- **Comprobado:** hoy cualquier 401 de una petición protegida llama a `clearAuthToken()` (`api-client.ts:253-256`). Si el stub respondiese 401, la telemetría cerraría la sesión del operador.
- **Propuesta:**
  - en `RequestOptions`: `keepalive?: boolean` e `ignoreUnauthorized?: boolean`;
  - un método nuevo `beaconJson(path, body): boolean` en el mismo `api-client`, que serializa (el único `JSON.stringify` sigue ahí) y llama a `navigator.sendBeacon` con un `Blob` `application/json`;
  - `lib/telemetry-api-client.ts` con `NEXT_PUBLIC_TELEMETRY_ENDPOINT`, siguiendo el patrón de `inventory-api-client.ts`;
  - **sin bucle:** los fallos del propio envío de telemetría **no** emiten `client_request_failed`, aunque `/telemetry/events` esté en su enum. Si la red está caída, ese evento tampoco saldría;
  - `tests/production-source.test.mjs`:
    - `sendBeacon` solo en `lib/api-client.ts`;
    - `track` como única entrada: ningún componente importa el cliente de telemetría;
    - `lib/telemetry.ts` sin `fetch(`.

---

## 3. Decisiones (las toma el usuario)

### D1 — Cómo se instrumentan los 5 obligatorios

#### Opción A — prerrequisitos de modelo y emisión desde el frontend

**Qué es:** se hacen P1–P3 (y P7, P9 y P10 en la API). El frontend emite 4 de los obligatorios con `track()` al recibir el 201, y la API emite `direct_stock_edit_rejected`.

- **Archivos:**
  - API: `inventory/models.py`, `schemas.py`, `service.py`, `vocabulary.py`, `core/config.py`, `core/errors.py`, `core/telemetry.py` (nuevo), `auth/security.py`;
  - frontend: `types/inventory.ts`, `normalizers.ts`, `inventory.service.ts`, los formularios y hooks de Entrada y Salida, y `lib/telemetry.ts`;
  - tests de las dos partes.
- **Contrato:** las respuestas de la API tienen que devolver lo que el frontend no sabe: `stock_before`, `stock_after`, `min_stock`, `currency`, `supplier_key` y el resultado de la comparación de costes. Es decir, `InboundOrderRead` y `OutboundOrderRead` crecen y SPECS Parte F (§37–§38) cambia.
- **Cambios en el plan:**
  - el emisor de 4 eventos pasa de API a frontend;
  - el colector tiene que **aceptar** eventos de negocio del cliente, justo lo que el plan prohíbe (§2.4);
  - un evento de negocio se perdería si la pestaña se cierra entre el 201 y el envío, cuando el plan solo acepta perder eventos de UX (§8.4).
- **Base de la demo:** las mismas `ALTER TABLE` que la opción C completa (abajo).
- **Resultado:** los 5 quedan instrumentados, pero la API calcula todo y el frontend solo lo reenvía. Es la opción con **más trabajo** y la de **datos menos fiables**.

#### Opción B — emisión desde el frontend con los datos actuales

**Qué es:** se emite desde el frontend con lo que hay hoy y se cambia el esquema.

- **Los datos no alcanzan:**
  - `kit_cost_variance_detected` no se puede calcular sin costes;
  - `inbound_order_created` necesita `unit_cost` y `supplier_key` (este, imposible en el navegador sin exponer la clave HMAC);
  - `direct_stock_edit_rejected` no ocurre en la UI (C3).
- **No es una versión menor:** quitar `unit_cost` o `supplier_key` de `required`, o quitar el evento, es una versión **mayor** según §5.4 (quitar una propiedad). Una `1.1.0` solo permite añadir propiedades opcionales o valores de enum.
- **Resultado:** quedan, como mucho, `outbound_order_created` (con un `stock_after` no fiable) y `stock_threshold_triggered` (con un cruce calculado sobre una lectura previa, lo que el plan descarta en §8.1). **No es viable**: se describe para descartarla.

#### Opción C (recomendada) — la API emite los obligatorios y el frontend sus 10 eventos

**Qué es:** se mantiene D10. La API emite los 5 obligatorios con `emit()` (P6), que escribe una línea JSON por evento en el logger `nexova.telemetry`. El frontend captura con `track()` sus 10 eventos (D2). Tiene dos niveles:

**C-mínimo, sin tocar la base de la demo:** P4, P6, P7 y P9 (solo la clave en el `.env`), más un parámetro de configuración para `min_stock`.

| Evento | Estado |
|---|---|
| `outbound_order_created` | Instrumentado. `product_category` y `programme_id` en `null`, `currency` derivada de la oficina |
| `stock_threshold_triggered` | Instrumentado, con `min_stock` = `INVENTORY_DEFAULT_MIN_STOCK` (5) para todos los activos hasta que exista la columna |
| `direct_stock_edit_rejected` | Instrumentado (P7) |
| `inbound_order_created` | **No** (falta `unit_cost`) |
| `kit_cost_variance_detected` | **No** (faltan los costes) |

Resultado: **3 de 5**. Hay que corregir el texto de §2.5 (el evento con `null` hasta la clasificación) y añadir el parámetro de configuración de `min_stock`. Sin cambio de esquema.

**C-completo:** C-mínimo, más P1, P2, P3 y P10, con migración. Instrumenta **los 5**.

- **Límites de los datos:**
  - `kit_cost_variance_detected` solo se dispara con 4 entradas con coste del mismo par: hasta que el usuario cargue esos datos, está instrumentado, pero no hay ninguno;
  - `product_category` y `programme_id` siguen en `null` hasta que el usuario clasifique los activos (D1-b).
- **Contrato que cambia:**
  - `AssetCreate`: `product_category`, `programme_id` y `min_stock` opcionales; `AssetRead` los devuelve;
  - `InboundOrderCreate.unit_cost`, obligatorio (P3): **cambio incompatible** para el formulario de Entrada, que necesita un campo «Coste unitario», y para el seed, que pasa por los schemas y necesitaría costes (los decide el usuario);
  - `InboundOrderRead` añade `unit_cost` y `currency`;
  - SPECS Parte F (§35–§39), el normalizador y los tipos del frontend, la ruta `PATCH /inventory/products/{id}/min-stock` de P2 (opcional en este ticket) y alinear el indicador «Bajo» (D4 del plan);
  - los tests del inventario.
- **Cambios en la base de la demo (Supabase).** Todos son aditivos y nullable o con `DEFAULT`, así que ninguna fila cambia de valor:

  ```sql
  BEGIN;
  ALTER TABLE assets ADD COLUMN IF NOT EXISTS product_category VARCHAR(32) NULL;
  ALTER TABLE assets ADD CONSTRAINT ck_assets_product_category
    CHECK (product_category IS NULL OR product_category IN ('training_kit', 'certification', 'onboarding_equipment'));
  ALTER TABLE assets ADD COLUMN IF NOT EXISTS programme_id VARCHAR(64) NULL;
  ALTER TABLE assets ADD COLUMN IF NOT EXISTS min_stock INTEGER NOT NULL DEFAULT 5;
  ALTER TABLE assets ADD CONSTRAINT ck_assets_min_stock CHECK (min_stock >= 0);
  ALTER TABLE asset_entries ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(12, 2) NULL;
  ALTER TABLE asset_entries ADD CONSTRAINT ck_asset_entries_unit_cost CHECK (unit_cost IS NULL OR unit_cost > 0);
  ALTER TABLE asset_entries ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NULL;
  ALTER TABLE asset_entries ADD CONSTRAINT ck_asset_entries_currency CHECK (currency IS NULL OR currency IN ('EUR', 'USD'));
  COMMIT;
  ```

  - **Sin pérdida:** las filas existentes quedan con `NULL` (y `min_stock = 5`); los `CHECK` las aceptan todas. Desde PostgreSQL 11, un `ADD COLUMN` con `DEFAULT` constante no reescribe la tabla. El bloqueo `ACCESS EXCLUSIVE` es breve: son tablas de decenas de filas.
  - **Las filas antiguas no se rellenan:** `currency` queda `NULL` en las entradas antiguas, como dice P3. Rellenarla desde la oficina sería un `UPDATE` y solo se haría con la confirmación del usuario.
  - **Reversible:** `ALTER TABLE … DROP CONSTRAINT …` y `DROP COLUMN …`. Solo se pierde lo escrito en las columnas nuevas.
  - **Cómo se aplica:** un script nuevo del módulo (p. ej. `python -m app.modules.inventory.migrate`), con `--dry-run` que imprime la SQL. Aplica todo en una transacción y es idempotente: `ADD CONSTRAINT` no admite `IF NOT EXISTS`, así que el script consulta `pg_constraint` antes. Nunca lo ejecuta `init_db` al arrancar. Orden:
    1. una base de pruebas (nunca la de la demo), dos veces: la segunda no hace nada;
    2. la de la demo, **solo con la confirmación del usuario**.

    `create_all` crea las columnas nuevas en las bases nuevas (tests en SQLite); el DDL de PostgreSQL se comprueba compilando, como el resto del inventario.
  - **Cómo se verifica sin tocar datos** (todo de solo lectura), antes y después:
    - `SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name IN ('assets', 'asset_entries')`;
    - `SELECT conname FROM pg_constraint WHERE conrelid IN ('assets'::regclass, 'asset_entries'::regclass)`;
    - `SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('assets', 'asset_entries', 'asset_exits')`: RLS sigue activo;
    - `SELECT count(*)` de las tres tablas: los mismos antes y después;
    - `GET /inventory/products`: el mismo `current_stock` por activo.

**Recomendación: C, con C-completo si el ticket tiene que cerrar con los 5 instrumentados.** C-mínimo da 3 de 5 sin tocar la base de la demo.

- **Por qué:**
  - respeta el plan aprobado (D10): la API es la única que ve `FOR UPDATE`, la clave HMAC, el historial de costes y los 405;
  - los eventos de negocio no se pueden fabricar desde el navegador ni se pierden al cerrar la pestaña;
  - no cambia `schemaVersion`.
- **Riesgo de evaluación, a sabiendas:** el criterio «todas las métricas obligatorias instrumentadas» se cumple en la API, no con `track()`, y esos eventos no aparecen en la pestaña Network: se ven en `docker compose logs api` (logger `nexova.telemetry`). La PR lo explica con D10 y la tabla de §2.5 del plan. Si la evaluación literal pesa más que el contrato, la alternativa es A, con su coste.
- **Infraestructura de la API que C añade:** P6 (`emit` + allowlist en tiempo de ejecución) y P4 (`sid`). P5 (`X-Request-ID`) es opcional: sin él, `requestId` lo genera el emisor (D8).
- **La allowlist de P6:** la imagen de la API se construye con el contexto `./services`, así que `docs/telemetry/event-schemas.json` **no está en el contenedor**. La tabla tiene que ser un módulo Python generado y comiteado (`app/core/telemetry_schemas.py`), con un test que compruebe que sigue al JSON. No se puede leer el JSON en tiempo de ejecución.

### D2 — Eventos no obligatorios

**Los 10 de emisor frontend del plan** (allowlists exactas de `event-schemas.json`). Todos necesitan P8 (este ticket) y P4 para el `sessionId`:

| # | `event_type` | Categoría | `properties` (allowlist exacta) | Punto de captura | ¿Ya? |
|---|---|---|---|---|---|
| 16 | `user_logged_out` | autenticación | `trigger` ∈ `header_button`, `session_error_screen` | `components/auth/account-nav.tsx:46` y `auth-guard.tsx:45`, antes de `session.logout()` (`hooks/use-auth-session.ts:210`); envío inmediato antes de borrar el token | Sí |
| 26 | `page_viewed` | navegación | `route_template` (enum de 15 rutas), `previous_route_template` (ídem o `null`), `entry` ∈ `initial_load`, `in_app_navigation` | `components/telemetry/page-view-tracker.tsx` (nuevo) en `app/layout.tsx`, con `usePathname` y 1 s de debounce | Sí |
| 27 | `page_not_found_viewed` | navegación | `previous_route_template` | `app/not-found.tsx:9` | Sí |
| 28 | `form_started` | flujos | `form` (enum de 11 formularios) | `hooks/use-form-telemetry.ts` (nuevo) | Sí |
| 29 | `form_submitted` | flujos | `form`, `outcome` ∈ `success`, `validation_error`, `api_rejected`, `session_expired`, `network_error`, `server_error`, `duration_ms`, `attempt_number` | `hooks/use-inbound-form.ts:107`/`:110`, `use-outbound-form.ts:210`/`:215` y los demás hooks de formulario | Sí (el `requestId` del envío necesita la parte cliente de P5) |
| 30 | `form_abandoned` | flujos | `form`, `last_field` (`^[a-z_]+$` o `null`), `had_validation_error`, `had_api_error`, `duration_ms` | `hooks/use-form-telemetry.ts`, en el desmontaje y en `pagehide` | Sí |
| 31 | `form_validation_failed` | flujos | `form`, `fields` (array de nombres) | `services/inventory.service.ts:289`/`:305`, `suppliers.service.ts:210`, `incident-manager.service.ts:270` y los `validate*Form` de `auth.service.ts:107-135` | Sí |
| 32 | `frontend_error_captured` | errores | `boundary` ∈ `route`, `global`, `route_template` (o `null`), `suppressed_count` | `app/error.tsx:23` y `app/global-error.tsx:25`, en un `useEffect`, sin leer el error | Sí |
| 33 | `client_request_failed` | errores | `kind` ∈ `network`, `timeout`, `config`, `http_method`, `api_route_template` (enum de 24 rutas), `timeout_ms` (o `null`), `suppressed_count` | `lib/api-client.ts:227` y `:247-251`, excepto las peticiones de telemetría (C9) | Sí |
| 39 | `page_load_recorded` | rendimiento | `route_template` ∈ `/suppliers`, `/incident-manager`, `/inventory/products`, `/inventory/orders`, `duration_ms`, `outcome` ∈ `data`, `empty`, `error` | `hooks/use-inventory-assets.ts:99`, `use-inventory-orders.ts:99`, `use-supplier-directory.ts` y `use-incident-board.ts` (primera carga) | Sí |

- **El piso técnico del enunciado:**
  - **errores:** `frontend_error_captured` (límites de error; el enunciado admite «o Error Boundaries») y `client_request_failed`;
  - **rendimiento:** `page_load_recorded`;
  - **navegación:** `page_viewed` y `page_not_found_viewed`.
- **`window.onerror` y `unhandledrejection`:** no están en el plan. Capturarlos exigiría añadir valores al enum `boundary` (p. ej. `window_error`, `unhandled_rejection`), una versión menor (D5). **Recomendación:** no en este ticket; los límites de error ya cumplen el enunciado.
- **Throttle en la pestaña (§7.2):** `client_request_failed` y `frontend_error_captured`, uno cada 60 s por clave, con `suppressed_count`; `page_viewed`, con debounce de 1 s; `form_started`, una vez por formulario y montaje.
- **Recomendación:**
  - los 10;
  - en los formularios, el inventario primero (Entrada y Salida, que son el flujo del BRIEFING) y, si cabe, el resto (`login`, `register`, `supplier_create`, `incident_create`…), con el mismo hook.
- **Negocio desde la API, si D1 = C:** con `emit()` ya hecho, las oportunidades de inventario son baratas y cubren la categoría de negocio no obligatoria:
  - `outbound_order_rejected` (stream: `insufficient_stock`);
  - `inbound_order_rejected`;
  - `inventory_validation_failed`;
  - `product_created`.

  `login_failed` y `user_logged_in` cubren la autenticación en la API (D4). **Recomendación:** esos 6, si el tiempo alcanza tras los 10 del frontend. El resto de los 42 de la API, en otro ticket.

### D3 — Web Vitals (actividad adicional)

- **Plan:** **no hay ningún evento** que los cubra, y §8.1 los **descarta** a propósito: la auditoría de rendimiento ya los midió (`AUDIT.md`), `page_load_recorded` cubre el tiempo hasta los datos, y «se puede añadir más adelante si reaparece un problema».
- **Coste técnico:** bajo. `useReportWebVitals` de `next/web-vitals` viene con Next 16 (sin dependencia nueva), en un componente cliente del layout.
- **Opción A — fuera (recomendada si D1 = C):** la PR dice que la actividad adicional no se hizo y por qué (§8.1). No cambia el contrato.
- **Opción B — evento nuevo en `1.1.0`:**
  - **evento:** `web_vital_recorded`; categoría rendimiento, emisor frontend, batch, prerrequisitos P4 y P8;
  - **allowlist:** `metric` ∈ `LCP`, `CLS`, `INP`, `FCP`, `TTFB`; `value` (`number`); `rating` ∈ `good`, `needs-improvement`, `poor`; `route_template` (enum de 15 rutas);
  - **frase:** detectar una regresión de la experiencia percibida tras un despliegue, para decidir si revertirlo o corregirlo;
  - **efecto:** al ser una versión global (D5), sube `schemaVersion` de los 52 eventos y de los 53 ejemplos, y las cifras del plan (53 eventos, 11 de frontend, 40 batch, rendimiento 3).
- **Recomendación:** A en este ticket. B solo si D1 o D2 obligan a una `1.1.0` de todos modos (por ejemplo, los valores nuevos de `boundary`); entonces se añade en la misma versión.

### D4 — `login_failed`

| | Enunciado | Plan |
|---|---|---|
| Emisor | Frontend (hooks de autenticación) | **API** (`services/api/app/routes/auth.py:42` y `:45`) |
| `reason` | `invalid_credentials`, `session_expired`, `network_error` | `malformed_email`, `invalid_credentials` |
| Identidad | — | Anónima: `userId` y `sessionId` siempre `null` |

- **Comparación por valor:**
  - `invalid_credentials`: está en los dos;
  - `session_expired`: **no aplica a un login**, que se envía con `skipAuth` y sin token. La caducidad la mide `session_expired` (evento #14, API);
  - `network_error`: la API no lo ve. Ya lo cubren `client_request_failed` (`kind = network`, `api_route_template = /auth/login`) y `form_submitted` (`form = login`, `outcome = network_error`).
- **Opción A (recomendada):** el plan tal cual. `login_failed` desde la API (P6), y en el hook de autenticación (`hooks/use-auth-form.ts`) `form_submitted`/`form_validation_failed` con `form = login`. Cubre las tres razones del enunciado sin duplicar el evento. Nunca el email ni la contraseña, que ningún esquema admite.
- **Opción B:** un `login_failed` también desde el frontend, con `network_error` añadido al enum (versión menor). Sería un evento con dos emisores (el validador asume uno por evento) y duplicaría los fallos que ya ve la API. **No recomendada.**

### D5 — Cómo se versiona el plan si cambia

- **Reglas (§5.4):**
  - versión menor (`1.1.0`): propiedad opcional o valor nuevo de un enum;
  - versión mayor (`2.0.0`), con un periodo en el que conviven las dos: quitar, renombrar, cambiar el tipo, hacer obligatoria una propiedad o quitar un valor;
  - las correcciones de `description` no cambian la versión.
- **La versión es global:** `scripts/validate_event_schemas.py:55` (`SCHEMA_VERSION = "1.0.0"`) exige el mismo `const` en todos los eventos y en todos los ejemplos (`:242`). Subirla toca los 52 esquemas, los 53 ejemplos del plan y la constante del script. Añadir un evento nuevo no está en §5.4; por analogía (es aditivo) sería una versión menor.
- **Lo que este análisis propone no cambia la versión:**
  - los textos de §2.4 (respuesta del stub, reintentos, ids «no confiados»), §2.5 (`null` hasta la clasificación, `min_stock` de la configuración) y §8.4;
  - D4 y D3, en su opción A.

  Solo D3 B y los valores nuevos de `boundary` (D2) llevarían a `1.1.0`.
- **Procedimiento si cambia:**
  1. ficha del plan + `event-schemas.json` + catálogo y cifras (§4 y la cabecera);
  2. `SCHEMA_VERSION` del script y la constante compartida del código: una en `lib/telemetry.ts` y otra en la API;
  3. `python scripts/validate_event_schemas.py`;
  4. `ajv-cli@5.0.0` solo si aparece una palabra clave nueva (§9.2);
  5. un test de contrato en el frontend que lea `event-schemas.json` y compare la constante y las allowlists del código (D6). Así, el código y el esquema no pueden divergir sin que falle un test.

### D6 — Verificación

**Frontend** (`node:test`, sin dependencias; `mock.timers` del runner nativo para los temporizadores):

- **El servicio**, construido con dependencias inyectadas (transporte, beacon, reloj, generador de UUID y visibilidad):
  - un evento solo → se envía a los 10 s, no antes;
  - 20 eventos → envío inmediato, sin esperar a los 10 s;
  - fallo de red o 5xx → reintentos a 1, 2 y 4 s y luego descarte;
  - un 4xx → sin reintento;
  - un lote a la vez;
  - `visibilitychange: hidden` → `sendBeacon` con lo pendiente y la cola vacía; si `sendBeacon` devuelve `false`, se descarta;
  - el envelope automático: `eventId` UUID v4, `timestamp` ISO con milisegundos y `Z` en el momento de la captura (no del envío), `schemaVersion` de la constante, `requestId` UUID, y `userId`/`sessionId` de los claims o `null`;
  - sin la variable de entorno, `track()` no hace nada;
  - `track()` nunca lanza;
  - el throttle con `suppressed_count`.
- **`api-client`:** `keepalive` llega al `fetch`; con `ignoreUnauthorized`, un 401 no borra el token; `beaconJson` serializa y usa `Blob` `application/json`.
- **Contrato** (`tests/telemetry-contract.test.mjs`): los `event_type`, las claves y los enums del código coinciden con los 10 esquemas de emisor frontend de `event-schemas.json`, y la constante de versión, con su `const`.
- **Estático** (`production-source.test.mjs`, C9): `sendBeacon` y `fetch(` solo en `api-client`; ningún componente importa el cliente de telemetría; los límites de error siguen sin leer el error.
- **Jest:** solo si alguna utilidad pura lo pide; si no, nada nuevo.
- **La fila de `uis/backoffice` de `AGENTS.md` §4:** `tsc`, `lint` (con los 4 errores conocidos), `build`, `node:test` y Jest.

**Stub** (`services/api/tests/test_telemetry_events.py`, en el contenedor efímero de `services/api/TESTING.md` §14, porque Windows bloquea el venv del host):

- **Lotes válidos:** 1, 20 y 50 eventos → `200 {"received": N}`; **sin token** → 200, no 401; con un token caducado → tampoco 401;
- **422:**
  - lote vacío o de 51 eventos;
  - una clave extra en el envelope;
  - un UUID mal formado;
  - un `timestamp` sin `Z`;
  - un `event_type` fuera del patrón o de emisor API (p. ej. `outbound_order_created`): el cliente no fabrica eventos de negocio;
- **413:** un cuerpo de más de 64 KiB;
- **Log:** `caplog` comprueba que se registran el número de eventos y sus `event_type`, y que nunca aparecen los valores de `properties`, los ids ni el cuerpo;
- **Configuración:** `TELEMETRY_ENDPOINT` se lee y se valida (D9);
- **Contrato y suite:** `response_model` del stub en la comprobación de cobertura de `test_serialization.py`; la suite entera (`unittest` y `pytest`) sin regresiones.

**Lo que hace el usuario en el navegador** (Docker, `localhost:3001`, con la pestaña Network filtrada por `telemetry`):

1. Entrar y navegar por Inicio → Activos → Entrada → Salida → Historial. Antes de 10 s no sale nada; a los 10 s, un `POST /backend/telemetry/events` con `{"events": [...]}` → **200** `{"received": N}`.
2. **Payload:** cada evento con las 8 claves, `page_viewed` con `route_template` y sin query string, y ningún email, nombre ni contraseña.
3. **Captura para la PR:** la petición seleccionada, con el payload y la respuesta 200 visibles.
4. **Lote por tamaño:** 20 eventos seguidos (p. ej. cambiar de página rápido) → envío antes de los 10 s.
5. **Beacon:** cambiar de pestaña con eventos pendientes → una petición de tipo `ping`/beacon, sin `Authorization`, con 200.
6. **Reintentos:** con la API parada (`docker compose stop api`), el envío falla y se repite 3 veces (1, 2 y 4 s) y luego para; la UI no muestra nada y la sesión no se cierra.
7. **Logout:** el lote con `user_logged_out` sale antes de volver a `/login`.
8. **Eventos de la API** (si D1 = C): `docker compose logs api | grep nexova.telemetry` tras una salida.

### D7 — Profundidad de la validación del stub (y del modelo `TelemetryEvent`)

- **Opción A (recomendada):** el modelo Pydantic, completo desde ya:
  - las 8 claves con `extra="forbid"`;
  - `eventId` y `requestId` UUID; `requestId` admite `null` según §5;
  - `timestamp` con el formato de §5;
  - `sessionId` y `userId` UUID o `null`;
  - `event_type` con el patrón de la taxonomía y restringido a los 10 de emisor frontend;
  - `schemaVersion` igual a la constante;
  - `properties` como objeto JSON.

  La allowlist por evento (claves, tipos y enums) llega con la tabla generada de P6, en este ticket si D1 = C y si no en la Fase 3. El modelo no cambia en la Fase 3: la allowlist es un paso posterior al modelo.
- **Opción B:** el stub valida también cada allowlist ya. Es más fiel al plan, pero adelanta la tabla generada de P6 aunque D1 no sea C.

### D8 — Identidad y correlación en el envelope del frontend

- **`sessionId` y `userId`:** de los claims del JWT, con P4 (C6). Es la recomendación; las alternativas, sus problemas y la tabla de opciones están en C6.
- **`requestId`:**
  - en `form_submitted` y `client_request_failed`, el `X-Request-ID` de la petición asociada. Exige que `api-client` añada la cabecera (la parte cliente de P5). En el backoffice es del mismo origen, sin CORS;
  - en los demás, un UUID propio por evento.
- **La parte servidor de P5** (middleware, `request.state`, línea de timing, CORS para el tracker): opcional en este ticket. **Recomendación:** sí, si D1 = C, porque `emit()` la necesita para el `requestId` de los eventos de la API. Si no, en la Fase 3.

### D9 — `TELEMETRY_ENDPOINT` en el backend

- **Enunciado:** la API declara `TELEMETRY_ENDPOINT` en su configuración «aunque todavía no la uses para redirigir tráfico».
- **Opción A (recomendada):** `Settings.telemetry_endpoint`, opcional, en `.env.example` (comentada) y validada al arrancar (`ConfigError` si no es una URL absoluta http(s) o un path que empieza por `/`). **No se usa** para montar la ruta, que sigue siendo `/telemetry/events`:
  - el contrato la fija: la ruta está en los enums `route_template` y `api_route_template` del plan;
  - hacerla configurable desacoplaría el frontend del contrato.

  Queda reservada para el destino del emisor de la API en la Fase 3.
- **Opción B:** usarla como path del router. **No recomendada**, por lo mismo.

---

## 4. Resumen de lo recomendado

| Decisión | Recomendación |
|---|---|
| D1 | C: la API emite los obligatorios (P4, P6, P7 y P9; C-completo con P1–P3 y P10 y la migración para tener los 5; C-mínimo, 3 de 5, sin tocar la base). El frontend emite sus 10 eventos |
| D2 | Los 10 de emisor frontend (formularios del inventario primero); si da tiempo, 6 de la API: `outbound_order_rejected`, `inbound_order_rejected`, `inventory_validation_failed`, `product_created`, `login_failed`, `user_logged_in` |
| D3 | Fuera (§8.1); se añade en `1.1.0` solo si se sube la versión por otro motivo |
| D4 | El plan: `login_failed` en la API; red y caducidad del login con `client_request_failed` y `form_submitted` |
| D5 | Sin cambio de versión: solo correcciones de texto en §2.4, §2.5 y §8.4; test de contrato en el frontend |
| D6 | `node:test` con temporizadores falsos, test de contrato, reglas estáticas, tests del stub en el contenedor efímero y el recorrido de Network del usuario |
| D7 | Modelo completo (8 claves, 10 tipos); allowlist por evento con P6 |
| D8 | Claims del JWT (P4); `X-Request-ID` en el cliente y, con D1 = C, el middleware |
| D9 | Declarada y validada, sin usarla para la ruta |
| C4 / C5 / C7–C9 | `200 {received}` + frontend que no lee el cuerpo; 3 reintentos solo en red, timeout, 5xx y 429; `NEXT_PUBLIC_TELEMETRY_ENDPOINT=/backend/telemetry/events` en el `.env` raíz y en compose; stub sin autenticación con límites; `api-client` con `keepalive`, `ignoreUnauthorized` y `beaconJson` |

**Orden de trabajo propuesto** (el del enunciado: stub → servicio → instrumentación):

1. Stub y configuración.
2. `api-client` y `lib/telemetry.ts` con sus tests.
3. Instrumentación del frontend.
4. Si D1 = C: P4, P6, P7 y P9, y después la migración (con la confirmación del usuario para la base de la demo).
5. Plan (§2.4, §2.5, §8.4), SPECS (parte nueva del stub), `uis/backoffice/CLAUDE.md`, `AGENTS.md`, `docs/local-development.md` y el banco de memoria.
6. PR `feat: telemetry event capture`.
