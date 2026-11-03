# Captura de telemetría en el frontend + colector stub: guía de revisión

Rama `feature/telemetry-capture`. Decisiones en [`capture-analysis.md`](./capture-analysis.md) (F0) y en el plan, §1.5 ([`telemetry-plan.md`](./telemetry-plan.md)). Contrato del stub y de las respuestas de alta: `services/api/SPECS.md`, Partes F y H. Reglas del frontend: `uis/backoffice/CLAUDE.md` («Telemetría»).

## 1. Qué se ha hecho, frente a lo que se evalúa

| Criterio del enunciado | Dónde | Estado |
|---|---|---|
| Stub `POST /telemetry/events` que acepta lotes con el modelo `TelemetryEvent` y devuelve `{ "received": N }` | `services/api/app/modules/telemetry/` (`router.py`, `schemas.py`) | Hecho: 200, de 1 a 50 eventos, ≤ 64 KiB, sin token, sin persistir |
| `TelemetryEvent` con todo el envelope del plan | `schemas.py`: las 8 claves de §5, `extra="forbid"`, los patrones del JSON | Hecho; la suite lo compara con `event-schemas.json` |
| URL desde `NEXT_PUBLIC_TELEMETRY_ENDPOINT`, no fija en el código | `lib/telemetry-api-client.ts`; `.env.example` y `docker-compose.yml` (`/backend/telemetry/events`) | Hecho |
| La API declara `TELEMETRY_ENDPOINT` | `app/core/config.py` (opcional, validada, sin uso: D9) | Hecho |
| Cola local, lotes de 10 s / 20 eventos, `sendBeacon` y reintentos con backoff | `lib/telemetry.ts` | Hecho: 3 reintentos (1, 2 y 4 s) solo ante red, timeout, 5xx y 429 |
| El servicio genera `eventId`, `sessionId`, `userId`, `timestamp`, `schemaVersion` y `requestId` | `lib/telemetry.ts` + `lib/session-identity.ts` (`sub`/`sid` del JWT, P4) | Hecho |
| Ni `fetch` ni axios para telemetría fuera del TelemetryService | `tests/production-source.test.mjs`: el único `fetch` y el único `sendBeacon`, en `lib/api-client.ts`; el cliente de telemetría solo lo usa `lib/telemetry.ts` | Hecho |
| Todas las métricas obligatorias instrumentadas | 4 con `track()` en el backoffice y `direct_stock_edit_rejected` en la API (§2) | Hecho, con la excepción de D1 |
| Piso técnico transversal (errores, rendimiento y navegación) | `frontend_error_captured`, `client_request_failed`, `page_load_recorded`, `page_viewed` y `page_not_found_viewed` | Hecho |
| `event_type` y allowlists del plan | `types/telemetry.ts` (14 eventos); `tests/telemetry-contract.test.mjs` y la validación de cada evento de los tests contra el JSON real | Hecho |
| Sin PII (email, nombre o contraseña) | Allowlists; tests que buscan canarios en los eventos | Hecho (§4) |
| Network: lotes en el stub con respuesta 200 | §3 | Hecho: verificado por el usuario el 2026-11-03, con las capturas en la PR |

**Actividad adicional:**

- **Web Vitals: no implementada** (D3). El plan los descarta a propósito (§8.1): la auditoría de rendimiento ya los midió y corrigió (`AUDIT.md`), y `page_load_recorded` cubre el tiempo hasta los datos. Añadirlos sería un evento nuevo y una versión `1.1.0` de los 52 esquemas, mezclada con este ticket.
- **Eventos de autenticación en los hooks:** sí. `user_logged_out` está en `useAuthSession.logout`. El fallo del login va en `form_submitted` (`form = login`, `outcome = api_rejected` / `network_error`), en el hook compartido `useAuthForm`.
  - `login_failed` y `session_expired` son de la API en el plan (D4) y **no** se emiten desde el frontend.
  - La allowlist de `login_failed` es `reason` ∈ `malformed_email`, `invalid_credentials`. El `session_expired` y el `network_error` del enunciado no aplican a un login, o no los ve la API.

