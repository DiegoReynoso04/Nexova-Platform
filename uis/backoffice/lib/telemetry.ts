// TelemetryService del backoffice (ticket de captura; plan §2.4, decisiones en
// docs/telemetry/capture-analysis.md). Todo el tracking pasa por `track()`:
// ningún componente construye eventos ni hace HTTP para la telemetría.
//
// - Envelope automático (plan §5): `eventId` y `requestId` (UUID v4),
//   `timestamp` del momento de la captura (ISO con ms y `Z`), `schemaVersion`
//   de la constante compartida, y `userId`/`sessionId` de los claims del JWT
//   (lib/session-identity.ts). Quien llama a `track()` solo pasa `properties`.
// - Allowlist: solo se envían las claves de `TELEMETRY_EVENT_KEYS`.
// - Cola en memoria; un lote cada 10 s o al llegar a 20 eventos, lo que pase antes.
// - Envío por lib/api-client.ts (el único `fetch`) con `keepalive` y sin que un
//   401 cierre la sesión. Hasta 3 reintentos (1, 2 y 4 s) ante red, timeout,
//   5xx o 429; un 4xx no se reintenta. Después, el lote se descarta.
// - Al ocultar o cerrar la pestaña (`visibilitychange: hidden`, `pagehide`), lo
//   pendiente sale con `navigator.sendBeacon` (sin `Authorization`, sin reintentos).
// - Nunca lanza, nunca muestra nada y nunca registra nada (sin `console.*`):
//   la telemetría no es crítica. Sin `NEXT_PUBLIC_TELEMETRY_ENDPOINT`, no hace nada.
// - Sin almacenamiento en el navegador: lo pendiente se pierde con la pestaña
//   si el beacon no sale (riesgo aceptado en el plan §8.4).

import { setTransportFailureListener, type ApiClient, type JsonValue, type TransportFailure } from '@/lib/api-client';
import { readSessionIdentity } from '@/lib/session-identity';
import { telemetryApiClient, telemetryEndpoint } from '@/lib/telemetry-api-client';
import type { TokenIdentity } from '@/services/normalizers';
import {
  API_ROUTE_TEMPLATES,
  PAGE_ROUTE_TEMPLATES,
  TELEMETRY_EVENT_KEYS,
  TELEMETRY_SCHEMA_VERSION,
  type ApiRouteTemplate,
  type PageRouteTemplate,
  type TelemetryEventProperties,
  type TelemetryEventType,
} from '@/types/telemetry';

/** Un lote cada 10 s… */
export const FLUSH_INTERVAL_MS = 10_000;
/** …o en cuanto la cola llega a 20 eventos. */
export const MAX_BATCH_SIZE = 20;
/** Esperas antes de cada reintento (exponencial): 3 reintentos y se descarta. */
export const RETRY_DELAYS_MS: readonly number[] = [1_000, 2_000, 4_000];
/** Timeout de cada envío. */
export const SEND_TIMEOUT_MS = 5_000;
/** Plan §7.2: un evento por clave y ventana en `client_request_failed` y `frontend_error_captured`. */
export const THROTTLE_WINDOW_MS = 60_000;

export interface TrackOptions {
  /** `requestId` de una petición asociada; si no, uno propio. */
  requestId?: string;
}

export interface TelemetryServiceDependencies {
  client: Pick<ApiClient, 'postJson' | 'beaconJson'>;
  /** Hay endpoint configurado. Se consulta en cada `track()`. */
  isEnabled: () => boolean;
  getIdentity: () => TokenIdentity;
  randomUUID: () => string;
  now: () => Date;
}

export interface TelemetryService {
  track<E extends TelemetryEventType>(eventType: E, properties: TelemetryEventProperties[E], options?: TrackOptions): void;
  /**
   * Throttle de pestaña (plan §7.2): el primer evento de cada `key` en la
   * ventana sale; los siguientes se cuentan y, al cerrarse la ventana, sale el
   * último con `suppressed_count` = los descartados.
   */
  trackThrottled<E extends ThrottledEventType>(key: string, eventType: E, build: (suppressedCount: number) => TelemetryEventProperties[E]): void;
  /** Envía ya lo pendiente (con `fetch` + `keepalive`), p. ej. antes de cerrar la sesión. */
  flush(): void;
  /** Envía lo pendiente con `sendBeacon` (pestaña oculta o cerrándose). */
  flushWithBeacon(): void;
  /** Eventos en cola, sin contar el lote en vuelo. Para los tests. */
  pendingCount(): number;
}

type WireEvent = { [key: string]: JsonValue };
type ThrottledEventType = 'client_request_failed' | 'frontend_error_captured';
type ThrottleEntry = { suppressed: number; emitLast: ((suppressed: number) => void) | null };

function isRetryableStatus(status: number): boolean {
  return status >= 500 || status === 429;
}

