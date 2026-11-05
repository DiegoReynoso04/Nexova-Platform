// Servicio del reporte técnico: única capa que llama a `GET /telemetry/report`
// (services/api/SPECS.md §48). Los componentes nunca hacen HTTP.
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
import { normalizeTelemetryReport } from '@/services/normalizers';
import type { TelemetryReport, TelemetryReportUiError } from '@/types/telemetry-report';

const REPORT_PATH = '/telemetry/report';
// La primera llamada calcula 5 métricas contra la base; después sale de la caché.
export const REPORT_TIMEOUT_MS = 15_000;

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
  getTelemetryReport(options?: CallOptions): Promise<TelemetryReport>;
}

export interface TelemetryReportServiceDependencies {
  client?: ApiClient;
  timeoutMs?: number;
}

function fail(uiError: TelemetryReportUiError): TelemetryReportServiceError {
  return new TelemetryReportServiceError(uiError);
}

async function readReport(response: ApiResponse): Promise<TelemetryReport> {
  if (response.status === 200) return response.json(normalizeTelemetryReport);
  if (response.status >= 500) throw fail({ kind: 'server_error' });
  if (response.status >= 400) throw fail({ kind: 'request_invalid' });
  throw fail({ kind: 'unexpected_response' });
}

export function createTelemetryReportService(dependencies: TelemetryReportServiceDependencies = {}): TelemetryReportService {
  const client = dependencies.client ?? apiClient;
  const timeoutMs = dependencies.timeoutMs ?? REPORT_TIMEOUT_MS;

  return {
    async getTelemetryReport(options = {}) {
      try {
        return await client.get(REPORT_PATH, { timeoutMs, signal: options.signal }, readReport);
      } catch (error) {
        if (error instanceof TelemetryReportServiceError || error instanceof ApiAbortError) throw error;
        if (error instanceof ApiConfigError) throw fail({ kind: 'config' });
        // 401: el cliente ya borró el token; el guard de rutas redirige a /login.
        if (error instanceof ApiUnauthorizedError) throw fail({ kind: 'session_expired' });
        if (error instanceof ApiTimeoutError) throw fail({ kind: 'timeout' });
        if (error instanceof ApiNetworkError) throw fail({ kind: 'network' });
        throw fail({ kind: 'unexpected_response' });
      }
    },
  };
}

const defaultService = createTelemetryReportService();

export const getTelemetryReport: TelemetryReportService['getTelemetryReport'] = (options) => defaultService.getTelemetryReport(options);
