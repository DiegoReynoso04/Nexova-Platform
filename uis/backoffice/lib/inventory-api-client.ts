// Cliente HTTP del inventario (Hito 5): la misma implementación que
// lib/api-client.ts (transporte, timeout, Bearer y 401), con otra base URL.
// No se duplica el cliente: solo cambia de dónde sale la URL.
//
// La base URL sale de `NEXT_PUBLIC_INVENTORY_API_URL` (solo el host, p. ej.
// `http://localhost:8000`; el servicio añade `/inventory/...`). Se lee en cada
// petición, como `NEXT_PUBLIC_API_URL`: si falta, `ApiConfigError` y la UI
// muestra el error de configuración, sin romper `npm run build`.
// **Sin reserva** a `NEXT_PUBLIC_API_URL`: si falta, es un error de configuración.

import { createApiClient, type ApiClient, type ApiClientDependencies } from '@/lib/api-client';

export const INVENTORY_BASE_URL_VARIABLE = 'NEXT_PUBLIC_INVENTORY_API_URL';

function inventoryBaseUrl(): string | undefined {
  // Acceso literal: Next.js solo sustituye `process.env.NEXT_PUBLIC_*` escrito así.
  return process.env.NEXT_PUBLIC_INVENTORY_API_URL;
}

/** Cliente con la base URL del inventario. Los tests inyectan el transporte y el token. */
export function createInventoryApiClient(dependencies: Omit<ApiClientDependencies, 'getBaseUrl' | 'baseUrlVariable'> = {}): ApiClient {
  return createApiClient({ ...dependencies, getBaseUrl: inventoryBaseUrl, baseUrlVariable: INVENTORY_BASE_URL_VARIABLE });
}

/** Cliente por defecto: `fetch` global, token de lib/auth-token.ts y `NEXT_PUBLIC_INVENTORY_API_URL`. */
export const inventoryApiClient: ApiClient = createInventoryApiClient();
