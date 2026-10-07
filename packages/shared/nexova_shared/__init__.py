"""Lógica de validación compartida de Nexova. Solo librería estándar.

- `nexova_shared.incident_csv`: el CSV de incidentes del helpdesk (esquema,
  lectura y las 7 reglas de registros inválidos).
- `nexova_shared.incidents`: el modelo del gestor centralizado de incidencias
  (vocabulario, reglas de campos, ciclo de vida y mapeo CSV → modelo).

Ningún módulo imprime ni registra, y ningún mensaje de error repite valores
recibidos: quien llama decide qué mostrar.
"""
