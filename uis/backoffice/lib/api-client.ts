// Cliente HTTP genérico del backoffice (patrón de uis/talent-pipeline-tracker,
// adaptado). No sabe nada de incidentes ni de proveedores: transporta la petición, aplica el
// timeout y traduce los fallos de transporte a errores tipados. Decidir qué
// significa cada status es tarea de los servicios (`services/*.service.ts`).
//
// Privacidad: no registra nada, no guarda cuerpos para diagnóstico y ningún
// error de este módulo lleva texto de la respuesta ni la excepción original
// (el SyntaxError de `JSON.parse` incluye fragmentos del cuerpo recibido).
//
// Autenticación (AUTH-02): toda petición es protegida salvo que el servicio
// pida `skipAuth` (login y registro). En las protegidas se adjunta
// `Authorization: Bearer <token>` con el token de lib/auth-token.ts y, si la
// API responde 401, se elimina el token (el guard de rutas redirige a /login)
// y se lanza `ApiUnauthorizedError` sin llamar al handler del servicio. Así
// ninguna vista repite esa lógica.
//
// El JSON recibido solo se entrega, sin inspeccionarlo, a la función `parse`
// que indique el servicio (un normalizador de `services/normalizers.ts`, única
// frontera que valida datos de red).

import { clearAuthToken, readAuthToken } from '@/lib/auth-token';

/**
 * Cualquier valor que puede producir `JSON.parse` sin reviver: exactamente lo
 * que devuelve `Response.json()`. Tipo preciso, pero sin garantías de forma:
 * quien lo recibe debe validarlo (los normalizadores lo hacen).
 */
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

/** `navigator.sendBeacon` (o un doble en los tests): `true` si el navegador encoló el envío. */
export type BeaconLike = (url: string, data: Blob) => boolean;

export interface ApiClientDependencies {
  /** Transporte; por defecto el `fetch` global. Inyectable en tests. */
  fetch?: FetchLike;
  /** Base URL; por defecto `NEXT_PUBLIC_API_URL`. Se lee en cada petición (validación perezosa). */
  getBaseUrl?: () => string | undefined;
  /**
   * Nombre de la variable que da la base URL, solo para el mensaje de
   * `ApiConfigError` (que la UI nunca muestra). Por defecto `NEXT_PUBLIC_API_URL`.
   */
  baseUrlVariable?: string;
  /** Token de sesión; por defecto el de `localStorage` (lib/auth-token.ts). Se lee en cada petición. */
  getToken?: () => string | null;
  /** Qué hacer ante un 401 de una petición protegida; por defecto, borrar el token. */
  onUnauthorized?: () => void;
  /** Envío al ocultar la pestaña; por defecto `navigator.sendBeacon` si existe. Inyectable en tests. */
  sendBeacon?: BeaconLike;
  /**
   * Avisar al oyente de `setTransportFailureListener` cuando una petición no
   * obtiene respuesta (red, timeout o configuración). Por defecto sí; el
   * cliente de la telemetría lo apaga (sus fallos no se pueden enviar).
   */
  reportTransportFailures?: boolean;
}

/** Petición sin respuesta de la API (telemetría `client_request_failed`). Sin URL, cuerpo ni error. */
export interface TransportFailure {
  kind: 'network' | 'timeout' | 'config';
  method: OutgoingMethod;
  /** Ruta pedida, relativa a la base URL (puede llevar ids y query string: quien la recibe la normaliza). */
  path: string;
  /** Timeout aplicado si `kind = timeout`. */
  timeoutMs: number | null;
}

let transportFailureListener: ((failure: TransportFailure) => void) | null = null;

/**
 * Un único oyente (lib/telemetry.ts) para los fallos de transporte de todos los
 * clientes. Así este módulo no importa la telemetría (que depende de él).
 * Un oyente que lanza nunca rompe la petición.
 */
export function setTransportFailureListener(listener: ((failure: TransportFailure) => void) | null): void {
  transportFailureListener = listener;
}

