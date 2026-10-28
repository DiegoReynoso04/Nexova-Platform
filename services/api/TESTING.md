# TESTING — Baterías de pruebas de `services/api` (AUTH-088, extras e inventario)

## 1. Qué cubre y por qué

AUTH-088 nace de una regresión real: la expiración de los tokens dejó de respetar `ACCESS_TOKEN_EXPIRE_MINUTES`. Esta batería cubre los 12 endpoints de autenticación, el JWT y su configuración. Por endpoint hay al menos un camino feliz, un caso límite y un modo de fallo.

Cada test afirma una **decisión de negocio** (quién puede hacer qué, qué se guarda y qué se rechaza) llamando directamente a la lógica: rutas, servicio, repositorio, seguridad y dependencias. No usa TestClient ni HTTP. Las bases TinyDB son temporales (`tmp_path`), el reloj es inyectado y el sender de email es falso. Una fixture comprueba que `data/*.json` no cambia en toda la sesión. Las fixtures están en [`tests/conftest.py`](tests/conftest.py).

## 2. Cómo ejecutar

Desde `services/api` (comprobado en Windows con PowerShell):

| Qué | Comando |
|---|---|
| Toda la suite (las baterías nuevas + los 312 tests `unittest` anteriores) | `uv run pytest` |
| Ídem con la cobertura de toda la app | `uv run pytest --cov` |
| Cobertura del módulo de auth con umbral | `uv run pytest --cov=app.auth --cov=app.routes.auth --cov=app.routes.users --cov=app.routes.profiles --cov-fail-under=70` |
| Ídem, informe a partir del último `--cov` | `uv run python -m coverage report --include="app/auth/*,app/routes/auth.py,app/routes/users.py,app/routes/profiles.py" --fail-under=70` |
| Solo la batería de auth | `uv run pytest tests/test_token.py tests/test_login.py tests/test_register.py tests/test_users.py tests/test_profiles.py tests/test_forgot_password.py tests/test_reset_password.py tests/test_change_password.py` |
| Suite anterior con `unittest` (`AGENTS.md` §4, desde la raíz) | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` |

- **`coverage.exe`:** el Control de aplicaciones de Windows (error 4551) puede bloquear los lanzadores `.exe` sin firmar de uv. Durante el desarrollo de esta batería llegó a bloquear `coverage.exe` (hoy arranca). `uv run python -m coverage …` funciona siempre y no depende del `.exe`.
- **No ejecutes `uv sync`:** sincroniza de forma exacta y desinstala `nexova-shared` y `nexova-incident-analyzer`, que se instalan con pip a propósito (ver [`README.md`](README.md#instalación-desde-la-raíz-del-monorepo)). `uv run` sí los conserva. pytest los encuentra igualmente (`pythonpath` en `pyproject.toml`), pero el comando `unittest` los necesita instalados. Si se perdieron, reinstálalos desde la raíz: `services\api\.venv\Scripts\python -m pip install --no-deps -e packages/shared -e packages/incident-analyzer`.

**Jest (lógica TypeScript de auth en `uis/backoffice`):** ver §10.
**Extras:** proveedores y gestor de incidencias con pytest (API-042) en §11; utilidades del frontend con Jest (FE-019) en §12.
**Inventario (Hito 5):** §13.
**Si el Control de aplicaciones de Windows bloquea el venv** (DLL de SQLAlchemy): las dos suites en un contenedor efímero, §14.

## 3. Plan de pruebas

| Endpoint | Camino feliz | Caso límite | Modo de fallo | Archivo |
|---|---|---|---|---|
| JWT y configuración | `exp = iat + N·60` (1, 30 y 1440 min) y `expires_in` coherente | 1 s antes / después de caducar; tope de 525600 / 525601 min; clave de 31 / 32 caracteres | otra clave, HS512, `alg: none`, sin `sub` o `exp`, token malformado; minutos ausentes, ≤ 0 o no enteros | [`test_token.py`](tests/test_token.py) |
| `POST /auth/login` | token del usuario con `expires_in` correcto | email con mayúsculas y espacios; más de 72 bytes no llega a bcrypt | contraseña incorrecta = email desconocido (con burn); email mal formado → 401; inactivo; vacía; NUL | [`test_login.py`](tests/test_login.py) |
| `GET /auth/me` | usuario con perfil, sin credenciales | sin perfil → `profile: null` | token de un usuario borrado o inactivo; sin token → 401 | [`test_token.py`](tests/test_token.py) |
| `POST /users` | `user` activo, hash verificable, perfil, sin hash en la respuesta | 7 / 8 caracteres; 72 / 73 bytes; multibyte (ñ, emoji); email de 254 / 255; perfil de 200 / 201 | duplicado (también en mayúsculas o con espacios) sin segundo perfil; `role`, `id`, `is_active`…; vacíos; NUL | [`test_register.py`](tests/test_register.py) |
| `GET /users` | el admin lista sin hashes | `manager` no es admin | `user` → 403 | [`test_users.py`](tests/test_users.py) |
| `GET /users/{id}` | uno mismo; el admin sobre otro | el admin sobre un inexistente → 404 | un no-admin sobre otro → 403, exista o no | [`test_users.py`](tests/test_users.py) |
| `PUT /users/{id}` | email propio normalizado; el admin fija contraseña y rol | cuerpo vacío o `null` sin cambios; email propio en mayúsculas sin 409 | H-1: `password` de un no-admin → 403 sin aplicar nada; `role` → 403 (antes que `password`); email ajeno → 409; inexistente → 404 | [`test_users.py`](tests/test_users.py) |
| `DELETE /users/{id}` | borrado propio en cascada y el token antiguo da 401 | doble borrado → 404 | un no-admin sobre otro → 403; el admin sobre un inexistente → 404 | [`test_users.py`](tests/test_users.py) |
| `GET /profiles/me` | el perfil propio | campos sin dato como `null` | usuario sin perfil → 404 | [`test_profiles.py`](tests/test_profiles.py) |
| `PUT /profiles/me` | actualización parcial | `null` borra; vacío sin cambios; `strip` y 200 / 201 | `user_id`, `id`, `email` → 422; sin perfil → 404 sin crearlo | [`test_profiles.py`](tests/test_profiles.py) |
| `POST /auth/forgot-password` | solo el SHA-256 en la base, `expires_at`, auditoría y email encolado | email normalizado; un único enlace pendiente; purga de los caducados | email desconocido o inactivo: la misma respuesta, sin token ni email; fallo del proveedor → solo la clase en el log | [`test_forgot_password.py`](tests/test_forgot_password.py) |
| `POST /auth/reset-password` | la nueva vale, la antigua no; `used_at` y auditoría | 1 s antes vale, en `expires_at` caduca; dos resets simultáneos → un único `VALID` | usado, caducado, anulado, usuario borrado o inactivo, desconocido → el mismo 400 con el motivo auditado; token `""` / 513 | [`test_reset_password.py`](tests/test_reset_password.py) |
| `POST /auth/change-password` | cambia, audita y anula los enlaces pendientes | nueva igual a la actual; actual de más de 72 bytes | actual incorrecta → 400 (no 401) sin cambios; actual con NUL sin bcrypt; usuario borrado → 404 | [`test_change_password.py`](tests/test_change_password.py) |

## 4. Por qué estos casos

Se eligieron los casos donde un error tiene coste real:
- **La regresión del ticket:** la expiración del token.
- **Los límites de bcrypt:** 72 bytes (no caracteres) y el byte NUL.
- **La no enumeración de usuarios:** misma respuesta y mismo coste de bcrypt exista o no el email.
- **H-1:** un no-admin no puede fijar su contraseña sin la actual.
- **La frontera de caducidad de los enlaces:** `expires_at` ya no vale.
- **El uso único bajo concurrencia.**

**Cómo se validó que los tests sirven:** cada regla se rompió a propósito en `app/` (mutación), se comprobó que algún test falla y se deshizo el cambio (`git diff -- app` vacío).

| Mutación | Test que la detecta |
|---|---|
| `minutes * 60` → `minutes * 1` (la regresión del enunciado) | 8 casos de 4 tests, entre ellos `test_token_expires_exactly_the_configured_minutes_after_issue` y `test_expires_in_matches…` |
| Quitar `require_exp` / aceptar HS512 | `test_token_without_a_usable_sub_or_exp_is_rejected[sin exp]` / `test_token_not_signed_with_hs256…[HS512…]` |
| Quitar el burn del login | `test_malformed_email_is_rejected_as_bad_credentials_after_burning` |
| Quitar el tope de minutos | `test_expiration_beyond_the_technical_cap_is_rejected_at_startup` |
| Quitar `normalize_email` | 8 tests de registro y usuarios |
| Límite de 72 bytes → 72 caracteres | `test_password_limits_count_bytes…[ñ x37]` y `[emoji x19]` |
| Quitar el NUL del validador / de `verify_password` | `test_new_password_with_nul_byte…` (4 casos) / `test_password_with_nul_byte_fails_like_bad_credentials…` |
| Quitar la regla H-1 / invertir el orden rol-contraseña | `test_non_admin_cannot_set_a_password…` / `test_role_rule_is_checked_before_the_password_rule` |
| `delete_user` sin borrar el perfil | `test_deleting_yourself_removes_profile_and_invalidates_your_token` |
| `<=` → `<` en la caducidad del enlace | `test_link_is_expired_exactly_at_its_expiry_instant` |
| No anular los enlaces pendientes (nuevo enlace / change-password) | `test_only_the_latest_link_is_pending…` / `test_change_sets_the_new_password…`, y los casos «anulado» de `test_unusable_link_is_rejected…` |
| No marcar `used_at` | `test_valid_link_sets_the_new_password_and_is_marked_used`, `[ya usado]` y la concurrencia |
| Quitar el lock de `consume_reset_token` | `test_two_simultaneous_resets_with_the_same_link_succeed_exactly_once` (10 de 10) |
| Encolar el email también para desconocidos | `test_unknown_or_inactive_email_gets_the_same_answer…` |

## 5. Bugs encontrados y corregidos

| | Tope de minutos del token | Byte NUL en la contraseña | Título del gestor con emojis (backoffice) |
|---|---|---|---|
| **Lo destapó** | Caso de la IA: un valor que la configuración acepta no puede romper cada login (primera versión del test de `test_token.py`) | Caso de la IA: ¿un NUL en la contraseña es un error de validación o un 500? | Un caso límite de la batería de utilidades (§12): ¿el cliente cuenta los caracteres del título como la API? |
| **Síntoma** | Con `ACCESS_TOKEN_EXPIRE_MINUTES = 10**10` la API arrancaba, pero cada login daba 500 (`OverflowError`) | 500 en el registro, el login (con email existente o desconocido), el reset, el cambio de contraseña (nueva y actual) y el `PUT /users/{id}` del admin | Con 61 emojis, el formulario de alta de incidencias decía «no puede superar los 120 caracteres» y el contador marcaba 122 / 120, aunque la API acepta ese título |
| **Causa** | `Settings` solo rechazaba 0 y negativos; `iat + timedelta` se salía del rango de `datetime` | bcrypt rechaza el NUL (`PasswordValueError`) y ni `_check_password` ni `verify_password` lo tenían en cuenta | El cliente medía con `.length` (unidades UTF-16: un emoji vale 2) y la API con `len()` de Python (caracteres) |
| **Corrección** | Tope técnico de 525600 min (1 año) con `ConfigError` al arrancar. No es una política de sesión: la decide el CTO | El validador rechaza el NUL (422); `verify_password` devuelve `False` sin bcrypt (401 en el login, 400 como contraseña actual) | `countCharacters` (`[...value].length`, un carácter por punto de código), usada por la validación y por el contador. Era el único límite de longitud que comprobaba el cliente |
| **Commit** | `65cfb36` | `988ff96` | `1ddaaf8` |
| **Tests** | `test_expiration_at_the_technical_cap…` y `…beyond_the_technical_cap…` | `test_new_password_with_nul_byte…`, `test_password_with_nul_byte…` (login) y `test_current_password_with_nul_byte…` | `61 emojis are accepted` y el resto del límite del título en `__tests__/utils/incident-manager.service.test.ts` |

## 6. Casos propuestos por la IA

**Cómo se usó la IA:** un agente propuso el plan por endpoint y casos límite adicionales. El desarrollador decidió cuáles entraban como test y cuáles solo se documentaban (lo que recoge esta sección). También revisó cada test y cada corrección antes de confirmarlos. Ningún bug se corrigió sin una decisión explícita suya.

**Aceptados como test:**
- Minutos enormes: destapó el primer bug.
- Byte NUL: destapó el segundo bug.
- Dos resets simultáneos con el mismo enlace. Medido en 200 rondas: con lock, todas correctas; sin lock, ninguna (31 con doble uso y el resto con el archivo TinyDB corrupto). El lock protege también la integridad del archivo.

**Solo documentados** (son decisiones de producto pendientes, no bugs):

| Caso | Comportamiento actual y motivo |
|---|---|
| Contraseña solo con espacios | Se acepta si tiene 8 caracteres o más: ninguna regla documentada la prohíbe |
| NFC / NFD | No se normaliza: la misma «ñ» compuesta o descompuesta son contraseñas distintas |
| Longitud de `JWT_SECRET_KEY` | Se mide en caracteres, no en bytes ni en entropía (D-AUTH-4) |
| Emails Unicode | Se aceptan con la validación sencilla sin dependencias (D-AUTH-6) |
| Enlace de reset tras cambiar el email | Sigue valiendo: el token va ligado al usuario, no al email |
| `iat` / `nbf` en el futuro | Un `iat` futuro se acepta (solo se exigen firma, `sub` y `exp`, D-AUTH-5); un `nbf` futuro lo rechaza python-jose |
| Perfil `"   "` | Se guarda como `""`, no como `null` |
| Último admin | Puede borrarse o quitarse el rol; se recupera con `uv run create-admin` |
| Filas huérfanas | Borrar un usuario conserva sus enlaces de reset y su auditoría (los enlaces ya no sirven) |

## 7. Riesgos conocidos (documentados, no fijados por tests)

Detalle en [`docs/auth-password-reset.md`](../../docs/auth-password-reset.md) §14 y [`SPECS.md`](SPECS.md) §27.

| ID | Riesgo |
|---|---|
| M-1 | Restablecer o cambiar la contraseña no invalida los JWT ya emitidos |
| M-2 | `forgot-password` tarda unos ms más para un email existente (una escritura más) |
| M-3 | Sin límite de peticiones en `forgot-password` |
| H-1 residual | Un admin fija contraseñas con `PUT /users/{id}` sin la actual, sin anular enlaces ni auditar |
| L-1 | La contraseña nueva se hashea antes de validar el token (coste de bcrypt por petición anónima) |
| L-2 | `PASSWORD_RESET_URL` admite `http://` |
| L-3 | El token aparece en la URL de la primera carga |
| L-4 | **Resuelto** por A1 (`24f0e0d`): `http.client.HTTPException` ya se convierte en `EmailDeliveryError` |
| L-5 | Auditoría con IP sin política de retención |
| L-6 | Con otra sesión abierta, tras el reset no se ve el aviso de éxito |
| Id de proveedor reutilizado | TinyDB reutiliza el `id` del último proveedor borrado: se borra el 2, se crea otro y recibe el 2. Quien conserve el id antiguo podría modificar o borrar el nuevo. Ningún documento lo prohíbe (D-SUP-4: «`id` = `doc_id` de TinyDB»; D-AUTH-2 ya advierte de que ese id no es estable). La UI no borra proveedores. Solo documentado, sin test ni cambios |

