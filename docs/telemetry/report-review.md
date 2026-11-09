# Reporte técnico de telemetría: guía de revisión

Rama `feature/telemetry-report`. Decisiones en [`report-analysis.md`](./report-analysis.md) (F0). Contrato: `services/api/SPECS.md`, Parte H (§48).

## 1. Qué se ha hecho, frente a lo que se evalúa

| Criterio del enunciado | Dónde | Estado |
|---|---|---|
| `analysis.py` con al menos 3 funciones | `services/telemetry/analysis.py` | Hecho: 5 métricas |
| La fórmula, en orden | Comentarios `# 1.` a `# 6.` en cada función | Hecho; lo comprueba el test de AST |
| `utc=True` antes del `groupby` | Todas las funciones | Hecho; test de AST |
| Sin loops | Todo el archivo | Hecho; test de AST (sin `for`, `while`, comprensiones, `iterrows`, `apply`) |
| Listas de dicts serializables | `to_dict(orient="records")` | Hecho; `json.dumps(allow_nan=False)` en los tests |
| 7 días por defecto | `app/modules/telemetry/report.py` | Hecho |
| Estructura `{period, metrics}` | `TelemetryReport` | Hecho |
| Caché con TTL de 60 s | `ResponseCache`, espacio `telemetry_report` | Hecho |
| Métricas técnicas, no de negocio | §3 | Hecho; ningún campo de negocio ni identificador |
| Una dimensión de agrupamiento por métrica | §2 | Hecho |
| Extra 1: `auth_failure_rate` | `analysis.py` | Hecho, con `form_submitted` (D6) |
| Extra 2: dashboard | `uis/backoffice` → `/telemetry` | Hecho; verificado por el usuario en el stack (§9) |

## 2. Las métricas

| Clave | Pregunta | Agrupa por | Sin datos |
|---|---|---|---|
| `events_per_day` | ¿Llega telemetría cada día, y de quién? | `day`, `service` | Todos los días a 0 |
| `error_rate_by_type` | ¿Qué falla, cuánto pesa, y es el sistema o el usuario? | `day`, `error_type`, `error_class` | `[]` |
| `page_load_latency_by_route` | ¿En qué sección esperan más los operadores? | `day`, `route_template`, `outcome` | `[]` |
| `dominant_event_types` | ¿Qué tipos ocupan la tabla y el cupo del colector? | `event_type`, `service` | `[]` |
| `auth_failure_rate` | ¿Cuántos logins fallan al día desde el backoffice? | `day` | `[]` |

## 3. Decisiones que conviene mirar en la revisión

- **Un periodo sin ninguna fila devuelve los días a 0, no `[]`.** La pregunta de la métrica es si el colector dejó de recibir, y una caída total es justo el caso que más interesa. Con `[]` no se distinguiría de «no se ha calculado», y el formato cambiaría cuando más hace falta. Con el tope de 90 días son como mucho 182 filas. Las otras métricas devuelven `[]`, porque una fila a 0 no aporta nada: la ausencia de errores ya se lee como ausencia.
- **`events_per_day` cuenta filas guardadas; `error_rate_by_type`, ocurrencias** (`1 + suppressed_count`). Una mide el pipeline y la otra, lo que pasó (C17).
- **El denominador son eventos técnicos, no peticiones** (D4): las correctas no se emiten. No es una tasa por petición.
- **La latencia es la espera en el navegador**, no la de la API, y solo de 4 rutas (C3).
- **`auth_failure_rate` solo ve lo que pasa por el navegador** (C5): un ataque con `curl` a `/auth/login` no sale aquí.
- **Las tasas salen con todos sus decimales** (D11): `test_architecture.py` prohíbe `round` en `app/` porque el redondeo es una regla del núcleo, y saltársela aprovechando que `services/telemetry/` queda fuera del test sería engañarlo. Así además no se pierde precisión: el cuadre con SQL de §6 es exacto.
- **`dominant_event_types` convierte `timestamp` aunque no agrupe por tiempo.** Es una línea sin efecto en el resultado: mantiene la misma fórmula en las 5 funciones y deja que el test de AST no tenga excepciones.
- **Filtro de `event_type`:** `IN` también con un solo tipo, para tener un único camino en `_load`.
- **`period` puede tener hasta 60 s de antigüedad** en la ventana por defecto: es el del cálculo que está en caché, coherente con sus datos.
- **El epoch (`?start_date=1730000000`) se acepta** sin documentarlo: lo hace Pydantic, y un parseo propio sería más código sin ganar nada (D9).
- **El día es UTC**, no el de Valencia ni el de Miami.

## 4. Efecto en la imagen y en el entorno

| | Antes | Después |
|---|---|---|
| En disco (`docker images`) | 337 MB | **476 MB** (+139 MB) |
| Comprimida (`docker compose images`) | 84,1 MB | **113 MB** (+29 MB) |

Por Pandas y numpy (más `python-dateutil` y `tzdata`). Hay que reconstruir al cambiar a esta rama: con `--reload`, el código monta sobre una imagen sin Pandas y la API no arranca.

