# AUTH-02 — Flujos de autenticación y vistas protegidas en el frontend

Documento de contexto del ticket AUTH-02 y resumen de cómo se implementó. Es la continuación de [AUTH-01](./auth-api.md) (la API ya exige JWT). El contrato HTTP sigue en [`services/api/SPECS.md`](../services/api/SPECS.md) Parte C; las reglas de cada app, en su propia documentación (ver §4). Aquí no se duplican.

## 1. Ticket (texto recibido)

> La API ya exige un token JWT en las rutas protegidas. Esta tarea cubre el lado frontend de ese contrato:
>
> - **Vistas de login y registro** — formularios que llaman a la API, reciben el token y lo almacenan correctamente.
> - **Vistas de gestión de cuenta** — página de perfil.
> - **Protección de rutas** — cualquier vista que requiera sesión debe redirigir a los usuarios no autenticados al login. Esto aplica a todas las aplicaciones del monorepo excepto el website público (Hito 1), que permanece completamente público.
>
> El token debe almacenarse en `localStorage` y adjuntarse a cada llamada protegida a la API mediante la cabecera `Authorization: Bearer`. Al cerrar sesión, el token se elimina y el usuario es redirigido al login.
>
> No construyas una aplicación de autenticación separada. Integra estos flujos en las aplicaciones Next.js existentes dentro de tu monorepo.

Flujo indicado junto al ticket:

1. Almacenar el token en `localStorage` después de una respuesta de login exitosa.
2. Leer el token en cada llamada protegida y enviarlo en `Authorization: Bearer <token>`.
3. Proteger rutas con un layout guard o hook en el cliente que lea `localStorage` y redirija a `/login` si no hay token. **No** usar el middleware de Next.js para esta comprobación (corre en el servidor y no puede leer `localStorage`), salvo que también se guarde una cookie.
4. Limpiar el token al cerrar sesión y redirigir.

Nota del ticket: la rotura temporal del frontend de la entrega anterior (AUTH-01: `/incidents` y `/suppliers` respondían 401) termina aquí; todas las vistas protegidas deben funcionar de extremo a extremo con autenticación real.

## 2. Alcance

| App | ¿Protegida? | Motivo |
|---|---|---|
| `uis/website` (Hito 1) | **No** | El ticket la excluye: sigue completamente pública, sin cambios |
| `uis/backoffice` | Sí: todas las vistas salvo `/login` y `/register` | `/`, `/incidents`, `/suppliers`, `/account/profile` |
| `uis/talent-pipeline-tracker` | Sí: todas las vistas salvo `/login` y `/register` | `/`, `/candidates/[id]`, `/account/profile`. Sus datos siguen viniendo de la API de 4Geeks, que **no** recibe el token |

## 3. Requisitos, hechos y propuestas

Esta sección separa lo que exige el ticket, lo que se comprobó en el repositorio y lo que se decidió durante la implementación. **Ninguna de las propuestas de §3.3 ha sido revisada ni aprobada todavía por el tech lead ni por la CTO**: describen lo implementado en la rama `feature/auth-frontend` y quedan pendientes de revisión.

### 3.1 Requisitos del ticket AUTH-02 (§1)

| ID | Requisito | Cómo se cumple |
|---|---|---|
| R-1 | Vistas de login y registro que llaman a la API, reciben el token y lo almacenan | `/login` (`POST /auth/login`) y `/register` (`POST /users` + `POST /auth/login` con las mismas credenciales, sin `role`) en cada app Next.js; el token solo se guarda si la respuesta del login es válida |
| R-2 | Vista de gestión de cuenta (perfil) | `/account/profile`: `GET /auth/me` y `PUT /profiles/me` |
| R-3 | Toda vista con sesión redirige a los no autenticados al login; todas las apps salvo el website | Guard global en el layout raíz de `uis/backoffice` y `uis/talent-pipeline-tracker`; `uis/website` sin cambios |
| R-4 | Token en `localStorage`, enviado como `Authorization: Bearer` en cada llamada protegida | Un único módulo por app (`lib/auth-token.ts`); la cabecera se añade solo en `lib/api-client.ts` |
| R-5 | Logout: eliminar el token y redirigir al login | Botón "Cerrar sesión" en la cabecera de cada app, sin petición a la API |
| R-6 | Sin app de autenticación separada; sin middleware de Next.js para leer `localStorage` (salvo cookie) | Flujos integrados en las apps existentes; guard en cliente; sin middleware ni cookies |
| R-7 | Las vistas protegidas funcionan de extremo a extremo con autenticación real | `/incidents` y `/suppliers` del backoffice vuelven a funcionar enviando el JWT |

