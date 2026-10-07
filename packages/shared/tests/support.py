"""Utilidades de test. Solo datos ficticios (`example.invalid`)."""

import re
from functools import cache
from pathlib import Path

from nexova_shared.incident_csv import IncidentRow

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
SOURCE_DIR = PACKAGE_ROOT / "nexova_shared"
CONTEXT = REPO_ROOT / "docs" / "centralized-incident-manager.md"
# Fixture sintético de aceptación del analizador: 100 filas, 96 válidas.
ACCEPTANCE_FIXTURE = (
    REPO_ROOT / "packages" / "incident-analyzer" / "tests" / "fixtures" / "incidents-acceptance-synthetic.csv"
)
HEADER = "ticket_id,date,client_company,category,description,agent_id,status,customer_email,satisfaction_score"


def make_row(row_number: int = 2, **overrides: str) -> IncidentRow:
    """Una fila válida (OPEN, sin score); `overrides` cambia campos concretos."""
    values = {
        "ticket_id": "NXV-000001",
        "date": "2026-08-01",
        "client_company": "Synthetic Client",
        "category": "TECHNICAL",
        "description": "Synthetic ticket: printer not responding",
        "agent_id": "AGT-07",
        "status": "OPEN",
        "customer_email": "someone@example.invalid",
        "satisfaction_score": "",
    }
    values.update(overrides)
    return IncidentRow(row_number=row_number, **values)


def csv_lines(*rows: IncidentRow) -> list[str]:
    """Serializa filas (sin comas ni comillas en los valores) a líneas CSV con cabecera."""
    fields = HEADER.split(",")
    return [HEADER + "\n", *(",".join(getattr(row, field) for field in fields) + "\n" for row in rows)]


@cache
def context_text() -> str:
    return CONTEXT.read_text(encoding="utf-8")


def context_table(marker: str) -> list[list[str]]:
    """Filas de datos de la primera tabla Markdown que sigue a la línea `marker` del CONTEXT.

    Cada celda sin espacios ni comillas invertidas en los extremos.
    """
    lines = context_text().splitlines()
    start = lines.index(marker)
    rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip().strip("`").strip() for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r"-+", cell) for cell in cells):
            continue
        rows.append(cells)
    # La primera fila es la cabecera de la tabla.
    return rows[1:]


def context_values(marker: str) -> list[str]:
    """Primera columna de la tabla que sigue a `marker`."""
    return [row[0] for row in context_table(marker)]