```bash
docker compose up -d --build
```

**Fuera de Docker:** uvicorn en el host necesita `services/` en `PYTHONPATH`, porque `services/telemetry` se importa como `telemetry`. Los tests ya lo resuelven (`tests/__init__.py`). Docker es el único arranque soportado.

## 5. Validación

Desde la raíz, además de las suites (`AGENTS.md` §4):

```bash
python scripts/validate_event_schemas.py
```

```bash
F=services/api/app/modules/telemetry/schemas.py; diff <(git show main:$F | tr -d '' | sed -n '1,/^        return value/p') <(tr -d '' < $F | sed -n '1,/^        return value/p') && echo "TelemetryEvent sin cambios"
```

```bash
git diff main --stat -- uis/
```

**Mutaciones (14, todas detectadas):** fin inclusivo en `date_range` y en SQL, inicio exclusivo, sin rellenar días, sin `suppressed_count`, negocio en el denominador, cualquier formulario en el login, sin `utc=True`, sin normalizar a UTC, `start == end` aceptado, sin tope, `now` en la clave, ruta sin token y TTL distinto.

**Probado sobre PostgreSQL 17.6 real**, en un contenedor desechable, ya borrado, con un rol sin superusuario y sin tocar el stack:

- `timestamp` llega como `datetime` con zona y `tags` como `dict`, como se esperaba en F0.
- Con la sesión en `Europe/Madrid`, `timestamp` llega con `+01:00` y las 5 métricas dan lo mismo: es lo que hace `utc=True`.
- Las 5 métricas coinciden con [`report-check.sql`](./report-check.sql).
- Una segunda ejecución del seed falla y no inserta nada.

## 6. Verificación en el efímero (Parada 2)

**Todo en PowerShell, desde la raíz del repo.** La base es de usar y tirar; `telemetry_events` es inmutable y el seed es ficticio: **nunca contra la demo**. El propio seed se niega a correr fuera de `nexova_test`.

### 6.1 Postgres efímero

```powershell
$su = [guid]::NewGuid().ToString('N')
$app = [guid]::NewGuid().ToString('N')
docker network create nexova-telemetry-net
docker run -d --name nexova-telemetry-pg --network nexova-telemetry-net -e POSTGRES_PASSWORD=$su -v nexova-telemetry-pg-data:/var/lib/postgresql/data postgres:17.6-alpine3.22
```

Espera a que responda (repite hasta ver `accepting connections`):

```powershell
docker exec nexova-telemetry-pg pg_isready -U postgres
```

```powershell
docker exec nexova-telemetry-pg psql -U postgres -c "CREATE ROLE nexova_app LOGIN NOSUPERUSER PASSWORD '$app'"
docker exec nexova-telemetry-pg psql -U postgres -c "CREATE DATABASE nexova_test OWNER nexova_app"
```

### 6.2 Stack contra el efímero

El override va fuera del repo porque lleva la contraseña. Si cierras la terminal, `$app` y `$compose` se pierden.

```powershell
$override = Join-Path $env:TEMP 'nexova-report-override.yml'
@"
services:
  api:
    environment:
      DATABASE_URL: postgresql://nexova_app:$app@nexova-telemetry-pg:5432/nexova_test
    networks:
      - nexova
      - efimero
networks:
  efimero:
    name: nexova-telemetry-net
    external: true
"@ | Set-Content -Path $override -Encoding ascii
$compose = @('-f', 'docker-compose.yml', '-f', $override)
docker compose @compose up -d api
docker compose @compose ps
```

**Antes de seguir, comprueba que la API no apunta a la demo.** Esperado: `nexova-telemetry-pg`.

```powershell
docker compose @compose exec api python -c "import os; from urllib.parse import urlsplit; print(urlsplit(os.environ['DATABASE_URL']).hostname)"
```

```powershell
docker compose @compose exec api python -m app.modules.telemetry.migrate --dry-run
docker compose @compose exec api python -m app.modules.telemetry.migrate
```

### 6.3 Sembrar

50 eventos ficticios, de todos los tipos de error y de varios días ([`report-seed-ephemeral.sql`](./report-seed-ephemeral.sql)). Una sola vez: una segunda ejecución falla y no inserta nada. Esperado: `seeded = 50`.

```powershell
Get-Content docs\telemetry\report-seed-ephemeral.sql -Raw | docker exec -i nexova-telemetry-pg psql -q -U nexova_app -d nexova_test -v ON_ERROR_STOP=1
```

| Día (UTC, relativo a hoy) | Qué hay |
|---|---|
| D-9 | 1 `page_viewed`: fuera de la ventana por defecto |
| D-4 | 20 filas: logins fallidos, carga con error, `client_request_failed` con `suppressed_count = 4` |
| D-3 | **Nada:** debe salir a 0 |
| D-2 | 19 filas: el resto de errores, `direct_stock_edit_rejected` (`service = api`) |
| D-1 | 9 filas: los 4 eventos de negocio y logins |
| D-0 | 1 fila, a las 00:00:01 |

