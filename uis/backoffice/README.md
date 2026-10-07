# Backoffice

Panel administrativo interno de **Nexova Solutions**. Tiene cuatro vistas de negocio: la portada con la ficha de la empresa, el **análisis de incidentes de soporte** (`/incidents`), el **directorio de proveedores** (`/suppliers`) y el **gestor centralizado de incidencias** (`/incident-manager`, `/incident-manager/new`), todas protegidas por sesión (AUTH-02): `/login`, `/register` y `/account/profile`.

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
- Necesita la API en marcha y, para ver datos, el seeder ejecutado (`cd services/api && uv run seed`).

### `/incident-manager` y `/incident-manager/new` — gestor centralizado de incidencias

Registro estructurado de incidencias técnicas y operativas de Nexova. Requisitos: [`docs/centralized-incident-manager.md`](../../docs/centralized-incident-manager.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte E. Se abre desde **«Incidencias»** y **«Registrar incidencia»** en la cabecera. No es `/incidents` (el analizador del CSV).

- **`/incident-manager`**: el **resumen** arriba (totales por estado, categoría, origen y sede, de `GET /api/incidents/summary`) y el **listado** debajo (`GET /api/incidents`), con filtros por estado, origen y sede enviados a la API. El listado distingue cargando, error con «Reintentar», vacío (mensaje, sin tabla) y con datos. Cada incidencia se puede avanzar en su ciclo de vida desde su fila (`PATCH /api/incidents/{id}/status`): solo se ofrecen las transiciones válidas (`open` → `in_progress`/`discarded`; `in_progress` → `resolved`/`discarded`; los finales no tienen selector). El cambio es optimista: si la API lo rechaza o falla la red, la fila vuelve a su estado anterior y muestra el aviso. Tras un cambio correcto el resumen se recarga. El resumen y el listado cargan y fallan por separado.
- **`/incident-manager/new`**: título (máx. 120 caracteres, con contador), descripción, categoría, origen, sede (siempre visible y obligatoria, con las etiquetas del CONTEXT; se resalta con borde, fondo y un texto de ayuda cuando el origen es `branch`) y estado en solo lectura (`open`). Valida en cliente antes de enviar (sin petición si falta algo). Durante el envío, spinner y botón deshabilitado; los errores de la API se muestran en español junto a su campo (nunca el texto del servidor); tras el éxito, confirmación y formulario limpio.
- Valores literales del dominio (en inglés) salvo las sedes, que usan sus nombres del CONTEXT.
- Necesita la API en marcha; para ver datos históricos, el seed del CSV (`scripts/seed_incidents.py`, ver [`services/api/README.md`](../../services/api/README.md)).
- Guía de revisión de todo el proyecto (API, seed, UI, suites y trazabilidad): [`docs/centralized-incident-manager-review.md`](../../docs/centralized-incident-manager-review.md).

### Autenticación — `/login`, `/register`, `/account/profile` (AUTH-02)

Contexto: [`docs/auth-frontend.md`](../../docs/auth-frontend.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte C.

- **`/login`**: email y contraseña → `POST /auth/login`. Si es correcto, el JWT se guarda en `localStorage` y se va a `/`; si no, un mensaje claro ("Email o contraseña incorrectos") y no se guarda nada.
- **`/register`**: email, contraseña y, opcionalmente, nombre, teléfono y dirección → `POST /users` y después `POST /auth/login` con las mismas credenciales. Los errores de la API (422, email ya registrado) se muestran junto a su campo.
- **`/account/profile`**: email (del `User`) y nombre, teléfono y dirección (del `Profile`) desde `GET /auth/me`; editar nombre y contacto con `PUT /profiles/me` (un campo vacío borra ese dato).
- **Protección de rutas**: todas las vistas salvo `/login` y `/register` exigen sesión. Un guard en el layout raíz valida el token con `GET /auth/me` y redirige a `/login` si no hay token o la API responde 401 (el token se elimina). Toda llamada protegida lleva `Authorization: Bearer <token>`.
- **Cerrar sesión** (cabecera): elimina el token y vuelve a `/login`.
- Para crear la primera cuenta basta con `/register` (rol `user`); los admins se crean con `uv run create-admin` en `services/api`.

### Contraseñas — `/forgot-password`, `/reset-password`, `/account/change-password` (AUTH-03)

Contexto: [`docs/auth-password-reset.md`](../../docs/auth-password-reset.md); contrato: [`services/api/SPECS.md`](../../services/api/SPECS.md) Parte D.

- **`/login`** tiene el enlace "¿Olvidaste tu contraseña?" y, al volver de un restablecimiento (`/login?reset=success`), un aviso de éxito.
- **`/forgot-password`** (sin sesión): email → `POST /auth/forgot-password`. Tras enviarlo, el formulario se desactiva y muestra siempre "Si esa dirección está registrada, recibirás un enlace en breve".
- **`/reset-password`** (con o sin sesión): abre el enlace del email (`?token=…`), pide la contraseña nueva y su confirmación → `POST /auth/reset-password` → `/login` con aviso. Si el token falta, no es válido, caducó o ya se usó: error claro y enlace a `/forgot-password`.
- **`/account/change-password`** (con sesión; enlace en `/account/profile`): contraseña actual, nueva y confirmación (deben coincidir antes de llamar a la API) → `POST /auth/change-password`; muestra el éxito o el error junto a su campo.
- El email lo envía `services/api` con Resend: requiere `RESEND_API_KEY`, `EMAIL_FROM` y `PASSWORD_RESET_URL=http://localhost:3000/reset-password` en `services/api/.env` (ver su README).

## Stack técnico

Mismo stack que [`uis/talent-pipeline-tracker`](../talent-pipeline-tracker/README.md), decisión registrada en [`memory-bank/techContext.md`](../../memory-bank/techContext.md): Next.js 16 (App Router), React 19, TypeScript estricto, Tailwind CSS v4 (`@import "tailwindcss"` en `app/globals.css`, sin `tailwind.config.ts`). Sin librerías de estado externas y sin dependencias añadidas para `/incidents`, `/suppliers` ni `/incident-manager`.

## Puesta en marcha

Requisitos: Node.js 20 o superior para la app; **Node.js 24** para ejecutar los tests (`node --test` con TypeScript sin dependencias). Para `/incidents`, `/suppliers` y `/incident-manager`, además, la API de `services/api` en marcha (ver su README); para ver proveedores, el seeder ejecutado (`cd services/api && uv run seed`).

```bash
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000 (.env.local está ignorado por git)
npm run dev                  # servidor de desarrollo en http://localhost:3000
npm run build                # build de producción
npm run start                # sirve el build
```

| Variable | Valor local | Uso |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | URL base de `services/api`. Se incorpora al JavaScript **en tiempo de build** (`NEXT_PUBLIC_*`). Si falta, `/incidents` y `/suppliers` muestran un error de configuración al usarlas; el build no falla |

`.env.example` es solo documentación: Next.js no lo carga (solo lee `.env`, `.env.local`, `.env.$(NODE_ENV)` y `.env.$(NODE_ENV).local`).

La API solo acepta los orígenes de `CORS_ALLOWED_ORIGINS` (por defecto `http://localhost:3000`; ver `services/api/README.md`). Si el backoffice arranca en otro puerto porque el 3000 está ocupado, hay que liberar ese puerto o añadir el origen en `CORS_ALLOWED_ORIGINS` de la API. El Talent Pipeline Tracker usa el 3001.

## Validación

Desde `uis/backoffice`:

```bash
npx tsc --noEmit
npm run lint
npm run build
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"
```

Los tests (`tests/*.test.mjs`) usan el runner nativo de Node 24, sin dependencias: normalizadores, cliente HTTP, servicios de incidentes, proveedores, gestor de incidencias y autenticación, estado/sesión de los hooks (cancelación, carreras, exportación, recarga tras cambios, sesión, login/registro y perfil), token en `localStorage`, cabecera Bearer y 401, protección de rutas, vocabulario y renovaciones de proveedores contra el CONTEXT, vocabulario, etiquetas de sede y transiciones del gestor contra su CONTEXT, envío/listado/reversión optimista/resumen del gestor, y una revisión estática del código de producción (sin `any`, `unknown` solo en `services/normalizers.ts`, `fetch`, `JSON.stringify` y `Authorization` solo en `lib/api-client.ts`, `localStorage` solo en `lib/auth-token.ts`, sin lectura del archivo y sin borrado de proveedores). `tests/support/resolve-alias.mjs` resuelve el alias `@/` para Node sin tocar `tsconfig.json`. El aviso `MODULE_TYPELESS_PACKAGE_JSON` se silencia porque `package.json` no declara `"type"`.

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
└── globals.css                 # Tailwind v4 + paleta y tokens semánticos compartidos con talent-pipeline-tracker

components/
├── ui/                         # primitivas: button, loading-spinner, alert, nav-link, input
├── auth/                       # sesión, guard, navegación de cuenta, login, registro, perfil y contraseñas
├── incidents/                  # vista cliente (incident-analysis-view) + componentes presentacionales
├── suppliers/                  # vista cliente (supplier-directory-view) + filtros, tabla, formulario, badges
└── incident-manager/           # vistas cliente (board, form) + resumen, filtros, tabla, formulario, errores

hooks/use-incident-analysis.ts  # estado de /incidents: reducer + sesión (cancelación, carreras, exportación)
hooks/use-supplier-directory.ts # estado de /suppliers: reducer + sesión (filtros, alta, tarifa, estado, carreras)
hooks/use-incident-board.ts     # listado del gestor: filtros, cuatro estados, cambio de estado optimista
hooks/use-incident-summary.ts   # resumen del gestor (carga y error propios)
hooks/use-incident-form.ts      # envío del formulario del gestor (formKey para limpiarlo)
hooks/use-auth-session.ts       # sesión: token de localStorage + validación con GET /auth/me
hooks/use-auth-form.ts          # envío de /login, /register y los formularios de contraseña
hooks/use-profile.ts            # /account/profile: GET /auth/me + PUT /profiles/me
services/
├── incidents.service.ts        # frontera HTTP de incidentes (prevalidación UX, mapeo de errores, export)
├── suppliers.service.ts        # frontera HTTP de proveedores (campos requeridos, body, 422 por campo)
├── incident-manager.service.ts # frontera HTTP del gestor (validación en cliente, 400 → textos propios por campo)
├── auth.service.ts             # login, registro, usuario actual, perfil y contraseñas (services/api Partes C y D)
└── normalizers.ts              # única frontera con `unknown` de red
lib/
├── api-client.ts               # cliente HTTP genérico (timeout, errores tipados, Bearer y 401, sin credentials)
├── auth-token.ts               # JWT en localStorage (único uso de localStorage)
├── auth-routes.ts              # rutas públicas/abiertas y decisión del guard
├── supplier-renewal.ts         # renovaciones en los próximos 60 días (presentación)
├── incident-manager-routes.ts  # rutas del gestor de incidencias
└── company.ts                  # datos de Nexova, cada campo citado desde contexts/CONTEXT.md
types/incidents.ts              # contrato que recibe el frontend (incidentes)
types/suppliers.ts              # contrato y vocabulario del directorio de proveedores
types/incident-manager.ts       # contrato, vocabulario, etiquetas de sede y transiciones del gestor
types/auth.ts                   # contrato de autenticación y perfil
tests/                          # tests node --test (.mjs) + support/

.env.example                    # variables de entorno documentadas (sin secretos)
```

## Documentación relacionada

- [`CLAUDE.md`](./CLAUDE.md) — restricciones vigentes para este subproyecto, incluidas las de `/incidents`.
- [`memory-bank/techContext.md`](../../memory-bank/techContext.md) — por qué este proyecto usa Next.js en vez del HTML estático de `uis/website`, y decisiones técnicas de `/incidents`.
- [`memory-bank/projectbrief.md`](../../memory-bank/projectbrief.md) — resumen versionado del briefing de Nexova (el original, `contexts/CONTEXT.md`, es local y no viaja con el repositorio).
