# Desarrollo local — cómo levantar y probar el sistema completo

Guía de arranque del monorepo para quien llega nuevo. Resume lo imprescindible y enlaza al README de cada aplicación, que es donde está el detalle (no se duplica aquí). La autenticación del frontend se explica en [`auth-frontend.md`](./auth-frontend.md); el contrato HTTP de la API, en [`services/api/SPECS.md`](../services/api/SPECS.md).

## 1. Aplicaciones y puertos

| Aplicación | Qué es | Puerto local | Autenticación | Detalle |
|---|---|---|---|---|
| `uis/website` | Landing pública + formulario de registro de talento (Hito 1) | — (HTML estático, sin build) | **Ninguna**: es pública y no participa en el sistema de sesión | — (se publica en Netlify desde `netlify.toml`) |
| `services/api` | API FastAPI de Nexova: autenticación (`/auth`, `/users`, `/profiles`), incidentes y proveedores | `8000` | Emite y exige el JWT | [`services/api/README.md`](../services/api/README.md) |
| `uis/backoffice` | Panel interno: `/incidents`, `/suppliers`, cuenta | `3000` | Sesión obligatoria (salvo `/login` y `/register`) | [`uis/backoffice/README.md`](../uis/backoffice/README.md) |
| `uis/talent-pipeline-tracker` | Gestión de candidaturas contra la API de 4Geeks | `3001` | Sesión obligatoria (salvo `/login` y `/register`), contra `services/api` | [`uis/talent-pipeline-tracker/README.md`](../uis/talent-pipeline-tracker/README.md) |

## 2. Arranque (cada uno en su terminal)

1. **API** — requisitos, venv e instalación en su README. Después:

   ```bash
   cd services/api
   cp .env.example .env        # solo la primera vez; rellenar JWT_SECRET_KEY (ver el propio archivo)
   uv run seed                 # opcional: carga los 15 proveedores iniciales (idempotente)
   uv run --env-file .env uvicorn app.main:create_app --factory --port 8000 --workers 1
   ```

   Swagger en `http://localhost:8000/docs`.

2. **Backoffice:**

   ```bash
   cd uis/backoffice
   npm install
   cp .env.example .env.local  # NEXT_PUBLIC_API_URL=http://localhost:8000
   npm run dev                 # http://localhost:3000
   ```

3. **Tracker:**

   ```bash
   cd uis/talent-pipeline-tracker
   npm install
   # crear .env.local con las dos variables de la sección 3
   npm run dev                 # http://localhost:3001
   ```

4. **Website:** abrir `uis/website/index.html` en el navegador (o servir la carpeta con cualquier servidor estático). No necesita la API.

La primera cuenta se crea desde `/register` en cualquiera de las dos apps (rol `user`). Un admin se crea con `uv run --env-file .env create-admin` en `services/api` (ver su README).

## 3. Variables de entorno

**Ningún `.env` ni `.env.local` se versiona** (están en `.gitignore`); los valores reales, y en especial `JWT_SECRET_KEY`, solo viven en tu máquina. Lo versionado son los ejemplos (`services/api/.env.example`, `uis/backoffice/.env.example`) y esta documentación.

| App | Variable | Valor local | Para qué |
|---|---|---|---|
| `services/api` | `JWT_SECRET_KEY` | secreto propio (≥ 32 caracteres) | Firma de los JWT. Obligatoria |
| `services/api` | `ACCESS_TOKEN_EXPIRE_MINUTES` | p. ej. `30` | Validez del token. Obligatoria |
| `services/api` | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3001` | Orígenes que pueden llamar a la API desde el navegador (sección 5) |
| `services/api` | `RESEND_API_KEY` | tu API key de Resend | Envío del email de restablecimiento (AUTH-03). Opcional: va junto con las dos siguientes |
| `services/api` | `EMAIL_FROM` | `Nexova <onboarding@resend.dev>` | Remitente de pruebas de Resend: solo entrega a la dirección de tu cuenta de Resend |
| `services/api` | `PASSWORD_RESET_URL` | `http://localhost:3000/reset-password` | Página del enlace del email (`?token=…`) |
| `uis/backoffice` | `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | URL de `services/api` |
| `uis/talent-pipeline-tracker` | `NEXT_PUBLIC_API_URL` | `https://playground.4geeks.com/tracker/api/v1` | API de candidaturas de **4Geeks** (sin cambios) |
| `uis/talent-pipeline-tracker` | `NEXT_PUBLIC_AUTH_API_URL` | `http://localhost:8000` | URL de `services/api` para login, registro y perfil |