## 8. Límites de la batería

- **`exp == ahora` exacto:** no se prueba porque python-jose usa su propio reloj. La frontera se acota con −5 s y +1 s.
- **Sin cubrir con la batería de auth sola** (los cubre la suite anterior):
  - el sender real de Resend (exige simular `urlopen`);
  - `create-admin` (CLI interactiva);
  - el cableado de FastAPI en `dependencies.py` (`get_settings` y similares). Los tests llaman a las funciones con las dependencias ya resueltas.

## 9. Resultados

Medidos con los comandos de §2: la batería de auth el 2026-10-12; la suite completa, el 2026-10-13.

| Medida | Batería de auth sola | Suite completa |
|---|---|---|
| Tests | 143 | 515 (312 anteriores + 143 de auth + 60 de §11) |
| Cobertura del módulo de auth (`app/auth/*` y `app/routes/{auth,users,profiles}.py`) | 86 % | 99 % |
| Cobertura de toda la app (`app/`) | — | 98 % |
| Tiempo aproximado | ~10 s | ~1–2 min según la carga de la máquina (bcrypt real en la suite anterior) |

## 10. Jest: lógica TypeScript de autenticación (`uis/backoffice`)

Desde `uis/backoffice`: `npm run test:jest` (equivale a `jest --coverage`). Jest solo recoge `__tests__/**/*.test.ts` (configuración en [`jest.config.mjs`](../../uis/backoffice/jest.config.mjs)). La suite anterior de `node:test` (`tests/*.test.mjs`, comando en `AGENTS.md` §4) sigue igual y ya cubría parte de esta lógica; Jest es lo que pide el ticket y las dos conviven.

