"""Núcleo de análisis del CSV de incidentes de soporte de Nexova.

Contexto funcional: docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md.
Solo librería estándar. Ningún módulo imprime ni registra: el reporte y la
exportación se devuelven como texto o se escriben donde indique quien llama.

La lectura y la validación del CSV viven en `packages/shared`
(`nexova_shared.incident_csv`), compartidas con el seed del gestor de
incidencias; este paquete las reexporta sin cambios.
"""

import importlib.util
import sys
from pathlib import Path

# Funciona sin instalar `nexova_shared` (tests y CLI desde la raíz del
# monorepo): si no está en el entorno, se usa la copia del monorepo.
if importlib.util.find_spec("nexova_shared") is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from .analyze import analyze_binary_stream, analyze_file, analyze_stream  # noqa: E402
from .export import ExportMetric, build_export_metrics, render_results_csv, write_results_csv  # noqa: E402
from .metrics import (  # noqa: E402
    AnalysisResult,
    CategoryCount,
    RuleCount,
    SatisfactionSummary,
    ScoreCount,
    StatusCount,
)
from .reader import IncidentFileError  # noqa: E402
from .report import render_report  # noqa: E402
from .schema import Category, IncidentRow, Rule, Status  # noqa: E402
from .validation import ValidationResult, validate_row  # noqa: E402

__all__ = [
    "AnalysisResult",
    "Category",
    "CategoryCount",
    "ExportMetric",
    "IncidentFileError",
    "IncidentRow",
    "Rule",
    "RuleCount",
    "SatisfactionSummary",
    "ScoreCount",
    "Status",
    "StatusCount",
    "ValidationResult",
    "analyze_binary_stream",
    "analyze_file",
    "analyze_stream",
    "build_export_metrics",
    "render_report",
    "render_results_csv",
    "validate_row",
    "write_results_csv",
]
