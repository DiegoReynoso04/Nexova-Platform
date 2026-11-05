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
| Extra 2: dashboard | `uis/backoffice` | Pendiente: va tras la Parada 3 |

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

## 7. Lo que queda fuera o sin verificar

- **`frontend_error_captured` y `page_load_recorded` con `error` en la demo:** solo en el efímero (D13).
- **Latencia del reporte contra Supabase:** una conexión y 5 consultas por el pooler, sin medir.
- **C15:** pendiente de §6.8.
- **`/telemetry` y `/telemetry/report` fuera de los enums** (C14): la página no consta en su propia telemetría.
- **P6:** cuando se emitan `api_latency_recorded`, `login_failed` y `user_logged_in`, cambian D4, D5 y D6.

## 8. Borrador de la PR

Título: `feat: telemetry report endpoint`. Falta la muestra de JSON real (Parada 3) y el dashboard (Parada 4).

> Añade `GET /telemetry/report`: métricas técnicas de `telemetry_events` calculadas con Pandas, con caché de 60 s.
>
> **Por qué:** la tabla guarda eventos desde la PR #30, pero nadie podía saber si el colector recibe, qué falla o dónde esperan los operadores.
>
> **Métricas y pregunta que responde cada una:** tabla de §2.
>
> **Muestra de JSON real:** _pendiente (Parada 3)._
>
> **Extras:** `auth_failure_rate`, hecho con `form_submitted`, porque `user_login_failed` y `user_login_succeeded` no existen en el catálogo y `login_failed` y `user_logged_in` aún no se emiten. Dashboard: _pendiente (Parada 4)._
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
> **Verificación:** _pendiente (Paradas 2 y 3)._