export interface RequestOptions {
  timeoutMs: number;
  /** Cancelación desde fuera (p. ej. desmontaje de la vista). */
  signal?: AbortSignal;
  /**
   * Petición pública (`POST /auth/login`, `POST /users`): no envía el token y
   * su 401 lo interpreta el servicio (credenciales incorrectas), no es una
   * sesión caducada. Por defecto toda petición es protegida.
   */
  skipAuth?: boolean;
  /**
   * `fetch` con `keepalive`: la petición sobrevive a la navegación o al cierre
   * de la pestaña (telemetría). El navegador limita su cuerpo a unos 64 KiB.
   */
  keepalive?: boolean;
  /**
   * Telemetría: un 401 **no** borra el token ni lanza `ApiUnauthorizedError`;
   * lo recibe el handler como cualquier otro status. La telemetría nunca cierra
   * la sesión del operador.
   */
  ignoreUnauthorized?: boolean;
}

/** Respuesta HTTP mientras se procesa: el timeout sigue activo al leer el cuerpo. */
export interface ApiResponse {
  readonly status: number;
  header(name: string): string | null;
  /** Lee el cuerpo como JSON y lo pasa a `parse`. Lanza `ApiUnexpectedResponseError` si no es JSON. */
  json<T>(parse: (body: JsonValue) => T): Promise<T>;
  /** Lee el cuerpo como Blob. Lanza `ApiNetworkError` si la lectura falla (salvo abort). */
  blob(): Promise<Blob>;
}

export type ResponseHandler<T> = (response: ApiResponse) => Promise<T>;

export interface ApiClient {
  get<T>(path: string, options: RequestOptions, handle: ResponseHandler<T>): Promise<T>;
  /** `FormData` → multipart; `URLSearchParams` → `application/x-www-form-urlencoded` (login OAuth2). */
  postForm<T>(path: string, form: FormData | URLSearchParams, options: RequestOptions, handle: ResponseHandler<T>): Promise<T>;
  postJson<T>(path: string, body: JsonValue, options: RequestOptions, handle: ResponseHandler<T>): Promise<T>;
  patchJson<T>(path: string, body: JsonValue, options: RequestOptions, handle: ResponseHandler<T>): Promise<T>;
  putJson<T>(path: string, body: JsonValue, options: RequestOptions, handle: ResponseHandler<T>): Promise<T>;
  /**
   * `POST` JSON con `navigator.sendBeacon` (telemetría al ocultar la pestaña).
   * Sin cabeceras propias (el beacon no admite `Authorization`) ni respuesta.
   * `false` si no hay base URL, no hay beacon o el navegador no lo encola.
   */
  beaconJson(path: string, body: JsonValue): boolean;
}

const DEFAULT_BASE_URL_VARIABLE = 'NEXT_PUBLIC_API_URL';

// ---------------------------------------------------------------------------
// Errores de transporte. Mensajes fijos: nunca incluyen datos recibidos.
// ---------------------------------------------------------------------------

export class ApiClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiClientError';
  }
}

/** La variable de la base URL (`NEXT_PUBLIC_API_URL` u otra del cliente) ausente o vacía. */
export class ApiConfigError extends ApiClientError {
  constructor(variable = DEFAULT_BASE_URL_VARIABLE) {
    super(`API base URL is not configured (${variable})`);
    this.name = 'ApiConfigError';
  }
}

/** No se pudo conectar (API caída, CORS, DNS…). */
export class ApiNetworkError extends ApiClientError {
  constructor() {
    super('Could not reach the API');
    this.name = 'ApiNetworkError';
  }
}

/** Se agotó el timeout de la petición (incluida la lectura del cuerpo). */
export class ApiTimeoutError extends ApiClientError {
  constructor() {
    super('The API request timed out');
    this.name = 'ApiTimeoutError';
  }
}

/** Cancelada por quien llamó (`options.signal`). No es un fallo que mostrar al usuario. */
export class ApiAbortError extends ApiClientError {
  constructor() {
    super('The API request was aborted');
    this.name = 'ApiAbortError';
  }
}

/**
 * 401 en una petición protegida: no hay sesión válida (sin token, caducado o
 * usuario borrado). El token ya se ha eliminado cuando se lanza.
 */
