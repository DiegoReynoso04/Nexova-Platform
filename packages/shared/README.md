# packages/shared

Código compartido entre subproyectos del monorepo. Contiene dos piezas independientes:

| Pieza | Lenguaje | Qué es |
|---|---|---|
| `types/` + `package.json` | TypeScript | `@repo/shared-types`: tipos de ejemplo de la plantilla (`BaseEntity`). Ninguna app lo usa todavía |
| `nexova_shared/` + `pyproject.toml` | Python ≥ 3.11, **solo librería estándar** | Lógica de validación compartida: el CSV de incidentes del helpdesk y el modelo del gestor centralizado de incidencias |

## `nexova_shared` (Python)

Es el único lugar con reglas de validación de incidencias. Sus consumidores son capas finas que lo importan:

- el analizador de incidentes [`packages/incident-analyzer`](../incident-analyzer/README.md) (y, a través de él, la CLI `scripts/analyze.py` y `POST /api/incidents/analyze` de `services/api`), que reexporta `incident_csv` sin cambios;
- el gestor centralizado de incidencias: el seed `scripts/seed_incidents.py` y la API de `services/api` (fases posteriores; ver `memory-bank/progress.md`).

| Módulo | Responsabilidad | Fuente |
|---|---|---|
| `incident_csv/schema.py` | Las 9 columnas del CSV, categorías y estados del helpdesk, las 7 reglas (`Rule`), `IncidentRow` | [`docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`](../../docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md) |
| `incident_csv/reader.py` | CSV → `IncidentRow` (valores con `strip()`); `IncidentFileError` con mensajes sin contenido | ídem |
| `incident_csv/validation.py` | `validate_row` → `ValidationResult` (número de fila + reglas); `parse_score` | ídem |
| `incidents/vocabulary.py` | `IncidentStatus`, `IncidentOrigin`, `IncidentCategory`, `Branch` y sus etiquetas (`BRANCH_LABELS`), `TITLE_MAX_LENGTH` = 120 | [`docs/centralized-incident-manager.md`](../../docs/centralized-incident-manager.md) |
| `incidents/rules.py` | `validate_incident_fields` (obligatorios, valores permitidos, título ≤ 120, campos desconocidos) → `IncidentDraft` o `IncidentValidationError` con un `FieldError(field, error, message)` por problema; ciclo de vida (`ALLOWED_TRANSITIONS`, `can_transition`, `check_transition`) | ídem |
| `incidents/csv_mapping.py` | Mapeo CSV → modelo (estados, categorías, `description` → `title`, `date` → `created_at` a medianoche UTC, `origin` = `customer`, `branch` = `central`), clave de idempotencia (`ticket_id` o `title + created_at`) y `prepare_seed_batch`, que separa cada fila en cargable, inválida (7 reglas), no mapeable o duplicada | ídem |

Reglas del paquete:

- **Solo librería estándar** (sin pydantic ni frameworks web; lo comprueba `tests/test_source.py`). La API envuelve estas reglas con sus propios modelos; no las reimplementa.
- **Privacidad:** ningún módulo imprime ni registra; los mensajes de error nunca repiten el valor recibido; `IncidentRow`, `IncidentDraft` y `SeedIncident` no muestran valores en `repr`. `customer_email`, `client_company`, `agent_id` y `satisfaction_score` del CSV no pasan al modelo.
- **Valores exactos:** categorías, estados, orígenes y sedes se comparan sin recortar espacios ni ignorar mayúsculas, como exige el CONTEXT ("exactamente uno de estos valores").
- `status` es opcional al validar y por defecto `open`; `allowed_statuses` limita los admitidos (la API solo admite `open` al crear; el seed admite los cuatro).

```python
from nexova_shared.incidents import validate_incident_fields, IncidentValidationError, check_transition, prepare_seed_batch

draft = validate_incident_fields({"title": "…", "description": "…", "category": "sla_breach", "origin": "branch", "branch": "miami_office"})

with open("incidents.csv", encoding="utf-8-sig", newline="") as stream:
    batch = prepare_seed_batch(stream)   # batch.incidents / .invalid / .unmapped / .duplicates
```

### Instalación

No hace falta instalarlo para los tests ni para la CLI del analizador: `incident_analyzer` añade `packages/shared` a `sys.path` si `nexova_shared` no está en el entorno. En el venv de `services/api` se instala junto al resto, **siempre en la misma orden**:

```bash
python -m pip install -e packages/shared -e packages/incident-analyzer -e "services/api[dev]"
```

Igual que el núcleo del analizador, `nexova-shared` **no** se declara como dependencia en ningún `pyproject.toml`: el nombre está libre en PyPI y declararlo haría que pip lo buscase allí (*dependency confusion*).

### Tests

```bash
# Desde la raíz del monorepo, con cualquier Python ≥ 3.11
python -m unittest discover -s packages/shared/tests -t packages/shared
```

- `test_contract.py` lee `docs/centralized-incident-manager.md` y comprueba enumerados, etiquetas de sede, transiciones, mapeos, el límite de 120 caracteres y los "Valores esperados tras el seed" (27/56/13 y 49/35/12) con el fixture sintético de aceptación del analizador (`packages/incident-analyzer/tests/fixtures/incidents-acceptance-synthetic.csv`). El CSV real no está en el repositorio.
- `test_rules.py`: campos obligatorios, valores permitidos y las 16 combinaciones de transición.
- `test_csv_mapping.py`: recorte del título, título vacío, fechas inválidas, claves de idempotencia, duplicados y privacidad.
- `test_source.py`: solo librería estándar, sin `print`/`logging`, y que el analizador reexporta los mismos objetos (no tiene copia propia).
