# Reporte técnico de telemetría: análisis (F0)

Documento de trabajo del ticket «Telemetría · Reporte técnico». **F0: análisis y decisiones; no hay código.**

> **Decidido por el usuario el 2026-11-05:**
>
> - **D1–D14:** como se recomienda abajo. En D2 acepta también `python-dateutil` y `tzdata`, además de numpy.
> - **`events_per_day` rellena los días vacíos con 0**, sin loops: reindexado sobre `pd.date_range` del periodo (días UTC, fin exclusivo) × los `service` del vocabulario, con `fill_value=0`. La pregunta de la métrica es «un día a 0 es un colector caído», y un `groupby` sobre filas existentes no devuelve esos días. Qué devuelve un periodo sin ninguna fila se justifica en `report-review.md`.
> - **Fórmula visible:** cada función de `analysis.py` marca sus 6 pasos con un comentario, en orden, aunque alguno sea trivial. El test de AST comprueba además que `pd.to_datetime(..., utc=True)` va antes de cualquier `groupby`.
> - **D11:** sin redondeo en la API; la PR explica por qué las tasas salen con todos sus decimales.
> - **Verificación:** el stack contra el efímero lo monta el usuario con comandos de PowerShell; en la demo genera él los eventos reales. Commits por paso; sin push ni PR hasta su OK.
>
> Lo demás sigue tal como se presentó.

