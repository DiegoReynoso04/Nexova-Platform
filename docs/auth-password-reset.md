# AUTH-03 — Recuperación y cambio de contraseña

Documento de contexto del ticket AUTH-03 y resumen de cómo se implementó. Continúa [AUTH-01](./auth-api.md) (la API exige JWT) y [AUTH-02](./auth-frontend.md) (login, registro y perfil en el frontend). El contrato HTTP está en [`services/api/SPECS.md`](../services/api/SPECS.md) Parte D; las reglas de cada app, en su propia documentación (ver §5). Aquí no se duplican.

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
| `services/api` | 3 endpoints nuevos, envío con Resend, tablas `password_reset_tokens` y `password_audit` en `auth.json` |
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

El detalle técnico (token opaco hasheado, vigencia, un solo uso, 400 en vez de 401, envío en segundo plano…) está en `services/api/SPECS.md` §24 (D-PWD-1…11).

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

## 5. Dónde está cada cosa

- API: [`services/api/SPECS.md`](../services/api/SPECS.md) Parte D (§23–§27) y [`README.md`](../services/api/README.md) (variables de entorno y sección "Recuperación y cambio de contraseña").
- Backoffice: [`uis/backoffice/CLAUDE.md`](../uis/backoffice/CLAUDE.md) (sección "Autenticación") y [`README.md`](../uis/backoffice/README.md).
- Talent Pipeline Tracker: [`SPECS.md`](../uis/talent-pipeline-tracker/SPECS.md) §9.4, [`CLAUDE.md`](../uis/talent-pipeline-tracker/CLAUDE.md) y [`README.md`](../uis/talent-pipeline-tracker/README.md).
- Cómo levantar todo en local y probar el email real: [`local-development.md`](./local-development.md).
