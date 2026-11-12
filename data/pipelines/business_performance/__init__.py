"""Soporte del pipeline de desempeño de negocio (el flow y sus tasks están en `../pipeline.py`).

- `_bootstrap`: analítica de Prefect desactivada y rutas del monorepo (antes de importar Prefect).
- `config`: de dónde sale la URL de la base y qué host se imprime (D5).
- `repository`: la SQL de extracción, carga y log (`reporting.pipeline_runs`).
- `migrate`: el esquema `reporting` (DDL), con la guarda `--allow-demo`.
- `serve`: el worker de Compose (deployments `manual` y `weekly`).
- `trigger`: el disparo manual por la REST de Prefect. **Solo librería
  estándar**: es lo único de este paquete que importa la API.

Este `__init__` no importa nada: la API solo copia `__init__.py` y `trigger.py`.

Diseño: `data/pipelines/PIPELINE_DESIGN.md`; decisiones: `docs/reporting/implementation-analysis.md`.
"""