### 3.2 Hechos comprobados en el repositorio

- **Contrato de `services/api`** (`SPECS.md` Parte C y `app/auth/`): login con formulario OAuth2 (`username` = email; D-AUTH-3), respuesta `{access_token, token_type, expires_in}`; `POST /users` no admite `role` (D-AUTH-8); `GET /auth/me` devuelve el usuario con su `Profile`; `PUT /profiles/me` actualiza solo los campos enviados (D-AUTH-13) y el servicio documenta que `null` borra el dato (`exclude_unset`).
- **CORS antes de AUTH-02:** métodos `GET`/`POST`/`PATCH`/`DELETE`; `PUT` no estaba y `SPECS.md` §22 ya preveía añadirlo cuando el frontend llamara a `PUT /profiles/me`. Origen por defecto: `http://localhost:3000`.
- **Talent Pipeline Tracker:** sus datos vienen de la API de 4Geeks (`NEXT_PUBLIC_API_URL`), que no tiene autenticación (`SPECS.md` §5.1) y cuyo `SPECS.md` prohíbe proxy y Route Handlers (§2.3).
- **Puertos:** las dos apps Next.js usaban `next dev` sin puerto (3000 por defecto). Next 16 solo prueba otro puerto libre cuando se usa el puerto por defecto, así que, arrancadas a la vez, la segunda acababa en 3001 o en otro según el orden de arranque.
- **Backoffice:** su `CLAUDE.md` prohibía cualquier persistencia en el navegador; el ticket exige `localStorage` para el token, así que se documentó como única excepción.

### 3.3 Propuestas de implementación pendientes de revisión

| ID | Propuesta | Motivo |
|---|---|---|
| P-1 | **Puerto 3001 para el tracker** (`next dev --port 3001` y `next start --port 3001` en su `package.json`). Es configuración local de desarrollo, no un cambio de contrato ni de negocio | Poder ejecutar a la vez backoffice (3000), tracker (3001) y API con un origen CORS estable. La alternativa sin tocar `package.json` (arrancar con `npm run dev -- --port 3001`) depende de que cada persona lo recuerde |
| P-2 | **`NEXT_PUBLIC_AUTH_API_URL`** en el tracker (URL de `services/api`), separada de `NEXT_PUBLIC_API_URL` (4Geeks). Como esta, se exige al arrancar (`SPECS.md` §3.2) | El tracker habla con dos APIs distintas y el token solo debe ir a `services/api` |
| P-3 | **Validación inicial de sesión con `GET /auth/me`**, una vez por token, antes de mostrar una vista protegida; sin token o con 401 se va a `/login` | En el tracker es la única llamada protegida que puede detectar un token caducado (los datos de 4Geeks no usan el token); evita mostrar la vista protegida con una sesión inválida |
| P-4 | **`null` al vaciar un campo del perfil:** `PUT /profiles/me` envía siempre `name`, `phone` y `address`, con `null` en los vacíos para borrar ese dato | Coincide con el contrato comprobado (§3.2); enviar `""` guardaría una cadena vacía |
| P-5 | **CORS:** añadir `PUT` a los métodos y `http://localhost:3001` al `.env.example` de `services/api` (el valor por defecto en código sigue siendo solo `http://localhost:3000`) | Necesario para P-1 y para `PUT /profiles/me` desde el navegador |
| P-6 | Tras login o registro se va a `/`; `/login` y `/register` con sesión válida redirigen a `/`. La cabecera muestra el email de la sesión junto a "Mi perfil" y "Cerrar sesión" | El ticket no fija el destino ni el contenido de la cabecera |
| P-7 | Sin refresh tokens: al expirar el JWT, el 401 lleva a `/login` | Fuera del alcance del ticket (igual que en AUTH-01, `SPECS.md` §22) |

## 4. Dónde está cada cosa

- Backoffice: [`uis/backoffice/CLAUDE.md`](../uis/backoffice/CLAUDE.md) (sección "Autenticación") y [`README.md`](../uis/backoffice/README.md).
- Talent Pipeline Tracker: [`SPECS.md`](../uis/talent-pipeline-tracker/SPECS.md) §9, [`CLAUDE.md`](../uis/talent-pipeline-tracker/CLAUDE.md) y [`README.md`](../uis/talent-pipeline-tracker/README.md).
- API: [`services/api/SPECS.md`](../services/api/SPECS.md) Parte C (§16 D-AUTH-12 y §22 actualizados).
- Cómo levantar todo en local (puertos, variables, CORS, validación): [`local-development.md`](./local-development.md).