### 6.4 Token

Con tu usuario del backoffice (`auth.json` no cambia: la API sigue usando TinyDB). La contraseña no queda en el historial:

```powershell
$cred = Get-Credential -Message 'Usuario del backoffice'
$login = @{ username = $cred.UserName; password = $cred.GetNetworkCredential().Password }
$token = (Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/login -Body $login).access_token
$login = $null
$auth = "Authorization: Bearer $token"
$out = Join-Path $env:TEMP 'nexova-report'
New-Item -ItemType Directory -Force $out | Out-Null
```

### 6.5 Llamadas

**Ventana por defecto:**

```powershell
curl.exe -s -o "$out\default.json" -w "%{http_code} %{time_total}s`n" -H $auth "http://localhost:8000/telemetry/report"
$default = Get-Content "$out\default.json" -Raw | ConvertFrom-Json
$default.period
$default.metrics.events_per_day | Format-Table
```

Esperado: `200`, `period` de 7 días exactos, D-3 a 0 en los dos `service`, y D-9 fuera.

**Con fechas** (inicio inclusivo, fin exclusivo). De D-4 a D-1, los dos a medianoche:

```powershell
$today = (Get-Date).ToUniversalTime().Date
$s = $today.AddDays(-4).ToString('yyyy-MM-ddTHH:mm:ssZ')
$e = $today.AddDays(-1).ToString('yyyy-MM-ddTHH:mm:ssZ')
curl.exe -s -o "$out\window.json" -w "%{http_code} %{time_total}s`n" -H $auth "http://localhost:8000/telemetry/report?start_date=$s&end_date=$e"
$window = Get-Content "$out\window.json" -Raw | ConvertFrom-Json
$window.period
$window.metrics.events_per_day | Format-Table
```

Esperado: D-4, D-3 y D-2; D-4 con 20 (incluye la fila de las 00:00:00.000) y **sin D-1**: su fila de las 00:00:00.000 cae justo en el fin exclusivo.

**Errores:**

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://localhost:8000/telemetry/report"
curl.exe -s -w " [%{http_code}]`n" -H $auth "http://localhost:8000/telemetry/report?start_date=$e&end_date=$s"
curl.exe -s -w " [%{http_code}]`n" -H $auth "http://localhost:8000/telemetry/report?start_date=2026-01-01&end_date=2026-11-01"
curl.exe -s -o NUL -w "%{http_code}`n" -H $auth "http://localhost:8000/telemetry/report?start_date=no-es-fecha"
```

Esperado: `401`; `422` con «start_date must be earlier than end_date»; `422` con «the period cannot be longer than 90 days»; `422`.

### 6.6 La caché

**La prueba es `period.to`:** en la ventana por defecto depende de `now`. Si dos llamadas devuelven el mismo, la segunda no se ha calculado. Espera a que pase 1 minuto desde §6.5 y lanza esto:

```powershell
curl.exe -s -o "$out\c1.json" -w "%{http_code} %{time_total}s`n" -H $auth "http://localhost:8000/telemetry/report"
curl.exe -s -o "$out\c2.json" -w "%{http_code} %{time_total}s`n" -H $auth "http://localhost:8000/telemetry/report"
((Get-Content "$out\c1.json" -Raw | ConvertFrom-Json).period.to) -eq ((Get-Content "$out\c2.json" -Raw | ConvertFrom-Json).period.to)
(Get-FileHash "$out\c1.json").Hash -eq (Get-FileHash "$out\c2.json").Hash
```

Esperado: dos `True`, y el segundo tiempo mucho menor. Pasados 60 s, recalcula:

```powershell
Start-Sleep -Seconds 61
curl.exe -s -o "$out\c3.json" -w "%{http_code} %{time_total}s`n" -H $auth "http://localhost:8000/telemetry/report"
((Get-Content "$out\c1.json" -Raw | ConvertFrom-Json).period.to) -eq ((Get-Content "$out\c3.json" -Raw | ConvertFrom-Json).period.to)
```

Esperado: `False`. El log de timing lo confirma, con una línea por llamada:

```powershell
docker compose @compose logs api --since 3m | Select-String 'GET /telemetry/report'
```

### 6.7 Cuadrar cada métrica con SQL

[`report-check.sql`](./report-check.sql) calcula las 5 métricas a mano, sin Pandas, en una transacción de solo lectura, con el `period` del JSON:

```powershell
Get-Content docs\telemetry\report-check.sql -Raw | docker exec -i nexova-telemetry-pg psql -U nexova_app -d nexova_test -v "start=$($default.period.from)" -v "end=$($default.period.to)"
```

Y el JSON, para compararlo:

```powershell
$default.metrics.error_rate_by_type | Format-Table
$default.metrics.page_load_latency_by_route | Format-Table
$default.metrics.dominant_event_types | Format-Table
$default.metrics.auth_failure_rate | Format-Table
```

**Valores esperados** (`D-n` es el día; `share` cambia si añades filas):

| Métrica | Esperado |
|---|---|
| `events_per_day` | D-4: 20 / 0 · D-3: 0 / 0 · D-2: 18 / 1 · D-1: 9 / 0 · D-0: 1 / 0 (`backoffice` / `api`) |
| `error_rate_by_type` D-4, `total_events = 24` | `client_request_failed` 5 (`system`), `form_submitted:api_rejected` 3 (`rejected`), `page_load_recorded:error` 1 (`system`) |
| `error_rate_by_type` D-2, `total_events = 22` | `direct_stock_edit_rejected` 3, `frontend_error_captured` 2 (`system`) y 1 de cada: `form_submitted:api_rejected`, `:network_error`, `:server_error`, `:session_expired`, `:validation_error`, `form_validation_failed`, `page_not_found_viewed` |
| `error_rate_by_type` D-1, `total_events = 5` | `form_submitted:api_rejected` 1: los 4 de negocio no están en el total |
| `page_load_latency_by_route` | D-4 `/suppliers`: `data` 2 cargas, media 200, máx. 300; `error` 1, 5000. D-2: `/inventory/orders` `empty` 50; `/inventory/products` `data` 400 |
| `dominant_event_types` (49 filas) | `page_viewed` 18, `form_submitted` 13, `page_load_recorded` 5, `form_started` 2; el resto, 1 |
| `auth_failure_rate` | D-4: 3 / 1, tasa 0,75 · D-1: 1 / 2, tasa 0,333… (D-2 no tiene fila: sus logins no son intentos) |

Ningún valor debe contener `valencia`, `EUR`, un `user_id` ni un `session_id`:

```powershell
Select-String -Path "$out\default.json" -Pattern 'valencia|EUR|user_id|session_id|event_id|quantity'
```

Esperado: ninguna línea.

### 6.8 C15: parar la API

Comprueba lo que en F0 solo estaba leído en el código de Next: con la API parada, el navegador recibe una respuesta 500 y no un fallo de red. Por eso `client_request_failed` necesita el modo Offline.

```powershell
docker compose @compose stop api
curl.exe -s -i -m 15 http://localhost:3001/backend/health
docker compose @compose start api
```

Esperado: `HTTP/1.1 500` e `Internal Server Error`.

### 6.9 Cerrar el efímero

**Primero, el stack vuelve a la demo:** sin el override.

```powershell
docker compose up -d
docker compose ps
docker rm -f nexova-telemetry-pg
docker volume rm nexova-telemetry-pg-data
docker network rm nexova-telemetry-net
Remove-Item $override
Remove-Item -Recurse $out
Remove-Variable su, app, token, auth, cred
```

Si `docker compose up -d` no recrea `api`, añade `--force-recreate api`.

### 6.10 Resultado (verificado por el usuario el 2026-11-05)

Con esta receta, en un Postgres efímero, ya borrado:

| Paso | Resultado |
|---|---|
| §6.3 | `seeded = 50` |
| §6.5 ventana por defecto | 200, del `2026-10-29T23:19:03.760Z` al `2026-11-05T23:19:03.760Z`; D-3 (02/11) a 0 en los dos `service` y D-9 fuera |
| §6.5 con fechas | Del 01/11 al 04/11: salen 01, 02 y 03, sin el 04 (fin exclusivo) |
| §6.5 errores | 401 sin token; 422 con `start ≥ end`, con más de 90 días y con una fecha no válida |
| §6.6 caché | c1 200 en 0,056 s; c2 200 en 0,013 s, con el mismo `period.to` y el mismo hash; a los 61 s, `period.to` distinto |
| §6.7 cuadre | Las 5 métricas coinciden valor a valor con `report-check.sql`: `total_events` 24, 22 y 5; `/suppliers` 200/300 y 5000; 49 filas; 0,75 y 0,333… |
| §6.7 privacidad | Ninguna coincidencia de `valencia`, `EUR`, `user_id`, `session_id`, `event_id` ni `quantity` |
| §6.8 C15 | Con la API parada, `/backend/health` da `HTTP/1.1 500 Internal Server Error`: **C15 confirmado** |
| §6.9 | Stack de vuelta contra la demo y `healthy`; efímero, volumen, red, override y variables borrados |

## 7. Muestra en la demo (Parada 3)

**Nada de esto se hace sin la confirmación del usuario.** Todo lo que se genera aquí queda para siempre en `telemetry_events`, por eso solo se usan acciones reales del backoffice: sin seed, sin `curl` al colector y sin Entradas ni Salidas, que cambiarían el stock.

### 7.1 Antes de empezar

- Stack contra la demo y `healthy`. Comprueba la base; esperado, `True`:

  ```powershell
  docker compose exec api python -c "import os; from urllib.parse import urlsplit; print((urlsplit(os.environ['DATABASE_URL']).hostname or '').endswith(('supabase.com', 'supabase.co')))"
  ```

- `http://localhost:3001` en una sola pestaña, con DevTools **acoplado** a ella, en Network, filtrando por `telemetry`.
- **No cambies de pestaña ni minimices durante el paso 4:** al ocultarse, la cola sale por beacon, que no se reintenta, y sin red se pierde.
- Cada lote sale a los 10 s como mucho. En Network, su respuesta debe ser `200` con `rejected: 0`.

