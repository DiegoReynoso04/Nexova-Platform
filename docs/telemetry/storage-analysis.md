# Almacenamiento de telemetría — análisis (F0)

Documento de trabajo del ticket «Telemetría · Almacenamiento». **F0: análisis y decisiones; no hay código.**

> **Decidido por el usuario el 2026-11-04:**
>
> - **D1–D3 y D5–D10, D12:** opción A, como se recomienda abajo. D2 lleva `CHECK`. D5 se documenta en el plan, §8.3, con fecha y la condición de agregar antes de borrar. C15 y el cupo anónimo compartido se aceptan y van al plan, §8.4.
> - **D4: B.** Resultado de las dos consultas de solo lectura autorizadas sobre la demo: `current_user = postgres`, `rolsuper = false`, `rolbypassrls = true`. `anon`, `authenticated`, `postgres` y `service_role` tienen todos los privilegios sobre `assets`, así que una tabla nueva los hereda: el `REVOKE` alcanza a los cuatro y a `PUBLIC`. Con `rolbypassrls = true`, RLS no frena a la API ni con `FORCE`.
> - **D11: variante literal del enunciado, no la opción A.** «Parseable» = tiene un arreglo `events`. 422 solo si el body no es JSON, no tiene `events`, `events` no es una lista o hay claves extra junto a él. `events: []` → `200 {0, 0, 0}`. Más de 50 → se procesan los 50 primeros y el resto cuenta en `rejected`. C6 y la receta ya lo reflejan.
> - **Son 4 columnas libres, no 3** (§2.1).
>
> Lo demás sigue tal como se presentó.

