// Servicio del reporte semanal: única capa que llama a `/reporting/…` (services/api/SPECS.md
// Parte I). Los componentes nunca hacen HTTP.
//
// Todo error que sale de aquí es `ReportingServiceError`, salvo la cancelación pedida por quien
// llama, que se propaga como `ApiAbortError`. Dos respuestas no son errores de la vista:
// 404 `week_not_computed` (la semana todavía no se calculó) y 404 `pipeline_run_not_found`
// (el pipeline aún no ha corrido). El resto de textos se eligen por tipo, no por el cuerpo.

import {
  ApiAbortError,
  ApiConfigError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiUnauthorizedError,
  ApiUnexpectedResponseError,
  apiClient,
  type ApiClient,
  type ApiResponse,
  type JsonValue,
} from '@/lib/api-client';
import { normalizeApiErrorBody, normalizePipelineRun, normalizeWeeklyPerformance } from '@/services/normalizers';
import type { PipelineRun, ReportingUiError, WeeklyPerformanceResult } from '@/types/reporting';

const WEEKLY_PATH = '/reporting/weekly-office-program-performance';
const LATEST_RUN_PATH = '/reporting/pipeline-runs/latest';
// Lecturas de una tabla pequeña: sin caché ni cálculo.
export const REPORTING_TIMEOUT_MS = 10_000;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export class ReportingServiceError extends Error {
  readonly uiError: ReportingUiError;

  constructor(uiError: ReportingUiError) {
    super(`Reporting service error: ${uiError.kind}`);
    this.name = 'ReportingServiceError';
    this.uiError = uiError;
  }
}

interface CallOptions {
  signal?: AbortSignal;
}

export interface WeeklyPerformanceOptions extends CallOptions {
  /** Lunes `YYYY-MM-DD`. Sin él, la API devuelve la última semana calculada. */
  weekStart?: string;
}

export interface ReportingService {
  getWeeklyPerformance(options?: WeeklyPerformanceOptions): Promise<WeeklyPerformanceResult>;
  /** `null` si el pipeline todavía no ha corrido. */
  getLatestPipelineRun(options?: CallOptions): Promise<PipelineRun | null>;
}

export interface ReportingServiceDependencies {
  client?: ApiClient;
  timeoutMs?: number;
}

function fail(uiError: ReportingUiError): ReportingServiceError {
  return new ReportingServiceError(uiError);
}

/** El `code` del cuerpo de error de la API, o `null` si el cuerpo no es el esperado. Nunca lanza por la forma. */
async function readErrorCode(response: ApiResponse): Promise<string | null> {
  try {
    return await response.json((body: JsonValue) => normalizeApiErrorBody(body).code);
  } catch (error) {
    if (error instanceof ApiUnexpectedResponseError) return null;
    throw error;
  }
}

async function failFromStatus(response: ApiResponse): Promise<never> {
  if (response.status === 503 && (await readErrorCode(response)) === 'storage_unavailable') {
    throw fail({ kind: 'storage_unavailable' });
  }
  if (response.status >= 500) throw fail({ kind: 'server_error' });
  if (response.status >= 400) throw fail({ kind: 'request_invalid' });
  throw fail({ kind: 'unexpected_response' });
}

async function readWeekly(response: ApiResponse): Promise<WeeklyPerformanceResult> {
  if (response.status === 200) return { status: 'computed', report: await response.json(normalizeWeeklyPerformance) };
  if (response.status === 404 && (await readErrorCode(response)) === 'week_not_computed') return { status: 'not_computed' };
  return failFromStatus(response);
}

async function readLatestRun(response: ApiResponse): Promise<PipelineRun | null> {
  if (response.status === 200) return response.json(normalizePipelineRun);
  if (response.status === 404 && (await readErrorCode(response)) === 'pipeline_run_not_found') return null;
  return failFromStatus(response);
}

export function createReportingService(dependencies: ReportingServiceDependencies = {}): ReportingService {
  const client = dependencies.client ?? apiClient;
  const timeoutMs = dependencies.timeoutMs ?? REPORTING_TIMEOUT_MS;

  async function guarded<T>(operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      if (error instanceof ReportingServiceError || error instanceof ApiAbortError) throw error;
      if (error instanceof ApiConfigError) throw fail({ kind: 'config' });
      // 401: el cliente ya borró el token; el guard de rutas redirige a /login.
      if (error instanceof ApiUnauthorizedError) throw fail({ kind: 'session_expired' });
      if (error instanceof ApiTimeoutError) throw fail({ kind: 'timeout' });
      if (error instanceof ApiNetworkError) throw fail({ kind: 'network' });
      throw fail({ kind: 'unexpected_response' });
    }
  }

  return {
    getWeeklyPerformance(options = {}) {
      const { weekStart, signal } = options;
      // La fecha va en la URL: solo con la forma de un lunes ISO, nunca texto libre.
      if (weekStart !== undefined && !ISO_DATE.test(weekStart)) return Promise.reject(fail({ kind: 'request_invalid' }));
      const path = weekStart === undefined ? WEEKLY_PATH : `${WEEKLY_PATH}?week_start=${weekStart}`;
      return guarded(() => client.get(path, { timeoutMs, signal }, readWeekly));
    },

    getLatestPipelineRun(options = {}) {
      return guarded(() => client.get(LATEST_RUN_PATH, { timeoutMs, signal: options.signal }, readLatestRun));
    },
  };
}

const defaultService = createReportingService();

export const getWeeklyPerformance: ReportingService['getWeeklyPerformance'] = (options) =>
  defaultService.getWeeklyPerformance(options);
export const getLatestPipelineRun: ReportingService['getLatestPipelineRun'] = (options) =>
  defaultService.getLatestPipelineRun(options);
