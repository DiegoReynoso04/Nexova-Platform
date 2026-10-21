# Inventario de equipos y materiales — frontend del backoffice: guía de revisión

Documento para revisar la sección de inventario de `uis/backoffice`: cómo levantarla, qué se ve en cada página, qué cubre cada test y qué **no** está verificado.

- Brief literal del frontend (con la nota de equivalencias de este repo): [`inventory-frontend-brief.md`](./inventory-frontend-brief.md).
- Contexto de negocio (entidades, campos, vocabulario y reglas): [`context-nexova-gestion-inventario-hito-5.md`](./context-nexova-gestion-inventario-hito-5.md). El briefing de empresa es el [`README.md`](../README.md) raíz.
- Contrato HTTP de la API: [`services/api/SPECS.md`](../services/api/SPECS.md) Parte F; guía de revisión de la API: [`inventory-review.md`](./inventory-review.md).
- Reglas permanentes del frontend: [`uis/backoffice/CLAUDE.md`](../uis/backoffice/CLAUDE.md) (sección «Inventario»); puesta en marcha: [`uis/backoffice/README.md`](../uis/backoffice/README.md).
- Historial por fases (F1–F6) y validaciones ejecutadas: [`memory-bank/progress.md`](../memory-bank/progress.md).

> Las decisiones D1–D10 y los ajustes posteriores los tomó **el usuario** al aprobar el plan y revisar cada fase (2026-10-19 y 2026-10-20). No las han revisado el tech lead ni la CTO.

## Qué se construyó