export function createTelemetryService(dependencies: TelemetryServiceDependencies): TelemetryService {
  const { client, isEnabled, getIdentity, randomUUID, now } = dependencies;
  let queue: WireEvent[] = [];
  let inFlight: WireEvent[] | null = null;
  let waitingRetry = false;
  let flushTimer: ReturnType<typeof setTimeout> | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  const throttles = new Map<string, ThrottleEntry>();

  function clearFlushTimer(): void {
    if (flushTimer !== null) clearTimeout(flushTimer);
    flushTimer = null;
  }

  function scheduleFlush(): void {
    if (flushTimer === null && queue.length > 0) flushTimer = setTimeout(flush, FLUSH_INTERVAL_MS);
  }

  function batchDone(): void {
    inFlight = null;
    waitingRetry = false;
    retryTimer = null;
    if (queue.length >= MAX_BATCH_SIZE) flush();
    else scheduleFlush();
  }

  function retryOrDrop(attempt: number): void {
    const delay = RETRY_DELAYS_MS[attempt];
    if (delay === undefined) {
      batchDone(); // tras el último reintento, el lote se descarta
      return;
    }
    waitingRetry = true;
    retryTimer = setTimeout(() => {
      waitingRetry = false;
      retryTimer = null;
      send(attempt + 1);
    }, delay);
  }

  function send(attempt: number): void {
    const batch = inFlight;
    if (batch === null) return;
    client
      .postJson(
        '',
        { events: batch },
        { timeoutMs: SEND_TIMEOUT_MS, keepalive: true, ignoreUnauthorized: true },
        async (response) => response.status
      )
      .then(
        (status) => {
          if (status >= 200 && status < 300) batchDone();
          else if (isRetryableStatus(status)) retryOrDrop(attempt);
          else batchDone(); // 4xx: el lote no mejora al repetirlo
        },
        (error: Error) => {
          // Red y timeout se reintentan; configuración (sin endpoint) o abort, no.
          if (error.name === 'ApiNetworkError' || error.name === 'ApiTimeoutError') retryOrDrop(attempt);
          else batchDone();
        }
      );
  }

  function flush(): void {
    clearFlushTimer();
    if (inFlight !== null || queue.length === 0) return;
    inFlight = queue.slice(0, MAX_BATCH_SIZE);
    queue = queue.slice(MAX_BATCH_SIZE);
    send(0);
  }

  function flushWithBeacon(): void {
    clearFlushTimer();
    const pending = [...queue];
    queue = [];
    // Un lote esperando su reintento sale también por el beacon; uno en vuelo
    // no (su `fetch` lleva `keepalive` y sobrevive al cierre).
    if (inFlight !== null && waitingRetry) {
      if (retryTimer !== null) clearTimeout(retryTimer);
      pending.unshift(...inFlight);
      inFlight = null;
      waitingRetry = false;
      retryTimer = null;
    }
    for (let start = 0; start < pending.length; start += MAX_BATCH_SIZE) {
      // `false` (el navegador no lo encola): se descarta, sin reintentos.
      client.beaconJson('', { events: pending.slice(start, start + MAX_BATCH_SIZE) });
    }
  }

  function track<E extends TelemetryEventType>(eventType: E, properties: TelemetryEventProperties[E], options: TrackOptions = {}): void {
    try {
      if (!isEnabled()) return;
      const source: { [key: string]: JsonValue } = properties;
      const allowed: { [key: string]: JsonValue } = {};
      for (const key of TELEMETRY_EVENT_KEYS[eventType]) {
        const name = String(key);
        const value = source[name];
        if (value !== undefined) allowed[name] = value;
      }
      const identity = getIdentity();
      queue.push({
        eventId: randomUUID(),
        timestamp: now().toISOString(),
        sessionId: identity.sessionId,
        userId: identity.userId,
        event_type: eventType,
        schemaVersion: TELEMETRY_SCHEMA_VERSION,
        requestId: options.requestId ?? randomUUID(),
        properties: allowed,
      });
      if (queue.length >= MAX_BATCH_SIZE) flush();
      else scheduleFlush();
    } catch {
      // La telemetría nunca rompe la interfaz.
    }
  }

  function trackThrottled<E extends ThrottledEventType>(
    key: string,
    eventType: E,
    build: (suppressedCount: number) => TelemetryEventProperties[E]
  ): void {
    const throttleKey = `${eventType}:${key}`;
    const entry = throttles.get(throttleKey);
    if (entry !== undefined) {
      entry.suppressed += 1;
      entry.emitLast = (suppressed) => track(eventType, build(suppressed));
      return;
    }
    track(eventType, build(0));
    const fresh: ThrottleEntry = { suppressed: 0, emitLast: null };
    throttles.set(throttleKey, fresh);
    setTimeout(() => {
      // Fin de ventana: el último descartado sale con el recuento acumulado.
      throttles.delete(throttleKey);
      if (fresh.suppressed > 0 && fresh.emitLast !== null) fresh.emitLast(fresh.suppressed);
    }, THROTTLE_WINDOW_MS);
  }

  return { track, trackThrottled, flush, flushWithBeacon, pendingCount: () => queue.length };
}