## 2. Eventos instrumentados

Los 52 del catálogo siguen en el contrato; este ticket instrumenta 15. «Obligatorio» viene del BRIEFING; «propio» es una oportunidad identificada en el plan.

| `event_type` | Tipo | Categoría | Emisor | Lo captura |
|---|---|---|---|---|
| `inbound_order_created` | obligatorio | inventario | frontend | `hooks/use-inbound-form.ts` → `lib/inventory-telemetry.ts` (`trackInboundOrder`), con la respuesta 201 |
| `kit_cost_variance_detected` | obligatorio | inventario | frontend | El mismo, si el 201 trae `cost_variance` (lo calcula la API, P10) |
| `outbound_order_created` | obligatorio | inventario | frontend | `hooks/use-outbound-form.ts` → `trackOutboundOrder`, con la respuesta 201 |
| `stock_threshold_triggered` | obligatorio | inventario | frontend | El mismo, si `stock_before >= min_stock > stock_after` (datos de la API, bajo `FOR UPDATE`) |
| `direct_stock_edit_rejected` | obligatorio | inventario | **API** | `services/api/app/modules/telemetry/stock_edit.py`, desde los handlers de 405 y 422 de `core/errors.py` (P7); línea JSON en `nexova.telemetry` |
| `page_viewed` | propio | navegación | frontend | `components/telemetry/page-view-tracker.tsx` (layout raíz) → `lib/page-view-telemetry.ts` |
| `page_not_found_viewed` | propio | navegación | frontend | `components/telemetry/not-found-tracker.tsx` en `app/not-found.tsx` |
| `form_started` | propio | flujos | frontend | `hooks/use-form-telemetry.ts` (Entrada y Salida: primer cambio de campo; auth: primer envío) |
| `form_submitted` | propio | flujos | frontend | `lib/inventory-telemetry.ts` y `lib/auth-telemetry.ts` (`observe*`), en los hooks de formulario |
| `form_validation_failed` | propio | flujos | frontend | Los mismos, cuando la validación en cliente bloquea el envío |
| `form_abandoned` | propio | flujos | frontend | `hooks/use-form-telemetry.ts`: desmontaje y `pagehide` |
| `frontend_error_captured` | propio | errores | frontend | `components/telemetry/error-boundary-tracker.tsx` en `app/error.tsx` y `app/global-error.tsx` (el error no se pasa) |
| `client_request_failed` | propio | errores | frontend | `lib/api-client.ts` → `setTransportFailureListener` → `lib/telemetry.ts` (`reportTransportFailure`) |
| `page_load_recorded` | propio | rendimiento | frontend | `hooks/use-page-load-telemetry.ts` en Activos, Historial, Proveedores e Incidencias |
| `user_logged_out` | propio | autenticación | frontend | `hooks/use-auth-session.ts` (`logout(trigger)`), desde la cabecera y la pantalla de error de sesión |

**Formularios con embudo:** Entrada, Salida y los 5 de autenticación. El alta de proveedores, la de incidencias y la subida del CSV no lo tienen todavía.

## 3. Verificación en el navegador (pestaña Network)

**Verificado por el usuario el 2026-11-03**, en una ventana sin extensiones y contra un Postgres efímero (ya borrado), nunca contra la demo:

- **Lote por tiempo:** `POST /backend/telemetry/events` → 200 `{"received":4}`, con el envelope completo.
- **Beacon:** petición `ping` → 200.
- **Obligatorios del frontend:**
  - `inbound_order_created` en 5 entradas, con la misma `supplier_key` y sin el nombre del proveedor;
  - `kit_cost_variance_detected` en la 5.ª (referencia 10 → 20, +100 %, `increase`);
  - `outbound_order_created` y `stock_threshold_triggered` (18 → 4, mínimo 5).
- **`direct_stock_edit_rejected`:** 405 con id válido (oficina y moneda del activo) y con un segmento no numérico (`product_id` nulo); un segundo intento en menos de 60 s quedó suprimido por el throttle.
- **PII:** ninguna en ningún payload.

