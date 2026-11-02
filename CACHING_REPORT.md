# Informe de caching y optimización

> Ticket de caching y optimización (rama `feature/caching-optimisation`, 2026-10-31).
>
> - **Medición inicial, tabla de los 32 endpoints y decisiones D1–D11:** [`docs/caching-analysis.md`](./docs/caching-analysis.md), F0. El usuario tomó las decisiones el 2026-10-31.
> - **Contrato de la caché:** [`services/api/SPECS.md`](./services/api/SPECS.md) Parte G.
>
> Todas las cifras son de este repositorio, medidas con bases de prueba, nunca con la demo (§6). Los milisegundos son p50 / p95 en cliente, desde la red de Docker, salvo que se diga otra cosa.

## Resumen

| Qué | Dónde | Antes | Después |
|---|---|---|---|
| Caché de `GET /inventory/products` (60 s) | `services/api` | ~400 ms contra Supabase y 15 ms con volumen en local | **2,4–3,0 ms** por acierto |
| Caché de `GET /api/incidents/summary` (30 s) | `services/api` | 37 / 72 ms con 5096 incidencias | **2,6 / 3,3 ms** |
| Caché de `GET /api/incidents` con filtros (30 s) | `services/api` | 34–88 ms | **3,2–4,1 ms** con filtros; **13,4 ms** sin filtros (2 MB) |
| `React.memo` + `useMemo` en `SupplierTable` | `uis/backoffice` | 162 / 112 ms de re-render al abrir / cerrar el alta | **0 ms** |
| Lazy loading del formulario de alta y de las métricas de `/incidents` | `uis/backoffice` | en el chunk de su ruta | 2,1 KB y 1,6 KB comprimidos, que se piden solo al usarlos |

## 1. Decisiones en el frontend (`uis/backoffice`)

### 1.1 Lazy loading (D6)

Medido sobre el build de producción (`next build`). Tamaños con gzip -9 sobre los chunks; la petición, en la pestaña Network.

| Componente | Por qué diferirlo | Antes | Después |
|---|---|---|---|
| `SupplierCreateForm` (`/suppliers`) | Solo existe con `formOpen`: es lo que el usuario abre para dar de alta un proveedor. Leer el directorio no lo usa | dentro del chunk de la ruta (8 012 B) | chunk propio de **2 110 B**, pedido al abrir; chunk de la ruta, 8 173 B |
| `IncidentResults` (`/incidents`): `TotalsCards`, `InvalidBreakdownTable`, las dos `DistributionTable` y `SatisfactionPanel` | Solo existen después de analizar un CSV. Entrar en la página para subir el archivo no los usa | dentro del chunk de la ruta (5 892 B) | un único chunk de **1 617 B**, pedido al elegir el archivo; chunk de la ruta, 6 121 B |

**Razonamiento honesto: bytes frente a flujo.**

- **Bytes:** con componentes de este tamaño, `next/dynamic` **no** reduce el JS inicial. El chunk de cada ruta crece unos 0,2 KB, y el runtime de la carga diferida añade 1,2 KB al chunk compartido (medido en F0, `docs/caching-analysis.md` §5.1).
- **Experimento de F0:** con los 5 componentes de resultados por separado, eran 5 chunks y 3,7 KB. Agruparlos en `IncidentResults` los deja en uno de 1,6 KB.
- **Lo que se gana es el flujo:** la carga inicial deja de incluir código que la mayoría de las visitas no usa. Si esos componentes crecen (validaciones, gráficas), crecerán fuera del chunk de la ruta.

**Sin coste visible ni CLS:**

- **Precarga por intención:** el chunk del formulario se pide al acercar el puntero o el foco a «Nuevo proveedor»; el de las métricas, al elegir el archivo, antes de pulsar «Analizar». Medido: el chunk de 1,6 KB llega al elegir el CSV.
- **Hueco reservado:** el `loading` mide lo mismo que el contenido real en el build de producción.

  | Contenido | 375 px | Desde `sm` | Desde `lg` |
  |---|---|---|---|
  | Formulario | 961 px | 574–590 px (se reserva el menor) | — |
  | Métricas | 1850 px | — | 1249 px |

- **Verificado con un clic sintético**, que no dispara la precarga y obliga a mostrar el hueco:
  - el encabezado del directorio queda en la misma posición con el hueco y con el formulario (991 px a 1280 y 1458 px a 375);
  - el de los resultados, igual (577 y 693 px).
- **El único layout shift que queda** en `/incidents` (0,004–0,011) viene de la sección de subida, que crece 36 px al empezar el análisis. Ya ocurría antes de este cambio.
- **Una regla estática nueva** en `tests/production-source.test.mjs` impide volver a importarlos de forma estática.

