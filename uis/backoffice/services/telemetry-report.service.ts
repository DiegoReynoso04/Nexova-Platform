// Servicio del reporte técnico: única capa que llama a `GET /telemetry/report` y a
// `GET /tasks/{task_id}` (services/api/SPECS.md §48 y Parte J). Los componentes nunca
// hacen HTTP.
//
// Desde DEV-55 el reporte es asíncrono: `requestTelemetryReport` lo encola (202 con
// el id de la tarea) y `getTelemetryReportTask` lee su estado; el sondeo lo hace la
// sesión del hook (`hooks/use-telemetry-report.ts`).
//
// Todo error que sale de aquí es `TelemetryReportServiceError`, salvo la
// cancelación pedida por quien llama, que se propaga como `ApiAbortError`.
// La página usa la ventana por defecto de la API: los últimos 7 días.

import {
  ApiAbortError,
  ApiConfigError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiUnauthorizedError,
  apiClient,
  type ApiClient,
  type ApiResponse,
} from '@/lib/api-client';
import { normalizeTaskAccepted, normalizeTelemetryReportTask } from '@/services/normalizers';
import type { TelemetryReportTask, TelemetryReportUiError } from '@/types/telemetry-report';

const REPORT_PATH = '/telemetry/report';
const TASKS_PATH = '/tasks';
// Encolar y leer un estado son respuestas inmediatas (el cálculo lo hace el worker).
export const REQUEST_TIMEOUT_MS = 10_000;

export class TelemetryReportServiceError extends Error {
  readonly uiError: TelemetryReportUiError;

  constructor(uiError: TelemetryReportUiError) {
    super(`Telemetry report service error: ${uiError.kind}`);
    this.name = 'TelemetryReportServiceError';
    this.uiError = uiError;
  }
}

interface CallOptions {
  signal?: AbortSignal;
}

export interface TelemetryReportService {
  /** Encola el reporte. Devuelve el id de la tarea. */
  requestTelemetryReport(options?: CallOptions): Promise<string>;
  /** Estado de la tarea y, si terminó bien, el reporte. */
  getTelemetryReportTask(taskId: string, options?: CallOptions): Promise<TelemetryReportTask>;
}

export interface TelemetryReportServiceDependencies {
  client?: ApiClient;
  timeoutMs?: number;
}

function fail(uiError: TelemetryReportUiError): TelemetryReportServiceError {
  return new TelemetryReportServiceError(uiError);
}

function failForStatus(status: number): TelemetryReportServiceError {
  if (status === 503) return fail({ kind: 'queue_unavailable' });
  if (status >= 500) return fail({ kind: 'server_error' });
  if (status >= 400) return fail({ kind: 'request_invalid' });
  return fail({ kind: 'unexpected_response' });
}

async function readAccepted(response: ApiResponse): Promise<string> {
  if (response.status === 202) return response.json(normalizeTaskAccepted);
  throw failForStatus(response.status);
}

function readTask(taskId: string) {
  return async (response: ApiResponse): Promise<TelemetryReportTask> => {
    if (response.status === 200) return response.json((body) => normalizeTelemetryReportTask(body, taskId));
    // 404 durante el sondeo: la tarea caducó o ya no existe (SPECS §56).
    if (response.status === 404) throw fail({ kind: 'task_expired' });
    throw failForStatus(response.status);
  };
}

/** Ejecuta la petición y traduce cualquier error del cliente a `TelemetryReportServiceError`. */
async function translated<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (error) {
    if (error instanceof TelemetryReportServiceError || error instanceof ApiAbortError) throw error;
    if (error instanceof ApiConfigError) throw fail({ kind: 'config' });
    // 401: el cliente ya borró el token; el guard de rutas redirige a /login.
    if (error instanceof ApiUnauthorizedError) throw fail({ kind: 'session_expired' });
    if (error instanceof ApiTimeoutError) throw fail({ kind: 'timeout' });
    if (error instanceof ApiNetworkError) throw fail({ kind: 'network' });
    throw fail({ kind: 'unexpected_response' });
  }
}

export function createTelemetryReportService(dependencies: TelemetryReportServiceDependencies = {}): TelemetryReportService {
  const client = dependencies.client ?? apiClient;
  const timeoutMs = dependencies.timeoutMs ?? REQUEST_TIMEOUT_MS;

  return {
    requestTelemetryReport(options = {}) {
      return translated(() => client.get(REPORT_PATH, { timeoutMs, signal: options.signal }, readAccepted));
    },

    getTelemetryReportTask(taskId, options = {}) {
      const path = `${TASKS_PATH}/${encodeURIComponent(taskId)}`;
      return translated(() => client.get(path, { timeoutMs, signal: options.signal }, readTask(taskId)));
    },
  };
}

const defaultService = createTelemetryReportService();

export const requestTelemetryReport: TelemetryReportService['requestTelemetryReport'] = (options) =>
  defaultService.requestTelemetryReport(options);
export const getTelemetryReportTask: TelemetryReportService['getTelemetryReportTask'] = (taskId, options) =>
  defaultService.getTelemetryReportTask(taskId, options);
