// Cliente HTTP genérico. Fuente: SPECS.md §3.2, §5.1, §5.4 y §9 (AUTH-02).
// No tipa el cuerpo de las respuestas: siempre devuelve `unknown`. El
// estrechamiento a tipos firmes es responsabilidad de services/normalizers.ts.
//
// Dos destinos, cada uno con su variable de entorno:
//   - `apiClient`: API de candidaturas de 4Geeks (NEXT_PUBLIC_API_URL). Sin
//     autenticación (§5.1): nunca recibe el token de sesión.
//   - `authApiClient`: services/api de Nexova (NEXT_PUBLIC_AUTH_API_URL), para
//     login, registro, usuario actual y perfil (AUTH-02). Sus peticiones
//     protegidas llevan `Authorization: Bearer <token>`; un 401 en ellas borra
//     el token (el guard de rutas redirige a /login) y lanza UnauthorizedError.

import { clearAuthToken, readAuthToken } from '@/lib/auth-token';
import type { ValidationError } from '@/types/api';

import { ResponseShapeError } from '@/lib/response-shape-error';

export { ResponseShapeError };

const RAW_API_BASE_URL = process.env.NEXT_PUBLIC_API_URL;

if (!RAW_API_BASE_URL) {
  throw new Error(
    'NEXT_PUBLIC_API_URL no está definida. Añádela a .env.local (ver SPECS.md §3.2).'
  );
}

const RAW_AUTH_API_BASE_URL = process.env.NEXT_PUBLIC_AUTH_API_URL;

if (!RAW_AUTH_API_BASE_URL) {
  throw new Error(
    'NEXT_PUBLIC_AUTH_API_URL no está definida. Añádela a .env.local (ver SPECS.md §9).'
  );
}

// Ya comprobadas: string no vacío.
const API_BASE_URL: string = RAW_API_BASE_URL;
const AUTH_API_BASE_URL: string = RAW_AUTH_API_BASE_URL.replace(/\/+$/, '');

// El backend duerme en Heroku: un dyno frío puede tardar >10s en arrancar,
// y el router de Heroku corta la conexión a los 30s. 20s deja margen para
// el arranque en frío y sigue disparando ANTES que ese corte, para que el
// usuario vea nuestro mensaje en vez de un H12 genérico de Heroku.
const REQUEST_TIMEOUT_MS = 20000;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export class ValidationApiError extends ApiError {
  readonly detail: ValidationError[];

  constructor(detail: ValidationError[]) {
    super('Error de validación', 422);
    this.name = 'ValidationApiError';
    this.detail = detail;
  }
}

export class NotFoundError extends ApiError {
  constructor() {
    super('Recurso no encontrado', 404);
    this.name = 'NotFoundError';
  }
}

export class NetworkError extends Error {
  readonly originalError: unknown;

  constructor(originalError: unknown, message: string = 'No se pudo conectar con el servidor') {
    super(message);
    this.name = 'NetworkError';
    this.originalError = originalError;
  }
}

// 401 en una petición protegida de services/api: no hay sesión válida (sin
// token, caducado o usuario borrado). El token ya se ha eliminado.
export class UnauthorizedError extends ApiError {
  constructor() {
    super('La sesión ha caducado. Vuelve a iniciar sesión.', 401);
    this.name = 'UnauthorizedError';
  }
}

// 2xx o error HTTP cuyo cuerpo no es JSON legible. `status` permite saber si
// la operación llegó a aplicarse (2xx) aunque no se pueda leer la respuesta.
export class UnreadableResponseError extends ApiError {
  constructor(status: number) {
    super('La API devolvió una respuesta ilegible', status);
    this.name = 'UnreadableResponseError';
  }
}

// Valor lanzado que no es un Error (p. ej. `throw 'x'`). Sustituye a
// `new Error(String(valor))`: el valor no se convierte en texto ni se muestra.
export class UnknownClientError extends Error {
  constructor() {
    super('Error desconocido');
    this.name = 'UnknownClientError';
  }
}

/** El valor capturado como Error, conservando su clase para clasificarlo. */
export function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new UnknownClientError();
}

// Solo por el timeout propio de request() (ver más abajo): nunca por el
// nombre del error, que también es "AbortError" en un abort ajeno.
export class TimeoutError extends NetworkError {
  constructor() {
    super(undefined, 'La petición tardó demasiado. Comprueba tu conexión e inténtalo de nuevo.');
    this.name = 'TimeoutError';
  }
}

type QueryParams = Record<string, string | number | boolean | undefined | null>;

// §4.6 — los parámetros vacíos o sin valor no se envían en la query string
function buildQueryString(params?: QueryParams): string {
  if (!params) return '';

  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }

  const query = search.toString();
  return query ? `?${query}` : '';
}

function isRecordObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

