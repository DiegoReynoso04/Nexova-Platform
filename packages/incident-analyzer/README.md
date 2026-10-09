# incident-analyzer

Núcleo de análisis del CSV de incidentes de soporte de **Nexova** (servicio de outsourcing de soporte al cliente — contacto: Roberto Díaz, Customer Support Lead). Valida cada ticket con las reglas del contexto, calcula las métricas y genera el reporte de consola y la exportación `metric,value`.

Fuente de verdad funcional: [`docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md`](../../docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md).

Es el **único** lugar con lógica de análisis (métricas, reporte y exportación). La **lectura y validación del CSV** (esquema, las 7 reglas) viven desde el gestor centralizado de incidencias en [`packages/shared`](../shared/README.md) (`nexova_shared.incident_csv`), que también usa el seed `scripts/seed_incidents.py`; este paquete las reexporta sin cambios (`incident_analyzer.validate_row`, `incident_analyzer.reader.read_rows`… siguen funcionando). Sus consumidores son capas finas encima: la CLI [`scripts/analyze.py`](../../scripts/analyze.py) y la API HTTP [`services/api`](../../services/api/README.md). Cualquier otro consumidor debe importar este paquete en vez de reimplementar reglas o métricas. El paquete no depende de ningún framework web.

## Requisitos

Python 3.11 o superior. **Solo librería estándar** — sin dependencias de ejecución ni de test (`unittest`). Necesita `nexova_shared` (`packages/shared`): si no está instalado en el entorno, el paquete añade `packages/shared` a `sys.path` al importarse, así que los tests y la CLI siguen funcionando desde la raíz sin instalar nada.

## Uso

```bash
# Desde la raíz del monorepo (no hace falta instalar nada)
python scripts/analyze.py ruta/al/incidents-nexova.csv            # interactivo: pregunta si exportar
python scripts/analyze.py ruta/al/archivo.csv --export            # exporta a ./results.csv sin preguntar
python scripts/analyze.py ruta/al/archivo.csv --export --output out/metrics.csv
python scripts/analyze.py ruta/al/archivo.csv --no-export         # ni exporta ni pregunta (CI)
```

Códigos de salida: `0` correcto, `1` archivo ilegible o inválido (cabecera sin columnas requeridas, no UTF-8, CSV malformado) o resultado que no se puede escribir, `2` argumentos incorrectos. Ctrl+C o el fin de entrada en la pregunta de exportar equivalen a responder `n` (el análisis termina con `0`).

Si la consola no puede codificar los caracteres de caja (`cp1252` en Windows al redirigir la salida), el reporte usa automáticamente una variante ASCII.

## API pública

```python
from incident_analyzer import analyze_file, render_report, render_results_csv, write_results_csv

result = analyze_file("incidents-nexova.csv")
# o analyze_binary_stream(stream_binario)  — p. ej. UploadFile.file en la API
# o analyze_stream(lineas_de_texto_ya_decodificadas)
print(render_report(result, "incidents-nexova.csv"))
write_results_csv(result, "results.csv")
```

| Módulo | Responsabilidad |
|---|---|
| `schema.py` | Reexporta de `nexova_shared.incident_csv.schema` campos, categorías, estados, las 7 reglas (`Rule`) e `IncidentRow`; define solo las etiquetas de puntuación (son del reporte) |
| `reader.py` | Reexporta `read_rows` / `IncidentFileError` de `nexova_shared.incident_csv.reader` (CSV → `IncidentRow`, valores con `strip()`, mensajes sin contenido) |
| `validation.py` | Reexporta `validate_row` → `ValidationResult` (número de fila + reglas) y `parse_score` de `nexova_shared.incident_csv.validation` |
| `metrics.py` | `MetricsAccumulator` → `AnalysisResult` (solo conteos, `Decimal` + ROUND_HALF_UP) |
| `analyze.py` | Orquestación: leer → validar → agregar. `analyze_binary_stream` decodifica bytes (UTF-8 con BOM opcional, sin cerrar el stream) y `analyze_file` la reutiliza |
| `report.py` | Texto del reporte de consola |
| `export.py` | Métricas exportables y CSV `metric,value` con protección contra formula injection |

## Reglas de negocio implementadas

- **Inválido** = activa al menos una de las 7 reglas del contexto. `invalid_records` cuenta filas; el desglose cuenta activaciones (una fila puede activar varias, así que la suma del desglose puede ser mayor).
- Solo esas 7 reglas invalidan: `ticket_id`, `date` o `status` fuera de formato **no** invalidan. Un válido con un `status` distinto de `OPEN`/`CLOSED`/`DISCARDED` cuenta en categorías pero no en el desglose por estado.
- Todos los valores se comparan tras `strip()`; categorías y estados distinguen mayúsculas (`closed` no es `CLOSED`: la fila no activa "CLOSED sin score" y no entra en el desglose por estado ni en la satisfacción). `agent_id` debe cumplir `AGT-\d{2}` (dígitos ASCII). Email inválido = vacío o sin `@`.
- `satisfaction_score`: cualquier valor presente que no sea un entero ASCII 1–5 (`0`, `6`, `4.5`, `4.0`, `abc`, `+4`) activa "fuera de rango". `CLOSED` sin valor activa "CLOSED sin score". Una puntuación válida en `OPEN`/`DISCARDED` se admite pero no entra en el índice de satisfacción.
- Porcentajes sobre registros válidos con 1 decimal; media con 2 decimales; ambos con redondeo half-up.

## Privacidad

`customer_email` nunca sale del paquete: ni en el reporte, ni en `results.csv`, ni en `ValidationResult`, ni en mensajes de error. `IncidentRow` redefine `repr`/`str` para no mostrar valores, `AnalysisResult` solo contiene conteos, y ningún módulo imprime ni registra. `tests/test_privacy.py` verifica todo lo anterior.

El dataset real **no se versiona**: colócalo en `data/raw/incidents/` (ignorado por git).

## Tests

```bash
# Desde la raíz del monorepo
python -m unittest discover -s packages/incident-analyzer/tests -t packages/incident-analyzer
```

- `tests/fixtures/incidents-synthetic.csv` — fixture sintético de 13 filas con emails ficticios `example.invalid`.
- `tests/fixtures/incidents-acceptance-synthetic.csv` + `tests/test_acceptance_synthetic.py` — **fixture sintético de aceptación** (100 filas, no son datos de Nexova) que reproduce exactamente las cifras del contexto; se ejecuta siempre. Detalle en `tests/fixtures/README.md`.
- `tests/test_acceptance.py` — comprueba las cifras exactas del contexto (100 / 96 / 4, etc.) contra el dataset real. Aparece como **skipped (PENDING)** mientras `data/raw/incidents/incidents-nexova.csv` no exista; otra ruta se puede indicar con `NEXOVA_INCIDENTS_CSV`.
