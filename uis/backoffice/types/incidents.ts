// Contrato que recibe el frontend de la API de análisis de incidentes.
// Fuente: services/api/SPECS.md §3 (y services/api/app/modules/incidents/schemas.py).
// Prohibido añadir campos que no estén en ese contrato.
//
// Los `code` son `string`, no uniones cerradas: el vocabulario del dominio
// (reglas, categorías, estados) pertenece al núcleo Python y no se duplica
// aquí. Porcentajes y media llegan como string decimal ya redondeado por el
// backend (D-API-2) y se muestran tal cual; `null` = no calculable.

export interface Totals {
  total_records: number;
  valid_records: number;
  /** Filas distintas. La suma de `invalid_breakdown` puede ser mayor. */
  invalid_records: number;
}

/** Una de las 7 reglas de invalidación, en el orden del backend. */
export interface RuleBreakdownItem {
  code: string;
  label: string;
  count: number;
}

/** Entrada de una distribución sobre registros válidos (categorías o estados). */
export interface DistributionItem {
  code: string;
  count: number;
  percentage: string | null;
}

/** 5 categorías, en el orden del backend. */
export type CategoryResult = DistributionItem;

/** 3 estados, en el orden del backend. */
export type StatusResult = DistributionItem;

/** Una de las puntuaciones 1–5. */
export interface SatisfactionDistributionItem {
  score: number;
  label: string;
  count: number;
}

export interface SatisfactionResult {
  closed_tickets: number;
  scored_tickets: number;
  average_score: string | null;
  distribution: readonly SatisfactionDistributionItem[];
}

export interface ExportInfo {
  available: boolean;
  url: string;
  filename: string;
  format: string;
}

/** Respuesta 200 de `POST /api/incidents/analyze`. Solo agregados: ningún dato de filas. */
export interface AnalysisResult {
  analysis_id: string;
  analyzed_at: string;
  totals: Totals;
  invalid_breakdown: readonly RuleBreakdownItem[];
  categories: readonly CategoryResult[];
  statuses: readonly StatusResult[];
  satisfaction: SatisfactionResult;
  export: ExportInfo;
}

/**
 * Campos seguros extraídos de un cuerpo de error `{detail, code}` de la API.
 * `detail` solo se conserva si es un string (el 422 lo envía como lista y se
 * descarta). Mostrar `detail` al usuario solo está permitido para `invalid_csv`.
 */
export interface ApiErrorBody {
  code: string | null;
  detail: string | null;
}

/**
 * Errores que la UI sabe presentar. Solo `invalid_csv` transporta texto de la
 * API (su `detail` es seguro: cita columnas o números de fila, nunca valores).
 * El resto se muestra con mensajes fijos en español.
 */
export type UiError =
  | { kind: 'invalid_csv'; detail: string }
  | { kind: 'unsupported_file_type' }
  | { kind: 'file_too_large' }
  | { kind: 'request_invalid' }
  | { kind: 'no_analysis' }
  | { kind: 'server_error' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' }
  | { kind: 'session_expired' }
  | { kind: 'export_mismatch' };
