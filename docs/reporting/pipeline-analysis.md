# Pipeline de desempeño de negocio: análisis (F0)

Documento de trabajo del ticket «Data Pipelines · Diseño del pipeline de desempeño de negocio». **F0: análisis y decisiones; no hay código.** El entregable final del ticket es solo `data/pipelines/PIPELINE_DESIGN.md`; este documento prepara sus decisiones.

> **Decidido por el usuario el 2026-11-09:**
>
> - **D1–D14:** como se recomienda abajo (§4 y §7), con tres matices.
> - **D1:** el centinela `_unassigned` vive **solo** en `reporting`. En `PIPELINE_DESIGN.md`, P1 aparece como prerrequisito de negocio explícito: qué falta (catálogo de programas y clasificación de activos), quién lo da (Elena, L&D; sin inventar nombres ni programas) y qué cambia en el reporte cuando exista (solo los eventos nuevos traen programa; la historia sigue en `_unassigned`).
> - **D4:** la ambigüedad «órdenes frente a unidades» queda escrita junto al KPI, con `kits_delivered_units` como propuesta de v2.
> - **D9:** `run_id` y los `CHECK` se marcan como **aditivos** a la DDL del BRIEFING; el nombre de la tabla y sus columnas originales, intactos.
> - **Entrega (D13, D14):** el BRIEFING se versiona con el contenido intacto (el enlace roto a la versión inglesa se anota en su commit, no se edita); `PIPELINE_DESIGN.md` y `progress.md` van en un commit con el mensaje exacto `feat: add business performance pipeline design document`, sin pie de atribución. Sin push hasta que el usuario lea `PIPELINE_DESIGN.md`.
>
> Lo demás sigue tal como se presentó.

