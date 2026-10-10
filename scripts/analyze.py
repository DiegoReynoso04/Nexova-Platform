"""CLI del análisis de incidentes de soporte de Nexova.

Capa fina sobre `packages/incident-analyzer`: argumentos, impresión, pregunta
de exportación y códigos de salida. Toda la lógica de negocio vive en el
paquete; aquí no se valida ni se calcula nada.

Uso:
    python scripts/analyze.py <ruta/al/archivo.csv>              # interactivo
    python scripts/analyze.py <archivo.csv> --export [--output out.csv]
    python scripts/analyze.py <archivo.csv> --no-export

Códigos de salida: 0 correcto, 1 archivo ilegible o inválido, 2 argumentos.
"""

import argparse
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

# Funciona sin instalar el paquete: si no está en el entorno, se usa la copia
# del monorepo.
if importlib.util.find_spec("incident_analyzer") is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "incident-analyzer"))

from incident_analyzer import IncidentFileError, analyze_file, render_report, write_results_csv  # noqa: E402

DEFAULT_OUTPUT = "results.csv"
EXPORT_PROMPT = "Export results to CSV? [y / n]: "


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nexova — support ticket analysis of an incidents CSV file.")
    parser.add_argument("csv_file", help="path to the incidents CSV file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--export",
        dest="export",
        action="store_const",
        const=True,
        default=None,
        help="export results without asking (non-interactive)",
    )
    mode.add_argument(
        "--no-export",
        dest="export",
        action="store_const",
        const=False,
        help="do not export and do not ask (non-interactive)",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"export path (default: {DEFAULT_OUTPUT})")
    return parser.parse_args(argv)


def supports_unicode(stream: TextIO) -> bool:
    try:
        "├└—".encode(stream.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def describe_os_error(error: OSError) -> str:
    """`strerror` puede ser `None` (OSError sin errno): entonces, el nombre de la clase."""
    return error.strerror or type(error).__name__


def ask_export() -> bool:
    while True:
        try:
            answer = input(EXPORT_PROMPT).strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Fin de entrada o Ctrl+C en la pregunta: el reporte ya se mostró;
            # se trata como "no exportar" y el análisis termina con éxito.
            print()
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        result = analyze_file(args.csv_file)
    except IncidentFileError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: cannot read {args.csv_file}: {describe_os_error(error)}", file=sys.stderr)
        return 1

    print(render_report(result, Path(args.csv_file).name, ascii_only=not supports_unicode(sys.stdout)))

    should_export = ask_export() if args.export is None else args.export
    if should_export:
        try:
            write_results_csv(result, args.output)
        except OSError as error:
            print(f"error: cannot write {args.output}: {describe_os_error(error)}", file=sys.stderr)
            return 1
        print(f"Results exported to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