export class ApiUnauthorizedError extends ApiClientError {
  constructor() {
    super('The session is not valid');
    this.name = 'ApiUnauthorizedError';
  }
}

/** El cuerpo no es JSON cuando debería serlo. No incluye el cuerpo. */
export class ApiUnexpectedResponseError extends ApiClientError {
  constructor() {
    super('The API returned a response that is not valid JSON');
    this.name = 'ApiUnexpectedResponseError';
  }
}

// ---------------------------------------------------------------------------
// Implementación
// ---------------------------------------------------------------------------

function defaultBaseUrl(): string | undefined {
  // Acceso literal: Next.js solo sustituye `process.env.NEXT_PUBLIC_*` escrito así.
  return process.env.NEXT_PUBLIC_API_URL;
}

function defaultBeacon(): BeaconLike | undefined {
  if (typeof navigator === 'undefined' || typeof navigator.sendBeacon !== 'function') return undefined;
  return (url, data) => navigator.sendBeacon(url, data);
}

function isAbortLike(error: Error): boolean {
  // Por nombre, no por clase: el objeto de un fetch abortado varía entre entornos.
  return error.name === 'AbortError';
}

function isJsonContentType(value: string | null): boolean {
  if (value === null) return false;
  const mediaType = value.split(';')[0]?.trim().toLowerCase() ?? '';
  return mediaType === 'application/json' || mediaType.endsWith('+json');
}

function wrapResponse(raw: Response): ApiResponse {
  return {
    status: raw.status,
    header: (name) => raw.headers.get(name),
    async json(parse) {
      if (!isJsonContentType(raw.headers.get('content-type'))) {
        throw new ApiUnexpectedResponseError();
      }
      // `Response.json()` es JSON.parse sin reviver: su resultado es siempre un JsonValue.
      let body: JsonValue;
      try {
        body = await raw.json();
      } catch (error) {
        // Un abort durante la lectura lo traduce `send` (timeout o cancelación).
        if (error instanceof Error && isAbortLike(error)) throw error;
        // Sin `cause`: el SyntaxError contiene fragmentos del cuerpo.
        throw new ApiUnexpectedResponseError();
      }
      return parse(body);
    },
    async blob() {
      try {
        return await raw.blob();
      } catch (error) {
        // Igual que en json(): un abort lo traduce `send` (timeout o cancelación);
        // cualquier otro fallo al leer el cuerpo es de red. Sin `cause`.
        if (error instanceof Error && isAbortLike(error)) throw error;
        throw new ApiNetworkError();
      }
    },
  };
}

type OutgoingMethod = 'GET' | 'POST' | 'PATCH' | 'PUT';

interface OutgoingRequest {
  method: OutgoingMethod;
  body?: BodyInit;
  contentType?: string;
}

