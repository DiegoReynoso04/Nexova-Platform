# AUTH-01 — Autenticación y protección de rutas (`services/api`)

> **Desde #infra-40 la plataforma se arranca con Docker** (ver [`local-development.md`](./local-development.md)); los pasos de arranque de esta guía son los de su fecha.

Documento de contexto y guía de uso de la autenticación de la API de Nexova. El contrato HTTP completo y las decisiones de implementación (D-AUTH-1…13) están en [`services/api/SPECS.md`](../services/api/SPECS.md) Parte C; aquí no se duplican.

## 1. Contexto (ticket AUTH-01)

La API crece (analizador de incidentes, directorio de proveedores) y hasta ahora cualquiera que conociera una URL podía llamarla. Antes de la siguiente fase de la plataforma, la CTO fijó el criterio: **ninguna ruta que modifique o exponga datos sensibles puede ser accesible sin una sesión válida**. El tech lead lo convirtió en el ticket AUTH-01:

- Módulo `users` con CRUD completo solo de credenciales (email y contraseña).
- Módulo `profiles` uno a uno con cada usuario: el nombre visible y los datos de contacto viven en `Profile`, no en `User`.
- `POST /auth/login` que valida credenciales y devuelve un JWT firmado.
- Dependencia reutilizable `get_current_user` que decodifica el token e identifica al usuario.
- Esa dependencia aplicada a todas las rutas que no deben ser públicas.

Restricciones del ticket:

- `User` y `Profile` se guardan **solo en TinyDB**, ahora y después de añadir Supabase. No se crean tablas de usuarios ni perfiles en PostgreSQL/Supabase; las tablas de otros módulos guardarán solo el `id` de TinyDB como `user_uuid`.
- El JWT lleva el `id` del usuario en TinyDB y expira tras una ventana configurable.
- `OAuth2PasswordBearer` de FastAPI y `python-jose` para firmar el token.
- Contraseñas con `libpass[bcrypt]` (fork mantenido de passlib; `from passlib.hash import bcrypt`), nunca en texto plano.
- Rutas de autenticación bajo `/auth`, de usuarios bajo `/users` y de perfil bajo `/profiles`.
- 401 para peticiones no autenticadas y 403 cuando un usuario accede a un recurso que no le pertenece.

Consecuencia aceptada por el ticket: las pantallas del backoffice que llaman a rutas ahora protegidas (`/suppliers`, `/incidents`) dejan de funcionar hasta que el frontend envíe el token, en una fase posterior.

## 2. Variables de entorno

| Variable | Obligatoria | Uso |
|---|---|---|
| `JWT_SECRET_KEY` | **sí** | Clave de firma HS256, mínimo 32 caracteres. Solo en `.env` (ignorado por git), nunca en el código |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | **sí** | Minutos de validez del token (p. ej. `30`) |
| `AUTH_DB_PATH` | no | Archivo TinyDB de `User` y `Profile`. Por defecto `services/api/data/auth.json` (ignorado por git) |

Si falta `JWT_SECRET_KEY` (o es demasiado corta) o `ACCESS_TOKEN_EXPIRE_MINUTES`, **la API no arranca** y muestra un `ConfigError` que nombra la variable.

Preparar el `.env` (una vez, desde `services/api`):

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # pegar el resultado en JWT_SECRET_KEY
```

## 3. Arranque

```bash
cd services/api
uv run --env-file .env uvicorn app.main:create_app --factory --port 8000 --workers 1
```

La API no lee `.env` por sí sola (no se usa `python-dotenv`): es `uv run --env-file` quien carga las variables en el proceso.

## 4. Crear usuarios

**Registro público** (acepta `email`, `password`, `name`, `phone` y `address`; `name`, `phone` y `address` son opcionales y crean el `Profile` en la misma operación). El cliente **no** puede elegir el rol: el backend fija siempre `role=user` y enviar `role` responde 422:

```bash
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" \
  -d '{"email": "ana@example.com", "password": "<contraseña>", "name": "Ana", "phone": "+34 600 000 000"}'
