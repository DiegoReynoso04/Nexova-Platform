# Desarrollo local — cómo levantar y probar el sistema completo

Guía de arranque del monorepo para quien llega nuevo. **Desde el ticket #infra-40 (2026-10), Docker es el único modo de arrancar la plataforma en desarrollo:** website, backoffice y API se levantan con un solo `docker compose up`, un solo `.env` (el de la raíz) y un solo juego de puertos. El detalle de cada aplicación está en su README (no se duplica aquí); la guía de revisión del ticket, en [`infra-40-review.md`](./infra-40-review.md). La autenticación del frontend se explica en [`auth-frontend.md`](./auth-frontend.md); el contrato HTTP de la API, en [`services/api/SPECS.md`](../services/api/SPECS.md).

## 1. Requisitos

- **Docker Desktop** (Windows/macOS) o **Docker Engine con el plugin Compose v2** (Linux). Compose 2.17 o superior: `docker-compose.yml` usa `additional_contexts`. Comprobado con Docker 29.7.2 y Compose v5.5.0 en Windows.
- Para **ejecutar los tests** (siguen en el host, ver §8): Node.js 24 y el venv de `services/api` (ver su README). Arrancar la plataforma no necesita ni Node ni Python en el host.
- Un proyecto de **Supabase** para el inventario (Hito 5): la API no arranca sin `DATABASE_URL`. Cómo obtener la URI: [`services/api/README.md`](../services/api/README.md#crear-la-base-en-supabase).

## 2. Crear el `.env` (una sola vez)

```bash
cp .env.example .env
```

En `.env` (raíz del repositorio, ignorado por git):

- **`JWT_SECRET_KEY`:** 32 caracteres o más. Generar una: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- **`DATABASE_URL`:** la URI del Transaction pooler de tu proyecto de Supabase (puerto 6543), con la contraseña.
- **Cola de tareas (DEV-55):** `REDIS_PASSWORD` (solo letras y números: `python -c "import secrets; print(secrets.token_hex(24))"`) y `FLOWER_BASIC_AUTH` (`usuario:contraseña`). `REDIS_URL` viene ya en la plantilla como `redis://:${REDIS_PASSWORD}@redis:6379/0`: Compose sustituye la contraseña al leer el `.env`. Sin estas tres, `docker compose up` no arranca.
- El resto viene con valores válidos; cada variable está explicada en [`.env.example`](../.env.example). El trío de Resend (`RESEND_API_KEY`, `EMAIL_FROM`, `PASSWORD_RESET_URL`) va todo o nada: con solo una parte, la API no arranca.

Cuidado con:

- **Fin de línea LF** (no CRLF). Guarda el archivo en LF si tu editor de Windows lo permite.
- **El símbolo `$`:** Compose interpola `$VAR` y `${VAR}` al leer el `.env`, así que un valor con `$` puede llegar cambiado. Evítalo en los valores; si no puedes, compruébalo con `docker compose config --quiet` (sin `--quiet` imprime el entorno con los secretos: no lo hagas).
- **No volver a copiar la plantilla encima** del `.env` ya rellenado (ver §9).

## 3. Arrancar, parar y ver logs

Desde la raíz del repositorio:

```bash
docker compose up -d          # construye las imágenes la primera vez y arranca todo
docker compose ps             # api (healthy) y ui
docker compose logs -f ui     # o api
docker compose down           # parar (los datos de services/api/data se conservan)
```

La primera vez construye las dos imágenes (unos 30 s de build más la descarga de las imágenes base). La `ui` arranca cuando la `api` está `healthy`: si la API no puede arrancar (falta una variable, Supabase no responde), la `api` queda `unhealthy` y `docker compose up` termina con error.

**Cuándo reconstruir** (`docker compose up -d --build`): si cambian las dependencias o los archivos que no se montan:

- `uis/backoffice/package-lock.json` (añadir `-V` para renovar el `node_modules` del volumen anónimo: `docker compose up -d --build -V`);
- `services/api/requirements.txt` (regenerado desde `uv.lock`, ver [`services/api/README.md`](../services/api/README.md#docker));
- `uis/start.sh`, `uis/serve-website.mjs`, los `Dockerfile` o `docker-compose.yml`.

El código del website, del backoffice, de `services/api/app` y de `packages/` se monta desde el host: un cambio se ve sin reconstruir (website al recargar; backoffice en unos 2 s; la API se reinicia sola). El worker de la cola **no** se reinicia solo (ver §3.1).

### 3.1 El worker de la cola de tareas (DEV-55)

`docker compose up -d` arranca también `redis` (broker y resultados), `worker` (el proceso de Celery que calcula el reporte técnico de `/telemetry`) y `flower` (el monitor). El worker es un proceso aparte de la API: pararla no lo para, y los mensajes esperan en Redis (con AOF, también si Redis se reinicia). Detalle en [`services/task_queue/README.es.md`](../services/task_queue/README.es.md); contrato en [`services/api/SPECS.md`](../services/api/SPECS.md) Parte J.

```bash
docker compose up -d worker            # levantar solo el worker (arranca redis si hace falta)
docker compose logs -f worker          # «Connected to redis://:**@redis:6379/0», «ready» y una línea por tarea
docker compose restart worker          # tras cambiar services/task_queue, services/telemetry o services/api/app
docker compose stop worker             # detenerlo: espera a las tareas en curso (hasta 160 s); las de la cola esperan en Redis
docker compose exec worker celery -A task_queue.celery_app call task_queue.ping   # tarea de prueba
```

- **Flower:** `http://localhost:5555`, con el usuario y la contraseña de `FLOWER_BASIC_AUTH`. Solo escucha en `127.0.0.1`, como Redis (6379).
- **Cada línea del log del worker** lleva `task_id`, el intento (`attempt=2/4`), el estado (`started`, `success`, `retry`, `dead_letter`) y la duración. Los errores van redactados: nunca una URL, una contraseña ni la SQL.
- **Ojo, la base:** el worker usa la misma `DATABASE_URL` que la API (la demo). Solo lee `telemetry_events` y, si una tarea falla del todo, escribe en `ops.task_dead_letters`, que no existe hasta migrarla (`python -m task_queue.migrate`, en la demo con `--allow-demo` y solo con confirmación). Mientras no exista, el fallo queda en el log (`status=dead_letter_not_stored`).
- **Sin worker,** `/telemetry` se queda en «En cola» (deja de consultar a los 10 minutos); **sin Redis,** muestra «El servicio de cálculo no está disponible».

## 4. Aplicaciones y puertos

| Aplicación | Qué es | Dirección | Autenticación | Detalle |
|---|---|---|---|---|
| `uis/website` | Landing pública + formulario de registro de talento (Hito 1). HTML estático: se publica en Netlify (`netlify.toml`); en Docker lo sirve `uis/serve-website.mjs` | `http://localhost:3000` | **Ninguna** | — |
| `uis/backoffice` | Panel interno: incidentes, proveedores, gestor de incidencias, inventario y cuenta | `http://localhost:3001` | Sesión obligatoria (salvo `/login`, `/register` y las de contraseña) | [`uis/backoffice/README.md`](../uis/backoffice/README.md) |
| `services/api` | API FastAPI de Nexova | `http://localhost:8000` (Swagger en `/docs`) | Emite y exige el JWT | [`services/api/README.md`](../services/api/README.md) |
| `uis/talent-pipeline-tracker` | Gestión de candidaturas contra la API de 4Geeks. **Fuera de Docker** (el ticket no lo incluye) | `http://localhost:3002` | Sesión contra `services/api` | §7 |
| `redis` | Broker y result backend de la cola de tareas (DEV-55) | `127.0.0.1:6379` (entre contenedores, `redis:6379`) | `REDIS_PASSWORD` | §3.1 |
| `worker` | Worker de Celery (`services/task_queue`): calcula el reporte técnico fuera de la API | Sin puertos | — | §3.1 |
| `flower` | Monitor de la cola (solo desarrollo) | `http://localhost:5555` | `FLOWER_BASIC_AUTH` | §3.1 |

**Cómo hablan entre sí:** el navegador solo habla con el backoffice. Las peticiones a la API van a `http://localhost:3001/backend/…` (mismo origen, sin CORS) y el servidor de Next las reenvía a `http://api:8000` por el nombre del servicio en la red de Docker (`API_INTERNAL_URL`, rewrite de `uis/backoffice/next.config.ts`). El puerto 8000 se publica para `/docs`.

## 5. Comandos dentro del contenedor `api`

La imagen instala las dependencias de `requirements.txt`, no el proyecto, así que los atajos de `[project.scripts]` (`seed`, `create-admin`, `seed-inventory`) no existen dentro. Sus equivalentes, con la plataforma arrancada:

```bash
docker compose exec api python -m app.seed                                     # 15 proveedores iniciales (idempotente)
docker compose exec api python -m app.auth.create_admin --email admin@example.com --name "Nombre"   # pide la contraseña
docker compose exec api python -m app.modules.inventory.seed --email usuario@example.com          # datos del inventario en Supabase
```

El seed del gestor de incidencias (`scripts/seed_incidents.py`) no está en la imagen: se monta al ejecutarlo. Con el CSV real en `data/raw/incidents/incidents-nexova.csv` (ignorado por git):

```bash
docker compose run --rm -v ./scripts:/app/scripts:ro -v ./data/raw:/app/data/raw:ro -e PYTHONPATH=/app/api:/packages/shared:/packages/incident-analyzer api python /app/scripts/seed_incidents.py
```

`DATABASE_URL` y el resto de variables ya llegan al contenedor desde el `.env`. La primera cuenta también se puede crear desde `/register` del backoffice (rol `user`).

## 6. Dónde están los datos

- **Usuarios, proveedores e incidencias (TinyDB):** `services/api/data/` del host, montada en el contenedor (`/app/api/data`). Se conservan al parar o reconstruir. Ignorada por git.
- **Inventario (Hito 5):** en la base PostgreSQL de Supabase de `DATABASE_URL`. Las pruebas cambian el neto del seed; restaurarlo con `TRUNCATE` + `seed-inventory` solo cuando corresponda (ver [`services/api/README.md`](../services/api/README.md#inventario-hito-5)).

## 7. El tracker, fuera de Docker

`uis/talent-pipeline-tracker` no forma parte del ticket y se arranca como siempre, en el **3002**, con la plataforma de Docker en marcha:

```bash
cd uis/talent-pipeline-tracker
npm install
# .env.local con NEXT_PUBLIC_API_URL=https://playground.4geeks.com/tracker/api/v1
#            y NEXT_PUBLIC_AUTH_API_URL=http://localhost:8000
npm run dev                 # http://localhost:3002
```

Llama a la API desde el navegador con otro origen, así que el `.env` de la raíz debe tener `CORS_ALLOWED_ORIGINS=http://localhost:3002` (es el valor de la plantilla). Tras cambiarlo: `docker compose up -d api`. Síntoma si falta: el login devuelve `200` en la pestaña de red, pero la UI muestra «No se pudo conectar con el servidor» y no se guarda ningún token (petición CORS simple, sin preflight).

## 8. Validación (en el host)

Los tests y las comprobaciones de cada subproyecto se ejecutan en el host, no en los contenedores. Los comandos exactos están en [`AGENTS.md`](../AGENTS.md) §4. Ningún test lee el `.env` de la raíz ni conecta con la API o con Supabase.

| Subproyecto | Validación |
|---|---|
| `services/api` | `unittest` con su venv y pytest (comandos en `AGENTS.md` §4) |
| `services/task_queue` (DEV-55) | `unittest` con el venv de `services/api`; la integración (Redis y PostgreSQL locales, worker real) en la imagen (comando en `AGENTS.md` §4) |
| `uis/backoffice` | `npx tsc --noEmit`, `npm run lint`, `npm run build`, tests con Node 24 y Jest |
| `uis/` (servidor del website) | `node --test "uis/tests/*.test.mjs"` desde la raíz |
| `uis/talent-pipeline-tracker` | `npx tsc --noEmit`, `npm run lint` y tests con Node 24 |
| Docker (`Dockerfile`, `docker-compose.yml`, `start.sh`) | `docker compose config --quiet`, `docker compose up -d --build` y las comprobaciones de `AGENTS.md` §4 |
| `src/` (Hito 2) | `npm run check` desde la raíz |
| `packages/incident-analyzer` | `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` |
| `uis/website` | Sin build: verificación manual en el navegador |

- `npx tsc --noEmit` en las apps Next.js necesita los tipos que Next genera en `.next/` (`LayoutProps`, `PageProps`): ejecutar antes `npm run build`.
- `npm run lint` del tracker informa de 4 errores `react-hooks/set-state-in-effect` en `hooks/use-notes.ts`, `hooks/use-record-detail.ts` y `hooks/use-records.ts`, anteriores a AUTH-02.

## 9. Problemas conocidos

- **Docker Desktop no arranca en Windows** (el motor no responde: `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`). En `%LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log` aparece `starting services: initializing Ingest server: listening on unix://…/Docker/run/sailor-ingest.sock: rename …`. **Causa probable, no confirmada:** archivos `.stale` viejos en `%LOCALAPPDATA%\Docker\run`; en este equipo se arregló borrándolos con Docker Desktop cerrado. No usar «Reset to factory defaults» (borra imágenes y volúmenes).
- **La API queda `unhealthy` tras recrear el `.env`:** pasó al volver a copiar `.env.example` encima del `.env` ya rellenado, que dejó `JWT_SECRET_KEY` y `DATABASE_URL` vacías (`docker compose logs api`: `ConfigError: JWT_SECRET_KEY is required…`). El `.env` se crea una sola vez (§2).
- **Error de hidratación en la consola del navegador** con atributos `bis_*` o similares: lo provocan extensiones del navegador que modifican el HTML, no el código. Probar en una ventana privada sin extensiones.
- **El backoffice no recarga:** comprobar que `WATCHPACK_POLLING=true` está en el `.env`. El contenedor usa `next dev --webpack`: con Turbopack, el bundler por defecto, el código montado no recarga (comprobado en #infra-40).
- **La página se queda en «Comprobando la sesión…» entrando por `http://127.0.0.1:3001`:** `next dev` bloquea sus recursos de desarrollo pedidos desde un origen que no es `localhost` (aviso `allowedDevOrigins` en `docker compose logs ui`). Entrar por `http://localhost:3001` (DEV-55, 2026-11-22).
- **El worker queda `unhealthy` tras reiniciar Docker:** pasaba cuando volvía solo (`restart: unless-stopped`) y Redis no. Desde DEV-55, `redis` tiene la misma política. Si se ve: `docker compose up -d redis` y el worker se reconecta solo.
- **`/telemetry` se queda «En cola»:** el worker no está en marcha (`docker compose ps worker`; `docker compose up -d worker`).

## 10. Autenticación (AUTH-01, AUTH-02 y AUTH-03), en resumen

- **Login** (`/login`): `POST /auth/login` con formulario `application/x-www-form-urlencoded` (`username` = email, `password`). Si es correcto, el JWT se guarda en `localStorage` y se entra en `/`.
- **Registro** (`/register`): `POST /users` (email, contraseña y nombre/teléfono/dirección opcionales) y después login automático con las mismas credenciales.
- **Perfil** (`/account/profile`): `GET /auth/me` para leer; `PUT /profiles/me` para editar nombre y contacto.
- **Protección de rutas:** un guard en el layout raíz de cada app exige sesión en todas las vistas salvo `/login` y `/register`; la sesión se valida con `GET /auth/me`. Sin middleware de Next.js ni cookies.
- **401:** si la API rechaza el token (caducado o inválido), se borra de `localStorage` y se vuelve a `/login`.
- **Logout:** borra el token y vuelve a `/login`, sin llamar a la API.
- **Sin refresh tokens:** al caducar el JWT hay que volver a iniciar sesión.
- **Contraseñas (AUTH-03):** `/forgot-password` → email con enlace (Resend) → `/reset-password?token=…` → `/login`; `/account/change-password` con sesión. El enlace va a `PASSWORD_RESET_URL` (`http://localhost:3001/reset-password` con Docker), caduca (30 minutos por defecto) y solo sirve una vez. Para recibir el email: las tres variables de Resend en el `.env` y `docker compose up -d api`. Sin dominio verificado en Resend, usar el destinatario de pruebas `delivered@resend.dev` (o el email de tu cuenta de Resend). Guía paso a paso en [`auth-password-reset.md`](./auth-password-reset.md) §9–§12.
- **Separación de servicios:** el JWT solo se envía a `services/api`. **Nunca** se envía a la API de 4Geeks (el tracker usa dos clientes distintos) y el website no interviene en la autenticación.
