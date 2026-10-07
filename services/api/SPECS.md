# SPECS — API de Nexova (`services/api`)

Contrato HTTP de `services/api`. Si el código y este documento discrepan, el documento se actualiza en el mismo cambio que el código.

Una sola aplicación FastAPI (`app/main.py`) con tres dominios:

- **Parte A (§1–§7): analizador de incidentes** — `/api/incidents/*`.
- **Parte B (§8–§14): directorio de proveedores** — `/suppliers*`, persistido en TinyDB.
- **Parte C (§15–§22): autenticación (AUTH-01)** — `/auth`, `/users`, `/profiles`; JWT obligatorio en las rutas de las Partes A y B.
- **Parte D (§23–§27): recuperación y cambio de contraseña (AUTH-03)** — `POST /auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`; envío con Resend.

Este documento distingue **dos orígenes** de requisitos. Mezclarlos sería atribuir al cliente decisiones que no tomó.

---

## 1. Requisitos funcionales heredados (contexto de Nexova)

Fuente: [`docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`](../../docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md). La API **no** los reimplementa: los aplica el núcleo [`packages/incident-analyzer`](../../packages/incident-analyzer/README.md), el mismo que usa la CLI `scripts/analyze.py`.

| Requisito | Dónde se cumple |
|---|---|
| Estructura del CSV (9 campos, UTF-8, cabecera, coma) | `incident_analyzer` (`schema.py`, `reader.py`, reexportados de `packages/shared` → `nexova_shared.incident_csv`) |
| Las 7 reglas de registros inválidos y su recuento por regla | `incident_analyzer` (`validation.py`, reexportado de `nexova_shared.incident_csv`; `metrics.py`) |
| Métricas: totales, desglose por categoría y por estado sobre válidos, índice de satisfacción de CLOSED | `incident_analyzer` (`metrics.py`) |
| Exportación "una métrica por fila" | `incident_analyzer` (`export.py`, formato `metric,value`) |
| Privacidad: `customer_email` nunca en ninguna salida, "ni siquiera en errores"; nada de enviar datos a herramientas de IA externas | núcleo (solo conteos) + API (§5 de este documento) |

Las decisiones de interpretación del contexto (D1–D9: conteo por regla, `strip()`, `AGT-\d{2}`, scores no enteros, etc.) están documentadas en el README del núcleo y rigen igual para la API.

---

## 2. Decisiones de API (de esta implementación, no del contexto)

El documento de contexto de Nexova **no define ninguna API HTTP**: describe un script de consola. Todo lo de esta sección son decisiones del tech lead para la Fase 2 del proyecto (rama `feature/incident-analyzer`), registradas también en `memory-bank/`.

| ID | Decisión |
|---|---|
| D-API-1 | Rutas `POST /api/incidents/analyze` y `GET /api/incidents/results/export`. **Sin** prefijo `/api/v1` (a diferencia de `docs/ARCHITECTURE_PROPOSAL.md`, que sigue siendo una propuesta pendiente) |
| D-API-2 | Porcentajes y media de satisfacción como **string decimal** (`"29.2"`, `"3.84"`), `null` si no son calculables. El redondeo lo hace solo el núcleo |
| D-API-3 | Tests con `unittest` + `fastapi.testclient.TestClient` (sin pytest) |
| D-API-4 | Límite técnico `MAX_UPLOAD_BYTES`, por defecto **1 MiB (1048576 bytes)**, aplicado al **body HTTP completo** (cabeceras y delimitadores multipart incluidos), **no al CSV**. No es un requisito del cliente. Ver §3.1 "Límite de tamaño" |
| D-API-5 | El último resultado es **el último análisis que termina correctamente**; un POST fallido no lo modifica |
| D-API-11 | `Cache-Control: no-store` en las respuestas 200 de `POST /api/incidents/analyze` y `GET /api/incidents/results/export` |
| D-API-6 | `analysis_id` y `analyzed_at` en la respuesta del POST; `X-Analysis-Id` en el GET de exportación. Son metadatos de la API: no forman parte de `AnalysisResult` |
| D-API-7 | CORS con orígenes explícitos (`CORS_ALLOWED_ORIGINS`, por defecto `http://localhost:3000`), sin credenciales, nunca `*`. Métodos: `GET`/`POST` (y, desde el directorio de proveedores, `PATCH`/`DELETE`: ver §13) |
| D-API-8 | `GET /health` fuera de `/api` |
| D-API-9 | El núcleo expone `analyze_binary_stream(stream)`; la API le pasa `UploadFile.file` |
| D-API-10 | ~~**Sin autenticación.**~~ **Superada por AUTH-01 (Parte C):** las dos rutas de incidentes exigen un JWT válido (401 sin él). Sigue siendo un servicio pensado para uso local (un worker, estado en memoria) |

---

## 3. Endpoints

### 3.1 `POST /api/incidents/analyze`

**Petición:** `multipart/form-data` con un único campo obligatorio **`file`**.

- Se acepta si el nombre del archivo termina en `.csv` (sin distinguir mayúsculas). El `Content-Type` de la parte **no** se usa para decidir (Windows envía `application/vnd.ms-excel`, otros navegadores `text/plain`).
- La validez del contenido la decide el núcleo: UTF-8 con BOM opcional, CRLF o LF, cabecera con las 9 columnas.
- Un archivo con solo la cabecera es un análisis válido: 200 con todos los conteos a 0 y porcentajes/media `null`.

**Límite de tamaño (D-API-4) — body HTTP, no CSV:**

