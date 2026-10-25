# Inventario de equipos y materiales (Hito 5) — guía de revisión

> **Desde #infra-40 la plataforma se arranca con Docker** (ver [`local-development.md`](./local-development.md)); los pasos de arranque de esta guía son los de su fecha.

Documento para revisar el hito: cómo levantarlo, qué salida esperar, qué cubre cada test y qué **no** está verificado.

- Contexto de negocio (entidades, campos, reglas, datos semilla y notas de evaluación): [`context-nexova-gestion-inventario-hito-5.md`](./context-nexova-gestion-inventario-hito-5.md).
- Contrato HTTP, decisiones, equivalencia con los nombres del enunciado y esquema de tablas: [`services/api/SPECS.md`](../services/api/SPECS.md) Parte F (§34–§40).
- Instalación, Supabase y seed: [`services/api/README.md`](../services/api/README.md#inventario-hito-5).
- Tests y mutaciones: [`services/api/TESTING.md`](../services/api/TESTING.md) §13.
- Historial por fases (F1–F5) y validaciones ejecutadas: [`memory-bank/progress.md`](../memory-bank/progress.md).

> Las decisiones D1–D11 y las de F2–F4 las tomó **el usuario** al aprobar el plan y revisar cada fase (2026-10-17 y 2026-10-18). No las han revisado el tech lead ni la CTO.

## Qué se construyó

| Pieza | Dónde | Qué hace |
|---|---|---|
| Configuración | `services/api/app/core/config.py` | `DATABASE_URL` obligatoria (`repr=False`); desde el entorno, solo `postgresql://` y `postgresql+psycopg2://` |
| Conexión | `services/api/app/modules/inventory/database.py` | Motor por app (psycopg2 forzado, `NullPool`, `connect_timeout=5`); lifespan con `create_all` + RLS y `dispose()`; `get_db`, una sesión por petición |
| Modelos ORM | `models.py` (+ `vocabulary.py`) | `Asset`, `AssetEntry`, `AssetExit` (`table=True`) en `assets`, `asset_entries` y `asset_exits`; FK reales, `UNIQUE(sku)`, `CHECK` e índices |
| Schemas | `schemas.py` | Requests y responses Pydantic, sin importar los modelos ORM; `current_stock` solo en la respuesta |
| Lógica | `service.py` | Stock calculado en la misma consulta; salidas con `SELECT … FOR UPDATE`; `/orders` en dos consultas con JOIN |
| Rutas | `router.py` | `APIRouter(prefix="/inventory")` con las 6 rutas, registradas con JWT en `app/main.py` |
| Seed | `seed.py` → `uv run seed-inventory --email …` | Datos semilla del CONTEXT, idempotente, en una transacción |
| Errores | `app/core/errors.py` | 400 `insufficient_stock` / `office_mismatch`, 404 `asset_not_found`, 409 `sku_already_exists`, 503 `storage_unavailable` |

## Cómo revisar este hito (Windows PowerShell)

Todos los comandos se lanzan **desde la raíz del monorepo** salvo que se indique otra carpeta. Requisitos: Python ≥ 3.11 (verificado con 3.14.6), [uv](https://docs.astral.sh/uv/) y un proyecto de [Supabase](https://supabase.com/).

### 1. Instalar el venv de la API

```powershell
python -m venv services\api\.venv
services\api\.venv\Scripts\python -m pip install -e packages\shared -e packages\incident-analyzer -e "services\api[dev]"
```

Instala también `sqlmodel` y `psycopg2-binary`, que ya están en `pyproject.toml`. **No ejecutes `uv sync`**: desinstala `nexova-shared` y `nexova-incident-analyzer` (ver `services/api/README.md`).

### 2. Preparar `services/api/.env`

```powershell
cd services\api
Copy-Item .env.example .env   # solo la primera vez
```

En `.env`:

- **`JWT_SECRET_KEY`:** genérala con `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- **`DATABASE_URL`:** la URI del **Transaction pooler** de tu proyecto (panel de Supabase → **Connect** → Transaction pooler, puerto **6543**), con tu contraseña:

  ```text
  DATABASE_URL=postgresql://<usuario>:<contraseña>@<host-del-pooler>:6543/postgres
  ```

`.env` está en `.gitignore`. Para revisar sin tocar los datos de la demo, usa otro proyecto de Supabase.

### 3. Crear un usuario y arrancar la API

El seed y el recorrido necesitan un usuario en TinyDB (`services/api/data/auth.json`). Si no tienes uno, créalo con `create-admin`, que pide la contraseña sin mostrarla:

```powershell
uv run --env-file .env create-admin --email revisor@example.com --name "Revisor"
uv run --env-file .env uvicorn app.main:create_app --factory --port 8000 --workers 1
```

Al arrancar, la API crea las tablas que falten y activa RLS: `Application startup complete.`

- **Sin `DATABASE_URL`:** no arranca y termina en `app.core.config.ConfigError: DATABASE_URL is required (see services/api/.env.example)`.
- **Con Supabase inalcanzable:** uvicorn sale con código 3 y la línea `InventoryStartupError: inventory database is unavailable at startup: OperationalError`, sin host, usuario ni contraseña.

### 4. Cargar los datos semilla

En otra terminal, desde `services\api`, dos veces:

```powershell
uv run --env-file .env seed-inventory --email revisor@example.com
uv run --env-file .env seed-inventory --email revisor@example.com
```

**Primera ejecución:**

```text
Órdenes a nombre del usuario <id del usuario>
Activos insertados: 6
Activos ya existentes (omitidos): 0
Entradas insertadas: 4
Salidas insertadas: 3
Stock por SKU:
  NXV-IT-001: 13
  NXV-IT-002: 0
  NXV-PER-001: 0
  NXV-PER-002: 7
  NXV-OFF-001: 15
  NXV-TRN-001: 0
```

**Segunda ejecución:**

- `Activos insertados: 0`, `Activos ya existentes (omitidos): 6`, `Entradas insertadas: 0` y `Salidas insertadas: 0`;
- `Activos que ya tenían órdenes (no se les añade ninguna): 3`;
- el mismo stock.

### 5. Recorrido manual en `/docs`

`http://localhost:8000/docs`. Los pasos 3 y 4 escriben en la base: hazlo en un proyecto de pruebas o acepta que la demo cambie.

1. **Authorize:** usuario (`username`) y contraseña del usuario del paso 3.
2. **`GET /inventory/products`** → 200, ids 1..6 con `current_stock` 13, 0, 0, 7, 15, 0 (el neto del seed). Cada activo lleva `office`.
3. **Una entrada.** `POST /inventory/orders/inbound` con `{"asset_id": 3, "quantity": 5, "supplier": "TechDistrib Valencia S.L.", "office": "Valencia"}` → 201, `type: "inbound"`, el activo embebido y tu `user_uuid`. `GET /inventory/products/3` → `current_stock: 5`.
4. **Una salida válida.** `POST /inventory/orders/outbound` con `{"asset_id": 5, "quantity": 2, "exit_type": "consumption", "assigned_to": null, "office": "Valencia"}` → 201. `GET /inventory/products/5` → `current_stock: 13`.
5. **Una salida mayor que el stock.** `POST /inventory/orders/outbound` con `{"asset_id": 1, "quantity": 20, "exit_type": "allocation", "assigned_to": "EMPLEADO-FICTICIO-01", "office": "Valencia"}` → **400**:

   ```json
   {"detail": "Insufficient stock for asset 'Portátil 14\" Business'. Available: 13, requested: 20.", "code": "insufficient_stock"}
   ```

   `GET /inventory/products/1` sigue en 13: no se ha escrito nada.
6. **Una `allocation` sin `assigned_to`.** `{"asset_id": 1, "quantity": 1, "exit_type": "allocation", "office": "Valencia"}` → **422** con `"loc": ["body", "assigned_to"]`.
7. **`GET /inventory/orders`** → 200: las 7 órdenes del seed más las de los pasos 3 y 4, de la más reciente a la más antigua, cada una con `type`, `asset` (`id`, `name`, `sku`), `created_at` en UTC y `user_uuid`.

Sin *Authorize*, las 6 rutas responden 401.

Cada ruta muestra en `/docs` sus respuestas de error con el schema `ErrorResponse` (`{detail, code}`) y ejemplos. En `POST /inventory/orders/outbound`, el 400 tiene dos: `office_mismatch` e `insufficient_stock`, este con el mensaje literal del CONTEXT (`SPECS.md` §38). Es solo documentación: el comportamiento no cambia.

### 6. Ver las tablas y el RLS en Supabase

- **Table Editor:** las tablas `assets`, `asset_entries` y `asset_exits` del esquema `public`, cada una marcada con **RLS enabled**.
- **Authentication → Policies:** las tres tablas aparecen sin políticas. Por eso la Data API pública (`anon`, `authenticated`) no puede leerlas ni escribirlas.
- **SQL Editor:** también se puede comprobar con esta consulta. Debe dar `true`/`false` en las tres:

  ```sql
  SELECT relname, relrowsecurity, relforcerowsecurity
  FROM pg_class
  WHERE relname IN ('assets', 'asset_entries', 'asset_exits');
  ```

### 7. Suites y totales

| Suite | Comando (desde la raíz) | Total |
|---|---|---|
| `services/api` (`unittest`, `AGENTS.md` §4) | `services\api\.venv\Scripts\python -m unittest discover -s services/api/tests -t services/api` | 409 OK (312 anteriores + 97 del inventario) |
| `services/api` (pytest, desde `services\api`) | `uv run --no-sync python -m pytest -q` | 612 OK (515 + 97) |
| `packages/shared` | `python -m unittest discover -s packages/shared/tests -t packages/shared` | 81 OK (sin cambios en el hito) |
| `packages/incident-analyzer` | `python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer` | 121 OK, 7 omitidos (sin cambios en el hito) |

Ningún test conecta con Supabase. Si el Control de aplicaciones de Windows bloquea `pytest.exe` (os error 4551), `python -m pytest` funciona igual.

## Trazabilidad: "Qué vamos a evaluar" → implementación → test

Fuente de los puntos: el enunciado del Hito 5 (resumido por el usuario el 2026-10-17; no está versionado) y las «Notas de Evaluación» del CONTEXT. Los tests se citan como `archivo` → `Clase.test` (todos en `services/api/tests/`).

| Punto | Implementación | Test |
|---|---|---|
| Dos conexiones presentes y usadas a propósito: TinyDB para la autenticación y Supabase (SQLModel) para el inventario | `app/auth/repository.py` (sin cambios) y `app/auth/dependencies.py` → `get_current_user`; `app/modules/inventory/database.py` | `test_inventory_orders.py` → `CommonOrderRulesTests.test_user_uuid_is_the_authenticated_user_id`; `test_inventory_seed.py` → `SeedRunTests.test_orders_are_registered_to_the_seed_user`; `test_inventory_products.py` → `AuthenticationTests.test_every_product_route_requires_a_token`. Contra Supabase, verificado a mano (F2–F4) |
| `DATABASE_URL` en `.env`, nunca en el código | `config.py` (`database_url`, `repr=False`, `require_database`); `.env.example` sin valor; `.gitignore` | `test_inventory_database.py` → `DatabaseUrlConfigTests` (los 6). Ningún secreto en el diff de la rama: comprobado en la verificación final (F5) |
| Una sola dependencia `get_db` por petición vía `Depends()`; ninguna sesión global | `database.py` → `get_db`; `router.py` (`SessionDep`) | `test_inventory_database.py` → `NoGlobalSessionTests.test_no_session_is_created_at_module_level`, `test_sessions_are_only_opened_inside_get_db`; `GetDbTests.test_each_request_gets_its_own_session_and_it_is_closed`, `test_session_is_closed_when_the_route_fails` |
| `SQLModel.metadata.create_all(engine)` al iniciar | `database.py` → `init_db` en `inventory_lifespan` | `test_inventory_database.py` → `LifespanTests.test_startup_creates_the_tables`, `SqliteConstraintTests.test_init_db_creates_the_three_tables_and_is_idempotent`; `test_inventory_startup.py` (arranque fallido) |
| Modelos `Asset`, `AssetEntry`, `AssetExit` con los campos del CONTEXT; FK reales; `user_uuid` sin FK; sin modelo de usuario | `models.py` | `test_inventory_database.py` → `SchemaTests` (DDL de PostgreSQL: FK, `UNIQUE`, `TIMESTAMPTZ`, sin ENUM, `CHECK`, sin tabla de usuarios), `SqliteConstraintTests.test_foreign_key_is_enforced` |
| Schemas en otro archivo y con otra forma; ningún endpoint devuelve un ORM | `schemas.py`; `response_model` en las 6 rutas | `test_inventory_products.py` → `NoOrmInResponsesTests.test_every_inventory_route_has_a_non_orm_response_model`, `test_schemas_are_plain_pydantic_and_do_not_import_the_orm`, `test_schemas_differ_structurally_from_the_tables` |
| `office` en los modelos y en las respuestas | `models.py`; `AssetRead`, `InboundOrderRead`, `OutboundOrderRead` | `test_inventory_products.py` → `ReadProductTests.test_list_is_ordered_by_id_and_includes_office`; `test_inventory_orders.py` → `CommonOrderRulesTests.test_inbound_response_shape`, `OrdersListTests.test_lists_entries_and_exits_with_type_asset_and_user` |
| `APIRouter(prefix="/inventory")` con las 6 rutas | `router.py`; `app/main.py` | `test_inventory_products.py` → `NoOrmInResponsesTests.test_every_inventory_route_has_a_non_orm_response_model` (las 6), `test_openapi_lists_the_inventory_routes` (incluido `/inventory/products/{id}`), `OpenApiErrorsTests` (los errores de cada ruta en OpenAPI) |
| `current_stock` = entradas − salidas, calculado y nunca almacenado; nace en 0 | `service.py` → `_assets_with_stock` | `test_inventory_products.py` → `CurrentStockTests.test_current_stock_is_entries_minus_exits`, `test_stock_is_never_stored`, `CreateProductTests.test_creates_an_asset_with_zero_stock`; `test_inventory_orders.py` → `EvaluatorCasesTests.test_current_stock_is_the_net_of_several_orders_through_the_api` |
| Ninguna ruta permite modificar el stock directamente | Sin ruta de stock; `extra="forbid"` | `test_inventory_products.py` → `CreateProductTests.test_invalid_bodies_are_422` (`current_stock in the body`); `test_inventory_orders.py` → `CommonOrderRulesTests.test_other_invalid_bodies_are_422` |
| **Evaluador:** una salida mayor que el stock → 400 con el mensaje literal, antes de escribir | `service.add_outbound_order`; `InsufficientStockError` | `test_inventory_orders.py` → `EvaluatorCasesTests.test_exit_above_stock_is_400_with_the_literal_message_and_writes_nothing`, `test_message_uses_the_asset_name_as_stored`; `OutboundRulesTests.test_exit_equal_to_stock_is_accepted_and_leaves_zero` |
| **Evaluador:** `allocation` sin `assigned_to` → error de validación; `consumption` con valor → error | `OutboundOrderCreate._assigned_to_matches_exit_type`; `CHECK` en la base | `test_inventory_orders.py` → `EvaluatorCasesTests.test_allocation_without_assigned_to_is_422_on_that_field`, `OutboundRulesTests.test_consumption_with_assigned_to_is_422_on_that_field`; `test_inventory_database.py` → `SqliteConstraintTests.test_assigned_to_matches_exit_type` |
| Cada orden guarda el `user_uuid` del usuario autenticado | `router.py` (`CurrentUserDep`) → `service.add_*_order` | `test_inventory_orders.py` → `CommonOrderRulesTests.test_user_uuid_is_the_authenticated_user_id`, `test_user_uuid_in_the_body_is_rejected` |
| Sin N+1: los datos relacionados en la misma consulta | `service.list_assets` (subconsultas agregadas + LEFT JOIN); `service.list_orders` (dos consultas con JOIN) | `test_inventory_products.py` → `QueryCountTests.test_list_uses_the_same_single_query_for_1_and_20_assets`, `test_get_by_id_is_a_single_query`; `test_inventory_orders.py` → `OrdersListTests.test_same_number_of_queries_with_1_and_20_orders` |
| **Evaluador:** datos semilla del CONTEXT y `GET /inventory/products` con su neto | `seed.py` (`SEED_ASSETS`, `SEED_ENTRIES`, `SEED_EXITS`) | `test_inventory_seed.py` → `SeedRunTests.test_products_reflect_the_seeded_net_stock`, `test_first_run_inserts_everything_and_second_run_inserts_nothing`, `test_orders_are_registered_to_the_seed_user`. Contra Supabase, verificado a mano (F4): 13/0/0/7/15/0 |
| La base caída no filtra datos ni rompe la API | `errors.py` (503); `database.py` (`InventoryStartupError`) | `test_inventory_database.py` → `DatabaseUnavailableTests`; `test_inventory_startup.py` (los 3); `test_inventory_seed.py` → `SeedErrorTests.test_unreachable_database_is_2_without_connection_details`, `SeedCommandTests.test_command_with_the_database_down_exits_2_and_leaks_nothing` |
| Concurrencia: dos salidas simultáneas no dejan el stock en negativo | `service.locked_asset_query` (`FOR UPDATE`) | `test_inventory_orders.py` → `StockLockTests` (los 3). Contra Supabase, verificado a mano (F3b): dos salidas de 5 sobre un stock de 5 → una 201 y una 400 |

## Verificado por el usuario: recorrido en `/docs` (2026-10-18)

**El usuario hizo el recorrido en Swagger contra Supabase**, con la API arrancada con su `.env` y un **login real**: *Authorize* con su cuenta, así que el token llevaba su `user_uuid` (`45e456e9-…`).

| Paso | Resultado |
|---|---|
| `GET /inventory/products` | 200, ids 1–6 con stock 13/0/0/7/15/0 (el neto del seed) |
| Salida de 20 de `asset_id` 1 | 400 `insufficient_stock` con `Available: 13, requested: 20.` |
| `allocation` sin `assigned_to` | 422 con `loc` `["body", "assigned_to"]` |
| `GET /inventory/orders` | 200, las 7 órdenes del seed con su `user_uuid` |
| `/docs` tras reiniciar la API | los errores de las rutas aparecen documentados (400/404/401) |

No hizo los pasos 3 y 4 del recorrido (una entrada y una salida válidas): no se registró ninguna orden válida, así que **el neto del seed sigue intacto**.

## Lo que no está verificado

- **Entrada y salida válidas desde `/docs`.** Los pasos 3 y 4 del recorrido no se hicieron a mano (ver la sección anterior). Están cubiertos por los tests y, contra Supabase, por los scripts HTTP de F3b y por el seed de F4.
- **RLS desde la Data API.** Se comprobó `relrowsecurity = true` y 0 políticas en las tres tablas, pero no una petición real a la Data API con la clave `anon`.
- **`CHECK`, FK y `UNIQUE` en PostgreSQL.** En los tests se aplican en SQLite y se comprueban en el DDL compilado para PostgreSQL. En Supabase no se ha intentado insertar a mano una fila inválida.
- **Concurrencia.** Una sola prueba real (dos hilos), con un único worker de uvicorn. Sin pruebas de carga ni con varios procesos.
- **Rendimiento del `NullPool`.** Cada petición abre una conexión TLS con el pooler. No se ha medido la latencia.
- **Plataforma.** Solo en Windows con Python 3.14.6 y psycopg2-binary 2.9.13.
- **Sin interfaz.** El hito no incluye frontend: un futuro panel de `uis/backoffice` consumiría `GET /inventory/orders` (nombre, cantidad, tipo, fecha y `user_uuid`).
- **Revisión de decisiones.** D1–D11 y las de F2–F4 son decisiones del usuario; no las han revisado el tech lead ni la CTO.