### 1.2 `useMemo` + `React.memo` en la tabla de proveedores (D7-A)

**El problema medido (F0, `<Profiler>`):** al abrir o cerrar el formulario de alta, la vista se re-renderiza y arrastra `SupplierTable` entera, con 415 filas, sin ningún cambio de proveedores.

- Las props de la tabla son las mismas referencias:
  - `suppliers` y `rows` del reducer;
  - `today`, fijado al montar;
  - los callbacks, con `useCallback`.
- Dentro de cada render, lo caro que se repite es crear un `Intl.NumberFormat` por fila: 46–135 ms para 415 filas, frente a 1,1 ms reutilizando uno.

**Qué se aplicó:**

- **`React.memo(SupplierTable)`:** con las mismas props, la tabla no se vuelve a pintar.
- **`useMemo`** de las filas derivadas (renovación con `renewalInfo`, tarifa formateada y fecha de actualización) con dependencias **`[suppliers, today]`**, exactamente lo que usa el cálculo. Cuando la tabla sí se re-renderiza solo porque cambia `rows` (guardando una tarifa o un estado), las filas derivadas no se recalculan.

**Beneficio medido.** Build de producción con perfilado y `<Profiler>` temporal sin commitear; 3 pasadas con 415 proveedores, mediana:

| Interacción | Antes | Después |
|---|---|---|
| Abrir el formulario de alta | 162 ms (80–182) | **0 ms** (la tabla no se re-renderiza) |
| Cerrarlo | 112 ms (61–305) | **0 ms** |
| Guardar una tarifa: render de «guardando» | 150 ms (59–184) | 23–33 ms, y el cálculo de filas (20–29 ms) **no** se ejecuta |
| Guardar una tarifa: render tras el éxito | 154 ms (94–417) | 49–63 ms; el cálculo sí se ejecuta, porque cambia el proveedor |
| Montaje | 146–409 ms | 152–500 ms (sin cambio esperado: hay que pintar las 415 filas) |

- **Ruido:** las cifras varían mucho entre pasadas, porque el panel del navegador a veces está en segundo plano. Las de abrir y cerrar no dependen de ese ruido: pasan de un render completo a ninguno.
- **Medición del `useMemo` aparte:** el cálculo de las filas derivadas se cronometró dentro de su callback. Cuesta **20–29 ms**: se ejecuta 1 vez al montar y 1 por cada guardado correcto, y ninguna en los renders de «guardando», ni al abrir o cerrar el formulario.

### 1.3 Lo que se descartó en el frontend, con su medida

- **`useMemo` en `activeCount` y `upcomingCount`** (`supplier-directory-view.tsx`), el candidato inicial del ticket:
  - cuestan **0,1–0,4 ms** y **1,6 ms** (8,7 ms la primera vez) con 415 proveedores;
  - medido con `performance.now()`, **no se recalculan al escribir en el formulario de alta**: el estado del formulario es local a `SupplierCreateForm` y la vista padre no se re-renderiza al teclear (0 recálculos en 21 pulsaciones);
  - memoizarlos sería la «memoización prematura» del brief.
- **`useMemo` en las tablas de incidencias y órdenes:** su coste es el número de filas sin paginar (3,35 s para 5096 incidencias y **25,5 s** para 30 393 órdenes), no un cálculo repetido. Ni `useMemo` ni la caché lo arreglan (§5).

## 2. Decisiones en el backend (`services/api`)

**Cómo funciona la caché** (D2 y D3):

- Un diccionario en memoria con TTL (`app/core/cache.py`, sin dependencias), una instancia por app en `app.state`.
- Espacios de nombres que una escritura limpia enteros, y como máximo 64 entradas por espacio.
- Se consulta **dentro del handler, después de la autenticación**.
- Guarda los modelos de respuesta, que siguen pasando por `response_model`.
- Un contador de generación impide que una lectura que empezó antes de una invalidación guarde su valor viejo después.

**Cómo se midió:** en la tabla, «fallo» es la primera petición tras una invalidación real (una escritura en la base de pruebas; mediana de 10), y «acierto», las peticiones siguientes (mediana de 50, p95 cuando hay 50 o más).

### 2.1 `GET /inventory/products` y `GET /inventory/products/{id}` — 60 s