| Archivo probado | Qué afirman los tests | Test |
|---|---|---|
| `lib/auth-token.ts` | Un token de espacios o un almacenamiento que lanza cuentan como «sin sesión»; guardar un token en blanco no guarda ni avisa; si `setItem` falla se avisa igualmente; los cambios de otra pestaña se escuchan y los de otras claves no | [`auth-token.test.ts`](../../uis/backoffice/__tests__/auth/auth-token.test.ts) |
| `lib/auth-routes.ts` | `/reset-password` se abre con o sin sesión; las páginas públicas mandan a inicio con sesión; en «Reintentar» se mantiene el aviso de error; `/LOGIN` o una ruta nueva quedan protegidas | [`auth-routes.test.ts`](../../uis/backoffice/__tests__/auth/auth-routes.test.ts) |
| `services/auth.service.ts` | Validación en cliente (requeridos y confirmación), bodies sin `role` ni confirmación, y el servicio con un cliente HTTP falso: el token solo se guarda si la respuesta se normaliza bien; cada error de la API se traduce a un tipo para la UI | [`auth.service.test.ts`](../../uis/backoffice/__tests__/auth/auth.service.test.ts) |
| `services/normalizers.ts` (auth) | Token vacío o `expires_in` no entero → error; solo se copian los campos del contrato; los errores no repiten valores recibidos; los 422 mal formados no lanzan | [`normalizers.test.ts`](../../uis/backoffice/__tests__/auth/normalizers.test.ts) |
| `hooks/use-auth-session.ts` | Reducer, estado derivado y textos del guard; el controlador valida cada token una vez, ignora el 401 (ya no hay token) y el resultado de un token antiguo | [`use-auth-session.test.ts`](../../uis/backoffice/__tests__/auth/use-auth-session.test.ts) |

