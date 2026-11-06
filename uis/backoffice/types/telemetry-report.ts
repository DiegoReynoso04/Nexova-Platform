// Reporte técnico de telemetría (`GET /telemetry/report`, services/api/SPECS.md §48).
// Solo agregados técnicos: ni identificadores ni dimensiones de negocio.

export const ERROR_CLASSES = ['system', 'rejected'] as const;
export type ErrorClass = (typeof ERROR_CLASSES)[number];

export interface EventsPerDayRow {
  day: string;
  service: string;
  events: number;
}

export interface ErrorRateRow {
  day: string;
  error_type: string;
  error_class: ErrorClass;
  errors: number;
  total_events: number;
  error_rate: number;
}

export interface PageLoadLatencyRow {
  day: string;
  route_template: string;
  outcome: string;
  loads: number;
  avg_ms: number;
  max_ms: number;
}

export interface DominantEventTypeRow {
  event_type: string;
  service: string;
  events: number;
  share: number;
}

export interface AuthFailureRateRow {
  day: string;
  failed: number;
  succeeded: number;
  attempts: number;
  failure_rate: number;
}

export interface TelemetryReport {
  /** UTC. `from` es inclusivo y `to`, exclusivo. */
  period: { from: string; to: string };
  metrics: {
    events_per_day: readonly EventsPerDayRow[];
    error_rate_by_type: readonly ErrorRateRow[];
    page_load_latency_by_route: readonly PageLoadLatencyRow[];
    dominant_event_types: readonly DominantEventTypeRow[];
    auth_failure_rate: readonly AuthFailureRateRow[];
  };
}

export type TelemetryReportUiError =
  | { kind: 'request_invalid' }
  | { kind: 'server_error' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' }
  | { kind: 'session_expired' };