**Para repetirlo:** usa un Postgres de pruebas, nunca la demo, y `TELEMETRY_SUPPLIER_KEY` en la API.

1. Abre `http://localhost:3001`, inicia sesión y abre DevTools → Network, con el filtro `telemetry`.
2. **Lote por tiempo:** navega por Inicio → Inventario → Entrada → Salida → Historial. A los 10 s del primer evento sale un `POST /backend/telemetry/events`:
   - **Payload:** `{"events": [...]}`, cada evento con las 8 claves y `page_viewed` con `route_template` (sin query string);
   - **Respuesta:** **200** `{"received": N}`.
   - **La captura para la PR:** esta petición, con el payload y la respuesta visibles.
3. **Obligatorios:**
   - **Entrada:** una entrada con coste. Sale `inbound_order_created` con `office`, `product_id`, `product_category: null`, `programme_id: null`, `quantity`, `currency`, `unit_cost`, `supplier_key` y `asset_category`.
   - **Variación de coste:** tres entradas más del mismo activo y proveedor y una cuarta con un coste que se desvíe más del 10 % de la media → además `kit_cost_variance_detected`. **Los costes y las cantidades los eliges tú.**
   - **Salida:** una salida que deje el stock por debajo de 5 desde 5 o más → `outbound_order_created` y `stock_threshold_triggered`.
4. **Lote por tamaño:** 20 eventos seguidos (cambia rápido de página o escribe en un formulario) → el envío sale antes de los 10 s.
5. **Beacon:** con eventos pendientes, cambia de pestaña. Aparece una petición de tipo `ping` (beacon) al mismo endpoint, sin `Authorization`, con 200.
6. **Reintentos:**
   1. Para la API: `docker compose stop api`.
   2. Genera un evento y espera 10 s: el envío falla y se repite a 1, 2 y 4 s, y luego para. La UI no muestra nada y la sesión no se cierra.
   3. Vuelve a arrancarla: `docker compose start api`.
7. **Logout:** «Cerrar sesión» → un envío inmediato con `user_logged_out` antes de volver a `/login`.
8. **Sin datos personales:** en ningún payload aparecen el email, el nombre del activo, el proveedor ni `assigned_to`.
9. **El obligatorio de la API:** `curl -X PUT http://localhost:3001/backend/inventory/products/1` → 405. Comprueba la línea con `docker compose logs api | grep nexova.telemetry`.

## 4. Privacidad

- **Solo plantillas de ruta:** nunca el path real ni la query string (`?token=` de `/reset-password`).
- **Formularios:** solo nombres de campo (`^[a-z_]+$`) y el resultado; nunca un valor escrito.
- **Inventario:** ni el nombre del activo, ni el proveedor (solo su HMAC, `supplier_key`), ni `assigned_to`.
- **Errores:** los límites no pasan el error a su tracker; `client_request_failed` no lleva la URL.
- **Identidad:** `userId` es el seudónimo de TinyDB y `sessionId`, el `sid`. Nada nuevo se guarda en el navegador.
- **Logs del stub:** solo el número de eventos y sus tipos.

## 5. Entorno de verificación y migración

### 5.1 Migración P3 (probada en el efímero)

- **Prueba sobre un esquema anterior:** contenedor `nexova-telemetry-pg` (`postgres:17.6-alpine3.22`, solo en `127.0.0.1:55433`, red `nexova-telemetry-net`, volumen `nexova-telemetry-pg-data`). El esquema se creó con el código de `2d5c1d8` (anterior a P3) y una entrada de prueba.
- **Resultados:**
  - `--dry-run`: las 4 sentencias pendientes;
  - primera ejecución: aplicadas en una transacción;
  - segunda: «Nada que migrar».
- **Comprobado, de solo lectura:**
  - `unit_cost numeric(12,2)` y `currency varchar`, nullable;
  - los `CHECK` `ck_asset_entries_unit_cost_positive` y `ck_asset_entries_currency`;
  - RLS sigue activo en las 3 tablas;
  - la entrada previa sigue igual (cantidad 3), con coste `NULL`.