### 7.2 Acciones, en este orden

| # | Dónde | Acción | Evento | Alimenta |
|---|---|---|---|---|
| 1 | Cabecera | «Cerrar sesión», si tienes sesión | `user_logged_out` | Volumen |
| 2 | `/login` | «Iniciar sesión» con los campos vacíos | `form_started`, `form_validation_failed` (`login`) | `form_validation_failed` |
| 3 | `/login` | Tu email y una contraseña mala | `form_submitted` `api_rejected` | `form_submitted:api_rejected`, `auth_failure_rate` |
| 4 | `/login` | **Offline:** ver abajo | `form_submitted` `network_error`, `client_request_failed` (`network`, `POST`, `/auth/login`) | `form_submitted:network_error`, `client_request_failed` |
| 5 | `/register` | Enlace «Crear cuenta»; tu email real y `abc` como contraseña; «Crear cuenta» | `form_submitted` `validation_error` (`register`) | `form_submitted:validation_error` |
| 6 | `/register` | Enlace «Iniciar sesión», sin registrarte | `form_abandoned` (`register`) | Volumen y denominador |
| 7 | `/login` | Login correcto | `form_submitted` `success` | `auth_failure_rate` |
| 8 | Cabecera | Proveedores, Incidencias, Inventario (Activos) e Historial; espera a ver los datos, más de 1 s en cada una | `page_viewed` y `page_load_recorded` de las 4 rutas | `page_load_latency_by_route` |
| 9 | Barra de direcciones | `http://localhost:3001/esta-ruta-no-existe` | `page_not_found_viewed` | `page_not_found_viewed` |
| 10 | Inventario → Entrada de activos | «Registrar entrada» con el formulario vacío. **No lo rellenes** | `form_started`, `form_validation_failed` (`inbound_order`), sin petición | `form_validation_failed` |
| 11 | Cabecera | Vuelve a Activos | `form_abandoned` (`inbound_order`) | Volumen y denominador |
| 12 | — | Espera 15 s con la pestaña visible, hasta ver el último `200` | — | — |

