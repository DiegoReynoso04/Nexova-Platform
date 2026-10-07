// Servicio del gestor centralizado de incidencias: única capa que llama al
// cliente HTTP para esta funcionalidad (los componentes nunca lo hacen).
// Contrato: services/api/SPECS.md Parte E (§30–§32).
//
// Todo error que sale de aquí es `IncidentServiceError` (con un
// `IncidentUiError` para mostrar), salvo la cancelación pedida por quien
// llama, que se propaga como `ApiAbortError` porque no es un fallo que mostrar.
//
// Mensajes: la API responde 400 con `{code, detail: [{field, error, message}]}`.
// El `message` del servidor nunca llega a la UI: el normalizador lo descarta y
// aquí se elige un texto propio en español por `code`, `field` y `error`.
//
// Validación en cliente: campos obligatorios y título ≤ 120 (UX, antes de
// enviar). Si no pasa, no hay petición de red. La API sigue siendo la autoridad.

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
import {
  normalizeIncident,
  normalizeIncidentApiError,
  normalizeIncidentList,
  normalizeIncidentSummary,
} from '@/services/normalizers';
import {
  INITIAL_INCIDENT_STATUS,
  TITLE_MAX_LENGTH,
  type Incident,
  type IncidentApiError,
  type IncidentField,
  type IncidentFieldError,
  type IncidentFilters,
  type IncidentFormValues,
  type IncidentStatus,
  type IncidentSummary,
  type IncidentUiError,
} from '@/types/incident-manager';

const INCIDENTS_PATH = '/api/incidents';
const SUMMARY_PATH = `${INCIDENTS_PATH}/summary`;
export const INCIDENTS_TIMEOUT_MS = 10_000;

/** Error del servicio con un `IncidentUiError`. El mensaje solo lleva el tipo de error. */
export class IncidentServiceError extends Error {
  readonly uiError: IncidentUiError;

  constructor(uiError: IncidentUiError) {
    super(`Incident service error: ${uiError.kind}`);
    this.name = 'IncidentServiceError';
    this.uiError = uiError;
  }
}

export interface CallOptions {
  signal?: AbortSignal;
}

export interface IncidentManagerService {
  listIncidents(filters: IncidentFilters, options?: CallOptions): Promise<Incident[]>;
  getIncidentSummary(options?: CallOptions): Promise<IncidentSummary>;
  createIncident(values: IncidentFormValues, options?: CallOptions): Promise<Incident>;
  changeIncidentStatus(id: string, status: IncidentStatus, options?: CallOptions): Promise<Incident>;
}

export interface IncidentManagerServiceDependencies {
  client?: ApiClient;
  /** Solo para tests; en producción se usa INCIDENTS_TIMEOUT_MS. */
  timeoutMs?: number;
}

// ---------------------------------------------------------------------------
// Textos en español (propios del frontend)
// ---------------------------------------------------------------------------

/** Mensaje de campo obligatorio, el mismo en cliente y para los 400 `missing`/`blank`. */
export const REQUIRED_MESSAGES: Readonly<Record<IncidentField, string>> = {
  title: 'Escribe un título.',
  description: 'Describe la incidencia.',
  category: 'Selecciona una categoría.',
  status: 'El estado inicial debe ser «open».',
  origin: 'Selecciona el origen del reporte.',
  branch: 'Selecciona la sede.',
};

export const TITLE_TOO_LONG_MESSAGE = `El título no puede superar los ${TITLE_MAX_LENGTH} caracteres.`;

const INCIDENT_FIELDS: readonly IncidentField[] = ['title', 'description', 'category', 'status', 'origin', 'branch'];

function isIncidentField(value: string): value is IncidentField {
  return INCIDENT_FIELDS.some((field) => field === value);
}

/** Texto en español para un error de la API, elegido por campo y código (nunca el `message` del servidor). */
export function messageForApiError(field: string, error: string): IncidentFieldError {
  if (!isIncidentField(field)) {
    return {
      field: null,
      message:
        error === 'invalid_body'
          ? 'La solicitud enviada no es válida. Recarga la página e inténtalo de nuevo.'
          : 'La solicitud incluye un dato que no se admite.',
    };
  }
  switch (error) {
    case 'missing':
    case 'blank':
      return { field, message: REQUIRED_MESSAGES[field] };
    case 'too_long':
      return { field, message: field === 'title' ? TITLE_TOO_LONG_MESSAGE : 'El texto es demasiado largo.' };
    case 'invalid_choice':
      return {
        field,
        message: field === 'status' ? REQUIRED_MESSAGES.status : 'Selecciona una de las opciones de la lista.',
      };
    case 'invalid_transition':
      return { field, message: 'Ese cambio de estado no está permitido.' };
    default:
      return { field, message: 'El valor no es válido.' };
  }
}

// ---------------------------------------------------------------------------
// Validación en cliente, body y query
// ---------------------------------------------------------------------------

/** Obligatorios y título ≤ 120 caracteres (tras recortar espacios). Devuelve [] si se puede enviar. */
export function validateIncidentForm(values: IncidentFormValues): IncidentFieldError[] {
  const errors: IncidentFieldError[] = [];
  const title = values.title.trim();
  if (title === '') errors.push({ field: 'title', message: REQUIRED_MESSAGES.title });
  else if (title.length > TITLE_MAX_LENGTH) errors.push({ field: 'title', message: TITLE_TOO_LONG_MESSAGE });
  if (values.description.trim() === '') errors.push({ field: 'description', message: REQUIRED_MESSAGES.description });
  if (values.category === '') errors.push({ field: 'category', message: REQUIRED_MESSAGES.category });
  if (values.origin === '') errors.push({ field: 'origin', message: REQUIRED_MESSAGES.origin });
  if (values.branch === '') errors.push({ field: 'branch', message: REQUIRED_MESSAGES.branch });
  return errors;
}