Rama `feature/inventory-frontend`, sobre `main` en `8e5448e` (merge de la PR #21, la API del inventario). Sin dependencias nuevas.

| Pieza | Dónde | Qué hace |
|---|---|---|
| Contrato y vocabulario | `types/inventory.ts` | Activos, órdenes (discriminadas por `type`), valores de formulario, errores de UI; categorías, oficinas, tipos de salida, `QUANTITY_MAX` y `TEXT_MAX_LENGTH`, iguales al CONTEXT y a `vocabulary.py` |
| Frontera de red | `services/normalizers.ts` | Único `unknown`: activos, órdenes, cuerpo `{detail, code}` y campos de los 422 |
| Cliente | `lib/inventory-api-client.ts` | El mismo `createApiClient` de `lib/api-client.ts` (único `fetch`, Bearer, 401) con la base URL de `NEXT_PUBLIC_INVENTORY_API_URL`, sin reserva a `NEXT_PUBLIC_API_URL` |
| Servicio | `services/inventory.service.ts` | Único módulo que llama a `/inventory`: listar y leer activos, registrar entradas y salidas, listar órdenes; validación en cliente, body con números y la oficina del activo, y traducción de errores |
| Rutas y navegación | `lib/inventory-routes.ts`, `app/inventory/layout.tsx`, `components/inventory/inventory-nav.tsx` | Las 4 páginas del brief; un enlace «Inventario» en la cabecera y una subnavegación común; `/inventory` → `/inventory/products` |
| Activos | `/inventory/products` → `asset-list-view.tsx` → `hooks/use-inventory-assets.ts` | Tabla con Stock actual y nivel (`lib/stock-level.ts`: 0 Agotado, 1–5 Bajo, más de 5 Suficiente), y «Registrar entrada» / «Registrar salida» por fila con `?asset_id=` |
| Entrada de activos | `/inventory/orders/inbound` → `inbound-form-view.tsx` → `hooks/use-inbound-form.ts` | Selector «nombre — SKU (oficina)», Oficina de solo lectura, Cantidad, Proveedor; confirmación y formulario limpio con el activo del enlace |
| Salida de activos | `/inventory/orders/outbound` → `outbound-form-view.tsx` → `hooks/use-outbound-form.ts` | Stock reactivo (`GET /inventory/products/{id}` con cancelación), advertencia que no bloquea (`lib/stock-check.ts`), Asignación / Consumo, 400 de stock bajo Cantidad, stock leído de nuevo tras el envío |
| Historial | `/inventory/orders` → `order-history-view.tsx` → `hooks/use-inventory-orders.ts` | Tabla de solo lectura: tipo (insignia), activo, cantidad, oficina, detalle, fecha local (`lib/order-format.ts`) y `user_uuid` |
| Piezas compartidas | `asset-select.tsx`, `read-only-field.tsx`, `field-messages.tsx`, `inventory-error.tsx`, `lib/inventory-form-errors.ts`, `lib/asset-preselection.ts`, `lib/inventory-error-copy.ts` | Selector, valores de solo lectura (`<output>`), mensajes por campo, avisos de error y su reparto entre los campos y el aviso general |

## Cómo arrancarlo (Windows PowerShell)

Requisitos: lo de la [guía de la API](./inventory-review.md#cómo-revisar-este-hito-windows-powershell) (venv, `services/api/.env` con `DATABASE_URL` y un usuario en TinyDB), **Node.js 24** y `npm install` hecho en `uis/backoffice`.

### 1. La API, en una terminal

```powershell
cd services\api
uv run --env-file .env uvicorn app.main:create_app --factory --port 8000 --workers 1
```

La API acepta por defecto el origen `http://localhost:3000` (`CORS_ALLOWED_ORIGINS`). Para ver datos, el seed cargado (`uv run --env-file .env seed-inventory --email <usuario>`; ver la guía de la API).

### 2. `uis/backoffice/.env.local`, con las dos variables

```powershell
cd uis\backoffice
Copy-Item .env.example .env.local   # solo la primera vez
```

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_INVENTORY_API_URL=http://localhost:8000
```

`NEXT_PUBLIC_INVENTORY_API_URL` es solo el host: el servicio añade `/inventory/...`. `.env.local` está en `.gitignore`.

### 3. El backoffice, en otra terminal

```powershell
cd uis\backoffice
npm run dev
```

Abre `http://localhost:3000`, inicia sesión y entra en **«Inventario»**. Las variables `NEXT_PUBLIC_*` se leen al arrancar: **si cambias `.env.local`, para `npm run dev` (Ctrl+C) y vuelve a lanzarlo.** Sin `NEXT_PUBLIC_INVENTORY_API_URL`, las páginas del inventario muestran un error de configuración (el resto del backoffice sigue funcionando).

### 4. Suites y totales (desde `uis\backoffice`)

| Suite | Comando | Total |
|---|---|---|
| Tipos | `npx tsc --noEmit` | sin errores |
| Lint | `npm run lint` | sin errores |
| Build | `npm run build` | correcto; `/inventory/orders/inbound` y `/outbound` dinámicas (leen `?asset_id=`) |
| `node:test` | `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"` | 491 OK (344 antes del frontend del inventario) |
| Jest | `npm run test:jest` | 222 OK, 13 suites (161 antes) |

Ningún test conecta con la API ni con Supabase: el cliente y el servicio se prueban sobre un `fetch` falso, y los hooks con su sesión sin React.

## Recorrido manual (las 4 páginas)

Con la API, el seed y el backoffice en marcha, y una sesión iniciada. Las entradas y salidas **cambian el neto del seed**: para revisar sin tocar la demo, usa otro proyecto de Supabase o restaura después (ver la guía de la API).

1. **Sin sesión:** abre `http://localhost:3000/inventory/products` en una ventana privada → `/login`. Lo mismo con las otras tres rutas.
2. **Activos (`/inventory/products`):** la tabla muestra los 6 activos con Nombre, SKU, Categoría, Oficina y Stock actual. Cada stock lleva número y nivel con color, icono y texto: con el seed (13/0/0/7/15/0), tres «Suficiente» (13, 7 y 15) y tres «Agotado» (0). En la cabecera, «Inventario» está activo; la subnavegación marca «Activos».
3. **Entrada de activos:** pulsa «Registrar entrada» en una fila. La URL lleva `?asset_id=…`, el activo aparece elegido y la Oficina es la suya, como valor de solo lectura.
   - Envía vacío: errores junto a cada campo y **ninguna petición** (pestaña Red).
   - Cambia de activo: la Oficina cambia con él.
   - Con `?asset_id=999` en la URL: aviso «No se ha podido preseleccionar el activo» y el selector vacío.
   - Una entrada válida: el botón muestra «Registrando…» con spinner; después, «Entrada registrada: N × nombre (SKU)», Cantidad y Proveedor vacíos y el activo del enlace sigue elegido (si entras desde la subnavegación, sin `?asset_id=`, el selector vuelve a «Elige un activo…»).
4. **Salida de activos:** pulsa «Registrar salida» en una fila.
   - «Stock actual» aparece **antes** de la cantidad, con «Consultando stock…» mientras se lee; Cantidad está deshabilitada hasta conocerlo.
   - Cambia de activo y vuelve: el stock sigue al activo elegido.
   - «Asignación» sin «Asignado a»: error en ese campo, sin envío. Con «Consumo», «Asignado a» desaparece.
   - Una cantidad mayor que el stock: advertencia visible; el envío **no** se bloquea y la API responde con el 400, que aparece **bajo Cantidad** con su `detail` («Insufficient stock for asset '…'. Available: …, requested: ….»).
   - Una salida válida: «Salida registrada: N × nombre (SKU)», formulario limpio con el activo del enlace y el stock actualizado.
5. **Historial (`/inventory/orders`):** todas las órdenes, la más reciente primero, con insignias «↓ Entrada» y «↑ Salida» distintas, activo (nombre y SKU), cantidad, oficina, detalle («Proveedor: …», «Asignación → …» o «Consumo»), fecha local en español y el `user_uuid` completo. Sin botones de editar ni borrar.
6. **Errores:** para la API y recarga cualquier página del inventario → aviso de error con «Reintentar»; arranca la API y pulsa «Reintentar» → los datos cargan.
7. **Móvil:** con las herramientas del navegador a 375 px, ninguna página tiene scroll horizontal; las tablas se desplazan dentro de su contenedor.

## Trazabilidad: «Qué vamos a evaluar» → implementación → test → navegador

Fuente de los puntos: el brief literal ([`inventory-frontend-brief.md`](./inventory-frontend-brief.md), «Qué Vamos a Evaluar»). Los tests de `node:test` se citan como `archivo` → `bloque` → `test` (en `uis/backoffice/tests/`); los de Jest, en `uis/backoffice/__tests__/`. «Navegador» es la verificación del usuario con Supabase real (2026-10-20), salvo que se indique otra cosa.

| Punto | Implementación | Test | Navegador |
|---|---|---|---|
| Un módulo de integración dedicado; ningún `fetch` en los componentes | `services/inventory.service.ts` sobre `lib/inventory-api-client.ts` → `lib/api-client.ts` | `production-source` → «el único fetch de red está en lib/api-client.ts», «el inventario usa su propio cliente, sin reserva a NEXT_PUBLIC_API_URL», «la vista de entrada solo usa sus hooks; ni fetch ni cliente HTTP en las piezas del inventario», «historial: la vista solo usa su hook y nadie hace fetch» | — (estático) |
| Toda petición protegida lleva `Authorization` con el token actual | `lib/api-client.ts` (Bearer desde `lib/auth-token.ts`) | `inventory.service` → «servicio del inventario: peticiones» → «… lleva Authorization: Bearer» (las 5 operaciones); `production-source` → «la cabecera Authorization solo se construye en lib/api-client.ts» | Las 4 páginas cargan datos con sesión; sin token, la API respondería 401 |
| Activos con datos reales, `current_stock` e indicadores de nivel | `asset-list-view.tsx`, `asset-table.tsx`, `stock-level-badge.tsx`, `lib/stock-level.ts` | `use-inventory` → «listado de activos: estados» (los 4); Jest `utils/stock-level.test.ts` (umbrales 0, 1, 5, 6 y etiquetas); `production-source` → «cada fila de activos enlaza a registrar una entrada y una salida de ese activo» | F2 y F3: seed con 13/0/0/7/15/0; NXV-PER-001 con 3 y «Bajo» en ámbar tras una entrada |
| La entrada envía y muestra confirmación o un error legible en cada resultado | `hooks/use-inbound-form.ts`, `inbound-form.tsx`, `inventory-error.tsx`, `lib/inventory-error-copy.ts` | `inventory-inbound` → «Entrada de activos: envío» (éxito y `formKey`, validación sin petición, 400/404/500/503 con `detail`, 422 con `msg`, red/timeout/ilegible, doble envío); `use-inventory` → «textos de error del inventario» | F3: «Entrada registrada: 3 × Ratón ergonómico (NXV-PER-001)», formulario vacío con errores por campo y ninguna petición |
| La salida muestra el stock del activo elegido, de forma reactiva y antes de enviar | `hooks/use-outbound-form.ts` (`selectAsset`, abort y contador), `outbound-form.tsx` (`ReadOnlyField` «Stock actual») | `inventory-outbound` → «stock: valor mostrado y Cantidad» (lectura al elegir, A → B con abort, servicio que ignora la cancelación, A → B → A, fallo, sin activo); `production-source` → «salida: selector compartido, Stock actual antes que Cantidad…» | F4: «3 · Bajo» antes de la cantidad; 13 al cambiar a NXV-IT-001 y 3 al volver |
| Advertencia en el cliente si la cantidad supera el stock | `lib/stock-check.ts` → `exceedsStock`; contenedor `aria-live` en `outbound-form.tsx` | Jest `utils/stock-check.test.ts`; `inventory-outbound` → «advertencia de stock» (aparece; no bloquea el envío); `production-source` → «salida: Cantidad espera al stock, advertencia sin bloqueo…» | F4: consumo de 5 con stock 3 → advertencia visible |
| Un 400 de la salida muestra el mensaje de la API en la interfaz | `services/inventory.service.ts` (`insufficient_stock` → `quantity`), `FieldMessages` con `role="alert"` bajo Cantidad | `inventory.service` → «400 insufficient_stock: el detail de la API, junto a la cantidad»; `inventory-outbound` → «400 insufficient_stock: el detail junto a Cantidad, sin aviso general, y se vuelve a leer el stock» | F4: «Insufficient stock for asset 'Ratón ergonómico'. Available: 3, requested: 5.» bajo Cantidad |
| El historial muestra todas las órdenes con distinción entrada/salida, nombre, cantidad, fecha y `user_uuid` | `hooks/use-inventory-orders.ts`, `order-table.tsx`, `order-type-badge.tsx`, `lib/order-format.ts` | Jest `utils/order-format.test.ts` (insignias distintas, fecha local, detalle); `use-inventory-orders` (los 4 estados, carreras); `production-source` → «historial: las columnas del brief…», «historial: de solo lectura, sin acciones de editar ni borrar» | F5: 9 órdenes, insignias distintas, fecha en español y el `user_uuid` completo en todas; sin botones |
| Las 4 páginas redirigen al login sin sesión | Guard global de AUTH-02 (`components/auth/auth-guard.tsx`); las rutas no están en `PUBLIC_PATHS` ni en `OPEN_PATHS` | `inventory-contract` → «rutas del inventario» → «sin sesión, las cuatro redirigen al login; con sesión, se muestran»; Jest `auth/auth-routes.test.ts` («the inventory page %s redirects to the login…», las 5 rutas con `/inventory`) | F2 (agente) y F5 (usuario): sin sesión → `/login` |
| Nombres de entidades y etiquetas del BRIEFING | `types/inventory.ts`; títulos y etiquetas del CONTEXT («Activos», «Entrada de activos», «Salida de activos», «Asignación», «Consumo», «Oficina», «Proveedor», «Asignado a», «Stock actual») | `inventory-contract` → «vocabulario del inventario = CONTEXT y backend»; `production-source` → «la UI del inventario usa el vocabulario del CONTEXT («activos», no «productos»)», «el selector de activo muestra «nombre — SKU (oficina)», nunca el id» | F3–F5: selector con las 6 opciones «nombre — SKU (oficina)», sin ids |

## Decisiones y ajustes

### Decisiones del plan (D1–D10, 2026-10-19)

| | Decisión | Estado final |
|---|---|---|
| D1 | Rutas en la raíz del backoffice (`/inventory/...`, no `/backoffice/inventory/...`); quinta pieza en «Alcance actual» de `CLAUDE.md` | Hecho. **Ajuste (F2):** en vez de cuatro enlaces en la cabecera, uno solo, «Inventario», activo en todo `/inventory`, y una subnavegación común a las 4 páginas |
| D2 | `services/inventory.service.ts` sobre `lib/api-client.ts`; `unknown` solo en los normalizadores; vocabulario como excepción documentada con test de contrato | Hecho |
| D3 | `NEXT_PUBLIC_INVENTORY_API_URL`, perezosa; error de configuración en la UI sin romper el build | Hecho, con una segunda instancia de `createApiClient` (`lib/inventory-api-client.ts`) y **sin reserva** a `NEXT_PUBLIC_API_URL` |
| D4 | Errores: el `detail` de la API en 400/404/409; 422 por campo; textos fijos en 5xx, red, timeout o respuesta ilegible; 401 como siempre | **Ajustes:** (1) los 4xx (salvo 401 y 422) **y los 5xx** con un `detail` de texto muestran ese `detail` bajo un título en español; sin cuerpo legible, textos fijos. (2) 422, **opción 3**: texto propio en español por campo y, debajo, el `msg` de la API (sin `Value error, `, no vacío, hasta 300 caracteres) |
| D5 | Selector «nombre — SKU (oficina)»; oficina del activo, en solo lectura, enviada; números; `?asset_id=`; salida con stock reactivo, advertencia que no bloquea y stock leído de nuevo; `formKey` | Hecho. **Ajustes:** Oficina y Stock actual como **valor de solo lectura** (`<output>` sin borde de campo, F3); tras el éxito, el formulario limpio **conserva el activo del enlace** (`formInitialAssetId`); Cantidad deshabilitada hasta conocer el stock (o hasta que falle su lectura, con aviso); tras un 400 de stock, el stock también se vuelve a leer |
| D6 | Nivel de stock: 0 Agotado, 1–5 Bajo, más de 5 Suficiente, con texto o icono además del color, en una función pura documentada | Hecho (`lib/stock-level.ts`) |
| D7 | Vocabulario del CONTEXT en títulos y etiquetas; valores tal como los da la API; historial con etiqueta e icono por tipo y fecha local | Hecho. Tipo de salida con radios «Asignación» / «Consumo», que envían `allocation` / `consumption` |
| D8 | Sin dependencias nuevas; `node:test` y Jest; sin renderizador de React | Hecho |
| D9 | Rama desde `origin/main` (`8e5448e`); memory-bank sincronizado con la PR #21; fases revisadas; sin coautoría | Hecho: F1 `0e0f133`, F2 `72bd839` (más `2dccef0`, un `style(api)`), F3 `064a569`, F4 `a591686`, F5 `0fa0da3` |
| D10 | Pruebas manuales contra el Supabase del usuario; restaurar la demo al terminar; nunca borrar sin decirlo | Las pruebas reales las hizo el usuario; el agente probó en el navegador integrado con un `fetch` falso, sin tocar la API ni Supabase. La restauración de la demo queda para el cierre, con confirmación del usuario |

## Lo que no está verificado

- **Componentes de React sin tests de render.** Por D8 no hay renderizador: los componentes se validan con `tsc`, `lint`, `build`, las reglas estáticas de `production-source` y el navegador. La lógica (reducers, sesiones, formato y validación) sí tiene tests.
- **Las comprobaciones del agente en el navegador fueron con datos simulados.** En F3–F5, el agente usó un `fetch` falso dentro de la página (sin la API real ni Supabase). Las pruebas con datos reales las hizo el usuario.
- **Lectores de pantalla.** `aria-live`, `role="alert"`, `role="status"` y `<output>` están puestos y comprobados en el DOM, pero no se han escuchado con NVDA, JAWS ni VoiceOver.
- **Sesión que caduca en mitad del uso.** El 401 → sesión caducada está probado en el servicio y en el guard (AUTH-02), pero no se ha forzado a mano en una página del inventario.
- **Falta de `NEXT_PUBLIC_INVENTORY_API_URL` en el navegador.** Cubierta por tests (error de configuración sin petición), no comprobada a mano.
- **Zonas horarias.** En el navegador solo se vio `Europe/Madrid`; Jest comprueba también `America/New_York` y el cambio de día.
- **Navegadores.** Solo Chromium (el del usuario y el integrado), en Windows.
- **Stock desactualizado entre la lectura y el envío.** La advertencia usa el stock leído; si otra persona cambia el stock entretanto, decide la API (400). No hay refresco periódico.
- **Revisión de decisiones.** D1–D10 y los ajustes son decisiones del usuario; no las han revisado el tech lead ni la CTO.