**Qué no existe en TypeScript y no se prueba:** la generación de tokens, el decodificado de JWT y el hash de contraseñas. El backoffice recibe el JWT de `POST /auth/login` como una cadena opaca, lo guarda y lo envía como `Bearer`. Quién es el usuario y si el token sigue valiendo lo decide la API (`GET /auth/me`). Las contraseñas viajan a la API, que es la única que las hashea (bcrypt). Decodificar el JWT en el cliente obligaría a confiar en datos que el cliente no puede verificar. Comprobado buscando `atob`, `jwt-decode`, `bcrypt`, `crypto.subtle` y `createHash` en el código de producción: no aparecen.

**Validación con mutaciones** (código restaurado después):

| Mutación | Test que la detecta |
|---|---|
| `readAuthToken` sin `trim` | `a token made only of spaces counts as no session` |
| `/reset-password` tratada como solo pública | `/reset-password renders with session authenticated…` |
| Guardar el token aunque la normalización falle | `a 200 with empty access_token…` y `…non-integer expires_in…` |
| `normalizeAccessToken` acepta un `expires_in` no entero | 2 tests de `normalizeAccessToken` y 1 del servicio |

**Resultados** (medidos el 2026-10-12): 112 tests de auth en ~1 s (de los 161 que ejecuta `npm run test:jest` junto con §12). Cobertura de líneas (Jest):

