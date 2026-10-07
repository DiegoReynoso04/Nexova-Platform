# Carpeta `scripts`

Esta carpeta contiene **scripts auxiliares** del monorepo: automatizaciones de desarrollo, utilidades de mantenimiento, tareas repetitivas (setup, lint, migraciones, generación de datos, etc.) y tooling interno.

- **Propósito principal**: agrupar herramientas de soporte que no pertenecen a una app/agente/pipeline específico, pero facilitan el trabajo del equipo.
- **Recomendación**: documenta cada script (qué hace, parámetros, requisitos, ejemplos de uso) y procura que sean reproducibles (y seguros) en distintos entornos.

## Scripts de esta carpeta

| Script | Qué hace | Documentación |
|---|---|---|
| `analyze.py` | CLI del analizador de incidentes de Nexova (validación, métricas, exportación `results.csv`) | [`packages/incident-analyzer/README.md`](../packages/incident-analyzer/README.md) |
| `seed_incidents.py` | Carga el CSV de incidentes del helpdesk en el gestor centralizado de incidencias (idempotente; se ejecuta con el venv de `services/api`) | [`services/api/README.md`](../services/api/README.md#seed-de-datos-históricos-scriptsseed_incidentspy) |