- Se limita el **body HTTP completo** de la petición: el CSV **más** las cabeceras de la parte multipart (`Content-Disposition`, `Content-Type`) y los delimitadores (`--boundary`). Un body de exactamente `MAX_UPLOAD_BYTES` se acepta; uno de `MAX_UPLOAD_BYTES + 1` recibe 413.
- Por tanto el CSV máximo es **algo menor** que `MAX_UPLOAD_BYTES`: con 1 MiB, un CSV de exactamente 1 048 576 bytes se rechaza. La sobrecarga multipart depende del cliente (nombre del archivo, boundary): ~150 bytes en los tests, algo más en navegadores. Un frontend que quiera avisar antes de subir debe dejar margen (p. ej. rechazar CSV > 1 MiB − 4 KiB) y, en cualquier caso, tratar el 413 del servidor.
- Se aplica con y sin `Content-Length`: si la cabecera declara más del límite → 413 inmediato sin leer el body; si no la hay → se cuentan los bytes recibidos y se corta al superar el límite.
- Motivo: con el body ≤ 1 MiB, la parte del archivo nunca supera el umbral (1 MiB) a partir del cual Starlette la vuelca a un temporal en disco. Así un CSV con emails reales no toca disco (lo verifica un test).

**Respuesta 200** (`application/json`, `Cache-Control: no-store`):

```json
{
  "analysis_id": "7d3e0c2a-5b1f-4a57-9d0e-2f4c1b8a6e10",
  "analyzed_at": "2026-09-23T10:15:00Z",
  "totals": { "total_records": 13, "valid_records": 8, "invalid_records": 5 },
  "invalid_breakdown": [
    { "code": "missing_client_company", "label": "Missing client_company", "count": 2 },
    { "code": "invalid_category", "label": "Invalid or missing category", "count": 1 },
    { "code": "invalid_description", "label": "Invalid or missing description", "count": 1 },
    { "code": "invalid_agent_id", "label": "Invalid or missing agent_id", "count": 1 },
    { "code": "invalid_email", "label": "Invalid or missing email", "count": 2 },
    { "code": "closed_without_score", "label": "Closed ticket, no score", "count": 1 },
    { "code": "score_out_of_range", "label": "Score out of range", "count": 1 }
  ],
  "categories": [
    { "code": "TECHNICAL", "count": 2, "percentage": "25.0" },
    { "code": "BILLING", "count": 2, "percentage": "25.0" },
    { "code": "ACCESS", "count": 1, "percentage": "12.5" },
    { "code": "HR_QUERY", "count": 1, "percentage": "12.5" },
    { "code": "COMPLAINT", "count": 2, "percentage": "25.0" }
  ],
  "statuses": [
    { "code": "OPEN", "count": 2, "percentage": "25.0" },
    { "code": "CLOSED", "count": 4, "percentage": "50.0" },
    { "code": "DISCARDED", "count": 1, "percentage": "12.5" }
  ],
  "satisfaction": {
    "closed_tickets": 4,
    "scored_tickets": 4,
    "average_score": "3.75",
    "distribution": [
      { "score": 1, "label": "Very dissatisfied", "count": 0 },
      { "score": 2, "label": "Dissatisfied", "count": 1 },
      { "score": 3, "label": "Neutral", "count": 0 },
      { "score": 4, "label": "Satisfied", "count": 2 },
      { "score": 5, "label": "Very satisfied", "count": 1 }
    ]
  },
  "export": {
    "available": true,
    "url": "/api/incidents/results/export",
    "filename": "results.csv",
    "format": "metric,value"
  }
}
```

(Valores del fixture sintético `packages/incident-analyzer/tests/fixtures/incidents-synthetic.csv`.)

Garantías del contrato:

- Siempre las **7 reglas, 5 categorías, 3 estados y puntuaciones 1–5**, en el orden del núcleo (el del documento de contexto), aunque valgan 0.
- `invalid_records` cuenta filas; `invalid_breakdown` cuenta activaciones de regla (una fila puede activar varias), así que la suma del desglose puede ser mayor que `invalid_records`.
- Los conteos de `statuses` pueden sumar menos que `valid_records`: un válido con un status fuera de `OPEN`/`CLOSED`/`DISCARDED` no invalida la fila (D3) ni aparece en el desglose.
- Etiquetas (`label`) y códigos vienen del núcleo: el frontend no debe duplicarlos.
- **Nunca** contiene filas ni valores de registros: ni `customer_email`, ni `description`, `ticket_id`, `agent_id` o `client_company`. Tampoco el nombre del archivo subido.

### 3.2 `GET /api/incidents/results/export`

Devuelve el último análisis correcto del proceso como CSV.

| | |
|---|---|
| Estado | `200` |
| `Content-Type` | `text/csv; charset=utf-8` |
| `Content-Disposition` | `attachment; filename="results.csv"` |
| `X-Analysis-Id` | `analysis_id` del análisis exportado (expuesto por CORS para que el frontend lo lea) |
| `Cache-Control` | `no-store` (la URL es fija y el contenido cambia con cada análisis) |
| Cuerpo | `render_results_csv(AnalysisResult)` del núcleo: **byte a byte** lo mismo que escribe la CLI en `results.csv` (`metric,value`, una métrica por fila, CRLF) |

Sin análisis previo: `404` `{"detail": "no analysis available yet", "code": "no_analysis"}`.

### 3.3 `GET /health`

`200` `{"status": "ok"}`. Técnico, fuera de `/api`, sin datos.

---

## 4. Errores

Formato único: `{"detail": ..., "code": "..."}`.