| Archivo | Líneas | Motivo de lo no cubierto |
|---|---|---|
| `lib/auth-routes.ts` | 100 % | — |
| `lib/auth-token.ts` | 100 % (87,5 % de ramas) | Las ramas sin `window` (guardar, borrar y suscribirse en el servidor) |
| `services/auth.service.ts` | 93,4 % | Un 422 sin JSON, los errores de configuración y de timeout, y los atajos exportados del servicio por defecto |
| `hooks/use-auth-session.ts` | 80,3 % | El hook de React (`useAuthSession`): necesita React y se valida en el navegador |
| `services/normalizers.ts` | 58,5 % | Lo no cubierto son normalizadores de incidentes y proveedores, no de auth (los cubre `node:test`) |
| **Total de los cinco archivos** | **80,2 %** | |

## 11. Extra: proveedores y gestor de incidencias (pytest)

Misma forma que la batería de auth: llamadas directas a las funciones de ruta y a los repositorios, con TinyDB temporal y reloj inyectado, sin TestClient. Las suites anteriores (`test_suppliers_api.py` y `test_incident_manager_*.py`) ya cubrían el contrato HTTP y el repositorio del gestor por dentro. Esta batería fija las decisiones que solo se probaban por HTTP o que no se probaban.

| Endpoint | Camino feliz | Caso límite | Modo de fallo |
|---|---|---|---|
| `POST /suppliers` | id y `updated_at` = hora de creación; nombre recortado | tarifa de 0,01 o entera; 29-02-2028; las 9 categorías | moneda de otro país; país, categoría o estado fuera del CONTEXT; tarifa 0, de texto o infinita; `id`/`updated_at` del cliente |
| `GET /suppliers` | todos | categoría que coincide con cualquiera de las del proveedor; directorio vacío | país + categoría (AND) sin coincidencias |
| `GET` / `PATCH` / `DELETE /suppliers/{id}` | lectura; la tarifa registra la hora; suspender y reactivar | el estado **no** toca `updated_at` (es la traza de la tarifa) | id inexistente → 404 en las cuatro operaciones, sin escribir; doble borrado |
| Seed de proveedores | inserta lo que falta | idempotente por `name` | un proveedor existente (aunque editado) no se pisa |
| `POST /api/incidents` | nace `open`, texto recortado, fechas del reloj | título de 120 / 121 caracteres | sin sede, nace resuelta, categoría desconocida o `id` del cliente → 400 sin escribir |
| `GET /api/incidents` | filtros combinados con AND (cada uno necesario) | orden por fecha descendente y desempate por `id` con la misma fecha | filtro fuera del vocabulario → 400 (no una lista vacía) |
| `GET /api/incidents/summary` | totales por estado | gestor vacío → todo a cero | — |
| `GET /api/incidents/{id}` | la incidencia | — | id inexistente → 404 |
| `PATCH /api/incidents/{id}/status` | cambia `status` y `updated_at`, no `created_at` | `open → discarded` directo; `discarded` es final | transición inválida → 400 sin tocar el archivo; id inexistente → 404; cuerpo mal formado → 400 |
| Seed del gestor | idempotente por clave de origen | conserva la fecha y el estado del histórico | — |

**Cómo ejecutarla sola** (desde `services/api`): `uv run pytest tests/test_suppliers_logic.py tests/test_incident_manager_logic.py --cov=app.routes.suppliers --cov=app.database --cov=app.models --cov=app.modules.incident_manager --cov-fail-under=60`