- **Rama:** `feature/telemetry-report`, desde `main` en `fed0e39` (PR #30 mergeada; `origin/main` en el mismo commit).
- **Contrato:** [`telemetry-plan.md`](./telemetry-plan.md) y [`event-schemas.json`](./event-schemas.json), versión `1.0.0`. Almacenamiento: [`storage-analysis.md`](./storage-analysis.md), [`storage-review.md`](./storage-review.md) y `services/api/SPECS.md` Parte H. Caché: SPECS Parte G.
- **Enunciado del ticket:** no se versiona; aquí solo se cita lo que choca con el plan o con el código.
- **Cómo leerlo:** **Verificado** es lo comprobado en el código o ejecutado. **Propuesta** es diseño nuestro, pendiente de decisión.

**Qué se ejecutó en F0, además de leer:**

- **Una consulta de solo lectura en la demo** (§1.7), la autorizada: recuento por `event_type` y `service`.
- **Una resolución de dependencias en una copia temporal**, fuera del repo: `uv lock` y `uv export`, sin instalar nada. `uv.lock`, `requirements.txt` y el venv no han cambiado.
- **Sondas con el venv de `services/api`:** SQLite en memoria y una app FastAPI de prueba.
- **Lectura del código de Pandas 3.1.1** en GitHub, sin descargarlo como paquete.

**Pandas no se ha ejecutado en F0.** Lo que aquí se dice de Pandas viene de leer su código, y lo marca como tal. La primera prueba de F1 lo confirma.

---

## 1. Estado verificado

### 1.1 Tabla y modelo

| Pieza | Estado | Dónde |
|---|---|---|
| `TelemetryEventRecord` | 8 columnas: `event_id` (PK), `event_type`, `timestamp`, `service`, `user_id`, `session_id`, `schema_version`, `tags` | `app/modules/telemetry/models.py:47-61` |
| `tags` | `JSON().with_variant(JSONB(), "postgresql")`: JSONB en PostgreSQL, JSON en SQLite | `models.py:61` |
| `timestamp` | `DateTime(timezone=True)`, indexado | `models.py:56` |
| Índices | `event_type`, `timestamp`, GIN en `tags` y la PK. El filtro de rango y el `IN` usan índice | SPECS §47 |
| Inmutable | `REVOKE UPDATE, DELETE, TRUNCATE`: el reporte solo necesita `SELECT` | SPECS §47 |
| Retención | 90 días; fecha límite 2027-02-03, sin automatizar | `telemetry-plan.md:2418` |

### 1.2 Motor y sesión

| Pieza | Estado | Dónde |
|---|---|---|
| Motor | Uno por app en `app.state.inventory_engine`. PostgreSQL con psycopg2 y `NullPool`; SQLite con `StaticPool` en los tests | `modules/inventory/database.py:58-89`, `main.py:67` |
| Sesión | `get_db`: una `Session` por petición, perezosa: no abre conexión hasta la primera consulta | `database.py:146-151` |
| Coste de conectar | ~400 ms por petición contra Supabase: `NullPool` abre una conexión nueva al pooler | `docs/caching-analysis.md:13` |
| Consecuencia | Si el cálculo va dentro del `compute` de la caché, **un acierto no abre conexión**. Las métricas comparten una conexión: `session.connection()` | Propuesta |

### 1.3 Caché

| Pieza | Estado | Dónde |
|---|---|---|
| `ResponseCache.get_or_set(namespace, key, ttl, compute)` | Si `compute` lanza, no guarda: un 503 no se cachea | `core/cache.py:56-78` |
| Reloj | Inyectable; caduca con `clock() >= expires_at` | `cache.py:47`, `:98` |
| Espacios | `inventory` e `incidents` hoy; 64 entradas por espacio, sale la más antigua | `cache.py:35`, `:76-77` |
| Instancia | Una por app, `app.state.response_cache`. `CacheDep` para inyectarla | `main.py:77`, `cache.py:110` |
| Un solo proceso | Solo es coherente con `--workers 1` | SPECS §43 |
| Claves compartidas | Solo respuestas iguales para todo usuario autenticado, consultadas después de `get_current_user` | SPECS §42 |

### 1.4 Autenticación de las rutas

- `main.py:87`: `authenticated = [Depends(get_current_user)]`, aplicado al registrar los routers de incidentes, proveedores e inventario (`:88-94`).
- `main.py:102`: `app.include_router(telemetry_router)`, **sin** esa dependencia: el colector es público a propósito, porque un beacon no lleva token (SPECS §45).
- `router.py:25`: `APIRouter(prefix="/telemetry", tags=["telemetry"])`. Como el router es público, la protección del reporte tiene que ir en la propia ruta (C9).
- `auth/dependencies.py:71`: existe `require_admin`, sin uso en las rutas de datos.

### 1.5 `tests/test_architecture.py`

| Regla | Línea | ¿Afecta a Pandas? |
|---|---|---|
| `FORBIDDEN_NAMES` incluye `round`, `quantize` y `print` | `:30` | **Sí, si el código está en `app/`** |
| Cómo lo detecta | `:93-98` | Recorre el AST. Mira `ast.Name` (`node.id`) **y** `ast.Attribute` (`node.attr`) |
| Alcance | `:86` | Solo `APP_DIR` (`services/api/app`, `support.py:27`). `services/telemetry/` queda fuera |
| `FORBIDDEN_IMPORTS`: `csv`, `re`, `statistics`, `fractions` | `:29`, `:88-92` | No: Pandas los usa por dentro, pero el test solo mira nuestros `import` |
| Literales `CORE_LITERALS` y `MANAGER_LITERALS` | `:68-83` | No: 0 coincidencias con los literales previstos (ejecutado) |
| Ningún literal con `\d` | `:76` | No: `"%Y-%m-%d"` lleva `%d` |
| La palabra `logging` en el código fuente | `:112-120` | Solo en `app/`: el reporte no registra nada propio |

**Ejecutado contra el mismo criterio (AST):**

| Expresión | Resultado |
|---|---|
| `df["x"].round(2)`, `df.round(4)`, `np.round(x)`, `df["t"].dt.round("D")`, `round(x, 2)` | **Prohibidas**: las cuatro primeras por `ast.Attribute`; la última por `ast.Name` |
| `.dt.floor("D")`, `.dt.strftime(...)`, `.groupby(...).agg(...)`, `.reset_index()`, `.to_dict(...)` | Pasan |
| `np.around(x)`, `df.agg("round")` | Pasan, pero son saltarse la regla: no se usan |

Por tanto, **`Series.round` choca** dentro de `app/`. Los métodos que pide el enunciado, no.

### 1.6 Cómo llegan los valores

**SQLite (tests), ejecutado con la tabla real:**

| Consulta | `timestamp` | `tags` | `event_id` |
|---|---|---|---|
| `select(tabla.c…)` tipada | `datetime` **sin zona** (`2026-11-05 10:00:00.123`) | `dict` | `UUID` |
| `text("select …")` | **`str`** | **`str`** con el JSON | `str` |

| Filtro en SQLite | Filas |
|---|---|
| `timestamp >= t` con `t` igual al evento (inicio inclusivo) | 1 |
| `timestamp < t` con `t` igual al evento (fin exclusivo) | 0 |
| El mismo instante escrito en `+01:00` | **0**: SQLite compara el texto sin la zona |

**PostgreSQL con psycopg2 (documentado por el driver, sin ejecutar):** un `TIMESTAMPTZ` llega como `datetime` con zona, con el desplazamiento de la sesión, y un `JSONB` llega como `dict`. No se comprobó en la demo porque la consulta autorizada es solo el recuento; se confirma en el efímero (§6, paso 2).

**Consecuencias para F1:**

1. La carga usa un `select` tipado, nunca `text()`: con `text()`, los tests irían por otro camino que producción.
2. `start` y `end` se normalizan a UTC antes de llegar al SQL: en SQLite, otra zona falla sin dar error.
3. `pd.to_datetime(..., utc=True)` iguala los dos casos: naive en SQLite (lo trata como UTC, que es como se guardó) y con zona en PostgreSQL. El colector solo guarda UTC (`collector.py:24`, `:231`).

**Pandas 3.1.1 (leyendo su código):**

- `pandasSQL_builder` solo acepta un `sqlalchemy.engine.Connectable` (`pandas/io/sql.py:957`). **Ejecutado con SQLAlchemy 2.1.5:** `Connection` y `Engine` lo son; `Session`, **no**. Hay que pasar `session.connection()`.
- Con un `Select` usa `self.con.execute` (`sql.py:1727-1730`): se conservan los tipos de SQLAlchemy.
- Sus extras piden `SQLAlchemy>=2.0.42`; el repo tiene 2.1.5. Nunca se ha ejecutado esa combinación aquí.
- `to_dict(orient="records")` pasa los valores por `maybe_box_native` (`to_dict.py:236-257`): `int` y `float` de Python.

### 1.7 Datos reales de la demo

Consulta del 2026-11-05, en una transacción `READ ONLY`, desde el contenedor `api` (host de Supabase comprobado, sin imprimir la URL):

| `event_type` | `service` | Filas |
|---|---|---|
| `page_viewed` | `backoffice` | 8 |
| `form_submitted` | `backoffice` | 4 |
| `form_started` | `backoffice` | 3 |
| `page_load_recorded` | `backoffice` | 2 |
| `direct_stock_edit_rejected` | `api` | 1 |
| `inbound_order_created` | `backoffice` | 1 |
| `outbound_order_created` | `backoffice` | 1 |
| `stock_threshold_triggered` | `backoffice` | 1 |
| **Total** | | **21** |

**Solo 8 de los 15 tipos tienen filas.** Sin ninguna: `client_request_failed`, `frontend_error_captured`, `page_not_found_viewed`, `form_validation_failed`, `form_abandoned`, `user_logged_out` y `kit_cost_variance_detected`.

**Los `tags` no se han leído:** la autorización cubre el recuento. Lo que se sabe de ellos viene de `storage-review.md:129-131`: un login fallido (`api_rejected`) y uno correcto. Las otras dos filas de `form_submitted` serían la Entrada y la Salida, pero **eso es una inferencia**. Hay una consulta propuesta en §7.

### 1.8 Dependencia y Docker

| Pieza | Estado |
|---|---|
| Pandas hoy | Ni en el venv ni en la imagen, ni numpy |
| Resolución en la copia temporal | `pandas 3.1.1`, `numpy 2.5.4` (y `2.4.6` para Python < 3.12), `python-dateutil 4.0.0`, `tzdata 2026.6` |
| Efecto en el lock | 41 → 46 paquetes; solo «Added», ninguna versión existente cambia |
| Wheels `manylinux` cp314 | pandas 11,5 MiB, numpy 15,9 MiB; dateutil y tzdata suman 0,4 MiB |
| Imagen actual | `nexova-api:dev`, 337 MB |
| `test_requirements_lock.py` con los archivos regenerados | **6 tests OK** en la copia temporal (C2) |

---

## 2. Conflictos

### C1. Ruta de `analysis.py`

- **Enunciado:** «services/telemetry/analysis.py», y se evalúa con esa ruta literal.
- **`services/Dockerfile:50`:** `COPY api/app ./app`.
- **`services/Dockerfile:35`:** `PYTHONPATH=/packages/shared:/packages/incident-analyzer`.
- **`services/README.md:5`:** «Each subfolder inside `services/` must correspond to **one specific service**».
- **`.agents/rules/monorepo-structure.md:38`:** «Cada app/servicio/agente nuevo lleva su propia subcarpeta con README».

**Hechos:**

- El contexto de build es `./services` (`docker-compose.yml:15`): **`services/telemetry/` ya entra en el contexto**. Solo falta copiarla.
- `WORKDIR` es `/app/api` y uvicorn añade el directorio de trabajo al `sys.path`: por eso se encuentra `app`. Una carpeta copiada a `/app/api/telemetry` se importa sin tocar `PYTHONPATH`.
- `services/.dockerignore` no excluye `telemetry/`, y sí `**/tests` y `**/__pycache__`.
- `--reload-dir /app/api` (`docker-compose.yml:34-35`) ya vigila esa ruta. Falta el bind mount.
- En el host, los tests necesitan `services/` en `sys.path`. El comando `unittest` de `AGENTS.md` no aplica el `pythonpath` de `pyproject.toml`.
- `services/api/tests/__init__.py` se importa antes que cualquier test, con `unittest` y con `pytest`.
- `app/modules/telemetry/__init__.py` solo tiene un docstring: `analysis.py` puede importar el modelo sin ciclo.

**Encaje con la regla:** `services/telemetry/` no es un servicio desplegable, sino una librería de la API. Lleva README y una fila en `services/README.md` (y en `README.es.md`) que lo diga. Ver D1.

### C2. Pandas: dependencia nueva

**Autorizada por el ticket, y solo Pandas.** Pero no entra solo numpy:

| Paquete | Por qué entra |
|---|---|
| `numpy` | Dependencia de Pandas. **Dos versiones en el lock:** 2.5.4 (Python ≥ 3.12) y 2.4.6 (< 3.12), porque `requires-python` es `>=3.11` |
| `python-dateutil` | Dependencia de Pandas |
| `tzdata` | Dependencia de `python-dateutil` 4.0 |

`six` ya estaba. **Tu autorización dice «numpy entra como transitiva»: `python-dateutil` y `tzdata` también, y conviene que lo sepas.**

**Dónde se declara:** en `services/api/pyproject.toml`, porque `requirements.txt` sale de ahí y `services/Dockerfile:44` dice que los paquetes del monorepo «no declaran ninguna».

**Cómo se añade:**

1. Editar `pyproject.toml` a mano: `"pandas>=3.1,<3.2"`, con su comentario de autorización. **No `uv add` sin `--no-sync`, ni `uv sync`:** `AGENTS.md` lo prohíbe porque desinstaló los paquetes del monorepo.
2. `uv lock`.
3. `uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt`.
4. Venv: `uv pip install --python .venv/Scripts/python.exe --require-hashes -r requirements.txt`, que añade sin quitar nada.
5. Imagen: `docker compose up -d --build`.

**`test_requirements_lock.py`:** pasa, pero por casualidad en un punto. `read_requirements` y `read_lock` son diccionarios por nombre, así que de las dos `numpy` solo queda la última de cada archivo, 2.5.4 en ambos. **La línea de 2.4.6 no se compara.** Es inofensivo: esa versión nunca se instala en la imagen (Python 3.14). El test no necesita cambios.

**Imagen:** son 27,4 MiB de wheels comprimidos sobre 337 MB. El tamaño instalado es varias veces eso, **sin medir**: se mide en F1. El comentario de `services/Dockerfile:13` («las 28 dependencias») pasa a 33 líneas.

**Pandas 3, no 2:** es la versión que resuelve `uv` hoy, con wheels para cp314. Una diferencia que hay que tener presente: las cadenas son de tipo `str` por defecto. `pyarrow` no hace falta y no se añade.

**Riesgo en Windows:** el Control de aplicaciones ya bloqueó una DLL de SQLAlchemy en el venv (`TESTING.md:292`). Las `.pyd` de numpy y Pandas pueden sufrir lo mismo. Hay salida: el contenedor efímero de `TESTING.md` §14, que usa la imagen y por tanto necesita reconstruirla antes.

### C3. Latencia

- **Enunciado:** métricas de «latencia».
- **Plan (`:281`):** `api_latency_recorded`, emisor API, prerrequisito P6: **no se emite**.
- **Allowlist:** no está entre los 15 (`allowlists.py:8-9`).

| Candidata | ¿Mide latencia? |
|---|---|
| `page_load_recorded.duration_ms` | **Sí.** «Del montaje al primer estado final» (`plan:1827`), por `route_template`. Solo 4 rutas: `/suppliers`, `/incident-manager`, `/inventory/products`, `/inventory/orders` (`allowlists.py:183`) |
| `form_submitted.duration_ms` | **No.** «Tiempo desde `form_started`» (`plan:1455`): incluye lo que tarda la persona en escribir |
| `form_abandoned.duration_ms` | **No**, por lo mismo |

**La métrica mide la espera del operador en el navegador, no el tiempo de la API.** Hay que decirlo en la PR. Con `outcome = error` el tiempo es el de un fallo, y mezclarlo falsea la media: `outcome` va como dimensión de agrupamiento.

**Tampoco hay p95:** el enunciado permite «solo groupby/agg/count/sum/mean». Se usan `count`, `mean` y `max` dentro de `agg`.

### C4. Qué es un error y cuál es el denominador

- **Enunciado:** clave `error_rate_by_type`, sin definir «error».
- **Plan:** `server_error_returned` no se emite (`:277`). **La API no cuenta sus 500.**

**No existe el denominador natural.** Lo correcto sería errores / peticiones, pero las peticiones correctas no se emiten: sin `api_latency_recorded`, el sistema solo ve los fallos. Cualquier denominador es un sustituto.

**Candidatos a error, con los enums reales:**

| Evento | Filtro en `tags` | Qué significa | Clase propuesta |
|---|---|---|---|
| `client_request_failed` | — | La API no respondió (`kind`: `network`, `timeout`, `config`) | `system` |
| `frontend_error_captured` | — | Un límite de error capturó un fallo de render | `system` |
| `page_load_recorded` | `outcome = error` | Una página de datos terminó en error | `system` |
| `form_submitted` | `outcome` ∈ `network_error`, `server_error` | El envío falló por el sistema | `system` |
| `form_submitted` | `outcome` ∈ `api_rejected`, `validation_error`, `session_expired` | La API rechazó el envío: contraseña mala, 422, sesión caducada | `rejected` |
| `form_validation_failed` | — | El cliente bloqueó el envío: sin petición | `rejected` |
| `page_not_found_viewed` | — | 404 del backoffice | `rejected` |
| `direct_stock_edit_rejected` | — | La API rechazó un intento: 405 o 422 | `rejected` |

**El riesgo de una sola tasa:** una contraseña mal escrita y un fallo de la API sumarían igual. La tasa diría «errores» donde en realidad hay usuarios equivocándose. Por eso se propone `error_class`.

**Denominador:** ver D4. Ninguna opción da una tasa de peticiones, y la PR lo tiene que decir: es la proporción de eventos técnicos que son errores.

### C5. `auth_failure_rate`

- **Enunciado:** «fallidos / (fallidos + correctos), con event_type IN (...) en SQL». Los llama `user_login_failed` y `user_login_succeeded`.
- **JSON:** esos dos nombres no existen (0 coincidencias).
- **Plan (`:2390`):** «`user_login_succeeded` en el frontend | Duplicaría `user_logged_in`».
- **Plan (`:253-254`):** `user_logged_in` y `login_failed`, emisor API, prerrequisito P6: no se emiten.
- **Código (`lib/auth-telemetry.ts:3-5`):** «aquí el fallo del login queda en `form_submitted` con su `outcome`».

**Lo único que hay hoy:** `form_submitted` con `form = login`. Su `outcome` (`event-schemas.json:2419-2426`; `allowlists.py:145`):

| `outcome` | En el login significa | ¿Fallo? | ¿Intento? |
|---|---|---|---|
| `success` | Credenciales aceptadas | No | **Sí** |
| `api_rejected` | 401 `invalid_credentials`, u otro 4xx (`auth-telemetry.ts:19-24`, `auth.service.ts:213`, `:231`) | **Sí** | **Sí** |
| `validation_error` | 422 de la API: ni se compararon credenciales | No | No |
| `network_error` | Sin respuesta: `network`, `timeout`, `config` | No: es de sistema | No |
| `server_error` | 5xx o respuesta inesperada | No: es de sistema | No |
| `session_expired` | No debería darse: el login va con `skipAuth` (`auth.service.ts:270`) | No | No |

El filtro de SQL queda en `event_type = 'form_submitted'` y `form` y `outcome` se filtran en Pandas, como pide el enunciado para los `tags`. Es `=` y no `IN` porque solo hay un tipo: el enunciado admite los dos («= o IN»).

**Tres límites que hay que decir en la PR:**

- **Solo ve lo que pasa por el navegador.** Un ataque con `curl` a `/auth/login` no genera `form_submitted`. Esa detección es justo para lo que `login_failed` existe en el plan.
- **Se puede falsificar** por la ruta pública (riesgo aceptado, plan §8.4).
- **Se pierde si se pierde el evento:** un lote descartado (plan §8.4).

**El día que P6 emita `login_failed` y `user_logged_in`,** la métrica cambia de fuente; no se suman las dos o cada login contaría doble.

### C6. Negocio frente a técnico

- **Enunciado:** «Solo métricas técnicas»; «un reporte de negocio disfrazado no se acepta».
- **Plan (`:244-248`):** los 4 eventos de inventario del frontend son «obligatorio · inventario».

**Dónde está el límite:** un evento de negocio tiene dos partes:

- **Que existe como fila** es un hecho del pipeline: pesa, ocupa y cuenta en el volumen.
- **Lo que dice** (`office`, `product_id`, `quantity`, `currency`, `unit_cost`, `supplier_key`) es negocio.

Excluirlos de todo hace que `events_per_day` no cuadre con la tabla y esconde una caída del colector si esos días solo hubo órdenes. Meter sus `tags` sí sería un reporte de negocio. Ver D7.

**`direct_stock_edit_rejected`** es de categoría inventario, pero su hecho técnico es un 405 o 422 rechazado. Cuenta como error `rejected`, sin leer `office` ni `quantity`.

**`user_logged_out`** es técnico: entra en el denominador y en el volumen.

### C7. Caché y ventana por defecto

- **Enunciado:** «Caché en memoria con TTL de 60 s por combinación de start/end: dentro del TTL no se recalcula».
- **Hecho:** con los parámetros vacíos, `end = now`. Si la clave es el periodo resuelto, cambia en cada petición: **nunca acierta**.

La clave tiene que salir de lo que pidió el cliente, no del periodo resuelto: «combinación de start/end» es lo que llega en la URL. Ver D8.

**Reutilizar `ResponseCache`: sí.** Hace justo lo que pide el enunciado, con TTL, reloj inyectable y sin guardar errores. Una caché nueva duplicaría código y tests.

- **Espacio nuevo** `telemetry_report`; 60 s, constante en el router como `CACHE_TTL_SECONDS` en los demás.
- **Sin invalidación:** el colector no limpia nada. Un reporte con 60 s de retraso es lo que se pide, y limpiar en cada lote anularía la caché.
- **Cumple SPECS §42:** la respuesta es igual para todo usuario autenticado y sin datos personales.
- **Efecto:** en la ventana por defecto, `period` es el de la primera petición: hasta 60 s antiguo. Es coherente con los datos que acompaña.

### C8. Parámetros

**Ejecutado con FastAPI 0.141 y un parámetro `datetime | None`:**

| Entrada | Resultado |
|---|---|
| `2026-11-01` | 200: `2026-11-01T00:00:00`, naive |
| `2026-11-01T10:00:00` | 200, naive |
| `2026-11-01T10:00:00Z` y `…00.123Z` | 200, UTC |
| `2026-11-01T10:00:00%2B01:00` | 200, `+01:00` |
| `2026-11-01T10:00:00+01:00`, sin codificar | **422**: `+` en una URL es un espacio |
| `1730000000` | **200**: lo toma como epoch. No es ISO 8601 |
| `no-es-fecha`, `2026-13-45T00:00:00Z`, vacío | 422 |

Propuesta completa en D9. El `+` sin codificar es de HTTP: `/docs` lo codifica solo y la documentación recomienda `Z`.

**Un rango sin tope contradice «Nunca se carga la tabla entera»:** `start_date=2000-01-01` cargaría todas las filas. El enunciado no pide un tope, pero sin él esa frase no se cumple.

### C9. Autenticación del endpoint

- **Enunciado:** no lo dice.
- **Hecho:** el colector es público solo porque un beacon no puede llevar `Authorization` (SPECS §45). El reporte lo llama un `fetch`, sin esa limitación, y expone qué se usa, cuándo y qué falla.

Ver D10. **Efecto en el dashboard:** ninguno. `lib/api-client.ts` ya añade el Bearer y el 401 cierra la sesión.

### C10. Serialización y redondeo

| Valor | Problema | Propuesta |
|---|---|---|
| Fecha del grupo | `Timestamp` no es JSON | `dt.strftime("%Y-%m-%d")` antes del `groupby`: `day` ya es texto |
| `int64`, `float64` | numpy no es JSON | `to_dict(orient="records")` ya da tipos de Python (§1.6). Un test lo comprueba |
| `NaN` | Ver abajo | Evitarlo por construcción |
| `period` | | Lo formatea el router, no Pandas |

**`NaN`, ejecutado:**

| Ruta de prueba | Respuesta |
|---|---|
| Con `response_model` (`rate: float`) | **200 con `"rate": null`**: se transforma en silencio, y el contrato dice `float` |
| Sin `response_model` | **500** |

`test_serialization.py` exige `response_model`, así que el camino es el primero: **un `NaN` no rompería la ruta, sino que saldría un `null` falso**. No debería ocurrir: en las dos tasas se agrupa solo sobre filas existentes, así que el denominador nunca es 0. Sin filas, la función devuelve `[]`, no una tasa. Un test comprueba que ninguna respuesta lleva `null` en una métrica.

**Redondeo:** `Series.round` choca en `app/` (§1.5). En `services/telemetry/` el test no lo vería, pero sería saltarse la regla. Ver D11.

### C11. «Sin loops»

- **Enunciado:** «Sin loops: solo groupby/agg/count/sum/mean».

| Cuenta como loop | No cuenta |
|---|---|
| `for` y `while` | El dict literal `{"events_per_day": events_per_day(...), ...}` |
| Comprensiones sobre filas | Pasar `df["tags"].tolist()` al constructor de `DataFrame` |
| `iterrows`, `itertuples`, `apply` por fila | `.map(diccionario)`, `.isin(...)`, `.where(...)`, `.eq(...)` |

**Extraer `tags`:** `pd.DataFrame(df["tags"].tolist(), index=df.index).reindex(columns=[...])`. El `reindex` hace que un resultado vacío siga teniendo sus columnas: sin él, `dropna(subset=[…])` falla con la ventana vacía.

**Se hace cumplir con un test de AST** sobre `analysis.py`: ningún `For`, `While`, `ListComp`, `DictComp`, `SetComp` ni `GeneratorExp`, ni los atributos `iterrows`, `itertuples` o `apply`. En esa misma comprobación entra `FORBIDDEN_NAMES`, porque `test_architecture.py` no mira fuera de `app/`.

### C12. Datos de prueba

- **Hecho:** en la demo faltan casi todos los tipos de error (§1.7), y **lo que se escribe es permanente** (`REVOKE`).

| Evento | Cómo sale de forma real | ¿En la demo? |
|---|---|---|
| `page_not_found_viewed` | Con sesión, ir a una ruta inexistente | Sí: es verdadero e inocuo |
| `form_submitted` con `api_rejected` | Login con contraseña mala | Sí; ya hay uno |
| `client_request_failed` | DevTools → Network → Offline (C15) | Sí, con cuidado de tiempos |
| `form_validation_failed` | Enviar un formulario vacío | Sí |
| `frontend_error_captured` | Solo con un fallo de render: ruta temporal, como en la auditoría | **No**: solo en el efímero |
| `page_load_recorded` con `error` | Por sí solo no: API parada con `/inventory/products` | Solo en el efímero |

Ver D13.

### C13. Tests sobre SQLite

| Tema | Hecho | Propuesta |
|---|---|---|
| JSONB frente a JSON | Con `select` tipado, `dict` en los dos (§1.6) | Sin ramas por dialecto |
| `timestamp` | Naive en SQLite, con zona en PostgreSQL | `to_datetime(utc=True)`; y un test con los dos tipos |
| `tags` como `str` | Solo con `text()` | Prohibido `text()`, por revisión y porque los tests fallarían |
| `pd.read_sql` y la `Session` | `Session` no es `Connectable` | `pd.read_sql(stmt, session.connection())`, primera prueba de F1 |
| `StaticPool` | Una conexión compartida | Sin cambios: `session.connection()` la reutiliza |

**Cómo se prueba la fórmula** («SQL filtra; Pandas no recarga la ventana»):

- **El filtro va en SQL:** se escucha `before_cursor_execute` y se exige `timestamp >=`, `timestamp <` y el `event_type` en la sentencia; también compilada con el dialecto de PostgreSQL.
- **Límites:** una fila justo en `start` entra y una justo en `end`, no.
- **Pandas no filtra tiempo:** el test de AST prohíbe `now`, `Timedelta` y `between` en `analysis.py`: las funciones reciben el periodo.
- **Orden:** `to_datetime(..., utc=True)` antes del `groupby`, por AST sobre cada función.
- **Sin tabla entera:** con filas fuera de la ventana, la consulta devuelve solo las de dentro.
- **Lo propio de PostgreSQL** (`JSONB` a `dict`, `timestamptz`): en el efímero, porque ningún test conecta con Supabase.

### C14. Dashboard

- **Enunciado:** «página mínima en uis/backoffice (p. ej. /telemetry)», con «un gráfico o una tabla».
- **`package.json`:** solo `next`, `react` y `react-dom`. **`uis/backoffice/CLAUDE.md:182`:** «No añadir ninguna dependencia nueva sin autorización explícita». Los gráficos serían a mano; una tabla ya cumple.
- **`uis/backoffice/CLAUDE.md:7`:** «cinco piezas de negocio, y **solo estas cinco**». El reporte no es de negocio, pero hay que añadirlo a esa lista.
- **Capas (`CLAUDE.md:59`, `:188`):** página (Server Component) → vista `'use client'` → hook → `services/` → `lib/api-client.ts`; `unknown` solo en `services/normalizers.ts`.
- **Tests:** módulos puros con `node:test` (normalizador, servicio, reducer del hook), reglas en `production-source.test.mjs` y, si hay lógica de formato, Jest. Los componentes, con `tsc`, `lint`, `build`, `next typegen` y navegador.

**Choque de contrato (no estaba en la lista):** `/telemetry` no está en el enum de `route_template`, ni `/telemetry/report` en el de `api_route_template`.

- `pageRouteTemplate` devuelve `null` (`lib/telemetry.ts:237`) y `page-view-telemetry.ts:33` no emite nada.
- `reportTransportFailure` también se calla (`lib/telemetry.ts:306-307`).
- **Efecto:** la página no aparece en su propia telemetría, sin error.
- **Añadirlos** es un valor nuevo en un enum: versión `1.1.0` (`plan:363`), con cambios en el JSON, el plan, `allowlists.py`, `types/telemetry.ts` y todos los ejemplos.

Ver D14.

### C15. Parar la API no genera `client_request_failed` (no estaba en la lista)

- **Ticket:** «API parada → client_request_failed».
- **Código:** con Docker, el navegador habla con `/backend`, y es **Next** quien conecta con la API. Si no responde, `proxy-request.js:80-86` hace `res.statusCode = 500` y `res.end('Internal Server Error')`.
- **Consecuencia:** el navegador **recibe respuesta**: un 500. `api-client` no lanza `ApiNetworkError`, y los servicios lo tratan como `server_error` (p. ej. `suppliers.service.ts:166`). Sale `form_submitted` con `server_error`, pero **`client_request_failed`, no**.
- **Por qué el repo parecía decir otra cosa:** la prueba «API parada → No se pudo conectar» (`docs/error-handling-audit.md:448`) es del 2026-10-10, con `next start` y conexión directa, anterior a `/backend` (#infra-40).

**Esto es lectura de código, sin ejecutar:** parar la API es una acción que confirmas tú. Se comprueba en F1.

**Otro efecto:** si el evento se genera con la red caída, su lote también fallará. La cola envía a los 10 s, con reintentos a 1, 2 y 4 s, y después lo descarta (`capture-review.md:80-82`). **Hay que recuperar la red en unos 15 s** o se pierde.

**Y un efecto en el dato:** con Docker, una caída de la API se ve como `server_error`, no como `client_request_failed`. En el reporte seguirá apareciendo como `system`, pero en otra fila.

### C16. El stack se cae al cambiar el código (no estaba en la lista)

- **Hecho:** `./services/api/app` está montado sobre la imagen y uvicorn usa `--reload` (`docker-compose.yml:32`, `:41`). En cuanto `router.py` importe `telemetry.analysis`, la API recarga y falla: la imagen no tiene Pandas, ni `services/telemetry`.
- **Efecto:** el colector deja de responder y los eventos de esa ventana se pierden. Nada se daña.
- **Propuesta:** primero la dependencia, Docker y la reconstrucción; después el código (§6). Igual al revisar la PR: `docker compose up -d --build` antes de usarla.

### C17. Los eventos con throttle cuentan de menos (no estaba en la lista)

- **Plan (`:2345`):** «Los que se descartan se suman a `suppressed_count`».
- **Hecho:** `client_request_failed`, `frontend_error_captured` y `direct_stock_edit_rejected` emiten uno cada 60 s por clave. **Una fila puede representar decenas de fallos.** Un `count` diría que una caída de 5 minutos con 200 fallos son 5 errores.
- **Propuesta:** en `error_rate_by_type`, `occurrences = 1 + suppressed_count` y `sum`, no `count`, en el numerador y en el denominador. `events_per_day` sigue contando filas, porque mide lo guardado.

---

## 3. Propuesta de métricas

**Comunes a todas:**

- Firma: `metrica(connection, start, end) -> list[dict]`. Sin ventana propia, sin efectos secundarios y sin `user_id`, `session_id` ni `event_id` en el `select`.
- Pasos: cargar (`select` tipado, `pd.read_sql`) → refinar (extraer `tags`, `dropna`) → convertir (`to_datetime(utc=True)`, `to_numeric`) → agrupar → agregar → servir (`reset_index().to_dict(orient="records")`).
- `day` es el día **UTC**, en texto `YYYY-MM-DD`.
- Sin datos en la ventana: `[]`.
- Orden estable: `sort_values`, para que la respuesta sea reproducible.
- **Las cinco son independientes:** cada una hace su consulta.
- **Las cifras de los registros son de ejemplo:** muestran la forma, no un resultado.

### 3.1 Obligatorias

**`events_per_day`**

| | |
|---|---|
| Pregunta | ¿Está llegando telemetría cada día, y de quién? Un día a 0 es un colector caído |
| `event_type` (SQL) | Sin filtro: solo el rango. Carga `timestamp` y `service`; **no carga `tags`** |
| Campos de `tags` | Ninguno |
| Agrupamiento | `day`, `service` |
| Agregación | `count` |
| Registro | `{"day": "2026-11-05", "service": "backoffice", "events": 20}` |

**`error_rate_by_type`**

| | |
|---|---|
| Pregunta | ¿Qué falla, cuánto pesa, y es el sistema o el usuario? |
| `event_type` (SQL) | `IN` los 11 técnicos: los 15 menos los 4 de negocio del frontend |
| Campos de `tags` | `outcome`, `suppressed_count` |
| Agrupamiento | `day`, `error_type`, `error_class` |
| Agregación | `sum` de `occurrences`; `total_events` por día con `transform("sum")`; `error_rate = errors / total_events` |
| Registro | `{"day": "2026-11-05", "error_type": "form_submitted:api_rejected", "error_class": "rejected", "errors": 1, "total_events": 18, "error_rate": 0.0555…}` |

`error_type` es el `event_type`, con `:outcome` en los dos que lo necesitan (`form_submitted:server_error`, `page_load_recorded:error`).

**`page_load_latency_by_route`**

| | |
|---|---|
| Pregunta | ¿En qué sección esperan más los operadores a ver los datos? |
| `event_type` (SQL) | `= 'page_load_recorded'` |
| Campos de `tags` | `route_template`, `duration_ms`, `outcome` |
| Agrupamiento | `day`, `route_template`, `outcome` |
| Agregación | `agg(loads="count", avg_ms="mean", max_ms="max")` |
| Registro | `{"day": "2026-11-05", "route_template": "/inventory/products", "outcome": "data", "loads": 2, "avg_ms": 431.5, "max_ms": 520}` |

### 3.2 Adicional

**`dominant_event_types`** (cubre «tipos de evento dominantes», que el contexto del ticket nombra)

| | |
|---|---|
| Pregunta | ¿Qué tipos ocupan la tabla y el cupo del colector? |
| `event_type` (SQL) | Sin filtro. Carga `event_type` y `service`; **no carga `tags`** |
| Campos de `tags` | Ninguno |
| Agrupamiento | `event_type`, `service`, en todo el periodo |
| Agregación | `count`; `share = events / total` |
| Registro | `{"event_type": "page_viewed", "service": "backoffice", "events": 8, "share": 0.3809…}` |

### 3.3 Extra 1

**`auth_failure_rate`**

| | |
|---|---|
| Pregunta | ¿Cuántos logins fallan al día desde el backoffice? |
| `event_type` (SQL) | `= 'form_submitted'` |
| Campos de `tags` | `form`, `outcome` |
| Filtro en Pandas | `form == "login"`, `outcome` ∈ `success`, `api_rejected` |
| Agrupamiento | `day` |
| Agregación | `failed` y `succeeded` con `sum`, `attempts` con `count`; `failure_rate = failed / attempts` |
| Registro | `{"day": "2026-11-05", "failed": 1, "succeeded": 1, "attempts": 2, "failure_rate": 0.5}` |

Un día sin logins no tiene fila: nunca hay división por cero.

### 3.4 Respuesta

```json
{
  "period": {"from": "2026-10-29T12:00:00.000Z", "to": "2026-11-05T12:00:00.000Z"},
  "metrics": {
    "events_per_day": [],
    "error_rate_by_type": [],
    "page_load_latency_by_route": [],
    "dominant_event_types": [],
    "auth_failure_rate": []
  }
}
```

---

## 4. Lo que no es técnico y se queda fuera

No se calcula nada por `office`, `product_id`, `product_category`, `programme_id`, `quantity`, `currency`, `unit_cost`, `supplier_key`, `variance_pct` ni `stock_*`. Ninguna función de §3 lee esas claves, y un test lo comprueba sobre la lista de columnas de `reindex` y sobre la respuesta.

---

## 5. Decisiones

### D1. Dónde vive `analysis.py`

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `services/telemetry/` real, con `__init__.py`, `analysis.py` y README; paquete `telemetry`; `COPY telemetry ./telemetry` junto a `app`, un bind mount y `services/` en `sys.path` desde `tests/__init__.py` | El archivo evaluado es el que se ejecuta; 1 línea en el Dockerfile y 1 en Compose; sin instalar nada | La carpeta no es un servicio desplegable; `telemetry` es un nombre genérico |
| **B** Paquete en `packages/` y `services/telemetry/analysis.py` que lo reexporta | Sigue el patrón de `packages/*` | El archivo evaluado queda vacío de funciones |
| **C** Código en `app/modules/telemetry/` y reexportar en la ruta literal | Sin tocar Docker | Igual que B, y nada importaría ese archivo |
| **D** Como A, con `pyproject.toml` propio y `pip install -e` | Sin tocar `sys.path` en los tests | Un paso más en cada venv; `package-dir` raro para esta ruta |

**Recomendación: A.** Es la única en la que la ruta evaluada contiene de verdad las funciones, con el cambio más pequeño. Los tests siguen en `services/api/tests/`: no hace falta una fila nueva en `AGENTS.md` §4. Comprobado que `telemetry` no choca en el venv.

### D2. Versión de Pandas

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `pandas>=3.1,<3.2` en `services/api/pyproject.toml` | Es lo que resuelve Python 3.14; rango acotado, como el resto | Tres transitivas además de numpy (C2) |
| **B** `requires-python >= 3.12` para que solo haya una numpy | Lock más limpio | Cambio ajeno al ticket |

**Recomendación: A.** Necesito tu visto bueno para `python-dateutil` y `tzdata`.

### D3. Qué cuenta como error

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Solo `system` | Tasa pura de fallos | Se pierden los 404, los rechazos y lo que el ticket enumera |
| **B** Todos los de C4, con `error_class` `system` / `rejected` | Nada se esconde y no se confunde un usuario con una caída | Una columna más |
| **C** Todos, sin clase | Lo más simple | Una contraseña mala sube la «tasa de error» |

**Recomendación: B.**

### D4. Denominador de la tasa

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Eventos técnicos del mismo día (`total_events`), con `occurrences` | Siempre existe; las tasas de un día suman la tasa total | Depende de cuánto se navegue; no es por petición |
| **B** Por familia: `form_submitted` entre envíos, `page_load` entre cargas; el resto, entre `page_viewed` | Más exacta en las familias con resultado | Tasas no comparables; difícil de explicar |
| **C** Todos los eventos, también los de negocio | Más simple | Los de negocio entran en una tasa técnica |

**Recomendación: A**, y cuando exista `api_latency_recorded`, pasar a peticiones.

### D5. Métrica de latencia

**Recomendación: `page_load_recorded.duration_ms`, por `route_template` y `outcome`.** No hay otra: es la única `duration_ms` que mide espera (C3). Solo necesitas confirmar que aceptas que no es latencia de API.

### D6. Fuente de `auth_failure_rate`

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `form_submitted`, `form = login`; fallo = `api_rejected`; intento = `success` + `api_rejected` | Funciona hoy con datos reales | No ve lo que no pasa por el navegador |
| **B** `login_failed` / `user_logged_in` | Es la fuente correcta del plan | No se emiten: la métrica saldría siempre vacía |
| **C** Implementar esos dos eventos ahora | Métrica exacta | Es P6: fuera del ticket |

**Recomendación: A**, con el límite escrito en la PR.

### D7. Eventos de negocio

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Excluidos de todo | Imposible de acusar de negocio | El volumen no cuadra con la tabla; `dominant_event_types` queda incompleta |
| **B** Solo en el volumen: `events_per_day` y `dominant_event_types`, sin cargar `tags`; fuera de las tasas | Mide el pipeline sin mirar qué dicen | `outbound_order_created: 3` se lee como «3 salidas» |
| **C** Agrupados como `business_events` en `dominant_event_types` | Evita lo anterior | Otro valor inventado; se pierde qué tipo pesa |

**Recomendación: B.** Un recuento por `event_type` dice cuántas filas hay, y ningún eje del reporte es oficina, producto, cantidad o coste. Lo que convierte un reporte en uno de negocio son esos ejes, y `tags` ni se carga en esas dos funciones. Si lo prefieres más estricto, C.

### D8. Clave de la caché

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** La pareja recibida, normalizada a UTC: `(start, end)`, con `None` en lo que no llegó. Ventana por defecto = `(None, None)` | Literal: «por combinación de start/end». Dos formatos del mismo instante aciertan | `period` hasta 60 s antiguo (C7) |
| **B** `now` truncado al minuto | Clave con fechas reales | Falla justo al cambiar de minuto; el TTL real baja de 60 s |
| **C** Periodo resuelto | Simple | **Nunca acierta** en la ventana por defecto |

**Recomendación: A, con `ResponseCache`.** Primero se resuelve y valida el periodo, y solo se llama a `get_or_set` si es válido: un 422 no consume caché.

### D9. Parámetros

| Caso | Propuesta | Alternativa |
|---|---|---|
| Sin zona (`2026-11-01`, `…T10:00:00`) | Se toma como UTC | 422. Más estricto, pero obliga a escribir `Z` en `/docs` |
| Con zona | Se convierte a UTC antes del SQL (§1.6) | — |
| Solo `start_date` | `end = now` | — |
| Solo `end_date` | `start = end − 7 d` | Literal `now − 7 d`: con un `end` antiguo da 422 sin motivo claro |
| `start ≥ end` | 422 `validation_error`, con `loc` en `start_date` | — |
| Rango > 90 días | 422 `validation_error`, el tope de la retención (plan §8.3) | 31 días; o sin tope (C8) |
| Epoch (`1730000000`) | Se acepta sin documentarlo: es cosa de Pydantic | Parseo propio, más código |
| `period.from` y `to` | `2026-11-05T12:00:00.000Z`, como `timestamp` del envelope. **`to` es exclusivo**, y lo dice la documentación | — |
| Precisión | Se trunca a ms antes del SQL: lo mostrado es lo filtrado | — |

**Recomendación: la primera columna.** La duda real son los naive: los trato como UTC porque el enunciado habla en UTC y escribir solo la fecha es lo natural en `/docs`.

### D10. Autenticación

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Bearer en la ruta: `dependencies=[Depends(get_current_user)]`, cualquier rol | Como el resto de datos; cumple SPECS §42 | Cualquier operador ve el reporte |
| **B** Solo admin (`require_admin`) | Más restrictivo | Las demás rutas de datos no lo hacen; el dashboard necesita lógica de rol |
| **C** Pública | Sin cambios | Expone actividad y errores sin sesión |

**Recomendación: A.** La respuesta son agregados sin identificadores. En el decorador de la ruta y no en otro router: así `test_serialization.py` la ve y el colector sigue público.

### D11. Redondeo

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Sin redondear: `float` tal cual; formatea quien presenta | Respeta la regla; no se pierde precisión | `0.05555555555555555` en el JSON |
| **B** `.round(4)` en `services/telemetry/` | JSON legible | Se salta la regla aprovechando que el test no mira ahí |
| **C** Quitar `round` de `FORBIDDEN_NAMES` | Directo | Afloja una regla del núcleo por estética |

**Recomendación: A.** El dashboard formatea con `Intl.NumberFormat`. Si quieres un JSON legible, B, y entonces el test de AST no prohibiría `round`.

### D12. De dónde saca `analysis.py` la tabla

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `from app.modules.telemetry.models import TelemetryEventRecord` | Una sola definición: lo que pide «sin duplicar» | `services/telemetry` depende de la API |
| **B** `sqlalchemy.table(...)` propia, con 4 columnas | Independiente de `app` | Duplica nombres y tipos; pueden divergir sin aviso |

**Recomendación: A.** Solo corre dentro de la API y no se reutiliza fuera. El README lo dice.

### D13. Verificación y datos

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Todas las métricas con datos en un efímero; en la demo, solo eventos reales (404, login malo, formulario vacío, Offline) y la muestra de la PR | La muestra es real; lo sembrado nunca llega a la demo | Filas nuevas permanentes en la demo, verdaderas |
| **B** Efímero, y muestra de la demo con lo que ya hay | La demo no recibe nada nuevo | `error_rate_by_type` muy pobre |
| **C** Sembrar la demo | Muestra completa | **Datos falsos permanentes: no** |

**Recomendación: A**, y sin sembrar nunca en la demo. El efímero también prueba varios días, con un `INSERT` directo del rol de prueba: el colector corrige lo que se desvía más de 5 minutos. `frontend_error_captured` solo se ve en el efímero, y la muestra de la PR dirá que esa fila no aparece.

### D14. Dashboard

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Sí: `/telemetry`, con `period`, tablas y barras de CSS, sin tocar el contrato de eventos | Extra cumplido; sin dependencias ni `1.1.0` | Sus visitas no constan en la telemetría (C14) |
| **B** Sí, añadiendo las dos rutas al contrato | La página se mide a sí misma | `1.1.0` en 5 sitios por una página interna |
| **C** No | PR más pequeña | Extra sin hacer |

**Recomendación: A, como último paso y separado**, para que un problema en el dashboard no retrase el endpoint. Barras solo en `events_per_day`; el resto, tablas.

---

## 6. Plan de F1 (cuando decidas)

Cada paso termina con su validación de `AGENTS.md` §4. **Parada** significa que sigo cuando lo confirmes.

1. **Dependencia y Docker.**
   - `pyproject.toml`, `uv.lock`, `requirements.txt` (C2), comentario de `services/Dockerfile:13`.
   - `services/telemetry/` con `__init__.py` y README; `COPY` en el Dockerfile; bind mount en Compose; `services/` en `tests/__init__.py`; fila en `services/README.md` y `README.es.md`.
   - Instalar en el venv. Si el Control de aplicaciones lo bloquea, paro y te aviso.
   - **Primera prueba real de Pandas**, en la imagen: `pd.read_sql(select, session.connection())` sobre SQLite, `dict` en `tags` y `to_dict`.
   - **Validación:** fila Docker: `docker compose config --quiet`, `docker compose up -d --build`, las comprobaciones del bloque «Docker» y el tamaño de la imagen; `unittest` y `pytest` de `services/api`.
   - **Parada 1:** reconstruir afecta al stack que apunta a la demo, aunque no escribe en ella. Si Docker falla, paro y te lo cuento.
2. **`analysis.py`.** Las 5 funciones con sus tests:
   - `tests/test_telemetry_analysis.py`: cada métrica con datos, sin datos, con `null` en `tags`, valores de cada `outcome`, `suppressed_count`, límites de la ventana;
   - test de AST (C11, C13): sin loops, `to_datetime` antes del `groupby`, sin `round`, sin `now` ni `Timedelta`;
   - ninguna columna de negocio (§4) y ningún identificador personal.
   - **Validación:** fila de `services/api`.
3. **Endpoint y caché.**
   - `router.py`: `GET /telemetry/report`, `response_model`, Bearer, `CacheDep`.
   - `schemas.py`, **por debajo de la línea 66**: el `diff` de `storage-review.md` §3 sigue sin cambios.
   - `tests/test_telemetry_report.py`: forma `{period, metrics}`, 7 días por defecto, un solo periodo para todas las funciones, cada fila de D9, 401, colector aún público, acierto sin consultas (`before_cursor_execute` = 0), TTL con reloj inyectado, un 503 que no se cachea, ventana por defecto que acierta.
   - **Validación:** fila de `services/api` y `/docs` (*Authorize* → reporte; sin token → 401).
4. **Documentación.** SPECS: fila en §41 y Parte H, sección nueva; `TESTING.md`; `services/api/README.md`; bloque en `AGENTS.md`; `docs/telemetry/report-review.md`; plan, §7.3; memory-bank. **Validación:** `python scripts/validate_event_schemas.py`.
5. **Verificación en el efímero.**
   - Postgres efímero, rol sin superusuario, override fuera del repo, como `storage-review.md` §4.
   - Eventos de todos los tipos de error y varios días; comprobar `dict`, `timestamptz`, y que cada cifra coincide con un `SELECT` a mano.
   - Comprobar C15 parando la API en ese stack.
   - **Parada 2:** tú lo repasas. Después se borra el efímero.
6. **Demo.** **Parada 3:** nada sin tu confirmación.
   - Tú generas los eventos reales de D13.
   - `GET /telemetry/report` y JSON para la PR, sin identificadores.
7. **Dashboard, si D14 es A o B.**
   - `app/telemetry/page.tsx` → `components/telemetry/telemetry-report-view.tsx` → `hooks/use-telemetry-report.ts` → `services/telemetry-report.service.ts` → `lib/api-client.ts`; normalizador, tipos, enlace en `account-nav.tsx`, y `uis/backoffice/CLAUDE.md`.
   - **Validación:** fila de `uis/backoffice`, `npx next typegen` antes de `tsc`, y navegador: sin sesión → `/login`, `period` visible, vacío, error con «Reintentar», 375 px sin scroll horizontal.
   - **Parada 4.**
8. **Cierre.** Los 5 pasos de `AGENTS.md` §4 y la PR `feat: telemetry report endpoint`: cada métrica con su pregunta, la muestra de JSON real, los extras y los límites (no es latencia de API; el denominador; el login solo desde el navegador).

---

## 7. Fuera de alcance o sin verificar

**Sin verificar en F0:**

- **Pandas sin ejecutar** (§1.6): `read_sql` con SQLAlchemy 2.1.5, el `DataFrame` de `tags` y el vacío con `reindex`. Es la primera prueba del paso 1.
- **psycopg2 con `TIMESTAMPTZ` y `JSONB`:** documentado, sin ejecutar. La sonda sin conexión hizo fallar al intérprete y se descartó; se comprueba en el efímero.
- **C15:** lectura de código; no se paró la API.
- **Tamaño instalado de la imagen:** solo se conoce el de los wheels.
- **`.pyd` de numpy y Pandas en el venv de Windows** (C2).
- **Latencia del reporte contra Supabase:** una conexión y 5 consultas por el pooler, sin medir. La caché la limita a una vez por minuto y clave.
- **`tags` reales de la demo** (§1.7). Si quieres confirmarlos, de solo lectura y sin identificadores:

  ```sql
  SELECT event_type, tags ->> 'form' AS form, tags ->> 'outcome' AS outcome, tags ->> 'route_template' AS route_template, count(*) FROM telemetry_events WHERE event_type IN ('form_submitted', 'page_load_recorded') GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;
  ```

**Fuera de este ticket:**

- P6: `api_latency_recorded`, `server_error_returned`, `login_failed`, `user_logged_in`. Cuando lleguen, cambian D4, D5 y D6.
- Percentiles (el enunciado solo admite `count`, `sum` y `mean` en `agg`).
- Métricas por oficina, programa o categoría (reporte de negocio).
- Alertas, lote nocturno y agregados (plan §7.3); la retención sigue sin automatizar.
- Día local de Valencia o Miami: `day` es UTC.

**Visto de paso, sin tocar:** `[tool.setuptools] packages` de `services/api/pyproject.toml` no incluye `app.modules.telemetry`. No afecta al venv (instalación editable) ni a Docker (`COPY`).

---

## 8. Resumen de lo recomendado

| Decisión | Recomendación |
|---|---|
| D1 Ubicación | `services/telemetry/` real, copiada junto a `app` en la imagen |
| D2 Pandas | `pandas>=3.1,<3.2` en `services/api`; aceptar también `python-dateutil` y `tzdata` |
| D3 Error | Todos los candidatos, con `error_class` `system` / `rejected` |
| D4 Denominador | Eventos técnicos del día, sumando `suppressed_count` |
| D5 Latencia | `page_load_recorded.duration_ms` por ruta y `outcome` |
| D6 Login | `form_submitted`: fallo = `api_rejected`; intento = `success` + `api_rejected` |
| D7 Negocio | Solo cuentan en el volumen, sin cargar `tags`; fuera de las tasas |
| D8 Caché | `ResponseCache`, clave `(start, end)` recibida; `(None, None)` por defecto |
| D9 Parámetros | Naive = UTC, `start ≥ end` → 422, tope de 90 días, `Z` con ms, fin exclusivo |
| D10 Auth | Bearer, cualquier rol, en la propia ruta |
| D11 Redondeo | Sin redondear en la API; formatea el dashboard |
| D12 Tabla | Importar `TelemetryEventRecord` |
| D13 Datos | Todo en el efímero; en la demo, solo eventos reales y la muestra |
| D14 Dashboard | Sí, último y aparte, sin tocar el contrato de eventos |