| | Volumen local (126 activos, 30 393 órdenes) | Red real (Supabase de la demo, solo GET) |
|---|---|---|
| Antes (F0, sin caché) | 14,6 / 15,5 ms · detalle 10,5 / 11,0 | **397,8 / 468,8 ms** · detalle 399,7 / 495,0 |
| Fallo (después) | 19,5 ms tras una entrada · detalle 14,8 | 447–800 ms tras caducar el TTL; 728–2072 ms con el proceso recién arrancado |
| Acierto (después) | **3,0 / 4,1 ms** · detalle 3,0 / 3,9 | **2,4–2,8 / 3,5–3,7 ms** · detalle 2,7–3,0 / 3,6–3,8 |

- **Coste:**
  - **Red:** contra Supabase cada lectura paga unos 400 ms fijos, porque el motor usa `NullPool` y abre una conexión nueva al pooler en cada petición. Con 6 activos cuesta lo mismo que el detalle: es la red, no el volumen.
  - **Volumen:** en local, el agregado del stock sobre 30 k órdenes cuesta unos 15 ms.
  - **Red de hoy:** iba más lenta que en F0. El control sin caché, `GET /inventory/orders`, subió de 452 a 1147 ms, y por eso los fallos son mayores que el «antes».
  - **Acierto:** no abre ninguna conexión, porque la sesión solo conecta al primer `execute`.
- **Frecuencia:**
  - la lista la piden la página de Activos y los formularios de entrada y salida (para el selector);
  - el detalle, el formulario de salida («Stock actual» del activo elegido);
  - las dos se vuelven a pedir tras cada orden.
- **TTL de 60 s:** el stock solo cambia con una orden o un activo nuevo (en la demo hay 10 órdenes; el volumen real de Nexova no está documentado), y esas escrituras pasan por la API, que invalida al momento. Los 60 s solo acotan lo que no pasa por ella (§3.1).
- **Clave:** `"products"` y `("product", id)` en el espacio `inventory`. Sin el usuario, porque la respuesta es la misma para todos (§4).
- **Invalidación:** `POST /inventory/products`, `POST /inventory/orders/inbound` y `POST /inventory/orders/outbound` limpian todo el espacio, **solo si confirman**.
  - Un 400 (stock insuficiente u oficina distinta), 404, 409 o 422 no lo toca; los tests lo fijan uno a uno.
  - **Comprobado en la medición:** tras cada entrada, el GET siguiente fue un fallo (19,5 ms) y los 5 siguientes, aciertos (3,2 ms).

### 2.2 `GET /api/incidents/summary` — 30 s

| | Volumen (5096 incidencias, TinyDB en un volumen de Docker) |
|---|---|
| Antes (F0) | 36,8 / 71,5 ms (69,5 / 130,5 con bind mount, como la demo) |
| Fallo (después) | 44,8 ms tras crear una incidencia |
| Acierto (después) | **2,6 / 3,3 ms** |

- **Coste:** abre y valida el archivo TinyDB entero (3,6 MB) para devolver 410 bytes de recuentos.
- **Frecuencia:** al entrar en `/incident-manager` y **tras cada cambio de estado**, porque el tablero recarga el resumen.
- **TTL de 30 s:** se explica en §3.2.
- **Clave:** `"summary"` en el espacio `incidents`.
- **Invalidación:** `POST /api/incidents` y `PATCH /api/incidents/{id}/status`, solo si escriben. Una transición no permitida (400), un cuerpo no válido o un 404 no limpian nada.

### 2.3 `GET /api/incidents` (listado con filtros) — 30 s

| | Sin filtros (5096 filas, 2 MB) | `?status=open` (672) | `?branch=miami_office&category=sla_breach` (96) |
|---|---|---|---|
| Antes (F0, volumen) | 87,5 / 117,4 ms | 39,1 / 49,7 | 34,3 / 36,8 |
| Fallo (después) | 107,3 ms | 47,8 | 48,5 (con el proceso recién arrancado) |
| Acierto (después) | **13,4 / 16,7 ms** | **4,1 / 5,8** | **3,2 / 3,8** |

- **Coste:** igual que el resumen, más la serialización. El acierto sin filtros sigue en 13 ms porque `response_model` serializa 2 MB en cada petición: se eligió guardar modelos y no bytes (D3-A).
- **Frecuencia:** al entrar en `/incident-manager` y en cada cambio de filtro, y a menudo se vuelve a las mismas combinaciones.
- **TTL:** 30 s, como el resumen.
- **Clave:** `("list", IncidentFilters)`, con los filtros **ya normalizados** por `validate_filters` de `nexova_shared`.
  - El orden de los parámetros no crea entradas distintas.
  - Un filtro no válido (también uno vacío) responde 400 **antes** de llegar a la caché y no ocupa ninguna entrada.
  - Hay como máximo 900 combinaciones posibles y 64 entradas por espacio, porque el listado completo pesa megas.