**Cobertura de esos módulos:** 92,6 % con la batería sola (60 tests, menos de 1 s) y 99,0 % con la suite completa. Con la batería sola falta, sobre todo, la capa HTTP del router del gestor (`IncidentManagerRoute`), que convierte los errores de lectura de la petición y que cubren los tests de HTTP.

| Mutación | Test que la detecta |
|---|---|
| El cambio de estado de un proveedor toca `updated_at` | `test_status_change_does_not_touch_updated_at` |
| La tarifa no registra `updated_at` | `test_rate_change_records_the_time_of_the_change` |
| Sin el filtro de categoría (proveedores) | `test_category_filter_matches_any…` y `test_country_and_category_filters_combine_with_and` |
| El seed de proveedores no comprueba el `name` | `test_seed_inserts_only_names_not_yet_present…` |
| Aceptar una transición inválida | `test_invalid_transition_is_rejected_and_writes_nothing` y el de `discarded` final |
| Invertir el orden del listado | `test_list_is_newest_first_and_ties_are_broken_by_id` |
| Sin el filtro de origen, de sede o de categoría (gestor) | `test_filters_are_combined_with_and` |
| El seed del gestor no comprueba la clave de origen | `test_seed_is_idempotent_by_source_key…` |

La mutación del filtro de origen sobrevivió a la primera versión del test de filtros, porque las incidencias descartadas se distinguían por otro campo además del origen. Se reforzó para que cada una difiera en un solo campo.

## 12. Extra: utilidades del frontend (Jest, `uis/backoffice`)

Tests en `uis/backoffice/__tests__/utils/`. La suite de `node:test` ya cubría los casos generales de estas funciones; aquí van los límites que faltaban.

| Utilidad | Qué afirman los tests |
|---|---|
| `lib/supplier-renewal.ts` (`daysUntil`, `renewalInfo`) | Hoy, día 59 (29-02-2028), día 60 (incluido) y día 61 alrededor de un año bisiesto; la hora del día y los cambios de horario no alteran la cuenta; 2026-02-30, 2027-02-29, 2026-2-3 o un mes 13 o 0 → fecha no válida, sin destacar; `null` y fecha pasada |
| `services/suppliers.service.ts` (`parseRate`, `validateSupplierForm`) | Coma decimal admitida; `0,00`, separador de miles, signos, símbolo de moneda o `Infinity` → no válida; las fechas y el email opcionales los valida la API, no el cliente |
| `services/incident-manager.service.ts` (`countCharacters`, `validateIncidentForm`, `messageForApiError`) | Título de 120 / 121 caracteres contados como la API, también con emojis; descripción en blanco y sede obligatoria para cualquier origen; textos propios por código de error, nunca el mensaje del servidor |
| `services/normalizers.ts` (`normalizeApiErrorBody`) | Conserva `code` y un `detail` de texto; un `detail` estructurado se descarta |

**Cómo ejecutarla sola** (desde `uis/backoffice`): `npx jest __tests__/utils --coverage`. `npm run test:jest` ejecuta auth y utilidades juntas: 161 tests en ~1 s.

**Cobertura (líneas):**
- `lib/supplier-renewal.ts`: 100 %.
- `services/suppliers.service.ts`: 35,2 %.
- `services/incident-manager.service.ts`: 44,3 %.
- `services/normalizers.ts`: 58,5 %.

Las cinco funciones probadas quedan cubiertas al 100 %. El resto de esos archivos son los `build*Payload`, las clases de error y la parte HTTP de cada servicio, que cubre `node:test`.

| Mutación | Test que la detecta |
|---|---|
| La ventana de renovación excluye el día 60 | `today and up to day 60 (included) are upcoming…` |
| Sin la comprobación de calendario (acepta 2026-02-30) | 6 tests de fechas no válidas |
| `parseRate` sin coma decimal | 3 tests de tarifa |
| `status` con `invalid_choice` recibe el texto genérico | `each known code on a form field gets its own Spanish text…` |
| La descripción sin recortar | `a description made of spaces and a missing branch are reported…` |
| Volver a `.length` en el título | `61 emojis are accepted`, `120 emojis are accepted` y `countCharacters` |

## 13. Inventario (Hito 5)

Batería del inventario de equipos y materiales (`app/modules/inventory/`, `SPECS.md` Parte F): 97 tests `unittest`, que recogen los dos comandos de §2.