| HTTP | `code` | Cuándo | `detail` |
|---|---|---|---|
| 400 | `invalid_csv` | archivo vacío, sin cabecera, faltan columnas, no es UTF-8, CSV ilegible | mensaje del núcleo (solo nombres de columna o números de fila) |
| 401 | `not_authenticated` | ruta protegida sin token, con token mal formado, firma inválida, expirado o de un usuario inexistente (Parte C). Cabecera `WWW-Authenticate: Bearer` | `could not validate credentials` |
| 401 | `invalid_credentials` | `POST /auth/login` con email o contraseña incorrectos (Parte C) | `incorrect email or password` |
| 403 | `forbidden` | autenticado sin permiso: otro usuario sin ser admin, cambio de `role` sin ser admin, `GET /users` sin ser admin (Parte C) | texto fijo |
| 404 | `no_analysis` | export sin análisis previo | `no analysis available yet` |
| 404 | `supplier_not_found` | `/suppliers/{id}` con un id que no existe (Parte B) | `supplier not found` |
| 404 | `user_not_found` / `profile_not_found` | usuario o perfil inexistente, solo visible para quien tiene permiso (Parte C) | `user not found` / `profile not found` |
| 409 | `email_already_registered` | alta o cambio a un email ya registrado (Parte C) | `email already registered` (no repite el email) |
| 404 | `not_found` | ruta inexistente | `Not Found` |
| 405 | `method_not_allowed` | método no soportado; incluye la cabecera `Allow` con los métodos permitidos | `Method Not Allowed` |
| 413 | `file_too_large` | **body HTTP** mayor que `MAX_UPLOAD_BYTES` (por `Content-Length` o contando bytes en streaming si no hay `Content-Length`) | `request body exceeds the <N> bytes limit` |
| 415 | `unsupported_file_type` | el nombre no termina en `.csv` | `only .csv files are accepted` (no repite el nombre) |
| 422 | `validation_error` | falta el campo `file`, otro nombre de campo, cuerpo JSON, `file` enviado como texto | lista de `{loc, msg, type}`. Se eliminan `input`, `ctx` y `url` del formato nativo de FastAPI |
| 400 | `bad_request` | multipart ilegible (error del parser de Starlette) | `Bad Request` |
| 500 | `internal_error` | cualquier excepción no prevista | `internal server error` — sin mensaje, tipo ni traza |

---

## 5. Privacidad (obligatoria)

- **Datos de registros:** la API solo maneja `AnalysisResult`, que contiene conteos, enums y etiquetas fijas. No hay forma de que un valor de una fila llegue a una respuesta.
- **Errores:** los `detail` son textos fijos o mensajes del núcleo que solo citan columnas y números de fila. El 422 no reproduce lo enviado (`input`/`ctx`/`url` eliminados). El 415 no repite el nombre del archivo.
- **500:** un middleware propio captura la excepción y responde el cuerpo fijo. **No** se usa `exception_handler(Exception)`, porque Starlette relanza la excepción tras ejecutarlo y el servidor registraría la traza con su mensaje. Solo se registra el **nombre de la clase** de la excepción.
- **Logs:** no se registran bodies, filas ni mensajes de excepción. El access log de uvicorn registra método, ruta y estado.
- **Disco:** con el límite por defecto (1 MiB) el upload nunca pasa a un archivo temporal. Si se sube `MAX_UPLOAD_BYTES` por encima de 1 MiB, Starlette puede volcar a disco temporal el archivo durante la petición.
- **Estado:** el último resultado guarda solo `AnalysisResult` + `analysis_id` + `analyzed_at`. Ni el CSV ni sus bytes.

---

## 6. Estado del último análisis

`LastResultStore` (en memoria, `threading.Lock`), creado por `create_app()` en `app.state`.

- **Qué guarda:** **el último análisis que termina correctamente.** Un POST que falla (400, 413, 415, 422, 500) no lo modifica. Con peticiones concurrentes gana la que *termina* después, no la que empezó después (no se ordena por hora de inicio).
- **No es persistencia:** se pierde al reiniciar el proceso.
- **Global al proceso**, no por usuario: cualquier análisis correcto posterior (de cualquiera) reemplaza al anterior. `X-Analysis-Id` permite comprobar qué análisis se descarga.
- **Un único worker:** con varios workers cada proceso tendría su propio "último análisis".
- Sustituible por persistencia sin tocar el router: el servicio solo usa `save()` y `latest()`.

---

## 7. Configuración

Variables de entorno del proceso (la API no carga archivos `.env` por sí sola; se pasan con `uv run --env-file .env …`, ver `.env.example`):

| Variable | Por defecto | Validación |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | lista separada por comas; `*` se rechaza al arrancar |
| `MAX_UPLOAD_BYTES` | `1048576` | entero > 0; se valida al arrancar. Límite del **body HTTP completo**, no del CSV (§3.1) |
| `SUPPLIERS_DB_PATH` | `services/api/data/suppliers.json` | ruta del archivo TinyDB del directorio de proveedores (Parte B). La usan la API y el seeder |
| `JWT_SECRET_KEY` | **ninguno (obligatoria)** | clave HS256, ≥ 32 caracteres; sin ella la API no arranca (Parte C) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | **ninguno (obligatoria)** | entero > 0; sin ella la API no arranca (Parte C) |
| `AUTH_DB_PATH` | `services/api/data/auth.json` | archivo TinyDB de `User` y `Profile` (Parte C). La usan la API y `create-admin` |
| `INCIDENTS_DB_PATH` | `services/api/data/incidents.json` | archivo TinyDB del gestor centralizado de incidencias (tablas `incidents` y `seed_keys`). Lo usan el repositorio `app/modules/incident_manager/` y `scripts/seed_incidents.py`. Sus rutas HTTP se documentarán con F4 |

---

# Parte B — Directorio de proveedores

## 8. Requisitos heredados (contexto de Nexova)

Fuente: [`docs/ligthweight-storage-api.md`](../../docs/ligthweight-storage-api.md) (solicitado por Patricia Solís, HR Manager; tech lead Sergio Molina). Los nombres de campos, categorías y estados son **exactamente** los del documento.

