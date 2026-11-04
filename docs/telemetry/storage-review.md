# Almacenamiento de telemetría: guía de revisión

Rama `feature/telemetry-storage`. Decisiones en [`storage-analysis.md`](./storage-analysis.md) (F0) y en el plan, §1.6 ([`telemetry-plan.md`](./telemetry-plan.md)). Contrato: `services/api/SPECS.md`, Parte H (§45 y §47).

## 1. Qué se ha hecho, frente a lo que se evalúa

| Criterio del enunciado | Dónde | Estado |
|---|---|---|
| Tabla con 8 columnas e índices en `timestamp`, `event_type` y GIN en `tags` | `app/modules/telemetry/models.py`, `migrate.py` | Hecho. La PK es un cuarto índice |
| Sin `UPDATE` ni `DELETE` | Ningún camino en la API; `REVOKE` en la base; `test_no_code_updates_or_deletes_telemetry_events` | Hecho |
| Bulk insert: una operación por lote | `collector.py` (`insert_statement`, `store_rows`) | Hecho: `executemany=False` y un grupo `VALUES` por fila |
| Rechazo individual | `collector.py` (`_frontend_row`) | Hecho |
| `TelemetryEvent` sin cambios | `schemas.py:1-66` | Hecho: ver el `diff` de §3 |
| Frontend sin cambios | — | Hecho: `git diff main --stat -- uis/` vacío |
| `event_type`, `timestamp` y `tags` poblados en eventos técnicos y de negocio | `test_telemetry_storage.py` | Hecho en la suite; falta la verificación en el navegador (§4) |
| `tags` conserva las allowlists y las dimensiones del BRIEFING | `allowlists.py`, comparada con el JSON | Hecho; `product_category` y `programme_id` se guardan como JSON `null` |

**El esquema es decisión nuestra:** el enunciado anuncia la estructura y el mapeo, pero no los incluye. Solo fija `event_type`, `timestamp`, `service` y `tags`.

## 2. Decisiones que conviene mirar en la revisión

- **Más de 50 eventos y `events: []` responden 200** (D11, literal del enunciado). El plan decía «de 1 a 50».
- **La base caída responde 503, no 200** (D10): un 200 con todo en `rejected` perdería el lote sin reintento.
- **Un duplicado cuenta como `stored`** (D9): `stored` no es el número de filas nuevas; ese dato está en el log.
- **La clave extra se quita de `properties`, pero rechaza en el envelope** (D6): una es la allowlist y la otra, `extra="forbid"`.
- **`direct_stock_edit_rejected` se guarda con un insert síncrono** (D8): si la base cae, bloquea el bucle de eventos hasta 5 s, como ya hacía la lectura de la oficina. El throttle lo acota.
- **Los 4 obligatorios del frontend se pueden falsificar** por la ruta pública (C15): riesgo aceptado, plan §8.4.

## 3. Validación

Desde la raíz, además de las suites (`AGENTS.md` §4):

```bash
python scripts/validate_event_schemas.py
```

```bash
F=services/api/app/modules/telemetry/schemas.py; diff <(git show main:$F | sed -n '1,/^        return value/p') <(sed -n '1,/^        return value/p' $F) && echo "TelemetryEvent sin cambios"
```

```bash
git diff main --stat -- uis/
```

**Migración en el efímero** (2026-11-04), con el rol `nexova_app`, sin superusuario:

- `--dry-run`: las 6 sentencias, sin crear nada; aplicar, en una transacción; segunda ejecución: «Nada que migrar».
- 8 columnas, 4 índices, el `CHECK` y RLS activo. `SELECT` e `INSERT` sí; `UPDATE`, `DELETE` y `TRUNCATE`, `permission denied`.
- `ON CONFLICT DO NOTHING`: `rowcount` 1 y luego 0. `\u0000` en JSONB: rechazado por PostgreSQL.
- **Rol como el de la demo** (`BYPASSRLS`, con `anon`, `authenticated` y `service_role` heredando privilegios): el `REVOKE` alcanza a los cuatro.
- **Negativas:** con un superusuario, código 1; con un rol con `pg_write_all_data`, código 1 y todo deshecho.

**Rol de la demo** (consultas de solo lectura, 2026-11-04): `postgres`, `rolsuper = false`, `rolbypassrls = true`, no es miembro de `pg_write_all_data`.