**Por qué el paso 5 no crea nada:** tu email ya existe (409) y `abc` no pasa la validación de la API (422): cualquiera de los dos lo rechaza.

**Paso 4, Offline, con cuidado de los tiempos:**

1. Escribe tu email y una contraseña mala. No pulses nada.
2. Espera a que el último lote salga con `200` y deja pasar 12 s: la cola tiene que estar vacía.
3. DevTools → Network → **Offline**.
4. Pulsa «Iniciar sesión». Sale el aviso de que no se pudo conectar.
5. Vuelve a **No throttling antes de 5 s**.
6. Espera al `200`, y mira en su Payload que están los dos eventos.

**Son 5 s, no 15.** Tras el primer envío, los reintentos son a 1, 2 y 4 s, y el lote se descarta (`lib/telemetry.ts:41`). Con la cola vacía, el envío sale a los 10 s y aguanta hasta unos 17 s. Si ya había un envío en marcha, solo unos 7 s. Con 5 s vale en los dos casos.

**Si no aparecen:** repite el paso 4 pasado 1 minuto. `client_request_failed` tiene un throttle de 60 s por pestaña; lo perdido no se recupera y solo cuenta una fila más, así que no pasa nada.

**Con la contraseña mala a propósito,** si Offline no se aplicara, la petición saldría y sería otro `api_rejected`. Por eso este paso va en el login y no en un formulario que escriba.

### 7.3 Qué no se podrá ver en la demo

| Dato | Por qué |
|---|---|
| `frontend_error_captured` | Necesita un fallo de render real; solo se provoca con una ruta temporal, que no se monta contra la demo. Lo cubre el efímero |
| `page_load_recorded` con `error` | La página tendría que montarse con la API caída. Con la API parada, el colector también lo está y la API tarda más en volver que los reintentos: el evento se pierde. Offline no sirve: sin red, Next no carga la ruta. Lo cubre el efímero |
| `form_submitted:server_error` | Mismo motivo: exige la API parada y el lote se perdería. Lo cubre el efímero |
| `form_submitted:session_expired` | Exige que caduque el token con un formulario a medias. Lo cubre el efímero |
| `client_request_failed` por `timeout` o `config` | Sin forma limpia de provocarlos en el navegador. Con `network` basta para la fila |
| `kit_cost_variance_detected` y órdenes nuevas | Son negocio y cambiarían el stock. Solo cuentan en el volumen |
| `form_started` y similares en proveedores e incidencias | `supplier_create` e `incident_create` están en el enum, pero sus formularios no usan `useFormTelemetry` |
| Más de un día con datos | La demo solo tiene actividad reciente: `events_per_day` saldrá casi todo a 0. Es correcto, y enseña el relleno |

