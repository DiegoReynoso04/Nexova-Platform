"""Seed del gestor centralizado de incidencias: carga el histórico del CSV del helpdesk.

Capa fina: la lectura, las 7 reglas del analizador y el mapeo CSV → modelo son
de `nexova_shared` (packages/shared); la escritura (idempotente por el SHA-256
de `ticket_id`) es del repositorio de `services/api`. Aquí solo se traducen
argumentos, se imprime el informe y se devuelve el código de salida. Ninguna
fila se inserta tal cual y el informe nunca muestra contenido de las filas:
solo números de fila y códigos de regla.

Contexto: docs/centralized-incident-manager.md ("Datos históricos — seed desde CSV").

Uso (con el venv de services/api, desde la raíz del monorepo):
    services/api/.venv/Scripts/python scripts/seed_incidents.py [ruta/al.csv] [--db ruta/incidents.json]

Sin ruta se lee data/raw/incidents/incidents-nexova.csv (ignorado por git).
Sin --db se usa INCIDENTS_DB_PATH o services/api/data/incidents.json.

Códigos de salida: 0 correcto; 1 CSV inexistente, ilegible o con una cabecera
sin las columnas del analizador; 2 argumentos, configuración o entorno incorrectos.
"""

import argparse
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "data" / "raw" / "incidents" / "incidents-nexova.csv"
VENV_HINT = "run it with the services/api virtualenv (see services/api/README.md)"

# Funciona sin instalar los paquetes del monorepo: si no están en el entorno, se
# usan las copias del repositorio. tinydb y pydantic sí deben estar instalados
# (venv de services/api).
for module, folder in (("nexova_shared", REPO_ROOT / "packages" / "shared"), ("app", REPO_ROOT / "services" / "api")):
    if importlib.util.find_spec(module) is None:
        sys.path.insert(0, str(folder))

try:
    from nexova_shared.incident_csv import IncidentFileError, Rule
    from nexova_shared.incidents import SeedBatch, prepare_seed_batch

    from app.core.config import ConfigError, Settings
    from app.modules.incident_manager.repository import IncidentRepository, SeedResult
except ModuleNotFoundError as missing:
    print(f"error: missing module {missing.name!r}; {VENV_HINT}", file=sys.stderr)
    sys.exit(2)

# utf-8-sig acepta el archivo con o sin BOM, igual que el analizador.
CSV_ENCODING = "utf-8-sig"
_RULE_ORDER = list(Rule)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nexova — load the helpdesk incidents CSV into the centralized incident manager."
    )
    parser.add_argument(
        "csv_file", nargs="?", type=Path, default=DEFAULT_CSV, help=f"incidents CSV (default: {DEFAULT_CSV})"
    )
    parser.add_argument("--db", type=Path, default=None, help="TinyDB file (default: INCIDENTS_DB_PATH)")
    return parser.parse_args(argv)


def read_batch(csv_file: Path) -> SeedBatch:
    """Lee y transforma el CSV. Lanza `IncidentFileError` u `OSError`."""
    with csv_file.open(encoding=CSV_ENCODING, newline="") as stream:
        try:
            return prepare_seed_batch(stream)
        except UnicodeDecodeError:
            pass
    # Fuera del `except`: el error original guarda los bytes leídos.
    raise IncidentFileError("the file is not valid UTF-8")


def render_report(batch: SeedBatch, result: SeedResult, csv_name: str, db_path: Path) -> str:
    lines = [
        f"Archivo CSV: {csv_name}",
        f"Base de datos: {db_path}",
        f"Filas leídas: {batch.total_rows}",
        f"Insertadas: {result.inserted}",
        f"Ya existentes (omitidas): {result.existing}",
        f"Inválidas (no insertadas): {len(batch.invalid)}",
    ]
    for invalid in batch.invalid:
        rules = ", ".join(rule.code for rule in sorted(invalid.violations, key=_RULE_ORDER.index))
        lines.append(f"  - fila {invalid.row_number}: {rules}")
    lines.append(f"No mapeables (no insertadas): {len(batch.unmapped)}")
    for unmapped in batch.unmapped:
        lines.append(f"  - fila {unmapped.row_number}: {', '.join(sorted(unmapped.issues))}")
    lines.append(f"Duplicadas en el archivo (no insertadas): {len(batch.duplicates)}")
    for row_number in batch.duplicates:
        lines.append(f"  - fila {row_number}")
    lines.append(f"Total de incidencias en la base: {result.total}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.csv_file.is_file():
        print(f"error: CSV file not found: {args.csv_file}", file=sys.stderr)
        return 1
    try:
        db_path = args.db if args.db is not None else Settings.from_env().incidents_db_path
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        batch = read_batch(args.csv_file)
    except IncidentFileError as error:
        # Mensajes del lector compartido: solo nombres de columna o números de fila.
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: cannot read {args.csv_file}: {error.strerror}", file=sys.stderr)
        return 1

    result = IncidentRepository(db_path).seed(batch.incidents)
    print(render_report(batch, result, args.csv_file.name, db_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
