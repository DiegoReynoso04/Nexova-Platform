"""Lectura del CSV a `IncidentRow`.

Vive en `nexova_shared.incident_csv.reader` (`packages/shared`), compartida con
el seed del gestor de incidencias; aquí solo se reexporta.
"""

from nexova_shared.incident_csv.reader import HEADER_ROW_NUMBER, IncidentFileError, read_rows

__all__ = ["HEADER_ROW_NUMBER", "IncidentFileError", "read_rows"]