`direct_stock_edit_rejected` no hace falta repetirlo: ya hay una fila dentro de la ventana.

### 7.4 Token y JSON

Solo lectura. Con tu usuario, sin que la contraseña quede en el historial. Si has llamado al reporte hace menos de 60 s, espera: saldría de la caché.

```powershell
$cred = Get-Credential -Message 'Usuario del backoffice'
$login = @{ username = $cred.UserName; password = $cred.GetNetworkCredential().Password }
$token = (Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/login -Body $login).access_token
$login = $null
$auth = "Authorization: Bearer $token"
$out = Join-Path $env:TEMP 'nexova-report'
New-Item -ItemType Directory -Force $out | Out-Null
curl.exe -s -o "$out\demo.json" -w "%{http_code} %{time_total}s`n" -H $auth "http://localhost:8000/telemetry/report"
$demo = Get-Content "$out\demo.json" -Raw | ConvertFrom-Json
$demo.period
```

Esperado: `200`. El JSON queda en `$out\demo.json`, fuera del repo.

### 7.5 Revisar que no lleva identificadores

**1. Ni campos de negocio ni identificadores.** Busca las claves entre comillas: sin ellas, `stock_` coincide con los nombres `direct_stock_edit_rejected` y `stock_threshold_triggered` de `dominant_event_types`. Esperado: ninguna línea.

```powershell
Select-String -Path "$out\demo.json" -Pattern '"(user_id|session_id|event_id|userId|sessionId|office|product_id|product_category|programme_id|quantity|currency|unit_cost|supplier_key|stock_before|stock_after|min_stock)"|valencia|miami|EUR|USD'
```

**2. Ningún UUID ni email.** Esperado: ninguna línea.

```powershell
Select-String -Path "$out\demo.json" -Pattern '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-|@'
```

**3. Solo las claves del contrato.**

```powershell
$demo.metrics.PSObject.Properties | ForEach-Object { '{0}: {1}' -f $_.Name, (($_.Value | ForEach-Object { $_.PSObject.Properties.Name } | Sort-Object -Unique) -join ', ') }
```

Esperado (sin filas, la lista sale vacía):

```text
events_per_day: day, events, service
error_rate_by_type: day, error_class, error_rate, error_type, errors, total_events
page_load_latency_by_route: avg_ms, day, loads, max_ms, outcome, route_template
dominant_event_types: event_type, events, service, share
auth_failure_rate: attempts, day, failed, failure_rate, succeeded
```

**4. Míralo entero** antes de pegarlo en la PR:

```powershell
notepad "$out\demo.json"
```

**Al terminar:**

```powershell
Remove-Variable cred, token, auth
```

Borra `$out` cuando la muestra esté en la PR.

### 7.6 Resultado (verificado por el usuario el 2026-11-05)

`GET /telemetry/report` contra la demo: 200 en 0,82 s, con `period` del `2026-10-29T23:39:03.085Z` al `2026-11-05T23:39:03.085Z`. La muestra está en §10.

- **Revisión:** ningún UUID ni email, y ningún campo de negocio con el patrón de §7.5. El patrón anterior daba un falso positivo con `stock_`.
- **Clase `system`: no aparece en la muestra.** El paso Offline no quedó registrado y no se repite. `client_request_failed`, `frontend_error_captured`, `page_load_recorded:error` y `form_submitted:network_error` y `:server_error` están verificados en el efímero (§6.10).
- **`error_rate` 1.0 el 04/11:** ese día el único evento técnico es el `direct_stock_edit_rejected`, así que es 1 de 1. Es el efecto del denominador de D4: con pocos eventos, un solo error pesa mucho. No indica una caída.
- **La muestra no trae `/suppliers`.** Su `page_load_recorded` funciona (comprobado con el build de producción contra un stub), así que esa carga no llegó a la tabla: una visita de menos de 1 s, o un beacon perdido, no se puede distinguir desde aquí.
- **`form_validation_failed` sale 1 vez**, y la receta tenía dos pasos que lo emiten. No se han leído las filas: no se sabe cuál falta.

### 7.7 Doble `page_not_found_viewed`

Un solo 404 dio dos eventos, a 1 ms y con `eventId` distintos. **Es el doble efecto de StrictMode en `next dev`; en producción no ocurre.** No es un dato perdido ni un fallo del reporte.

| Modo | Eventos por un 404 |
|---|---|
| `next build` + `next start`, contra un stub local | **1** |
| `next dev --webpack`, contra el mismo stub | **2**, a 2 ms |

- **Causa:** `components/telemetry/not-found-tracker.tsx` emite en un `useEffect` sin guarda. Next activa Strict Mode por defecto con App Router (`reactStrictMode.md`), y en desarrollo React monta, desmonta y vuelve a montar cada efecto.
- **Por qué solo este evento:** `usePageLoadTelemetry` se protege con un `useRef`, `frontend_error_captured` tiene throttle, y `page_viewed` cancela su temporizador al limpiar.
- **Efecto real:** el stack de la demo corre `next dev`, así que **allí cada 404 cuenta doble**. Es lo que se ve en la muestra.
- **Corregido después, en una PR aparte** (rama `fix/not-found-telemetry-once`): la misma guarda con `useRef` que `usePageLoadTelemetry`, y un test. La muestra de §10 es anterior, y las filas dobles de la demo se quedan: la tabla es inmutable.

## 8. Lo que queda fuera o sin verificar

- **Lo que no se puede ver en la demo:** §7.3; lo cubre el efímero.
- **Latencia del reporte contra Supabase:** una conexión y 5 consultas por el pooler, sin medir.
- **`/telemetry` y `/telemetry/report` fuera de los enums** (C14): la página no consta en su propia telemetría.
- **P6:** cuando se emitan `api_latency_recorded`, `login_failed` y `user_logged_in`, cambian D4, D5 y D6.

## 9. Dashboard (Parada 4)

`/telemetry`: tablas y una barra de CSS por día, sin dependencias. Las capas y reglas están en `uis/backoffice/CLAUDE.md`.

**Comprobado con el build de producción, contra un stub local con el JSON de la demo** (sin tocar la API ni la demo): las 5 métricas con el periodo visible, tasas formateadas, estado de error con «Reintentar» ante un 500, y 375 px sin scroll horizontal (`scrollWidth` 375).

**Para verificar en el stack,** en `http://localhost:3001`. Cada visita lee la demo y no escribe nada: la página no emite telemetría (C14).