| Requisito | Dónde se cumple |
|---|---|
| Modelo de proveedor (10 campos) | `app/models.py` (`SupplierCreate`, `Supplier`) |
| 9 categorías válidas (`VALID_CATEGORIES`) y 2 estados (`VALID_STATUSES`) | `app/models.py` (`SupplierCategory`, `SupplierStatus`) |
| Moneda por país: Spain → EUR, USA → USD; la API rechaza combinaciones inconsistentes | validador de modelo de `SupplierCreate` → 422 |
| Trazabilidad de tarifas: cada cambio de `monthly_rate` registra `updated_at` | `app/database.py` (`update_rate`) |
| Seeder con los 15 proveedores de `SUPPLIERS_SEED` | `app/seed.py` (`uv run seed`) |
| Renovaciones en los próximos 60 días destacadas | frontend (`uis/backoffice`), no la API |
| Suspensión controlada: los suspendidos no se eliminan | `PATCH /suppliers/{id}/status`; ver la tensión con `DELETE` en §10 |

## 9. Decisiones de implementación (tech lead, 2026-09-29; no vienen del contexto)

| ID | Decisión |
|---|---|
| D-SUP-1 | **FastAPI + TinyDB + Pydantic** (decisión del tech lead; se migrará a Postgres cuando exista el ORM). Dependencia nueva autorizada: `tinydb>=4.9,<4.10` |
| D-SUP-2 | Rutas `/suppliers…` **sin** prefijo `/api`, tal como las define el brief del proyecto. Conviven con `/api/incidents/*` en la misma app |
| D-SUP-3 | Archivos con los nombres del brief dentro del paquete existente `app/` (no se duplica la aplicación): `app/main.py`, `app/models.py`, `app/database.py`, `app/routes/suppliers.py`, `app/seed.py` |
| D-SUP-4 | `id` = `doc_id` de TinyDB (entero) |
| D-SUP-5 | `updated_at` lo genera el sistema en **UTC** al crear y en cada `PATCH …/rate`. Cambiar el estado **no** lo modifica. El cliente no puede enviarlo (422) |
| D-SUP-6 | Entrada estricta: campos desconocidos, `id` o `updated_at` en el body → 422. `monthly_rate` debe ser un número JSON (`"100"` → 422), finito y > 0 |
| D-SUP-7 | Campos obligatorios de texto (`name`): se recortan espacios y no pueden quedar vacíos |
| D-SUP-8 | Filtros `country` y `category` combinables (AND); `category` coincide si está entre las `categories` del proveedor. Un valor fuera de la lista → 422 |
| D-SUP-9 | Seeder **explícito** (`uv run seed`), nunca automático al arrancar la API. Idempotente por `name`: solo inserta los que no existen y no modifica los existentes |
| D-SUP-10 | TinyDB se abre y cierra en cada operación bajo un `threading.Lock`: cada escritura queda en disco y la API se ejecuta con **un único worker**. No ejecutar el seeder mientras la API escribe |
| D-SUP-11 | Sin validación de formato de `contact_email` ni de `notes`: el contexto solo los define como string opcional |
| D-SUP-12 | `uv.lock` versionado (preferencia del tech lead, 2026-09-29): versiones exactas reproducibles para `uv run`. Los rangos de `pyproject.toml` se mantienen para el flujo con pip |

## 10. Tensión `DELETE` ↔ "suspensión controlada"

El contexto de Nexova dice que **los proveedores suspendidos no se eliminan** (se conservan para mantener el historial). El brief del proyecto **exige** `DELETE /suppliers/{id}` y lo evalúa.

Decisión del tech lead: el endpoint existe y funciona (204 / 404), pero **el frontend no lo expone**: Patricia solo puede activar o suspender. Así el historial se conserva en el uso normal y el requisito del brief se cumple. Cualquier uso de `DELETE` es una acción técnica fuera de la UI.

## 11. Modelo

| Campo | Tipo | Entrada (`POST`) | Validación |
|---|---|---|---|
| `id` | int | no se envía (422) | lo asigna TinyDB |
| `name` | string | obligatorio | no vacío tras recortar espacios |
| `country` | string | obligatorio | `"Spain"` o `"USA"` (exacto) |
| `categories` | lista de strings | obligatorio | mínimo 1; cada una de `VALID_CATEGORIES` |
| `monthly_rate` | number | obligatorio | > 0, finito, número JSON |
| `currency` | string | obligatorio | `"EUR"` o `"USD"`, coherente con `country` |
| `updated_at` | datetime ISO 8601 UTC | no se envía (422) | lo genera el sistema |
| `status` | string | obligatorio | `"active"` o `"suspended"` |
| `contract_renewal_date` | string o null | opcional | fecha real en formato `YYYY-MM-DD` |
| `contact_email` | string o null | opcional | — |
| `notes` | string o null | opcional | — |

Las respuestas incluyen siempre los 11 campos; los opcionales ausentes van como `null`.

## 12. Endpoints

| Método y ruta | Body | Éxito | Errores |
|---|---|---|---|
| `POST /suppliers` | `SupplierCreate` | **201** + proveedor completo con `id` | 422 |
| `GET /suppliers?country=&category=` | — | **200** + lista (todos si no hay filtros) | 422 (valor de filtro inválido) |
| `GET /suppliers/{id}` | — | **200** + proveedor | 404 `supplier_not_found`, 422 (id no numérico) |
| `PATCH /suppliers/{id}/rate` | `{"monthly_rate": number}` | **200** + proveedor con `updated_at` nuevo | 404, 422 (≤ 0, no numérico, campos extra) |
| `PATCH /suppliers/{id}/status` | `{"status": "active"}` o `{"status": "suspended"}` | **200** + proveedor (`updated_at` sin cambios) | 404, 422 |
| `DELETE /suppliers/{id}` | — | **204** sin cuerpo | 404 |