```

**Primer administrador** — `POST /users` nunca crea admins, así que el primero se crea con un comando explícito (mismo patrón que `uv run seed`). La contraseña se pide de forma oculta, dos veces; no se pasa como argumento ni se imprime:

```bash
cd services/api
uv run --env-file .env create-admin --email admin@example.com --name "Administración"
```

Si el email ya existe, el comando lo indica y termina con código 1 sin modificar nada. Después, un admin puede cambiar el rol de cualquier usuario con `PUT /users/{id}` (`{"role": "manager"}`).

## 5. Login y JWT

`POST /auth/login` recibe un **formulario OAuth2** (`application/x-www-form-urlencoded`), no JSON. El campo `username` es el email:

```bash
curl -X POST http://localhost:8000/auth/login -d "username=ana@example.com" -d "password=<contraseña>"
# {"access_token": "<jwt>", "token_type": "bearer", "expires_in": 1800}
```

El token lleva `sub` (el `id` UUID del usuario en TinyDB), `iat` y `exp`. Se envía en cada petición protegida:

```bash
curl http://localhost:8000/auth/me -H "Authorization: Bearer <jwt>"
```

## 6. Uso desde `/docs`

1. Abrir `http://localhost:8000/docs`.
2. `POST /users` → *Try it out* → registrar un usuario.
3. Botón **Authorize** (arriba a la derecha): `username` = email, `password` = contraseña → *Authorize*. Swagger hace el login contra `POST /auth/login` y guarda el token.
4. Las rutas con candado (`/suppliers`, `/api/incidents/*`, `/users/{id}`, `/auth/me`, `/profiles/me`…) ya se pueden llamar: Swagger añade `Authorization: Bearer <token>`.
5. *Logout* en el mismo diálogo para comprobar que las rutas protegidas devuelven 401.

## 7. Rutas protegidas y públicas

- **Públicas:** `GET /health`, `/docs` (y `/openapi.json`, `/redoc`), `POST /auth/login`, `POST /users`.
- **Protegidas (cualquier usuario con token válido):** las 8 rutas existentes — `POST /suppliers`, `GET /suppliers`, `GET /suppliers/{id}`, `PATCH /suppliers/{id}/rate`, `PATCH /suppliers/{id}/status`, `DELETE /suppliers/{id}`, `POST /api/incidents/analyze`, `GET /api/incidents/results/export` — más `GET /auth/me`, `GET`/`PUT /profiles/me`.
- **Protegidas con permiso:** `GET /users` solo admin; `GET`/`PUT`/`DELETE /users/{id}` el propio usuario o un admin; cambiar `role` solo un admin.

Matriz completa en `SPECS.md` §21.

## 8. 401 frente a 403

| Respuesta | Significa | Ejemplos |
|---|---|---|
| **401** `not_authenticated` (+ `WWW-Authenticate: Bearer`) | No hay una sesión válida | sin cabecera `Authorization`, token mal formado, firmado con otra clave, expirado, de un usuario borrado |
| **401** `invalid_credentials` | Login fallido | email inexistente o contraseña incorrecta (mismo mensaje en ambos casos) |
| **403** `forbidden` | Sesión válida, pero sin permiso | un `user` pide `GET /users`, lee/modifica/borra a otro usuario o intenta cambiar su propio `role` |

## 9. Dónde viven `User` y `Profile`

Solo en TinyDB, en `AUTH_DB_PATH` (por defecto `services/api/data/auth.json`), tablas `users` y `profiles`, separado de `suppliers.json`. La carpeta `data/` está en `.gitignore`. En `users` solo hay hashes bcrypt (`$2b$12$…`), nunca contraseñas.

No existe, ni debe crearse, ninguna tabla de usuarios o perfiles en PostgreSQL/Supabase. Cuando se introduzcan, sus tablas referenciarán al usuario únicamente con una columna `user_uuid` que contenga el `id` de TinyDB.
