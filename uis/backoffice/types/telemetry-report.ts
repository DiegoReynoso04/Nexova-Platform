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

// --- Cola de tareas (DEV-55, services/api/SPECS.md Parte J) --------------------
// `GET /telemetry/report` encola y responde 202 `{task_id}`; el reporte llega por
// `GET /tasks/{task_id}`, que se sondea hasta `success` o `failure`.

export const TASK_STATUSES = ['pending', 'started', 'success', 'failure'] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

/** Lo que interesa de `GET /tasks/{task_id}` para el reporte: el estado y, si terminó bien, el reporte. */
export type TelemetryReportTask =
  | { status: 'pending' }
  | { status: 'started' }
  | { status: 'success'; report: TelemetryReport }
  | { status: 'failure' };

export type TelemetryReportUiError =
  /** 503 al encolar o al sondear: Redis o el worker no están disponibles. */
  | { kind: 'queue_unavailable' }
  /** La tarea terminó en `failure` (reintentos agotados o error del cálculo). */
  | { kind: 'task_failed' }
  /** 404 de `/tasks/{id}` durante el sondeo: la tarea caducó o ya no existe. */
  | { kind: 'task_expired' }
  /** Tope de espera del sondeo (10 min) sin que la tarea termine. */
  | { kind: 'polling_timeout' }
  | { kind: 'request_invalid' }
  | { kind: 'server_error' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' }
  | { kind: 'session_expired' };