Errores con el formato común `{detail, code}` (§4); el 422 devuelve la lista `{loc, msg, type}` sin `input`.

## 13. Persistencia y CORS

- Archivo TinyDB `SUPPLIERS_DB_PATH` (por defecto `services/api/data/suppliers.json`, **ignorado por git**), tabla `suppliers`. Los datos sobreviven a reinicios de la API.
- CORS añade `PATCH` y `DELETE` a los métodos permitidos (el backoffice cambia tarifa y estado desde el navegador). Mismos orígenes explícitos que la Parte A.

## 14. Seeder

`cd services/api && uv run seed` (entry point `seed = "app.seed:main"` en `[project.scripts]`). Sin uv, con el venv del servicio: `python -m app.seed` o el ejecutable `seed` del venv.

Salida en consola: ruta de la base, **proveedores insertados**, ya existentes (omitidos) y total. Una segunda ejecución inserta 0.

---

# Parte C — Autenticación y protección de rutas (AUTH-01)

## 15. Requisitos heredados (ticket AUTH-01)

Fuente: [`docs/auth-api.md`](../../docs/auth-api.md) (ticket del tech lead; la CTO exige que ninguna ruta que modifique o exponga datos sensibles sea accesible sin sesión válida).

| Requisito | Dónde se cumple |
|---|---|
| `User` solo con credenciales (`id`, `email`, `hashed_password`, `is_active`, `role`, `created_at`) | `app/auth/models.py`, `app/auth/repository.py` |
| `Profile` uno a uno con `User` (`id`, `user_id`, `name`, `phone`, `address`) | ídem; se crea con el usuario y se borra con él |
| `role` ∈ `admin`/`manager`/`user` (`Enum`), por defecto `user` | `UserRole`; otro valor → 422 |
| Capa de servicios: crear, obtener por id, obtener por email, actualizar, eliminar | `app/auth/service.py` (`UserService`) |
| Contraseñas con `libpass[bcrypt]` (`from passlib.hash import bcrypt`), nunca en texto plano | `app/auth/security.py` |
| JWT firmado con `python-jose`, con `sub` = id de `User` y `exp` configurable | `app/auth/security.py` |
| `OAuth2PasswordBearer` + dependencia `get_current_user` (401 si algo falla) | `app/auth/dependencies.py` |
| Rutas bajo `/auth`, `/users` y `/profiles` | `app/routes/{auth,users,profiles}.py` |
| ≥ 5 rutas existentes protegidas | las 8 de las Partes A y B (§20) |
| 401 sin autenticación válida, 403 con recurso ajeno | §21 |
| `User`/`Profile` solo en TinyDB, también tras introducir Supabase/PostgreSQL | §17 |

## 16. Decisiones de implementación (tech lead, 2026-09-30)

| ID | Decisión |
|---|---|
| D-AUTH-1 | Dependencias nuevas autorizadas por el ticket: `libpass[bcrypt]>=1.9.3,<1.10` (instala `bcrypt` 5) y `python-jose[cryptography]>=3.5,<3.6` (el extra lo pide la especificación; instala `cryptography` como backend aunque HS256 no lo necesita). Sin `python-dotenv` ni `email-validator` |
| D-AUTH-2 | `User.id` y `Profile.id` son **UUID v4** generados por el sistema y guardados como campo del documento (string). **No** se usa el `doc_id` entero de TinyDB (a diferencia de los proveedores, D-SUP-4): el id es estable, viaja en el JWT como `sub` y otros módulos lo guardarán como `user_uuid`. No afecta a ningún contrato existente: ningún dato de proveedores ni de incidentes referencia usuarios |
| D-AUTH-3 | Login con `OAuth2PasswordRequestForm` (formulario `application/x-www-form-urlencoded`): el campo `username` es el **email**. Así funciona el botón *Authorize* de `/docs`. No hay variante JSON |
| D-AUTH-4 | `JWT_SECRET_KEY` (≥ 32 caracteres) y `ACCESS_TOKEN_EXPIRE_MINUTES` **sin valor por defecto**: `create_app()` lanza `ConfigError` si faltan, así que la API no arranca. El seeder y `create-admin` no las necesitan |
| D-AUTH-5 | Algoritmo `HS256`. Claims: `sub`, `iat`, `exp`. Al decodificar se exigen firma válida, algoritmo `HS256` (se rechaza `alg: none`), `sub` y `exp` no vencido |
| D-AUTH-6 | Email normalizado (recortado y en minúsculas) y validado sin regex ni dependencias: una sola `@`, parte local y dominio no vacíos, dominio con punto interior y sin espacios. Máximo 254 caracteres |
| D-AUTH-7 | Contraseña: mínimo 8 caracteres y **máximo 72 bytes UTF-8** (límite de bcrypt), validado antes del hash (422). No se trunca en silencio |
| D-AUTH-8 | `POST /users` es público y **no acepta `role`**: `UserCreate` = `email`, `password`, `name`, `phone`, `address`; enviar `role` (con cualquier valor) → 422. El backend fija siempre `role=user`. Los roles los asigna un admin con `PUT /users/{id}` (valor fuera del `Enum` → 422); el primer admin se crea con `create-admin` |
| D-AUTH-9 | Primer admin con el comando explícito `uv run create-admin` (patrón de `uv run seed`); contraseña interactiva y oculta (`getpass`), nunca por argumento |
| D-AUTH-10 | TinyDB propio en `AUTH_DB_PATH` (por defecto `services/api/data/auth.json`, ignorado por git), tablas `users` y `profiles`. Mismo patrón que D-SUP-10 (lock + abrir/cerrar por operación, un worker) |
| D-AUTH-11 | Las 8 rutas existentes se protegen a nivel de router (`include_router(..., dependencies=[Depends(get_current_user)])`): cualquier ruta nueva de esos routers queda protegida por defecto. Sin permisos por rol en ellas (basta un token válido) |
| D-AUTH-12 | CORS añade solo la cabecera `Authorization` a `allow_headers`. **No** se añade `PUT` a los métodos en AUTH-01 (ver §22). *Actualizado en AUTH-02 (2026-10-02): `PUT` ya está permitido para `PUT /profiles/me` desde el navegador* |
| D-AUTH-13 | `PUT /users/{id}` y `PUT /profiles/me` actualizan solo los campos enviados (semántica parcial). Cuerpo vacío → 200 sin cambios. *Actualizado en AUTH-03 (2026-10-06, hallazgo H-1 de la auditoría de seguridad): en `PUT /users/{id}`, `password` solo lo puede enviar un admin; un `user`/`manager` recibe 403 y no se aplica ningún campo de la petición. Los usuarios que no son admin cambian su contraseña con `POST /auth/change-password` (Parte D), que exige la actual* |