- **Rama:** `feature/telemetry-storage`, desde `main` en `8461f34` (PR #29 mergeada; `origin/main` en el mismo commit).
- **Contrato:** [`telemetry-plan.md`](./telemetry-plan.md) y [`event-schemas.json`](./event-schemas.json), versión `1.0.0`. Decisiones de la captura: [`capture-analysis.md`](./capture-analysis.md) y [`capture-review.md`](./capture-review.md). BRIEFING: [`docs/proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md`](../proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md).
- **Enunciado del ticket:** no se versiona; aquí solo se cita lo que choca con el plan o con el código.
- **Cómo leerlo:** **Verificado** es lo comprobado en el código o ejecutado. **Propuesta** es diseño nuestro, pendiente de decisión.

**Aviso sobre el enunciado.** Dice que `docs/telemetria-de-tu-compañia-almacenamiento.md` «explica qué campos del envelope y qué dimensiones de tags importan». **No es así:** ese archivo es byte a byte el BRIEFING (`cmp` sin diferencias con `docs/proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md`). No contiene la palabra `tags`. Del envelope solo dice «además del envelope estándar» y, en esa misma línea (`:49`), nombra los 6 campos mínimos de `properties`. El contrato de los campos y de las dimensiones es el plan (§5, §6) y `event-schemas.json`.

**Falta parte del enunciado.** Anuncia «la siguiente estructura» y «este contrato» de mapeo `TelemetryEvent` → fila, pero no los incluye. Solo se sabe que hay 8 columnas, de las que nombra `event_type`, `timestamp`, `service` y `tags`. El resto del esquema es decisión nuestra y la PR tiene que decirlo.

---

## 1. Estado verificado

### 1.1 Colector y telemetría de la API

| Pieza | Estado | Dónde |
|---|---|---|
| Stub | `def receive_events(batch: TelemetryBatch)`: valida el lote entero, registra y responde `200 {"received": N}`. Sin dependencia de autenticación ni de base | `services/api/app/modules/telemetry/router.py:26-33` |
| `TelemetryEvent` | 8 claves, `extra="forbid"`, `frozen=True`, patrones del JSON. `event_type` debe estar entre los 52 del catálogo | `schemas.py:44-66` |
| `TelemetryBatch` | `events: list[TelemetryEvent]`, de 1 a 50, `extra="forbid"`. Es justo el tipo que el enunciado prohíbe como body | `schemas.py:69-74` |
| `catalog.py` | Copia de los 52 `event_type` y de `SCHEMA_VERSION`, comparada con el JSON por la suite. No tiene el emisor ni la allowlist de cada evento | `catalog.py:1-67`; `tests/test_telemetry_events.py:182-204` |
| `emitter.py` | `emit()` construye el envelope y llama a `log_event`; nunca lanza. `requestId` es un `uuid4` si no hay otro (P5). `Throttle` deja pasar uno por ventana: no es un contador de 120/min | `emitter.py:56-102` |
| Log `nexova.telemetry` | Una línea JSON por evento; solo la escribe `log_event`. Nadie la lee | `app/core/telemetry.py:39-44` |
| Log `api.telemetry` | Una línea por lote con el número de eventos y sus tipos | `app/core/telemetry.py:34-36` |
| `StockEditReporter` | Único emisor de la API. Ya tiene el motor (`main.py:80`). Se llama desde handlers `async` y abre una `Session` síncrona: bloquea el bucle de eventos | `stock_edit.py:106-114`; `core/errors.py:207-219` |
| `BodySizeLimitMiddleware` | 64 KiB por ruta, con las dos barreras, antes de la app. Responde 413 `file_too_large` | `core/limits.py:21-52`; `main.py:119-123` |
| Handlers de error | `OperationalError`, `InterfaceError` y `TimeoutError` de SQLAlchemy → 503 `storage_unavailable`, sin SQL. El resto (`ProgrammingError`, `DataError`) → 500 opaco | `core/errors.py:26`, `:222-229`, `:263-294` |

### 1.2 Cómo trata el frontend cada respuesta

`uis/backoffice/lib/telemetry.ts:125-147`, comprobado en el código:

| Respuesta | Qué hace | Línea |
|---|---|---|
| 2xx | Lote hecho. **Solo mira el código de estado, nunca el cuerpo** | `:133`, `:137` |
| 5xx y 429 | Reintenta a 1, 2 y 4 s; después descarta | `:81-83`, `:111-123`, `:138` |
| Otro 4xx (también 401, 413 y 422) | Descarta sin reintentar | `:139` |
| `ApiNetworkError` o `ApiTimeoutError` | Reintenta igual | `:143` |
| Otro error (configuración, abort) | Descarta | `:144` |
| Beacon | Sin reintento y sin leer la respuesta | `:170-173` |

Además: el timeout de cada envío es de 5 s (`:43`), un lote vacío no se envía nunca (`:151`) y el lote máximo es de 20 eventos (`:39`). Un 200 con `rejected > 0` no se reintenta: los rechazados se pierden en silencio, que es lo que pide el enunciado.

### 1.3 Base de datos

| Pieza | Estado | Dónde |
|---|---|---|
| Motor | Uno por app en `app.state.inventory_engine`. PostgreSQL con psycopg2, `NullPool`, `connect_timeout=5`, `hide_parameters`. Supabase por el Transaction pooler (6543) | `modules/inventory/database.py:58-89` |
| Sesión | `get_db`, una `Session` por petición. Es perezosa: si no hay ningún evento válido, no se abre conexión | `database.py:146-151` |
| `init_db` | Al arrancar, `create_all` **solo de `INVENTORY_TABLES`** y RLS. Si falla, uvicorn no arranca | `database.py:98-111` |
| RLS | `ENABLE` sin políticas en las tres tablas. **La API conecta como dueña y RLS no se le aplica** (sin `FORCE`) | `database.py:114-126` |
| `migrate.py` | `--dry-run`, una transacción, idempotente, solo PostgreSQL, códigos 0/1/2, nunca lo ejecuta la API | `modules/inventory/migrate.py:1-147` |
| Sin dependencias nuevas | SQLAlchemy 2.1.5, sqlmodel 0.0.48 y psycopg2-binary 2.9.13 cubren `JSONB`, GIN y `ON CONFLICT` | `services/api/uv.lock` |

### 1.4 Restricciones de `tests/test_architecture.py`

| Regla | Línea | Efecto en este ticket |
|---|---|---|
| Prohibido importar `re`, `csv`, `statistics`, `fractions` en `app/` | `:29`, `:79-92` | El validador de `scripts/validate_event_schemas.py` usa `re`: no se puede copiar. Los patrones tienen que ir por Pydantic (`Field(pattern=…)`) |
| Ningún literal con `\d` | `:70` | Los 3 patrones de los 15 eventos no lo llevan (ejecutado) |
| Sin vocabulario del gestor en `app/` | `:72-77` | **La allowlist de los 52 eventos choca:** 18 valores (`open`, `resolved`, `customer`…). La de los 15 que hacen falta no choca con ninguno (85 valores, ejecutado) |
| `print` solo en `PRINT_ALLOWED` | `:36`, `:88` | Un `migrate.py` nuevo necesita su entrada, como la de `modules/inventory/migrate.py` |
| La palabra `logging` solo en `core/errors.py`, `core/timing.py` y `core/telemetry.py` | `:106-114` | Los logs del colector van por funciones de `core/telemetry.py` |

### 1.5 Pruebas ejecutadas (en memoria, sin conectar a ninguna base)

Con el venv de `services/api`, que hoy carga SQLAlchemy sin el bloqueo que describe `TESTING.md` §14:

| Comprobación | Resultado |
|---|---|
| DDL compilado con el dialecto de PostgreSQL | `UUID`, `TIMESTAMP WITH TIME ZONE`, `JSONB`, `USING gin (tags)`. `timestamp` no es palabra reservada para SQLAlchemy: va sin comillas |
| Misma tabla en SQLite | Con `JSON().with_variant(JSONB(), "postgresql")` y `Uuid` se crea sin cambios: `CHAR(32)`, `JSON` e índice normal |
| `postgresql.insert(t).values(filas).on_conflict_do_nothing(...)` | Compila a **un solo `VALUES`** y **también se ejecuta en SQLite**: un solo camino de código para tests y producción. 4 filas con un duplicado dentro del lote → `rowcount` 3 |
| Repetir el mismo lote | `rowcount` 0, sin error |
| `session.execute(insert(t), filas)` | En SQLite también dispara **un** `before_cursor_execute`, pero con `executemany=True`: contar eventos no basta (C13) |
| Claves con `null` en `tags` | Se conservan como JSON `null`: `{"a": null, "product_category": null}` |
| `TelemetryEvent` con `2026-13-45T99:99:99.000Z` o `0000-01-01T…` | **Lo acepta:** el patrón no comprueba el calendario. `datetime.fromisoformat` lanza `ValueError` (C4) |
| `TelemetryEvent` con `Infinity`, `NaN` o `\u0000` en `properties` | **Lo acepta.** `json.loads` también admite `NaN` y `1e400` (C4) |
| `TelemetryEvent.model_validate` con un item que no es objeto | `ValidationError` (`model_type`): lo recoge el `try/except` del enunciado |
| Strings en las allowlists de los 15 eventos | Todos tienen `enum` o `pattern`: ningún texto libre. Los números sin `maximum` son solo enteros (`suppressed_count`, `timeout_ms`) |
| Lote mixto de §5.4 | Cada evento da el resultado previsto contra `TelemetryEvent` y contra el JSON |

---

## 2. Diseño de las 8 columnas

### 2.1 Lo fijado y lo que queda

**Fijado por el enunciado:** `event_type`, `timestamp`, `service` y `tags` (JSONB = `properties` filtrado por la allowlist), más índices en `timestamp` y `event_type` y GIN en `tags`.

**Quedan 4 columnas sin nombre, no 3.** El encargo de F0 habla de 5 candidatas para 3 columnas, pero la cuenta es: 8 columnas menos las 4 fijadas (`service` incluida) son 4. Las candidatas sí son 5: `eventId`, `sessionId`, `userId`, `schemaVersion` y `requestId`. La propuesta a contrastar también usa 4. **Sobra siempre al menos una clave del envelope**, y una más por cada columna propia (`id`, `received_at`).

`service` no está en el envelope ni en el plan. Lo más cercano es el emisor: `$comment` dice `emisor=frontend` o `emisor=api`, y la columna «Emisor» de §4 dice `frontend` o `API` (D2).

### 2.2 Opciones

Tipos comunes a las tres opciones: `event_type VARCHAR(64) NOT NULL`, `timestamp TIMESTAMPTZ NOT NULL`, `service VARCHAR(16) NOT NULL` y `tags JSONB NOT NULL`. Sin `DEFAULT` en la base: todos los valores los pone la API, como en el inventario. El `event_type` más largo tiene 31 caracteres; 64 es holgura.

**Opción A (propuesta del usuario, recomendada).** Mapeo explícito de snake_case a camelCase:

| Columna | Tipo | NULL | Sale de | Sirve para |
|---|---|---|---|---|
| `event_id` | `UUID` PK | NOT NULL | `eventId` | Deduplicar (plan §7.3) |
| `event_type` | `VARCHAR(64)` | NOT NULL | `event_type` | Recuentos por evento |
| `timestamp` | `TIMESTAMPTZ` | NOT NULL | `timestamp`, tras la regla de ±5 min | Series por día |
| `service` | `VARCHAR(16)` | NOT NULL | Lo pone el servidor (D2) | Separar `backoffice` y `api` |
| `user_id` | `UUID` | NULL | `userId`, o `sub` del token | Cruce con `user_uuid` de las órdenes (§8.3); retención |
| `session_id` | `UUID` | NULL | `sessionId`, o `sid` del token | Embudos y abandono por sesión |
| `schema_version` | `VARCHAR(16)` | NOT NULL | `schemaVersion` | Interpretar `tags` cuando convivan dos versiones (§5.4) |
| `tags` | `JSONB` | NOT NULL | `properties`, filtrado | Oficina, programa, categoría, cantidad, moneda |

**Se pierde:** `requestId`, y la hora de recepción.

**Opción B: `request_id` en lugar de `schema_version`.** Las demás columnas son iguales.

- **A favor:** guarda el envelope que hoy varía de verdad y, con P5, permitiría correlacionar con `api.timing`.
- **En contra:** hoy `requestId` es un UUID aleatorio por evento (`lib/telemetry.ts:194`, `emitter.py:97`, P5 pendiente): no correlaciona nada. Además, §8.3 lo trata como identificador sujeto a los 90 días. Y se pierde `schema_version`, que hoy es constante pero **no se puede reconstruir** cuando convivan `1.x` y `2.0.0`.

**Opción C: columnas propias.** `id BIGINT IDENTITY` PK, `event_id UUID UNIQUE`, `event_type`, `timestamp`, `received_at TIMESTAMPTZ`, `service`, `user_id`, `tags`.

- **A favor:** conserva el orden de llegada (§7.3 lo pide para las líneas del log) y deja medir la desviación del reloj.
- **En contra:** para que quepan hay que perder `session_id`, `schema_version` y `request_id`. `id` no aporta nada a `event_id`, que ya es una clave natural, y añade otro índice. `received_at` tiene poco valor: la cola solo guarda un evento hasta 10 s, más 7 s de reintentos, y un `timestamp` desviado ya se sustituye.

**Comparación:**

| | A | B | C |
|---|---|---|---|
| Deduplicación | PK | PK | `UNIQUE` |
| Índices físicos | 4 (3 + PK) | 4 | 5 |
| Interpretar `tags` entre versiones | Sí | **No** | **No** |
| Embudos por sesión | Sí | Sí | **No** |
| Correlación con la API (tras P5) | No | Sí | No |
| Cruce con las órdenes | Sí, con `user_id::text` | Igual | Igual |
| Retención (§8.3) | Borrado por `timestamp` | Igual, con un identificador más | Borrado por `timestamp` o `received_at` |
| Privacidad | `user_id`, `session_id` | Además `request_id` | Solo `user_id` |

**Índices y evaluación:** «3 índices» son los del enunciado. La PK crea un cuarto índice que `pg_indexes` mostrará; es inevitable si se deduplica en la base. La PR debe decirlo.

### 2.3 Detalles comunes

- **`UUID` frente a `VARCHAR(36)`:** `UUID` es la segunda barrera en la base, como los `CHECK` del inventario. El precio es un cast en el cruce (`user_uuid` es `VARCHAR(36)`, `vocabulary.py:13`). Con `sa.Uuid`, las filas llevan objetos `uuid.UUID`. El `sub` real siempre es un `uuid4` (`auth/repository.py:93`), pero se valida antes de sustituirlo (C3).
- **`timestamp`:** la hora del cliente si está a ±5 min de la recepción; si no, la de recepción. Una sola hora de recepción por lote. Para eventos de la API, la de `emit`. Se pierde la hora original del cliente cuando se sustituye (aceptable: es la que estaba mal).
- **GIN:** `jsonb_ops`, el operador por defecto, que admite `@>` y `?`. `jsonb_path_ops` ocupa menos, pero no admite `?`.
- **`tags` guarda los `null`:** `tags ? 'programme_id'` es verdadero aunque el valor sea `null`. Una consulta debe usar `tags ->> 'programme_id' IS NULL`, no `NOT tags ? …`.

---

## 3. Conflictos

### C1. Respuesta

- **Enunciado:** «responde HTTP 200 {"received": N, "stored": M, "rejected": R}».
- **Plan** (`telemetry-plan.md:165`): «`202 {"accepted": n, "rejected": m}`».
- **Stub** (`router.py:33`): `TelemetryBatchReceived(received=len(batch.events))` → `200 {"received": N}`.
- **Hecho:** el frontend solo mira 2xx (§1.2): ninguna de las tres le afecta.
- **Propuesta:** manda el enunciado, que es lo que se evalúa. Se corrige §2.4 del plan (texto, sin cambio de versión). No necesita decisión.

### C2. Evento rechazado, sin tocar `TelemetryEvent`

- **Enunciado:** «El modelo TelemetryEvent se reutiliza SIN MODIFICARLO».
- **Plan** (`:162`): «solo los `event_type` de emisor *frontend*».
- **Comentario en el código** (`schemas.py:62-63`): «El colector definitivo solo aceptará los de emisor frontend». **Ese comentario se queda como está:** queda desfasado a propósito, y lo aclara SPECS.

Todo lo que el plan pide al colector es un paso **posterior** al modelo, en un módulo nuevo:

| Regla | Dónde vive (propuesta) | ¿Rechazo? |
|---|---|---|
| Envelope (8 claves, patrones, catálogo) | `TelemetryEvent.model_validate(raw)` | `rejected` |
| Emisor frontend | `FRONTEND_EVENT_TYPES` en `catalog.py`, comparado con el JSON por la suite | `rejected` |
| Fecha real | `datetime.fromisoformat` tras el modelo (C4) | `rejected` |
| Token: `userId`/`sessionId` | Sobre la fila, no sobre el modelo (`frozen=True`) | No |
| Allowlist | Tabla de C5 | Según D6 |
| ±5 min | Sobre la fila | No: se corrige, no se rechaza |
| 120 eventos/min | Contador nuevo en memoria (`--workers 1`) | `rejected` (`:2352`) |

**Cómo se demuestra** que la clase no cambió: las clases nuevas van después de la línea 66 y se comparan las 66 primeras, con el docstring del módulo, los patrones y la clase:

```bash
F=services/api/app/modules/telemetry/schemas.py; diff <(git show main:$F | sed -n '1,/^        return value/p') <(sed -n '1,/^        return value/p' $F) && echo "TelemetryEvent sin cambios"
```

Probado hoy: 66 líneas, sin diferencias. La salida va en la PR. `TelemetryBatch` se sustituye (es lo que el enunciado prohíbe) y `TelemetryBatchReceived` crece con los dos contadores: los dos están por debajo de la línea 66.

### C3. Identidad: cliente frente a token

- **Plan** (`:160`): «el colector los sustituye por los del token cuando la petición trae uno válido». **Pero** `:298` dice: «En el frontend lo pone el colector, nunca el cliente», una frase anterior a C6 de la captura que se corrige en F1.
- **Hecho:** `read_token_claims` ya existe y no consulta TinyDB (`auth/security.py:112-134`). Un beacon no lleva token (`telemetry.ts:15`).
- **Propuesta:** con token válido, `user_id = sub` y `session_id = sid`, solo si cumplen el patrón UUID v4. Sin token, o con uno inválido, quedan los declarados. Nunca un 401: la ruta sigue siendo pública (`main.py:97-99`).
- **Efecto secundario aceptado:** un lote con eventos anteriores al login, enviado después, queda atribuido al usuario que acaba de entrar.
- **Las reglas de identidad del esquema** (`sessionId` y `userId` no nulos en 5 de los 14 eventos: los 4 de negocio y `user_logged_out`) se comprueban **después** de sustituir.

### C4. `try/except ValidationError` no basta

- **Enunciado:** «Cada item se valida con TelemetryEvent.model_validate(raw) dentro de un try/except ValidationError».
- **Verificado (§1.5):** el modelo deja pasar lo que después **rompe el insert de todo el lote**:
  - una fecha imposible con el patrón correcto: `ValueError` en Python o, sin conversión, error en PostgreSQL;
  - `NaN`, `Infinity` o `\u0000` dentro de `properties`: `jsonb` no los admite, y un `DataError` no es de los que dan 503 (→ 500).
- **Consecuencia:** un evento envenenado tiraría 19 válidos y se reintentaría 3 veces. Es justo lo contrario del rechazo individual.
- **Propuesta:** `fromisoformat` en el mismo paso por evento, capturando `ValueError`, y la allowlist antes del insert. Como no hay texto libre en los 15 eventos y las claves extra no llegan a `tags`, ni `\u0000` ni `NaN` pueden pasar, siempre que los números se validen con `allow_inf_nan=False`. Test específico de cada caso.

### C5. Allowlist en `tags`

- **Enunciado:** `tags` guarda `properties` «solo con las claves de la allowlist».
- **El plan se contradice:**
  - `:123-124` (P6): «Una clave fuera de la allowlist **se descarta** antes de emitir. Un valor fuera de su tipo o enum **anula el evento**»;
  - `:370`: «P6 la descarta; el colector, P8, la rechaza»;
  - `:163`: «cada evento se valida contra su allowlist (como P6)»;
  - `:2362`: «validar cada evento contra `event-schemas.json` antes de guardarlo», que tiene `additionalProperties: false`.
- **La API no tiene el JSON:** la imagen se construye con `./services` (`catalog.py:3-7`).
- **Propuesta de la tabla:** `allowlists.py`, copia de la definición de **15 eventos** (14 de frontend + `direct_stock_edit_rejected`), comparada con el JSON por la suite, como `catalog.py`. Los modelos por evento se construyen con Pydantic al importar (`create_model`, `strict`, `pattern`, `Literal`, `extra="ignore"`). No puede ser un validador con `re`, ni la tabla de los 52 (§1.4). El `oneOf` oficina–moneda de los eventos de inventario necesita una regla propia. Regla de clave y valor: D6.

### C6. Envelope laxo

«Envelope» significa dos cosas: en el enunciado es el cuerpo `{"events": […]}`; en el plan, las 8 claves del evento.

- **Enunciado:** «Mientras el envelope sea parseable, responde HTTP 200».
- **Plan** (`:159`): «de 1 a 50 eventos, ≤ 64 KiB». La suite actual exige 422 en vacío y en 51 (`test_telemetry_events.py:87-91`).

Decidido (D11, «parseable = tiene un arreglo `events`»):

| Entrada | Respuesta | Por qué |
|---|---|---|
| Body no JSON | 422 | No es parseable |
| Sin `events`, o `events` no es lista | 422 | Ídem |
| Clave extra junto a `events` | 422 | Como hoy: el cuerpo tiene una sola clave |
| `events: []` | `200 {"received": 0, "stored": 0, "rejected": 0}` | Es parseable; el frontend no lo envía nunca |
| Más de 50 eventos | 200: se procesan los 50 primeros y el resto cuenta en `rejected` (`received` = total) | Es parseable; `MAX_EVENTS_PER_BATCH` se reutiliza como tope de proceso |
| Item que no es objeto | 200, cuenta en `rejected` | Para eso es laxo: `events: list[Any]` |
| Más de 64 KiB | 413, sin cambios | `BodySizeLimitMiddleware` |

Un 4xx no se reintenta (§1.2). Cambia lo que la suite del stub exigía en vacío y en 51 eventos, y el «de 1 a 50» del plan, §2.4.

### C7. Deduplicación e invariante

- **Plan** (`:2363`): «deduplicar por `eventId`»; (`:176`): «La deduplicación por `eventId` (§7.3) absorbe un reintento».
- **Enunciado:** `stored` y `rejected`, sin nada para duplicados.
- **Hecho:** un reintento tras un timeout puede repetir un lote que sí se guardó (`telemetry.ts:143`), y `ON CONFLICT DO NOTHING` también absorbe duplicados dentro del mismo lote (ejecutado).
- Ver D9.

### C8. `direct_stock_edit_rejected`

- **Plan:** `:2361` pide «leer las líneas de `nexova.telemetry`»; es un obligatorio del BRIEFING.
- **Enunciado:** habla solo del colector HTTP. La evaluación pide `event_type`, `timestamp` y `tags` «tanto en eventos técnicos como de negocio».
- **Hecho:** el plan prohíbe que llegue por el colector (`:162`). Hoy solo existe como línea de log, que se pierde con el contenedor.
- Ver D8.

### C9. Inmutabilidad frente a retención

- **Enunciado:** «Sin lógica de UPDATE ni DELETE: los eventos son inmutables».
- **Plan** (`:2409`): «**90 días**. Después se borran o se agregan».
- **Propuesta:** son dos cosas distintas. La aplicación nunca actualiza ni borra; la retención es una operación de administración, fuera de la API. Ver D5.

### C10. Cómo se hace inmutable en la base

- **Hecho:** la API conecta como dueña y RLS no se le aplica (`database.py:118-119`): RLS **no** impide nada a la API. Un `FORCE` con políticas tampoco es seguro si el rol tiene `BYPASSRLS`.
- **Sin verificar:** los atributos del rol real en Supabase (§6). Ver D4.
- **Ojo al probarlo:** el usuario por defecto de la imagen `postgres` es superusuario y **salta cualquier `REVOKE`**. La prueba tiene que hacerse con un rol sin superusuario (§5.3).

### C11. Dimensiones del BRIEFING

- **Enunciado:** `tags` «conserva las allowlists y las dimensiones del BRIEFING».
- **Hecho:** `office`, `product_id`, `product_category`, `programme_id`, `quantity` y `currency` están en la allowlist de los 9 eventos de inventario. `product_category` y `programme_id` van en `null` (`lib/inventory-telemetry.ts:45-46`; `stock_edit.py:141-142`).
- **Confirmado (§1.5):** se guardan como JSON `null`, sin desaparecer, siempre que el filtro use la presencia de la clave y no su veracidad. Todas son obligatorias en el esquema (plan `:380`): si faltara una, el evento se rechaza. F1 incluye un test específico de estos `null`.

### C12. Fallo de la base durante el insert

- **Enunciado:** no lo trata. Dice 200 «mientras el envelope sea parseable».
- **Hecho:** `OperationalError` y similares dan 503 sin código nuevo (`errors.py:222-229`). El frontend reintenta los 5xx.
- Ver D10.

### C13. Tests sobre SQLite

- **Enunciado:** evalúa «bulk insert (una operación por lote)».
- **Hecho:** la suite usa SQLite (`tests/support.py:39`) y ningún test conecta con Supabase.
- **Propuesta:**
  - **JSONB, GIN y DDL:** compilar con el dialecto de PostgreSQL, como `test_inventory_database.py:57-61`;
  - **una sentencia:** escuchar `before_cursor_execute` y exigir **una** llamada, con `executemany=False` y N grupos en `VALUES`. Contar llamadas no basta: `session.execute(insert(t), filas)` también da 1 (§1.5);
  - **inmutabilidad:** las sentencias de la migración, como texto, en la suite; el efecto real (`permission denied`), en el Postgres efímero, como se hizo con P3 (`TESTING.md:332`);
  - **`test_serialization.py`** ya exige `response_model`: el modelo nuevo entra solo.

### C14. Stream, batch y alertas

- **Plan** (`:2364-2365`): «enviar los eventos stream a la ruta de alertas» y «consolidar los batch en el lote nocturno».
- **Enunciado:** no lo pide; las consultas analíticas son «del siguiente proyecto».
- **Hecho:** no existe ninguna ruta de alertas.
- **Propuesta:** fuera. Se anota en §7.3 qué queda pendiente. El efecto es que `stock_threshold_triggered` y `kit_cost_variance_detected` se guardan, pero nadie recibe una alerta.

### C15. Eventos de negocio falsificables (no estaba en la lista)

- **Plan** (`:162`): «el frontend no puede fabricar intentos de edición del stock». Solo protege uno de los 5 obligatorios.
- **Hecho:** desde D1 «A ligera», los otros 4 llegan por una ruta **pública**, y `capture-analysis.md:149` (C8) los daba por protegidos antes de esa decisión. Hasta hoy un evento falso no dejaba rastro; con este ticket se guarda para siempre en una tabla que alimentará el informe de Laura.
- **Por qué no se resuelve aquí:** exigir token rompería el beacon (`telemetry.ts:15`), y un obligatorio que salga por ahí se perdería. Tampoco hay columna para marcar «no verificado» sin cambiar el diseño.
- **Propuesta:** riesgo aceptado y documentado en §8.4 del plan, con el throttle como único freno. Necesita tu visto bueno (D7).

### C16. Crear la tabla al arrancar escribiría en la demo (no estaba en la lista)

- **Tu regla:** «la base de la demo, solo con mi confirmación explícita».
- **Hecho:** el `.env` del stack apunta a la demo (`capture-review.md:144`), la API usa `--reload` (`docker-compose.yml:32`) y `init_db` corre en cada arranque. Si la tabla entra en `INVENTORY_TABLES`, **cambiar a esta rama con el stack levantado la crea en Supabase sin preguntar.**
- Ver D3.

---

## 4. Decisiones

### D1. Las 8 columnas

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `event_id` PK, `event_type`, `timestamp`, `service`, `user_id`, `session_id`, `schema_version`, `tags` | Conserva lo que no se puede reconstruir; clave natural | Sin `requestId`: la correlación de P5 necesitará otra columna |
| **B** `request_id` en lugar de `schema_version` | Prepara P5 | Hoy guarda ruido; `tags` queda ambiguo al cambiar de versión |
| **C** `id`, `event_id`, `received_at`, sin `session_id` ni `schema_version` | Orden de llegada | Pierde embudos y versión a cambio de poco |

**Recomendación: A, con `UUID` en los tres ids.** `schema_version` no se puede reconstruir después y `requestId` hoy no significa nada. Si P5 llega, se añade `request_id` con un `ADD COLUMN` nullable.

### D2. Valores de `service`

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `backoffice` / `api` | Nombra la app (`uis/backoffice`, `services/api`); distingue al tracker si un día entra | Vocabulario nuevo (el plan dice «emisor») |
| **B** `frontend` / `api` | Es el vocabulario exacto del `$comment` | No distinguiría dos frontends |

**Recomendación: A**, documentada como decisión nuestra. Lo pone siempre el servidor según por dónde entra el evento: colector → `backoffice`; emisor → `api`. El cliente no puede enviarlo (`extra="forbid"`). Con `CHECK`, como el vocabulario del inventario. Hoy `service` se deduce de `event_type`; un test comprueba que coincide con el catálogo. Una petición con `curl` a la ruta pública también queda como `backoffice`.

### D3. Cómo se crea la tabla

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `python -m app.modules.telemetry.migrate [--dry-run]`, nunca al arrancar | Respeta tu regla; patrón de P3; RLS y `REVOKE` en la misma transacción | Un paso más, y sin él el colector da 500 |
| **B** En `init_db` | Sin pasos manuales | **Crea la tabla en la demo sin confirmación** (C16) |
| **C** SQL a mano en Supabase | Nada de código | Sin idempotencia ni prueba; el esquema puede divergir del modelo |

**Recomendación: A.** El DDL se compila del modelo, para que no diverjan. Sin migrar, el colector responde 500 (`ProgrammingError`) y el frontend descarta tras 3 reintentos: **la migración tiene que ir antes del merge.** Los tests crean la tabla con un helper.

### D4. Inmutabilidad en la base

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Solo convención + RLS sin políticas | Lo más simple | No frena a la API ni a nadie con el rol dueño |
| **B** A + `REVOKE UPDATE, DELETE, TRUNCATE` a `PUBLIC` y al rol de la API (y a `anon`, `authenticated` y `service_role` si existen) | Lo impone la base al rol que usa la API; sin objetos nuevos | El dueño puede volver a concederse el permiso; no vale si el rol es superusuario |
| **C** A + trigger `BEFORE UPDATE OR DELETE` y `BEFORE TRUNCATE` que lanza una excepción | Frena a todos, también en el editor SQL | Función y dos triggers; la retención tiene que desactivarlo |

**Recomendación: B**, si la comprobación de solo lectura de §6 confirma que el rol no es superusuario; si lo es, C. B encaja con la retención: el trabajo de limpieza se concede `DELETE`, borra y lo revoca en una transacción. Con `INSERT … ON CONFLICT DO NOTHING` basta `INSERT` y `SELECT`. Una prueba de `UPDATE` en el efímero, con rol sin superusuario, debe dar `permission denied`.

### D5. Retención de 90 días

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Fuera del ticket, documentada como operación de administración | Cumple «sin lógica de DELETE»; alcance limpio | Si nadie la programa, se incumple D9 del plan |
| **B** Job programado ahora (`pg_cron`) | Automático | Infraestructura no pedida; borra antes de que exista un agregado |
| **C** Anonimizar con `UPDATE` | Conserva los eventos | Contradice la inmutabilidad |

**Recomendación: A**, con fecha: la primera fila caduca 90 días después de la primera escritura. El siguiente proyecto tiene que agregar **antes** de borrar: los agregados aún no existen.

### D6. Allowlist

| Opción | Clave extra en `properties` | Valor inválido | Encaja con |
|---|---|---|---|
| **A** | Se descarta la clave y se guarda el evento | Se rechaza el evento | P6 (`:123-124`), `:163` y el «solo con las claves de la allowlist» del enunciado |
| **B** | Se rechaza el evento | Se rechaza el evento | `:370`, `:2362` y `additionalProperties: false` |

**Recomendación: A.** Es la regla del emisor que el plan pone como modelo, y perder un evento de negocio por una clave de más es peor que quitarla: la clave nunca llega a la tabla y la fila resultante valida contra el JSON. Se corrige `:370` y `:2362` (texto, sin cambio de versión). El log cuenta las claves quitadas, sin sus nombres, que son texto del cliente. Una clave extra **en el envelope** sigue siendo rechazo: es `extra="forbid"` y no se toca.

### D7. Qué reglas del colector definitivo entran

Emisor frontend, sustitución por token, ±5 min y validación por allowlist no tienen alternativa razonable: son el contrato y sin ellas se guardarían datos que el plan prohíbe. La duda real es el throttle:

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Todas, con 120/min por token y uno común para anónimos; exceso → `rejected` | Única protección de una ruta pública que ahora escribe en la base | Todos los beacons comparten el mismo cupo anónimo |
| **B** Sin throttle | Menos código | Cualquiera llena la tabla inmutable |

**Recomendación: A**, y aceptar C15. El cupo anónimo compartido se revisa con la primera semana de datos: unas decenas de operadores, con beacons de pocos eventos, no deberían llegar a 120/min (estimación, no medido; plan `:2354`).

### D8. Eventos que emite la API

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Insert directo tras `emit`, con el motor que ya tiene `StockEditReporter`; `service='api'` | Un obligatorio en la tabla sin infraestructura nueva | Bloquea el bucle hasta 5 s si la base cae, como ya hace `_office_of` (`stock_edit.py:110`) |
| **B** `BackgroundTask` en la respuesta | No bloquea | Toca `core/errors.py`, que hoy no conoce nada de esto |
| **C** Fuera: solo el log | Nada que cambiar | El obligatorio no llega a la tabla |
| **D** Leer las líneas del log (`:2361`) | Literal del plan | Otro proceso y otro despliegue |

**Recomendación: A.** El throttle (1 por 60 s y clave) acota el bloqueo, y un fallo nunca cambia la respuesta (`stock_edit.py:83-84`): se registra la clase y el evento queda solo en el log. Es «bulk» de una fila por la misma función del colector. El evento pasa por la misma allowlist. Si te preocupa el bloqueo, B.

### D9. Duplicados

| Opción | Reintento de un lote ya guardado | Riesgo |
|---|---|---|
| **A** Cuenta como `stored` | Misma respuesta: `stored` = «está en la tabla» | `stored` no es el número de filas nuevas |
| **B** Cuenta como `rejected` | `rejected` crece sin que nada esté mal | Falsa alarma |
| **C** Tercer contador `duplicates` | Lo más exacto | Rompe `{received, stored, rejected}` |

**Recomendación: A**, con `event_id` PK y `ON CONFLICT (event_id) DO NOTHING`. Mantiene `received = stored + rejected` y la operación es idempotente. El log de `api.telemetry` da el número de filas nuevas (`rowcount`).

### D10. Fallo de la base

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** 503 `storage_unavailable` | Sin código nuevo; el frontend reintenta y la deduplicación absorbe; es honesto | Los beacons no se reintentan: se pierden |
| **B** 200 con todo en `rejected` | Literal del enunciado | Pérdida silenciosa de todo el lote sin reintento |

**Recomendación: A.** «Mientras el envelope sea parseable» habla del formato, no de la disponibilidad de la base. Se dice en la PR.

### D11. Cuerpos inválidos

| Opción | Qué es |
|---|---|
| **A** | La tabla de C6: 422 a lo que no es un lote; 200 con `rejected` solo para los items |
| **B** | 200 `{0,0,0}` con `events: []` y 200 con recorte en más de 50 |

**Recomendación: A.** Mantiene el 1–50 del plan y los tests del stub. El frontend no produce ninguno de los dos casos.

### D12. Dónde se hace la verificación final

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Todo en el efímero; en la demo, migración + recorrido real, con tu confirmación | La captura sale de Supabase, como pide la entrega | Las filas de prueba son **inmutables** y las entradas y salidas cambian el stock de la demo |
| **B** Solo el efímero, y la captura sale de ahí | La demo no cambia | La tabla no queda creada en Supabase |

**Recomendación: A, y el lote mixto de `curl` solo en el efímero:** en la demo dejaría para siempre un `outbound_order_created` falso. Para el JSON de la PR vale el del efímero. El recorrido real en la demo, sí: produce eventos verdaderos. Restaurar el stock después solo con tu confirmación (AGENTS §4).

---

## 5. Plan de F1 (cuando decidas)

Cada paso termina con su validación. Las de `services/api` son las de `AGENTS.md` §4: `unittest` con el venv y `uv run --no-sync python -m pytest` desde `services/api` (o el contenedor de `TESTING.md` §14 si Windows vuelve a bloquear el venv). Nada cambia en `uis/`, Docker ni `requirements.txt`.

### 5.1 Pasos

1. **Tabla y migración.**
   - `modules/telemetry/models.py`: `TelemetryEventRecord` (SQLModel, 8 columnas, 3 índices).
   - `modules/telemetry/migrate.py`, con `--dry-run`: tabla, índices, RLS y `REVOKE`, en una transacción; idempotente. `PRINT_ALLOWED` en `test_architecture.py`.
   - Tests: DDL compilado y sentencias de la migración.
   - **Validación:** suite + §5.3 en el efímero, dos veces. La demo, no.
2. **Colector.**
   - `catalog.py`: `FRONTEND_EVENT_TYPES`. `allowlists.py`: la copia de los 15 eventos.
   - `collector.py`: un paso por evento (§C2) y `store`: un único `insert`.
   - `schemas.py`, por debajo de la línea 66: cuerpo laxo y respuesta de tres contadores.
   - `router.py` y `core/telemetry.py` (la línea de log); `stock_edit.py`/`emitter.py` para D8.
   - **Validación:** suite + el `diff` de C2 + `python scripts/validate_event_schemas.py`.
3. **Tests.** Reescribir las clases `Stub*` de `test_telemetry_events.py` (el comportamiento cambia a propósito) y añadir:
   - lote mixto e invariante; cada rechazo de §C2; C4 (fecha, `NaN`, `\u0000`);
   - `null` en las 6 dimensiones; clave extra fuera de `tags`;
   - duplicados dentro del lote y entre lotes;
   - una sentencia por lote (C13), también ninguna si todo es inválido;
   - token frente a beacon; ±5 min en sus dos lados; throttle;
   - 503 con la base caída; el log sin ids ni `properties`;
   - `allowlists.py` y `FRONTEND_EVENT_TYPES` contra el JSON;
   - eventos reales de los 14 ejemplos del plan guardados con éxito.
   - **Validación:** suite completa sin regresiones.
4. **Documentación.** SPECS Parte H; plan §1.5, §2.4, `:298`, `:370`, §7.3, §8.3 y §8.4 (texto; `1.0.0` no cambia); `services/api/README.md`, `TESTING.md`; `AGENTS.md`; `docs/telemetry/storage-review.md`; `memory-bank` (`progress` y `techContext`).
   - **Validación:** `python scripts/validate_event_schemas.py`.
5. **Verificación.** §5.3 y §5.4, en el efímero. Con tu confirmación explícita, la demo: `--dry-run`, aplicar, segunda ejecución sin cambios, recorrido real.
6. **Cierre.** `git diff main --stat -- uis/` vacío, los pasos de `AGENTS.md` §4 y la PR `feat: telemetry event storage`, con las decisiones de esquema marcadas como nuestras.

### 5.2 Orden de despliegue

Migrar antes de que el código llegue a la base en uso. Con `--reload`, el stack carga el colector en cuanto se cambia de rama: sin la tabla, las peticiones dan 500 y esos eventos se pierden. No daña nada, pero conviene saberlo.

### 5.3 Postgres efímero (Docker Desktop tiene que estar arrancado)

Como en P3 (`capture-review.md` §5.1): `postgres:17.6-alpine3.22`, solo en `127.0.0.1:55433`. **Diferencia:** hay que crear un rol sin superusuario, dueño de la base, y usarlo en `DATABASE_URL`; con el usuario por defecto el `REVOKE` no se nota. La contraseña y el override de Compose, fuera del repo.

```sql
CREATE ROLE nexova_app LOGIN NOSUPERUSER PASSWORD '<generada>';
CREATE DATABASE nexova_test OWNER nexova_app;
```

Tras `migrate`, con esa conexión:

```sql
SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'telemetry_events' ORDER BY ordinal_position;
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'telemetry_events';
SELECT relrowsecurity FROM pg_class WHERE relname = 'telemetry_events';
SELECT privilege_type, has_table_privilege(current_user, 'telemetry_events', privilege_type) FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) AS privilege_type;
UPDATE telemetry_events SET service = 'api';  -- esperado: permission denied
DELETE FROM telemetry_events;                 -- esperado: permission denied
```

### 5.4 Receta de la Fase 3

**Recorrido real** en `localhost:3001`: una Entrada, una Salida y navegar (eventos técnicos), con `TELEMETRY_SUPPLIER_KEY` en la API, porque sin ella no se emite `inbound_order_created`. Después, `curl -X PUT http://localhost:3001/backend/inventory/products/1` (405) para el evento de la API.

```sql
SELECT event_type, timestamp, service, user_id, session_id, schema_version, tags FROM telemetry_events ORDER BY timestamp DESC LIMIT 20;
SELECT service, event_type, count(*) FROM telemetry_events GROUP BY 1, 2 ORDER BY 1, 2;
SELECT event_type, tags ->> 'office' AS office, tags ->> 'currency' AS currency, tags -> 'quantity' AS quantity, tags ? 'product_category' AS has_category, tags ? 'programme_id' AS has_programme, tags ->> 'product_category' AS category FROM telemetry_events WHERE tags ? 'office';
EXPLAIN SELECT count(*) FROM telemetry_events WHERE tags @> '{"office": "valencia"}';
```

Con pocas filas, `EXPLAIN` puede preferir un `Seq Scan`. Para ver el índice, `SET enable_seqscan = off` en esa sesión.

**Lote mixto, solo en el efímero** (validado contra `TelemetryEvent` y el JSON, §1.5). Ids fijos a propósito: repetirlo comprueba la deduplicación. Datos ficticios.

```bash
curl -s -X POST http://localhost:3001/backend/telemetry/events -H 'Content-Type: application/json' --data-binary @- <<'JSON'
{"events": [
  {"eventId": "11111111-1111-4111-8111-111111111101", "timestamp": "2026-11-04T12:00:00.000Z", "sessionId": null, "userId": null, "event_type": "page_viewed", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222201", "properties": {"route_template": "/inventory/products", "previous_route_template": null, "entry": "initial_load"}},
  {"eventId": "11111111-1111-4111-8111-111111111102", "timestamp": "2026-11-04T12:00:00.000Z", "sessionId": "33333333-3333-4333-8333-333333333301", "userId": "44444444-4444-4444-8444-444444444401", "event_type": "outbound_order_created", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222202", "properties": {"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 1, "currency": "EUR", "outbound_order_id": 1, "exit_type": "consumption", "stock_after": 1, "asset_category": "hardware"}},
  {"eventId": "11111111-1111-4111-8111-111111111103", "timestamp": "2026-11-04T12:00:00.000Z", "sessionId": null, "userId": null, "event_type": "page_viewed", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222203", "properties": {"route_template": "/suppliers", "previous_route_template": null, "entry": "initial_load", "email": "leak@example.invalid"}},
  {"eventId": "11111111-1111-4111-8111-111111111104", "timestamp": "2026-11-04T12:00:00.000Z", "sessionId": null, "userId": null, "event_type": "page_viewed", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222204", "properties": {"route_template": "/", "previous_route_template": null, "entry": "initial_load"}, "email": "leak@example.invalid"},
  {"eventId": "11111111-1111-4111-8111-111111111105", "timestamp": "2026-11-04T12:00:00.000Z", "sessionId": null, "userId": null, "event_type": "button_clicked", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222205", "properties": {}},
  {"eventId": "11111111-1111-4111-8111-111111111106", "timestamp": "2026-11-04T12:00:00.000Z", "sessionId": null, "userId": null, "event_type": "direct_stock_edit_rejected", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222206", "properties": {"office": null, "product_id": null, "product_category": null, "programme_id": null, "quantity": null, "currency": null, "attempt_kind": "method_not_allowed", "http_method": "PUT", "route_template": "/inventory/products", "status_code": 405, "authenticated": false, "suppressed_count": 0}},
  {"eventId": "11111111-1111-4111-8111-111111111107", "timestamp": "2026-11-04T12:00:00Z", "sessionId": null, "userId": null, "event_type": "page_viewed", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222207", "properties": {"route_template": "/", "previous_route_template": null, "entry": "initial_load"}},
  {"eventId": "11111111-1111-4111-8111-111111111108", "timestamp": "2026-13-45T99:99:99.000Z", "sessionId": null, "userId": null, "event_type": "page_viewed", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222208", "properties": {"route_template": "/", "previous_route_template": null, "entry": "initial_load"}},
  {"eventId": "11111111-1111-4111-8111-111111111109", "timestamp": "2026-11-04T12:00:00.000Z", "sessionId": null, "userId": null, "event_type": "page_viewed", "schemaVersion": "1.0.0", "requestId": "22222222-2222-4222-8222-222222222209", "properties": {"route_template": "/ruta-inventada", "previous_route_template": null, "entry": "initial_load"}},
  "no-soy-un-objeto"
]}
JSON
```

| # | Caso | Resultado |
|---|---|---|
| 1 | Técnico válido | `stored` |
| 2 | Negocio válido, con dos `null` | `stored`, con las 6 dimensiones en `tags` |
| 3 | Clave extra en `properties` | `stored`, sin `email` |
| 4 | Clave extra en el envelope | `rejected` (modelo) |
| 5 | `event_type` desconocido | `rejected` (modelo) |
| 6 | Emisor API | `rejected` (colector) |
| 7 | `timestamp` sin milisegundos | `rejected` (modelo) |
| 8 | Fecha imposible con patrón correcto | `rejected` (`fromisoformat`) |
| 9 | Valor fuera del enum | `rejected` (allowlist) |
| 10 | Item que no es objeto | `rejected` (modelo) |

**Esperado:** `200 {"received": 10, "stored": 3, "rejected": 7}`. Repetido: la misma respuesta y el mismo `count(*)`. Y:

```sql
SELECT count(*) FROM telemetry_events WHERE event_id::text LIKE '11111111-%';  -- 3
SELECT count(*) FROM telemetry_events WHERE tags ? 'email';                    -- 0
SELECT timestamp, event_type FROM telemetry_events WHERE event_id = '11111111-1111-4111-8111-111111111101';
```

Si el lote se envía más de 5 min después de `12:00:00`, ese `timestamp` será la hora de recepción: comprueba además la regla de ±5 min.

**Cuerpos límite (D11):** los comandos, en [`storage-review.md`](./storage-review.md).

| Body | Respuesta |
|---|---|
| `{"events": []}` | `200 {"received": 0, "stored": 0, "rejected": 0}` |
| 51 items que no son objetos | `200 {"received": 51, "stored": 0, "rejected": 51}` |
| `{}` | 422 |
| `{"events": "x"}` | 422 |
| `{"events": [], "sent_at": "now"}` | 422 |
| `no-es-json` | 422 |

---

## 6. Fuera de alcance o sin verificar

**Sin verificar (F0 no conectó con ninguna base):**

- **El rol real de la API en Supabase.** D4 depende de esto. De solo lectura, cuando quieras:

  ```sql
  SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;
  SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_name = 'assets' ORDER BY 1, 2;
  ```

- **`ON CONFLICT`, `JSONB`, `\u0000`, `rowcount` y `REVOKE` sobre un PostgreSQL real:** en F0 solo están compilados o probados en SQLite; el efímero lo comprueba en F1. Docker Desktop estaba parado.
- **Pydantic en modo estricto:** que un `number` admita enteros y el `uniqueItems` de `fields` se comprueban en F1 con los 14 ejemplos del plan.
- **Latencia del insert por el pooler** dentro de los 5 s del frontend: no medida. Si la base tarda más, hay reintento y la deduplicación lo absorbe.
- **Volumen real:** los 120/min y el cupo anónimo son estimaciones (plan `:2431`).
- **El stack en marcha:** `.env` ya tiene `TELEMETRY_SUPPLIER_KEY` (comprobada su presencia, sin leer el valor), aunque `capture-review.md:148` dice que no. No se ha comprobado que la API en marcha la haya cargado.

**Fuera de este ticket:**

- alertas, canal stream y lote nocturno (C14); agregados y tabla analítica;
- job de retención (D5);
- P1 (`product_category`, `programme_id` siguen en `null`), P2, P5 y P6 completo: los otros 37 eventos de la API;
- `request_id` en la tabla (D1);
- proteger los eventos de negocio contra la falsificación (C15);
- cualquier cambio en `uis/`, en `TelemetryEvent`, en `event-schemas.json` y en `schemaVersion`.

---

## 7. Resumen de lo recomendado

| Decisión | Recomendación |
|---|---|
| D1 Columnas | A: `event_id` PK, `event_type`, `timestamp`, `service`, `user_id`, `session_id`, `schema_version`, `tags`; ids `UUID` |
| D2 `service` | `backoffice` / `api`, puesto por el servidor |
| D3 Creación | Migración explícita, nunca al arrancar |
| D4 Inmutabilidad | RLS + `REVOKE`; trigger si el rol resulta ser superusuario |
| D5 Retención | Fuera, documentada con fecha |
| D6 Allowlist | Clave extra: se descarta. Valor inválido: se rechaza el evento |
| D7 Reglas | Todas, con throttle |
| D8 Eventos de la API | Insert directo tras `emit`, `service='api'` |
| D9 Duplicados | `ON CONFLICT DO NOTHING`; cuentan como `stored` |
| D10 Base caída | 503; el frontend reintenta |
| D11 Cuerpos inválidos | 422 al lote; 200 con `rejected` solo por item |
| D12 Verificación | Efímero; en la demo, solo migración y recorrido real, con confirmación |
