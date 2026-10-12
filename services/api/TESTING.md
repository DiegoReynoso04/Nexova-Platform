# TESTING — API de autenticación (AUTH-088)

## 1. Qué cubre y por qué

AUTH-088 nace de una regresión real: la expiración de los tokens dejó de respetar `ACCESS_TOKEN_EXPIRE_MINUTES`. Esta batería cubre los 12 endpoints de autenticación, el JWT y su configuración. Por endpoint hay al menos un camino feliz, un caso límite y un modo de fallo.

Cada test afirma una **decisión de negocio** (quién puede hacer qué, qué se guarda y qué se rechaza) llamando directamente a la lógica: rutas, servicio, repositorio, seguridad y dependencias. No usa TestClient ni HTTP. Las bases TinyDB son temporales (`tmp_path`), el reloj es inyectado y el sender de email es falso. Una fixture comprueba que `data/*.json` no cambia en toda la sesión. Las fixtures están en [`tests/conftest.py`](tests/conftest.py).

## 2. Cómo ejecutar

Desde `services/api` (comprobado en Windows con PowerShell):

| Qué | Comando |
|---|---|
| Toda la suite (batería nueva + 312 tests `unittest` anteriores) | `uv run pytest` |
| Ídem con la cobertura de toda la app | `uv run pytest --cov` |
| Cobertura del módulo de auth con umbral | `uv run pytest --cov=app.auth --cov=app.routes.auth --cov=app.routes.users --cov=app.routes.profiles --cov-fail-under=70` |
| Ídem, informe a partir del último `--cov` | `uv run python -m coverage report --include="app/auth/*,app/routes/auth.py,app/routes/users.py,app/routes/profiles.py" --fail-under=70` |
| Solo la batería nueva | `uv run pytest tests/test_token.py tests/test_login.py tests/test_register.py tests/test_users.py tests/test_profiles.py tests/test_forgot_password.py tests/test_reset_password.py tests/test_change_password.py` |
| Suite anterior con `unittest` (`AGENTS.md` §4, desde la raíz) | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` |

- **`coverage.exe`:** el Control de aplicaciones de Windows (error 4551) puede bloquear los lanzadores `.exe` sin firmar de uv. Durante el desarrollo de esta batería llegó a bloquear `coverage.exe` (hoy arranca). `uv run python -m coverage …` funciona siempre y no depende del `.exe`.
- **No ejecutes `uv sync`:** sincroniza de forma exacta y desinstala `nexova-shared` y `nexova-incident-analyzer`, que se instalan con pip a propósito (ver [`README.md`](README.md#instalación-desde-la-raíz-del-monorepo)). `uv run` sí los conserva. pytest los encuentra igualmente (`pythonpath` en `pyproject.toml`), pero el comando `unittest` los necesita instalados. Si se perdieron, reinstálalos desde la raíz: `services\api\.venv\Scripts\python -m pip install --no-deps -e packages/shared -e packages/incident-analyzer`.

**Jest (lógica TypeScript de auth en `uis/backoffice`):** ver §10.
**Extras API-042 y FE-019:** *pendientes de F7 y F8 (opcionales).*

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
| No anular los enlaces pendientes (nuevo enlace / change-password) | `test_only_the_latest_link_is_pending…` / `test_change_sets_the_new_password…` y RP3 |
| No marcar `used_at` | RP1, `[ya usado]` y la concurrencia |
| Quitar el lock de `consume_reset_token` | `test_two_simultaneous_resets_with_the_same_link_succeed_exactly_once` (10 de 10) |
| Encolar el email también para desconocidos | `test_unknown_or_inactive_email_gets_the_same_answer…` |

## 5. Bugs encontrados y corregidos

| | Tope de minutos del token | Byte NUL en la contraseña |
|---|---|---|
| **Lo destapó** | Caso de la IA: un valor que la configuración acepta no puede romper cada login (primera versión del test de `test_token.py`) | Caso de la IA: ¿un NUL en la contraseña es un error de validación o un 500? |
| **Síntoma** | Con `ACCESS_TOKEN_EXPIRE_MINUTES = 10**10` la API arrancaba, pero cada login daba 500 (`OverflowError`) | 500 en el registro, el login (con email existente o desconocido), el reset, el cambio de contraseña (nueva y actual) y el `PUT /users/{id}` del admin |
| **Causa** | `Settings` solo rechazaba 0 y negativos; `iat + timedelta` se salía del rango de `datetime` | bcrypt rechaza el NUL (`PasswordValueError`) y ni `_check_password` ni `verify_password` lo tenían en cuenta |
| **Corrección** | Tope técnico de 525600 min (1 año) con `ConfigError` al arrancar. No es una política de sesión: la decide el CTO | El validador rechaza el NUL (422); `verify_password` devuelve `False` sin bcrypt (401 en el login, 400 como contraseña actual) |
| **Commit** | `65cfb36` | `988ff96` |
| **Tests** | `test_expiration_at_the_technical_cap…` y `…beyond_the_technical_cap…` | `test_new_password_with_nul_byte…`, `test_password_with_nul_byte…` (login) y `test_current_password_with_nul_byte…` |

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

## 8. Límites de la batería

- **`exp == ahora` exacto:** no se prueba porque python-jose usa su propio reloj. La frontera se acota con −5 s y +1 s.
- **Sin cubrir con la batería nueva sola** (los cubre la suite anterior):
  - el sender real de Resend (exige simular `urlopen`);
  - `create-admin` (CLI interactiva);
  - el cableado de FastAPI en `dependencies.py` (`get_settings` y similares). Los tests llaman a las funciones con las dependencias ya resueltas.

## 9. Resultados

Medidos el 2026-10-12 con los comandos de §2.

| Medida | Batería nueva sola | Suite completa |
|---|---|---|
| Tests | 143 | 455 (312 anteriores + 143) |
| Cobertura del módulo de auth (`app/auth/*` y `app/routes/{auth,users,profiles}.py`) | 86 % | 99 % |
| Cobertura de toda la app (`app/`) | — | 98 % |
| Tiempo aproximado | ~10 s | ~50 s (bcrypt real en la suite anterior) |

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

**Resultados** (medidos el 2026-10-12): 112 tests en ~1 s. Cobertura de líneas (Jest):

| Archivo | Líneas | Motivo de lo no cubierto |
|---|---|---|
| `lib/auth-routes.ts` | 100 % | — |
| `lib/auth-token.ts` | 100 % (87,5 % de ramas) | Las ramas sin `window` (guardar, borrar y suscribirse en el servidor) |
| `services/auth.service.ts` | 93,4 % | Un 422 sin JSON, los errores de configuración y de timeout, y los atajos exportados del servicio por defecto |
| `hooks/use-auth-session.ts` | 80,3 % | El hook de React (`useAuthSession`): necesita React y se valida en el navegador |
| `services/normalizers.ts` | 58,5 % | Lo no cubierto son normalizadores de incidentes y proveedores, no de auth (los cubre `node:test`) |
| **Total de los cinco archivos** | **80,2 %** | |