## 17. Modelo y almacenamiento

`User` (tabla `users`):

| Campo | Tipo | Entrada | Notas |
|---|---|---|---|
| `id` | UUID (string) | nunca (422) | lo genera el sistema; es el `sub` del JWT y el futuro `user_uuid` |
| `email` | string | `POST`/`PUT` | normalizado a minúsculas; único (409) |
| `hashed_password` | string bcrypt (`$2b$12$…`) | nunca (422) | se envía `password` y se guarda solo el hash. **Nunca sale en una respuesta** |
| `is_active` | bool | nunca (422) | `true` al crear; un usuario inactivo no puede hacer login ni usar su token |
| `role` | `admin` \| `manager` \| `user` | solo `PUT` de un admin (D-AUTH-8, §21) | `user` en todo registro público |
| `created_at` | datetime ISO 8601 UTC | nunca (422) | lo genera el sistema |

`Profile` (tabla `profiles`): `id` (UUID), `user_id` (= `User.id`), `name`, `phone`, `address` (strings opcionales, recortados, máx. 200 caracteres). Se crea en la misma operación que el usuario (con los campos opcionales de `POST /users` o vacío) y se borra con él: nunca hay un perfil sin usuario.

**User y Profile viven solo en TinyDB**, ahora y después de introducir Supabase/PostgreSQL: no existen ni se deben crear tablas de usuarios ni de perfiles en PostgreSQL. Las tablas PostgreSQL de otros módulos guardarán únicamente el `id` de TinyDB como `user_uuid`.

## 18. Endpoints

| Método y ruta | Auth | Body | Éxito | Errores |
|---|---|---|---|---|
| `POST /users` | pública | `{email, password, name?, phone?, address?}` (`role` → 422) | **201** + `UserRead` (`role=user`) | 409, 422 |
| `GET /users` | admin | — | **200** + lista de `UserRead` | 401, 403 |
| `GET /users/{id}` | propio o admin | — | **200** + `UserRead` | 401, 403, 404 (solo admin), 422 (id no UUID) |
| `PUT /users/{id}` | propio o admin | `{email?, password?, role?}` (`password` y `role` solo admin) | **200** + `UserRead` | 401, 403 (otro usuario, o `role`/`password` sin ser admin), 404, 409, 422 |
| `DELETE /users/{id}` | propio o admin | — | **204** (borra también el `Profile`) | 401, 403, 404 |
| `POST /auth/login` | pública | formulario OAuth2 `username` (= email), `password` | **200** `{access_token, token_type: "bearer", expires_in}` | 401 `invalid_credentials`, 422 |
| `GET /auth/me` | token | — | **200** `{id, email, role, is_active, created_at, profile}` | 401 |
| `GET /profiles/me` | token | — | **200** `Profile` | 401 |
| `PUT /profiles/me` | token | `{name?, phone?, address?}` (`user_id` → 422) | **200** `Profile` | 401, 422 |

`UserRead` = `{id, email, role, is_active, created_at}`: ninguna respuesta contiene `password` ni `hashed_password`.

## 19. JWT y `get_current_user`

- Firma HS256 con `JWT_SECRET_KEY`; `exp` = emisión + `ACCESS_TOKEN_EXPIRE_MINUTES`.
- `get_current_user` (en `app/auth/dependencies.py`): lee `Authorization: Bearer <token>` con `OAuth2PasswordBearer(tokenUrl="/auth/login")`, decodifica y valida (firma, algoritmo, `sub`, `exp`), busca el usuario por `sub` en TinyDB y lo devuelve. Cualquier fallo (sin cabecera, esquema distinto de `Bearer`, token mal formado, firma de otra clave, expirado, sin `sub`/`exp`, usuario borrado o inactivo) → **401** `not_authenticated` con `WWW-Authenticate: Bearer`.
- Login fallido: mismo mensaje si el email no existe o la contraseña no coincide; si el email no existe se verifica igualmente contra un hash ficticio para no revelar qué emails están registrados por el tiempo de respuesta.
- Los tokens son sin estado: cambiar la contraseña o el rol **no** invalida los tokens ya emitidos hasta que expiran (sí lo hace borrar el usuario).

## 20. Rutas protegidas y públicas

Protegidas (JWT obligatorio, cualquier rol): `POST /suppliers`, `GET /suppliers`, `GET /suppliers/{id}`, `PATCH /suppliers/{id}/rate`, `PATCH /suppliers/{id}/status`, `DELETE /suppliers/{id}`, `POST /api/incidents/analyze`, `GET /api/incidents/results/export`; además `GET /users`, `GET`/`PUT`/`DELETE /users/{id}`, `GET /auth/me`, `GET`/`PUT /profiles/me`.