- **Invalidación:** la del resumen; las dos comparten el espacio `incidents`.

## 3. Intercambios conocidos

### 3.1 Frescura frente a rendimiento: el inventario a 60 s

- **Qué puede quedar viejo:** el stock que muestran la lista de activos y el formulario de salida, **hasta 60 s**, y solo si el cambio llega por fuera de la API (un seed, SQL directo en Supabase, otra instancia). Cualquier orden registrada en el backoffice invalida al momento: el backoffice vuelve a leer el stock justo después y ya lo ve actualizado (lo fijan los tests).
- **Por qué es aceptable:** es un inventario de equipos y materiales de oficina. Lo que cambia el stock son órdenes registradas por el personal de operaciones, no un flujo continuo, y las que entran por el backoffice invalidan al momento. A cambio, cada lectura se ahorra unos 400 ms de red en el despliegue real.
- **Por qué no hay riesgo de sobreventa:** `POST /inventory/orders/outbound` comprueba la regla del stock **en la base, con `FOR UPDATE`**, nunca contra la caché.
  - Un stock desactualizado en pantalla, como mucho, provoca el 400 `insufficient_stock` con su mensaje literal, que el formulario ya muestra bajo «Cantidad».
  - Hay un test que lo fija: con la caché diciendo 5 y la base 1, una salida de 2 da 400 `Available: 1, requested: 2`.

### 3.2 Las incidencias a 30 s: por qué más corto

- **Herramienta compartida:** el gestor centraliza las incidencias de todas las sedes (central, Valencia, Miami y remoto), y una incidencia que registra otra persona debería verse pronto.
- **El seed escribe directo:** `scripts/seed_incidents.py` escribe en TinyDB sin pasar por la API.
- **Por qué no menos:** con 30 s el resumen sigue sirviéndose desde la caché en las visitas repetidas de una misma sesión de trabajo, y las escrituras propias invalidan al momento. Bajarlo mucho más dejaría la caché casi sin aciertos.

### 3.3 Un solo proceso (`--workers 1`)

- **Hoy:** la caché vive en la memoria del proceso. Con un solo worker, que ya exige TinyDB, es única y coherente, y la invalidación vale para todo el tráfico.
- **Con más workers o réplicas:** cada proceso tendría su copia y una escritura solo limpiaría la del que la recibe; los demás servirían datos viejos hasta el TTL. El TTL acota el daño, pero la regla queda escrita en `SPECS.md` §43: **subir workers obliga a revisar la caché**. Una caché compartida, como Redis, necesitaría autorización y un servicio nuevo.

### 3.4 Los seeds no invalidan

- **Qué escriben y dónde:** `seed-inventory` y `scripts/seed_volume.py` escriben en PostgreSQL; `scripts/seed_incidents.py`, en TinyDB. Ninguno pasa por la API.
- **Consecuencia:** con la API en marcha, sus datos tardan hasta el TTL en verse. Lo documenta el README de `services/api`, que también da la salida inmediata: `docker compose restart api`.
- **Lo fija un test:** el seed no cambia el resumen hasta que pasa el TTL; después, se ve.

## 4. Qué no se cacheó y por qué

| Endpoint | Por qué no |
|---|---|
| `GET /suppliers` (y `/suppliers/{id}`) | Cuesta 3–8 ms con 415 proveedores (8,1 / 10,1 ms medido en F1, sin caché): no hay nada que ganar. Además, el CONTEXT pide que un cambio de tarifa «se vea reflejado inmediatamente», y los filtros cambian con cada clic |
| `GET /inventory/orders` | El coste es el volumen sin paginar: 30 393 órdenes, 8,5 MB, 660–860 ms en la API y **25,5 s** de render en el navegador. Una caché ahorraría menos de 1 s de 26 y guardaría 8,5 MB por entrada. Lo que hace falta es paginación (§5) |
| `GET /auth/me` y `GET /profiles/me` | Se piden en cada carga de página, pero son **personales** y cuestan 1,5–2,6 ms. Necesitarían una clave por usuario y una invalidación en `PUT /profiles/me` y `PUT /users/{id}`: no compensa el riesgo |
| `GET /users`, `GET /users/{id}` | Datos de usuarios (sensibles) y sin ninguna pantalla que los use |
| `POST /api/incidents/analyze` | Es una escritura con un cuerpo distinto cada vez, y el CSV lleva emails de clientes |
| `GET /api/incidents/results/export` | Ya sale de memoria (`LastResultStore`, 4–7 ms) |
| Todas las escrituras | No se cachean: invalidan |

**Regla general:** **nada personal, de sesión o sensible se guarda en una clave compartida.**

