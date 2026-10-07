"""Lectura del CSV a `IncidentRow`.

Los mensajes de `IncidentFileError` citan solo nombres de columna o números de
fila, nunca contenido del archivo: pueden acabar en consola o en una respuesta
HTTP.
"""

import csv
from collections.abc import Iterable, Iterator

from .schema import FIELDS, IncidentRow

HEADER_ROW_NUMBER = 1


class IncidentFileError(Exception):
    """El archivo no se puede analizar. El mensaje es seguro de mostrar."""


def read_rows(lines: Iterable[str]) -> Iterator[IncidentRow]:
    """Recorre las filas de datos; la primera fila de datos es la número 2.

    Espera líneas ya decodificadas y abiertas con `newline=""` (ver módulo
    `csv`). Una fila con menos columnas que la cabecera se completa con
    valores vacíos, que las reglas de validación marcarán; las columnas
    sobrantes se ignoran. Las líneas totalmente en blanco no cuentan.
    """
    reader = csv.reader(lines)
    row_number = HEADER_ROW_NUMBER
    try:
        header = next(reader, None)
        if header is None:
            raise IncidentFileError("the file is empty: no header row found")

        columns = [name.strip() for name in header]
        missing = [field for field in FIELDS if field not in columns]
        if missing:
            raise IncidentFileError(f"missing required columns: {', '.join(missing)}")
        positions = {field: columns.index(field) for field in FIELDS}

        for record in reader:
            if not record:
                continue
            row_number += 1
            values = {
                field: record[index].strip() if index < len(record) else ""
                for field, index in positions.items()
            }
            yield IncidentRow(row_number=row_number, **values)
    except csv.Error:
        # El mensaje de csv.Error no incluye datos, pero no lo reenviamos: el
        # nuestro es suficiente y no depende de la versión de Python.
        raise IncidentFileError(f"malformed CSV after row {row_number}") from None
