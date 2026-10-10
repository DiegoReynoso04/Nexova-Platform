# Talent Pipeline Tracker

Panel interno de gestión de candidaturas para **Nexova Solutions** (Operaciones de Selección). Permite visualizar, filtrar, registrar y hacer seguimiento del flujo de selección de candidatos consumiendo directamente la API REST pública `/tracker/api/v1`.

> Proyecto académico (milestone de 4Geeks Academy — AI Engineering). La empresa "Nexova Solutions" es ficticia; la API consumida es real y compartida entre distintos alumnos.

## Qué hace la aplicación

- **Listado de candidaturas** (`/`): tabla/tarjetas responsive con nombre, puesto, estado y etapa de cada candidato. Incluye filtro por estado, filtro por etapa, búsqueda por nombre o email (con debounce) y paginación. Distingue claramente "sin resultados" de "error al cargar", y descarta respuestas de búsquedas obsoletas si llegan fuera de orden.
- **Detalle de candidatura** (`/candidates/[id]`): muestra todos los datos del candidato (contacto, puesto, experiencia, LinkedIn/CV, fechas). Los enlaces a LinkedIn/CV solo se renderizan como link si son URLs http(s) válidas; si no, se muestra el texto plano. Un `id` inexistente cae en una página `not-found` dedicada.
- **Cambio rápido de estado y etapa**: dos selectores en el detalle que actualizan `status`/`stage` mediante `PATCH`, con actualización optimista (`useOptimistic`) y reversión visible si la petición falla.
- **Alta y edición de candidaturas**: un único formulario, en un modal (`<dialog>` nativo), reutilizado para crear (`POST`) y editar (`PUT`). Valida en cliente antes de enviar y mapea los errores `422` de la API al campo correspondiente.
- **Notas por candidato**: listar, añadir y eliminar notas de texto libre asociadas a una candidatura, con confirmación antes de borrar.
- **Notificaciones**: cada alta, edición, cambio de estado/etapa o nota (crear/borrar) muestra un toast de éxito o error, accesible mediante regiones `aria-live`.
- **Manejo de errores robusto**: errores de validación (422), recurso no encontrado (404), otros errores HTTP, errores de red y timeouts (20 s) se distinguen entre sí y siempre producen un mensaje legible — nunca un fallo silencioso ni un spinner infinito.

- **Sesión de usuario (AUTH-02)**: `/login`, `/register` y `/account/profile` contra `services/api` de Nexova (no contra la API de candidaturas). Todas las demás vistas exigen sesión: sin token, o si `services/api` responde 401, se vuelve a `/login`. "Cerrar sesión" en la cabecera elimina el token. Detalle en `SPECS.md` §9.
- **Contraseñas (AUTH-03)**: "¿Olvidaste tu contraseña?" en `/login` → `/forgot-password` (enlace por email), `/reset-password` (contraseña nueva desde el enlace) y `/account/change-password` (con sesión, enlace en el perfil). Detalle en `SPECS.md` §9.4.

Lo que la aplicación **no** hace, a propósito: no permite eliminar candidaturas (el endpoint existe en la API pero queda fuera de alcance de esta versión). La API de candidaturas de 4Geeks no requiere autenticación y nunca recibe el token de sesión.

## Stack técnico

