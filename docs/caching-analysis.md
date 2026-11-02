# Caching y optimización — análisis y medición inicial (F0)

> **Actualización (2026-10-31, F1):** el usuario decidió D1 A, D2 A (sin la opción B), D3 A con un máximo de 64 entradas por espacio, D4 y D5 como se proponen, D6 A, D7 A (B como mejora futura), D8 B, D9 fuera de este ticket (trabajo futuro), D10 como trabajo futuro y D11 sí. La implementación, la medición «después» y el informe están en [`CACHING_REPORT.md`](../CACHING_REPORT.md) y el contrato en `services/api/SPECS.md` Parte G. Lo que sigue es la foto de F0, sin cambios.
>
> **Estado al cerrar F0:** **sin ninguna caché implementada**. Rama `feature/caching-optimisation` (desde `main` en `9f312e1`, merge de la PR #26). El `CACHING_REPORT.md` del brief se escribirá en F1, cuando el usuario decida D1–D11 (§7).
>
> Commits de F0: `1178ddf` (`feat(api): middleware de timing por petición`) y el de este documento, el brief y el seeder de volumen.

## 1. Resumen

- **Backend.** Con volumen realista, las lecturas caras son dos familias, por motivos distintos:
  - **Incidencias** (TinyDB, 5096 documentos): **22–110 ms**. Cada petición abre el archivo de 3,6 MB y valida los 5096 documentos, también el detalle por id y el resumen. El coste lo pone el volumen, no la red.
  - **Inventario contra Supabase**: **~400 ms por lectura con solo 6 activos**. Es un coste fijo de red: el motor usa `NullPool` y cada petición abre una conexión nueva al pooler. Con el volumen grande en local, `/inventory/products` cuesta 15–25 ms.
- **Lo que no se arregla con caché:** `GET /inventory/orders` (30 393 órdenes, 8,5 MB, 660 ms en la API y **25,5 s** de render en el backoffice) y `GET /api/incidents` sin filtros (2 MB, 3,4 s de render). Ahí falta paginación (D10).
- **Proveedores** (415): 3–6 ms. No compensa cachear, y el CONTEXT pide que un cambio de tarifa se vea «inmediatamente».
- **Frontend.**
  - App Router ya divide el JS por ruta (4,9–8,0 KB comprimido por vista).
  - Con `next/dynamic`, `SupplierCreateForm` y los resultados de `/incidents` **no** reducen el JS inicial: lo suben unos 0,4 KB comprimidos, porque el runtime de carga diferida pasa al chunk compartido. Solo aplazan 2,1 KB y 3,7 KB (§5.1).
  - `activeCount` y `upcomingCount` cuestan 0,1–1,6 ms y **no** se recalculan al escribir en el formulario de alta (medido).
  - Sí cuesta el re-render completo de `SupplierTable` (150–372 ms con 415 filas) al abrir o cerrar ese formulario, sin ningún cambio de datos. Buena parte es crear un `Intl.NumberFormat` por fila: 46–135 ms frente a 1,1 ms reutilizándolo (§5.2).

## 2. Cómo se midió

### 2.1 Bases de prueba (nunca la demo)

| Eje | Base | Para qué |
|---|---|---|
| **Volumen** | PostgreSQL efímero `postgres:17.6-alpine3.22` (`linux/amd64`, `sha256:747d5ed1…`, 398 MB en disco), contenedor `nexova-cache-pg` fuera de `docker-compose.yml`, solo en `127.0.0.1:55432`, red propia `nexova-cache-net` y volumen `nexova-cache-pg-data`. Esquema creado por el **lifespan de la API** (`create_all` + RLS). TinyDB en archivos aparte (`AUTH_DB_PATH`, `SUPPLIERS_DB_PATH`, `INCIDENTS_DB_PATH` → `/data/*.json`, en el scratchpad de la sesión) | Cuánto cuesta cada lectura según el número de filas |
| **Red** | La base de la demo en Supabase, **solo con GET**, con su volumen actual (6 activos y 10 órdenes; el banco de memoria decía 7, no se tocó). Con `uvicorn --lifespan off`, para que el arranque no lance ni `create_all` ni `ALTER TABLE … ENABLE ROW LEVEL SECURITY`; los usuarios, en la TinyDB de pruebas | Cuánto cuesta la red real hasta Supabase |

- **En Supabase solo se hicieron GET:** el log de timing del contenedor no tiene ninguna línea de otro método, salvo los `POST /auth/login`, que van a la TinyDB de pruebas. La `DATABASE_URL` se pasó al contenedor por variable de entorno, sin imprimirla, y el contenedor se borró al terminar.
- **Cuentas temporales:** un `user` (alta con `POST /users`) y un `admin` (con `AuthRepository`, para `GET /users`), las dos **solo en la TinyDB de pruebas**, con emails `cache-f0-…@example.invalid`. Se borraron con esa TinyDB (§8).

### 2.2 Volumen, antes y después del seed

| Colección | «Antes» (volumen de la demo, con sus propios seeds) | «Después» (`scripts/seed_volume.py`) |
|---|---|---|
| Incidencias (TinyDB) | 96 (`seed_incidents.py` con el fixture de aceptación) | **5096** (+5000), 3,6 MB en disco |
| Proveedores (TinyDB) | 15 (`python -m app.seed`) | **415** (+400) |
| Activos (PostgreSQL) | 6 (`seed-inventory`) | **126** (+120) |
| Entradas / salidas | 4 / 3 | **12 202 / 18 191** (82–397 órdenes por activo sintético) |
| Usuarios (TinyDB) | 2 (las cuentas temporales) | 2 |

**`scripts/seed_volume.py`** (revisable):

- **Datos sintéticos:** títulos «[SINTÉTICO] …», «Proveedor sintético NNN», SKU `SYN-…`, empleados `EMPLEADO-SINTETICO-NNN` y emails `*.example.invalid`. Ningún dato de Nexova.
- **Vocabulario real:** el de `nexova_shared` y el del inventario.
- **Determinista:** semilla `20261031` y fecha de referencia fija 2026-10-01.
- **Idempotente:** la segunda ejecución inserta 0 en las tres colecciones (comprobado).
- **Mismas reglas que la API:** `validate_incident_fields`, `SupplierCreate` y los schemas de órdenes.
- **Protecciones:** se niega a escribir en `services/api/data` y en un PostgreSQL que no sea local; las dos se probaron (salida 1).

**Repartos sembrados (comprobados):**

- **Incidencias:**
  - estados por antigüedad: 3142 resolved, 737 in_progress, 672 open y 545 discarded;
  - 8 categorías (de 275 a 1305 cada una), 3 orígenes y 4 sedes;
  - fechas entre 2024-09-30 y 2026-10-01, más densas en lo reciente.
- **Proveedores:** 239 en Spain/EUR y 176 en USA/USD; 356 activos y 59 suspendidos; 332 con fecha de renovación, una parte dentro de los 60 días.
- **Inventario:** el stock acumulado nunca baja de 0 (mínimo 0 con una ventana SQL); 11 085 asignaciones, todas con `assigned_to`, y 7106 consumos, ninguno con él.

### 2.3 Ráfagas

- **Método:** por endpoint, 3 peticiones de calentamiento y después **N idénticas** (misma URL, mismos parámetros, misma cuenta). N = 100 con el volumen de la demo y N = 50 con el volumen sembrado.
- **Desde dónde:** desde un contenedor de la misma red de Docker, como hace el backoffice (`ui` → `api`).
- **Primer intento descartado:** desde el host, el reenvío de puertos de Docker Desktop en Windows añadía ruido; por ejemplo, `?country=Spain` salía más lento que el listado completo.
- **Qué se registra:**
  - p50 y p95 en cliente;
  - bytes y filas;
  - si la respuesta es idéntica en las N;
  - si es la misma para la otra cuenta (`user` ↔ `admin`).
- **Lado servidor:** el log `api.timing` del mismo periodo da cifras iguales con 1 ms menos.

### 2.4 Reproducir en F1

Desde Git Bash, en la raíz. `PW` y `JWT` son valores aleatorios de un solo uso; no van al repositorio.

```bash
docker network create nexova-cache-net
docker run -d --name nexova-cache-pg --network nexova-cache-net -e POSTGRES_USER=nexova_cache -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=nexova_cache -p 127.0.0.1:55432:5432 -v nexova-cache-pg-data:/var/lib/postgresql/data postgres:17.6-alpine3.22
# API de medición: el código del árbol en solo lectura y las TinyDB de prueba en ./tmp-cache-data (fuera de git)
MSYS_NO_PATHCONV=1 docker run -d --name nexova-cache-api --network nexova-cache-net -p 127.0.0.1:8100:8000 \
  -v "$(pwd -W)/services/api/app:/app/api/app:ro" -v "$(pwd -W)/packages/shared/nexova_shared:/packages/shared/nexova_shared:ro" \
  -v "$(pwd -W)/packages/incident-analyzer/incident_analyzer:/packages/incident-analyzer/incident_analyzer:ro" -v "<carpeta de prueba>:/data" \
  -e JWT_SECRET_KEY="$JWT" -e ACCESS_TOKEN_EXPIRE_MINUTES=120 -e DATABASE_URL="postgresql://nexova_cache:$PW@nexova-cache-pg:5432/nexova_cache" \
  -e AUTH_DB_PATH=/data/auth.json -e SUPPLIERS_DB_PATH=/data/suppliers.json -e INCIDENTS_DB_PATH=/data/incidents.json \
  nexova-api:latest uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1
# Seeds (en un contenedor de un solo uso con las mismas variables y el repo en /repo:ro, -w /repo/services/api)
python -m app.seed
python /repo/scripts/seed_incidents.py /repo/packages/incident-analyzer/tests/fixtures/incidents-acceptance-synthetic.csv
python -m app.modules.inventory.seed --email <cuenta de prueba>
python /repo/scripts/seed_volume.py incidents suppliers inventory --email <cuenta de prueba> --allow-db-host nexova-cache-pg
```

Limpieza (hecha al cerrar F0):

```bash
docker rm -f nexova-cache-api nexova-cache-pg
docker volume rm nexova-cache-pg-data nexova-cache-tinydb
docker network rm nexova-cache-net
```

El script de las ráfagas (`bench.py`, solo GET, con `http.client` de la librería estándar) quedó fuera del repositorio. D11 decide si se versiona para F1.

## 3. Medición del backend

p50 / p95 en ms, en cliente, dentro de la red de Docker. «Antes» y «Después» se midieron con las TinyDB en un **bind mount de Windows**, como la demo (`./services/api/data`). «Después, volumen» es lo mismo con las TinyDB en un **volumen de Docker**, como sería en producción (`docker-compose.yml`: «En producción, un volumen con nombre»).

| Endpoint | Filas antes → después | Bytes antes → después | Antes | Después (bind mount) | Después (volumen) | Supabase (red, solo GET) | Idéntica en N | Igual para otra cuenta |
|---|---|---|---|---|---|---|---|---|
| `GET /health` | — | 15 | 0,8 / 1,0 | 0,9 / 1,0 | 1,1 / 1,5 | — | sí | sí |
| `GET /auth/me` | — | 196 | 9,9 / 53,2 | 7,0 / 9,3 | 1,8 / 2,6 | — | sí | **no** (personal) |
| `GET /profiles/me` | — | 41 | 9,0 / 27,5 | 7,0 / 16,7 | 1,5 / 2,0 | — | sí | sí, solo porque los dos perfiles están vacíos (personal) |
| `GET /users` (admin) | 2 | 332 | 7,9 / 51,7 | 7,6 / 43,9 | 1,7 / 2,2 | — | sí | no (403 para `user`) |
| `GET /users/{id}` | — | 161 | 7,1 / 13,3 | 7,3 / 9,3 | 1,9 / 2,5 | — | sí | el propio usuario (personal) |
| `GET /suppliers` | 15 → 415 | 4,7 KB → 146 KB | 7,2 / 11,9 | 11,3 / 43,6 | **6,3 / 7,2** | — | sí | sí |
| `GET /suppliers?country=Spain` | 8 → 239 | 2,6 → 85 KB | 10,1 / 34,6 | 17,2 / 57,3 | 5,4 / 6,1 | — | sí | sí |
| `GET /suppliers?category=ats_software` | 2 → 57 | 0,7 → 20 KB | 8,0 / 51,3 | 9,8 / 14,2 | 4,3 / 4,9 | — | sí | sí |
| `GET /suppliers/{id}` | — | 352 | 7,4 / 49,4 | 8,6 / 39,6 | 2,9 / 3,6 | — | sí | sí |
| `GET /api/incidents` | 96 → 5096 | 23 KB → **2,0 MB** | 8,8 / 51,9 | **110,8 / 189,1** | **87,5 / 117,4** | — | sí | sí |
| `GET /api/incidents?status=open` | 27 → 672 | 6 → 262 KB | 8,3 / 15,7 | 75,9 / 129,7 | 39,1 / 49,7 | — | sí | sí |
| `GET /api/incidents?branch=miami_office&category=sla_breach` | 0 → 96 | 0 → 39 KB | 8,2 / 10,7 | 101,4 / 135,4 | 34,3 / 36,8 | — | sí | sí |
| `GET /api/incidents/summary` | — | 410 | 8,1 / 12,9 | **69,5 / 130,5** | **36,8 / 71,5** | — | sí | sí |
| `GET /api/incidents/{id}` | — | 426 | 7,7 / 25,1 | 63,2 / 122,9 | 22,0 / 23,9 | — | sí | sí |
| `GET /api/incidents/results/export` | 34 | 931 | 4,4 / 12,5 | 7,0 / 16,5 | — | — | sí | sí (ver §4, privacidad) |
| `GET /inventory/products` | 6 → 126 | 0,7 → 16 KB | 13,3 / 21,6 | 25,3 / 41,3 | 14,6 / 15,5 | **397,8 / 468,8** | sí | sí |
| `GET /inventory/products/{id}` | — | 121 | 19,6 / 44,9 | 15,9 / 34,7 | 10,5 / 11,0 | **399,7 / 495,0** | sí | sí |
| `GET /inventory/orders` | 7 → 30 393 | 1,8 KB → **8,5 MB** | 12,6 / 19,0 | **674,1 / 724,2** | 657,4 / 708,1 | 452,4 / 524,2 (10 órdenes) | sí | sí |
| `POST /api/incidents/analyze` (fixture de 100 filas, 10 veces) | — | — | 17,6 (p50) | 16,1 (p50) | — | — | — | — |

**Qué sostiene cada medida:**

- **Coste por volumen (PostgreSQL y TinyDB locales).**
  - Las incidencias escalan con el número de documentos: de 8 a 37–110 ms. El detalle por id (22 ms en volumen) da el suelo: leer y validar el archivo entero.
  - Los proveedores casi no cambian: de 7 a 3–6 ms en volumen. Con 415 documentos no hay nada que ganar.
  - `/inventory/products` agrega 30 k órdenes en 15–25 ms: PostgreSQL agrega bien.
  - `/inventory/orders` es caro por el tamaño de la respuesta (8,5 MB), no por la consulta.
  - Esta medida sostiene **qué** endpoints cuestan por su trabajo.
- **Coste por red (Supabase).**
  - Con 6 activos, las tres lecturas cuestan **~400 ms**, y el listado tanto como el detalle: es un coste fijo por petición (conexión TCP/TLS nueva al pooler en cada petición, por `NullPool`, más las idas y vueltas), no del volumen. `/inventory/orders` suma unos 50 ms: una consulta más.
  - Esta medida sostiene que, en el despliegue real, **toda lectura del inventario es cara aunque haya pocos datos**: es el argumento de frecuencia × coste para `/inventory/products`, que se pide en tres pantallas y tras cada orden (§4).
- **Bind mount frente a volumen.**
  - El coste fijo de cualquier ruta autenticada (`get_current_user` abre `auth.json` en cada petición) pasa de ~7 ms a ~1,5 ms.
  - El de las incidencias filtradas baja a la mitad.
  - Las cifras del bind mount son las de la demo; las del volumen, las de producción. F1 debe comparar las dos.
- **Ninguna lectura depende del momento:** las N respuestas son idénticas en todos los endpoints. Entre cuentas, solo cambian las personales.

## 4. Todos los endpoints (32)

**Leyenda:**

- **Frecuencia:** qué pantallas y acciones del backoffice (`uis/backoffice`) y del tracker (`uis/talent-pipeline-tracker`, solo auth) disparan cada endpoint.
- **Cambio:** con qué frecuencia cambian los datos que devuelve.
- **Personal:** ¿personal, sensible o de sesión?

| # | Endpoint | (a) Coste medido (volumen / red) | (b) Frecuencia | (c) Cambio de los datos | (d) Personal | Veredicto |
|---|---|---|---|---|---|---|
| 1 | `GET /health` | 1 ms | healthcheck de Docker cada 5 s | nunca | no | **No**: no tiene coste |
| 2 | `POST /auth/login` | bcrypt, 190–260 ms | cada login | — | credenciales | **No**: escritura de sesión y secreto |
| 3 | `GET /auth/me` | 1,8 ms (volumen) / 7 ms (bind mount) | **cada carga de página** (guard global de las dos apps) | al cambiar el perfil o el rol | **sí**, de sesión | **No**: barato y personal; una caché tendría que ir por usuario y no compensa |
| 4 | `POST /auth/forgot-password` | — | rara | — | sensible | **No** (escritura) |
| 5 | `POST /auth/reset-password` | — | rara | — | sensible | **No** (escritura) |
| 6 | `POST /auth/change-password` | — | rara | — | sensible | **No** (escritura) |
| 7 | `POST /users` | bcrypt | registro | — | personal | **No** (escritura) |
| 8 | `GET /users` | 1,7 ms | ninguna pantalla (API de admin) | con cada alta | **sí**, datos de usuarios | **No**: sensible y sin uso |
| 9 | `GET /users/{id}` | 1,9 ms | ninguna pantalla | al editar | **sí** | **No** |
| 10 | `PUT /users/{id}` | — | API de admin | — | sí | **No** (escritura) |
| 11 | `DELETE /users/{id}` | — | API | — | sí | **No** (escritura) |
| 12 | `GET /profiles/me` | 1,5 ms | `/account/profile` | al guardar el perfil | **sí** | **No**: personal y barato |
| 13 | `PUT /profiles/me` | — | guardar el perfil | — | sí | **No** (escritura) |
| 14 | `GET /suppliers` (+ `country`, `category`) | 3–6 ms / 415 filas (volumen), 10–17 ms (bind mount) | entrar en `/suppliers` y cada cambio de filtro | alta, tarifa, estado; el CONTEXT pide ver la tarifa nueva «inmediatamente» | no | **No**: el coste no lo justifica y la frescura es requisito de negocio (D5) |
| 15 | `GET /suppliers/{id}` | 3 ms | ninguna pantalla | igual | no | **No** |
| 16 | `POST /suppliers` | — | alta | — | no | **No** (escritura): invalidaría si se cacheara 14 |
| 17 | `PATCH /suppliers/{id}/rate` | — | editar tarifa | — | no | **No** (escritura) |
| 18 | `PATCH /suppliers/{id}/status` | — | activar/suspender | — | no | **No** (escritura) |
| 19 | `DELETE /suppliers/{id}` | — | ninguna pantalla | — | no | **No** (escritura) |
| 20 | `POST /api/incidents/analyze` | 16–18 ms (100 filas) | cada CSV subido | contenido nuevo en cada llamada | el CSV lleva emails de clientes | **No**: el cuerpo varía, y el resultado ya se guarda en memoria (`LastResultStore`) |
| 21 | `GET /api/incidents/results/export` | 4–7 ms | botón «Exportar» tras analizar | con cada análisis | resultados agregados, **compartidos entre usuarios** (un único último análisis por proceso) | **No**: ya está en memoria. Nota: el «último análisis» es global, no por usuario; es anterior a este ticket y queda fuera de alcance |
| 22 | `POST /api/incidents` | — | alta en `/incident-manager/new` | — | no | **No** (escritura): invalida 23–25 |
| 23 | `GET /api/incidents` (+ 4 filtros) | **34–110 ms** / 96–5096 filas; 2 MB sin filtros | entrar en `/incident-manager` y cada cambio de filtro | alta o cambio de estado (minutos u horas); seed esporádico | no (igual para todas las cuentas) | **Candidato** (D1): coste por volumen × navegación repetida; clave con los filtros normalizados |
| 24 | `GET /api/incidents/summary` | **37–70 ms** (lee las 5096) | entrar en `/incident-manager` y **tras cada cambio de estado** (`reload`) | igual que 23 | no | **Candidato** (D1): mismo coste que el listado para 410 bytes; muy estable |
| 25 | `GET /api/incidents/{id}` | 22–63 ms (lee las 5096 para encontrar una) | ninguna pantalla todavía | igual | no | Lo cubriría la opción B de D2 (caché del repositorio), no una caché propia |
| 26 | `PATCH /api/incidents/{id}/status` | — | selector de estado de la tabla | — | no | **No** (escritura): invalida 23–25 |
| 27 | `GET /inventory/products` | 15–25 ms (126 activos / 30 k órdenes) · **~400 ms en Supabase** | `/inventory/products`, formularios de entrada y salida (selector y «Stock actual»), y otra vez tras cada orden | con cada orden o activo nuevo (pocas al día en la demo) | no | **Candidato fuerte** (D1): coste de red fijo × tres pantallas |
| 28 | `GET /inventory/products/{id}` | 10–16 ms · **~400 ms en Supabase** | formulario de salida (stock del activo elegido) | igual que 27 | no | **Candidato** con 27: misma familia de claves y misma invalidación |
| 29 | `POST /inventory/products` | — | ninguna pantalla (API) | — | no | **No** (escritura): invalida 27–28 |
| 30 | `POST /inventory/orders/inbound` | — | formulario de entrada | — | no | **No** (escritura): invalida 27–28 |
| 31 | `POST /inventory/orders/outbound` | — | formulario de salida | — | no | **No** (escritura): invalida 27–28 |
| 32 | `GET /inventory/orders` | **660 ms / 8,5 MB** (30 k) · 450 ms en Supabase (10) | `/inventory/orders` (historial) | con cada orden | no; lleva el `user_uuid` de quien registró cada orden, igual para todas las cuentas | **No** (D5): el coste es el volumen sin paginar (25,5 s de render en el navegador); una caché ahorraría ≤ 0,7 s de 26 s y retendría 8,5 MB por entrada |

**Privacidad:** los tres candidatos devuelven lo mismo a cualquier usuario autenticado (columna «Igual para otra cuenta»). Una clave compartida no filtra nada entre usuarios, siempre que la caché viva **dentro** del handler, después de `get_current_user`: sin token, la respuesta sigue siendo 401 (D3).

## 5. Frontend (`uis/backoffice`)

**Montaje:**

- Build de producción con perfilado de React (`next build --profile`), servido con `next start`.
- La API de medición de §2 con el volumen sembrado detrás, a través de los rewrites de `/backend`.
- Variables solo en la sesión de PowerShell.
- Instrumentación **temporal y sin commitear**: `<Profiler>` en las vistas y `performance.now()` alrededor de los contadores, recogidos en `window`.
- Al terminar: los archivos se restauraron con `git checkout`, se repitió `npm run build` sin variables y se volvió a arrancar el `ui` de Docker.

> **Puerto:** el 3003 estaba ocupado por un `next start -p 3003` de la auditoría de rendimiento, en marcha desde el 2026-10-28, que reenvía `/backend` a la API de la demo. No se paró (no hubo permiso para terminar ese proceso); la medición se hizo en el **3004**. Conviene pararlo (D11).

### 5.1 JS por ruta y Lazy Loading

**Peticiones `/_next/static/chunks/` en una carga completa (Network, `encodedBodySize`):**

- **Todas las rutas comparten** unos 152 KB comprimidos; 79 KB son de `react-dom`, en su variante de perfilado en este build.
- **Cada vista añade un único chunk propio:**

| Vista | Chunk propio (comprimido / sin comprimir) |
|---|---|
| `/suppliers` | 8,0 / 27,4 KB (vista, tabla **y formulario de alta**) |
| `/incident-manager` | 6,6 / 21,4 KB |
| `/incidents` | 5,9 / 19,5 KB (vista, formulario **y componentes de resultados**) |
| `/inventory/products` | 4,9 / 13,5 KB |
| `/` | ninguno |

**Experimento temporal (sin commitear):**

- `SupplierCreateForm` con `next/dynamic`, y los cinco componentes de resultados de `/incidents` (`AnalysisMeta`, `TotalsCards`, `InvalidBreakdownTable`, `DistributionTable` y `SatisfactionPanel`), también con `next/dynamic`.
- Mismo build, mismos tamaños medidos con gzip -9 sobre los chunks.

| | Base | Con `next/dynamic` |
|---|---|---|
| Chunk de `/suppliers` | 8 012 B | 8 306 B (+294) |
| Chunk diferido del formulario | — | 2 128 B (se pide al pulsar «Nuevo proveedor») |
| Chunk de `/incidents` | 5 892 B | 6 165 B (+273) |
| Chunks diferidos de resultados | — | 5 chunks, 3 719 B en total (tras «Analizar») |
| Chunks compartidos (todas las rutas) | 56 594 B | 56 729 B (+135; el runtime de `next/dynamic` sube 1,2 KB y otro chunk baja 1,1 KB) |
| **JS inicial de `/suppliers`** | — | **+429 B** |
| **JS inicial de `/incidents`** | — | **+408 B** |

**Conclusión medida:**

- Los dos candidatos **no** pesan lo bastante para que el lazy loading reduzca la carga inicial: la empeora un poco y añade una petición al abrir el formulario o mostrar los resultados.
- El formulario sigue siendo el mejor candidato del brief en cuanto a flujo: solo existe con `formOpen`, que el usuario abre a propósito.
- En `/incidents`, un único `dynamic` que agrupe los resultados (1 chunk en vez de 5) recortaría peticiones.
- **CLS:** un contenido que aparece en los 500 ms siguientes a la acción del usuario no cuenta como cambio de diseño inesperado (`hadRecentInput`).
  - El formulario solo aparece tras el clic, así que no puede perder lo ganado en la auditoría de rendimiento si el `loading` reserva el alto.
  - Los resultados llegan tras la respuesta de la API y pueden tardar más de 500 ms: su `loading` debe ocupar el mismo hueco que el estado vacío actual, como ya hace el esqueleto de H2 en `/incident-manager`.
- Decisión en D6.

### 5.2 Re-renders (`<Profiler>`, `actualDuration`)

| Interacción | Qué se re-renderiza | Coste |
|---|---|---|
| Carga de `/suppliers` (415 filas) | `SupplierTable` (montaje) | **580 ms** |
| Abrir el formulario de alta | `SupplierDirectoryView` → **`SupplierTable` entera**, sin ningún cambio de proveedores | **372 ms** |
| Cerrar el formulario («Cancelar») | lo mismo | **150 ms** |
| Escribir 21 caracteres en «Nombre» | solo `SupplierCreateForm` (0,1–3,2 ms por pulsación); la vista padre no se re-renderiza por el formulario | 0 recálculos de `activeCount` y `upcomingCount` |
| `activeCount` (415) | — | 0,1–0,4 ms |
| `upcomingCount` (415, `renewalInfo` por fila) | — | 1,6 ms (8,7 la primera vez) |
| `Intl.NumberFormat` nuevo por fila (`formatRate`), 415 veces | — | **46–135 ms** frente a **1,1 ms** reutilizando uno por moneda |
| Carga de `/incident-manager` (5096 filas) | `IncidentTable` (montaje) | **3,35 s** (petición de 263 ms y 2 MB) |
| Cambiar el filtro de estado a `open` | `IncidentTable` con las 5096 (estado de carga) y después con 672 | 1,62 s + 240 ms (4,4 s en total) |
| Carga de `/inventory/orders` (30 393 filas) | `OrderTable` (montaje) | **25,5 s** (petición de 0,9 s y 8,5 MB) |
| Carga de `/inventory/products` (126) | `AssetTable` (montaje) | 131 ms |

**Lectura:**

- **Lo que dice el brief que se confirma:** `SupplierTable` se re-renderiza sin cambio real de props. Al abrir o cerrar el formulario cambian `formOpen` y `create`, que la tabla no usa; sus props (`suppliers`, `rows`, `today` y callbacks con `useCallback`) son las mismas referencias. Un `React.memo` evitaría los 150–372 ms.
  - Dentro de la tabla, lo caro que se repite en cada render es **construir el formateador de moneda por fila**.
- **Lo que se descarta con la medida:** `useMemo` en `activeCount` y `upcomingCount`. Cuestan menos de 2 ms y solo se recalculan cuando la vista ya se re-renderiza por otro motivo (lista, filtros, alta, edición de fila), nunca al escribir en el formulario. Memoizarlos sería la «memoización prematura» del brief.
- **Fuera de alcance, pero dominante:** el render de las tablas sin paginar (3,4 s y 25,5 s). Ni `useMemo` ni la caché lo arreglan; hace falta paginación o virtualización (D10).

## 6. Hallazgos colaterales

1. **El access log de uvicorn registra la query string.** `docker compose logs api` muestra `GET /health?email=x@example.invalid` (comprobado). El middleware de timing no lo hace, pero el access log, que ya existía, sí. Hoy las rutas no llevan datos personales en la query, pero nada lo impide, y los filtros del gestor y de proveedores sí van ahí. Decisión en D9.
2. **El healthcheck genera una línea de timing cada 5 s** (`GET /health → 200 | 0.6ms`), además de su línea de access log. Decisión en D8.
3. **Coste fijo de Supabase por `NullPool`:** unos 400 ms por petición, haya pocos datos o muchos. Una caché lo esconde en las lecturas cacheadas, pero no en las escrituras ni en las lecturas no cacheadas. Lo que lo resolvería es un pool de conexiones, una decisión del Hito 5 que queda fuera de este ticket (D10).
4. **Listados sin paginar:** `/inventory/orders` (8,5 MB) y `/api/incidents` (2 MB) con volumen realista (D10).
5. **Un servidor del 3003 sigue vivo desde el 2026-10-28** (§5) (D11).

## 7. Decisiones pendientes del usuario (D1–D11)

### D1 — Qué endpoints cachear y con qué TTL

| Opción | Endpoints | TTL |
|---|---|---|
| **A (recomendada)** | `GET /inventory/products` + `GET /inventory/products/{id}` · `GET /api/incidents/summary` · `GET /api/incidents` (con filtros en la clave) | inventario **60 s**; incidencias **30 s** |
| B | Solo inventario y resumen | igual |
| C | Solo inventario | 60 s |

**Por qué A:**

- **Inventario:** es la familia con el coste más alto en el despliegue real (~400 ms fijos de red) y la que más pantallas leen (lista, dos formularios y relectura tras cada orden). Sus datos solo cambian con una orden o un activo nuevo, y esas escrituras pasan por la API, que invalida (D4).
  - **Por qué 60 s:** el TTL solo cubre lo que no pasa por esta API (el seed, SQL directo en Supabase, otra instancia). Para un inventario de oficina con pocas órdenes al día, que el stock mostrado tarde hasta 60 s en reflejar un cambio externo es aceptable.
  - **No hay riesgo de sobreventa:** la regla del stock de `POST /orders/outbound` se comprueba en la base con `FOR UPDATE` y nunca contra la caché. Un stock desactualizado en el formulario lo mucho que provoca es un 400 con el mensaje de la regla, que ya se muestra bajo «Cantidad».
- **Incidencias:** es la familia que más escala con el volumen (37–110 ms). Además, el resumen se vuelve a pedir tras **cada** cambio de estado.
  - **Por qué 30 s, más corto:** el gestor es una herramienta de trabajo. Una incidencia creada por otra persona debería verse pronto, y el seed escribe directamente en TinyDB.
  - Las escrituras por la API invalidan al momento; los 30 s solo acotan las externas.

**Estimación, sin medir todavía:** un acierto pasaría de ~400 a ~1–2 ms en el inventario contra Supabase y de 37–110 a ~1–3 ms en las incidencias, sumando la autenticación, que sigue ejecutándose. En F1 se medirá, y una petición de lista grande seguirá pagando la serialización (D3).

### D2 — Dónde vive la caché

| Opción | Descripción | A favor | En contra |
|---|---|---|---|
| **A (recomendada)** | Módulo propio `app/core/cache.py`: diccionario en memoria `{clave: (expira_en, valor)}` con `threading.Lock`, `time.monotonic()` y espacios de nombres (`inventory`, `incidents`) para invalidar en bloque. Una instancia por app en `app.state`, como el resto de dependencias, para que cada test empiece vacío | Sin dependencias; TTL e invalidación explícitos; testeable; seguro con el pool de hilos de FastAPI | Por proceso (ver abajo) |
| B | Caché en el **repositorio** de incidencias: los documentos ya validados, invalidados por las escrituras del propio repositorio y por el `mtime`/tamaño del archivo (un `stat` por petición) | Cubre a la vez el listado, el resumen y el detalle (25); detecta el seed que escribe directo en TinyDB sin esperar al TTL | Solo sirve para TinyDB; cada petición sigue filtrando y serializando (el detalle bajaría de 22 a unos 2 ms; el listado completo, solo hasta lo que cueste serializar 2 MB) |
| C | `functools.lru_cache` | En la librería estándar | Sin TTL ni invalidación por clave (solo `cache_clear()` de todo); los argumentos tienen que ser hashables y no puede envolver la sesión ni el repositorio. **Descartada** |
| D | Redis | Compartida entre procesos y réplicas | **Dependencia y servicio nuevos** (no autorizados), y otro contenedor en `docker-compose.yml`. Solo tiene sentido con más de un worker |

- **Recomendación:** A para los tres endpoints. Si se quiere además el detalle de incidencias y la detección del seed, B como complemento solo en el repositorio de incidencias; se decide aparte.
- **`--workers 1`:** hay un único proceso, así que una caché en memoria es única y coherente, y la invalidación es inmediata para todo el tráfico. Si algún día hay más workers o réplicas, cada uno tendrá su propia copia y una escritura solo invalidará la del proceso que la recibe; los demás servirán datos viejos hasta el TTL. Se documentará en `SPECS.md`: subir workers obliga a revisar la caché (Redis, D).
- **`--reload`** (en desarrollo) vacía la caché en cada recarga. Es inocuo.

### D3 — Clave de caché y qué se guarda

- **Clave:** `(endpoint, filtros normalizados)`.
  - **Incidencias:** los filtros, una vez pasados por `validate_filters` (enum o `None`, en el orden fijo `status, origin, branch, category`). `?status=open` y `?status=open&branch=` dan la misma clave. Una entrada no válida responde 400 y nunca entra en la caché.
  - **Cota de entradas:** 5 × 4 × 5 × 9 = 900 combinaciones como máximo.
  - **Inventario:** `products` y `product:{id}`.
- **Sin usuario en la clave**, porque la respuesta es la misma para todos (§3 y §4). La caché vive dentro del handler, **después** de `Depends(get_current_user)`: sin token sigue habiendo 401, y un acierto nunca se salta la autenticación. Ningún endpoint personal (`/auth/me`, `/profiles/me`, `/users…`) entra en la caché.
- **Qué se guarda:**

| Opción | Qué se guarda | Notas |
|---|---|---|
| **A (recomendada)** | Los modelos de respuesta ya construidos (`list[AssetRead]`, `IncidentSummary`, `list[IncidentListItem]`) | Se sigue validando con `response_model` |
| B | El JSON ya serializado (`Response` con bytes) | Ahorra también la serialización (relevante en el listado de 2 MB), pero se salta `response_model` y la documentación de OpenAPI tendría que mantenerse a mano |

  Con A, los objetos se tratan como de solo lectura: no se modifican tras guardarlos.
- **Tamaño:** el listado completo de incidencias ocupa varios MB en memoria por entrada. Recomendación: un máximo de entradas por espacio de nombres (por ejemplo, 64) que expulse la más antigua.

### D4 — Invalidación

**Siempre después de un commit correcto**, nunca si la escritura falla (400, 404, 409, 503):

| Escritura | Limpia |
|---|---|
| `POST /inventory/products` | todo el espacio `inventory` (`products` y `product:*`) |
| `POST /inventory/orders/inbound`, `POST /inventory/orders/outbound` | todo `inventory`. Es una entrada por activo, pero el listado agrega todos; limpiar el espacio entero es más simple y no hay casi nada que perder |
| `POST /api/incidents`, `PATCH /api/incidents/{id}/status` | todo `incidents` (resumen y todas las claves de listado). Una invalidación selectiva por filtro no compensa con 900 claves posibles |
| Seeds (`seed-inventory`, `seed_incidents.py`, `seed_volume.py`) y cambios directos en Supabase | **no pasan por la API**, así que no invalidan: el TTL los acota (60 s / 30 s); con D2-B, el `mtime` detecta los de TinyDB al momento. Se documentará en el README: «tras un seed con la API en marcha, los datos pueden tardar hasta el TTL en verse» |

El backoffice vuelve a leer el stock y el resumen justo después de una escritura correcta. La invalidación ocurre antes de devolver la respuesta de la escritura, así que esa relectura ya es fresca. F1 lo prueba con tests.

### D5 — Qué se descarta y por qué

- **`GET /suppliers`:** cuesta 3–6 ms con 415 proveedores en volumen. El CONTEXT exige que la tarifa nueva se vea «inmediatamente» y los filtros cambian en cada clic. Cachearlo añadiría riesgo de datos viejos para ahorrar milisegundos.
- **`GET /inventory/orders`:** el coste es el volumen sin paginar (8,5 MB y 25,5 s de render). Cachearlo guardaría megas en memoria y no tocaría el render: hace falta paginación (D10).
- **`GET /auth/me` y `GET /profiles/me`:** se piden en cada página, pero son personales y cuestan 1,5–2 ms con un volumen. Necesitarían una clave por usuario y una invalidación en `PUT /profiles/me` y `PUT /users/{id}`. No compensa.
- **`POST /api/incidents/analyze` y la exportación:** el análisis es una escritura con un cuerpo distinto cada vez, y la exportación ya sale de memoria.
- **Componente:** `useMemo` en `activeCount` y `upcomingCount`, por la medida de §5.2.

### D6 — Lazy loading con `next/dynamic`

| Opción | Qué | Medido |
|---|---|---|
| **A (recomendada)** | `SupplierCreateForm` con `next/dynamic` y `loading` que reserva el alto del formulario; **un solo** `dynamic` para un componente nuevo `IncidentResults`, que agrupe los 5 componentes de resultados, con `loading` del mismo alto que el estado vacío | Inicial +0,4 KB comprimidos por vista y diferido 2,1 KB y unos 3,5 KB en un único chunk. Cumple el brief en los dos flujos que solo existen tras una acción del usuario |
| B | Lo mismo con los 5 componentes por separado | Igual que A, con 5 peticiones en vez de 1 |
| C | No aplicar lazy loading y documentarlo con esta medida | No cumple el ítem del brief |

El `CACHING_REPORT.md` explicará que el beneficio es el flujo (no cargar lo que no se usa), no los bytes. Con esta medida, los bytes salen ligeramente peor. La prueba de CLS: abrir el formulario y analizar un CSV con el Profiler de rendimiento de Chrome sin `layout-shift` fuera de `hadRecentInput`, y el `loading` con el alto reservado.

### D7 — `useMemo` y re-renders

| Opción | Qué | Medido / estimado |
|---|---|---|
| **A (recomendada)** | `useMemo` en `SupplierTable` para las filas derivadas (renovación con `renewalInfo` y tarifa formateada), con dependencias `[suppliers, today]`, más `React.memo(SupplierTable)` | `React.memo` evita los 150–372 ms al abrir o cerrar el formulario. El `useMemo` evita recalcular las 415 filas (46–135 ms de formateadores) cuando la tabla sí se re-renderiza solo por `rows` (guardar una tarifa o un estado). Es el valor no trivial que pide el brief |
| B | Además, un formateador por moneda reutilizado en `format.ts` (fuera de React) | Baja el coste del formateo a ~1 ms. Es la corrección de fondo, pero deja el `useMemo` de A con poco que ahorrar: si se elige B, el `useMemo` pierde su justificación medida |
| C | `useMemo` en `activeCount` y `upcomingCount` (el candidato del ticket) | Menos de 2 ms y no se recalculan al escribir: **descartada** con la medida |

Recomendación: A en F1, con la medida antes y después del Profiler. B queda como mejora posterior anotada, para no anular la justificación del `useMemo`. Si el usuario prefiere la corrección de fondo, B + `React.memo`, y el `useMemo` se buscaría en otro sitio.

### D8 — ¿El middleware de timing se queda en producción?

| Opción | Qué |
|---|---|
| A | Siempre activo (como ahora) |
| **B (recomendada)** | Detrás de un flag `REQUEST_TIMING_LOG` (por defecto `true` en desarrollo, documentado en `.env.example`) y **sin registrar `GET /health`** |
| C | Solo en desarrollo; quitarlo después del ticket |

**Por qué B:** la línea cuesta menos de 0,1 ms y no lleva datos personales (sin query string), así que es telemetría útil en producción, que es justo lo que el brief echa en falta («cero telemetría» en el CONTEXT). Pero el healthcheck de Docker escribe una línea cada 5 s (17 280 al día) sin información: excluirlo deja el log legible. El flag permite apagarlo si el volumen de logs molesta.

### D9 — El access log de uvicorn registra la query string

| Opción | Qué |
|---|---|
| A | `--no-access-log` en `docker-compose.yml` y en el `Dockerfile`: el middleware de timing pasa a ser la única línea por petición (con D8-B, sin `/health`) |
| **B (recomendada)** | Un filtro de logging en `uvicorn.access` que elimine la query string del mensaje antes de emitirlo |
| C | Dejarlo como está y documentar que no se pongan datos personales en la query |

**Por qué B:**

- Conserva la IP y el método de uvicorn sin la query, y no hace falta tocar el arranque.
- A es más simple, pero pierde la IP de origen, que puede servir para diagnosticar.
- C confía en que nadie meta nunca un email en un filtro.

**Alcance:** `services/api` (un módulo en `app/core/`, con la excepción de logging de `test_architecture.py` ampliada, y un test que compruebe que `?email=` no aparece). Se puede hacer en F1 o como tarea aparte.

### D10 — Lo que no es caché pero domina la experiencia (fuera de este ticket)

- **Paginación** de `GET /inventory/orders` y `GET /api/incidents`, en la API y en las tablas.
- **Pool de conexiones a Supabase** en lugar de `NullPool`, que revisaría la decisión del Hito 5 con el Transaction pooler.
- **`get_current_user` abre `auth.json` en cada petición.**

Recomendación: anotarlos como trabajo futuro en el `CACHING_REPORT.md` y abrir tickets propios. No mezclarlos con este, porque cambian contratos (paginación) o decisiones aprobadas (`NullPool`).

### D11 — Limpieza y herramientas

- ¿Se versiona el script de las ráfagas (`bench.py`, solo librería estándar) en `scripts/` para medir el «después» en F1 con el mismo método? **Recomendado sí**: hace reproducible la comparación del informe.
- ¿Se para el `next start -p 3003` que sigue vivo desde la auditoría de rendimiento (PID 28816)? **Recomendado sí**: sirve un build antiguo contra la API de la demo.

## 8. Limpieza al cerrar F0

| Elemento | Estado |
|---|---|
| Contenedores `nexova-cache-pg`, `nexova-cache-api`, `nexova-cache-api-vol` y `nexova-cache-api-sb` | borrados |
| Volúmenes `nexova-cache-pg-data` y `nexova-cache-tinydb`, red `nexova-cache-net` | borrados |
| Imagen `postgres:17.6-alpine3.22` | se conserva para F1 (`docker image rm postgres:17.6-alpine3.22` para quitarla) |
| Cuentas temporales | solo existían en la TinyDB de pruebas del scratchpad, que se borró entera; `services/api/data/auth.json` no se tocó |
| Backoffice | instrumentación revertida con `git checkout`, `npm run build` sin variables y `ui` de Docker arrancado de nuevo (`localhost:3001/backend/health` → ok) |
| Demo | ni Supabase (solo GET) ni `services/api/data` recibieron escrituras |