1. Sin sesión, `/telemetry` lleva a `/login`.
2. Con sesión, enlace «Telemetría» en la cabecera, marcado como activo.
3. Periodo visible y las 5 secciones con los datos del reporte.
4. Con la API parada (`docker compose stop api`) y entrando desde otra página sin recargar: error con «Reintentar». Después, `docker compose start api`, «Reintentar» y los datos.
5. A 375 px, sin scroll horizontal: las tablas se desplazan dentro de su marco.

**Verificado por el usuario el 2026-11-05, en el stack contra la demo:**

- **Con sesión:** enlace «Telemetría» en la cabecera, periodo en hora local con la nota de días UTC, y las 5 secciones con datos reales, entre ellas los logins fallidos, 3 de 6 (50 %).
- **Sin sesión:** lleva a `/login`.
- **API parada, entrando desde la cabecera sin recargar:** «Error del servidor. No se pudo calcular el reporte», con «Reintentar»: es el 500 del proxy de Next, coherente con C15. Con la API arrancada, «Reintentar» recupera los datos.
- **Al recargar con la API parada:** salta antes el control de sesión global («No se pudo comprobar la sesión»), como en el resto del backoffice.
- **375 px:** la página no se desplaza; solo las tablas anchas, dentro de su contenedor.

## 10. Borrador de la PR

Título: `feat: telemetry report endpoint`.

> Añade `GET /telemetry/report`: métricas técnicas de `telemetry_events` calculadas con Pandas, con caché de 60 s.
>
> **Por qué:** la tabla guarda eventos desde la PR #30, pero nadie podía saber si el colector recibe, qué falla o dónde esperan los operadores.
>
> **Métricas y pregunta que responde cada una:** tabla de §2.
>
> **Muestra de JSON real:** al final de este borrador. La clase `system` no aparece en ella: `client_request_failed`, `frontend_error_captured`, `page_load_recorded:error` y `form_submitted:network_error` y `:server_error` se verificaron en un Postgres efímero. `page_not_found_viewed` cuenta 2 por un solo 404, por el doble efecto de StrictMode en `next dev`: en producción es 1, y su arreglo va en una PR aparte. El `error_rate` de 1.0 del 04/11 es el efecto del denominador: ese día el único evento técnico fue el `direct_stock_edit_rejected`, así que es 1 de 1, no una caída.
>
> **Extras:** `auth_failure_rate`, hecho con `form_submitted`, porque `user_login_failed` y `user_login_succeeded` no existen en el catálogo y `login_failed` y `user_logged_in` aún no se emiten. Dashboard: hecho, en `/telemetry`, con tablas y una barra de CSS por día, sin dependencias nuevas.
>
> **Lo que el reporte no dice:**
> - `error_rate` es la proporción de eventos técnicos, no de peticiones: las correctas no se emiten.
> - La latencia es la espera en el navegador, no la de la API.
> - `auth_failure_rate` no ve lo que no pasa por el navegador.
>
> **Por qué las tasas salen con todos sus decimales:** la API no redondea. `test_architecture.py` prohíbe `round` en `app/`: el redondeo es una regla del núcleo y no se reimplementa en cada capa. Formatea quien presenta, y el valor exacto permite cuadrarlo con SQL.
>
> **Dependencia nueva (autorizada por el ticket):** `pandas` en `services/api`, con sus transitivas `numpy`, `python-dateutil` y `tzdata`.
>
> **Efecto en la imagen:** de 337 a 476 MB en disco (+29 MB comprimida), por Pandas y numpy. Hay que ejecutar `docker compose up -d --build` al cambiar a esta rama.
>
> **Verificación:** las 5 métricas cuadradas valor a valor con SQL a mano en un Postgres efímero, con un seed ficticio de varios días (`report-review.md` §6.10). En la demo, con eventos reales generados desde el backoffice: 200 en 0,82 s, sin identificadores ni campos de negocio.

