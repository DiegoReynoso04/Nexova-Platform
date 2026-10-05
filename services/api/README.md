# services/api — API de Nexova

Una sola aplicación FastAPI con tres dominios:

- **Analizador de incidentes** (`/api/incidents/*`) — descrito a continuación.
- **Directorio de proveedores** (`/suppliers*`, FastAPI + TinyDB + Pydantic) — ver [Directorio de proveedores](#directorio-de-proveedores) y `SPECS.md` Parte B.
- **Autenticación (AUTH-01)** (`/auth`, `/users`, `/profiles`; JWT + bcrypt, `User`/`Profile` en TinyDB) — ver [Autenticación](#autenticación-auth-01), `SPECS.md` Parte C y [`docs/auth-api.md`](../../docs/auth-api.md). **Todas las rutas de incidentes y proveedores exigen un JWT válido.**

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
| `PUT` | `/users/{id}` | 👤 | Cambia `email`/`password`; `role` solo un admin |
| `DELETE` | `/users/{id}` | 👤 | Elimina el usuario y su `Profile` (204) |
| `POST` | `/auth/login` | 🔓 | Formulario OAuth2 (`username` = email, `password`) → JWT |
| `GET` | `/auth/me` | 🔒 | `email`, `role` y `Profile` del usuario autenticado |
| `GET` | `/profiles/me` | 🔒 | Perfil del usuario autenticado |
| `PUT` | `/profiles/me` | 🔒 | Actualiza `name`, `phone`, `address` del propio perfil |

Sin token válido → **401**; token válido sobre un recurso ajeno o una acción de admin → **403** (`SPECS.md` §21). Ninguna respuesta incluye `password` ni `hashed_password`.

Documentación interactiva de FastAPI en `http://localhost:8000/docs` con el servidor arrancado.

## Requisitos

Python 3.11 o superior (verificado con 3.14.6). Dependencias (`pyproject.toml`), acotadas a las versiones probadas (versiones exactas en [`uv.lock`](./uv.lock), versionado): `fastapi>=0.141,<0.142`, `python-multipart>=0.0.32,<0.1`, `uvicorn>=0.53,<0.54`, `tinydb>=4.9,<4.10`, `libpass[bcrypt]>=1.9.3,<1.10` y `python-jose[cryptography]>=3.5,<3.6` (AUTH-01) y, para tests (extra `dev`), `httpx>=0.28,<0.29`. Sin pytest ni librerías de configuración.

## Instalación (desde la raíz del monorepo)

```bash
python -m venv services/api/.venv
# Windows (PowerShell):  services\api\.venv\Scripts\Activate.ps1
# Linux/macOS:           source services/api/.venv/bin/activate
python -m pip install -e packages/incident-analyzer -e "services/api[dev]"
```

**Instalar siempre los dos en la misma orden.** El núcleo (`packages/incident-analyzer`) no está publicado y **no** figura en las dependencias de `pyproject.toml` a propósito: su nombre está libre en PyPI y declararlo haría que pip lo buscase allí (*dependency confusion*). `pip install -e "services/api[dev]"` a solas instala el servicio pero no el núcleo, y la API fallará al importar `incident_analyzer`. `.venv/` y `*.egg-info/` están en `.gitignore`.

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
- **Códigos HTTP:** `201` alta · `200` consultas y `PATCH` · `204` borrado · `404` `supplier_not_found` (id inexistente) · `422` `validation_error` (cuerpo, filtro o id inválidos; lista `{loc, msg, type}`). Filtros de `GET /suppliers`: `country` (`Spain`/`USA`) y `category` (una de las 9 del contexto), combinables. Contrato completo: `SPECS.md` §11–§12.

**Puesta en marcha del directorio** (desde cero):

1. Instalar el venv del servicio (sección [Instalación](#instalación-desde-la-raíz-del-monorepo)).
2. Cargar los proveedores: `cd services/api && uv run seed` (ver abajo).
3. Arrancar la API (sección [Arranque](#arranque)); Swagger en `http://localhost:8000/docs`.
4. Para la interfaz web, arrancar el backoffice y abrir `http://localhost:3000/suppliers` (ver [`uis/backoffice/README.md`](../../uis/backoffice/README.md)).

### Seeder

Carga los 15 proveedores del contexto. Idempotente: solo inserta los que no existen (por `name`) y confirma en consola cuántos insertó.

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
- **Protección:** `get_current_user` (`app/auth/dependencies.py`) se aplica a los routers de incidentes y proveedores y a las rutas privadas de `/users`, `/auth/me` y `/profiles`.

### Primer administrador

`POST /users` siempre crea usuarios `user`. El primer admin se crea con un comando explícito (la contraseña se pide oculta, dos veces; no se imprime ni se pasa por argumento):

```bash
cd services/api
uv run --env-file .env create-admin --email admin@example.com --name "Administración"
```

Sin uv, con el venv del servicio: `python -m app.auth.create_admin --email ...`. Si el email ya existe, termina con código 1 sin tocar nada. Como el seeder, ejecutarlo sin escrituras de la API en curso (TinyDB no coordina procesos distintos).

## Limitaciones conocidas (deliberadas en esta fase)

- **El último análisis se pierde al reiniciar** el proceso: no hay persistencia.
- Se guarda **el último análisis que termina correctamente**; un POST fallido no lo cambia. Es **global al proceso**, no por usuario, y con peticiones concurrentes gana la que termina después. `X-Analysis-Id` en la exportación identifica el análisis descargado.
- **Autenticación sin estado**: no hay revocación ni refresh de tokens; cambiar contraseña o rol no invalida los tokens ya emitidos hasta que expiran. Sin permisos por rol en las rutas de incidentes y proveedores (basta un token válido).
- Con `MAX_UPLOAD_BYTES` > 1 MiB, Starlette puede volcar el archivo subido a un temporal en disco durante la petición.
- Las respuestas 200 de análisis y exportación llevan `Cache-Control: no-store`.

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
| `test_suppliers_seed.py` | Seeder = `SUPPLIERS_SEED` del CONTEXT, idempotente, no sobrescribe, salida en consola; persistencia tras reiniciar la app |
| `test_auth.py` | AUTH-01: registro (hash bcrypt, sin texto plano, `Profile` automático, `role=user` fijado por el backend y `role` en el body → 422, 409), login (401 genérico, solo formulario), JWT (`sub`/`exp`, expirado, mal formado, otra clave, `alg: none`), `/users` (401/403/admin, propio vs ajeno, cambio de rol, borrado en cascada), `/profiles/me`, `/auth/me` sin credenciales |
| `test_auth_protection.py` | Las 8 rutas existentes: 401 sin token o con token inválido/expirado y funcionamiento con token válido; rutas públicas; esquema OAuth2 en OpenAPI; CORS `Authorization`; `JWT_SECRET_KEY`/`ACCESS_TOKEN_EXPIRE_MINUTES` obligatorias |
| `test_create_admin.py` | `create-admin`: admin + `Profile` + hash bcrypt, email existente, contraseñas distintas, entrada inválida; nunca imprime la contraseña |

Los tests reutilizan el fixture sintético del núcleo (`example.invalid`). Como las rutas de incidentes y proveedores exigen JWT, `tests/support.py` crea para cada cliente una base de usuarios temporal y un token válido (la clave JWT de test se genera al importar; no hay ninguna fija). Los tests de AUTH-01 hashean con bcrypt real, por eso la suite tarda alrededor de un minuto. El núcleo tiene su propia suite (ver su README).

**Aviso conocido:** Starlette 1.7 emite `StarletteDeprecationWarning` recomendando `httpx2` para `TestClient`. Se mantiene `httpx` (la dependencia autorizada); los tests pasan igual.

## Estructura

```text
app/
├── main.py                  # create_app(): middlewares, handlers, routers (+ protección JWT), /health
├── core/
│   ├── config.py            # Settings desde variables de entorno (stdlib); exige la config JWT al arrancar
│   ├── errors.py            # formato {detail, code}, 401/403/409, 422 saneado, middleware de 500 opaco
│   └── limits.py            # límite del body (Content-Length + conteo en streaming)
├── auth/                    # AUTH-01
│   ├── models.py            # User/Profile (Pydantic), UserRole, validación de email y contraseña
│   ├── repository.py        # AuthRepository: única capa que toca TinyDB de usuarios y perfiles
│   ├── security.py          # bcrypt (libpass) y JWT (python-jose)
│   ├── service.py           # UserService: crear, obtener por id/email, actualizar, eliminar, login
│   ├── dependencies.py      # OAuth2PasswordBearer, get_current_user, require_admin, ensure_self_or_admin
│   └── create_admin.py      # entry point de `uv run create-admin`
├── routes/auth.py           # POST /auth/login, GET /auth/me
├── routes/users.py          # CRUD /users
├── routes/profiles.py       # GET/PUT /profiles/me
├── models.py                # Proveedores: modelos Pydantic, categorías y estados del contexto
├── database.py              # Proveedores: TinyDB (SupplierRepository, thread-safe, un archivo JSON)
├── seed.py                  # Proveedores: SUPPLIERS_SEED + entry point de `uv run seed`
├── routes/suppliers.py      # Proveedores: 6 endpoints /suppliers
└── modules/incidents/
    ├── router.py            # 2 endpoints: request → servicio → respuesta
    ├── schemas.py           # contrato JSON (traducción de AnalysisResult, sin cálculo)
    ├── service.py           # extensión .csv, llamada al núcleo, guardado del resultado
    └── store.py             # LastResultStore (memoria, thread-safe)
tests/
```