Las variables `NEXT_PUBLIC_*` se incorporan al build: tras cambiarlas hay que reiniciar `npm run dev` (o recompilar).

## 4. Autenticación (AUTH-01, AUTH-02 y AUTH-03), en resumen

- **Login** (`/login`): `POST /auth/login` con formulario `application/x-www-form-urlencoded` (`username` = email, `password`). Si es correcto, el JWT se guarda en `localStorage` y se entra en `/`.
- **Registro** (`/register`): `POST /users` (email, contraseña y nombre/teléfono/dirección opcionales) y después login automático con las mismas credenciales.
- **Perfil** (`/account/profile`): `GET /auth/me` para leer; `PUT /profiles/me` para editar nombre y contacto.
- **Protección de rutas:** un guard en el layout raíz de cada app exige sesión en todas las vistas salvo `/login` y `/register`; la sesión se valida con `GET /auth/me`. Sin middleware de Next.js ni cookies.
- **401:** si la API rechaza el token (caducado o inválido), se borra de `localStorage` y se vuelve a `/login`.
- **Logout:** borra el token y vuelve a `/login`, sin llamar a la API.
- **Sin refresh tokens:** al caducar el JWT hay que volver a iniciar sesión.
- **Contraseñas (AUTH-03):** `/forgot-password` → email con enlace (Resend) → `/reset-password?token=…` → `/login`; `/account/change-password` con sesión. El token del enlace caduca (30 minutos por defecto) y solo sirve una vez. Para recibir el email en local: configurar las tres variables de Resend de la sección 3, reiniciar la API y pedir el enlace con el email de tu cuenta de Resend (registrado antes en `/register`). Contexto en [`auth-password-reset.md`](./auth-password-reset.md).
- **Separación de servicios:** el JWT solo se envía a `services/api`. **Nunca** se envía a la API de 4Geeks (el tracker usa dos clientes distintos) y el website no interviene en la autenticación.

## 5. CORS

El navegador solo deja que una app lea las respuestas de la API si su origen está en `CORS_ALLOWED_ORIGINS` (`services/api/.env`; por defecto en código solo `http://localhost:3000`). El tracker corre en `http://localhost:3001`, así que ese origen **debe** estar en la lista; `services/api/.env.example` ya lo incluye. Tras cambiar el `.env`, reiniciar la API.

Síntoma típico si falta: en el tracker, el login devuelve `200` en la pestaña de red pero la UI muestra "No se pudo conectar con el servidor" y no se guarda ningún token (el login es una petición CORS simple, sin preflight, y el navegador bloquea la lectura de la respuesta).

## 6. Validación

Los comandos exactos de cada subproyecto están en [`AGENTS.md`](../AGENTS.md) §4. Resumen:

| Subproyecto | Validación |
|---|---|
| `services/api` | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` (desde la raíz; Linux/macOS: `services/api/.venv/bin/python …`) |
| `uis/backoffice` | `npm run build`, `npx tsc --noEmit`, `npm run lint` y tests con Node 24 (comando en su README) |
| `uis/talent-pipeline-tracker` | `npm run build`, `npx tsc --noEmit`, `npm run lint` y tests con Node 24 (comando en su README) |
| `src/` (Hito 2) | `npm run check` desde la raíz |
| `packages/incident-analyzer` | `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` |
| `uis/website` | Sin build: verificación manual en el navegador |

Problemas conocidos, anteriores a AUTH-02 (también en `main`):

- `npx tsc --noEmit` en las apps Next.js necesita los tipos que Next genera en `.next/` (`LayoutProps`, `PageProps`): ejecutar antes `npm run build` (o `npm run dev`).
- `npm run lint` del tracker informa de 4 errores `react-hooks/set-state-in-effect` en `hooks/use-notes.ts`, `hooks/use-record-detail.ts` y `hooks/use-records.ts`.
