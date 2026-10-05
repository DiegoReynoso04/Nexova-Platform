// Servicio de análisis de incidentes: única capa que llama al cliente HTTP para
// esta funcionalidad (los componentes nunca lo hacen). Contrato:
// services/api/SPECS.md §3 y §4.
//
// Todo error que sale de aquí es `IncidentServiceError` (con un `UiError`
// seguro para mostrar), salvo la cancelación pedida por quien llama, que se
// propaga como `ApiAbortError` porque no es un fallo que mostrar.
//
// Privacidad: el archivo nunca se lee en JavaScript (va tal cual en FormData),
// el CSV exportado no se interpreta, y solo el `detail` de `invalid_csv`
// (seguro por contrato: cita columnas o números de fila) llega a la UI.

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
} from '@/lib/api-client';
import { normalizeAnalysisResponse, normalizeApiErrorBody } from '@/services/normalizers';
import type { AnalysisResult, ApiErrorBody, UiError } from '@/types/incidents';

const ANALYZE_PATH = '/api/incidents/analyze';
const EXPORT_PATH = '/api/incidents/results/export';
const DEFAULT_EXPORT_FILENAME = 'results.csv';

export const ANALYZE_TIMEOUT_MS = 30_000;
export const EXPORT_TIMEOUT_MS = 15_000;

/**
 * Prevalidación de UX, NO el límite real. El límite lo impone la API sobre el
 * body HTTP completo (1 MiB por defecto, configurable en el servidor; SPECS §3.1)
 * y su 413 es siempre la fuente de verdad. El margen cubre las cabeceras y
 * delimitadores del multipart que añade el navegador.
 */
export const API_DEFAULT_BODY_LIMIT_BYTES = 1_048_576;
export const CLIENT_SIZE_MARGIN_BYTES = 4_096;
export const CLIENT_MAX_FILE_BYTES = API_DEFAULT_BODY_LIMIT_BYTES - CLIENT_SIZE_MARGIN_BYTES;

/** Error del servicio con un `UiError` seguro. El mensaje solo lleva el tipo de error. */
export class IncidentServiceError extends Error {
  readonly uiError: UiError;

  constructor(uiError: UiError) {
    super(`Incident service error: ${uiError.kind}`);
    this.name = 'IncidentServiceError';
    this.uiError = uiError;
  }
}

export interface ExportedResults {
  blob: Blob;
  analysisId: string;
  filename: string;
}

export interface CallOptions {
  signal?: AbortSignal;
}

export interface IncidentsService {
  analyzeIncidentFile(file: File, options?: CallOptions): Promise<AnalysisResult>;
  exportIncidentResults(expectedAnalysisId: string, options?: CallOptions): Promise<ExportedResults>;
}

export interface IncidentsServiceDependencies {
  client?: ApiClient;
  /** Solo para tests; en producción se usan ANALYZE_TIMEOUT_MS y EXPORT_TIMEOUT_MS. */
  timeouts?: { analyzeMs: number; exportMs: number };
}

// ---------------------------------------------------------------------------
// Traducción de errores
// ---------------------------------------------------------------------------

function fail(uiError: UiError): IncidentServiceError {
  return new IncidentServiceError(uiError);
}

/**
 * Status + `{code, detail}` de la API → `UiError`. Manda el status; el `code`
 * solo distingue dentro de 400 y 404. Ningún texto de la API sale de aquí,
 * salvo el `detail` de `invalid_csv`.
 */
export function uiErrorFromHttp(status: number, body: ApiErrorBody): UiError {
  if (status === 413) return { kind: 'file_too_large' };
  if (status === 415) return { kind: 'unsupported_file_type' };
  if (status >= 500) return { kind: 'server_error' };
  if (status === 400 && body.code === 'invalid_csv') return { kind: 'invalid_csv', detail: body.detail ?? '' };
  if (status === 404 && body.code === 'no_analysis') return { kind: 'no_analysis' };
  // bad_request, validation_error (422), not_found, method_not_allowed y cualquier
  // otro 4xx o código desconocido.
  if (status >= 400) return { kind: 'request_invalid' };
  // 1xx/2xx/3xx inesperados para esta operación.
  return { kind: 'unexpected_response' };
}

/** Lee `{code, detail}` si el cuerpo es JSON; si no, sigue solo con el status. */
async function readErrorBody(response: ApiResponse): Promise<ApiErrorBody> {
  try {
    return await response.json(normalizeApiErrorBody);
  } catch (error) {
    if (error instanceof ApiUnexpectedResponseError) return { code: null, detail: null };
    throw error;
  }
}

async function failFromResponse(response: ApiResponse): Promise<never> {
  throw fail(uiErrorFromHttp(response.status, await readErrorBody(response)));
}

