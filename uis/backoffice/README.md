# Backoffice

Panel administrativo interno de **Nexova Solutions**. Tiene cinco piezas de negocio: la portada con la ficha de la empresa, el **análisis de incidentes de soporte** (`/incidents`), el **directorio de proveedores** (`/suppliers`), el **gestor centralizado de incidencias** (`/incident-manager`, `/incident-manager/new`) y el **inventario de equipos y materiales** (`/inventory/*`), todas protegidas por sesión (AUTH-02): `/login`, `/register` y `/account/profile`.

## Vistas

### `/` — portada

- Una ficha de empresa (`lib/company.ts` → `NEXOVA_COMPANY`) con datos reales de Nexova: nombre, año de fundación, sede, oficina de expansión, empleados, facturación aproximada, CEO y líneas de negocio. Cada campo está respaldado literalmente por `contexts/CONTEXT.md` (ver los comentarios en `lib/company.ts` para la frase exacta) y resumido en [`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md) — `contexts/` es una carpeta local que no viaja con el repositorio (`.gitignore`), así que ese segundo archivo es la referencia disponible para quien clone el repo sin ella.
- Una lista de áreas internas de Nexova (RRHH, Ventas, Dirección Ejecutiva) descritas en ese mismo briefing que todavía no tienen herramienta propia en este monorepo — marcada explícitamente como roadmap, no como funcionalidad implementada.

### `/incidents` — análisis de incidentes de soporte

Fase 3 del procesador de incidentes de Nexova (Atención al Cliente — Roberto Díaz). Permite elegir el CSV de tickets de soporte, analizarlo, ver las métricas (totales, 7 reglas de invalidación, categorías, estados, satisfacción) y descargar `results.csv` (`metric,value`).

- **API consumida** ([`services/api`](../../services/api/README.md), contrato en [`SPECS.md`](../../services/api/SPECS.md)): `POST /api/incidents/analyze` y `GET /api/incidents/results/export`, directamente desde el navegador (CORS de la API). Todo el análisis lo hace el backend; el frontend no replica reglas de negocio.
- **Requisitos funcionales:** [`docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`](../../docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md) (describe un script; la interfaz web es decisión del tech lead).
- **Límite de tamaño:** el límite real lo impone la API: **1048576 bytes (1 MiB) sobre el body HTTP completo** (CSV + cabeceras multipart), configurable en el servidor con `MAX_UPLOAD_BYTES`. La comprobación del navegador (extensión `.csv` y tamaño ≤ 1 MiB − 4 KiB) es solo **orientativa** para avisar antes de subir; el backend es la autoridad y su 413 siempre se trata. El texto de la interfaz dice "aproximadamente 1 MiB".
- **Exportación:** va ligada al análisis mostrado (se comprueba `X-Analysis-Id`). Si llega un análisis nuevo mientras se exporta el anterior, esa descarga se cancela; si el análisis nuevo falla, la del anterior termina.
- **Privacidad:** el frontend **no lee ni muestra el contenido del CSV** (el archivo se envía tal cual; no hay `FileReader`, `file.text()` ni vista previa) y nunca muestra `customer_email` ni datos de filas: solo nombre y tamaño del archivo, las métricas agregadas y mensajes de error fijos. No hay logs ni persistencia en el navegador, y nada se envía a servicios externos.
- **Requiere sesión** (AUTH-02): la API exige el JWT; sin sesión la vista redirige a `/login`.

### `/suppliers` — directorio de proveedores

Registro oficial de proveedores de Nexova (Patricia Solís, HR Manager). Requisitos: [`docs/ligthweight-storage-api.md`](../../docs/ligthweight-storage-api.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte B. Se abre desde el enlace **«Proveedores»** de la cabecera (o en `http://localhost:3000/suppliers`).

- Listado cargado de `GET /suppliers` con nombre, país, categorías, tarifa mensual y moneda (con la fecha de su última actualización), renovación y estado.
- Filtros por país y categoría, combinables, que piden a la API el listado filtrado sin recargar la página.
- Alta con formulario (`POST /suppliers`): valida en cliente los campos requeridos y muestra por campo los errores 422 de la API (p. ej. moneda incoherente con el país).
- Cambio de tarifa (`PATCH /suppliers/{id}/rate`) y activar/suspender (`PATCH /suppliers/{id}/status`) en cada fila; la respuesta de la API se refleja al momento.
- Badges `active` / `suspended` (color + símbolo). Las renovaciones de los próximos 60 días (fecha local del navegador) se destacan con un borde lateral y la etiqueta «Renueva en N días»; de los 15 proveedores del seed, 10 tienen fecha de renovación (todas ya pasadas) y 5 no tienen fecha, así que ninguno aparece como renovación próxima: solo se ve con proveedores registrados con una fecha próxima.
- **Sin botón de eliminar**: el endpoint `DELETE` existe en la API, pero los proveedores se suspenden, no se borran.
- Necesita la API en marcha y, para ver datos, el seeder ejecutado (`docker compose exec api python -m app.seed`, ver [`docs/local-development.md`](../../docs/local-development.md)).

### `/incident-manager` y `/incident-manager/new` — gestor centralizado de incidencias

Registro estructurado de incidencias técnicas y operativas de Nexova. Requisitos: [`docs/centralized-incident-manager.md`](../../docs/centralized-incident-manager.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte E. Se abre desde **«Incidencias»** y **«Registrar incidencia»** en la cabecera. No es `/incidents` (el analizador del CSV).

- **`/incident-manager`**: el **resumen** arriba (totales por estado, categoría, origen y sede, de `GET /api/incidents/summary`) y el **listado** debajo (`GET /api/incidents`), con filtros por estado, origen y sede enviados a la API. El listado distingue cargando, error con «Reintentar», vacío (mensaje, sin tabla) y con datos. Cada incidencia se puede avanzar en su ciclo de vida desde su fila (`PATCH /api/incidents/{id}/status`): solo se ofrecen las transiciones válidas (`open` → `in_progress`/`discarded`; `in_progress` → `resolved`/`discarded`; los finales no tienen selector). El cambio es optimista: si la API lo rechaza o falla la red, la fila vuelve a su estado anterior y muestra el aviso. Tras un cambio correcto el resumen se recarga. El resumen y el listado cargan y fallan por separado.
- **`/incident-manager/new`**: título (máx. 120 caracteres, con contador), descripción, categoría, origen, sede (siempre visible y obligatoria, con las etiquetas del CONTEXT; se resalta con borde, fondo y un texto de ayuda cuando el origen es `branch`) y estado en solo lectura (`open`). Valida en cliente antes de enviar (sin petición si falta algo). Durante el envío, spinner y botón deshabilitado; los errores de la API se muestran en español junto a su campo (nunca el texto del servidor); tras el éxito, confirmación y formulario limpio.
- Valores literales del dominio (en inglés) salvo las sedes, que usan sus nombres del CONTEXT.
- Necesita la API en marcha; para ver datos históricos, el seed del CSV (`scripts/seed_incidents.py`, ver [`services/api/README.md`](../../services/api/README.md)).
- Guía de revisión de todo el proyecto (API, seed, UI, suites y trazabilidad): [`docs/centralized-incident-manager-review.md`](../../docs/centralized-incident-manager-review.md).

### `/inventory/*` — inventario de equipos y materiales

Interfaz del inventario del Hito 5 para el personal de operaciones: consultar el stock, registrar entregas y salidas y revisar el historial. Brief: [`docs/inventory-frontend-brief.md`](../../docs/inventory-frontend-brief.md); contexto: [`docs/context-nexova-gestion-inventario-hito-5.md`](../../docs/context-nexova-gestion-inventario-hito-5.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte F. Se abre desde **«Inventario»** en la cabecera; una subnavegación lleva a las cuatro páginas (`/inventory` redirige a Activos).

- **`/inventory/products` (Activos)**: `GET /inventory/products`. Nombre, SKU, categoría, oficina y Stock actual con su nivel (0 «Agotado», de 1 a 5 «Bajo», más de 5 «Suficiente»; color, icono y texto). Cada fila enlaza a registrar una entrada o una salida de ese activo (`?asset_id=`).
- **`/inventory/orders/inbound` (Entrada de activos)**: `POST /inventory/orders/inbound`. Selector «nombre — SKU (oficina)», Oficina del activo en solo lectura, Cantidad y Proveedor. Validación en cliente sin petición; tras el éxito, «Entrada registrada: N × nombre (SKU)» y formulario limpio con el activo del enlace.
- **`/inventory/orders/outbound` (Salida de activos)**: `POST /inventory/orders/outbound`. Al elegir un activo se lee su stock (`GET /inventory/products/{id}`) y se muestra antes de la cantidad; Cantidad espera a conocerlo. Asignación (con «Asignado a») o Consumo. Una cantidad mayor que el stock avisa sin bloquear; el 400 de stock insuficiente aparece bajo Cantidad con el mensaje de la API. Tras el envío, el stock se vuelve a leer.
- **`/inventory/orders` (Historial)**: `GET /inventory/orders`, de solo lectura, la más reciente primero: tipo (Entrada/Salida), activo, cantidad, oficina, detalle, fecha local y `user_uuid`.
- **Errores:** un 4xx/5xx con `detail` muestra ese mensaje de la API bajo un título en español; los 422, un texto propio por campo con el mensaje de la API debajo; red, timeout o respuesta ilegible, textos fijos con «Reintentar».
- Necesita la API en marcha con `DATABASE_URL` y, para ver datos, el seed (`docker compose exec api python -m app.modules.inventory.seed --email <usuario>`; ver [`services/api/README.md`](../../services/api/README.md#inventario-hito-5)).
- **Prueba manual** (las 4 páginas, paso a paso) y trazabilidad con el brief: [`docs/inventory-frontend-review.md`](../../docs/inventory-frontend-review.md).

### Autenticación — `/login`, `/register`, `/account/profile` (AUTH-02)

Contexto: [`docs/auth-frontend.md`](../../docs/auth-frontend.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte C.

- **`/login`**: email y contraseña → `POST /auth/login`. Si es correcto, el JWT se guarda en `localStorage` y se va a `/`; si no, un mensaje claro ("Email o contraseña incorrectos") y no se guarda nada.
- **`/register`**: email, contraseña y, opcionalmente, nombre, teléfono y dirección → `POST /users` y después `POST /auth/login` con las mismas credenciales. Los errores de la API (422, email ya registrado) se muestran junto a su campo.
- **`/account/profile`**: email (del `User`) y nombre, teléfono y dirección (del `Profile`) desde `GET /auth/me`; editar nombre y contacto con `PUT /profiles/me` (un campo vacío borra ese dato).
- **Protección de rutas**: todas las vistas salvo `/login` y `/register` exigen sesión. Un guard en el layout raíz valida el token con `GET /auth/me` y redirige a `/login` si no hay token o la API responde 401 (el token se elimina). Toda llamada protegida lleva `Authorization: Bearer <token>`.
- **Cerrar sesión** (cabecera): elimina el token y vuelve a `/login`.
- Para crear la primera cuenta basta con `/register` (rol `user`); los admins se crean con `docker compose exec api python -m app.auth.create_admin` (ver [`services/api/README.md`](../../services/api/README.md#primer-administrador)).

### Contraseñas — `/forgot-password`, `/reset-password`, `/account/change-password` (AUTH-03)

Contexto: [`docs/auth-password-reset.md`](../../docs/auth-password-reset.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte D.

- **`/login`** tiene el enlace "¿Olvidaste tu contraseña?" y, al volver de un restablecimiento (`/login?reset=success`), un aviso de éxito.
- **`/forgot-password`** (sin sesión): email → `POST /auth/forgot-password`. Tras enviarlo, el formulario se desactiva y muestra siempre "Si esa dirección está registrada, recibirás un enlace en breve".
- **`/reset-password`** (con o sin sesión): abre el enlace del email (`?token=…`), pide la contraseña nueva y su confirmación → `POST /auth/reset-password` → `/login` con aviso. Si el token falta, no es válido, caducó o ya se usó: error claro y enlace a `/forgot-password`.
- **`/account/change-password`** (con sesión; enlace en `/account/profile`): contraseña actual, nueva y confirmación (deben coincidir antes de llamar a la API) → `POST /auth/change-password`; muestra el éxito o el error junto a su campo.
- El email lo envía `services/api` con Resend: requiere `RESEND_API_KEY`, `EMAIL_FROM` y `PASSWORD_RESET_URL=http://localhost:3001/reset-password` en el `.env` de la raíz (ver su `.env.example`).

## Stack técnico

Mismo stack que [`uis/talent-pipeline-tracker`](../talent-pipeline-tracker/README.md), decisión registrada en [`memory-bank/techContext.md`](../../memory-bank/techContext.md): Next.js 16 (App Router), React 19, TypeScript estricto, Tailwind CSS v4 (`@import "tailwindcss"` en `app/globals.css`, sin `tailwind.config.ts`). Sin librerías de estado externas y sin dependencias añadidas para `/incidents`, `/suppliers`, `/incident-manager` ni `/inventory`.

## Puesta en marcha

**Desde el ticket #infra-40, el backoffice se arranca con Docker**, junto con el website y la API, desde la raíz del monorepo:

```bash
cp .env.example .env    # una sola vez, en la raíz: rellenar JWT_SECRET_KEY y DATABASE_URL
docker compose up -d    # backoffice en http://localhost:3001 (website en el 3000, API en el 8000)
```

Guía completa (requisitos, logs, cuándo reconstruir, comandos de seed y problemas conocidos): [`docs/local-development.md`](../../docs/local-development.md). Para ver proveedores, el seeder ejecutado (`docker compose exec api python -m app.seed`); para el inventario, `DATABASE_URL` y `seed-inventory` (ver [`services/api/README.md`](../../services/api/README.md#inventario-hito-5)).

| Variable (en el `.env` de la raíz) | Valor con Docker | Uso |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `/backend` | URL base de `services/api` que usa el navegador: la ruta `/backend` del propio backoffice. Se incorpora al JavaScript al arrancar `next dev` (`NEXT_PUBLIC_*`). Si falta, `/incidents` y `/suppliers` muestran un error de configuración al usarlas; el build no falla |
| `NEXT_PUBLIC_INVENTORY_API_URL` | `/backend` | URL base de la API del inventario (el servicio añade `/inventory/...`). La pide el brief. **Sin reserva** a `NEXT_PUBLIC_API_URL`: si falta, las páginas del inventario muestran un error de configuración; el build no falla |
| `API_INTERNAL_URL` | `http://api:8000` | Solo de servidor (sin `NEXT_PUBLIC_`): destino del rewrite de `/backend/*` en `next.config.ts`, por el nombre del servicio en la red de Docker. Sin ella no hay rewrite |
| `WATCHPACK_POLLING` | `true` | Recarga de `next dev --webpack` con el código montado desde Windows |

Tras cambiar una de estas variables: `docker compose up -d ui`. Con Docker, el backoffice llama a la API por su mismo origen (`/backend`): no necesita CORS. El Talent Pipeline Tracker, fuera de Docker, usa el **3002**.

`.env.example` (de esta carpeta) ya no se usa para arrancar: la plantilla es el [`.env.example`](../../.env.example) de la raíz.

## Validación

Los casos de error y su verificación manual (auditoría de gestión de errores) están en [`docs/error-handling-audit.md`](../../docs/error-handling-audit.md) §7.4.

Desde `uis/backoffice`:

```bash
npx tsc --noEmit
npm run lint
npm run build
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"
```

Los tests (`tests/*.test.mjs`) usan el runner nativo de Node 24, sin dependencias: normalizadores, cliente HTTP, servicios de incidentes, proveedores, gestor de incidencias y autenticación, estado/sesión de los hooks (cancelación, carreras, exportación, recarga tras cambios, sesión, login/registro y perfil), token en `localStorage`, cabecera Bearer y 401, protección de rutas, vocabulario y renovaciones de proveedores contra el CONTEXT, vocabulario, etiquetas de sede y transiciones del gestor contra su CONTEXT, envío/listado/reversión optimista/resumen del gestor, y una revisión estática del código de producción. Esa revisión comprueba: sin `any`; `unknown` solo en `services/normalizers.ts`; `fetch`, `JSON.stringify` y `Authorization` solo en `lib/api-client.ts`; `localStorage` solo en `lib/auth-token.ts`; sin lectura del archivo; sin borrado de proveedores; existen `app/error.tsx`, `app/global-error.tsx` y `app/not-found.tsx`, que no leen el error y enlazan a inicio; y ningún texto de la UI muestra detalles técnicos. Del inventario cubren: el vocabulario contra el CONTEXT y el backend; el servicio (Bearer, números y oficina del activo en el body, y todos los errores); los hooks de Activos, Entrada, Salida (stock reactivo, carreras, advertencia sin bloqueo, nueva lectura del stock) e Historial; y reglas estáticas (sin `fetch` en los componentes, selector sin id, Oficina y Stock en solo lectura, columnas del historial y ninguna acción de editar ni borrar). `tests/support/resolve-alias.mjs` resuelve el alias `@/` para Node sin tocar `tsconfig.json`. El aviso `MODULE_TYPELESS_PACKAGE_JSON` se silencia porque `package.json` no declara `"type"`.

**Jest (AUTH-088 y FE-019):** `npm run test:jest` ejecuta con cobertura los tests de `__tests__/**/*.test.ts`. `__tests__/auth/` cubre la lógica TypeScript de autenticación: token en `localStorage`, protección de rutas, servicio de auth, normalizadores de auth y estado de la sesión. `__tests__/utils/` cubre los límites de las utilidades del frontend: renovaciones de proveedores, tarifa, validación de los formularios de proveedores, del gestor y del inventario, textos de error, nivel de stock, advertencia de la salida y formato del historial. La configuración está en `jest.config.mjs` (entorno `node`, alias `@/` y ts-jest en CommonJS). Jest no recoge `tests/*.test.mjs`, que siguen con `node:test`. Plan, cobertura medida y por qué no hay generación ni decodificado de tokens ni hash en TypeScript: [`services/api/TESTING.md`](../../services/api/TESTING.md) §10 y §12.

La unión con React (montaje/desmontaje), la descarga real y los flujos de autenticación (login, registro, perfil, redirecciones, logout) se validan manualmente en el navegador.

## Estructura

```text
app/
├── layout.tsx                  # layout raíz: sesión, cabecera (navegación/logout) y guard global de rutas
├── login/page.tsx              # /login (pública)
├── register/page.tsx           # /register (pública)
├── account/profile/page.tsx    # /account/profile
├── account/change-password/page.tsx # /account/change-password (AUTH-03)
├── forgot-password/page.tsx    # /forgot-password (pública, AUTH-03)
├── reset-password/page.tsx     # /reset-password (abierta: enlace del email, AUTH-03)
├── page.tsx                    # portada: ficha de empresa + roadmap
├── incidents/page.tsx          # /incidents: Server Component (metadata) que renderiza la vista cliente
├── suppliers/page.tsx          # /suppliers: Server Component (metadata) que renderiza el directorio
├── incident-manager/page.tsx   # /incident-manager: resumen + listado del gestor de incidencias
├── incident-manager/new/page.tsx # /incident-manager/new: formulario de registro
├── inventory/                  # layout con la subnavegación; /inventory → /inventory/products
│   ├── products/page.tsx       # Activos
│   ├── orders/page.tsx         # Historial
│   ├── orders/inbound/page.tsx # Entrada de activos (lee ?asset_id=)
│   └── orders/outbound/page.tsx # Salida de activos (lee ?asset_id=)
└── globals.css                 # Tailwind v4 + paleta y tokens semánticos compartidos con talent-pipeline-tracker

components/
├── ui/                         # primitivas: button, loading-spinner, alert, nav-link, input
├── auth/                       # sesión, guard, navegación de cuenta, login, registro, perfil y contraseñas
├── incidents/                  # vista cliente (incident-analysis-view) + componentes presentacionales
├── suppliers/                  # vista cliente (supplier-directory-view) + filtros, tabla, formulario, badges
├── incident-manager/           # vistas cliente (board, form) + resumen, filtros, tabla, formulario, errores
└── inventory/                  # vistas cliente (activos, entrada, salida, historial) + selector, tablas, insignias, valores de solo lectura

hooks/use-incident-analysis.ts  # estado de /incidents: reducer + sesión (cancelación, carreras, exportación)
hooks/use-supplier-directory.ts # estado de /suppliers: reducer + sesión (filtros, alta, tarifa, estado, carreras)
hooks/use-incident-board.ts     # listado del gestor: filtros, cuatro estados, cambio de estado optimista
hooks/use-incident-summary.ts   # resumen del gestor (carga y error propios)
hooks/use-incident-form.ts      # envío del formulario del gestor (formKey para limpiarlo)
hooks/use-auth-session.ts       # sesión: token de localStorage + validación con GET /auth/me
hooks/use-auth-form.ts          # envío de /login, /register y los formularios de contraseña
hooks/use-profile.ts            # /account/profile: GET /auth/me + PUT /profiles/me
hooks/use-inventory-assets.ts   # Activos (también el selector de los formularios)
hooks/use-inbound-form.ts       # envío de la entrada (formKey)
hooks/use-outbound-form.ts      # activo elegido, stock reactivo y envío de la salida
hooks/use-inventory-orders.ts   # Historial
services/
├── incidents.service.ts        # frontera HTTP de incidentes (prevalidación UX, mapeo de errores, export)
├── suppliers.service.ts        # frontera HTTP de proveedores (campos requeridos, body, 422 por campo)
├── incident-manager.service.ts # frontera HTTP del gestor (validación en cliente, 400 → textos propios por campo)
├── auth.service.ts             # login, registro, usuario actual, perfil y contraseñas (services/api Partes C y D)
├── inventory.service.ts        # único módulo que llama a /inventory (validación, body, errores)
└── normalizers.ts              # única frontera con `unknown` de red
lib/
├── api-client.ts               # cliente HTTP genérico (timeout, errores tipados, Bearer y 401, sin credentials)
├── auth-token.ts               # JWT en localStorage (único uso de localStorage)
├── auth-routes.ts              # rutas públicas/abiertas y decisión del guard
├── supplier-renewal.ts         # renovaciones en los próximos 60 días (presentación)
├── incident-manager-routes.ts  # rutas del gestor de incidencias
├── inventory-api-client.ts     # el mismo cliente con NEXT_PUBLIC_INVENTORY_API_URL
├── inventory-routes.ts         # rutas del inventario y enlaces con ?asset_id=
├── stock-level.ts, stock-check.ts, order-format.ts # nivel de stock, advertencia de la salida y formato del historial
├── asset-preselection.ts, inventory-form-errors.ts, inventory-error-copy.ts # preselección, reparto de errores y textos
└── company.ts                  # datos de Nexova, cada campo citado desde contexts/CONTEXT.md
types/incidents.ts              # contrato que recibe el frontend (incidentes)
types/suppliers.ts              # contrato y vocabulario del directorio de proveedores
types/incident-manager.ts       # contrato, vocabulario, etiquetas de sede y transiciones del gestor
types/auth.ts                   # contrato de autenticación y perfil
types/inventory.ts              # contrato y vocabulario del inventario
tests/                          # tests node --test (.mjs) + support/

.env.example                    # variables de entorno documentadas (sin secretos)
```

## Documentación relacionada

- [`CLAUDE.md`](./CLAUDE.md) — restricciones vigentes para este subproyecto, incluidas las de `/incidents` y `/inventory`.
- [`docs/inventory-frontend-review.md`](../../docs/inventory-frontend-review.md) — guía de revisión del inventario: arranque, recorrido de las 4 páginas, trazabilidad con el brief y lo que no está verificado.
- [`memory-bank/techContext.md`](../../memory-bank/techContext.md) — por qué este proyecto usa Next.js en vez del HTML estático de `uis/website`, y decisiones técnicas de `/incidents`.
- [`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md) — resumen versionado del briefing de Nexova (el original, `contexts/CONTEXT.md`, es local y no viaja con el repositorio).