### 5.2 La base de la demo (migrada el 2026-11-03, con la confirmación del usuario)

**Resultado:** `--dry-run` con las 4 sentencias de P3, aplicadas en una transacción, y una segunda ejecución sin cambios. Antes y después, en una transacción `READ ONLY`, son iguales los conteos (6 activos, 5 entradas y 5 salidas), el stock por activo, una huella md5 de las entradas y otra de las salidas, RLS y las columnas y `CHECK` previos. Solo se añadieron `unit_cost`, `currency` y sus 2 `CHECK`. Las 5 entradas quedan con coste y moneda `NULL`.

**Para otra base existente:** desde `services/api`, con su `DATABASE_URL` en el entorno:

```bash
python -m app.modules.inventory.migrate --dry-run
```

```bash
python -m app.modules.inventory.migrate
```

**Comprobaciones de solo lectura, antes y después** (en el SQL editor de Supabase):

```sql
SELECT column_name, data_type, numeric_precision, numeric_scale, is_nullable FROM information_schema.columns WHERE table_name = 'asset_entries' ORDER BY ordinal_position;
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'asset_entries'::regclass ORDER BY 1;
SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('assets', 'asset_entries', 'asset_exits');
SELECT (SELECT count(*) FROM assets) AS assets, (SELECT count(*) FROM asset_entries) AS entries, (SELECT count(*) FROM asset_exits) AS exits;
```

Además, `GET /inventory/products` debe dar el mismo `current_stock` por activo. **Reversión** (solo si hiciera falta):

```sql
ALTER TABLE asset_entries DROP CONSTRAINT ck_asset_entries_currency, DROP CONSTRAINT ck_asset_entries_unit_cost_positive, DROP COLUMN currency, DROP COLUMN unit_cost;
```

**Una base sin migrar:** una API con este código contra ella falla al leer o escribir entradas (la columna no existe).

### 5.3 Vuelta al stack normal

Hecha el 2026-11-03: `docker compose up -d`, sin el override del efímero. La API usa la `DATABASE_URL` del `.env` (la demo). `GET /inventory/products`, `/inventory/products/{id}` y `/inventory/orders` responden 200 por `/backend`, con el stock de siempre (12/1/0/7/15/0) y sin ninguna escritura. El token de esa comprobación se firmó dentro del contenedor de la API y no salió de él.

## 6. Lo que queda fuera o sin verificar

- **`TELEMETRY_SUPPLIER_KEY` en el stack normal:** el `.env` de la raíz no la tiene. Hasta añadirla (y recrear `api`), las entradas devuelven `supplier_key` nulo y el backoffice no emite `inbound_order_created` ni `kit_cost_variance_detected`. Una clave distinta de la usada en la verificación da otras `supplier_key`, pero en el efímero no se guardó ninguna.
- **Prerrequisitos pendientes:**
  - **P1:** `product_category` y `programme_id` van en `null` y no hay catálogo de programas;
  - **P2:** `min_stock` es la configuración (5), no un mínimo por activo;
  - **P5:** `requestId` es un UUID propio de cada evento, sin correlación con `api.timing`;
  - **P6 completo:** allowlist y agregados de la API.
- **El stub, que hará el colector definitivo:**
  - acepta cualquier evento del catálogo (también los de la API);
  - un evento inválido rechaza el lote entero;
  - no hay throttle;
  - `userId` y `sessionId` no se verifican contra el token.
- **Pérdida de eventos:** un obligatorio de los que emite el frontend se pierde si la pestaña se cierra entre el 201 y el envío y el beacon tampoco sale (riesgo aceptado, D1, plan §8.4).
- **Un token anterior a P4** (sin `sid`) da `sessionId` nulo; `user_logged_out` no se emite hasta el siguiente login.
- **El Historial no muestra el coste**, aunque la API ya lo devuelve.
- **El seed** sigue sin costes: el CONTEXT no los da.
- **Sin comprobar a mano:** `global-error.tsx`, que solo aparece si falla el layout raíz; `client_request_failed` por timeout.
