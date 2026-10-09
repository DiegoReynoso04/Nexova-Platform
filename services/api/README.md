# services/api — API de Nexova

Una sola aplicación FastAPI con estos dominios:

- **Analizador de incidentes** (`/api/incidents/*`) — descrito a continuación.
- **Directorio de proveedores** (`/suppliers*`, FastAPI + TinyDB + Pydantic) — ver [Directorio de proveedores](#directorio-de-proveedores) y `SPECS.md` Parte B.
- **Autenticación (AUTH-01)** (`/auth`, `/users`, `/profiles`; JWT + bcrypt, `User`/`Profile` en TinyDB) — ver [Autenticación](#autenticación-auth-01), `SPECS.md` Parte C y [`docs/auth-api.md`](../../docs/auth-api.md). **Todas las rutas de incidentes y proveedores exigen un JWT válido.**
- **Gestor centralizado de incidencias** (`/api/incidents`, `/api/incidents/summary`, `/api/incidents/{id}`; TinyDB + seed del histórico; validación con **400**, no 422) — ver [Gestor centralizado de incidencias](#gestor-centralizado-de-incidencias) y `SPECS.md` Parte E.

## Analizador de incidentes

API HTTP (FastAPI) que expone el análisis del CSV de incidentes de soporte de Nexova (Atención al Cliente — Roberto Díaz). Es una **capa fina** sobre el núcleo [`packages/incident-analyzer`](../../packages/incident-analyzer/README.md): no contiene reglas, métricas, redondeo ni formato de exportación propios. La CLI [`scripts/analyze.py`](../../scripts/analyze.py) usa el mismo núcleo, así que el mismo CSV da los mismos números por ambas vías.

- Contrato HTTP, errores y decisiones: [`SPECS.md`](./SPECS.md).
- Requisitos funcionales: [`docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`](../../docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md). Ese documento no define ninguna API: las rutas son una decisión de implementación (ver `SPECS.md` §2).

> ⚠️ **Uso local.** Las rutas con datos exigen JWT (AUTH-01), pero el servicio sigue pensado para un único proceso local (estado en memoria, TinyDB). No exponerlo públicamente con datos reales.

## Endpoints

Columna *Auth*: 🔓 pública · 🔒 JWT válido · 👤 propio usuario o admin · 🛡️ solo admin.

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `POST` | `/api/incidents/analyze` | 🔒 | Analiza un CSV (`multipart/form-data`, campo `file`) y devuelve las métricas en JSON |
| `GET` | `/api/incidents/results/export` | 🔒 | Descarga `results.csv` (`metric,value`) del último análisis |
| `GET` | `/health` | 🔓 | Liveness |
| `POST` | `/suppliers` | 🔒 | Registra un proveedor (201) |
| `GET` | `/suppliers` | 🔒 | Lista proveedores; filtros opcionales `?country=` y `?category=` |
| `GET` | `/suppliers/{id}` | 🔒 | Detalle de un proveedor (404 si no existe) |
| `PATCH` | `/suppliers/{id}/rate` | 🔒 | Cambia `monthly_rate` y registra `updated_at` |
| `PATCH` | `/suppliers/{id}/status` | 🔒 | `active` / `suspended` |
| `DELETE` | `/suppliers/{id}` | 🔒 | Elimina un proveedor (204; la UI no lo expone) |
| `POST` | `/users` | 🔓 | Registro (`role=user`) + `Profile` inicial opcional (`name`, `phone`, `address`) |
| `GET` | `/users` | 🛡️ | Lista usuarios |
| `GET` | `/users/{id}` | 👤 | Detalle de un usuario |
| `PUT` | `/users/{id}` | 👤 | Cambia `email`; `password` y `role` solo un admin (los demás cambian su contraseña con `POST /auth/change-password`) |
| `DELETE` | `/users/{id}` | 👤 | Elimina el usuario y su `Profile` (204) |
| `POST` | `/auth/login` | 🔓 | Formulario OAuth2 (`username` = email, `password`) → JWT |
| `GET` | `/auth/me` | 🔒 | `email`, `role` y `Profile` del usuario autenticado |
| `GET` | `/profiles/me` | 🔒 | Perfil del usuario autenticado |
| `PUT` | `/profiles/me` | 🔒 | Actualiza `name`, `phone`, `address` del propio perfil |
| `POST` | `/auth/forgot-password` | 🔓 | `{email}` → envía un enlace de restablecimiento si el email existe; siempre 200 (AUTH-03) |
| `POST` | `/auth/reset-password` | 🔓 | `{token, new_password}` → cambia la contraseña; 400 si el token es inválido, caducó o ya se usó |
| `POST` | `/auth/change-password` | 🔒 | `{current_password, new_password}` → cambia la contraseña; 400 si la actual es incorrecta |
| `POST` | `/api/incidents` | 🔒 | Gestor de incidencias: registra una incidencia (201, nace `open`); 400 por campo |
| `GET` | `/api/incidents` | 🔒 | Lista incidencias (más recientes primero); filtros opcionales `status`, `origin`, `branch`, `category` (AND) |
| `GET` | `/api/incidents/summary` | 🔒 | Totales por estado, categoría, origen y sede (todas las claves, también a 0) |
| `GET` | `/api/incidents/{id}` | 🔒 | Detalle (id UUID; 404 si no existe o no es un UUID) |
| `PATCH` | `/api/incidents/{id}/status` | 🔒 | Cambia solo el estado; 400 `invalid_status_transition` si el ciclo de vida no lo permite |

Sin token válido → **401**; token válido sobre un recurso ajeno o una acción de admin → **403** (`SPECS.md` §21). Ninguna respuesta incluye `password` ni `hashed_password`.

Si un archivo TinyDB (`suppliers.json`, `auth.json` o `incidents.json`) no se puede abrir, leer o escribir, o está corrupto, la ruta responde **503** `{"detail": "storage is temporarily unavailable", "code": "storage_unavailable"}`, sin la ruta del archivo. El registro dice solo el almacén y la clase del error: `storage auth is unavailable: JSONDecodeError`. Con `auth.json` dañado fallan el login y todas las rutas protegidas. Para recuperarlo, restaura el archivo desde una copia o bórralo: se perderán sus datos y, con `auth.json`, habrá que recrear el administrador con `create-admin`. Detalle: `SPECS.md` §4 y §5.

Documentación interactiva de FastAPI en `http://localhost:8000/docs` con el servidor arrancado.

## Requisitos

Python 3.11 o superior (verificado con 3.14.6). Dependencias (`pyproject.toml`), acotadas a las versiones probadas (versiones exactas en [`uv.lock`](./uv.lock), versionado): `fastapi>=0.141,<0.142`, `python-multipart>=0.0.32,<0.1`, `uvicorn>=0.53,<0.54`, `tinydb>=4.9,<4.10`, `libpass[bcrypt]>=1.9.3,<1.10` y `python-jose[cryptography]>=3.5,<3.6` (AUTH-01) y, para tests (extra `dev`), `httpx>=0.28,<0.29`. Sin pytest ni librerías de configuración.

## Instalación (desde la raíz del monorepo)

```bash
python -m venv services/api/.venv
# Windows (PowerShell):  services\api\.venv\Scripts\Activate.ps1
# Linux/macOS:           source services/api/.venv/bin/activate
python -m pip install -e packages/shared -e packages/incident-analyzer -e "services/api[dev]"
```

**Instalar siempre los tres en la misma orden.** El núcleo (`packages/incident-analyzer`) y la validación compartida que usa (`packages/shared`, paquete `nexova_shared`) no están publicados y **no** figuran en las dependencias de `pyproject.toml` a propósito: sus nombres están libres en PyPI y declararlos haría que pip los buscase allí (*dependency confusion*). `pip install -e "services/api[dev]"` a solas instala el servicio pero no el núcleo, y la API fallará al importar `incident_analyzer`. (Si falta solo `nexova_shared`, el núcleo lo encuentra igualmente en el monorepo, pero el venv documentado lo instala.) `.venv/` y `*.egg-info/` están en `.gitignore`.

## Arranque

La API necesita `JWT_SECRET_KEY` y `ACCESS_TOKEN_EXPIRE_MINUTES`; sin ellas **no arranca** (`ConfigError`). Se guardan en `services/api/.env` (ignorado por git) y se cargan con `uv run --env-file`:

```bash
cd services/api
cp .env.example .env    # rellenar JWT_SECRET_KEY: python -c "import secrets; print(secrets.token_urlsafe(48))"
uv run --env-file .env uvicorn app.main:create_app --factory --port 8000 --workers 1
```

Con el venv activado y sin uv, exportar antes las variables (ver abajo) y lanzar `uvicorn app.main:create_app --factory --port 8000 --workers 1`.

**Siempre con un único worker**: el último análisis vive en memoria del proceso y TinyDB (proveedores y usuarios) solo se protege con un bloqueo dentro del proceso.

### Configuración

Variables de entorno (la API **no** carga archivos `.env` por sí sola, no usa `python-dotenv`: las carga `uv run --env-file .env`; [`.env.example`](./.env.example) las documenta):

| Variable | Por defecto | Uso |
|---|---|---|
| `JWT_SECRET_KEY` | — (**obligatoria**) | Clave de firma HS256 de los JWT, mínimo 32 caracteres. Nunca en el código ni en git |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | — (**obligatoria**) | Validez del token de acceso en minutos (entero > 0) |
| `AUTH_DB_PATH` | `services/api/data/auth.json` | Archivo TinyDB de `User` y `Profile` (API y `create-admin`). `data/` está en `.gitignore` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Orígenes permitidos, separados por comas. `*` se rechaza al arrancar. Con AUTH-02 el Talent Pipeline Tracker (puerto 3001) también llama a la API para login, registro y perfil: en local usar `http://localhost:3000,http://localhost:3001` (así viene en `.env.example`) |
| `SUPPLIERS_DB_PATH` | `services/api/data/suppliers.json` | Archivo TinyDB del directorio de proveedores (API y seeder). `data/` está en `.gitignore` |
| `INCIDENTS_DB_PATH` | `services/api/data/incidents.json` | Archivo TinyDB del gestor centralizado de incidencias: tabla `incidents` y tabla `seed_keys` (solo el SHA-256 de la clave de origen de cada registro histórico cargado; nunca el `ticket_id` en claro). Lo usan el repositorio de `app/modules/incident_manager/` y `scripts/seed_incidents.py`. `data/` está en `.gitignore` |
| `RESEND_API_KEY` | — (opcional) | API key de [Resend](https://resend.com/) para enviar el email de restablecimiento (AUTH-03). Nunca en el código ni en git. Sin ella (y sin las dos siguientes) la API arranca, pero no envía emails |
| `EMAIL_FROM` | — (con `RESEND_API_KEY`) | Remitente, p. ej. `Nexova <onboarding@resend.dev>` (remitente de pruebas de Resend: solo entrega a la dirección de tu cuenta de Resend) |
| `PASSWORD_RESET_URL` | — (con `RESEND_API_KEY`) | URL absoluta de la página de restablecimiento del frontend; el enlace añade `?token=…`. En local: `http://localhost:3000/reset-password` |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | `30` | Vigencia del enlace, entre 15 y 60 minutos |
| `MAX_UPLOAD_BYTES` | `1048576` (1 MiB) | Límite técnico del **body HTTP completo** (CSV + cabeceras y delimitadores multipart), **no del CSV**: el CSV máximo es algo menor. Decisión de la API, no requisito del cliente. Detalle en `SPECS.md` §3.1 |

```powershell
$env:CORS_ALLOWED_ORIGINS = "http://localhost:3000,http://localhost:3001"
$env:SUPPLIERS_DB_PATH = "C:\ruta\absoluta\suppliers.json"   # bash: export SUPPLIERS_DB_PATH=/ruta/absoluta/suppliers.json
```

Una ruta relativa en `SUPPLIERS_DB_PATH` se resuelve desde el directorio en el que se lanza cada proceso: para que la API y el seeder usen el mismo archivo, usar una ruta absoluta o lanzar ambos desde `services/api`. Sin la variable, los dos usan `services/api/data/suppliers.json`.

## Directorio de proveedores

Registro oficial de proveedores de Nexova (Patricia Solís, HR Manager). Contexto: [`docs/ligthweight-storage-api.md`](../../docs/ligthweight-storage-api.md); contrato y decisiones: `SPECS.md` Parte B.

- **Persistencia:** TinyDB en `data/suppliers.json` (configurable con `SUPPLIERS_DB_PATH`). Los datos sobreviven a reinicios. La API **no** carga datos por sí sola: sin seeder, el directorio empieza vacío.
- **Validación:** Pydantic rechaza con 422 cualquier entrada que no cumpla el modelo (país, moneda coherente, categorías, tarifa > 0, estado, fecha `YYYY-MM-DD`) antes de tocar la base.
- **`updated_at`:** lo genera el sistema (UTC) al crear y en cada cambio de tarifa; el cambio de estado no lo modifica.
- **Estados:** `active` / `suspended`. Suspender es la forma prevista de dar de baja un proveedor (se conserva el historial); `DELETE` existe en la API pero el backoffice no lo usa (`SPECS.md` §10).
- **Arquitectura:** `routes/suppliers.py` (endpoints) → modelos Pydantic de `models.py` (validan la entrada; 422 si no cumple) → `SupplierRepository` de `database.py` (única capa que toca TinyDB). El seeder (`seed.py`) usa el mismo repositorio y la misma validación.
- **Códigos HTTP:** `201` alta · `200` consultas y `PATCH` · `204` borrado · `404` `supplier_not_found` (id inexistente) · `422` `validation_error` (cuerpo, filtro o id inválidos; lista `{loc, msg, type}`) · `503` `storage_unavailable` (`suppliers.json` ilegible o corrupto). Filtros de `GET /suppliers`: `country` (`Spain`/`USA`) y `category` (una de las 9 del contexto), combinables. Contrato completo: `SPECS.md` §11–§12.

**Puesta en marcha del directorio** (desde cero):

1. Instalar el venv del servicio (sección [Instalación](#instalación-desde-la-raíz-del-monorepo)).
2. Cargar los proveedores: `cd services/api && uv run seed` (ver abajo).
3. Arrancar la API (sección [Arranque](#arranque)); Swagger en `http://localhost:8000/docs`.
4. Para la interfaz web, arrancar el backoffice y abrir `http://localhost:3000/suppliers` (ver [`uis/backoffice/README.md`](../../uis/backoffice/README.md)).

### Seeder

Carga los 15 proveedores del contexto. Idempotente: solo inserta los que no existen (por `name`) y confirma en consola cuántos insertó. Con una variable de entorno inválida (por ejemplo, la configuración de email incompleta) o una base `SUPPLIERS_DB_PATH` ilegible o corrupta, escribe el motivo en stderr y termina con código `1`, sin traceback.

```bash
cd services/api
uv run seed
```

`uv run` usa el `.venv` de `services/api` (el mismo del flujo con pip) y, antes de ejecutar, lo sincroniza con `pyproject.toml`/`uv.lock`. Esa sincronización **no siempre conserva** el núcleo `incident-analyzer`, que se instala aparte con pip: `uv run seed` y `uv run --env-file .env uvicorn …` lo han conservado, pero `uv run --extra dev …` lo desinstaló (comprobado el 2026-09-30), y a partir de ahí la API de incidentes y los tests fallan al importar `incident_analyzer`. Con el venv ya instalado, `uv run --no-sync …` lo usa tal cual, sin sincronizar. Si el núcleo desaparece, se reinstala desde la raíz con `services\api\.venv\Scripts\python -m pip install --no-deps -e packages/incident-analyzer` (Linux/macOS: `services/api/.venv/bin/python …`). El seeder no importa el núcleo, por lo que `uv run seed` también funciona en un clon limpio con solo uv instalado.

> **Nota sobre `uv sync`:** `uv sync` sincroniza el entorno de forma **exacta** con `uv.lock` y elimina los paquetes que no declara `pyproject.toml`; en este `.venv` eso incluye el núcleo `incident-analyzer` (instalado aparte, ver Instalación) y el extra `dev` si no se pide, con lo que la API de incidentes y los tests dejarían de funcionar hasta reinstalarlos. Para cargar los proveedores, la operación prevista es `uv run seed`.

Sin uv, con el venv del servicio ya instalado: `python -m app.seed` (desde `services/api`). Ejecutarlo con la API parada o sin peticiones de escritura en curso (TinyDB no coordina procesos distintos).

## Autenticación (AUTH-01)

Contexto y guía paso a paso (incluido el flujo en `/docs`): [`docs/auth-api.md`](../../docs/auth-api.md). Contrato, decisiones D-AUTH-1…13 y matriz de permisos: `SPECS.md` Parte C.

- **Almacenamiento:** `User` (solo credenciales) y `Profile` (`name`, `phone`, `address`) viven **solo en TinyDB**, en `data/auth.json` (`AUTH_DB_PATH`), separado de los proveedores. Ids UUID propios; `Profile.user_id` = `User.id`. Nunca en PostgreSQL/Supabase.
- **Contraseñas:** hash bcrypt con `libpass` (`from passlib.hash import bcrypt`); 8 caracteres mínimo y 72 bytes máximo, validado antes del hash.
- **JWT:** HS256 con `JWT_SECRET_KEY`; claims `sub` (= `User.id`), `iat`, `exp` (+`ACCESS_TOKEN_EXPIRE_MINUTES`). Login con formulario OAuth2 en `POST /auth/login` (`username` = email): el botón **Authorize** de `/docs` funciona directamente.
- **Protección:** `get_current_user` (`app/auth/dependencies.py`) se aplica a los routers de incidentes y proveedores y a las rutas privadas de `/users`, `/auth/me`, `/auth/change-password` y `/profiles`.

### Recuperación y cambio de contraseña (AUTH-03)

Contexto: [`docs/auth-password-reset.md`](../../docs/auth-password-reset.md). Contrato y decisiones D-PWD-1…12: `SPECS.md` Parte D. **Guía para revisar AUTH-03** (endpoints, arranque, variables, validación manual paso a paso, prueba de H-1, Resend sin dominio propio, tests y deuda técnica): ese mismo documento, §5–§14.

- **Envío con Resend** por HTTP (`urllib`, sin dependencias nuevas). Configurar `RESEND_API_KEY`, `EMAIL_FROM` y `PASSWORD_RESET_URL` en `services/api/.env` (ver `.env.example`) y arrancar con `uv run --env-file .env …` (la API no lee `.env` por sí sola). Con el remitente de pruebas `onboarding@resend.dev` y sin dominio verificado, Resend restringe los destinatarios: para una demo, registra en Nexova un usuario con el destinatario de pruebas `delivered@resend.dev` (detalle en `docs/auth-password-reset.md` §10).
- **Token de un solo uso:** aleatorio, guardado solo como SHA-256 en `auth.json` (`password_reset_tokens`), caduca a los `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`. Un enlace nuevo, un reset correcto o un cambio de contraseña invalidan los pendientes.
- **Sin enumeración:** `forgot-password` responde 200 con el mismo cuerpo exista o no el email; el email se envía después de responder.
- **Auditoría:** cada evento queda en `password_audit` (`auth.json`) con IP y fecha, sin email ni token.
- **Un solo camino para cambiar la propia contraseña:** `PUT /users/{id}` con `password` responde 403 si no eres admin (hallazgo H-1 de la auditoría de seguridad); usa `POST /auth/change-password`, que exige la contraseña actual. Un admin puede seguir fijando contraseñas con `PUT /users/{id}`.

### Primer administrador

`POST /users` siempre crea usuarios `user`. El primer admin se crea con un comando explícito (la contraseña se pide oculta, dos veces; no se imprime ni se pasa por argumento). Termina con código `1`, sin traceback ni crear nada, si el email ya existe, la entrada no es válida, se cancela (Ctrl+C o fin de entrada), falla la configuración o `auth.json` no se puede abrir o está corrupto:

```bash
cd services/api
uv run --env-file .env create-admin --email admin@example.com --name "Administración"
```

Sin uv, con el venv del servicio: `python -m app.auth.create_admin --email ...`. Si el email ya existe, termina con código 1 sin tocar nada. Como el seeder, ejecutarlo sin escrituras de la API en curso (TinyDB no coordina procesos distintos).

## Limitaciones conocidas (deliberadas en esta fase)

- **El último análisis se pierde al reiniciar** el proceso: no hay persistencia.
- Se guarda **el último análisis que termina correctamente**; un POST fallido no lo cambia. Es **global al proceso**, no por usuario, y con peticiones concurrentes gana la que termina después. `X-Analysis-Id` en la exportación identifica el análisis descargado.
- **Autenticación sin estado**: no hay revocación ni refresh de tokens; cambiar o restablecer la contraseña (AUTH-03) o el rol no invalida los tokens ya emitidos hasta que expiran. Sin permisos por rol en las rutas de incidentes y proveedores (basta un token válido).
- Con `MAX_UPLOAD_BYTES` > 1 MiB, Starlette puede volcar el archivo subido a un temporal en disco durante la petición.
- Las respuestas 200 de análisis y exportación llevan `Cache-Control: no-store`.

## Gestor centralizado de incidencias

Registro estructurado de incidencias de Nexova (Sergio Molina, CTO; Roberto Díaz, Customer Support Lead). Contexto: [`docs/centralized-incident-manager.md`](../../docs/centralized-incident-manager.md). Vocabulario, reglas y mapeo del CSV: [`packages/shared`](../../packages/shared/README.md) (`nexova_shared.incidents`); aquí no se repite ningún valor. Contrato HTTP y decisiones (P4-1…P4-13, tomadas por el usuario): `SPECS.md` Parte E. Interfaz web: `uis/backoffice` → `/incident-manager` y `/incident-manager/new`. **Cómo revisarlo** (comandos de PowerShell, salidas esperadas y trazabilidad): [`docs/centralized-incident-manager-review.md`](../../docs/centralized-incident-manager-review.md).

- **Persistencia:** TinyDB en `data/incidents.json` (configurable con `INCIDENTS_DB_PATH`), tablas `incidents` (id UUID v4, `created_at`/`updated_at` en UTC generados por el repositorio) y `seed_keys` (solo el SHA-256 de la clave de origen de cada registro histórico y el `id` de la incidencia creada; el `ticket_id` nunca se guarda en claro).
- **API** (`app/modules/incident_manager/router.py`, router propio con prefijo `/api/incidents` y JWT): `POST` (201), `GET` con filtros, `GET /summary`, `GET /{id}` y `PATCH /{id}/status`. A diferencia del resto de la API, **la validación responde 400** con `{"code": "validation_error", "detail": [{"field", "error", "message"}]}` (también si el body no es JSON); una transición no permitida, 400 `invalid_status_transition`. Las rutas con id usan el convertidor `uuid`: `GET /api/incidents/analyze` sigue en 405 y un id que no es UUID da 404. Prueba manual en `/docs`: *Authorize* → `POST /api/incidents` → `PATCH …/status`.
- **Repositorio** (`app/modules/incident_manager/repository.py`): filtros combinables por `status`, `origin`, `branch` y `category`; cambio de estado solo por transición válida del ciclo de vida (actualiza `updated_at`); resumen con todas las claves de cada enumerado. Sin base o con la base vacía, las lecturas devuelven lista vacía y totales a cero, y no crean el archivo.

### Seed de datos históricos (`scripts/seed_incidents.py`)

Carga el CSV del helpdesk (el del analizador de incidentes) con `origin = customer` y `branch = central`. Cada fila pasa por las 7 reglas del analizador y por el mapeo del CONTEXT (estado, categoría, `description` → `title` de 120 caracteres, `date` → `created_at` a medianoche UTC); nunca se inserta una fila tal cual. Es **idempotente**: una segunda ejecución no duplica nada.

Se ejecuta con el intérprete del venv de `services/api` (necesita `tinydb` y `pydantic`), desde la raíz del monorepo. Con el **fixture sintético de aceptación** (100 filas, 96 válidas; no son datos de Nexova) y una base temporal:

```bash
# Windows (PowerShell)
services\api\.venv\Scripts\python scripts\seed_incidents.py packages\incident-analyzer\tests\fixtures\incidents-acceptance-synthetic.csv --db $env:TEMP\incidents-demo.json
# Linux/macOS
services/api/.venv/bin/python scripts/seed_incidents.py packages/incident-analyzer/tests/fixtures/incidents-acceptance-synthetic.csv --db /tmp/incidents-demo.json
```

- Sin ruta del CSV se lee `data/raw/incidents/incidents-nexova.csv` (el dataset real, ignorado por git). Sin `--db` se usa `INCIDENTS_DB_PATH` o, si no está definida, `services/api/data/incidents.json`.
- Informe final en consola: filas leídas, insertadas, ya existentes, inválidas (número de fila + código de regla), no mapeables (número de fila + motivo), duplicadas en el archivo y total en la base. **Nunca** muestra contenido de las filas (ni emails, ni descripciones, ni `ticket_id`).
- Códigos de salida: `0` correcto · `1` CSV inexistente, no UTF-8 o con una cabecera sin las columnas del analizador · `2` argumentos, configuración o entorno incorrectos (por ejemplo, ejecutarlo con un Python sin el venv, o una base `--db`/`INCIDENTS_DB_PATH` que no se puede abrir o escribir, o que está corrupta). Ningún error termina con traceback; ante una base dañada, stderr muestra la línea del registro (`storage incidents is unavailable: <Clase>`) y el mensaje del script con solo el nombre del archivo.
- Con el fixture de aceptación: 96 insertadas y 4 inválidas (filas 18, 45, 71 y 93); en la segunda ejecución, 0 insertadas y 96 ya existentes.
- Igual que el seeder de proveedores: ejecutarlo con la API parada o sin escrituras en curso.

## Tests

La suite necesita las dependencias del venv de `services/api` (con el Python global falla al importar `fastapi`). Desde la raíz del monorepo, **sin necesidad de activar el venv**, usando su intérprete directamente:

```bash
# Windows
services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api
# Linux/macOS
services/api/.venv/bin/python -m unittest discover -s services/api/tests -t services/api
```

Equivalente con el venv activado: `python -m unittest discover -s services/api/tests -t services/api`.

Con uv, desde `services/api` y con el venv ya instalado:

```bash
uv run --no-sync python -m unittest discover -s tests -t .
```

**Sin `--no-sync`** (por ejemplo `uv run --extra dev python -m unittest …`), uv sincroniza el venv y puede desinstalar el núcleo `incident-analyzer` (ver [Seeder](#seeder)). La suite usa `unittest` y **no hay pytest** (D-API-3 en `SPECS.md`): `uv run pytest` responde `program not found`.

La suite del núcleo (Fase 1) no necesita el venv: `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` con cualquier Python ≥ 3.11.

| Archivo | Qué cubre |
|---|---|
| `test_analyze.py` | POST correcto, contrato JSON, orden de reglas/categorías/estados, paridad con el núcleo, `/health` |
| `test_export.py` | 404 sin análisis, cabeceras, cuerpo idéntico al `results.csv` de la CLI, sustitución A→B, B fallido (400/413/415/422/500) no borra A, `Cache-Control: no-store` |
| `test_errors.py` | 400/404/405 (con `Allow`)/413/415/422, límite con y sin `Content-Length` incluida la frontera exacta (`MAX` → 200, `MAX+1` → 413), ausencia de volcado a disco, configuración, CORS (métodos declarados, incluido `PUT` para `/profiles/me` desde AUTH-02) |
| `test_privacy.py` | Ningún email ni dato de registro en respuestas, errores, export ni logs; 500 opaco con excepción que contiene un email |
| `test_architecture.py` | La API no duplica reglas, categorías, estados, regex, lógica de score ni redondeo; solo usa la API pública del núcleo; el núcleo no importa FastAPI |
| `test_suppliers_api.py` | Proveedores: modelo = CONTEXT, 422 antes de tocar TinyDB (país, estado, tarifa ≤ 0, moneda, categorías, fecha, campos del sistema), 201/404/204, filtros país/categoría combinados, `updated_at` en cambio de tarifa y no en cambio de estado, CORS PATCH/DELETE |
| `test_suppliers_seed.py` | Seeder = `SUPPLIERS_SEED` del CONTEXT, idempotente, no sobrescribe, salida en consola; persistencia tras reiniciar la app; `main()` con configuración inválida o base corrupta → código 1 sin traceback |
| `test_auth.py` | AUTH-01: registro (hash bcrypt, sin texto plano, `Profile` automático, `role=user` fijado por el backend y `role` en el body → 422, 409), login (401 genérico, solo formulario), JWT (`sub`/`exp`, expirado, mal formado, otra clave, `alg: none`), `/users` (401/403/admin, propio vs ajeno, cambio de rol, borrado en cascada), `/profiles/me`, `/auth/me` sin credenciales |
| `test_auth_protection.py` | Las 8 rutas existentes: 401 sin token o con token inválido/expirado y funcionamiento con token válido; rutas públicas; esquema OAuth2 en OpenAPI; CORS `Authorization`; `JWT_SECRET_KEY`/`ACCESS_TOKEN_EXPIRE_MINUTES` obligatorias |
| `test_incident_manager_repository.py` | Gestor de incidencias: base inexistente o vacía (lista vacía, resumen a cero, sin crear el archivo), id UUID y fechas UTC, filtros combinados, resumen con todas las claves, transiciones válidas/inválidas/finales, seed idempotente, totales del CONTEXT y `seed_keys` sin `ticket_id` en claro |
| `test_incident_manager_api.py` | Gestor de incidencias por HTTP: caso feliz y cada 400 de cada ruta (ausente, vacío, valor no permitido, título > 120, campo desconocido, id/fechas del cliente, `status` ≠ `open` al crear, filtro inválido, body no JSON/no objeto, PATCH sin `status`), las 16 transiciones, base vacía, totales tras el seed, 401 en las 5 rutas, 404 (inexistente / no UUID), 500 opaco, OpenAPI y no regresión (405 de `/analyze`, 404 de rutas desconocidas, 422 de proveedores y auth) |
| `test_incident_manager_seed.py` | `scripts/seed_incidents.py`: informe exacto con el fixture de aceptación (96 insertadas, filas inválidas 18/45/71/93), segunda ejecución sin duplicados, resumen tras el seed, no mapeables y duplicadas por número de fila, ningún contenido de fila en consola ni emails/`ticket_id` en la base, códigos de salida (CSV inexistente, cabecera de otro esquema, vacío, no UTF-8; `--db` como directorio o corrupta → `2` sin traceback) e `INCIDENTS_DB_PATH` |
| `test_create_admin.py` | `create-admin`: admin + `Profile` + hash bcrypt, email existente, contraseñas distintas, entrada inválida, fin de entrada en `input`, Ctrl+C en `getpass`, `auth.json` corrupto y `ConfigError` (código 1, sin crear nada); nunca imprime la contraseña |
| `test_password_reset.py` | AUTH-03 (forgot/reset/change-password, auditoría, sender de Resend). Incluye las respuestas cortadas del proveedor (`IncompleteRead`, `BadStatusLine`, `LineTooLong`): son `EmailDeliveryError` y se registran como fallo de entrega, no como 500 |
| `test_storage.py` | 503 `storage_unavailable` en los tres almacenes: JSON inválido, no UTF-8, otra forma, ruta que no se puede abrir y fallo de escritura. Incluye el login con `auth.json` corrupto. Comprueba que ni el cuerpo ni el log llevan la ruta ni el contenido y que el error no arrastra la excepción original. Regresión del ámbito: el 422 de proveedores, el 400 del gestor (también la transición lanzada dentro de la operación), el 409 y un `ValidationError` de Pydantic dentro de la operación (500, no 503) |

Los tests reutilizan el fixture sintético del núcleo (`example.invalid`). Como las rutas de incidentes y proveedores exigen JWT, `tests/support.py` crea para cada cliente una base de usuarios temporal y un token válido (la clave JWT de test se genera al importar; no hay ninguna fija). Los tests de AUTH-01 hashean con bcrypt real, por eso la suite tarda alrededor de un minuto. El núcleo tiene su propia suite (ver su README).

**Aviso conocido:** Starlette 1.7 emite `StarletteDeprecationWarning` recomendando `httpx2` para `TestClient`. Se mantiene `httpx` (la dependencia autorizada); los tests pasan igual.

## Estructura

```text
app/
├── main.py                  # create_app(): middlewares, handlers, routers (+ protección JWT), /health
├── core/
│   ├── config.py            # Settings desde variables de entorno (stdlib); exige la config JWT al arrancar
│   ├── errors.py            # formato {detail, code}, 401/403/409, 422 saneado, 503 de almacenamiento, middleware de 500 opaco
│   ├── limits.py            # límite del body (Content-Length + conteo en streaming)
│   └── storage.py           # GuardedJSONStorage: fallos del archivo TinyDB → 503 storage_unavailable
├── auth/                    # AUTH-01
│   ├── models.py            # User/Profile (Pydantic), UserRole, validación de email y contraseña
│   ├── repository.py        # AuthRepository: única capa que toca TinyDB de usuarios y perfiles
│   ├── security.py          # bcrypt (libpass) y JWT (python-jose)
│   ├── service.py           # UserService: crear, obtener por id/email, actualizar, eliminar, login, contraseñas
│   ├── email.py             # AUTH-03: envío con Resend (urllib) y texto del email de restablecimiento
│   ├── dependencies.py      # OAuth2PasswordBearer, get_current_user, require_admin, ensure_self_or_admin
│   └── create_admin.py      # entry point de `uv run create-admin`
├── routes/auth.py           # POST /auth/login, GET /auth/me; AUTH-03: forgot/reset/change-password
├── routes/users.py          # CRUD /users
├── routes/profiles.py       # GET/PUT /profiles/me
├── models.py                # Proveedores: modelos Pydantic, categorías y estados del contexto
├── database.py              # Proveedores: TinyDB (SupplierRepository, thread-safe, un archivo JSON)
├── seed.py                  # Proveedores: SUPPLIERS_SEED + entry point de `uv run seed`
├── routes/suppliers.py      # Proveedores: 6 endpoints /suppliers
├── modules/incident_manager/  # Gestor centralizado de incidencias (SPECS Parte E)
│   ├── router.py            # 5 endpoints /api/incidents, 400 propio (IncidentManagerRoute)
│   ├── models.py            # Incident, IncidentSummary (enums de nexova_shared)
│   └── repository.py        # IncidentRepository: TinyDB (incidents + seed_keys), filtros, transiciones, resumen, seed
└── modules/incidents/
    ├── router.py            # 2 endpoints: request → servicio → respuesta
    ├── schemas.py           # contrato JSON (traducción de AnalysisResult, sin cálculo)
    ├── service.py           # extensión .csv, llamada al núcleo, guardado del resultado
    └── store.py             # LastResultStore (memoria, thread-safe)
tests/
```