- **Rama:** `docs/business-pipeline-design`, desde `main` en `006aa1e` (PR #32; `origin/main` en el mismo commit).
- **BRIEFING:** [`docs/proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md`](../proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md) (versionado en esta rama, D13; antes, sin seguimiento como `docs/diseño-de-un-pipeline-de-desempeño-de-negocio.md`). Manda en KPI, grano, tabla y endpoints. Se cita como «BRIEFING»; los números de línea no cambian.
- **Contrato de telemetría:** [`telemetry-plan.md`](../telemetry/telemetry-plan.md) y [`event-schemas.json`](../telemetry/event-schemas.json), versión `1.0.0`; almacenamiento y reporte en `services/api/SPECS.md` Parte H.
- **Cómo leerlo:** **Verificado** es lo comprobado en el código, en la documentación o ejecutado. **Propuesta** es diseño nuestro.

**Qué se ejecutó en F0, además de leer:**

- **Una consulta de solo lectura en la demo** (§1.9), la autorizada: transacción `READ ONLY`, recuento de los 4 `event_type` del BRIEFING por semana ISO (UTC), `tags->>'office'` y `tags->>'programme_id'`, más el total de filas de la tabla. Ninguna otra clave de `tags`; la URL de la base no se imprimió.
- **Nada instalado:** Prefect no se ha resuelto, descargado ni ejecutado. Todo lo que aquí se dice de Prefect es diseño y está marcado como no verificado (§6).

---

## 1. Estado verificado

### 1.1 Los 4 eventos del BRIEFING en `telemetry_events`

Fuente: `services/api/app/modules/telemetry/allowlists.py:31-118` (copia del JSON comprobada por `tests/test_telemetry_storage.py`). Todas las claves son obligatorias; las de más se quitan antes de guardar (SPECS §45, paso 5).

| `event_type` | KPI del BRIEFING | Claves que guarda en `tags` | Lo que usa el pipeline |
|---|---|---|---|
| `inbound_order_created` | Costo de material | `office`, `product_id`, `product_category`, `programme_id`, `quantity`, `currency`, `inbound_order_id`, `unit_cost`, `supplier_key`, `asset_category` | `office`, `programme_id`, `currency`, `quantity`, `unit_cost`, `inbound_order_id` |
| `outbound_order_created` | Kits entregados | `office`, `product_id`, `product_category`, `programme_id`, `quantity`, `currency`, `outbound_order_id`, `exit_type`, `stock_after`, `asset_category` | `office`, `programme_id`, `currency`, `outbound_order_id` (y `quantity`, según D4) |
| `stock_threshold_triggered` | Frecuencia de escasez | lo mínimo + `outbound_order_id`, `stock_before`, `stock_after`, `min_stock`, `asset_category` | `office`, `programme_id`, `currency`, `outbound_order_id` |
| `kit_cost_variance_detected` | Frecuencia de variación de costo | lo mínimo + `inbound_order_id`, `supplier_key`, `unit_cost`, `reference_unit_cost`, `variance_pct`, `direction`, `threshold_pct`, `reference_window`, `asset_category` | `office`, `programme_id`, `currency`, `inbound_order_id` |

- **Emisor:** los 4 los emite el **frontend** con `track()` desde la respuesta 201 de alta (D1 «A ligera», plan `:74-84`); `uis/backoffice/lib/inventory-telemetry.ts:58-82`.
- **Oficina y moneda:** `office` en minúsculas (`valencia`/`miami`) y el par oficina–moneda lo exige el colector (`office_currency=(("valencia", "EUR"), ("miami", "USD"))`, `allowlists.py:46`). Un evento con `miami` y `EUR` se rechaza: **una fila del agregado nunca puede mezclar monedas si se agrupa por oficina**.
- **Identidad:** los 4 tienen `identity_required=True` (`userId` y `sessionId` no nulos). El pipeline **no los necesita** y no los lee (C11).

### 1.2 `unit_cost`, `currency` y `supplier_key` hoy

| Campo | Cómo se calcula | Dónde |
|---|---|---|
| `unit_cost` | Lo escribe el operador en la Entrada; **obligatorio** en `InboundOrderCreate` (`unit_cost: UnitCost`), `NUMERIC(12,2)`, `> 0`. Solo es `NULL` en las filas anteriores a P3 y en las del seed | `inventory/schemas.py:106`, `inventory/models.py:107-109`, SPECS §39 |
| `currency` | La pone la API desde la oficina: `OFFICE_CURRENCY[Office(payload.office)]`; nunca el cliente | `inventory/service.py:202`, `inventory/vocabulary.py:48` |
| `supplier_key` | HMAC-SHA256 del proveedor normalizado con `TELEMETRY_SUPPLIER_KEY`; `None` sin clave | `telemetry/emitter.py:50-54`, `inventory/service.py:276` |

- **Consecuencia para el KPI de coste:** el frontend **no emite** `inbound_order_created` si `unit_cost`, `currency` o `supplier_key` son `null` (`inventory-telemetry.ts:76`). Sin `TELEMETRY_SUPPLIER_KEY` en la API, **ninguna entrada llega a la telemetría** y el coste sale a 0 sin error (C3, C14).
- **`total_cost` no existe** en el evento; sí `unit_cost` y `quantity`. El BRIEFING pide «un campo `unit_cost` o `total_cost`» (BRIEFING `:45`): con `unit_cost` basta, **sin extensión de esquema** (C3).

### 1.3 `product_category` y `programme_id`

- **En el modelo:** `Asset` tiene `id`, `name`, `sku`, `category`, `office` y nada más (`inventory/models.py:73-86`). **No existen** ni `product_category` ni `programme_id`: son P1, pendiente (plan `:84`).
- **En los eventos:** van **siempre en `null`**: `product_category: null, programme_id: null` (`inventory-telemetry.ts:45-46`), con el comentario «van en `null` hasta que exista la clasificación de activos (P1; el esquema lo admite, D1-a)» (`:12-13`).
- **Catálogo de programas:** no existe en ninguna fuente. Solo hay ejemplos: `ventas-b2b` y `liderazgo-basico` (BRIEFING de telemetría `docs/proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md:31`; plan D2, `:60`) y `b2b-sales` en el ejemplo de respuesta de este BRIEFING (`:109`). El `README.md` raíz no da ninguno.

### 1.4 `asset_entries` y `asset_exits` como fuentes alternativas

Esquema en SPECS §39 y `inventory/models.py:89-138`.

| Tabla | Columnas útiles | ¿Se actualiza? |
|---|---|---|
| `asset_entries` | `id`, `asset_id`, `quantity`, `office` (`Valencia`/`Miami`), `created_at` (UTC), `user_uuid`, `unit_cost` (nullable), `currency` (nullable), `supplier` (texto libre) | **Solo inserción.** No hay ruta de edición ni de borrado (SPECS §40, «Fuera de alcance: edición o borrado»). Escriben la API y el seed |
| `asset_exits` | `id`, `asset_id`, `quantity`, `exit_type`, `assigned_to` (PII), `office`, `created_at`, `user_uuid` | **Solo inserción**, igual |

- **Excepción administrativa:** la restauración de la demo hace `TRUNCATE assets, asset_entries, asset_exits RESTART IDENTITY CASCADE` (`AGENTS.md:81`), solo con confirmación. Tras ella, **los ids de orden vuelven a empezar** (C7).
- **No tienen** `programme_id`, `product_category`, escasez ni variación: la escasez y la variación se calculan en la API en el momento de la orden y solo quedan en la telemetría.

### 1.5 Deduplicación existente

- **Por `event_id`:** clave primaria de `telemetry_events` y `INSERT … ON CONFLICT (event_id) DO NOTHING` (`telemetry/collector.py:201-206`; SPECS §47). Un reintento del frontend con el mismo `eventId` no duplica.
- **No hay deduplicación por clave natural** (`inbound_order_id`/`outbound_order_id`): dos eventos con distinto `eventId` y la misma orden se guardan los dos.

### 1.6 Regla de ±5 min del `timestamp`

`TIMESTAMP_MAX_DRIFT = timedelta(minutes=5)` (`collector.py:41`); `return moment if abs(moment - received_at) <= TIMESTAMP_MAX_DRIFT else received_at` (`collector.py:153`). **Consecuencia:** el `timestamp` guardado nunca es anterior a la recepción en más de 5 min. Un evento no puede aparecer «en una semana ya cerrada» más de 5 min después del cierre: si llega más tarde, se le pone la hora de recepción y cae en la semana siguiente (C6).

### 1.7 Retención (plan §8.3)

- **90 días** para los eventos en bruto; **fecha límite 2027-02-03** (plan `:2427`).
- «**Condición: agregar antes de borrar.** Los agregados aún no existen» (plan `:2428`).
- La limpieza es de administración, fuera de la API (`telemetry/migrate.py:19-20`).
- Los agregados sin identificadores personales se conservan **sin límite** (plan §8.3).

### 1.8 Qué existe ya

| Pieza | Estado |
|---|---|
| Prefect | **No existe** en el repo: ni en `pyproject.toml`, `uv.lock`, `requirements.txt` ni en ningún `.py` o `.md` (búsqueda de «prefect») |
| Esquema `reporting` | **No existe en el código** (ninguna referencia a `reporting.`). En la demo **no se ha comprobado**: la consulta autorizada solo leía `telemetry_events` |
| `data/pipelines/` | Solo `README.md` y `README.es.md` (plantilla) |
| `data/process/` | Solo `README.md` y `README.es.md` (plantilla) |
| `data/README.md` | **No existe** (el ticket pide leerlo); hay `README` en `data/raw`, `data/pipelines`, `data/process` y `data/eval` |
| `services/reporting/` | No existe. `services/telemetry/` es una librería de la API, no un servicio (`services/telemetry/README.md:5`) |
| Agregados de telemetría | No existen (plan `:2381`, «consolidar los batch… y crear los agregados», pendiente) |
| Rol `admin` | Existe: `require_admin` → 403 (`app/auth/dependencies.py:71-77`) |

### 1.9 Datos reales de la demo (consulta de solo lectura, 2026-11-09)

`telemetry_events` tiene **66 filas** en total. De los 4 tipos del BRIEFING:

| `event_type` | `week_start` (lunes, UTC) | `office` | `programme_id` | Filas |
|---|---|---|---|---|
| `inbound_order_created` | 2026-11-02 | `valencia` | `null` | 1 |
| `outbound_order_created` | 2026-11-02 | `miami` | `null` | 1 |
| `stock_threshold_triggered` | 2026-11-02 | `miami` | `null` | 1 |
| `kit_cost_variance_detected` | — | — | — | 0 |

- **Una sola semana** con actividad de negocio; **el 100 % con `programme_id` nulo**. Con la tabla del BRIEFING tal cual (`programme_id text not null`), hoy **no se podría cargar ni una fila** sin decidir C1.
- `kit_cost_variance_detected` = 0: necesita 4 entradas con coste del mismo par activo–proveedor (plan §8.4, «La variación de coste necesita historial»).

---

## 2. Conflictos

### C1. `programme_id`: obligatorio en el grano, siempre nulo en la fuente

- **BRIEFING `:62`:** «una fila por `office` por `programme_id` por semana ISO».
- **BRIEFING `:81`:** `programme_id text not null,`; **`:89`:** `unique (office, programme_id, week_start)`.
- **Plan `:59` (D1):** «D1-a: `null` para lo que no es formación ni incorporación; el schema admite `null` y nunca un cuarto valor. D1-b: en este ticket no se clasifica ningún activo». (D1-a habla de `product_category`; para `programme_id`, D2 dice «validado solo por el patrón» y la ficha: «`null` si el activo no tiene programa».)
- **Plan `:84`:** «**P1** (clasificación) y **P2** (mínimo por activo) quedan para más adelante. Hasta entonces, `product_category` y `programme_id` van en `null`».
- **Plan `:2441`:** «Hasta que se clasifiquen, `product_category` y `programme_id` son `null` y las métricas por programa salen vacías | … Hasta entonces, el agregado usa `asset_category`».
- **`.agents/rules/nexova-context.md:19`:** «Si un dato no aparece en ninguno de esos archivos, **no se asume ni se rellena por inferencia**».
- **Demo (§1.9):** 3 de 3 eventos con `programme_id` nulo.

**Opciones y qué dice cada fuente:**

| Opción | Qué implica | Encaje |
|---|---|---|
| **A** Implementar P1 en este hito | Columnas en `assets`, migración aditiva, `AssetCreate`/`AssetRead`, emisión en el frontend y **clasificar los 6 activos** | Fuera de un ticket de solo diseño (no se escribe código). Además, **no hay catálogo**: los 6 activos del seed son hardware, periféricos y material de oficina, más «Cuaderno de formación en liderazgo» (`seed.py:49-54`); asignarle `liderazgo-basico` sería inferencia. Y los eventos ya guardados **siguen con `null`** (tabla inmutable) |
| **B** Centinela documentado en la capa de reporting | `COALESCE(programme_id, '<centinela>')` en la transformación. Los eventos no cambian | Respeta «nunca un cuarto valor» en los **eventos**; el centinela vive solo en `reporting`. No inventa un programa: dice «sin programa asignado». El reporte no sale vacío y los totales cuadran |
| **C** Excluir las filas sin programa | `WHERE programme_id IS NOT NULL` | Literal con el grano, pero **el reporte sale vacío** hoy y hasta P1, y se pierde dinero y kits de los totales por oficina |
| **D** `programme_id` nullable + `UNIQUE NULLS NOT DISTINCT` | Cambia la DDL del BRIEFING | Contradice `not null` del BRIEFING; necesita PostgreSQL ≥ 15 (la versión de Supabase de la demo **no está verificada**) |
| **E** Enriquecer desde `assets` al transformar (cuando exista P1) | `product_id` → `assets.programme_id` actual | Reescribe la historia con la clasificación de hoy; hoy no aporta nada (la columna no existe) |

**Elección del centinela (si B):** un valor que **no cumpla el patrón** `^[a-z0-9]+(-[a-z0-9]+)*$` no puede chocar nunca con un programa real. `_unassigned` (con guion bajo) lo garantiza; `unassigned` o `sin-programa` sí cumplen el patrón y podrían chocar con un programa futuro. Ver D1.

### C2. Fuente: `telemetry_events` frente a `asset_entries`/`asset_exits`

- **BRIEFING `:47`:** «Tu fuente es `telemetry_events`, filtrada a las métricas obligatorias».
- **BRIEFING `:56`:** «No necesitas ningún evento fuera de esta lista para la v1».
- **Plan `:2445` (C15 de storage):** «`POST /telemetry/events` es público… cualquiera puede inyectar un `outbound_order_created` falso, que queda en una tabla inmutable y alimenta los informes».
- **Plan `:2444`:** «lo pendiente se pierde si fallan los 3 reintentos o si el beacon no sale al cerrar».
- **Plan `:2451`:** «Seeds y cambios directos | No emiten eventos».

| KPI | Desde la telemetría | Desde el inventario |
|---|---|---|
| Costo de material | Σ `unit_cost × quantity` de `inbound_order_created` | Σ `unit_cost × quantity` de `asset_entries` con coste (la verdad contable) |
| Kits entregados | `outbound_order_created` | `asset_exits` (la verdad) |
| Escasez | `stock_threshold_triggered` (**solo aquí**) | Habría que reconstruir el cruce con el stock acumulado: duplica la regla D4 de la API |
| Variación de costo | `kit_cost_variance_detected` (**solo aquí**) | Habría que repetir la media de las 3 anteriores por proveedor normalizado: duplica P10 |
| `programme_id` | `null` | No existe |

**Riesgos de la telemetría:** falsificable (C15), pérdida por beacon (plan §8.4), entradas sin `supplier_key` no emitidas (§1.2), seeds sin eventos. **Autoridad:** para coste y kits, el inventario es la verdad; para escasez y variación, la telemetría es la única fuente. Ver D2.

### C3. Coste: `total_material_cost = Σ unit_cost × quantity`

- **BRIEFING `:65`:** «suma de los costos de `inbound_order_created` de la semana, en la moneda local de la oficina».
- **BRIEFING `:45`:** «un campo `unit_cost` o `total_cost` en `properties`… Si tu esquema… aún no lo tiene, agrégalo ahora».

**Hechos:** el evento ya trae `unit_cost` (2 decimales) y `quantity` (entero), ambos obligatorios: **no hace falta ampliar el esquema** y la versión `1.0.0` no cambia. «Costo» de una entrada = `unit_cost × quantity` (sumar solo `unit_cost` daría el precio de un kit, no el gasto). Cálculo en `numeric`, nunca en `float`: `(tags->>'unit_cost')::numeric * (tags->>'quantity')::integer`. Las entradas anteriores a P3 y las del seed **no tienen evento** (el frontend no emite sin coste): no suman, y no se puede saber cuánto se dejó fuera sin leer `asset_entries` (C2, D2).

### C4. `kits_delivered_count`: ¿órdenes o unidades?

- **BRIEFING `:66`:** «`kits_delivered_count` — Kits entregados: conteo de `outbound_order_created` de la semana».
- **BRIEFING `:35`:** «Cuántos kits o certificados se entregaron realmente».
- **Plan M10 (`:52`):** el tipo de destinatario no está modelado; `exit_type` ∈ `allocation`/`consumption`.

Una salida de 12 unidades es 1 evento y 12 kits. El texto de §4 (la fórmula) dice «conteo»; el de §2 (el KPI) se lee mejor como unidades. Sobre `exit_type`: el BRIEFING no distingue; el modelo no sabe si una salida fue «a un cliente, candidato, consultor o agente» (M10). Ver D4.

### C5. Moneda y valores de `office`

- **BRIEFING `:63`:** «`office` (`valencia`/`miami`)»; **`:69`:** «`EUR` o `USD`, según la oficina. **No conviertas monedas**»; **`:127`:** «Nunca mezcles monedas en una sola fila agregada».
- **`inventory/vocabulary.py:31-32`:** `VALENCIA = "Valencia"`, `MIAMI = "Miami"` (dominio con mayúscula).
- **`allowlists.py:34`:** `"office": {"enum": ["valencia", "miami"]}` (eventos en minúscula, D6 del plan).

**Hechos:** la fuente del BRIEFING ya trae minúsculas, que es lo que pide la tabla. Solo hace falta `lower()` si se leen las tablas del inventario (D2). Como el colector impone el par oficina–moneda, agrupar por `office` ya separa monedas; aun así, la transformación debe **fallar** (no mezclar) si una celda tuviera dos monedas. La respuesta del endpoint presenta las dos oficinas lado a lado, cada una con su `currency`, y **nunca un total entre oficinas**.

### C6. Semana ISO en UTC, cadencia y frescura

- **BRIEFING `:62`:** «`week_start` = el lunes de esa semana, UTC».
- **BRIEFING `:24`:** «fresco la mañana del lunes».
- **`memory-bank/projectbrief.md:7`:** sede en Valencia (Laura, CEO); **`README.md:31`:** su informe semanal hoy es manual.

**Hechos:** `date_trunc('week', "timestamp" AT TIME ZONE 'UTC')::date` da el lunes ISO (comprobado en la consulta de la demo). La semana cierra el lunes 00:00 UTC = 01:00 en Valencia en invierno (CET) y 02:00 en verano (CEST); = domingo 19:00 / 20:00 en Miami. Consecuencias:

- un evento de Miami del domingo por la tarde-noche cuenta en la semana siguiente; uno de Valencia del lunes a las 00:30 locales, en la anterior. Es lo que pide el BRIEFING (UTC) y se documenta;
- por la regla de ±5 min (§1.6), a las 00:05 UTC del lunes ya no puede entrar ningún evento de la semana cerrada;
- «mañana del lunes» sin zona: lo natural es la de Laura, `Europe/Madrid`. Un cron `0 6 * * 1` en `Europe/Madrid` (05:00 o 04:00 UTC) deja ≥ 4 h de margen sobre el cierre y respeta el cambio de hora.

### C7. Eventos tardíos, recálculo y deduplicación por orden

- **BRIEFING `:93`:** «El constraint `unique (office, programme_id, week_start)` es en el que debe apoyarse tu estrategia de idempotencia (upsert)».

**Hechos y riesgos:**

- La fuente es **inmutable** (`REVOKE UPDATE, DELETE, TRUNCATE`, SPECS `:908`): recalcular una semana con los mismos eventos da siempre el mismo resultado. **No hace falta CDC ni marca de agua incremental.**
- Un evento perdido que el navegador reenvía mucho después **no es tardío**: el colector le pone la hora de recepción (§1.6) y cae en otra semana. No se puede «corregir» esa semana.
- **El upsert solo sobrescribe:** si una celda (oficina, programa, semana) deja de tener eventos al recalcular (por ejemplo, tras cambiar la regla del centinela o enriquecer con P1), su fila vieja **se queda**. Hace falta borrar en la misma transacción las filas de las semanas recalculadas que no estén en el resultado nuevo.
- **Rastro:** con `computed_at` solo se sabe *cuándo*; la tabla del BRIEFING no tiene `run_id`. Sin él no se puede enlazar una fila con la corrida que la escribió (C11).
- **Duplicados con distinto `eventId`:** hoy el frontend emite cada obligatorio una vez por 201 (en un manejador, no en un efecto), así que no deberían existir. Contarlos por `outbound_order_id`/`inbound_order_id` distinto protegería de reenvíos y de inyecciones repetidas, **pero** el `TRUNCATE … RESTART IDENTITY` de la demo (§1.4) reutiliza ids: dos órdenes distintas podrían compartir id. Ver D6.
- **Retención:** recalcular una semana cuyos eventos ya se purgaron la **sobrescribiría con ceros**. El recálculo debe negarse para semanas fuera de la retención (C15).

### C8. Ubicación del código y contexto de build

- **BRIEFING `:99`:** «un módulo **nuevo**, `services/reporting/`, separado de `services/telemetry/`».
- **Enunciado:** «nada de ETL en services/».
- **`docker-compose.yml:15`:** `context: ./services`; **`:16-18`:** `additional_contexts: packages: ./packages`.
- **`services/Dockerfile:50-53`:** `COPY api/app ./app` y `COPY telemetry ./telemetry` (D1 del reporte).
- **`services/README.md:5`:** «Each subfolder inside `services/` must correspond to **one specific service**».
- **`data/pipelines/README.md:5`:** «Each subfolder or file under `data/pipelines/` should represent **one pipeline**».

**Hechos:** `data/` está **fuera** del contexto de build de la API: hoy la imagen no podría importar nada de `data/pipelines/`. Lo que deben compartir `services/reporting/` (que lee) y `data/pipelines/` (que escribe) es poco: el nombre del esquema y de las tablas, las columnas, los estados de una corrida y el centinela de C1. Hay un precedente de código compartido que entra en la imagen sin instalarse: `packages/` como contexto adicional y `PYTHONPATH` (`Dockerfile:16-22, 35`), con `nexova_shared` (solo librería estándar). Comparación con `services/telemetry/` (D1 del reporte): allí el código vivía donde se ejecutaba; aquí **hay dos procesos** (la API y el orquestador), así que copiar `data/pipelines/` en la imagen de la API solo tendría sentido si la API ejecutase el flow (C9). Ver D7.

### C9. Prefect: dependencia, dónde corre y cómo lo dispara la API

- **`AGENTS.md` §3:** «No añadir dependencias nuevas a ningún subproyecto sin autorización explícita».
- **SPECS `:831`:** «uvicorn arranca con `--workers 1`»; la caché y el throttle viven en memoria.
- **Compose:** la API corre con `--reload` y un bind mount (`docker-compose.yml:32-37`): un cambio de código reinicia el proceso (C16 del reporte).
- **Enunciado, Fase 4:** blocks con las credenciales de Supabase.

**Hechos:** los blocks de Prefect se guardan en la base de un servidor de Prefect (o en Prefect Cloud): pedir blocks implica un servidor. Ejecutar el flow dentro de la API (BackgroundTasks) lo ataría a un proceso que se reinicia con cada cambio de código y que comparte su único worker con las peticiones; además metería Prefect y `data/pipelines/` en la imagen de la API. Disparar un deployment por la API REST de Prefect (`POST /api/deployments/{id}/create_flow_run`) se puede hacer con `urllib` de la librería estándar, como Resend (AUTH-03): la API no dependería de Prefect. **Nada de esto está verificado** (§6). La caché de la API (`ResponseCache`) no la puede invalidar otro proceso. Ver D8 y D12.

### C10. Esquema `reporting` y DDL del BRIEFING frente a la convención

- **BRIEFING `:79`:** `id uuid primary key default gen_random_uuid()`; **`:88`:** `computed_at timestamptz not null default now()`.
- **Convención del repo:** `created_at` «lo pone la aplicación en UTC» (`inventory/models.py:16`); tablas creadas con una **migración explícita** idempotente con `--dry-run`, nunca al arrancar contra la demo (`telemetry/migrate.py:1-25`); RLS sin políticas + `REVOKE` a `anon`, `authenticated`, `service_role` (SPECS `:908`).

**Hechos:** `gen_random_uuid()` es nativa desde PostgreSQL 13 (sin `pgcrypto`). `now()` devuelve la hora de **inicio de la transacción**: todas las filas de una carga tendrían el mismo `computed_at`, que es lo deseable. La DDL del BRIEFING no tiene `CHECK` (oficina, moneda, par coherente, contadores ≥ 0, `week_start` en lunes). La Data API de Supabase solo expone los esquemas configurados (por defecto `public`); un esquema nuevo no se expone salvo que se añada, pero los privilegios de los roles de Supabase sobre objetos nuevos dependen de los `DEFAULT PRIVILEGES` del proyecto: **no verificado** en la demo. Hoy la API conecta como dueña (con `BYPASSRLS`): un rol separado para el pipeline sería otro cambio en Supabase. Ver D9.

### C11. Log de ejecución (`pipeline_runs`)

- **BRIEFING `:120`:** «`GET /reporting/pipeline-runs/latest` — estado y metadata de la última corrida… (puedes reutilizar este mismo patrón para cualquier pipeline futuro)».
- **Enunciado, Fase 3:** log con ≥ 5 campos con nombre, tipo y justificación de auditoría.

**Hechos:** el estado de Prefect vive en la base del servidor de Prefect, no en Supabase; si el endpoint lo leyera de ahí, dependería de que ese servidor esté arriba. Un log propio en `reporting.pipeline_runs` hace al endpoint independiente de Prefect y deja el rastro junto a los datos. «Cualquier pipeline futuro» pide una columna `pipeline_name`. Nunca debe guardar el mensaje de una excepción (puede llevar la URL de la base), solo su clase, como `telemetry/migrate.py:23-24`. Ver D10.

### C12. Concurrencia: cron y disparo manual a la vez

- **SPECS `:670`:** Supabase por el **Transaction pooler** (puerto 6543).

**Hechos:** con el pooler de transacciones, un `pg_advisory_lock` de **sesión** no es fiable (cada transacción puede ir por una conexión distinta); `pg_advisory_xact_lock` (de transacción) sí. Dos corridas a la vez sobre las mismas semanas escribirían los mismos valores (fuente inmutable), pero la segunda podría borrar filas que la primera acaba de cargar si usan reglas distintas, y el log tendría dos `running`. Un índice único parcial `(pipeline_name) WHERE status = 'running'` deja una sola corrida activa sin depender de la conexión; una corrida que muere sin cerrar dejaría la fila bloqueada para siempre si no hay un plazo. Ver D11.

### C13. Endpoints: autenticación, formato y errores

- **BRIEFING `:101`:** «acepta un `week_start` opcional (por defecto, la semana calculada más reciente)».
- **SPECS `:917`:** `/telemetry/report` usa «Bearer, cualquier rol, en la propia ruta».
- **API:** validación con 422 `validation_error`, salvo `/api/incidents` (400 propio); `require_admin` → 403.

**Preguntas abiertas:** ¿puede cualquier usuario disparar una corrida? ¿qué pasa con un `week_start` que no es lunes? ¿«la semana calculada más reciente» es la mayor `week_start` de la tabla (que no ve las semanas calculadas sin actividad) o la última semana cubierta por una corrida `completed`? ¿404 o `entries: []`? ¿caché? Ver D12.

### C14. Silencio: dos ceros que no significan lo mismo

No estaba en la lista. Una celda a 0 puede ser «no hubo actividad» o «la telemetría no llegó»: API sin `TELEMETRY_SUPPLIER_KEY` (§1.2), colector caído (503, el frontend descarta tras 3 reintentos), migración sin aplicar (500), beacon perdido. El reporte técnico ya resolvió algo parecido rellenando días a 0 («un día a 0 es un colector caído», `report-analysis.md`, cabecera). Ver pregunta 4 (§3) y D2.

### C15. Retención de 90 días: agregar antes de borrar

- **Plan `:2427-2428`:** fecha límite **2027-02-03** y «agregar antes de borrar».

**Hechos:** el primer evento de negocio es de la semana del 2026-11-02 (§1.9). El pipeline debe estar en marcha, y haber cubierto todas las semanas desde esa, **antes** de la primera purga. Y la purga (de administración) debería comprobar en `pipeline_runs` que cada semana a borrar está cubierta por una corrida `completed`. A la inversa, el pipeline no debe recalcular semanas cuyos eventos ya no existen (C7).

### C16. Vocabulario

| Concepto | Nombre real | Variante que aparece |
|---|---|---|
| Programa | `programme_id` (slug, patrón `^[a-z0-9]+(-[a-z0-9]+)*$`) | Ejemplos: `ventas-b2b`, `liderazgo-basico` (BRIEFING de telemetría `:31`) y `b2b-sales` (este BRIEFING `:109`) |
| Oficina | `office` = `valencia`/`miami` en eventos y en `reporting`; `Valencia`/`Miami` en el inventario | — |
| Activo | `product_id` = `Asset.id` (entero); `asset_category` ∈ `hardware`/`peripherals`/`office_supplies`/`training_materials` | `Product` en los BRIEFING |
| Órdenes | `inbound_order_id` = `AssetEntry.id`, `outbound_order_id` = `AssetExit.id` | `InboundOrder`/`OutboundOrder` |
| Salida | `exit_type` ∈ `allocation`/`consumption` | «entrega» en el BRIEFING |
| Proveedor | `supplier_key` (HMAC) | Nunca el nombre |

**Propuesta:** en el diseño, los ejemplos usan `ventas-b2b` (el del BRIEFING de telemetría y del plan D2), marcados como ejemplo, y se anota que el ejemplo de respuesta del BRIEFING del pipeline usa `b2b-sales`. Ninguno es un programa real (no hay catálogo, C1).

### C17. Versionado del BRIEFING

- **`.agents/rules/nexova-context.md:11-17`:** todo dato de negocio debe estar en una fuente versionada (`docs/` incluido).
- **Precedente:** el de telemetría se versionó como `docs/proyectos-de-telemetria-plan-captura-almacenamiento-reporte.md`, nombre derivado de su subtítulo («Proyectos de Telemetría (Plan · Captura · Almacenamiento · Reporte)»).
- **En F0:** `docs/diseño-de-un-pipeline-de-desempeño-de-negocio.md` estaba **sin seguimiento** y con `ñ` en el nombre. Enlaza a `./nexova-pipeline-BRIEFING.md` (`:7`), que **no existe**. *(Resuelto con D13: versionado sin cambios como `docs/proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md`; el enlace roto sigue y está anotado en el commit.)*

Los nombres de Laura, Elena y Patricia y la frecuencia semanal ya están versionados (`README.md`); el grano, los KPI y la tabla, no. Ver D13.

### C18. Entrega: commit con mensaje fijo frente a ramas y PR

- **Enunciado:** commit `feat: add business performance pipeline design document` (y push).
- **Repo:** ramas y PR; mensajes `docs(...)` para documentación; `AGENTS.md` §4 (cinco pasos antes de commitear).

Las dos cosas son compatibles si el commit con el mensaje exacto existe en la rama y llega a `main` **sin squash** (merge commit, como las PR #31 y #32). Ver D14.

### C19. Alcance de «material de formación» (no estaba en la lista)

- **BRIEFING `:19`:** «costo de material, kits entregados…» de formación; **plan M0 (`:42`):** el inventario real es de hardware y material de IT y operaciones.

Con `product_category` siempre nulo, filtrar «solo formación» dejaría el reporte vacío o solo con `NXV-TRN-001`. El BRIEFING (`:47`) filtra **solo por `event_type`**: el v1 suma todo el material del inventario. El portátil de Miami cuenta como «material». Se documenta como limitación hasta P1. Ver D3.

---

## 3. Borrador de respuestas a las preguntas del enunciado

Los ejemplos del enunciado son genéricos. Correspondencias: `stock_waste_registered` → no existe en nuestro catálogo (lo más cercano, `stock_threshold_triggered`); `POST /telemetry` → nuestro colector es `POST /telemetry/events`; `Idempotency-Key` → no existe, la clave de idempotencia es el `eventId`; `localStorage` → no se usa como buffer de eventos (solo guarda el token, `lib/auth-token.ts`).

### Idempotencia

1. **Duplicados.** Tres capas: (a) en la ingesta, `event_id` es la PK y el insert lleva `ON CONFLICT (event_id) DO NOTHING` (`collector.py:201-206`): un reintento del mismo lote no duplica; (b) en la transformación, **Propuesta D6**: se cuenta por `outbound_order_id`/`inbound_order_id` distinto dentro de la semana y se registra cuántos se colapsaron (`duplicates_collapsed`); (c) en la carga, el `unique (office, programme_id, week_start)` del BRIEFING y `INSERT … ON CONFLICT … DO UPDATE`: una segunda corrida sobrescribe, nunca añade. `Idempotency-Key` no aplica: el colector no lee cabeceras de idempotencia; el `eventId` hace ese papel.
2. **Reintento tras un fallo en la carga.** La carga es **una transacción** por corrida: `pg_advisory_xact_lock` → borrar las filas huérfanas de las semanas recalculadas → upsert de las filas nuevas → commit. Si falla, PostgreSQL deshace todo: la tabla queda **exactamente como antes de la corrida** (los valores de la corrida anterior). El log se cierra en otra transacción con `status = 'failed'`, `phase = 'load'` y la clase del error. La segunda corrida relee la fuente (inmutable), produce las mismas filas y las escribe; `computed_at` y `run_id` pasan a ser los suyos. Si el proceso muere **después** del commit y antes de cerrar el log, la fila queda en `running`; la siguiente corrida la marca `failed` por plazo vencido (D11) y vuelve a escribir los mismos valores sin duplicar nada. Prefect reintenta las tareas de E/S (extracción y carga) ante errores transitorios; la transformación es pura y no se reintenta.
3. **Eventos tardíos.** Acotados por el colector: un `timestamp` nunca es anterior a la recepción en más de 5 min (`collector.py:153`); lo que llega más tarde se fecha en la recepción y cae en la semana en que llegó. La corrida del lunes a las 06:00 (`Europe/Madrid`) empieza ≥ 4 h después del cierre (C6). Aun así, cada corrida programada recalcula la última semana cerrada **y la anterior** (D5), para cubrir una corrida fallida o un cambio de reglas; el backfill cubre cualquier semana dentro de la retención.

### Observabilidad

4. **Silencio frente a ausencia.** Una celda a 0 no basta. Cada corrida guarda en `pipeline_runs`, por semana, el **total de eventos técnicos** de `telemetry_events` (filas de los 11 tipos no de negocio, sin leer sus `tags`) y, si se decide D2-A con conciliación, las órdenes de `asset_entries`/`asset_exits`. Eventos técnicos > 0 y de negocio = 0 → no hubo actividad; técnicos = 0 → silencio (colector o frontend caído); órdenes > eventos → pérdida. `GET /telemetry/report` ya muestra los días a 0 (`events_per_day`).
5. **Trazabilidad.** Fila del reporte → `run_id` → `pipeline_runs` (quién o qué la disparó, parámetros, semanas, filas leídas y escritas, versión del esquema) → eventos de esa semana, oficina y programa → `inbound_order_id`/`outbound_order_id` → `asset_entries`/`asset_exits` con `user_uuid` (con control de acceso, plan D9). El pipeline nunca copia `user_id`, `session_id` ni `supplier_key`.
6. **Crecimiento frente a pérdida.** Una bajada de eventos de negocio con los técnicos estables y las órdenes del inventario también a la baja es menos actividad; con las órdenes estables, es pérdida. La proporción eventos/órdenes por semana (conciliación) es la señal; los rechazos del colector solo están en el log `api.telemetry` (no en la base), así que no entran en el pipeline.

### Recuperabilidad

7. **Caída de la base.** Supabase caído: el colector responde 503 `storage_unavailable` y el frontend reintenta 3 veces y descarta; la API de reporting responde 503. El pipeline falla en la extracción tras sus reintentos y queda `Failed` en Prefect; **tampoco puede escribir su log** (misma base), así que ese fallo solo consta en Prefect. La siguiente corrida (programada o manual) recalcula las dos últimas semanas y lo recupera; para huecos más largos, el backfill.
8. **Buffer en el frontend.** No hay buffer persistente: `lib/telemetry.ts` mantiene una cola **en memoria** (10 s / 20 eventos), 3 reintentos con backoff y `sendBeacon` al ocultar la pestaña (`telemetry.ts:15, 71`). `localStorage` no aplica (riesgo aceptado, plan `:2444`). El pipeline no puede recuperar lo perdido; lo hace **visible** con la conciliación (pregunta 4). La alternativa documentada en el plan es que la API emita también esos 4 eventos.
9. **Reintento de transmisión.** El frontend reenvía el lote con los **mismos** `eventId`; el colector cuenta como `stored` los que ya estaban, así que un reintento da la misma respuesta (SPECS §45) y no duplica. Un 503 provoca reintento; un 422 (cuerpo mal formado) no. El reintento del pipeline es el de las tareas de Prefect y, a nivel de corrida, volver a ejecutar el flow (idempotente).

### Transversal

10. **Corridas concurrentes.** Una sola corrida activa por pipeline: índice único parcial `(pipeline_name) WHERE status = 'running'` en `pipeline_runs` (la base es la autoridad, sirve para el cron y para el disparo manual), más `pg_advisory_xact_lock` en la transacción de carga (válido con el Transaction pooler) y el límite de concurrencia 1 del deployment en Prefect. `POST /reporting/pipeline-runs` con una corrida en marcha → 409. Una fila `running` con más de un plazo (p. ej. 30 min) se cierra como `failed` antes de empezar otra.

---

## 4. Decisiones

### D1. `programme_id` (principal)

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Implementar P1 en este hito | El grano se cumple con datos reales | Código en un ticket de solo diseño; sin catálogo, habría que inventar programas; los eventos ya guardados siguen en `null` |
| **B** Centinela `_unassigned` en `reporting` | Reporte no vacío, totales completos, DDL del BRIEFING intacta, eventos sin tocar; no cumple el patrón slug, así que no choca nunca con un programa real | El reporte dice «sin programa» en todas las filas hasta P1 |
| **B'** Centinela que cumple el patrón (`unassigned`, `sin-programa`) | Más legible | Puede chocar con un programa futuro |
| **C** Excluir filas sin programa | Literal con el grano | Reporte vacío hoy |
| **D** `programme_id` nullable + `NULLS NOT DISTINCT` | Honesto (`null`) | Cambia la DDL del BRIEFING; PostgreSQL ≥ 15 sin verificar |

**Recomendación: B** (`_unassigned`). Es la única que respeta a la vez la DDL del BRIEFING (`not null`), el plan (los eventos siguen en `null`; el centinela no es un cuarto valor de ningún evento) y la regla de no inventar. El endpoint lo devuelve tal cual y el diseño lo explica. **P1 queda como prerrequisito de negocio** (el catálogo lo debe dar Elena), fuera de este ticket; cuando exista, solo los eventos nuevos traerán programa (la historia sigue en `_unassigned`, porque la tabla es inmutable).

### D2. Fuente de datos

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** `telemetry_events` para los 4 KPI + conciliación de solo lectura con `asset_entries`/`asset_exits` (conteos por semana y oficina, guardados en `pipeline_runs`, sin cambiar los KPI) | Literal con el BRIEFING; la pérdida y la falsificación se hacen visibles | Los KPI pueden quedarse cortos (pérdida) o inflados (falsificación) |
| **B** Híbrida: coste y kits del inventario; escasez y variación de la telemetría | Coste y kits exactos | Se aparta del BRIEFING; dos fuentes con relojes distintos; sin `programme_id` en ninguna |
| **C** Solo telemetría, sin conciliación | Lo más simple | Silencio y pérdida invisibles |

**Recomendación: A.** El BRIEFING manda en la fuente y la evaluación mira la consistencia con él; la conciliación responde las preguntas de observabilidad sin cambiar ningún número. Solo cuenta las entradas **con coste** (las otras nunca emiten) y las salidas.

### D3. Qué material entra

**Recomendación: todos los eventos de los 4 tipos, sin filtrar por categoría** (BRIEFING `:47` filtra solo por `event_type`). Cuando exista P1, filtrar por `product_category` sería un cambio de definición del KPI, con recálculo y nota en el diseño. Alternativa: solo `asset_category = 'training_materials'` (hoy, un activo).

### D4. `kits_delivered_count`

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Conteo de órdenes (`outbound_order_created`), ambos `exit_type` | Literal con la fórmula del BRIEFING (`:66`) | 1 orden de 12 kits cuenta 1 |
| **B** Σ `quantity` | Literal con el KPI («cuántos kits») | Se aparta de la fórmula |
| **C** A en `kits_delivered_count` + columna aditiva `kits_delivered_units` | Las dos lecturas | Amplía la DDL del BRIEFING |

**Recomendación: A**, documentando la ambigüedad y proponiendo C como v2 si Elena lo pide. `allocation` y `consumption` cuentan igual: el BRIEFING no distingue y el destinatario no está modelado (M10).

### D5. Ventana de recálculo y cadencia

**Recomendación:** cron `0 6 * * 1`, zona `Europe/Madrid`. Cada corrida programada recalcula la **última semana cerrada y la anterior**; la manual, por defecto la última cerrada (o el `week_start` pedido); nunca la semana en curso. Backfill: un rango de semanas, cada una dentro de la retención (D11 de guarda). Alternativa: solo la última semana (más barato, pero una corrida fallida deja un hueco hasta el backfill).

### D6. Deduplicación por orden

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Solo `event_id` (lo que ya hay) | Sin supuestos | Un evento reenviado con otro `eventId` cuenta dos veces |
| **B** Además, por `inbound_order_id`/`outbound_order_id` distinto **dentro de la semana y oficina**, con `duplicates_collapsed` en el log | Protege de reenvíos e inyecciones repetidas, y lo deja a la vista | Tras un `TRUNCATE … RESTART IDENTITY` a mitad de semana, dos órdenes reales con el mismo id contarían una |

**Recomendación: B.** El `TRUNCATE` de la demo es una operación de administración con confirmación; el diseño lo documenta y el contador lo delata.

### D7. Ubicación del código y código compartido

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** ETL en `data/pipelines/business_performance/` (flow, tasks, migración del esquema `reporting`); `services/reporting/` como librería de la API (router + lecturas + disparo), copiada junto a `app` como `services/telemetry`; lo compartido (nombres de esquema, tablas, columnas, estados, centinela) en `nexova_shared.reporting`, solo librería estándar, que ya entra en las dos imágenes por `packages/` | Sin duplicar; la API no importa `data/`; mismo mecanismo que hoy (`additional_contexts` + `PYTHONPATH`) | `nexova_shared` crece con algo que no es del gestor de incidencias |
| **B** Igual, pero el contrato en un paquete nuevo `packages/reporting/` | Separación más limpia | Otro paquete, otra fila de validación |
| **C** La API importa `data/pipelines/` (nuevo contexto adicional `pipelines`) | Un solo proceso | Lleva ETL y Prefect a la imagen de la API |

**Recomendación: A.** «Nada de ETL en `services/`» se comprueba con un test (AST) en `services/api/tests/`: `services/reporting/` no importa `prefect`, `pandas` ni `business_performance`, y no escribe en `reporting.weekly_office_program_performance`. `data/process/README.md` documenta la tabla como el artefacto que produce el pipeline (sin archivos de datos en git). `PIPELINE_DESIGN.md` va en la raíz de `data/pipelines/` (ruta del BRIEFING) y el código futuro, en su subcarpeta.

### D8. Dónde corre Prefect

| Opción | Ventaja | Riesgo |
|---|---|---|
| **A** Dos contenedores nuevos en Compose, bajo un perfil `pipelines` (`docker compose --profile pipelines up`): `prefect-server` y `pipeline-worker` (`flow.serve` con los deployments programado y manual). La API dispara por la API REST de Prefect con `urllib` | Blocks, estados y UI de Prefect reales; la API sin Prefect ni ETL; el arranque por defecto no cambia | Dos servicios más; Prefect solo en la imagen del worker (dependencia nueva, a autorizar en el ticket de implementación) |
| **B** En el proceso de la API (BackgroundTasks, modo efímero de Prefect) | Sin contenedores nuevos | `--reload` y `--workers 1`: el flow muere con cada cambio de código y comparte el único worker; Prefect en la imagen de la API |
| **C** Prefect Cloud | Sin servidor propio | Servicio externo y cuenta; credenciales de la demo fuera |
| **D** Sin Prefect (cron del sistema) | Simple | No cumple la Fase 4 |

**Recomendación: A.** Blocks: un `Secret` de Prefect con la URL de la base del pipeline (sin colecciones extra como `prefect-sqlalchemy`). Solo diseño: la versión y el comportamiento exacto de `serve` y de la API REST se verifican en el ticket de implementación (§6).

### D9. DDL del esquema `reporting`

**Recomendación:**

- **La tabla del BRIEFING literal** (nombre, columnas, `gen_random_uuid()`, `default now()`, `unique`), más:
  - **aditivo:** `run_id uuid not null references reporting.pipeline_runs(run_id)` (rastro, C7);
  - **`CHECK`:** `office` en `valencia`/`miami`, `currency` en `EUR`/`USD`, par coherente, contadores y coste ≥ 0, `extract(isodow from week_start) = 1`.
- **`computed_at`:** el pipeline no lo envía; el `default now()` da el mismo instante a toda la carga. En el upsert, `computed_at = now()` explícito en el `DO UPDATE` (el default no se aplica en una actualización).
- **Migración:** `python -m business_performance.migrate [--dry-run]`, patrón de `telemetry/migrate.py`: `CREATE SCHEMA IF NOT EXISTS reporting`, tablas e índices compilados del modelo, RLS sin políticas, `REVOKE ALL` sobre el esquema y las tablas a `PUBLIC`, `anon`, `authenticated` y `service_role`; idempotente, en una transacción, nunca al arrancar; **en la demo solo con la confirmación del usuario**. No se añade `reporting` a los esquemas expuestos de la Data API.
- **Roles:** v1 con el rol actual (dueño), como el inventario y la telemetría; dos roles separados (pipeline: `SELECT` en `telemetry_events` y escritura en `reporting`; API: `SELECT` en `reporting`) quedan como mejora documentada, porque crearlos es un cambio en la demo.

Alternativa: ids y `computed_at` puestos por la aplicación (convención del repo). Se aparta de la DDL evaluada.

### D10. Log de ejecución: `reporting.pipeline_runs`

**Recomendación** (nombre, tipo y justificación de auditoría; el diseño lo presenta como tabla):

| Campo | Tipo | Por qué |
|---|---|---|
| `run_id` | `uuid` PK | Enlaza cada fila del reporte con su corrida |
| `pipeline_name` | `text` not null | Reutilizable por pipelines futuros (BRIEFING `:120`) |
| `trigger` | `text`, `CHECK` `schedule`/`manual`/`backfill` | Quién o qué lo disparó |
| `requested_by` | `uuid` null | `id` del usuario del `POST` (seudónimo, como `user_uuid`); `null` en el cron |
| `prefect_flow_run_id` | `uuid` null | Enlace con el estado y los logs de Prefect |
| `status` | `text`, `CHECK` `running`/`completed`/`failed` | Lo que devuelve `GET /reporting/pipeline-runs/latest` |
| `phase` | `text`, `CHECK` `extract`/`transform`/`load`/`done` | Checkpoint: en qué fase falló |
| `week_from`, `week_to` | `date` not null | Qué semanas recalculó |
| `started_at`, `finished_at` | `timestamptz` | Duración y detección de corridas colgadas |
| `source_rows_read` | `integer` | Eventos leídos (silencio frente a ausencia) |
| `rows_rejected` | `integer` | Eventos con `tags` inesperados (no debería pasar tras la allowlist) |
| `duplicates_collapsed` | `integer` | D6 |
| `rows_upserted`, `rows_deleted` | `integer` | Qué cambió en la tabla |
| `quality` | `jsonb` | Por semana y oficina: eventos técnicos y, con D2-A, órdenes del inventario |
| `error_class` | `text` null | Solo la clase de la excepción, nunca el mensaje |
| `schema_version` | `text` | `1.0.0`: con qué contrato de eventos se calculó |

Índice único parcial `(pipeline_name) WHERE status = 'running'` (D11).

### D11. Concurrencia

**Recomendación:** el índice único parcial como autoridad + `pg_advisory_xact_lock` en la carga + límite 1 del deployment; una fila `running` con más de 30 min se cierra como `failed` (`error_class = 'Abandoned'`) antes de abrir otra. **Guarda de retención:** la corrida se niega (y falla con su clase) si alguna semana pedida empieza antes de `now() - 84 días` (90 menos una semana de margen).

### D12. Endpoints en `services/reporting/`

**Recomendación:**

| Ruta | Auth | Qué llama | Respuestas |
|---|---|---|---|
| `GET /reporting/weekly-office-program-performance?week_start=YYYY-MM-DD` | Bearer, cualquier rol | Lee `reporting.weekly_office_program_performance` (filas que escribe la task `load_weekly_rows`) | 200 con `entries` (ordenadas por `office`, `programme_id`); sin `week_start`, la última semana cubierta por una corrida `completed`; semana cubierta sin actividad → 200 `entries: []`; semana nunca calculada → 404 `week_not_computed`; no lunes o fecha inválida → 422; base caída → 503 |
| `GET /reporting/pipeline-runs/latest` | Bearer, cualquier rol | Lee `reporting.pipeline_runs` (lo escriben las tasks `start_run`/`finish_run`) | 200; sin corridas → 404 |
| `POST /reporting/pipeline-runs` | Bearer, **solo `admin`** (`require_admin`, 403) | Crea un flow run del deployment manual del flow `weekly_office_program_performance` por la API REST de Prefect | 202 con `prefect_flow_run_id`; corrida en marcha → 409; Prefect no disponible → 503 |

- **Sin caché:** la tabla es pequeña (oficinas × programas por semana) y otro proceso (el worker) la cambia, así que la API no podría invalidar `ResponseCache`. Alternativa: TTL de 60 s sin invalidación, como `/telemetry/report`.
- `total_material_cost` sale como número JSON (como `unit_cost`), sin redondear en la API.

### D13. Versionar el BRIEFING

**Recomendación:** sí, sin `ñ`, siguiendo el precedente: `docs/proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md` (de su subtítulo, `:3`), en un commit aparte y sin cambiar el contenido salvo el enlace roto a la versión inglesa (o dejándolo y anotándolo). Los otros dos BRIEFING sin seguimiento (`docs/telemetria-*.md`) no son de este ticket.

### D14. Entrega

**Recomendación:** en `docs/business-pipeline-design`, (1) el BRIEFING versionado (`docs: …`), (2) este análisis con las decisiones (`docs(reporting): …`), (3) `data/pipelines/PIPELINE_DESIGN.md` + `progress.md` con el mensaje **exacto** `feat: add business performance pipeline design document`; push de la rama y PR a `main` con **merge commit** (sin squash), para que el commit evaluado exista tal cual en `main`. Push y PR solo con tu OK.

---

## 5. Índice propuesto de `data/pipelines/PIPELINE_DESIGN.md`

| § | Sección | Criterio que cubre |
|---|---|---|
| 0 | Cabecera: propósito, fuentes (BRIEFING versionado, plan, SPECS), decisiones D1–D14 resumidas, qué es diseño y qué no está verificado | Trazabilidad |
| **Fase 1** | | |
| 1.1 | Eventos capturados hoy: los 15 de la tabla y los 4 del BRIEFING con sus `tags` reales | Estado actual |
| 1.2 | Dónde se guardan: `telemetry_events` (columnas, inmutable, dedup por `event_id`, ±5 min, retención 90 días) | Estado actual |
| 1.3 | Qué responde `GET /telemetry/report` (5 métricas técnicas, ninguna de negocio) | Estado actual |
| 1.4 | La brecha: nadie agrega por oficina, programa y semana; `programme_id` nulo; la cifra real de la demo | Brecha de negocio |
| **Fase 2** | | |
| 2.1 | Propósito en **una** frase (entregable, 4 KPI, métricas obligatorias) | Propósito |
| 2.2 | Extracción: tabla origen, columnas y claves de `tags` leídas (y las que no), forma de cada registro extraído, filtro por `event_type` y ventana, cadencia (cron, zona) | Formato de extracción |
| 2.3 | Diagrama Mermaid: `telemetry_events` (+ `asset_entries`/`asset_exits` para conciliar) → tasks de Prefect → `reporting.weekly_office_program_performance` y `reporting.pipeline_runs` → `services/reporting` | Diagrama E-T-L |
| 2.4 | Transformación: reglas por KPI (fórmulas, D3, D4, D6), semana ISO UTC, centinela, monedas sin mezclar | Lógica |
| 2.5 | Registros que se actualizan y duplicados: fuente inmutable, inventario solo inserción, upsert + borrado de huérfanas, `TRUNCATE` de la demo | Estrategia de actualización |
| 2.6 | Tabla de destino: DDL del BRIEFING + aditivos (D9), migración y permisos | Tabla de destino |
| 2.7 | Endpoints en `services/reporting/` (resumen; detalle en Fase 5) | Endpoints |
| **Fase 3** | | |
| 3.1 | Idempotencia: la segunda corrida tras un fallo en la carga, paso a paso | Idempotencia |
| 3.2 | Log de ejecución `reporting.pipeline_runs`: campos, tipo y justificación (D10) | Log ≥ 5 campos |
| 3.3 | Concurrencia y guarda de retención (D11) | Robustez |
| **Fase 4** | | |
| 4.1 | Flow `weekly_office_program_performance` y tasks: `start_run`, `resolve_weeks`, `extract_business_events`, `extract_reconciliation_counts`, `transform_weekly_rows`, `load_weekly_rows`, `finish_run` (retries, qué recibe y devuelve cada una) | Flow + ≥ 3 tasks |
| 4.2 | States (Scheduled, Pending, Running, Completed, Failed, Crashed, Cancelled) y su reflejo en `pipeline_runs.status` | States |
| 4.3 | Blocks: `Secret` con la URL de la base; nada en el código ni en el repo | Blocks |
| 4.4 | Deployments (programado y manual), dónde corren (D8), flow de backfill opcional como subflows por semana | Despliegue |
| **Fase 5** | | |
| 5.1 | Los 3 endpoints: contrato, auth, errores, qué lee o qué flow dispara cada uno; nada de ETL en `services/` (y cómo se comprueba) | Endpoints |
| 6 | Respuestas a las 10 preguntas (§3 de este documento, revisadas) | Preguntas |
| 7 | Riesgos, limitaciones (P1, pérdida, falsificación, M0) y fuera de alcance | Honestidad |
| 8 | Glosario de vocabulario real (C16) | Consistencia de dominio |

---

## 6. Fuera de alcance o sin verificar

- **Fuera de este ticket (solo diseño):** cualquier código, migración, dependencia (Prefect), cambio en `uis/`, en `services/telemetry/analysis.py` o en `GET /telemetry/report`, y cualquier escritura en `telemetry_events` o en Supabase. P1 (clasificación y catálogo de programas) y P2 (mínimo por activo).
- **Sin verificar:**
  - Prefect: versión, `flow.serve` con un servidor propio, límites de concurrencia del deployment, `Cron` con zona horaria y la ruta REST para crear un flow run. Todo es diseño hasta el ticket de implementación;
  - si existe ya un esquema `reporting` en la demo, la versión de PostgreSQL de Supabase y los `DEFAULT PRIVILEGES` / esquemas expuestos de su Data API;
  - si la API de la demo tiene hoy `TELEMETRY_SUPPLIER_KEY` (el único `inbound_order_created` de la demo indica que la tenía al registrarlo);
  - el volumen real: con 3 eventos de negocio en una semana, cualquier cifra de rendimiento es estimación.
- **No hay interfaz** para Laura y Elena en este ticket: el BRIEFING pide la tabla y los endpoints. Una página del backoffice sería otro ticket.
- **`data/README.md` no existe**, aunque el ticket lo cita.

---

## 7. Resumen de lo recomendado

| Decisión | Recomendación |
|---|---|
| D1 `programme_id` | B: centinela `_unassigned` solo en `reporting`; P1 como prerrequisito de negocio |
| D2 Fuente | A: `telemetry_events` + conciliación de solo lectura con el inventario |
| D3 Material | Todos los eventos de los 4 tipos, sin filtro de categoría |
| D4 Kits | A: conteo de órdenes, `allocation` y `consumption` |
| D5 Cadencia | Lunes 06:00 `Europe/Madrid`; última semana cerrada + la anterior |
| D6 Duplicados | B: además por id de orden dentro de la semana, con contador |
| D7 Código | A: ETL en `data/pipelines/business_performance/`, lectura en `services/reporting/`, contrato en `nexova_shared.reporting` |
| D8 Prefect | A: servidor + worker en un perfil de Compose; la API dispara por REST sin depender de Prefect |
| D9 DDL | BRIEFING literal + `run_id` + `CHECK`; migración explícita, RLS y `REVOKE` |
| D10 Log | `reporting.pipeline_runs` con 17 campos |
| D11 Concurrencia | Índice único parcial + `pg_advisory_xact_lock` + plazo de 30 min + guarda de retención |
| D12 Endpoints | GET con cualquier rol, POST solo `admin`; 404 solo si la semana nunca se calculó; sin caché |
| D13 BRIEFING | Versionarlo como `docs/proyectos-de-data-pipeline-diseno-implementacion-subflows-tests.md` |
| D14 Entrega | Commit con el mensaje exacto en la rama; PR con merge commit |