- **Cómo trabaja:** `TestClient` con `with` (el lifespan crea las tablas), servicios llamados directamente y el comando del seed en proceso y en un subproceso.
- **Base de datos:** SQLite en memoria (`sqlite://`) o en un archivo temporal, con `PRAGMA foreign_keys=ON`, para que las FK se apliquen de verdad. **Ningún test conecta con Supabase.**
- **Lo propio de PostgreSQL**, sin conexión: el DDL y la SQL se compilan con su dialecto (FK, `UNIQUE`, `TIMESTAMPTZ`, sin ENUM, `CHECK`, `FOR UPDATE`, sentencias de RLS).
- **Base caída:** el arranque se prueba contra un puerto local cerrado.

| Archivo | Qué fija |
|---|---|
| `test_inventory_database.py` (34) | `DATABASE_URL` obligatoria y solo con esquemas de PostgreSQL desde el entorno, sin repetir la URL; motor (psycopg2 forzado, `NullPool`, `connect_timeout`); esquema; restricciones aplicadas en SQLite; RLS; ninguna sesión global y `get_db` por petición; 503 sin la SQL ni los datos de conexión; lifespan y `dispose()` |
| `test_inventory_startup.py` (3) | `InventoryStartupError` sin `__cause__`/`__context__` y con el proceso vivo; uvicorn real sale con código 3 sin host, usuario, contraseña ni `psycopg2` en la salida |
| `test_inventory_products.py` (23) | Rutas de productos; stock = entradas − salidas (10 + 5 − 2 − 1 = 12, donde un JOIN sin agregar daría 24); una sola consulta con 1 y con 20 activos; 409 también en carrera; ningún `response_model` hereda de SQLModel; `/inventory/products/{id}` en OpenAPI; los errores de cada ruta documentados en OpenAPI (`ErrorResponse`, 401/503 comunes y los propios, con el mensaje literal de `insufficient_stock`) |
| `test_inventory_orders.py` (24) | Los casos del evaluador; oficina; 404; orden de las comprobaciones; `user_uuid` del token y rechazado en el body; límites de cantidad; salida igual al stock; `/orders` (forma, orden, desempate y número de consultas); `FOR UPDATE`; 401 |
| `test_inventory_seed.py` (13) | Primera ejecución 6/4/3 y segunda 0; activos existentes con órdenes; datos que rompen el stock (nada escrito); códigos 1 y 2 (también en subproceso); `GET /inventory/products` exacto tras el seed (caso del evaluador) y 7 órdenes con el `user_uuid` del usuario |

**Cómo ejecutarla sola** (desde `services/api`):

```bash
uv run --no-sync python -m unittest tests.test_inventory_database tests.test_inventory_startup tests.test_inventory_products tests.test_inventory_orders tests.test_inventory_seed
```

`uv run --no-sync python -m pytest tests/test_inventory_*.py` es equivalente. Si el Control de aplicaciones de Windows bloquea `pytest.exe` (os error 4551, visto el 2026-10-17), `python -m pytest` funciona igual.

**Mutaciones** (aplicadas una a una y deshechas; todas detectadas):

| Mutación | Test que la detecta |
|---|---|
| Sin `PRAGMA foreign_keys=ON` | `test_foreign_key_is_enforced`, `test_sqlite_engine_shares_one_connection_with_foreign_keys_on` |
| `init_db` sin RLS, o RLS sin el `ALTER` | `test_init_db_enables_rls_after_creating_the_tables`, `test_postgresql_enables_rls_on_the_three_tables` |
| Una `Session` a nivel de módulo, o cacheada en `get_db` | `test_no_session_is_created_at_module_level`, `test_each_request_gets_its_own_session_and_it_is_closed`, `test_sessions_are_only_opened_inside_get_db` |
| Sin forzar psycopg2 | `test_postgresql_url_uses_psycopg2_without_connecting` y el test de uvicorn |
| `InventoryStartupError` lanzada dentro del `except` | los tres de `test_inventory_startup.py` (uvicorn imprime entonces `localhost` y `psycopg2`) |
| JOIN sin agregar antes, sin `COALESCE` o N+1 en el listado | `test_current_stock_is_entries_minus_exits`, `test_list_uses_the_same_single_query_for_1_and_20_assets` |
| Sin capturar el `IntegrityError` del SKU | `test_duplicate_sku_in_a_race_is_409_not_500` |
| Sin `extra="forbid"`; una ruta que devuelve el ORM; router sin JWT | `test_invalid_bodies_are_422`; `test_every_inventory_route_has_a_non_orm_response_model`; `test_every_product_route_requires_a_token` |
| Sin `FOR UPDATE`; stock comprobado después de insertar; `>=` en vez de `>` | `test_asset_query_locks_the_row_in_postgresql`; `test_exit_equal_to_stock_is_accepted_and_leaves_zero` (y el de la salida mayor que el stock) |
| Sin comprobar la oficina; `user_uuid` del body; N+1 en `/orders`; validador de `assigned_to` sobre el body | `test_office_mismatch_is_400_and_writes_nothing`; `test_user_uuid_in_the_body_is_rejected`; `test_same_number_of_queries_with_1_and_20_orders`; `test_allocation_without_assigned_to_is_422_on_that_field` |
| Sin el 503 común en OpenAPI; sin el ejemplo de `insufficient_stock` | `OpenApiErrorsTests` |
| Seed sin buscar el SKU; salidas del seed sin la regla del stock; órdenes duplicadas en la segunda ejecución; lifespan sin `dispose()` | `test_first_run_inserts_everything_and_second_run_inserts_nothing`; `test_seed_data_that_breaks_the_stock_rule_writes_nothing`; `test_existing_assets_with_orders_are_not_duplicated`; `test_shutdown_disposes_the_engine` |

