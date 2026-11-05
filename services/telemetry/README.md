# `services/telemetry`

Análisis de la tabla `telemetry_events` con Pandas: las métricas técnicas de `GET /telemetry/report`.

**No es un servicio desplegable.** Es una librería de la API de Nexova ([`services/api`](../api/README.md)): corre dentro de su proceso y usa su modelo de la tabla (`TelemetryEventRecord`). Vive aquí porque el ticket evalúa la ruta `services/telemetry/analysis.py` (D1 de [`docs/telemetry/report-analysis.md`](../../docs/telemetry/report-analysis.md)).

- **Dónde corre:** la imagen la copia junto a `app/`, en `/app/api/telemetry`, y Compose la monta encima para recargar sin reconstruir. Se importa como `telemetry`.
- **Dependencias:** Pandas se declara en `services/api/pyproject.toml`. Esta carpeta no tiene `pyproject.toml` propio.
- **Tests:** en `services/api/tests/`, con la validación de `services/api` (`AGENTS.md` §4). `tests/__init__.py` pone `services/` en `sys.path`.