## 4. Recorrido (Fase 3)

**El lote mixto, solo en un Postgres efímero:** en la demo dejaría filas falsas que la API no puede borrar. Sin Docker Desktop en marcha no hay efímero.

### 4.1 Recorrido real

En `http://localhost:3001`, con `TELEMETRY_SUPPLIER_KEY` cargada en la API (sin ella no se emite `inbound_order_created`):

1. Inicia sesión y navega por Inicio → Activos → Entrada → Salida → Historial.
2. Haz una Entrada con coste y una Salida. Las cantidades y los costes los eliges tú.
3. Espera 10 s o cambia de pestaña. En Network: `POST /backend/telemetry/events` → 200 `{"received": N, "stored": N, "rejected": 0}`.
4. Provoca el evento de la API:

```bash
curl -i -X PUT http://localhost:3001/backend/inventory/products/1
```

Esperado: 405, y una fila con `service = 'api'`. Un segundo intento en menos de 60 s lo suprime el throttle.

### 4.2 Lote mixto

Ids fijos a propósito: repetirlo comprueba la deduplicación. Datos ficticios. El lote está en [`storage-analysis.md`](./storage-analysis.md) §5.4.

**Esperado:** `200 {"received": 10, "stored": 3, "rejected": 7}`; repetido, la misma respuesta y el mismo número de filas.

### 4.3 Cuerpos límite

```bash
curl -s -w ' [%{http_code}]\n' -X POST http://localhost:3001/backend/telemetry/events -H 'Content-Type: application/json' -d '{"events": []}'
```

Esperado: `{"received":0,"stored":0,"rejected":0} [200]`.

```bash
curl -s -w ' [%{http_code}]\n' -X POST http://localhost:3001/backend/telemetry/events -H 'Content-Type: application/json' -d '{"events": [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]}'
```

Esperado: `{"received":51,"stored":0,"rejected":51} [200]`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:3001/backend/telemetry/events -H 'Content-Type: application/json' -d '{}'
```

Esperado: `422`. Igual con `{"events": "x"}`, `{"events": [], "sent_at": "now"}` y `no-es-json`.

### 4.4 Consultas

```sql
SELECT event_type, timestamp, service, user_id, session_id, schema_version, tags FROM telemetry_events ORDER BY timestamp DESC LIMIT 20;
SELECT service, event_type, count(*) FROM telemetry_events GROUP BY 1, 2 ORDER BY 1, 2;
SELECT event_type, tags ->> 'office' AS office, tags ->> 'currency' AS currency, tags -> 'quantity' AS quantity, tags ? 'product_category' AS has_category, tags ? 'programme_id' AS has_programme FROM telemetry_events WHERE tags ? 'office';
SELECT count(*) FROM telemetry_events WHERE tags ? 'email';
```

La última debe dar 0. `tags ? 'product_category'` debe ser verdadero aunque el valor sea `null`.

## 5. Base de la demo

Solo con la confirmación del usuario y **antes** de que el stack normal cargue este código: sin la tabla, los lotes dan 500 y se pierden. Desde `services/api`, con la `DATABASE_URL` de la demo:

```bash
python -m app.modules.telemetry.migrate --dry-run
```

```bash
python -m app.modules.telemetry.migrate
```

Comprobaciones de solo lectura:

```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'telemetry_events' ORDER BY 1;
SELECT relrowsecurity FROM pg_class WHERE relname = 'telemetry_events';
SELECT r, p, has_table_privilege(r, 'telemetry_events', p) FROM unnest(ARRAY['postgres', 'anon', 'authenticated', 'service_role']) AS r, unnest(ARRAY['UPDATE', 'DELETE', 'TRUNCATE']) AS p;
```

**Reversión** (solo si hiciera falta, y borra lo guardado): `DROP TABLE telemetry_events;`.

## 6. Lo que queda fuera o sin verificar

- **Alertas, lote nocturno y agregados** (plan §7.3).
- **Retención:** fecha límite y condición en el plan, §8.3; sin automatizar.
- **Latencia del insert por el pooler de Supabase:** sin medir.
- **El throttle y el cupo anónimo:** estimaciones sin datos reales.
- **P1, P2, P5 y P6 completo.** `request_id` no se guarda.
- **Un lote con eventos anteriores al login**, enviado después, queda atribuido al usuario que acaba de entrar.
