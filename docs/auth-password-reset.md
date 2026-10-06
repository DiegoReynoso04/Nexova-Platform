# AUTH-03 — Recuperación y cambio de contraseña

Documento principal de AUTH-03: ticket, cómo funciona, cómo levantarlo, cómo validarlo (manual y automáticamente), qué pruebas de seguridad se hicieron y qué queda pendiente. Continúa [AUTH-01](./auth-api.md) (la API exige JWT) y [AUTH-02](./auth-frontend.md) (login, registro y perfil en el frontend). El contrato HTTP formal está en [`services/api/SPECS.md`](../services/api/SPECS.md) Parte D (§23–§27); las reglas de cada app, en su propia documentación (§14).

**Índice:** [1. Ticket](#1-ticket-resumen-del-texto-recibido) · [2. Alcance](#2-alcance) · [3. Decisiones del usuario](#3-decisiones-del-usuario-2026-10-05) · [4. Propuestas pendientes](#4-propuestas-de-implementación-pendientes-de-revisión) · [5. Endpoints](#5-endpoints-de-auth-03) · [6. Cómo funciona](#6-cómo-funciona-técnicamente) · [7. H-1](#7-h-1--protección-del-cambio-de-contraseña-mediante-put-usersid) · [8. Puesta en marcha](#8-puesta-en-marcha-local) · [9. Guía de validación manual](#9-guía-de-validación-manual-paso-a-paso) · [10. Resend sin dominio propio](#10-resend-sin-dominio-propio) · [11. Pruebas de seguridad](#11-pruebas-de-seguridad-realizadas) · [12. Tests automatizados](#12-tests-automatizados) · [13. Estado de la validación manual](#13-estado-final-de-la-validación-manual) · [14. Deuda técnica](#14-deuda-técnica-y-fuera-de-alcance) · [15. Dónde está cada cosa](#15-dónde-está-cada-cosa)

## 1. Ticket (resumen del texto recibido)

El sistema de autenticación funciona, pero un usuario que olvida su contraseña no puede recuperar su cuenta y uno con sesión no puede cambiarla. El tech lead abre **AUTH-03 — Recuperación y cambio de contraseña**, que cubre API y frontend:

- **Backend:** `POST /auth/forgot-password` (`{email}`: si el usuario existe, genera un token de restablecimiento de corta duración, 15–60 minutos, y envía el enlace por email; **siempre 200**), `POST /auth/reset-password` (`{token, new_password}`: valida firma, expiración y que no se haya usado; hashea, actualiza e **invalida el token**; **400** si es inválido, expirado o usado) y `POST /auth/change-password` (autenticado, `{current_password, new_password}`; **400** si la actual es incorrecta).
- **Email:** integrar **Resend** o **SendGrid** (los dos permiten probar sin dominio propio). El email lleva el enlace y es legible en móvil. La API key solo en variables de entorno, documentada en el README o en un `.env.example`.
- **Frontend:** `/forgot-password` (confirmación "Si esa dirección está registrada, recibirás un enlace en breve" tras enviar, exista o no el email; el formulario se desactiva tras el envío), `/reset-password` (lee el token del query string; con éxito → `/login` con mensaje; con token inválido o caducado → error claro y enlace a `/forgot-password`), `/account/change-password` (actual, nueva y confirmación; comprueba que coinciden antes de llamar a la API) y un enlace "¿Olvidaste tu contraseña?" en `/login`.
- **Seguridad:** los tokens expiran y no se pueden usar dos veces; `forgot-password` nunca revela si un email está registrado; ninguna API key en el código. El ticket advierte que un JWT con solo `exp` no se puede invalidar tras usarlo: hace falta estado en el servidor.
- **Opcionales (no evaluados):** plantilla HTML del email, rate limiting por email y registro de auditoría (timestamp, IP).

## 2. Alcance

| Pieza | Cambio |
|---|---|
| `services/api` | 3 endpoints nuevos, envío con Resend, tablas `password_reset_tokens` y `password_audit` en `auth.json`; corrección H-1 en `PUT /users/{id}` (§7) |
| `uis/backoffice` | `/forgot-password`, `/reset-password`, `/account/change-password`, enlace en `/login` y en `/account/profile` |
| `uis/talent-pipeline-tracker` | Las mismas tres vistas y enlaces (mismo criterio que AUTH-02: todas las apps salvo el website) |
| `uis/website` | Sin cambios (sigue público) |

## 3. Decisiones del usuario (2026-10-05)

| Decisión | Elección |
|---|---|
| Proveedor de email | **Resend** |
| Cómo llamarlo | **HTTP con la librería estándar** (`urllib`): sin dependencias nuevas, ni SDK ni `requests` |
| Apps con los flujos | **Backoffice y tracker** |
| Opcionales | **Solo auditoría** (sin plantilla HTML ni rate limiting) |

El detalle técnico (token opaco hasheado, vigencia, un solo uso, 400 en vez de 401, envío en segundo plano, H-1…) está en `services/api/SPECS.md` §24 (D-PWD-1…12).

## 4. Propuestas de implementación pendientes de revisión

Igual que en AUTH-02: decisiones tomadas al implementar que el ticket no fija. **Ninguna está revisada ni aprobada por el tech lead ni por la CTO.**

| ID | Propuesta | Motivo |
|---|---|---|
| P3-1 | **Una sola URL de restablecimiento** (`PASSWORD_RESET_URL`, en local el backoffice). El tracker tiene su `/reset-password`, pero el email no sabe desde qué app se pidió el enlace | Tomar la URL de la petición permitiría enlaces manipulados; no hay contrato para distinguir apps |
| P3-2 | **Email opcional al arrancar**: sin `RESEND_API_KEY`/`EMAIL_FROM`/`PASSWORD_RESET_URL` la API arranca y `forgot-password` responde 200 sin enviar (queda registrado como `EmailNotConfiguredError`) | No obligar a configurar Resend para usar incidentes o proveedores |
| P3-3 | **`/reset-password` accesible con o sin sesión** (`OPEN_PATHS`); `/forgot-password` redirige a `/` con sesión, como `/login` | El enlace del email debe funcionar aunque el navegador tenga otra sesión abierta |
| P3-4 | **En `/forgot-password` solo un fallo de red o del servidor (o un 422 de formato) muestra error y permite reintentar**; una respuesta 200 muestra siempre la misma confirmación | La API ya responde igual exista o no el email; mostrar "enviado" ante un fallo de red sería falso |
| P3-5 | **El token se quita de la barra de direcciones** al cargar `/reset-password` y la página usa `referrer: no-referrer` | Que el token no quede en el historial ni se envíe como `Referer` |
| P3-6 | **Email en texto plano**, en español | El ticket solo pide que sea legible en móvil; la plantilla HTML es opcional y no se eligió |

## 5. Endpoints de AUTH-03

Formato de error de toda la API: `{"detail": "...", "code": "..."}` (los 422 llevan en `detail` la lista de errores por campo). Ninguna respuesta incluye el email del usuario, el token ni contraseñas.

### `POST /auth/forgot-password`

| | |
|---|---|
| **Propósito** | Solicitar un enlace de restablecimiento por email |
| **Autenticación** | Pública (sin token) |
| **Request** | `{"email": "usuario@example.invalid"}` |
| **Respuesta** | **200** `{"detail": "if that email is registered, a reset link has been sent"}` — **la misma exista o no el email** |
| **Errores** | **422** si el email está mal formado o se envían campos extra (no depende de que el email exista) |

Seguridad:
- **Sin enumeración de usuarios:** mismo status y mismo cuerpo para un email registrado, uno desconocido o uno de un usuario inactivo.
- **Token solo para usuarios existentes y activos**; para el resto no se genera nada (solo queda una fila de auditoría `unknown_email`).
- **Token temporal y de un solo uso** (§6). En el backend se guarda **solo su hash SHA-256**, nunca el token en claro.
- **El enlace se construye con `PASSWORD_RESET_URL`** (variable de entorno del backend) + `?token=…`. Nunca se toma de la petición, así que un atacante no puede hacer que el email apunte a su dominio.
- **El email lo envía Resend** en una tarea en segundo plano, **después** de responder: el tiempo de respuesta no depende del envío y un fallo del proveedor no cambia la respuesta (en la consola de la API solo aparece el nombre de la clase de error).
- **Las credenciales de Resend solo viven en variables de entorno** del backend (`RESEND_API_KEY`); nunca en el código, el frontend ni las respuestas.

### `POST /auth/reset-password`

| | |
|---|---|
| **Propósito** | Fijar una contraseña nueva con el token del enlace |
| **Autenticación** | Pública (el token del enlace hace de prueba de posesión del email) |
| **Request** | `{"token": "<token del enlace>", "new_password": "NuevaClave123!"}` |
| **Respuesta** | **200** `{"detail": "password updated"}` |
| **Errores** | **400** `invalid_reset_token` si el token no existe, ha caducado o ya se usó (un único código para los tres casos); **422** si la contraseña nueva no cumple las reglas (mínimo 8 caracteres, máximo 72 bytes) |

Seguridad:
- **Duración configurable** con `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` (admitido 15–60; **30 minutos por defecto**, que es la configuración actual).
- **Uso único:** validar el token, cambiar la contraseña y marcarlo como usado ocurre en una sola operación; reutilizar el mismo enlace → 400.
- **Invalidación de tokens anteriores:** pedir un enlace nuevo invalida los pendientes del mismo usuario; un reset correcto y un cambio de contraseña también.
- **La contraseña nueva** pasa la misma validación que el registro y se guarda con el mismo hashing de AUTH-01 (bcrypt vía `libpass`).

### `POST /auth/change-password`

| | |
|---|---|
| **Propósito** | Cambiar la propia contraseña estando conectado. **Es el endpoint que deben usar los usuarios normales (`user`/`manager`) para cambiar su contraseña** (§7) |
| **Autenticación** | **Obligatoria**: `Authorization: Bearer <JWT>` |
| **Request** | `{"current_password": "ClaveActual123!", "new_password": "NuevaClave123!"}` |
| **Respuesta** | **200** `{"detail": "password updated"}`; la contraseña nueva funciona en el login y la antigua deja de funcionar |
| **Errores** | **400** `incorrect_password` si la contraseña actual no coincide; **401** sin token o con token inválido; **422** si la nueva no cumple las reglas |

Seguridad:
- Exige la contraseña actual: un token robado no basta para cambiarla.
- Siempre actúa sobre el usuario del token: el body no admite `user_id` (campos extra → 422).
- La contraseña actual incorrecta da **400 y no 401**, para que el frontend no cierre la sesión del usuario.
- Invalida los enlaces de restablecimiento pendientes del usuario.

## 6. Cómo funciona técnicamente

```text
forgot-password ──► ¿email de usuario activo? ──no──► auditoría (unknown_email) ──► 200 genérico
                         │ sí
                         ▼
        token = secrets.token_urlsafe(32)  (256 bits)
        guarda SHA-256(token), expires_at = ahora + 30 min, used_at = null
        invalida los tokens pendientes anteriores del usuario
                         │
                         ▼
        200 genérico ──► (después de responder) Resend envía PASSWORD_RESET_URL?token=<token>

reset-password ──► SHA-256(token) ──► ¿existe, no usado y no caducado?  ──no──► 400 invalid_reset_token
                                            │ sí (todo en una operación con lock)
                                            ▼
                         nueva contraseña con bcrypt + used_at = ahora + invalida otros pendientes ──► 200
```

| Pieza | Archivo |
|---|---|
| Endpoints | `services/api/app/routes/auth.py` (`forgot_password`, `reset_password`, `change_password`) |
| Lógica | `services/api/app/auth/service.py` (`UserService.request_password_reset`, `reset_password`, `change_password`) |
| Persistencia (TinyDB, `auth.json`) | `services/api/app/auth/repository.py` (tablas `password_reset_tokens` y `password_audit`) |
| Token y hash | `services/api/app/auth/security.py` (`new_reset_token`, `hash_reset_token`) |
| Envío con Resend | `services/api/app/auth/email.py` (`ResendEmailSender`, `POST https://api.resend.com/emails` con `urllib`) |
| Configuración | `services/api/app/core/config.py` |
| Corrección H-1 | `services/api/app/routes/users.py` (`update_user`) |

**Auditoría:** cada intento queda en `password_audit` con evento (`reset_requested`, `reset_completed`, `reset_rejected`, `password_changed`, `password_change_rejected`), `user_id` (o `null` si el email no existe), IP, motivo y fecha. **Nunca** el email, el token ni contraseñas.

**Frontend (backoffice y tracker):** `/login` tiene el enlace "¿Olvidaste tu contraseña?"; `/forgot-password` (pública) muestra siempre la misma confirmación y desactiva el formulario tras enviarlo; `/reset-password` (accesible con o sin sesión) lee `?token=`, lo quita de la URL y, con éxito, lleva a `/login?reset=success` con un aviso; si el token falta, es inválido, caducó o ya se usó muestra un error claro con enlace a `/forgot-password`; `/account/change-password` (protegida, enlazada desde `/account/profile`) comprueba que la nueva y la confirmación coinciden antes de llamar a la API. El token de restablecimiento **nunca** se guarda en `localStorage`/`sessionStorage` ni se escribe en consola.

## 7. H-1 — protección del cambio de contraseña mediante `PUT /users/{id}`

Hallazgo **H-1** de la auditoría de seguridad de AUTH-03 (2026-10-06), ya corregido. Antes, `PUT /users/{id}` (AUTH-01) permitía a un usuario normal cambiar su propio `password` **sin conocer la contraseña actual**, esquivando la comprobación de `POST /auth/change-password`.

Comportamiento actual (`services/api/app/routes/users.py`, `update_user`; `SPECS.md` D-AUTH-13, §21 y D-PWD-12):

- Los usuarios **`user` y `manager` no pueden enviar `password`** en `PUT /users/{id}`, ni sobre su propio id ni sobre el de otro usuario.
- Ese intento devuelve **HTTP 403** con `{"detail": "use POST /auth/change-password to change your password", "code": "forbidden"}`.
- **El PUT rechazado no aplica ningún otro cambio** del mismo request (por ejemplo, un `email` enviado junto a `password` tampoco se guarda).
- Un usuario normal **sigue pudiendo cambiar su `email`** con `PUT /users/{id}`.
- **Los administradores mantienen la capacidad de AUTH-01** de establecer la contraseña de cualquier usuario con `PUT /users/{id}` (riesgo residual documentado en §14).
- El cambio de contraseña de los usuarios normales se hace **exclusivamente** con `POST /auth/change-password`, que exige la contraseña actual.

Prueba manual en PowerShell 5.1 (datos ficticios; la API en `http://127.0.0.1:8000`). El JWT se guarda en una variable y **no se imprime**:

```powershell
$api = "http://127.0.0.1:8000"

# 1. Crear un usuario normal de prueba (rol user) y hacer login.
Invoke-RestMethod -Method Post -Uri "$api/users" -ContentType "application/json" `
  -Body '{"email":"h1-test@example.invalid","password":"H1Test123!"}'
$login = Invoke-RestMethod -Method Post -Uri "$api/auth/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=h1-test@example.invalid&password=H1Test123!"
$headers = @{ Authorization = "Bearer $($login.access_token)" }   # JWT en memoria, no se muestra
$me = Invoke-RestMethod -Uri "$api/auth/me" -Headers $headers

# 2. Intentar cambiar la contraseña con PUT /users/{id} enviando solo "password": se espera 403.
try {
  Invoke-RestMethod -Method Put -Uri "$api/users/$($me.id)" -Headers $headers `
    -ContentType "application/json" -Body '{"password":"H1NewPassword123!"}'
  "INESPERADO: el PUT se aceptó"
} catch {
  "Status: $($_.Exception.Response.StatusCode.value__)"   # esperado: 403
  $_.ErrorDetails.Message                                  # esperado: use POST /auth/change-password ...
}

# 3. La contraseña original sigue funcionando (200) y la del PUT no (401).
(Invoke-WebRequest -Method Post -Uri "$api/auth/login" -UseBasicParsing `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=h1-test@example.invalid&password=H1Test123!").StatusCode   # esperado: 200
try {
  Invoke-WebRequest -Method Post -Uri "$api/auth/login" -UseBasicParsing `
    -ContentType "application/x-www-form-urlencoded" `
    -Body "username=h1-test@example.invalid&password=H1NewPassword123!" | Out-Null
} catch { "Login con la contraseña del PUT: $($_.Exception.Response.StatusCode.value__)" }   # esperado: 401

# 4. El camino correcto: POST /auth/change-password con la contraseña actual (200).
Invoke-RestMethod -Method Post -Uri "$api/auth/change-password" -Headers $headers `
  -ContentType "application/json" `
  -Body '{"current_password":"H1Test123!","new_password":"H1NewPassword123!"}'      # esperado: password updated
```

## 8. Puesta en marcha local

Guía general (puertos, CORS, `.env.local` de los frontends): [`local-development.md`](./local-development.md). Lo imprescindible para AUTH-03:

| Aplicación | Directorio | Comando | URL |
|---|---|---|---|
| API (FastAPI) | `services/api` | `uv run --env-file .env uvicorn app.main:create_app --factory --port 8000 --workers 1` | `http://localhost:8000` (Swagger en `/docs`) |
| Backoffice | `uis/backoffice` | `npm run dev` | `http://localhost:3000` |
| Talent Pipeline Tracker | `uis/talent-pipeline-tracker` | `npm run dev` | `http://localhost:3001` |

**API.** El backend vive en `services/api` y usa su propio entorno virtual `services/api/.venv`, gestionado con `uv` (instalación inicial en [`services/api/README.md`](../services/api/README.md)). La aplicación se crea con la factory `create_app`: por eso el comando usa `app.main:create_app --factory` (**no** existe un objeto `app.main:app`). `--workers 1` es obligatorio (estado en memoria y TinyDB).

> **Importante:** la API **no** carga el archivo `.env` por sí sola (no usa `python-dotenv`). Hay que arrancarla con `uv run --env-file .env …` o exportar antes las variables en la terminal. Si se arranca sin ellas y faltan las de Resend, la API funciona pero no envía emails (en su consola aparece `EmailNotConfiguredError`).

**Variables de entorno de la API** (en `services/api/.env`, a partir de `services/api/.env.example`; **`.env` está en `.gitignore` y nunca debe committearse**):

| Variable | Obligatoria | Qué es (sin valores secretos) |
|---|---|---|
| `JWT_SECRET_KEY` | Sí (la API no arranca sin ella) | Clave de firma de los JWT, mínimo 32 caracteres. Generar una propia: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Sí | Validez del JWT de sesión en minutos (p. ej. `30`) |
| `RESEND_API_KEY` | Para enviar emails | API key de Resend (se crea en el panel de Resend). Va junto a las dos siguientes: las tres o ninguna |
| `EMAIL_FROM` | Con `RESEND_API_KEY` | Remitente. Sin dominio propio: `onboarding@resend.dev` (§10) |
| `PASSWORD_RESET_URL` | Con `RESEND_API_KEY` | Página de restablecimiento del frontend, p. ej. `http://localhost:3000/reset-password` |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | No (30 por defecto) | Vigencia del enlace, entre 15 y 60 |
| `CORS_ALLOWED_ORIGINS` | Recomendada | `http://localhost:3000,http://localhost:3001` para que los dos frontends puedan llamar a la API |

**Frontends.** Necesitan su `.env.local` (tampoco se versiona): el backoffice `NEXT_PUBLIC_API_URL=http://localhost:8000`; el tracker `NEXT_PUBLIC_API_URL` (API de candidaturas de 4Geeks) y `NEXT_PUBLIC_AUTH_API_URL=http://localhost:8000`. Detalle en [`local-development.md`](./local-development.md) §3. Ningún secreto de la API va a los frontends.

## 9. Guía de validación manual paso a paso

Requisitos: API, backoffice y tracker arrancados como en §8, con las tres variables de Resend configuradas. Los datos de ejemplo son ficticios.

### 9.1 Forgot password

1. **Email inexistente:** en `http://localhost:3000/forgot-password` (o con la petición de abajo) enviar `nadie@example.invalid` → **HTTP 200** y el mensaje genérico; en la UI, "Si esa dirección está registrada, recibirás un enlace en breve" y el formulario queda desactivado. No se envía ningún email.
2. **Email existente:** registrar antes un usuario en `/register` con el email de destino de la demo (sin dominio propio: `delivered@resend.dev`, ver §10) y repetir → **HTTP 200 con el mismo mensaje genérico**. La UI no distingue los dos casos.
3. **Resend recibe el envío:** en el panel de Resend (sección *Emails*/*Logs*) aparece el envío a ese destinatario como entregado. Abriendo el email en el panel se ve su contenido y el enlace `http://localhost:3000/reset-password?token=…`.

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/auth/forgot-password" `
  -ContentType "application/json" -Body '{"email":"nadie@example.invalid"}'
# detail: if that email is registered, a reset link has been sent
```

### 9.2 Reset password

1. Abrir el enlace del email (`/reset-password?token=…`). La página quita el token de la barra de direcciones al cargar.
2. Escribir la contraseña nueva dos veces y guardar → redirección a `/login` con el aviso "Contraseña restablecida".
3. Iniciar sesión con la contraseña nueva → correcto; con la antigua → "Email o contraseña incorrectos".
4. **Volver a abrir exactamente el mismo enlace** y enviar otra contraseña → error "El enlace no es válido o ha caducado" con el enlace "Solicitar un enlace nuevo" (la API responde 400 `invalid_reset_token`).
5. Opcional (caducidad): con un enlace sin usar, esperar más de 30 minutos (o el valor configurado) → mismo error.

### 9.3 Change password

1. Iniciar sesión → `/account/profile` → enlace **"Cambiar contraseña"** (`/account/change-password`).
2. **Contraseña actual incorrecta** → error junto al campo "La contraseña actual no es correcta" (la API responde **400** `incorrect_password`) y la sesión sigue abierta.
3. **Contraseña actual correcta** (y la nueva repetida igual) → "Contraseña actualizada" (la API responde **200**).
4. Cerrar sesión: el login con la **contraseña nueva funciona** y con la **antigua ya no**.
5. Si la nueva y la confirmación no coinciden, el formulario lo indica sin llamar a la API.

### 9.4 H-1

Seguir la prueba de PowerShell de §7: crear o usar un usuario normal, obtener su JWT, `PUT /users/{id}` con solo `password` → **403**; la contraseña original sigue funcionando; el cambio correcto se hace con `POST /auth/change-password`.

### 9.5 Frontends

Repetir 9.1–9.3 en los dos frontends:

| Comprobación | Backoffice (`:3000`) | Tracker (`:3001`) |
|---|---|---|
| Enlace "¿Olvidaste tu contraseña?" en `/login` | ✓ | ✓ |
| `/forgot-password` con mensaje genérico y formulario desactivado tras enviar | ✓ | ✓ |
| `/reset-password` con token válido y con token inválido/reutilizado | ✓ | ✓ |
| `/account/change-password`, enlazado desde `/account/profile` | ✓ | ✓ |

Nota: el enlace del email apunta a la página configurada en `PASSWORD_RESET_URL` (en local, el backoffice). La `/reset-password` del tracker funciona igual si se abre con un token válido o si `PASSWORD_RESET_URL` apunta a `http://localhost:3001/reset-password` (propuesta P3-1).

## 10. Resend sin dominio propio

- `onboarding@resend.dev` es el **remitente de pruebas** de Resend. Sin un dominio verificado, Resend **restringe los destinatarios**: no permite enviar a direcciones arbitrarias, solo a la dirección de la propia cuenta de Resend y a sus **direcciones de prueba**, como `delivered@resend.dev` (simula una entrega correcta y el envío queda visible en el panel como *delivered*, pero no llega a ningún buzón real).
- Por eso, en una demo sin dominio propio, el usuario de prueba de Nexova se registra con **`delivered@resend.dev`** y se pide el enlace para ese email; el contenido del email (y el enlace) se consulta en el panel de Resend.
- **No es un fallo de Nexova:** la API llama a Resend correctamente; la restricción es del plan de pruebas del proveedor. Si se pide un enlace para un email que no está registrado en Nexova, **por diseño** no se llama a Resend (§5), así que tampoco aparecerá nada en su panel.
- **Para enviar a emails reales** hay que verificar un dominio propio en Resend (registros DNS) y usar un `EMAIL_FROM` de ese dominio (p. ej. `Nexova <no-reply@dominio-verificado.example>`). No requiere ningún cambio de código, solo de configuración.

## 11. Pruebas de seguridad realizadas

**Auditoría de seguridad de AUTH-03 (revisión estática, 2026-10-06):** resultado **sin hallazgos críticos** y con **un hallazgo alto (H-1), corregido** (§7). Controles comprobados como correctos:

| Área | Resultado |
|---|---|
| Tokens de reset | 256 bits de entropía; solo se guarda el SHA-256; caducidad real configurable entre 15 y 60 min (30); un solo uso con validación y marcado atómicos; un enlace nuevo, un reset o un cambio de contraseña invalidan los pendientes |
| Contraseñas | Siempre bcrypt con el mecanismo de AUTH-01; mismas reglas en registro, reset y cambio; nunca en logs ni auditoría |
| Enumeración | Mismo status y cuerpo para email existente, desconocido o inactivo; el email se envía después de responder (ver M-2 en §14) |
| Email | API key solo en variables de entorno, oculta en `repr` y en errores; enlace construido solo desde `PASSWORD_RESET_URL`; el email solo lleva el enlace |
| Change password | Exige token y la contraseña actual; solo actúa sobre el usuario del token |
| Autorización | El token de reset va ligado al usuario en el servidor; no hay forma de dirigir reset o cambio a otro usuario (tras H-1) |
| Validación de entrada | Email normalizado (máx. 254), token y contraseña actual de 1–512 caracteres, contraseña nueva máx. 72 bytes, body máx. 1 MiB; la confirmación se comprueba en el frontend |
| Logs y auditoría | Solo evento, usuario, IP, motivo y fecha; los fallos de Resend se registran solo por nombre de clase |
| Frontend | El token no se guarda en el navegador ni se escribe en consola; se quita de la URL; React escapa el contenido; rutas públicas, abiertas y protegidas correctas |
| Configuración | Secretos solo en `services/api/.env` (ignorado por git); sin claves por defecto; configuración parcial de email → la API no arranca; los frontends solo reciben URLs |

Comprobaciones adicionales: búsqueda exacta de la `RESEND_API_KEY` y la `JWT_SECRET_KEY` reales en todos los archivos del repositorio, en el diff del commit y en los bundles `.next` de los frontends → **sin coincidencias**; prueba de humo contra un servidor real con base temporal (18/18, incluido el preflight CORS de las tres rutas desde los dos frontends). Los hallazgos no bloqueantes (M-1…M-3, L-1…L-6) están en §14.

## 12. Tests automatizados

Comandos exactos (desde la raíz del monorepo salvo que se indique; en Linux/macOS sustituir `services\api\.venv\Scripts\python` por `services/api/.venv/bin/python`). Ninguno llama a Resend real: el envío se prueba con un sender falso o simulando `urlopen`.

| Qué | Comando | Resultado registrado |
|---|---|---|
| Suite completa de la API | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` | 205 tests OK |
| Solo AUTH-03 (forgot/reset/change, Resend, configuración, auditoría) | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api -p "test_password_reset.py"` | 33 tests OK |
| Solo H-1 | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api -p "test_auth.py" -k password_with_put -k another_users_password -k change_password_endpoint_remains -k updates_own_email` | 6 tests OK |
| Alternativa con uv (desde `services/api`) | `uv run --no-sync python -m unittest discover -s tests -t .` | — |
| Backoffice (desde `uis/backoffice`) | `npx tsc --noEmit`, `npm run lint`, `npm run build` y `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"` | 263 tests OK; `tsc`, `lint` y `build` OK |
| Solo contraseñas del backoffice | mismo comando de Node con `"tests/password.service.test.mjs"` | 15 tests OK |
| Tracker (desde `uis/talent-pipeline-tracker`) | `npx tsc --noEmit`, `npm run lint` y `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test --test-timeout=10000 "tests/*.test.mjs"` | 35 tests OK; `tsc` OK; `lint` con 4 errores `react-hooks/set-state-in-effect` **anteriores** a AUTH-02 |
| Solo contraseñas del tracker | mismo comando de Node con `"tests/password.test.mjs"` | 15 tests OK |

Qué cubren:
- **`services/api/tests/test_password_reset.py`:** respuesta idéntica para email existente y desconocido, usuario inactivo sin email, solo el hash en la base, caducidad (incluido el límite exacto), un solo uso, enlace nuevo que invalida el anterior, reglas de la contraseña nueva, `change-password` (401 sin token, 400 con la actual incorrecta, 200 con la correcta, invalida enlaces pendientes), auditoría sin datos personales ni secretos, configuración (todas o ninguna, rango 15–60, URL absoluta, clave oculta), petición a Resend y errores del proveedor sin filtrar datos.
- **`services/api/tests/test_auth.py` (H-1):** `test_user_cannot_change_own_password_with_put`, `test_manager_cannot_change_own_password_with_put`, `test_user_cannot_change_another_users_password`, `test_admin_can_still_set_another_users_password`, `test_change_password_endpoint_remains_the_way_for_users` y `test_user_updates_own_email` (el antiguo test [18], que exigía el comportamiento eliminado).
- **Frontend:** servicio de contraseñas (bodies, confirmación que no se envía, 400/401/422), rutas públicas/abiertas/protegidas y revisión estática del código de producción (backoffice).

## 13. Estado final de la validación manual

Validación manual realizada por el desarrollador (2026-10-06) y registrada en [`memory-bank/progress.md`](../memory-bank/progress.md):

| Prueba | Estado |
|---|---|
| `forgot-password` con email inexistente → 200 y mensaje genérico | ✓ realizada |
| `forgot-password` con email existente → 200 y el mismo mensaje | ✓ realizada |
| Integración real con Resend usando un destinatario de pruebas | ✓ realizada |
| Generación del enlace de restablecimiento | ✓ realizada |
| Reset de contraseña con el enlace | ✓ realizada |
| Rechazo del mismo token tras el primer uso | ✓ realizada |
| `change-password` con contraseña actual incorrecta → 400 | ✓ realizada |
| `change-password` con contraseña actual correcta → 200 | ✓ realizada |
| Login con la contraseña nueva | ✓ realizada |
| Rechazo de la contraseña antigua | ✓ realizada |
| H-1: `PUT /users/{id}` con `password` → 403 | ✓ realizada |
| H-1: el PUT rechazado no modificó la contraseña | ✓ realizada |
| Frontend Backoffice (enlace, forgot, reset, change) | ✓ realizada |
| Frontend Tracker: `/forgot-password`, envío a Resend, mensaje genérico, botón desactivado tras enviar y `/reset-password` | ✓ realizada |
| Caducidad del token | ✓ informada en la validación del 2026-10-06 ("el token de reset caduca y es de un solo uso"); además cubierta por tests automáticos con reloj simulado |
| Envío a un email real fuera del entorno de pruebas de Resend | **Pendiente**: requiere un dominio verificado (§10) |
| Medición de tiempos de `forgot-password` (M-2), reset concurrente con el mismo token y log de `next dev` con la URL del token (L-3) | **Pendiente** (propuestos en la auditoría) |

## 14. Deuda técnica y fuera de alcance

Ninguno de estos puntos bloquea AUTH-03; están documentados en `services/api/SPECS.md` §27 y en `memory-bank/progress.md`:

| ID | Punto |
|---|---|
| M-1 | **Sesiones abiertas:** restablecer o cambiar la contraseña **no** invalida los JWT ya emitidos; siguen valiendo hasta su `exp` (igual que en AUTH-01) |
| M-2 | **Diferencia de tiempo** en `forgot-password`: para un email existente hay una escritura más en `auth.json` (pocos ms) |
| M-3 | **Sin rate limiting** en `forgot-password` (opcional del ticket no elegido): se pueden pedir enlaces sin límite y cada petición escribe en `auth.json` |
| — | **Riesgo residual de H-1:** un admin puede establecer contraseñas (también la suya) con `PUT /users/{id}` sin la actual; ese cambio no invalida enlaces de reset pendientes ni se audita |
| L-1 | La contraseña nueva se hashea antes de validar el token (coste de bcrypt por petición anónima, como el login) |
| L-2 | `PASSWORD_RESET_URL` admite `http://` (conviene exigir `https://` fuera de local) |
| L-3 | El token aparece en la URL de la primera carga (logs del servidor de Next o de un proxy, panel de Resend); mitigado con caducidad, un solo uso, `replaceState` y `no-referrer` |
| L-4 | Excepciones poco comunes del cliente HTTP (`http.client.HTTPException`) no se capturan en el sender; las recoge el middleware de errores sin filtrar datos |
| L-5 | **Auditoría y retención:** se guardan IP sin política de retención ni endpoint de consulta (las IP son datos personales) |
| L-6 | Si el navegador ya tiene otra sesión abierta, tras el reset `/login` redirige a `/` y no se ve el aviso de éxito |
| — | Plantilla HTML del email (opcional del ticket, no elegido: solo texto plano) |
| — | Propuestas P3-1…P3-6 (§4) pendientes de revisión |

## 15. Dónde está cada cosa

- API: [`services/api/SPECS.md`](../services/api/SPECS.md) Parte D (§23–§27) y [`README.md`](../services/api/README.md) (variables de entorno y sección "Recuperación y cambio de contraseña").
- Backoffice: [`uis/backoffice/CLAUDE.md`](../uis/backoffice/CLAUDE.md) (sección "Autenticación") y [`README.md`](../uis/backoffice/README.md).
- Talent Pipeline Tracker: [`SPECS.md`](../uis/talent-pipeline-tracker/SPECS.md) §9.4, [`CLAUDE.md`](../uis/talent-pipeline-tracker/CLAUDE.md) y [`README.md`](../uis/talent-pipeline-tracker/README.md).
- Cómo levantar todo en local: [`local-development.md`](./local-development.md).