- [Next.js 16](https://nextjs.org) (App Router), Client Components únicamente — no hay Server Actions ni Route Handlers: la aplicación consume la API directamente desde el navegador (CORS lo permite).
- [React 19](https://react.dev) con hooks nativos (`useState`, `useReducer`, `useContext`, `useOptimistic`) — sin librerías externas de gestión de estado.
- TypeScript en modo estricto, sin `any`.
- Tailwind CSS v4 (configuración vía `@import "tailwindcss"` en `app/globals.css`, sin `tailwind.config.ts`).

## Puesta en marcha

Requisitos: Node.js 20 o superior.

```bash
npm install
```

Crea un archivo `.env.local` en la raíz del proyecto con las URL base de las dos APIs:

```bash
NEXT_PUBLIC_API_URL=https://playground.4geeks.com/tracker/api/v1
NEXT_PUBLIC_AUTH_API_URL=http://localhost:8000
```

La aplicación falla al arrancar con un error explícito si alguna de las dos no está definida. Para iniciar sesión hace falta `services/api` en marcha (ver su README) con `http://localhost:3001` en `CORS_ALLOWED_ORIGINS`.

```bash
npm run dev      # servidor de desarrollo en http://localhost:3001 (el 3000 es del backoffice)
npm run build    # build de producción
npm run start    # sirve el build de producción (puerto 3001)
npm run lint     # ESLint
```

## Validación

Los casos de error y su verificación manual (auditoría de gestión de errores) están en [`docs/error-handling-audit.md`](../../docs/error-handling-audit.md) §7.4.

```bash
npx tsc --noEmit
npm run lint
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"
```

Los tests (`tests/*.test.mjs`, AUTH-02) usan el runner nativo de **Node 24**, sin dependencias: token en `localStorage`, Bearer solo hacia `services/api` (nunca hacia la API de 4Geeks), 401, login/registro/perfil, normalizadores, sesión y protección de rutas. `tests/errors.test.mjs` cubre los textos fijos por tipo de error, el timeout que incluye la lectura del cuerpo, la clasificación del error al guardar una candidatura y el reintento del guard. `tests/production-source.test.mjs` revisa el código: existen los límites de error y la UI no muestra `error.message`, `digest` ni hace `console.*`. `tests/support/resolve-alias.mjs` resuelve el alias `@/`. Los flujos completos (login, registro, perfil, redirecciones, logout) se validan además en el navegador.

`npm run lint` informa hoy de 4 errores `react-hooks/set-state-in-effect` en `hooks/use-notes.ts`, `use-record-detail.ts` y `use-records.ts`, anteriores a AUTH-02 (también en `main`).

## Estructura del proyecto

```text
app/
├── page.tsx                     # listado de candidaturas
├── layout.tsx                   # layout raíz: ToastProvider, sesión, cabecera y guard global de rutas
├── login/page.tsx               # /login (pública)
├── register/page.tsx            # /register (pública)
├── account/profile/page.tsx     # /account/profile
├── account/change-password/page.tsx # /account/change-password (AUTH-03)
├── forgot-password/page.tsx     # /forgot-password (pública, AUTH-03)
├── reset-password/page.tsx      # /reset-password (abierta: enlace del email, AUTH-03)
└── candidates/[id]/
    ├── page.tsx                 # detalle de candidatura
    └── not-found.tsx            # id inexistente (404)

components/
├── candidates/                  # listado, tabla/tarjetas, filtros, paginación,
│                                 # detalle, formulario de alta/edición, controles de estado
├── notes/                       # listado, alta y borrado de notas
└── ui/                          # botón, input, select, badge, spinner, modal, toasts

hooks/
├── use-records.ts               # listado: fetch, filtros, paginación, control de carrera
├── use-record-detail.ts         # detalle: fetch por id
├── use-notes.ts                 # notas: fetch, alta, borrado
└── use-debounce.ts              # debounce del campo de búsqueda

services/
├── records.service.ts           # llamadas a /records
├── notes.service.ts             # llamadas a /records/{id}/notes
└── normalizers.ts                # única frontera donde se maneja `unknown` de red

lib/
├── api-client.ts                # fetch genérico: timeout, errores tipados, parseo de 204/422
└── format.ts                    # formateo defensivo de fechas y valores

types/
├── record.ts                    # RecordOut, RecordCreate, RecordPatch, Note, etc.
├── known-values.ts              # KnownStatus / KnownStage
└── api.ts                       # ValidationError, HTTPValidationError
```

## Decisiones de arquitectura relevantes

- **Frontera de confianza**: todo lo que llega de la red como `unknown` se valida y se convierte a tipos firmes exclusivamente en `services/normalizers.ts`. El resto de la aplicación nunca ve `unknown` ni hace `as` sobre una respuesta de red. Cada endpoint tiene su propio normalizador porque la API usa tres formatos de envoltorio distintos (`GET /records` envuelve en `{ data, total, page, limit }`, `GET /records/{id}/notes` en `{ data, meta: { total } }`, y `POST /records/{id}/notes` devuelve la nota desnuda).
- **Cliente HTTP centralizado** (`lib/api-client.ts`): distingue explícitamente `ValidationApiError` (422, con `detail[]` mapeable a campos), `NotFoundError` (404), `ApiError` genérico (otros códigos), `NetworkError` (fetch rechazado) y `TimeoutError` (sin respuesta en 20 s — el backend corre en un dyno de Heroku que puede tardar en despertar). Un cuerpo `204` nunca se pasa a `.json()`; un cuerpo ilegible (JSON corrupto) se convierte en un error explícito en vez de propagar un `SyntaxError` sin capturar.
- **`<dialog>` nativo para modales**: tanto el formulario de alta/edición como la confirmación de borrado de una nota usan el elemento `<dialog>` con `showModal()`. El navegador gestiona el atrapado de foco y el cierre con `Escape` de forma nativa, sin JavaScript adicional.
- **Reconciliación de `notes_count`**: tras crear o borrar una nota, el contador que se muestra sale de `meta.total` (o de la longitud de la lista en memoria), nunca del `notes_count` de `RecordOut`, que queda obsoleto en cuanto cambia el número de notas.
- **`status`/`stage` como `string`, no `enum`**: el contrato OpenAPI los declara como `string`; `KnownStatus`/`KnownStage` documentan los valores conocidos para los selectores sin dejar de aceptar cualquier valor que la API devuelva.

## Documentación del proyecto

Este README describe el funcionamiento general. Las reglas de negocio, el contrato de la API y las restricciones técnicas obligatorias están documentadas con más detalle en:

- [`SPECS.md`](./SPECS.md) — especificación técnica completa: modelos, endpoints, contratos observados de la API y requisitos funcionales (REQ-1 a REQ-6).
- [`CLAUDE.md`](./CLAUDE.md) — restricciones permanentes de stack, tipado y arquitectura para cualquier cambio futuro.

Ante cualquier duda sobre el comportamiento esperado de la aplicación, `SPECS.md` es la fuente de verdad.