**Totales tras el Hito 5:** `unittest` 409 OK (312 + 97) y `uv run pytest` 612 OK (515 + 97).

## 14. Ejecución en un contenedor efímero (cuando Windows bloquea el venv)

Desde la auditoría de serialización (2026-10-28), el Control de aplicaciones de Windows bloquea en el venv del host una DLL compilada de SQLAlchemy (`ImportError: DLL load failed while importing _util_cy: Una directiva de Control de aplicaciones bloqueó este archivo`): ninguno de los dos comandos de §2 llega a importar la app. Alternativa sin tocar `pyproject.toml`, `uv.lock`, `requirements.txt` ni el Dockerfile: un contenedor de un solo uso (`--rm`) con la imagen de `api` que construye `docker compose` (`nexova-api:latest`; si no existe, `docker compose build api`).

- **Qué se monta:** el monorepo entero en **solo lectura** (`/repo:ro`), no solo `services/api/tests`. La imagen excluye los tests (`services/.dockerignore`) y además ellos leen fuera de `services/api` a partir de `REPO_ROOT` (`tests/support.py`): fixtures de `packages/incident-analyzer/tests/fixtures/`, `scripts/seed_incidents.py`, `docs/ligthweight-storage-api.md`, `uv.lock`. Así se prueba el código del árbol de trabajo (no la copia de `app/` de la imagen) y el contenedor no puede escribir en el repositorio; las bases temporales van a `/tmp` del contenedor. `PYTHONDONTWRITEBYTECODE=1` (de la imagen) y `-p no:cacheprovider` evitan `__pycache__` y `.pytest_cache`.
- **Paquetes del monorepo:** por `PYTHONPATH` desde `/repo/packages`, como hace la imagen.
- **Dependencias de test:** solo dentro del contenedor y se pierden al salir, con `--no-deps` y las versiones exactas del grupo `dev` de `uv.lock` y sus transitivas que no están en `requirements.txt`: `httpx==0.28.1 httpcore==1.0.9 certifi==2026.7.22 pytest==9.1.1 pytest-cov==7.1.0 coverage==7.16.2 pluggy==1.6.0 iniconfig==2.3.1 packaging==26.3 pygments==2.21.0`. Hacen falta también para `unittest`: `TestClient` necesita `httpx`, y el descubrimiento de `unittest` importa los módulos de estilo pytest (`import pytest`), que en el venv del host sí lo tienen. Sin pytest, `unittest` da 10 errores de importación.
- **Sin variables del `.env`:** los tests inyectan su propia `Settings`; no se pasa `--env-file` ni ningún secreto.

Desde la raíz, en PowerShell:

```powershell
docker run --rm -v "${PWD}:/repo:ro" -w /repo/services/api -e PYTHONPATH=/repo/packages/shared:/repo/packages/incident-analyzer nexova-api:latest sh -c "uv pip install --system --no-cache --no-deps -q httpx==0.28.1 httpcore==1.0.9 certifi==2026.7.22 pytest==9.1.1 pytest-cov==7.1.0 coverage==7.16.2 pluggy==1.6.0 iniconfig==2.3.1 packaging==26.3 pygments==2.21.0 && python -m unittest discover -s tests -t . && python -m pytest -q -p no:cacheprovider"
```

En Git Bash, lo mismo con `MSYS_NO_PATHCONV=1` delante y `"$(pwd -W):/repo:ro"` como volumen (sin ello Git Bash reescribe las rutas `/repo/…`).

**Cifras de partida** con este procedimiento, sobre `main` en `d987a06` (2026-10-28): `unittest` **415 OK** y `pytest` **618 passed** (3164 subtests). Un aviso esperado: `StarletteDeprecationWarning` de `starlette.testclient` por `httpx`.

**Tras la auditoría de serialización** (`0f2ff58`, mismo procedimiento): `unittest` **436 OK** y `pytest` **639 passed** (3498 subtests). Los 21 nuevos están en `test_suppliers_api.py` (`ResponseSchemaTests`), `test_incident_manager_contract.py` y `test_serialization.py` (cobertura de `response_model` en las 32 rutas). Detalle en [`docs/serialization-audit.md`](../../docs/serialization-audit.md) §9.