// Duck typing sobre `.name`, no `instanceof DOMException`/`instanceof
// Error`: el objeto que rechaza un fetch abortado no siempre es la misma
// clase en todos los entornos, pero `.name === 'AbortError'` sí es estable.
function isAbortError(value: unknown): boolean {
  return isRecordObject(value) && value.name === 'AbortError';
}

function isValidationError(value: unknown): value is ValidationError {
  if (!isRecordObject(value)) return false;
  const { loc, msg, type } = value;
  return Array.isArray(loc) && typeof msg === 'string' && typeof type === 'string';
}

// §5.4 — un 422 se parsea como HTTPValidationError. `null` = "no reconozco
// esta forma en absoluto": la decisión de qué hacer con eso es de
// request(), que es quien sabe convertirlo en un ApiError explícito. Si el
// array existe pero algún ítem no tiene forma de ValidationError, se
// conservan los válidos y se añade uno sintético (loc: []) para no perder
// la señal de que la API devolvió algo raro — sale por el balde
// "unmatched" del formulario en vez de desaparecer en silencio.
function parseValidationDetail(body: unknown): ValidationError[] | null {
  if (!isRecordObject(body) || !Array.isArray(body.detail)) {
    return null;
  }

  const validItems = body.detail.filter(isValidationError);
  if (validItems.length === body.detail.length) {
    return validItems;
  }

  return [
    ...validItems,
    {
      loc: [],
      msg: 'La API devolvió errores de validación adicionales con un formato no reconocido.',
      type: 'unknown_format',
    },
  ];
}

// `none`: API de 4Geeks (sin token). `bearer`: ruta protegida de services/api.
// `public`: login y registro en services/api (sin token; su 401 significa
// "credenciales incorrectas" y lo interpreta el servicio).
type AuthMode = 'none' | 'bearer' | 'public';

interface OutgoingRequest {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: string | URLSearchParams;
  contentType?: string;
}

function buildInit(outgoing: OutgoingRequest, auth: AuthMode): RequestInit {
  const headers: Record<string, string> = {};
  if (outgoing.contentType !== undefined) headers['Content-Type'] = outgoing.contentType;
  if (auth === 'bearer') {
    const token = readAuthToken();
    // Sin token se envía igualmente: services/api responde 401 y se trata abajo.
    if (token !== null) headers.Authorization = `Bearer ${token}`;
  }
  const init: RequestInit = { method: outgoing.method };
  if (outgoing.body !== undefined) init.body = outgoing.body;
  if (Object.keys(headers).length > 0) init.headers = headers;
  return init;
}

async function request(
  baseUrl: string,
  path: string,
  outgoing: OutgoingRequest,
  auth: AuthMode = 'none'
): Promise<unknown> {
  const init = buildInit(outgoing, auth);

  // El timeout cubre la petición y la lectura del cuerpo (response.json()):
  // un cuerpo que no termina de llegar también acaba en TimeoutError. El
  // finally de fuera limpia el temporizador en todos los caminos.
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const hasTimedOut = () => timedOut;

  try {
    let response: Response;
    try {
      // Nunca se establece `credentials`: CORS de la API es Allow-Origin: * +
      // Allow-Credentials: true, combinación inválida (§5.1).
      response = await fetch(`${baseUrl}${path}`, { ...init, signal: controller.signal });
    } catch (cause) {
      // La bandera decide, no el nombre del error: un abort por nuestro
      // timeout y uno por desmontaje de la página (o cualquier otro motivo
      // ajeno) son ambos AbortError.
      if (timedOut) {
        throw new TimeoutError();
      }
      if (isAbortError(cause)) {
        // No es nuestro timeout: se relanza tal cual. No es un fallo que
        // deba mostrarse al usuario (p. ej. la navegación cerrando la
        // página a mitad de la petición).
        throw cause;
      }
      throw new NetworkError(cause);
    }

    // §5.4 — comprobar 204 ANTES de intentar parsear el cuerpo
    if (response.status === 204) {
      return undefined;
    }

    if (!response.ok) {
      if (response.status === 401 && auth === 'bearer') {
        clearAuthToken();
        throw new UnauthorizedError();
      }

      // §5.4 — la detección de 404 se basa en el status, nunca en el cuerpo
      if (response.status === 404) {
        throw new NotFoundError();
      }

      if (response.status === 422) {
        const detail = parseValidationDetail(await readJson(response, hasTimedOut));
        if (detail === null) {
          throw new UnreadableResponseError(response.status);
        }
        throw new ValidationApiError(detail);
      }

      // El mensaje no lleva el código: describeApiError clasifica por `status`.
      throw new ApiError('La API rechazó la petición', response.status);
    }

    return await readJson(response, hasTimedOut);
  } finally {
    clearTimeout(timeoutId);
  }
}