- Las cuatro rutas cacheadas devuelven lo mismo a cualquier usuario autenticado. Se midió en F0: respuestas idénticas entre una cuenta `user` y una `admin`.
- La caché vive después de `get_current_user`: sin token o con uno no válido sigue habiendo 401 (hay tests de las cuatro).
- `/inventory/products` no lleva datos de usuario, y el modelo de incidencia del gestor no tiene ningún campo de usuario ni de cliente (título, descripción, categoría, estado, origen y sede). Lo que cambia por usuario (`/auth/me`, `/profiles/me`) no se cachea.

## 5. Volumen antes y después del seed, y cómo cambió la latencia

**El seed:** `scripts/seed_volume.py`, con datos sintéticos, determinista (semilla `20261031`) e idempotente. Solo escribe en bases de prueba: rechaza `services/api/data` y un PostgreSQL que no sea local.

| Colección | Volumen de la demo | Volumen sembrado |
|---|---|---|
| Incidencias (TinyDB) | 96 | **5096** (3,6 MB) |
| Proveedores (TinyDB) | 15 | **415** |
| Activos / entradas / salidas (PostgreSQL) | 6 / 4 / 3 | **126 / 12 202 / 18 191** |

| Endpoint | Volumen de la demo, sin caché | Volumen sembrado, sin caché | Volumen sembrado, con caché (acierto) |
|---|---|---|---|
| `GET /api/incidents/summary` | 8,1 ms | 36,8 ms (volumen) · 69,5 (bind mount) | **2,6 ms** |
| `GET /api/incidents?status=open` | 8,3 | 39,1 · 75,9 | **4,1** |
| `GET /api/incidents` (sin filtros) | 8,8 | 87,5 · 110,8 | **13,4** |
| `GET /inventory/products` (local) | 13,3 | 14,6 · 25,3 | **3,0** |
| `GET /inventory/products` (Supabase, 6 activos) | 397,8 | — | **2,4–2,8** |
| `GET /suppliers` (no cacheado) | 7,2 | 6,3 · 11,3 | — |
| `GET /inventory/orders` (no cacheado) | 12,6 | 657,4 · 674,1 | — |

**Lectura:**

- Con el volumen de la demo, todo cuesta menos de 15 ms en local: el timing no distinguía nada.
- El seed hizo aparecer dos familias de coste:
  - las incidencias, que escalan con el número de documentos;
  - el inventario contra Supabase, cuyo coste de red no depende del volumen.
- **Bind mount frente a volumen de Docker:** con las TinyDB en un bind mount de Windows (como la demo), cualquier ruta autenticada paga unos 7 ms más, porque `get_current_user` abre `auth.json` en cada petición. En un volumen de Docker, como sería en producción, baja a 1,5 ms.

**Entorno de medición:**

- PostgreSQL efímero `postgres:17.6-alpine3.22` con el esquema creado por el lifespan de la API.
- TinyDB de prueba en un volumen de Docker.
- Supabase de la demo **solo con GET**, con `uvicorn --lifespan off`, para no lanzar ni `create_all` ni `ALTER TABLE` al arrancar; el log de timing no tiene ninguna línea de otro método.
- Ráfagas con [`scripts/bench_reads.py`](./scripts/bench_reads.py), solo GET y con la librería estándar.
- Todo se borró al terminar. La receta para repetirlo está en `docs/caching-analysis.md` §2.4.

## 6. Trabajo futuro

- **D9 — el access log de uvicorn registra la query string.**
  - El timing nuevo no la registra, pero `uvicorn.access` sí (comprobado: `GET /health?email=x@example.invalid`).
  - Hoy ninguna ruta lleva datos personales en la query.
  - Recomendación: un filtro de logging en `uvicorn.access` que la elimine.
- **D10 — lo que no es caché pero domina la experiencia:**
  - **Paginación** de `GET /inventory/orders` y `GET /api/incidents`, en la API y en las tablas: 25,5 s y 3,35 s de render.
  - **Un pool de conexiones a Supabase** en lugar de `NullPool`, que revisaría la decisión del Hito 5 con el Transaction pooler: unos 400 ms fijos en cada petición no cacheada y en cada escritura.
  - **`get_current_user` abre `auth.json` en cada petición** (de 1,5 a 7 ms según el almacenamiento).
- **D7-B — un formateador de moneda por moneda en `components/suppliers/format.ts`,** fuera de React. Bajaría el formateo de 46–135 ms a ~1 ms en cualquier render, también al montar. Se deja para después a propósito: dejaría el `useMemo` de §1.2 sin casi nada que ahorrar.