// ---------------------------------------------------------------------------
// Plantillas de ruta: nunca el path real (ids, `?token=` de /reset-password).
// ---------------------------------------------------------------------------

/** Página del backoffice → su plantilla del plan, o `null` si no es una ruta conocida. */
export function pageRouteTemplate(pathname: string): PageRouteTemplate | null {
  const path = pathname.split(/[?#]/)[0] ?? '';
  const trimmed = path.length > 1 ? path.replace(/\/+$/, '') : path;
  return PAGE_ROUTE_TEMPLATES.find((template) => template === trimmed) ?? null;
}

const API_TEMPLATE_MATCHERS: readonly { template: ApiRouteTemplate; pattern: RegExp }[] = API_ROUTE_TEMPLATES.map((template) => ({
  template,
  pattern: new RegExp(`^${template.replace(/\{[a-z_]+\}/g, '[^/]+')}$`),
}));

/**
 * Ruta de una petición a la API (relativa a la base URL) → su plantilla, o
 * `null` si no es una ruta del contrato. Las rutas literales ganan a las que
 * llevan parámetro (`/api/incidents/summary` antes que `/{incident_id}`).
 */
export function apiRouteTemplate(path: string): ApiRouteTemplate | null {
  const clean = (path.split(/[?#]/)[0] ?? '').replace(/\/+$/, '');
  const literal = API_ROUTE_TEMPLATES.find((template) => template === clean);
  if (literal !== undefined) return literal;
  return API_TEMPLATE_MATCHERS.find(({ template, pattern }) => template.includes('{') && pattern.test(clean))?.template ?? null;
}

/** Milisegundos enteros desde `start` (`performance.now()`), acotados al máximo del esquema. */
export function elapsedMs(start: number, end: number, max: number): number {
  return Math.min(max, Math.max(0, Math.round(end - start)));
}

// ---------------------------------------------------------------------------
// Servicio por defecto y arranque en el navegador
// ---------------------------------------------------------------------------

function browserUUID(): string {
  return crypto.randomUUID();
}

let defaultService: TelemetryService | null = null;

function service(): TelemetryService {
  if (defaultService === null) {
    defaultService = createTelemetryService({
      client: telemetryApiClient,
      isEnabled: () => typeof window !== 'undefined' && Boolean(telemetryEndpoint()?.trim()),
      getIdentity: readSessionIdentity,
      randomUUID: browserUUID,
      now: () => new Date(),
    });
  }
  return defaultService;
}

/** Única función pública de tracking del backoffice. */
export function track<E extends TelemetryEventType>(eventType: E, properties: TelemetryEventProperties[E], options?: TrackOptions): void {
  service().track(eventType, properties, options);
}

/** `track` con el throttle de pestaña del plan §7.2 (errores de frontend y de red). */
export function trackThrottled<E extends ThrottledEventType>(
  key: string,
  eventType: E,
  build: (suppressedCount: number) => TelemetryEventProperties[E]
): void {
  service().trackThrottled(key, eventType, build);
}

/** Envía ya lo pendiente (p. ej. `user_logged_out`, antes de borrar el token). */
export function flushTelemetry(): void {
  service().flush();
}

/** `TransportFailure` de lib/api-client.ts → `client_request_failed`. */
export function reportTransportFailure(failure: TransportFailure, telemetry: Pick<TelemetryService, 'trackThrottled'> = service()): void {
  const route = apiRouteTemplate(failure.path);
  if (route === null) return;
  telemetry.trackThrottled(`${failure.kind}:${route}`, 'client_request_failed', (suppressedCount) => ({
    kind: failure.kind,
    http_method: failure.method,
    api_route_template: route,
    timeout_ms: failure.kind === 'timeout' ? failure.timeoutMs : null,
    suppressed_count: suppressedCount,
  }));
}

let started = false;

/**
 * Lo llama una vez `components/telemetry/telemetry-provider.tsx` al montarse:
 * envío por beacon al ocultar o cerrar la pestaña y `client_request_failed`.
 * Devuelve la función que lo deshace.
 */
export function startTelemetry(): () => void {
  if (started || typeof window === 'undefined') return () => {};
  started = true;
  const onVisibility = () => {
    if (document.visibilityState === 'hidden') service().flushWithBeacon();
  };
  const onPageHide = () => service().flushWithBeacon();
  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('pagehide', onPageHide);
  setTransportFailureListener((failure) => reportTransportFailure(failure));
  return () => {
    started = false;
    document.removeEventListener('visibilitychange', onVisibility);
    window.removeEventListener('pagehide', onPageHide);
    setTransportFailureListener(null);
  };
}