export function createApiClient(dependencies: ApiClientDependencies = {}): ApiClient {
  const transport: FetchLike = dependencies.fetch ?? ((input, init) => fetch(input, init));
  const getBaseUrl = dependencies.getBaseUrl ?? defaultBaseUrl;
  const baseUrlVariable = dependencies.baseUrlVariable ?? DEFAULT_BASE_URL_VARIABLE;
  const getToken = dependencies.getToken ?? readAuthToken;
  const onUnauthorized = dependencies.onUnauthorized ?? clearAuthToken;
  const sendBeacon = dependencies.sendBeacon ?? defaultBeacon();
  const reportTransportFailures = dependencies.reportTransportFailures ?? true;

  function report(kind: TransportFailure['kind'], method: OutgoingMethod, path: string, timeoutMs: number | null): void {
    if (!reportTransportFailures || transportFailureListener === null) return;
    try {
      transportFailureListener({ kind, method, path, timeoutMs });
    } catch {
      // La telemetría nunca rompe una petición.
    }
  }

  function buildInit(request: OutgoingRequest, options: RequestOptions): RequestInit {
    const headers: Record<string, string> = {};
    if (request.contentType !== undefined) headers['Content-Type'] = request.contentType;
    if (!options.skipAuth) {
      const token = getToken();
      // Sin token se envía igualmente: la API responde 401 y se trata abajo.
      if (token !== null) headers.Authorization = `Bearer ${token}`;
    }
    const init: RequestInit = { method: request.method };
    if (request.body !== undefined) init.body = request.body;
    if (options.keepalive) init.keepalive = true;
    if (Object.keys(headers).length > 0) init.headers = headers;
    return init;
  }

  function resolveUrl(path: string): string | null {
    const baseUrl = getBaseUrl()?.trim();
    return baseUrl ? `${baseUrl.replace(/\/+$/, '')}${path}` : null;
  }

  async function send<T>(path: string, request: OutgoingRequest, options: RequestOptions, handle: ResponseHandler<T>): Promise<T> {
    const url = resolveUrl(path);
    if (url === null) {
      report('config', request.method, path, null);
      throw new ApiConfigError(baseUrlVariable);
    }
    if (options.signal?.aborted) throw new ApiAbortError();
    const init = buildInit(request, options);

    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs);
    const onCallerAbort = () => controller.abort();
    options.signal?.addEventListener('abort', onCallerAbort);

    try {
      let raw: Response;
      try {
        // Nunca se envían credenciales (cookies): la API no las acepta (CORS sin
        // credentials). El JWT viaja solo en la cabecera Authorization.
        raw = await transport(url, { ...init, signal: controller.signal });
      } catch (error) {
        if (timedOut) {
          report('timeout', request.method, path, options.timeoutMs);
          throw new ApiTimeoutError();
        }
        if (controller.signal.aborted) throw new ApiAbortError();
        if (error instanceof Error && isAbortLike(error)) throw new ApiAbortError();
        report('network', request.method, path, null);
        throw new ApiNetworkError();
      }
      if (raw.status === 401 && !options.skipAuth && !options.ignoreUnauthorized) {
        onUnauthorized();
        throw new ApiUnauthorizedError();
      }
      try {
        return await handle(wrapResponse(raw));
      } catch (error) {
        // Solo se traducen los aborts; los errores del handler (normalizador,
        // servicio) se propagan tal cual.
        if (error instanceof Error && isAbortLike(error)) {
          throw timedOut ? new ApiTimeoutError() : new ApiAbortError();
        }
        throw error;
      }
    } finally {
      clearTimeout(timeoutId);
      options.signal?.removeEventListener('abort', onCallerAbort);
    }
  }

  // Único punto que serializa JSON de salida: el cuerpo lo construye el servicio
  // campo a campo a partir de datos del formulario (nunca respuestas de la API).
  function jsonRequest(method: 'POST' | 'PATCH' | 'PUT', body: JsonValue): OutgoingRequest {
    return { method, contentType: 'application/json', body: JSON.stringify(body) };
  }

  function beaconJson(path: string, body: JsonValue): boolean {
    const url = resolveUrl(path);
    if (url === null || sendBeacon === undefined) return false;
    // Blob `application/json`: la API lo lee como un POST JSON normal. Mismo
    // origen (`/backend`), así que el tipo no necesita CORS.
    try {
      return sendBeacon(url, new Blob([JSON.stringify(body)], { type: 'application/json' }));
    } catch {
      // Un beacon por encima del límite del navegador puede lanzar en vez de devolver false.
      return false;
    }
  }

  return {
    beaconJson,
    get: (path, options, handle) => send(path, { method: 'GET' }, options, handle),
    postJson: (path, body, options, handle) => send(path, jsonRequest('POST', body), options, handle),
    patchJson: (path, body, options, handle) => send(path, jsonRequest('PATCH', body), options, handle),
    putJson: (path, body, options, handle) => send(path, jsonRequest('PUT', body), options, handle),
    // Sin cabecera Content-Type: el navegador la genera (boundary del multipart
    // o `application/x-www-form-urlencoded` para URLSearchParams).
    postForm: (path, form, options, handle) => send(path, { method: 'POST', body: form }, options, handle),
  };
}

/** Cliente por defecto: `fetch` global y `NEXT_PUBLIC_API_URL`. */
export const apiClient: ApiClient = createApiClient();