/** Ejecuta una operación y garantiza que solo salen IncidentServiceError o ApiAbortError. */
async function guarded<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof IncidentServiceError || error instanceof ApiAbortError) throw error;
    if (error instanceof ApiConfigError) throw fail({ kind: 'config' });
    // 401: el cliente ya borró el token; el guard de rutas redirige a /login.
    if (error instanceof ApiUnauthorizedError) throw fail({ kind: 'session_expired' });
    if (error instanceof ApiTimeoutError) throw fail({ kind: 'timeout' });
    if (error instanceof ApiNetworkError) throw fail({ kind: 'network' });
    // UnexpectedResponseError (normalizador: 200 que no cumple el contrato),
    // ApiUnexpectedResponseError (no es JSON) o cualquier fallo no previsto.
    // Nunca se reenvía el texto del error original.
    throw fail({ kind: 'unexpected_response' });
  }
}

// ---------------------------------------------------------------------------
// Prevalidación y nombre de descarga
// ---------------------------------------------------------------------------

/** Solo UX: extensión y tamaño. El contenido lo valida el backend. */
export function precheckFile(file: File): UiError | null {
  if (!file.name.trim().toLowerCase().endsWith('.csv')) return { kind: 'unsupported_file_type' };
  if (file.size > CLIENT_MAX_FILE_BYTES) return { kind: 'file_too_large' };
  return null;
}

const SAFE_FILENAME = /^[A-Za-z0-9][A-Za-z0-9._ -]{0,99}$/;

/**
 * Nombre de descarga a partir de `Content-Disposition`. Solo se usa como nombre
 * del archivo descargado (nunca como ruta): se queda con el último segmento,
 * exige caracteres seguros y extensión `.csv`; si no, `results.csv`.
 */
export function safeDownloadFilename(contentDisposition: string | null): string {
  if (contentDisposition === null) return DEFAULT_EXPORT_FILENAME;
  const match = /filename\s*=\s*(?:"([^"]*)"|([^;]*))/i.exec(contentDisposition);
  const raw = (match?.[1] ?? match?.[2] ?? '').trim();
  const baseName = raw.split(/[\\/]/).pop()?.trim() ?? '';
  if (!SAFE_FILENAME.test(baseName) || !baseName.toLowerCase().endsWith('.csv') || baseName.includes('..')) {
    return DEFAULT_EXPORT_FILENAME;
  }
  return baseName;
}

// ---------------------------------------------------------------------------
// Servicio
// ---------------------------------------------------------------------------

export function createIncidentsService(dependencies: IncidentsServiceDependencies = {}): IncidentsService {
  const client = dependencies.client ?? apiClient;
  const analyzeMs = dependencies.timeouts?.analyzeMs ?? ANALYZE_TIMEOUT_MS;
  const exportMs = dependencies.timeouts?.exportMs ?? EXPORT_TIMEOUT_MS;

  return {
    analyzeIncidentFile(file, options = {}) {
      return guarded(async () => {
        const precheckError = precheckFile(file);
        if (precheckError !== null) throw fail(precheckError);

        const form = new FormData();
        form.append('file', file, file.name);

        return client.postForm(ANALYZE_PATH, form, { timeoutMs: analyzeMs, signal: options.signal }, async (response) => {
          if (response.status !== 200) return failFromResponse(response);
          return response.json(normalizeAnalysisResponse);
        });
      });
    },

    exportIncidentResults(expectedAnalysisId, options = {}) {
      return guarded(() =>
        client.get(EXPORT_PATH, { timeoutMs: exportMs, signal: options.signal }, async (response) => {
          if (response.status !== 200) return failFromResponse(response);

          // Se comprueba antes de descargar el cuerpo: si el servidor tiene otro
          // análisis (otra sesión, reinicio), no se descarga nada.
          const analysisId = response.header('X-Analysis-Id')?.trim() ?? '';
          if (analysisId === '' || expectedAnalysisId.trim() === '' || analysisId !== expectedAnalysisId) {
            throw fail({ kind: 'export_mismatch' });
          }

          const filename = safeDownloadFilename(response.header('Content-Disposition'));
          const blob = await response.blob();
          return { blob, analysisId, filename };
        })
      );
    },
  };
}

const defaultService = createIncidentsService();

export function analyzeIncidentFile(file: File, options?: CallOptions): Promise<AnalysisResult> {
  return defaultService.analyzeIncidentFile(file, options);
}

export function exportIncidentResults(expectedAnalysisId: string, options?: CallOptions): Promise<ExportedResults> {
  return defaultService.exportIncidentResults(expectedAnalysisId, options);
}