/**
 * Body de `POST /api/incidents`, construido campo a campo. `status` es siempre
 * el inicial (`open`), el que el formulario muestra en solo lectura. Nunca
 * incluye `id` ni fechas: los genera el sistema.
 */
export function buildIncidentPayload(values: IncidentFormValues): { [key: string]: JsonValue } {
  return {
    title: values.title.trim(),
    description: values.description.trim(),
    category: values.category,
    status: INITIAL_INCIDENT_STATUS,
    origin: values.origin,
    branch: values.branch,
  };
}

/** `?status=…&origin=…&branch=…` solo con los filtros activos. */
export function incidentsQuery(filters: IncidentFilters): string {
  const params = new URLSearchParams();
  if (filters.status !== null) params.set('status', filters.status);
  if (filters.origin !== null) params.set('origin', filters.origin);
  if (filters.branch !== null) params.set('branch', filters.branch);
  const query = params.toString();
  return query === '' ? INCIDENTS_PATH : `${INCIDENTS_PATH}?${query}`;
}

// ---------------------------------------------------------------------------
// Traducción de errores
// ---------------------------------------------------------------------------

function fail(uiError: IncidentUiError): IncidentServiceError {
  return new IncidentServiceError(uiError);
}

async function readErrorBody(response: ApiResponse): Promise<IncidentApiError> {
  try {
    return await response.json(normalizeIncidentApiError);
  } catch (error) {
    if (error instanceof ApiUnexpectedResponseError) return { code: null, errors: [] };
    throw error;
  }
}

/** Status + cuerpo de error → `IncidentUiError`. Manda el status; después, `code`. */
async function failFromResponse(response: ApiResponse): Promise<never> {
  const { status } = response;
  if (status === 400) {
    const body = await readErrorBody(response);
    if (body.code === 'invalid_status_transition') throw fail({ kind: 'invalid_transition' });
    if (body.code === 'validation_error' && body.errors.length > 0) {
      throw fail({
        kind: 'validation',
        source: 'api',
        errors: body.errors.map((item) => messageForApiError(item.field, item.error)),
      });
    }
    throw fail({ kind: 'request_invalid' });
  }
  if (status === 404) {
    const body = await readErrorBody(response);
    throw fail(body.code === 'incident_not_found' ? { kind: 'not_found' } : { kind: 'request_invalid' });
  }
  if (status >= 500) throw fail({ kind: 'server_error' });
  if (status >= 400) throw fail({ kind: 'request_invalid' });
  throw fail({ kind: 'unexpected_response' });
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
    throw fail({ kind: 'unexpected_response' });
  }
}

// ---------------------------------------------------------------------------
// Servicio
// ---------------------------------------------------------------------------

export function createIncidentManagerService(dependencies: IncidentManagerServiceDependencies = {}): IncidentManagerService {
  const client = dependencies.client ?? apiClient;
  const timeoutMs = dependencies.timeoutMs ?? INCIDENTS_TIMEOUT_MS;

  function expect<T>(successStatus: number, parse: (body: JsonValue) => T) {
    return async (response: ApiResponse): Promise<T> => {
      if (response.status !== successStatus) return failFromResponse(response);
      return response.json(parse);
    };
  }

  return {
    listIncidents(filters, options = {}) {
      return guarded(() =>
        client.get(incidentsQuery(filters), { timeoutMs, signal: options.signal }, expect(200, normalizeIncidentList))
      );
    },

    getIncidentSummary(options = {}) {
      return guarded(() =>
        client.get(SUMMARY_PATH, { timeoutMs, signal: options.signal }, expect(200, normalizeIncidentSummary))
      );
    },

    createIncident(values, options = {}) {
      return guarded(async () => {
        const errors = validateIncidentForm(values);
        if (errors.length > 0) throw fail({ kind: 'validation', source: 'client', errors });
        return client.postJson(
          INCIDENTS_PATH,
          buildIncidentPayload(values),
          { timeoutMs, signal: options.signal },
          expect(201, normalizeIncident)
        );
      });
    },

    changeIncidentStatus(id, status, options = {}) {
      return guarded(() =>
        client.patchJson(
          `${INCIDENTS_PATH}/${encodeURIComponent(id)}/status`,
          { status },
          { timeoutMs, signal: options.signal },
          expect(200, normalizeIncident)
        )
      );
    },
  };
}

const defaultService = createIncidentManagerService();

export const listIncidents: IncidentManagerService['listIncidents'] = (filters, options) =>
  defaultService.listIncidents(filters, options);
export const getIncidentSummary: IncidentManagerService['getIncidentSummary'] = (options) =>
  defaultService.getIncidentSummary(options);
export const createIncident: IncidentManagerService['createIncident'] = (values, options) =>
  defaultService.createIncident(values, options);
export const changeIncidentStatus: IncidentManagerService['changeIncidentStatus'] = (id, status, options) =>
  defaultService.changeIncidentStatus(id, status, options);