Públicas: `GET /health`, `GET /docs` (y `/openapi.json`, `/redoc`), `POST /auth/login`, `POST /users`; desde AUTH-03, `POST /auth/forgot-password` y `POST /auth/reset-password` (`POST /auth/change-password` exige token, Parte D).

## 21. 401 frente a 403 y matriz de permisos

- **401**: no hay autenticación válida (ver §19). Nunca se usa para un usuario autenticado sin permiso.
- **403**: token válido, pero el recurso no es suyo o la acción exige admin. Un no-admin recibe 403 al pedir otro id **exista o no** (no se revela qué ids existen); un admin recibe 404 si no existe.

| Acción | `user` / `manager` | `admin` | Sin token |
|---|---|---|---|
| `POST /users` (crea siempre `role=user`; `role` en el body → 422) | ✓ | ✓ | ✓ |
| `GET /users` | 403 | ✓ | 401 |
| `GET /users/{id}` propio | ✓ | ✓ | 401 |
| `GET /users/{id}` ajeno | 403 | ✓ | 401 |
| `PUT /users/{id}` propio: `email` | ✓ | ✓ | 401 |
| `PUT /users/{id}` con `password` (propio o ajeno) | 403 → usar `POST /auth/change-password` | ✓ | 401 |
| `PUT /users/{id}` con `role` | 403 | ✓ | 401 |
| `PUT /users/{id}` ajeno | 403 | ✓ | 401 |
| `DELETE /users/{id}` propio | ✓ | ✓ | 401 |
| `DELETE /users/{id}` ajeno | 403 | ✓ | 401 |
| `GET /auth/me`, `GET`/`PUT /profiles/me` | ✓ (el suyo) | ✓ (el suyo) | 401 |
| 8 rutas de proveedores e incidentes | ✓ | ✓ | 401 |

`manager` tiene hoy los mismos permisos que `user`: el ticket no pide permisos distintos por rol.

Desde AUTH-03 (H-1), cambiar la propia contraseña sin ser admin solo es posible con `POST /auth/change-password` (contraseña actual obligatorio, §25). Un admin conserva la capacidad de AUTH-01 de fijar la contraseña de cualquier usuario con `PUT /users/{id}` (residual en §27).

## 22. Pendiente / fuera de alcance (no bloquea AUTH-01)

- ~~**CORS:** los métodos CORS siguen siendo `GET`/`POST`/`PATCH`/`DELETE`~~ — **resuelto en AUTH-02 (2026-10-02, [`docs/auth-frontend.md`](../../docs/auth-frontend.md))**: CORS permite `GET`/`POST`/`PATCH`/`PUT`/`DELETE` (cualquier otro método → preflight 400); `test_errors.py` comprueba `PUT` desde el origen del frontend y que un método no declarado (`TRACE`) se rechaza.
- ~~**Frontend:** `/suppliers` e `/incidents` del backoffice responden 401 hasta que envíe el token~~ — **resuelto en AUTH-02**: el backoffice y el tracker envían `Authorization: Bearer <token>` (token en `localStorage`) y redirigen a `/login` sin sesión o ante un 401.
- **Mejoras futuras de tokens (fuera de alcance):** refresh tokens, revocación/blacklist e invalidación de los tokens emitidos al cambiar la contraseña. Hoy un token sigue siendo válido hasta su `exp` aunque cambie la contraseña o el rol; no es un bloqueo para este ticket. *AUTH-03 (2026-10-05) tampoco lo cambia: restablecer o cambiar la contraseña no cierra las sesiones abiertas (§27).*
- Sin bloqueo por intentos fallidos ni forma de desactivar usuarios por API (`is_active` solo se puede cambiar en la base).
- Un admin puede quitarse su propio rol o borrarse aunque sea el último admin; se recupera con `uv run create-admin`.

---

# Parte D — Recuperación y cambio de contraseña (AUTH-03)

## 23. Requisitos heredados (ticket AUTH-03)

Fuente: [`docs/auth-password-reset.md`](../../docs/auth-password-reset.md) (ticket del tech lead).

| Requisito | Dónde se cumple |
|---|---|
| `POST /auth/forgot-password` acepta `{email}`, responde siempre 200 y, si el usuario existe, envía un enlace con un token de corta duración (15–60 min) | `app/routes/auth.py`, `UserService.request_password_reset`, `app/auth/email.py` |
| `POST /auth/reset-password` acepta `{token, new_password}`; valida firma/expiración/uso; hashea, actualiza e invalida el token; 400 si es inválido, expirado o usado | `UserService.reset_password`, `AuthRepository.consume_reset_token` |
| `POST /auth/change-password` con sesión, `{current_password, new_password}`; 400 si la actual es incorrecta | `UserService.change_password` |
| Email transaccional con Resend o SendGrid, con el enlace, legible en móvil | Resend (D-PWD-1), texto plano (§25) |
| API key solo en variables de entorno, documentada | `RESEND_API_KEY` en `.env.example` y README |
| Opcional elegido: registro de auditoría (timestamp, IP) | tabla `password_audit` (§26) |

## 24. Decisiones de implementación (2026-10-05)

