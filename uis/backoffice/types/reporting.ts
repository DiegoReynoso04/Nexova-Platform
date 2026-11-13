// Reporte semanal de desempeño por oficina y programa (`/reporting`).
// Contrato: services/api/SPECS.md Parte I (`GET /reporting/weekly-office-program-performance` y
// `GET /reporting/pipeline-runs/latest`) y BRIEFING §4/§6. Solo se leen los campos que la vista
// necesita: de la última corrida, ni la fase, ni los contadores, ni `error_class`.

export const REPORT_OFFICES = ['valencia', 'miami'] as const;
export type Office = (typeof REPORT_OFFICES)[number];

export const REPORT_CURRENCIES = ['EUR', 'USD'] as const;
export type Currency = (typeof REPORT_CURRENCIES)[number];

/** La moneda de cada oficina (BRIEFING §4): nunca se convierte ni se suma entre oficinas. */
export const CURRENCY_BY_OFFICE: Readonly<Record<Office, Currency>> = { valencia: 'EUR', miami: 'USD' };

/** Centinela del programa mientras la clasificación de activos (P1) no exista (D1 del diseño). */
export const UNASSIGNED_PROGRAMME = '_unassigned';

export interface WeeklyPerformanceEntry {
  office: Office;
  programme_id: string;
  /** Número JSON sin redondear (la API no redondea). */
  total_material_cost: number;
  kits_delivered_count: number;
  shortage_events_count: number;
  cost_variance_events_count: number;
  currency: Currency;
}

export interface WeeklyPerformance {
  /** Lunes de la semana (UTC), `YYYY-MM-DD`. */
  week_start: string;
  entries: readonly WeeklyPerformanceEntry[];
}

/** `GET /reporting/weekly-office-program-performance`: la semana, o «todavía no calculada» (404). */
export type WeeklyPerformanceResult = { status: 'computed'; report: WeeklyPerformance } | { status: 'not_computed' };

export const RUN_STATUSES = ['running', 'completed', 'failed'] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

/** Lo que la franja de frescura usa de la última corrida. */
export interface PipelineRun {
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  /** Semanas que cubrió la corrida (lunes, `YYYY-MM-DD`). */
  week_from: string;
  week_to: string;
}

export type ReportingUiError =
  | { kind: 'request_invalid' }
  | { kind: 'server_error' }
  | { kind: 'storage_unavailable' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' }
  | { kind: 'session_expired' };
