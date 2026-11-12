"""Ejecuta archivos `.sql` de consulta en una transacción de SOLO LECTURA y la deshace siempre.

    python -m business_performance.readonly ..\\..\\docs\\reporting\\demo-snapshot.sql    # desde data/pipelines

Para las fotos de la demo y el cuadre (`pipeline-check.sql`) sin `psql` ni la URL
en la terminal:

- **URL:** como el script del pipeline (D5): `DATABASE_URL` de la terminal o,
  si falta, esa sola clave del `.env` de la raíz. Se imprime de dónde salió y
  el host, nunca la URL.
- **Solo lectura garantizada por PostgreSQL:** la primera sentencia es
  `SET TRANSACTION READ ONLY`, así que cualquier escritura o DDL del archivo
  falla («cannot execute … in a read-only transaction»); y al final, siempre
  `ROLLBACK`. Válido con el Transaction pooler de Supabase (todo va en una
  transacción).
- **Formato:** las líneas que empiezan por `\\` (metacomandos de `psql`, como
  `\\set ON_ERROR_STOP on`) y los comentarios `--` se ignoran; las sentencias se
  separan por `;` al final de línea. Imprime cada resultado como una tabla.

Códigos de salida: 0 bien; 1 configuración o archivo; 2 la base falló o
rechazó una sentencia (solo se imprime la clase del error).
"""

from . import _bootstrap  # noqa: F401  (rutas de packages/shared y data/process)

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import ConfigError, DatabaseTarget, resolve_database_target
from .repository import build_engine

CONFIG_ERROR_EXIT = 1
DATABASE_ERROR_EXIT = 2
READ_ONLY = "SET TRANSACTION READ ONLY"


def statements(sql: str) -> list[str]:
    """Las sentencias del archivo, sin metacomandos de `psql` ni comentarios de línea."""
    kept: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("\\") or stripped.startswith("--"):
            continue
        kept.append(line)
    chunks: list[str] = []
    current: list[str] = []
    for line in kept:
        current.append(line)
        if line.rstrip().endswith(";"):
            chunks.append("\n".join(current).strip().rstrip(";").strip())
            current = []
    tail = "\n".join(current).strip()
    if tail:
        chunks.append(tail)
    return [chunk for chunk in chunks if chunk]


def _format(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    cells = [[("" if value is None else str(value)) for value in row] for row in rows]
    widths = [max([len(column), *(len(row[index]) for row in cells)]) for index, column in enumerate(columns)]
    lines = [" | ".join(column.ljust(width) for column, width in zip(columns, widths, strict=True))]
    lines.append("-+-".join("-" * width for width in widths))
    lines.extend(" | ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)) for row in cells)
    lines.append(f"({len(cells)} {'fila' if len(cells) == 1 else 'filas'})")
    return "\n".join(lines)


def run_readonly(engine, sql_statements: Sequence[str]) -> list[str]:
    """Ejecuta las sentencias en una transacción de solo lectura y la deshace. Devuelve las tablas."""
    outputs: list[str] = []
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(READ_ONLY))
            for statement in sql_statements:
                result = connection.execute(text(statement))
                if result.returns_rows:
                    outputs.append(_format(list(result.keys()), result.all()))
        finally:
            transaction.rollback()
    return outputs


def run(argv: Sequence[str] | None = None, target: DatabaseTarget | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m business_performance.readonly",
        description="Ejecuta archivos .sql de consulta en una transacción de solo lectura (siempre ROLLBACK).",
    )
    parser.add_argument("files", nargs="+", type=Path, help="Archivos .sql")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return CONFIG_ERROR_EXIT if exit_request.code else 0
    try:
        sql = [(path, statements(path.read_text(encoding="utf-8"))) for path in args.files]
    except OSError as error:
        print(f"Error: no se puede leer un archivo ({type(error).__name__}).", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    try:
        target = target if target is not None else resolve_database_target()
    except ConfigError as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    print(f"{target.describe()} (solo lectura, ROLLBACK al terminar)")
    engine = build_engine(target.url)
    try:
        for path, file_statements in sql:
            print(f"\n== {path.name}")
            for output in run_readonly(engine, file_statements):
                print(output, end="\n\n")
    except SQLAlchemyError as error:
        print(f"Error: la base falló o rechazó una sentencia ({type(error).__name__}). No se ha cambiado nada.",
              file=sys.stderr)
        return DATABASE_ERROR_EXIT
    finally:
        engine.dispose()
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