// Lee el cuerpo como JSON. Si el temporizador corta la lectura → TimeoutError;
// si el cuerpo no es JSON (o la conexión se corta) → UnreadableResponseError,
// sin el SyntaxError original (puede citar fragmentos del cuerpo).
async function readJson(response: Response, hasTimedOut: () => boolean): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    if (hasTimedOut()) throw new TimeoutError();
    throw new UnreadableResponseError(response.status);
  }
}

function json(method: 'POST' | 'PUT' | 'PATCH', body: unknown): OutgoingRequest {
  return { method, contentType: 'application/json', body: JSON.stringify(body) };
}

function get(path: string, params?: QueryParams): Promise<unknown> {
  return request(API_BASE_URL, `${path}${buildQueryString(params)}`, { method: 'GET' });
}

function post(path: string, body?: unknown): Promise<unknown> {
  return request(API_BASE_URL, path, json('POST', body));
}

function put(path: string, body?: unknown): Promise<unknown> {
  return request(API_BASE_URL, path, json('PUT', body));
}

function patch(path: string, body?: unknown): Promise<unknown> {
  return request(API_BASE_URL, path, json('PATCH', body));
}

function del(path: string): Promise<unknown> {
  return request(API_BASE_URL, path, { method: 'DELETE' });
}

// API de candidaturas de 4Geeks: sin token (§5.1).
export const apiClient = { get, post, put, patch, del };

// services/api de Nexova (AUTH-02, §9).
export const authApiClient = {
  /** GET protegido (Bearer). */
  get: (path: string): Promise<unknown> => request(AUTH_API_BASE_URL, path, { method: 'GET' }, 'bearer'),
  /** PUT protegido (Bearer). */
  put: (path: string, body: unknown): Promise<unknown> => request(AUTH_API_BASE_URL, path, json('PUT', body), 'bearer'),
  /** POST protegido con JSON (Bearer): cambio de contraseña (AUTH-03). */
  post: (path: string, body: unknown): Promise<unknown> => request(AUTH_API_BASE_URL, path, json('POST', body), 'bearer'),
  /** POST público con JSON (registro y recuperación de contraseña): sin token. */
  postPublic: (path: string, body: unknown): Promise<unknown> =>
    request(AUTH_API_BASE_URL, path, json('POST', body), 'public'),
  /** POST público `application/x-www-form-urlencoded` (login OAuth2): sin token. */
  postFormPublic: (path: string, form: URLSearchParams): Promise<unknown> =>
    request(AUTH_API_BASE_URL, path, { method: 'POST', body: form }, 'public'),
};

// Clasificación de cualquier error capturado (§5.4: "otros 4xx/5xx: mensaje
// legible"; red y timeout se distinguen de los errores HTTP).
export type ApiErrorKind =
  | 'validation'
  | 'network'
  | 'timeout'
  | 'unauthorized'
  | 'not_found'
  | 'client'
  | 'server'
  | 'unreadable'
  | 'unknown';

export function classifyApiError(error: unknown): ApiErrorKind {
  if (error instanceof ValidationApiError) return 'validation';
  if (error instanceof TimeoutError) return 'timeout';
  if (error instanceof NetworkError) return 'network';
  if (error instanceof UnauthorizedError) return 'unauthorized';
  if (error instanceof NotFoundError) return 'not_found';
  if (error instanceof UnreadableResponseError || error instanceof ResponseShapeError) return 'unreadable';
  if (error instanceof ApiError) return error.status >= 500 ? 'server' : 'client';
  return 'unknown';
}

// Textos fijos por tipo: nunca el código HTTP, el mensaje de un normalizador
// ni String(error). Solo el 422 muestra los `msg` de la API (§5.4).
export const API_ERROR_MESSAGES: Readonly<Record<Exclude<ApiErrorKind, 'validation'>, string>> = {
  network: 'No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.',
  timeout: 'El servidor tardó demasiado en responder. Inténtalo de nuevo.',
  unauthorized: 'La sesión ha caducado. Vuelve a iniciar sesión.',
  not_found: 'No se encontró lo que buscabas. Puede que ya no exista.',
  client: 'El servidor rechazó la petición. Revisa los datos e inténtalo de nuevo.',
  server: 'El servidor tuvo un problema. Inténtalo de nuevo en unos minutos.',
  unreadable: 'El servidor respondió de forma inesperada. Inténtalo de nuevo; si se repite, avisa al equipo técnico.',
  unknown: 'No se pudo completar la operación. Inténtalo de nuevo.',
};

const VALIDATION_FALLBACK_MESSAGE = 'Revisa los datos e inténtalo de nuevo.';

// Mensaje legible único a partir de cualquier error capturado.
export function describeApiError(error: unknown): string {
  if (error instanceof ValidationApiError) {
    const detailMessage = error.detail.map((item) => item.msg).join(' ');
    return detailMessage || VALIDATION_FALLBACK_MESSAGE;
  }
  const kind = classifyApiError(error);
  return kind === 'validation' ? VALIDATION_FALLBACK_MESSAGE : API_ERROR_MESSAGES[kind];
}
