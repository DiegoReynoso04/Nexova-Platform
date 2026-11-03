// Cliente HTTP de la telemetría (ticket de captura): la misma implementación
// que lib/api-client.ts, con la URL del colector como base (patrón de
// lib/inventory-api-client.ts). La ruta de cada envío es vacía: la variable
// es la URL **completa** del endpoint, también para `sendBeacon`.
//
// `NEXT_PUBLIC_TELEMETRY_ENDPOINT` (con Docker, `/backend/telemetry/events`)
// se lee en cada envío. Si falta, lib/telemetry.ts no envía nada y no avisa:
// la telemetría nunca bloquea la interfaz (distinto de las otras variables).
// Sus propios fallos no se notifican como `client_request_failed` (no habría
// por dónde enviarlos).

import { createApiClient, type ApiClient, type ApiClientDependencies } from '@/lib/api-client';

export const TELEMETRY_ENDPOINT_VARIABLE = 'NEXT_PUBLIC_TELEMETRY_ENDPOINT';

export function telemetryEndpoint(): string | undefined {
  // Acceso literal: Next.js solo sustituye `process.env.NEXT_PUBLIC_*` escrito así.
  return process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT;
}

export function createTelemetryApiClient(dependencies: Omit<ApiClientDependencies, 'getBaseUrl' | 'baseUrlVariable'> = {}): ApiClient {
  return createApiClient({
    reportTransportFailures: false,
    ...dependencies,
    getBaseUrl: telemetryEndpoint,
    baseUrlVariable: TELEMETRY_ENDPOINT_VARIABLE,
  });
}

/** Cliente por defecto: `fetch` global, `navigator.sendBeacon` y el token de lib/auth-token.ts. */
export const telemetryApiClient: ApiClient = createTelemetryApiClient();
