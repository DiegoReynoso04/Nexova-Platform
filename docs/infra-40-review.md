# Ticket #infra-40 — entorno de desarrollo con Docker: guía de revisión

Documento para revisar el ticket: qué se construyó, cómo arrancarlo, qué evidencia hay para cada criterio de evaluación del brief, qué se decidió y qué **no** está verificado.

- Brief literal (con la nota de equivalencias de este repo): [`infra-40-brief.md`](./infra-40-brief.md).
- Guía de arranque del día a día: [`local-development.md`](./local-development.md).
- Reglas para agentes y validación de cada pieza: [`AGENTS.md`](../AGENTS.md) §4 (bloque «Docker»).
- Historial por fases (F0–F5 y F7) y validaciones ejecutadas: [`memory-bank/progress.md`](../memory-bank/progress.md).

> Las decisiones D1–D7 y las posteriores (webpack, `data/` montada, Docker como único modo, tracker al 3002, VPS fuera de esta entrega) las tomó **el usuario** al revisar cada fase (2026-10-22 a 2026-10-25). No las ha revisado el tech lead.

## Qué se construyó

Rama `feature/docker-dev-env`, desde `main`. Sin dependencias nuevas: las imágenes instalan exactamente lo que ya fijaban `uv.lock` y `uis/backoffice/package-lock.json`.

| Pieza | Dónde | Qué hace |
|---|---|---|
| Orquestación | [`docker-compose.yml`](../docker-compose.yml) | Dos servicios, `api` y `ui`, en la red `nexova-net`. `ui` arranca cuando `api` está `healthy` (healthcheck sobre `/health`). Puertos 3000 (website), 3001 (backoffice) y 8000 (API) |
| Variables | [`.env.example`](../.env.example) → `.env` en la raíz (ignorado) | Todas las variables de los dos contenedores. `api` recibe el `.env` (`env_file`, obligatorio); `ui` solo `API_INTERNAL_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_INVENTORY_API_URL` y `WATCHPACK_POLLING`, con `${VAR:?…}` |
| Imagen de la API | [`services/Dockerfile`](../services/Dockerfile), [`services/.dockerignore`](../services/.dockerignore) | `python:3.14.6-slim`, `uv` 0.12.21, `uv pip install --system --require-hashes -r requirements.txt`; `nexova_shared` e `incident_analyzer` por `PYTHONPATH` desde el contexto adicional `packages`; uvicorn con `--reload` |
| Dependencias de la API | [`services/api/requirements.txt`](../services/api/requirements.txt) | Exportado de `uv.lock` con `uv export --frozen --no-dev --no-emit-project` (28 paquetes con hashes) |
| Imagen de interfaces | [`uis/Dockerfile`](../uis/Dockerfile), [`uis/.dockerignore`](../uis/.dockerignore) | `node:24.20.0-alpine`; `npm ci` del backoffice (variantes musl de los binarios nativos); el website no tiene `package.json` |
| Arranque de interfaces | [`uis/start.sh`](../uis/start.sh) | Website en el 3000 y `next dev --webpack` en el 3001; reenvía SIGTERM/SIGINT y, si uno cae, para el otro y sale con error (cada app en su grupo de procesos) |
| Servidor del website | [`uis/serve-website.mjs`](../uis/serve-website.mjs) | Módulo `http` de Node, sin dependencias: `/` → `index.html`, 404 con `404.html`, nada fuera de `uis/website` |
| Rewrite | [`uis/backoffice/next.config.ts`](../uis/backoffice/next.config.ts) | `/backend/:path*` → `API_INTERNAL_URL` (`http://api:8000`) solo si la variable existe |
| Fin de línea | [`.gitattributes`](../.gitattributes) | LF en `*.sh` y `Dockerfile` (con `core.autocrlf=true`, un `start.sh` con CRLF falla en Linux) |
| Tests | `uis/backoffice/tests/next-config.test.mjs`, `services/api/tests/test_requirements_lock.py`, `uis/tests/serve-website.test.mjs` | Rewrite, `requirements.txt` frente a `uv.lock`, rutas del servidor del website |

## Cómo arrancarlo

```bash
cp .env.example .env   # una sola vez: rellenar JWT_SECRET_KEY y DATABASE_URL
docker compose up -d
docker compose ps      # api (healthy) y ui
```

- Website: `http://localhost:3000` · Backoffice: `http://localhost:3001` · API: `http://localhost:8000/docs`.
- Requisitos, cuándo reconstruir, comandos de seed dentro del contenedor, datos y problemas conocidos: [`local-development.md`](./local-development.md).

### Suites y totales (en el host)

