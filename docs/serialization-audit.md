# Auditoría de serialización — `services/api`

**Estado: F1 hecha y verificada (2026-10-28).** Rama `feature/serialization-audit`, creada desde `main` en `d987a06` (merge de la PR #25). F0 (`5b0bd38`) registró el estado original, que se conserva en las columnas «Salida actual» y «Estado original». El usuario decidió D1–D9 (§6), F1 se implementó en cuatro commits por módulo (§7) y la verificación final está en §9. Brief literal y nota de equivalencias en [`serialization-audit-brief.md`](./serialization-audit-brief.md).

## 0. Método y leyenda

- **Rutas:** las 32 de `openapi.json` del contenedor `api` en marcha (2026-10-28, código de `main` montado con recarga), cruzadas con los decoradores de `services/api/app/**`. No hay rutas fuera de OpenAPI salvo `/docs`, `/redoc` y `/openapi.json`, que genera FastAPI y no se auditan. `GET /health` se comprobó además con `curl` (`200 {"status":"ok"}`).
- **Qué devuelve el handler:** leído en el código (repositorio o servicio que construye el objeto), no supuesto por la anotación.
- **Consumidores:** seguidos desde `services/*.service.ts` → `services/normalizers.ts` → hooks y componentes de [`uis/backoffice`](../uis/backoffice) y [`uis/talent-pipeline-tracker`](../uis/talent-pipeline-tracker). `uis/website` no llama a la API. «Lee» = el normalizador lo exige; «usa» = algún componente o hook lo muestra o decide con él.
- **Clasificación** (la del brief): ✅ `response_model` explícito y esquema adecuado · ⚠️ tiene modelo pero incompleto, expone campos innecesarios o no coincide con el cliente · ❌ dict sin tipar u objeto ORM en crudo.
- **Ningún endpoint devuelve hoy un objeto ORM de SQLModel** (`Asset`, `AssetEntry`, `AssetExit`): `service.py` del inventario construye siempre un schema de `schemas.py`. **Ningún endpoint devuelve `hashed_password`, tokens de restablecimiento ni su hash.** Lo que sí ocurre es que varios módulos TinyDB devuelven **el mismo modelo Pydantic con el que guardan el documento** (§1, T1).

**Resumen:** 32 endpoints. Estado original **15 ✅ · 16 ⚠️ · 1 ❌**; estado final **32 ✅**: cada ruta declara `response_model` y ninguna devuelve un documento de TinyDB ni un modelo ORM. Lo fija `services/api/tests/test_serialization.py`.

## 1. Hallazgos transversales

| ID | Hallazgo | Dónde | Efecto |
|---|---|---|---|
| T1 | **Modelo de almacenamiento = respuesta.** El repositorio valida el documento de TinyDB con el modelo y la ruta lo devuelve tal cual | `Supplier` ([`database.py:126`](../services/api/app/database.py)), `Incident` ([`repository.py:214-218`](../services/api/app/modules/incident_manager/repository.py)), `Profile` ([`auth/repository.py:110`](../services/api/app/auth/repository.py)); `UserRead` es además la **base** de `UserInDB` ([`auth/models.py:117`](../services/api/app/auth/models.py)) | Un campo nuevo en el documento sale por la API sin decidirlo; el contrato depende del esquema de almacenamiento (justo lo que el brief pide evitar) |
| T2 | **La salida hereda de la entrada.** `class Supplier(SupplierCreate)` ([`models.py:97`](../services/api/app/models.py)) | proveedores | El esquema de respuesta arrastra `extra="forbid"`, `strict` en `monthly_rate`, el validador de fecha y el de moneda por país. Se ejecutan **al leer** de TinyDB: un documento que no los cumpla (editado a mano, o tras cambiar una regla) hace fallar con 500 toda la lista de `GET /suppliers`. Y el OpenAPI no distingue qué campos escribe el cliente |
| T3 | **Rutas sin cuerpo JSON sin declaración explícita.** `/health` no tiene `response_model`: FastAPI lo infiere de la anotación `dict[str, str]` (OpenAPI: objeto con `additionalProperties`). La exportación CSV y los dos `DELETE` 204 usan `response_class=Response` sin `response_model=None` ni `responses=` | [`main.py:78-80`](../services/api/app/main.py), [`incidents/router.py:38`](../services/api/app/modules/incidents/router.py), [`routes/users.py:58`](../services/api/app/routes/users.py), [`routes/suppliers.py:64`](../services/api/app/routes/suppliers.py) | El entregable mínimo («`response_model` explícito en cada endpoint») no se cumple en 4 rutas; OpenAPI dice «200: sin contenido» para el CSV |
| T4 | **Errores sin documentar en OpenAPI.** Solo el inventario declara `responses=` con `ErrorResponse` (SPECS §38). En el resto, OpenAPI solo muestra el 422 **nativo** de FastAPI (`HTTPValidationError` con `input`/`ctx`), que la API no devuelve (lo sanea a `{loc, msg, type}`, §4), y el gestor de incidencias anuncia un 422 que **nunca** responde (valida con 400, SPECS §31) | todas menos `/inventory/*` | `/docs` describe errores que no existen y omite los reales (401, 403, 404, 409, 400, 503) |
| T5 | **Entradas del gestor sin esquema.** `POST /api/incidents` y `PATCH …/status` reciben `JsonObject = dict[str, Any]` ([`incident_manager/router.py:75`](../services/api/app/modules/incident_manager/router.py)); OpenAPI: `{"type": "object", "additionalProperties": true}` con un ejemplo. La validación real es estricta (`nexova_shared.incidents`: campos desconocidos → 400 `unknown_field`), pero no se ve en el contrato | gestor | El cliente no sabe por OpenAPI qué campos acepta la escritura |
| T6 | **Los normalizadores de los dos frontends son estrictos.** Exigen cada campo con su tipo y lanzan si falta (p. ej. [`backoffice normalizers.ts:383-391`](../uis/backoffice/services/normalizers.ts), [`tracker normalizers.ts:317-328`](../uis/talent-pipeline-tracker/services/normalizers.ts)) | backoffice y tracker | **Quitar un campo de la API sin tocar el normalizador rompe la pantalla** (`UnexpectedResponseError` / `ResponseShapeError`). Todo recorte de F1 se hace en el mismo commit en la API, el normalizador, los tipos y sus tests |

## 2. Rutas de autenticación (registro, login, forgot, reset, change, `/auth/me`)

| Ruta | Método | Auth | Entrada | Salida actual (`response_model` → qué devuelve el handler) | Campos que salen | Campos que usa el consumidor | Estado original | Mejora necesaria | Estado final |
|---|---|---|---|---|---|---|---|---|---|
| `/users` (registro) | POST | pública | `UserCreate` (JSON; `email`, `password`, `name?`, `phone?`, `address?`), `extra="forbid"` (`role` → 422), separado de la salida | `UserRead` → `UserInDB.public()` (copia sin `hashed_password`) | `id`, `email`, `role`, `is_active`, `created_at` | **Ninguno.** Backoffice descarta el cuerpo ([`auth.service.ts:293`](../uis/backoffice/services/auth.service.ts), `expect(201, () => null)`); tracker también ([`auth.service.ts:86`](../uis/talent-pipeline-tracker/services/auth.service.ts)). Los dos encadenan `POST /auth/login` | ⚠️ | Reenvía el `email` (el brief lo prohíbe en registro). Ver nota A1 y **D1** | ✅ `RegisteredUser` = `{id}` (D1); entrada sin cambios |
| `/auth/login` | POST | pública | `OAuth2PasswordRequestForm` (form: `username` = email, `password`; FastAPI acepta además `grant_type`, `scope`, `client_id`, `client_secret` del estándar, que se ignoran) | `Token` → `Token(...)` | `access_token`, `token_type`, `expires_in` | Backoffice lee los tres ([`normalizers.ts:371-380`](../uis/backoffice/services/normalizers.ts)) y usa `access_token`; tracker lee los tres ([`normalizers.ts:331-346`](../uis/talent-pipeline-tracker/services/normalizers.ts)) y usa `access_token` | ✅ | — (sin email ni datos del usuario) | ✅ sin cambios |
| `/auth/forgot-password` | POST | pública | `ForgotPasswordRequest` (`email`), `extra="forbid"` | `Message` → mensaje fijo | `detail` (siempre el mismo texto) | Ninguno: ambos descartan el cuerpo (backoffice [`auth.service.ts:330`](../uis/backoffice/services/auth.service.ts), tracker [`auth.service.ts:150`](../uis/talent-pipeline-tracker/services/auth.service.ts)) | ✅ | — (no reenvía el email; idéntico exista o no) | ✅ sin cambios |
| `/auth/reset-password` | POST | pública | `ResetPasswordRequest` (`token`, `new_password`), `extra="forbid"` | `Message` | `detail` | Ninguno (backoffice [`:345`](../uis/backoffice/services/auth.service.ts), tracker [`:157`](../uis/talent-pipeline-tracker/services/auth.service.ts)) | ✅ | — | ✅ sin cambios |
| `/auth/change-password` | POST | token | `ChangePasswordRequest` (`current_password`, `new_password`), `extra="forbid"` | `Message` | `detail` | Ninguno (backoffice [`:358`](../uis/backoffice/services/auth.service.ts), tracker [`:167`](../uis/talent-pipeline-tracker/services/auth.service.ts)) | ✅ | — | ✅ sin cambios |
| `/auth/me` | GET | token (propio) | — | `CurrentUser` → `CurrentUser(**UserRead, profile=Profile)`; el `Profile` es el modelo de almacenamiento (T1) | `id`, `email`, `role`, `is_active`, `created_at`, `profile: {id, user_id, name, phone, address} \| null` | **Leen** todo (backoffice [`normalizers.ts:400-410`](../uis/backoffice/services/normalizers.ts), tracker [`normalizers.ts:353-371`](../uis/talent-pipeline-tracker/services/normalizers.ts)). **Usan** solo `email` (cabecera: backoffice [`account-nav.tsx:55`](../uis/backoffice/components/auth/account-nav.tsx), tracker [`app-header.tsx:39`](../uis/talent-pipeline-tracker/components/auth/app-header.tsx); perfil: [`profile-view.tsx:55`](../uis/backoffice/components/auth/profile-view.tsx) / [`:52`](../uis/talent-pipeline-tracker/components/auth/profile-view.tsx)) y `profile.name`, `profile.phone`, `profile.address` (backoffice [`profile-view.tsx:14-19,59-67`](../uis/backoffice/components/auth/profile-view.tsx), tracker [`profile-view.tsx:15,56-64`](../uis/talent-pipeline-tracker/components/auth/profile-view.tsx)). Ninguna pantalla usa `id`, `role`, `is_active`, `created_at`, `profile.id` ni `profile.user_id` | ⚠️ | El `email` está permitido (brief). Sobran `profile.id` (id interno) y `profile.user_id` (FK que repite el `id` de arriba), e `is_active` es siempre `true` aquí (un usuario inactivo no pasa `get_current_user`). Ver nota A2, **D2** y **D3** | ✅ `CurrentUser` = `{id, email, role, created_at, profile: ProfileRead \| null}` (D2, D3); normalizadores y tipos de las dos apps sin `is_active`, `profile.id` ni `profile.user_id` |

### Notas de auth

**A1 — `POST /users`.** *Por qué:* el registro es un flujo no autenticado; reenviar el email que el cliente acaba de enviar no le aporta nada y es exactamente lo que el brief marca. Tampoco lo lee nadie. `role` es siempre `user` (D-AUTH-8) e `is_active` siempre `true` al crear, así que son constantes. *Payload objetivo* (propuesta, **D1**): `RegisteredUser = {id}` — una confirmación con la referencia estable del recurso creado (la necesitan los tests y `/users/{id}`), sin credenciales ni datos de contacto. *Entrada:* sin cambios (`UserCreate` ya acepta solo lo que debe y rechaza `role`, `id`, `hashed_password`, `is_active`, `user_id`).

**A2 — `GET /auth/me`.** *Por qué:* es la vista de detalle de la sesión, así que puede llevar la mayoría de campos seguros, pero la relación `Profile` sale **completa con sus dos claves**: `user_id` es una FK en bruto teniendo el objeto padre al lado (el brief lo cita expresamente) y `profile.id` es un id interno que no sirve para ninguna ruta (no hay `/profiles/{id}`). *Payload objetivo* (propuesta, **D2** + **D3**): `{id, email, role, created_at, profile: {name, phone, address} | null}`. Se mantiene el `email` (permitido y usado), `role` (identidad de la sesión, la necesitará cualquier vista por rol) e `id` y `created_at` (proyección segura de detalle); se quitan `profile.id`, `profile.user_id` e `is_active`.

## 3. Resto de la API, por módulo

### 3.1 Usuarios y perfiles (`/users`, `/profiles`)

| Ruta | Método | Auth | Entrada | Salida actual | Campos que salen | Campos que usa el consumidor | Estado original | Mejora necesaria | Estado final |
|---|---|---|---|---|---|---|---|---|---|
| `/users` | GET | admin | — | `list[UserRead]` → `[u.public() …]` | `id`, `email`, `role`, `is_active`, `created_at` por usuario | **Ningún frontend** (solo `/docs` y los tests) | ✅ | Lista ya plana y sin anidados; el `email` lo necesita un admin para identificar cuentas. Ver **D5**. Solo T1 (base de `UserInDB`, **D4**) y T4 | ✅ `UserRead` explícito, ya no es la base de `UserInDB` (D4) |
| `/users/{user_id}` | GET | propio o admin | path UUID | `UserRead` | ídem | Ninguno | ✅ | Ruta autenticada (no es un flujo de auth del brief): el email del propio usuario o, para un admin, de otro, es legítimo. T1/T4 | ✅ ídem |
| `/users/{user_id}` | PUT | propio o admin (`password`/`role` solo admin) | `UserUpdate` (`email?`, `password?`, `role?`), `extra="forbid"`, separado de la salida | `UserRead` | ídem | Ninguno | ✅ | Entrada ya limitada a lo escribible. T1/T4 | ✅ ídem |
| `/users/{user_id}` | DELETE | propio o admin | path UUID | **sin `response_model`**; `response_class=Response`, 204 | sin cuerpo | Ninguno | ⚠️ | T3: declarar `response_model=None` y documentar 204/401/403/404 (**D7**) | ✅ `response_model=None` declarado y 204 documentado en `responses=` (D7) |
| `/profiles/me` | GET | token (propio) | — | `Profile` → modelo de almacenamiento | `id`, `user_id`, `name`, `phone`, `address` | **Ningún frontend** (los dos leen el perfil dentro de `/auth/me`) | ⚠️ | T1 + ids internos y FK en bruto (**D2**). Objetivo: `{name, phone, address}` | ✅ `ProfileRead` = `{name, phone, address}` (D2) |
| `/profiles/me` | PUT | token (propio) | `ProfileUpdate` (`name?`, `phone?`, `address?`), `extra="forbid"` (`user_id` → 422), separado de la salida | `Profile` | ídem | **Leen** los cinco (backoffice [`auth.service.ts:317`](../uis/backoffice/services/auth.service.ts) → [`normalizers.ts:383-397`](../uis/backoffice/services/normalizers.ts); tracker [`auth.service.ts:100`](../uis/talent-pipeline-tracker/services/auth.service.ts) → [`normalizers.ts:348-351`](../uis/talent-pipeline-tracker/services/normalizers.ts)). **Usan** `name`, `phone`, `address`: el perfil guardado sustituye al mostrado ([`use-profile.ts:53-55`](../uis/backoffice/hooks/use-profile.ts)) | ⚠️ | Como el GET (**D2**). Objetivo: `{name, phone, address}` | ✅ `ProfileRead` (D2); entrada sin cambios |

### 3.2 Analizador de incidentes (`/api/incidents/analyze`, `/api/incidents/results/export`)

| Ruta | Método | Auth | Entrada | Salida actual | Campos que salen | Campos que usa el consumidor | Estado original | Mejora necesaria | Estado final |
|---|---|---|---|---|---|---|---|---|---|
| `/api/incidents/analyze` | POST | token | `multipart/form-data`, campo `file` (`UploadFile`) | `AnalysisResponse` → `AnalysisResponse.from_stored(...)` (schema propio, construido campo a campo desde `AnalysisResult`) | `analysis_id`, `analyzed_at`, `totals{3}`, `invalid_breakdown[{code,label,count}]`, `categories[{code,count,percentage}]`, `statuses[…]`, `satisfaction{closed_tickets, scored_tickets, average_score, distribution[{score,label,count}]}`, `export{available,url,filename,format}` | Backoffice lee todo ([`normalizers.ts:227-245`](../uis/backoffice/services/normalizers.ts)) y usa todo salvo `export.url` y `export.format` (la descarga usa la constante `EXPORT_PATH`, [`incidents.service.ts:28`](../uis/backoffice/services/incidents.service.ts); `available` y `filename` en [`analysis-meta.tsx:36-40`](../uis/backoffice/components/incidents/analysis-meta.tsx)) | ✅ | Ya explícito y sin datos de filas (SPECS §5). `export.url`/`format` son contrato D-API-6 y pesan unos bytes: no se proponen cambios. Solo T4 | ✅ sin cambios |
| `/api/incidents/results/export` | GET | token | — | **sin `response_model`**; `Response` con `text/csv` + `Content-Disposition`, `X-Analysis-Id`, `Cache-Control` | CSV `metric,value` (sin JSON) | Backoffice: cuerpo como blob y cabecera `X-Analysis-Id` ([`incidents.service.ts:190-195`](../uis/backoffice/services/incidents.service.ts)) | ⚠️ | T3: OpenAPI dice «200: sin contenido». Declarar `response_model=None` y documentar `200 text/csv` con sus cabeceras y el 404 `no_analysis` (**D7**) | ✅ `response_model=None` declarado; `200 text/csv` con `Content-Disposition`, `X-Analysis-Id` y `Cache-Control` documentados (D7) |

### 3.3 Gestor centralizado de incidencias (`/api/incidents…`)

| Ruta | Método | Auth | Entrada | Salida actual | Campos que salen | Campos que usa el consumidor | Estado original | Mejora necesaria | Estado final |
|---|---|---|---|---|---|---|---|---|---|
| `/api/incidents` | POST | token | **`JsonObject` sin tipar** (T5); valida `nexova_shared.validate_incident_fields` (`title`, `description`, `category`, `origin`, `branch`, `status?` solo `open`; desconocidos → 400 `unknown_field`) | `Incident` → modelo de almacenamiento (T1) | `id`, `title`, `description`, `category`, `status`, `origin`, `branch`, `created_at`, `updated_at` | Backoffice lee los nueve ([`incident-manager.service.ts:275`](../uis/backoffice/services/incident-manager.service.ts) → [`normalizers.ts:429-447`](../uis/backoffice/services/normalizers.ts)); tras el alta usa `title` y `status` ([`incident-form-view.tsx:26`](../uis/backoffice/components/incident-manager/incident-form-view.tsx)) | ⚠️ | T1 (esquema de lectura propio, **D4**), T5 (esquema de entrada visible sin romper el 400, **D6**), T4 (OpenAPI anuncia 422; responde 400) | ✅ `IncidentRead` (D4); contrato de entrada `IncidentCreateRequest` en OpenAPI, validación de `nexova_shared` (D6); 400/401/503 documentados y sin el 422 nativo (D8 B) |
| `/api/incidents` | GET | token | query `status`, `origin`, `branch`, `category` (strings con `enum` en OpenAPI; valida `nexova_shared.validate_filters` → 400) | `list[Incident]` | los nueve por fila | Backoffice lee los nueve ([`normalizers.ts:450-454`](../uis/backoffice/services/normalizers.ts)); la tabla usa `id`, `title`, `description`, `category`, `origin`, `branch`, `created_at`, `status` ([`incident-table.tsx:46-130`](../uis/backoffice/components/incident-manager/incident-table.tsx)). **`updated_at` no lo usa ningún componente** | ⚠️ | T1 y listado = detalle: `updated_at` sobra en la lista (**D5**). T4 | ✅ `list[IncidentListItem]`, sin `updated_at` (D5); normalizador y tipo `IncidentListItem` en el backoffice; 400/401/503 documentados |
| `/api/incidents/summary` | GET | token | — | `IncidentSummary` (schema propio) | `total`, `by_status{4}`, `by_category{8}`, `by_origin{3}`, `by_branch{4}` | Backoffice lee y usa todo ([`normalizers.ts:470-484`](../uis/backoffice/services/normalizers.ts), panel de resumen) | ✅ | Solo T4 | ✅ sin cambios de esquema; 401/503 documentados |
| `/api/incidents/{incident_id}` | GET | token | path UUID (convertidor `:uuid`) | `Incident` | los nueve | **Ningún frontend** (el servicio no tiene `getIncident`) | ⚠️ | T1 (**D4**); detalle completo `IncidentRead`. T4 | ✅ `IncidentRead`; 401/404/503 documentados |
| `/api/incidents/{incident_id}/status` | PATCH | token | **`JsonObject` sin tipar** (T5); valida `validate_status_change` (solo `status`) | `Incident` | los nueve | Backoffice lee los nueve ([`incident-manager.service.ts:286`](../uis/backoffice/services/incident-manager.service.ts)) y sustituye la fila por la respuesta ([`use-incident-board.ts:84-108,150`](../uis/backoffice/hooks/use-incident-board.ts)) | ⚠️ | T1, T5 (**D6**), T4 | ✅ `IncidentRead`; contrato `IncidentStatusChangeRequest` (D6); 400 (`validation_error`, `invalid_status_transition`)/401/404/503 documentados |

### 3.4 Directorio de proveedores (`/suppliers`)

| Ruta | Método | Auth | Entrada | Salida actual | Campos que salen | Campos que usa el consumidor | Estado original | Mejora necesaria | Estado final |
|---|---|---|---|---|---|---|---|---|---|
| `/suppliers` | POST | token | `SupplierCreate`, `extra="forbid"` (`id`/`updated_at` → 422) | `Supplier(SupplierCreate)` (T2) → modelo de almacenamiento (T1) | `id`, `name`, `country`, `categories`, `monthly_rate`, `currency`, `updated_at`, `status`, `contract_renewal_date`, `contact_email`, `notes` | Backoffice lee los once ([`suppliers.service.ts:217`](../uis/backoffice/services/suppliers.service.ts) → [`normalizers.ts:290-310`](../uis/backoffice/services/normalizers.ts)) | ⚠️ | T2 + T1: esquema de salida propio (`SupplierRead`) que no herede de la entrada (**D4**). T4 | ✅ `SupplierRead` (11 campos nombrados, sin validadores de entrada) construido desde el documento `Supplier`, que ya no hereda de `SupplierCreate` (D4); mismo JSON |
| `/suppliers` | GET | token | query `country`, `category` (enums de Pydantic → 422) | `list[Supplier]` | los once por fila | Backoffice lee los once ([`normalizers.ts:313-316`](../uis/backoffice/services/normalizers.ts)) y **la tabla usa los once**: `id`, `name`, `country`, `categories`, `monthly_rate`, `currency`, `updated_at`, `status`, `contract_renewal_date`, `contact_email`, `notes` ([`supplier-table.tsx:42-192`](../uis/backoffice/components/suppliers/supplier-table.tsx); `contact_email` y `notes` en la línea 83-84) | ⚠️ | T2/T1. El listado sí necesita los once campos: esquema compartido con el detalle justificado (**D5**) | ✅ `list[SupplierRead]`: mismo esquema que el detalle, porque la tabla usa los once campos (D5) |
| `/suppliers/{supplier_id}` | GET | token | path int | `Supplier` | los once | **Ningún frontend** | ⚠️ | T2/T1 | ✅ `SupplierRead` |
| `/suppliers/{supplier_id}/rate` | PATCH | token | `RateUpdate` (`monthly_rate`), `extra="forbid"` | `Supplier` | los once | Backoffice lee los once ([`suppliers.service.ts:230`](../uis/backoffice/services/suppliers.service.ts)) y sustituye la fila ([`use-supplier-directory.ts:129-130`](../uis/backoffice/hooks/use-supplier-directory.ts)) | ⚠️ | T2/T1 | ✅ `SupplierRead`; entrada `RateUpdate` sin cambios |
| `/suppliers/{supplier_id}/status` | PATCH | token | `StatusUpdate` (`status`), `extra="forbid"` | `Supplier` | los once | ídem ([`suppliers.service.ts:241`](../uis/backoffice/services/suppliers.service.ts)) | ⚠️ | T2/T1 | ✅ `SupplierRead`; entrada `StatusUpdate` sin cambios |
| `/suppliers/{supplier_id}` | DELETE | token | path int | **sin `response_model`**; `Response` 204 | sin cuerpo | Ninguno (la UI no lo expone, SPECS §10) | ⚠️ | T3 (**D7**) | ✅ `response_model=None` declarado y 204 documentado (D7) |

### 3.5 Inventario (`/inventory/*`)

| Ruta | Método | Auth | Entrada | Salida actual | Campos que salen | Campos que usa el consumidor | Estado original | Mejora necesaria | Estado final |
|---|---|---|---|---|---|---|---|---|---|
| `/inventory/products` | GET | token | — | `list[AssetRead]` → `service._read(...)` (schema Pydantic, **no** el ORM `Asset`) | `id`, `name`, `sku`, `category`, `office`, `current_stock` | Backoffice lee y la tabla usa los seis ([`normalizers.ts:503-524`](../uis/backoffice/services/normalizers.ts), [`asset-table.tsx:36-57`](../uis/backoffice/components/inventory/asset-table.tsx)) | ✅ | Ya cumple: schemas separados del ORM y `responses=` (SPECS §38). Lista = detalle justificado (usa los seis) | ✅ sin cambios |
| `/inventory/products` | POST | token | `AssetCreate` (`name`, `sku`, `category`, `office`), `extra="forbid"` | `AssetRead` (`current_stock: 0`) | los seis | **Ningún frontend** (solo `/docs` y el seed) | ✅ | — | ✅ sin cambios |
| `/inventory/products/{id}` | GET | token | path int | `AssetRead` | los seis | Salida de activos: relee el stock ([`use-outbound-form.ts:165-167`](../uis/backoffice/hooks/use-outbound-form.ts)); el normalizador exige los seis | ✅ | — | ✅ sin cambios |
| `/inventory/orders/inbound` | POST | token | `InboundOrderCreate` (`asset_id`, `quantity`, `supplier`, `office`), `extra="forbid"` (`user_uuid` → 422) | `InboundOrderRead` | `type`, `id`, `asset{id,name,sku}`, `quantity`, `supplier`, `office`, `created_at`, `user_uuid` | Lee todo ([`normalizers.ts:526-563`](../uis/backoffice/services/normalizers.ts)); la confirmación usa `asset.name`, `asset.sku`, `quantity` ([`use-inbound-form.ts:55`](../uis/backoffice/hooks/use-inbound-form.ts)) | ✅ | — | ✅ sin cambios |
| `/inventory/orders/outbound` | POST | token | `OutboundOrderCreate` (`asset_id`, `quantity`, `exit_type`, `assigned_to`, `office`), `extra="forbid"` | `OutboundOrderRead` | `type`, `id`, `asset{id,name,sku}`, `quantity`, `exit_type`, `assigned_to`, `office`, `created_at`, `user_uuid` | Lee todo; confirmación con `asset.name`, `asset.sku`, `quantity` ([`use-outbound-form.ts:109`](../uis/backoffice/hooks/use-outbound-form.ts)) | ✅ | — | ✅ sin cambios |
| `/inventory/orders` | GET | token | — | `list[InboundOrderRead \| OutboundOrderRead]` (discriminada por `type`) | los de cada tipo | El historial usa `id`, `type`, `asset.name`, `asset.sku`, `quantity`, `office`, `created_at`, `user_uuid` ([`order-table.tsx:34-48`](../uis/backoffice/components/inventory/order-table.tsx)) y `supplier` / `exit_type` / `assigned_to` ([`order-format.ts:38-39`](../uis/backoffice/lib/order-format.ts)). **`asset.id` lo lee el normalizador ([`:529`](../uis/backoffice/services/normalizers.ts)) pero no lo usa ninguna pantalla** | ✅ | Proyección plana ya decidida (D8 del Hito 5). `asset.id`: ver **D5** | ✅ sin cambios; `asset.id` se mantiene (D5) |

### 3.6 Técnico

| Ruta | Método | Auth | Entrada | Salida actual | Campos que salen | Campos que usa el consumidor | Estado original | Mejora necesaria | Estado final |
|---|---|---|---|---|---|---|---|---|---|
| `/health` | GET | pública | — | **sin `response_model`**: dict; FastAPI infiere `dict[str, str]` de la anotación | `status` (`"ok"`) | Healthcheck de Docker, solo el código de estado ([`docker-compose.yml:52`](../docker-compose.yml)); `curl` de `docs/local-development.md` y `AGENTS.md` §4 (cuerpo `{"status":"ok"}`) | ❌ | Dict sin tipar. Objetivo: `HealthResponse = {status: "ok"}` (`Literal["ok"]`), mismo cuerpo (**D7**) | ✅ `HealthResponse` = `{status: "ok"}`, mismo cuerpo; Docker sigue `healthy` (D7) |

## 4. Notas de mejora (⚠️ y ❌ fuera de auth)

- **N1 — Proveedores (6 rutas).** *Por qué:* T2 y T1. Los campos son los adecuados (la UI usa los once), pero el contrato de salida está atado a las reglas de entrada y al documento guardado. *Payload objetivo* `SupplierRead`, con los once campos nombrados uno a uno y sin validadores: `id`, `name`, `country`, `categories`, `monthly_rate`, `currency`, `updated_at`, `status`, `contract_renewal_date`, `contact_email`, `notes`. Mismo JSON que hoy. *Entradas:* sin cambios (`SupplierCreate`, `RateUpdate`, `StatusUpdate` ya aceptan solo lo escribible).
- **N2 — Gestor de incidencias (4 rutas).** *Por qué:* T1, T4, T5 y el listado. *Payload objetivo:* `IncidentRead` (detalle, `POST`, `PATCH`): `id`, `title`, `description`, `category`, `status`, `origin`, `branch`, `created_at`, `updated_at`; `IncidentListItem` (si se acepta **D5**): lo mismo sin `updated_at`. *Entradas:* alta = `title`, `description`, `category`, `origin`, `branch`, `status?` (solo `open`); cambio de estado = `status`. Ya lo garantiza `nexova_shared`; falta hacerlo visible (**D6**).
- **N3 — Perfiles.** *Por qué:* T1 y FK en bruto. *Payload objetivo:* `ProfileRead = {name, phone, address}` en `GET`/`PUT /profiles/me` y dentro de `/auth/me` (**D2**). *Entrada:* sin cambios.
- **N4 — Sin cuerpo JSON** (`DELETE /users/{id}`, `DELETE /suppliers/{id}`, exportación, `/health`). Ver **D7**.

## 5. Relaciones

| Relación | Dónde sale hoy | Forma actual | Decisión propuesta |
|---|---|---|---|
| `User` 1:1 `Profile` (`Profile.user_id` = `User.id`) | `GET /auth/me` | **Anidado completo**, con `profile.id` y `profile.user_id` | **Proyección anidada sin claves** `profile: {name, phone, address} \| null`: el cliente necesita los datos del perfil junto al usuario, no sus ids (**D2**) |
| ídem | `GET`/`PUT /profiles/me` | Objeto con la FK `user_id` | Sin claves: el dueño es siempre el del token, la FK no aporta nada al cliente (**D2**) |
| `AssetEntry`/`AssetExit` N:1 `Asset` (FK `asset_id`) | `POST /inventory/orders/*`, `GET /inventory/orders` | **Proyección plana anidada** `asset: {id, name, sku}` en lugar de `asset_id` (D8 del Hito 5) | **Mantener.** El historial muestra nombre y SKU; el activo completo (`category`, `office`, `current_stock`) sobraría y obligaría a calcular el stock por fila. `asset.id`, ver **D5** |
| Orden → usuario (`user_uuid`, sin FK: el usuario vive en TinyDB y la orden en PostgreSQL) | ídem | **Solo el ID** plano | **Mantener solo el ID.** La UI lo muestra tal cual ([`order-table.tsx:48`](../uis/backoffice/components/inventory/order-table.tsx)). Resolverlo a email exigiría una lectura de TinyDB por usuario distinto (no hay JOIN entre las dos bases) y **expondría el email de otros usuarios** a cualquier usuario autenticado |
| `Supplier.categories` | `/suppliers*` | Lista de valores del vocabulario | No es una relación: sin cambios |
| `Incident`, `AnalysisResponse`, `IncidentSummary` | — | Sin relaciones | — |

## 6. Decisiones que toma el usuario (D1–D9)

### D1 — Respuesta del registro (`POST /users`)

| Opción | Payload 201 | Consecuencias |
|---|---|---|
| **A (recomendada)** | `RegisteredUser = {id}` | Ningún frontend cambia (los dos descartan el cuerpo). Tests: `test_auth.py:27-28` (conjunto de claves y `email`) cambia; los que usan `register(...).json()["id"]` (`auth_support.py:80`, `test_auth.py:51,58`) siguen igual |
| B | `UserRead` sin `email`: `{id, role, is_active, created_at}` | Igual de compatible, pero `role` e `is_active` son constantes en el registro (`user`, `true`) |
| C | `Message` `{"detail": "user registered"}` | Lo más pequeño, pero sin referencia al recurso creado: rompe los tests que leen `id` y quita el único dato útil de la confirmación |

*Por qué A:* lo siguiente que hace el cliente es el login con lo que ya tiene; el `id` es la proyección segura mínima de un recurso recién creado. SPECS §18 cambia («201 + `UserRead`» → «201 + `{id}`»).

### D2 — `Profile` sin `id` ni `user_id`

| Opción | Forma | Qué cambia |
|---|---|---|
| **A (recomendada)** | `ProfileRead = {name, phone, address}` en `/auth/me`, `GET` y `PUT /profiles/me` | API: modelo de respuesta nuevo; `Profile` queda como modelo interno del repositorio. **Backoffice:** `types/auth.ts:16-22`, `services/normalizers.ts:383-391` (deja de exigir `id`/`user_id`), fixtures de `__tests__/auth/normalizers.test.ts:12,49` (el caso «`user_id: 7`» pasa a otro campo), `tests/auth.service.test.mjs:18`, `tests/use-auth.test.mjs` y `__tests__/auth/*.test.ts`. **Tracker:** `types/auth.ts`, `services/normalizers.ts:317-328`, `tests/auth.test.mjs:28`. **API:** `test_auth.py:400-403` (`body["profile"]["user_id"]`). Los tests sobre la base (`raw_profiles()`, `test_profiles.py` a nivel de servicio) no cambian |
| B | Quitar solo `user_id` (redundante), dejar `profile.id` | Mismo trabajo en normalizadores; deja un id interno sin uso |
| C | Aplanar el perfil en `/auth/me` (`name`, `phone`, `address` arriba) | Además cambia la forma que usan `profile-view.tsx` y `use-profile.ts` en las dos apps; más superficie sin ganancia |

*Por qué A:* ninguna pantalla usa los ids; quitarlos es la «FK en bruto con el objeto disponible» del brief. Requisito del orden: API, normalizadores, tipos y tests en el **mismo commit** (T6).

### D3 — Campos de primer nivel de `/auth/me`

| Opción | Forma | Qué cambia |
|---|---|---|
| **A (recomendada)** | `{id, email, role, created_at, profile}` (sin `is_active`) | `is_active` es siempre `true` en esta ruta (un inactivo recibe 401 antes). Backoffice: `normalizers.ts:407`, `types/auth.ts:29`; tracker: `normalizers.ts:358-364`, `types/auth.ts`; fixtures `ME` de los tests de las dos apps; `test_auth.py` si comprueba `is_active` en `/auth/me` |
| B | Sin cambios en el primer nivel (solo D2) | Menos cambios; mantiene un campo constante |
| C | Mínimo `{email, profile}` | Quita `id` y `role`, que identifican la sesión y harán falta en cuanto una vista dependa del rol |

### D4 — Esquemas de lectura separados del modelo de almacenamiento

| Opción | Qué se hace |
|---|---|
| **A (recomendada)** | Un `*Read` explícito por recurso, con cada campo nombrado y sin validadores de entrada, construido desde el modelo interno: `SupplierRead`, `IncidentRead`, `ProfileRead`. `UserRead` deja de ser la base de `UserInDB` (se construye con sus campos). Mismo JSON salvo lo decidido en D1–D3 y D5 |
| B | Solo `SupplierRead` (T2, el caso con riesgo de 500), dejando `Incident` y `Profile` como están | Menos cambios; T1 sigue en el gestor y en perfiles |
| C | Nada (los campos ya son los correctos) | No resuelve T1/T2 ni el «el esquema es la fuente de verdad» del brief |

### D5 — Listados: esquema ligero o el del detalle

| Listado | Qué usa la UI | Opción recomendada | Alternativa |
|---|---|---|---|
| `GET /suppliers` | los once campos | **Mismo `SupplierRead`** que el detalle (la tabla muestra `notes` y `contact_email`) | Esquema sin `notes`/`contact_email` → rompe la tabla |
| `GET /api/incidents` | todo menos `updated_at` | **`IncidentListItem` sin `updated_at`**; `IncidentRead` completo en detalle, `POST` y `PATCH`. Backoffice: `normalizeIncidentList` deja de exigirlo y `types/incident-manager.ts` separa los dos tipos; `use-incident-board.ts` sigue sustituyendo la fila con la respuesta del `PATCH` (es un superconjunto) | Mismo esquema: un timestamp por fila (~45 bytes) |
| `GET /users` | sin consumidor | **Mismo `UserRead`** (5 campos planos; el admin necesita el email) | `UserListItem {id, email, role}` |
| `GET /inventory/products` | los seis | **Mismo `AssetRead`** | — |
| `GET /inventory/orders` | todo menos `asset.id` | **Mantener `asset.id`**: es la identidad estable de la proyección y lo que permitiría enlazar con el activo; son unos bytes | Quitarlo: `AssetSummary = {name, sku}`; cambia `normalizers.ts:526-533`, `types/inventory.ts` y los tests del inventario, y aleja la respuesta del contrato del Hito 5 (SPECS §37) |

### D6 — Entradas tipadas del gestor sin romper el 400 de la Parte E

Restricciones: el 400 `{code: "validation_error", detail: [{field, error, message}]}` con todos los errores a la vez y los códigos `missing`, `blank`, `too_long`, `invalid_type`, `invalid_choice`, `unknown_field`, `invalid_body` (SPECS §31, P4-2); la UI elige su texto por `error` ([`incident-manager.service.ts`](../uis/backoffice/services/incident-manager.service.ts)); el seed valida con las mismas reglas; `test_architecture.py` prohíbe en `services/api/app` los literales del vocabulario.

| Opción | Qué se hace | Riesgos |
|---|---|---|
| **A (recomendada)** | **Esquema de entrada solo para el contrato.** Modelos `IncidentCreateRequest` y `IncidentStatusChangeRequest` en el router, con los tipos de `nexova_shared` (`IncidentCategory`, `IncidentOrigin`, `Branch`, `IncidentStatus`: tipos importados, no literales, así que `test_architecture.py` no cambia) y `extra="forbid"`, publicados en OpenAPI con `openapi_extra` (cuerpo) y `responses={400: …}`. El handler sigue recibiendo el objeto JSON y validando con `nexova_shared`, que es la autoridad. Un test compara los campos del esquema con los que acepta `nexova_shared` | Dos descripciones de la misma entrada: el test de coherencia evita que se separen |
| B | Modelo Pydantic «tipado» con todo `Any \| None` y `extra="allow"`, volcado a dict para `nexova_shared` | Tipado solo de nombre; OpenAPI seguiría sin decir qué valores valen |
| C | Modelo Pydantic real (tipos, longitudes, `status` solo `open`) y traducción de los errores de Pydantic a los códigos del gestor en `IncidentManagerRoute` | Duplica reglas de `nexova_shared` (límite de `title`, `blank`, vocabulario) en la API y en el seed; Pydantic no da los mismos códigos ni el mismo orden (`missing` vs `blank`, `null` = `missing`), así que cambia el contrato del 400 y la UI |
| D | Llevar el modelo Pydantic a `packages/shared` | `nexova_shared` no tiene dependencias (`dependencies = []`): añadir Pydantic es una dependencia nueva que requiere autorización, y el problema de C sigue |

Con A se corrige también T4 en el gestor: documentar el 400 real y el 404, y sustituir el 422 que FastAPI añade por defecto.

**Decidido: A** (usuario, 2026-10-28), con la condición de dejar claro el reparto. Así queda implementado:

- **Contrato publicado (OpenAPI):** `IncidentCreateRequest` e `IncidentStatusChangeRequest` (`app/modules/incident_manager/models.py`). Es lo que lee quien consume la API: qué campos acepta cada escritura, sus valores y cuáles son obligatorios, con `additionalProperties: false`. Se publican con `openapi_extra` y **no validan nada**.
- **Autoridad de validación:** `nexova_shared` (`validate_incident_fields`, `validate_status_change`). El handler recibe el objeto JSON tal cual y es `nexova_shared` quien lo acepta o rechaza, igual que en el seed del CSV.
- **Por qué no la opción C:** validar con Pydantic cambiaría el 400 de la Parte E del que depende la UI. Con la traducción actual de `IncidentManagerRoute`, todo error de un campo del cuerpo saldría como `{field: "body", error: "invalid_body"}`, sin el campo. Aunque se tradujeran uno a uno, Pydantic no da los mismos códigos: un `null` es `string_type` y no `missing` (para `nexova_shared`, `null` cuenta como ausente), un texto en blanco no es `blank` y el orden de los errores no es el de `INPUT_FIELDS`. Además, las reglas quedarían duplicadas entre la API y el seed.
- **Test de coherencia** (`services/api/tests/test_incident_manager_contract.py`): los campos del esquema publicado son exactamente `INPUT_FIELDS` y `STATUS_CHANGE_FIELDS` de `nexova_shared`; los obligatorios publicados son los que `nexova_shared` reporta como `missing` con un cuerpo vacío; el vocabulario, el máximo del título y el `status` inicial coinciden; y un campo no previsto (`id`, `created_at`, `updated_at`, `priority` en el alta; `title`, `updated_at` en el cambio de estado) responde **400 `unknown_field`**.

### D7 — `response_model` explícito cuando no hay cuerpo JSON

| Opción | Qué se hace |
|---|---|
| **A (recomendada)** | `/health`: `response_model=HealthResponse` (`{status: Literal["ok"]}`, mismo cuerpo). Exportación: `response_model=None` declarado + `responses={200: {content: {"text/csv": {schema: string}}, headers: {Content-Disposition, X-Analysis-Id, Cache-Control}}, 404: …}`. `DELETE` 204: `response_model=None` + `responses={204: {description}, …errores}`. Más un test de arquitectura nuevo que recorre `app.routes` y exige que cada `APIRoute` tenga un `response_model` que sea un modelo Pydantic (o lista/unión de ellos) **o** esté en una lista cerrada de rutas sin cuerpo JSON con sus `responses=` declarados |
| B | Solo `response_model=None` en las tres sin cuerpo, sin `responses=` | Cumple la letra; OpenAPI sigue sin describir el CSV ni el 204 |
| C | Devolver JSON en los `DELETE` (200 + `Message`) | Cambia un contrato de SPECS (§12, §18) sin necesidad |

### D8 — Esquemas de error en `responses=` (OpenAPI)

| Opción | Qué se hace |
|---|---|
| **A (recomendada)** | Generalizar el patrón del inventario (`ErrorResponse` + `_error()` con ejemplos construidos desde las excepciones reales de `core/errors.py`) a `app/core/openapi.py` y usarlo en todas las rutas con sus errores reales (401, 403, 404, 409, 400, 503); añadir un `ValidationErrorResponse` saneado (`{detail: [{loc, msg, type}], code}`) para que el 422 documentado sea el que se responde, y el `IncidentErrorResponse` del gestor (D6). El inventario pasa a importarlo, sin cambiar su OpenAPI (`OpenApiErrorsTests` sigue verde). Solo documentación |
| B | Solo el gestor (donde OpenAPI miente: 422 frente a 400) | Lo mínimo para que `/docs` no contradiga a SPECS |
| C | Nada | El brief no lo exige; T4 queda |

Propuesta de alcance: el commit de cada módulo añade sus `responses=`; el helper compartido va en el primero.

**Decidido: B** (usuario, 2026-10-28): esquemas de error solo en el gestor de incidencias, donde `/docs` anunciaba un 422 que nunca se responde. Implementado con `IncidentErrorResponse` e `IncidentValidationErrorResponse` (nombres propios, para no chocar con el `ErrorResponse` del inventario en los componentes de OpenAPI) y `drop_native_validation_responses`, que quita el 422 nativo solo de las cinco rutas del gestor. **La opción A queda como trabajo futuro:** llevar el patrón a `app/core/openapi.py` y documentar 401/403/404/409/503 y un 422 saneado en auth, usuarios, perfiles, proveedores y el analizador (hoy siguen mostrando solo el 422 nativo de FastAPI, T4).

### D9 — Contratos y tests que cambian (para que sean intencionados)

Si se aceptan las recomendadas:

| Dónde | Cambio |
|---|---|
| SPECS Parte C §17–§18 | `POST /users` → 201 `{id}`; `GET /auth/me` → `{id, email, role, created_at, profile: {name, phone, address} \| null}`; `GET`/`PUT /profiles/me` → `{name, phone, address}`; nota de `UserRead` («ninguna respuesta contiene…») ampliada a la lista de esquemas |
| SPECS Parte B §11–§12 | «Las respuestas incluyen siempre los 11 campos» se mantiene; se nombra `SupplierRead` como esquema de salida distinto de `SupplierCreate` |
| SPECS Parte E §30–§31 | listado sin `updated_at` (D5); esquemas de entrada documentados (D6); ejemplo de respuesta en dos formas (detalle y fila) |
| SPECS Parte A §3.2–§3.3 y §4 | `HealthResponse` y la exportación documentada (D7); errores en OpenAPI (D8) |
| SPECS Parte F | sin cambios de contrato (solo, si D8 = A, que `ErrorResponse` vive en `core`) |
| Tests de la API | `test_auth.py` (registro, `/auth/me`), `test_profiles.py`, `test_register.py`, `test_users.py` donde comprueben formas; `test_suppliers_api.py` (esquema de OpenAPI si lo comprueba); `test_incident_manager_api.py` (listado sin `updated_at`, OpenAPI de entradas y 400); `test_analyze.py`/`test_export.py`/`test_errors.py` (OpenAPI de `/health` y la exportación); test nuevo de cobertura de `response_model` (D7) y de coherencia de entradas del gestor (D6) |
| Tests del backoffice | `__tests__/auth/normalizers.test.ts`, `__tests__/auth/auth.service.test.ts`, `__tests__/auth/use-auth-session.test.ts`, `tests/auth.service.test.mjs`, `tests/use-auth.test.mjs` (fixtures `PROFILE`/`ME`); `tests/support/incident-fakes.mjs`, `tests/use-incident-manager.test.mjs` y los del servicio del gestor (lista sin `updated_at`) |
| Tests del tracker | `tests/auth.test.mjs` (fixtures `PROFILE`/`ME`) |

## 7. Plan de F1 (tras decidir D1–D9)

Un commit por módulo, en este orden. Cada uno deja la API y los dos frontends en verde por sí solo (T6) y actualiza SPECS y la columna «Estado final» de este documento.

| # | Commit | Archivos | Tests | Validación (`AGENTS.md` §4) |
|---|---|---|---|---|
| 1 | auth/users/profiles | `app/auth/models.py` (`RegisteredUser`, `ProfileRead`, `CurrentUser`, `UserRead` sin herencia hacia `UserInDB`), `app/routes/{users,auth,profiles}.py`, `app/core/openapi.py` (si D8 = A); backoffice `types/auth.ts`, `services/normalizers.ts`; tracker `types/auth.ts`, `services/normalizers.ts`; SPECS Parte C/D | API: `test_auth.py`, `test_register.py`, `test_profiles.py`, `test_users.py`; backoffice: los de la fila de D9; tracker: `tests/auth.test.mjs` | `services/api` (unittest + `uv run --no-sync python -m pytest`); `uis/backoffice` (tsc, lint, build, node:test, Jest); `uis/talent-pipeline-tracker` (tsc, lint, node:test). Navegador: login, registro, perfil (ver y guardar) en las dos apps |
| 2 | suppliers | `app/models.py` (`SupplierRead`), `app/routes/suppliers.py`, `app/database.py` (si el repositorio pasa a devolver el modelo interno); SPECS Parte B | `test_suppliers_api.py`, `test_suppliers_logic.py` | `services/api`; `seed` idempotente; `uis/backoffice` solo si cambia algo (el JSON no cambia). Navegador: `/suppliers` (lista, alta, tarifa, estado) |
| 3 | gestor de incidencias | `app/modules/incident_manager/{models,router}.py`; backoffice `types/incident-manager.ts`, `services/normalizers.ts`; SPECS Parte E | `test_incident_manager_api.py` (+ coherencia D6), `test_architecture.py` (sin cambios esperados); backoffice: los del gestor | `services/api`; `packages/shared` solo si se toca (no está previsto); `uis/backoffice`. `/docs`: alta, listado con filtros, cambio de estado válido e inválido, `/summary`. Navegador: `/incident-manager` |
| 4 | health, exportación, `DELETE` y cobertura | `app/main.py` (`HealthResponse`), `app/modules/incidents/router.py`, `app/routes/{users,suppliers}.py` (204), test nuevo de cobertura de `response_model`; SPECS Parte A | `test_analyze.py`, `test_export.py`, `test_errors.py`, test nuevo | `services/api`; `docker compose ps` con `api` `healthy` (el healthcheck no cambia) y `curl localhost:3001/backend/health` |

Cierre de F1 (fuera de los cuatro commits de módulo): prueba manual de al menos tres endpoints en `/docs` comparando la respuesta con el esquema (propuesta: `POST /users`, `GET /auth/me`, `GET /api/incidents`), columna «Estado final» a ✅, `memory-bank/progress.md` y, si cambia algo técnico, `techContext.md`. Push y PR `feat: serialization audit and implementation` solo con el OK del usuario.

## 8. No verificado en F0 (resuelto en F1, ver §9)

- Las respuestas reales de las rutas protegidas no se pidieron al contenedor (habría hecho falta crear una cuenta en la TinyDB de la demo): sus formas salen del código y de `openapi.json`. Se comprobará en `/docs` al cerrar F1.
- `test_profiles.py`, `test_users.py` y `test_register.py` usan ayudantes de `auth_support.py`/`conftest.py`; qué aserciones exactas cambian se confirma al ejecutarlos en F1.
- La suite de `services/api` no se ejecutó en F0 (no hay cambios de código). En el Python del host, importar SQLAlchemy falla hoy con «Una directiva de Control de aplicaciones bloqueó este archivo» (`_util_cy`, DLL compilada del venv): para F1 hará falta ejecutar los tests en un entorno donde Windows no bloquee esa DLL (o dentro del contenedor).

## 9. Verificación final (F1, 2026-10-28)

**Commits**, uno por módulo:

| Commit | Qué |
|---|---|
| `29cd134` | Procedimiento de las suites en un contenedor efímero (`services/api/TESTING.md` §14) |
| `e452889` | F1.1, auth, usuarios y perfiles (D1–D4); normalizadores de backoffice y tracker |
| `112bed6` | F1.2, proveedores (`SupplierRead`, D4–D5) |
| `1384400` | F1.3, gestor de incidencias (D4–D6, D8 B); backoffice |
| `0f2ff58` | F1.4, `/health`, exportación y `DELETE` 204 (D7) + `test_serialization.py` |

**Suites de `services/api`**, en el contenedor efímero de `TESTING.md` §14, porque el Control de aplicaciones de Windows bloquea la DLL de SQLAlchemy del venv del host:

| | `unittest` | pytest |
|---|---|---|
| Partida (`d987a06`) | 415 OK | 618 passed |
| Tras F1.1 | 415 OK | 618 passed |
| Tras F1.2 | 417 OK | 620 passed |
| Tras F1.3 | 429 OK | 632 passed |
| Tras F1.4 | **436 OK** | **639 passed** (3498 subtests) |

Los tests que cambiaron lo hicieron a propósito (D9): leían de la respuesta campos que ya no salen (`email` y `role` del registro, `user_id` del perfil) o comparaban la respuesta con el documento interno. Ninguno se borró. Los nuevos son `ResponseSchemaTests` en `test_suppliers_api.py` (incluido un documento antiguo que rompe la regla de moneda y se sigue listando), `test_incident_manager_contract.py` (coherencia D6 y OpenAPI) y `test_serialization.py` (cobertura de las 32 rutas; una mutación, quitar el `response_model` de `/health`, lo hace fallar).

**Frontends** (fila de `AGENTS.md` §4):

- **`uis/backoffice`:** `tsc`, `lint` (0 problemas), `build`, `node:test` 505/505 y Jest 240/240.
- **`uis/talent-pipeline-tracker`:** `tsc`, `node:test` 55/55 y `lint` con los 4 errores `react-hooks/set-state-in-effect` anteriores a AUTH-02 (documentados en `AGENTS.md`), ninguno nuevo.

**`/docs`, a mano**, con una cuenta de prueba temporal (`@example.invalid`), creada y borrada en la sesión:

| Endpoint | Respuesta | Esquema |
|---|---|---|
| `POST /users` | 201 `{"id": "…"}` | `RegisteredUser` ✓ (sin email) |
| *Authorize* + `GET /auth/me` | 200 `{id, email, role, created_at, profile: {name, phone, address}}` | `CurrentUser` / `ProfileRead` ✓ |
| `GET /api/incidents` | 200, filas con `id, title, description, category, status, origin, branch, created_at` | `IncidentListItem` ✓ (sin `updated_at`) |

`/docs` muestra además los esquemas de entrada del gestor y sus 400/401/404/503 sin el 422, y el 200 `text/csv` de la exportación.

**Navegador, backoffice en Docker (3001)**, con la misma cuenta: login, `/account/profile` (email, nombre y guardar el teléfono → «Perfil actualizado»), `/suppliers` (15 proveedores) e `/incident-manager` (resumen y listado de 97). La primera carga de `/incident-manager` mostró «No se pudo comprobar la sesión»: un `socket hang up` puntual del proxy `/backend` (`Failed to proxy … ECONNRESET` en el log de `ui`; la API no registró ningún error). Con «Reintentar» cargó bien. No se cambió ningún estado ni proveedor de la demo.

**Cuenta borrada** con la API: login, `/auth/me` con su email, `DELETE /users/{id}` → 204 (borra también el `Profile`). Después, el login da 401 y `services/api/data/auth.json` no contiene ni su email ni su id. El archivo de credenciales del scratchpad se eliminó.

**Docker:** `api` sigue `healthy` con `HealthResponse` y `curl localhost:3001/backend/health` → `{"status":"ok"}`. El seed de proveedores (`docker compose exec api python -m app.seed`) inserta 0 de 15.

**No verificado:**

- **El tracker en el navegador.** Corre fuera de Docker (3002) y el `.env` de la raíz no incluye `http://localhost:3002` en `CORS_ALLOWED_ORIGINS`. No se tocó esa configuración. Sus cambios (normalizador y tipos de `/auth/me` y del perfil) están cubiertos por `tests/auth.test.mjs`.
- **El registro desde la UI** (`/register`) en el navegador: crearía una segunda cuenta. Los dos frontends descartan el cuerpo del 201, y lo cubren los tests de su servicio.
- **Trabajo futuro (D8 A):** errores documentados en `responses=` fuera del gestor.