| ID | Decisión |
|---|---|
| D-PWD-1 | Proveedor **Resend** (elegido por el usuario; el ticket permite Resend o SendGrid). Se llama a `POST https://api.resend.com/emails` con `urllib` de la librería estándar: **sin dependencias nuevas** (ni SDK de Resend ni `requests`). `User-Agent` propio (Cloudflare puede rechazar el de `urllib`) |
| D-PWD-2 | Token de restablecimiento **opaco**, no JWT: `secrets.token_urlsafe(32)` (256 bits). En TinyDB solo se guarda su **SHA-256** (tabla `password_reset_tokens`); el token en claro solo viaja en el enlace. Un JWT con `exp` no se puede invalidar tras usarlo (lo advierte el ticket) |
| D-PWD-3 | Vigencia `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`, por defecto **30**, admitida entre **15 y 60** (rango del ticket); fuera de rango → `ConfigError` al arrancar |
| D-PWD-4 | Un solo uso: validar, cambiar la contraseña y marcar `used_at` ocurre en una única operación bajo el lock del repositorio. Un enlace nuevo invalida los pendientes del mismo usuario; un reset correcto o un cambio de contraseña también. Los tokens caducados se borran al emitir uno nuevo |
| D-PWD-5 | Un único error `400 invalid_reset_token` para token desconocido, caducado o ya usado (el motivo solo queda en la auditoría) |
| D-PWD-6 | `forgot-password` responde **200 con el mismo cuerpo** exista o no el email (también para usuarios inactivos, que no reciben email). El envío se hace en una **tarea en segundo plano** (después de responder): el tiempo de respuesta no depende de si hubo email y un fallo del proveedor no cambia la respuesta (solo se registra el nombre de la clase del error) |
| D-PWD-7 | `change-password` con contraseña actual incorrecta → **400** `incorrect_password`, no 401: la sesión es válida y un 401 haría que el frontend la cerrase |
| D-PWD-8 | Email opcional al arrancar: `RESEND_API_KEY`, `EMAIL_FROM` y `PASSWORD_RESET_URL` van juntas (todas o ninguna; si no → `ConfigError`). Sin ellas la API arranca, `forgot-password` sigue respondiendo 200 y el fallo de envío queda registrado como `EmailNotConfiguredError` |
| D-PWD-9 | El enlace se construye con `PASSWORD_RESET_URL` (URL absoluta del frontend, p. ej. `http://localhost:3000/reset-password`) + `?token=…`. **Nunca** se toma de la petición (evita enlaces manipulados). Una sola URL: en local apunta al backoffice |
| D-PWD-10 | La contraseña nueva sigue las reglas de AUTH-01 (8 caracteres mínimo, 72 bytes máximo; 422). No se exige que sea distinta de la actual |
| D-PWD-11 | Auditoría (opcional del ticket) en la tabla `password_audit` del mismo `auth.json`: evento, `user_id` (o `null`), IP del cliente directo (`request.client.host`, sin leer `X-Forwarded-For`), motivo y `created_at`. Nunca el email, el token ni contraseñas. Sin endpoint de lectura ni política de retención (§27) |
| D-PWD-12 | **Corrección H-1 (auditoría de seguridad, 2026-10-06):** `PUT /users/{id}` ya no acepta `password` de un usuario que no sea admin (403 `forbidden`, sin aplicar ningún campo), así que no se puede esquivar la contraseña actual que exige `POST /auth/change-password`. Admin sin cambios (D-AUTH-13, §21) |

## 25. Endpoints

| Método y ruta | Auth | Body | Éxito | Errores |
|---|---|---|---|---|
| `POST /auth/forgot-password` | pública | `{email}` | **200** `{"detail": "if that email is registered, a reset link has been sent"}` (siempre el mismo) | 422 (email mal formado o campos extra) |
| `POST /auth/reset-password` | pública | `{token, new_password}` | **200** `{"detail": "password updated"}` | **400** `invalid_reset_token`, 422 |
| `POST /auth/change-password` | token | `{current_password, new_password}` | **200** `{"detail": "password updated"}` | **400** `incorrect_password`, 401, 422 |

Email enviado (texto plano, legible en móvil: líneas cortas y el enlace solo en su línea): asunto "Restablece tu contraseña de Nexova", el enlace `PASSWORD_RESET_URL?token=<token>`, la vigencia en minutos y el aviso de ignorarlo si no se pidió.

## 26. Almacenamiento

En `AUTH_DB_PATH` (el mismo archivo que `users` y `profiles`):

- `password_reset_tokens`: `id` (UUID), `user_id`, `token_hash` (SHA-256 hex), `created_at`, `expires_at`, `used_at` (`null` hasta usarse).
- `password_audit`: `id`, `event` (`reset_requested`, `reset_completed`, `reset_rejected`, `password_changed`, `password_change_rejected`), `user_id` (`null` si el email no existe), `ip`, `reason` (`unknown_email`; `unknown`/`expired`/`used` en `reset_rejected`; si no, `null`), `created_at`.

## 27. Pendiente / fuera de alcance (no bloquea AUTH-03)

- **Sesiones abiertas:** restablecer o cambiar la contraseña no invalida los JWT ya emitidos (igual que §19 y §22).
- **Contraseña fijada por un admin (`PUT /users/{id}` con `password`, capacidad de AUTH-01):** no exige la contraseña actual (tampoco para la del propio admin), no invalida los enlaces de restablecimiento pendientes del usuario afectado y no se registra en `password_audit`. Riesgo residual aceptado tras H-1; cambiarlo es una decisión aparte.
- **Rate limiting** de `forgot-password` (opcional del ticket, no elegido): hoy se puede pedir un enlace tantas veces como se quiera; cada petición invalida el anterior.
- **Plantilla HTML** del email (opcional del ticket, no elegido): solo texto plano.
- **Auditoría:** sin endpoint de consulta ni retención definida; las IP son datos personales.
- **Remitente de desarrollo:** con el remitente de onboarding de Resend (`onboarding@resend.dev`) solo se puede enviar a la dirección de la cuenta de Resend; para otros destinatarios hace falta verificar un dominio propio.