| Suite | Comando | Total |
|---|---|---|
| `uis/backoffice` node:test | ver `AGENTS.md` §4 | 497 (491 antes del ticket) |
| `uis/backoffice` Jest | `npm run test:jest` | 222 (sin cambios) |
| `uis/` | `node --test "uis/tests/*.test.mjs"` | 8 (nuevo) |
| `services/api` unittest | ver `AGENTS.md` §4 | 415 (409 antes) |
| `services/api` pytest | `uv run --no-sync python -m pytest` (desde `services/api`) | 618 (612 antes) |
| `uis/talent-pipeline-tracker` | ver `AGENTS.md` §4 | `tsc` sin errores, 4 errores de lint previos, 55 tests |

## Trazabilidad: «Lo que evaluaremos» → implementación → evidencia

Fuente: el brief literal, sección «Lo que evaluaremos». «F4» y «F5» son las fases de [`progress.md`](../memory-bank/progress.md).

| Criterio | Implementación | Evidencia |
|---|---|---|
| `docker compose up` desde la raíz levanta la plataforma completa sin errores ni pasos adicionales | `docker-compose.yml`; `.env` creado una vez desde `.env.example` (lo pide el propio brief) | **F4h, desde cero:** `docker compose down --rmi local --volumes` y luego `docker compose up -d` sin `--build` → código 0, `api` `healthy`, plataforma respondiendo a los 17 s (con caché de BuildKit); con `build --no-cache`, 31 s de build y 46 s hasta responder. **Pruebas del usuario en el navegador (F4):** login, inventario, `/incidents` con subida y exportación, `/suppliers`, `/incident-manager` y recuperación de contraseña, todo correcto |
| Los cambios en el host se ven sin reconstruir (bind mounts en los dos servicios) | Bind mounts de `uis/website`, `uis/backoffice`, `services/api/app` y los dos paquetes de `packages/`; `node_modules` y `.next` en volúmenes anónimos; `next dev --webpack` + `WATCHPACK_POLLING`; uvicorn `--reload-dir /app/api --reload-dir /packages` | **F4g**, con marcas temporales deshechas: website en 0,2 s; backoffice en ~2 s (con Turbopack no recargaba ni con polling; con webpack sí); API (`app/main.py`) en 1,1 s y `packages/shared` en ~1 s («StatReload detected changes…»). El usuario confirmó la recarga del backoffice en el navegador |
| El servicio de interfaces arranca las dos apps en puertos distintos (3000 y 3001) desde un único contenedor | `uis/start.sh` (CMD de `uis/Dockerfile`): `serve-website.mjs` en el 3000 y `next dev` en el 3001 | `docker compose ps`: `nexova-ui-1` publica `3000-3001`; log del contenedor (`website: http://0.0.0.0:3000` y `Next.js 16.3.2 (webpack)`). **Desviación:** el website es HTML estático, no Next.js (ver Decisiones) |
| Comunicación interna por nombre de servicio, no por `localhost` ni IP | Rewrite `/backend/:path*` → `API_INTERNAL_URL=http://api:8000`; red `nexova-net` | **F4d:** `docker compose exec ui wget -qO- http://api:8000/health` → `{"status":"ok"}`; `curl localhost:3001/backend/health` → 200, y el log de la API muestra el origen 172.19.0.3 (la ui). **F4f:** el JavaScript del navegador lleva `"/backend"`, sin `localhost:8000`. **F5:** `next-config.test.mjs` (6 tests). El usuario comprobó en la pestaña Red que no hay ninguna petición a `:8000` |
| Sin secretos en `Dockerfile` ni `docker-compose.yml` | Variables solo en el `.env` (`env_file` e interpolación `${VAR:?…}`); ningún `ENV` ni `ARG` con secretos | **F4i:** `grep -i -E "secret\|password\|key\|postgresql://\|eyJ"` en los tres archivos solo encuentra comentarios, y ningún valor real del `.env`. `docker history --no-trunc` de las dos imágenes, sin secretos (F2, F3). En la `ui`, `JWT_SECRET_KEY`, `DATABASE_URL`, `RESEND_API_KEY` y `EMAIL_FROM` ausentes (F4e). Verificación final del cierre (F7): ningún secreto en `git log -p` de la rama |
| `.env` en `.gitignore` y fuera del historial | `.gitignore` (`.env`, `.env.*`, `!.env.example`) | `git check-ignore -v .env` → `.gitignore:6:.env`; `git log --all -- .env '**/.env'` → 0 commits (F1, repetido en F4 y en el cierre) |
| Existen `.dockerignore` en `/uis/` y en `/services/` | `uis/.dockerignore`, `services/.dockerignore` | Las imágenes no contienen `.env*`, `node_modules` del host, `.next`, `tests`, `.venv`, `data/`, `*.egg-info` ni `__pycache__` (F2 y F3, con `find` dentro de la imagen) |
| Contenedores desplegados en producción en el VPS | — | **Fuera de esta entrega** por decisión del usuario (2026-10-25), pendiente de confirmación del profesor. No hay `docker-compose.prod.yml` |