**Muestra para la PR** (`GET /telemetry/report`, demo, 2026-11-05):

```json
{
  "period": {"from": "2026-10-29T23:39:03.085Z", "to": "2026-11-05T23:39:03.085Z"},
  "metrics": {
    "events_per_day": [
      {"day": "2026-10-29", "service": "backoffice", "events": 0},
      {"day": "2026-10-29", "service": "api", "events": 0},
      {"day": "2026-10-30", "service": "backoffice", "events": 0},
      {"day": "2026-10-30", "service": "api", "events": 0},
      {"day": "2026-10-31", "service": "backoffice", "events": 0},
      {"day": "2026-10-31", "service": "api", "events": 0},
      {"day": "2026-11-01", "service": "backoffice", "events": 0},
      {"day": "2026-11-01", "service": "api", "events": 0},
      {"day": "2026-11-02", "service": "backoffice", "events": 0},
      {"day": "2026-11-02", "service": "api", "events": 0},
      {"day": "2026-11-03", "service": "backoffice", "events": 0},
      {"day": "2026-11-03", "service": "api", "events": 0},
      {"day": "2026-11-04", "service": "backoffice", "events": 0},
      {"day": "2026-11-04", "service": "api", "events": 1},
      {"day": "2026-11-05", "service": "backoffice", "events": 55},
      {"day": "2026-11-05", "service": "api", "events": 0}
    ],
    "error_rate_by_type": [
      {"day": "2026-11-04", "error_type": "direct_stock_edit_rejected", "error_class": "rejected", "errors": 1, "total_events": 1, "error_rate": 1.0},
      {"day": "2026-11-05", "error_type": "form_submitted:api_rejected", "error_class": "rejected", "errors": 3, "total_events": 52, "error_rate": 0.057692307692307696},
      {"day": "2026-11-05", "error_type": "form_submitted:validation_error", "error_class": "rejected", "errors": 2, "total_events": 52, "error_rate": 0.038461538461538464},
      {"day": "2026-11-05", "error_type": "form_validation_failed", "error_class": "rejected", "errors": 1, "total_events": 52, "error_rate": 0.019230769230769232},
      {"day": "2026-11-05", "error_type": "page_not_found_viewed", "error_class": "rejected", "errors": 2, "total_events": 52, "error_rate": 0.038461538461538464}
    ],
    "page_load_latency_by_route": [
      {"day": "2026-11-05", "route_template": "/incident-manager", "outcome": "data", "loads": 1, "avg_ms": 259.0, "max_ms": 259.0},
      {"day": "2026-11-05", "route_template": "/inventory/orders", "outcome": "data", "loads": 1, "avg_ms": 523.0, "max_ms": 523.0},
      {"day": "2026-11-05", "route_template": "/inventory/products", "outcome": "data", "loads": 4, "avg_ms": 478.75, "max_ms": 674.0}
    ],
    "dominant_event_types": [
      {"event_type": "page_viewed", "service": "backoffice", "events": 21, "share": 0.375},
      {"event_type": "form_submitted", "service": "backoffice", "events": 10, "share": 0.17857142857142858},
      {"event_type": "form_started", "service": "backoffice", "events": 8, "share": 0.14285714285714285},
      {"event_type": "page_load_recorded", "service": "backoffice", "events": 6, "share": 0.10714285714285714},
      {"event_type": "form_abandoned", "service": "backoffice", "events": 3, "share": 0.05357142857142857},
      {"event_type": "page_not_found_viewed", "service": "backoffice", "events": 2, "share": 0.03571428571428571},
      {"event_type": "direct_stock_edit_rejected", "service": "api", "events": 1, "share": 0.017857142857142856},
      {"event_type": "form_validation_failed", "service": "backoffice", "events": 1, "share": 0.017857142857142856},
      {"event_type": "inbound_order_created", "service": "backoffice", "events": 1, "share": 0.017857142857142856},
      {"event_type": "outbound_order_created", "service": "backoffice", "events": 1, "share": 0.017857142857142856},
      {"event_type": "stock_threshold_triggered", "service": "backoffice", "events": 1, "share": 0.017857142857142856},
      {"event_type": "user_logged_out", "service": "backoffice", "events": 1, "share": 0.017857142857142856}
    ],
    "auth_failure_rate": [
      {"day": "2026-11-05", "failed": 3, "succeeded": 3, "attempts": 6, "failure_rate": 0.5}
    ]
  }
}
```