## Decisiones

| | Decisión | Motivo y evidencia |
|---|---|---|
| D1 | `uis/website` sigue siendo HTML estático; en Docker lo sirve `uis/serve-website.mjs` (módulo `http` de Node), fuera de `uis/website/` | Netlify publica esa carpeta tal cual; convertirla a Next.js añadiría dependencias y un build. La `busybox` de `node:24-alpine` no trae `httpd` (comprobado: `busybox --list` sin `httpd`) |
| D2 | Backoffice en el 3001 dentro de Docker; CORS sin tocar para el backoffice | Con el rewrite, el backoffice llama a la API por su mismo origen y no necesita CORS |
| D3 | Rewrite `/backend` → `API_INTERNAL_URL`, variable solo de servidor | El navegador no puede resolver `api`; sin la variable no hay rewrite. Con `next start`, los rewrites salen del `routes-manifest.json` de `next build`, así que un build de producción necesitaría la variable al construir |
| D4 | `services/Dockerfile` con contexto `services/` y `packages/` como contexto adicional; `requirements.txt` desde `uv.lock`; paquetes del monorepo por `PYTHONPATH` | Mismas versiones exactas que el venv, con hashes; los paquetes del monorepo no se instalan desde PyPI (instalarlos pediría `setuptools` a PyPI) y en desarrollo se ven sin reconstruir |
| D5 | Recarga verificada, no supuesta; `node_modules` y `.next` en volúmenes anónimos; `.gitattributes` para `*.sh` y `Dockerfile` | El índice ya estaba en LF; el CRLF solo estaba en la copia de trabajo (`core.autocrlf=true`) |
| D6 | Un solo `.env` en la raíz y un `.env.example` versionado | La `ui` solo recibe sus cuatro variables |
| D7 | Producción con `docker-compose.prod.yml` | **No se hizo:** el VPS quedó fuera de esta entrega |
| — | **`next dev --webpack`** en Docker | Con Turbopack, el código montado no recargaba ni con `watchOptions.pollIntervalMs` ni con cambios hechos dentro del contenedor; con webpack y `WATCHPACK_POLLING` sí (~2 s). Sin polling, webpack tampoco recarga |
| — | **`services/api/data` del host montada** en la API | Conserva usuarios, proveedores e incidencias; Docker es el único modo de arranque, así que no hay otro uvicorn escribiendo en los mismos JSON |
| — | **Docker como único modo de arranque** en desarrollo | Un solo `.env` y un solo juego de puertos; `services/api/.env` y `uis/backoffice/.env.local` dejan de usarse (el usuario los borró). Los tests siguen en el host |
| — | **Tracker al 3002**, fuera de Docker | El brief no lo incluye y el 3001 es del backoffice; CORS del `.env.example` de la raíz: solo `http://localhost:3002` |
| — | **VPS fuera de esta entrega** | Decisión del usuario, pendiente de confirmación del profesor |

## Lo que no está verificado

- **Despliegue en el VPS.** Fuera de esta entrega (pendiente de confirmación del profesor): no hay compose de producción, ni `next build` con `API_INTERNAL_URL` como argumento de build, ni prueba en un servidor.
- **Otros sistemas.** Solo Windows 11 con Docker Desktop 29.7.2 (Compose v5.5.0, motor Linux de WSL 2). Sin pruebas en macOS ni en Linux con Docker Engine; en Linux, un bind mount entrega eventos de cambio y el polling podría no hacer falta.
- **Arquitecturas.** Las imágenes base existen para amd64 y arm64, pero solo se construyó en amd64.
- **Primer arranque en una máquina limpia.** La prueba desde cero (F4h) se hizo con las imágenes base ya descargadas.
- **Supabase caído al arrancar.** Comprobado sin Docker (`InventoryStartupError`, código 3) y con la configuración incompleta en Docker (`api` `unhealthy`, la `ui` no arranca); no se ha simulado una caída real de Supabase con el compose.
- **Accesibilidad.** Sin cambios de interfaz en este ticket; no se ha probado con lector de pantalla.
- **La regla de `/incidents` en `uis/backoffice/CLAUDE.md`** («el CSV no debe pasar por el servidor de Next»): con el rewrite, en Docker sí pasa (como proxy, en streaming). Conflicto pendiente de decisión del usuario.
