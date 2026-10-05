// Almacén del JWT de sesión (AUTH-02). Único módulo del tracker que usa
// `localStorage`, exigido por el ticket AUTH-02 (documentado en CLAUDE.md).
// Solo guarda el token de acceso de services/api (nunca datos de
// candidaturas ni de usuario). La API de 4Geeks no recibe nunca este token.
//
// Es un store externo para `useSyncExternalStore`: quien lo escucha (el guard
// de rutas) reacciona a cualquier cambio, venga de un login, de un logout, de
// un 401 detectado por lib/api-client.ts o de otra pestaña (evento `storage`).
//
// Toda lectura/escritura va en try/catch: en el servidor no hay `window`, y en
// modo privado o con el almacenamiento bloqueado `localStorage` puede lanzar.
// En ese caso se comporta como "sin sesión".

export const AUTH_TOKEN_STORAGE_KEY = 'nexova.tracker.access_token';

type Listener = () => void;

const listeners = new Set<Listener>();

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

function notify(): void {
  for (const listener of listeners) listener();
}

/** Token guardado, o `null` si no hay sesión (o no hay almacenamiento disponible). */
export function readAuthToken(): string | null {
  try {
    const value = storage()?.getItem(AUTH_TOKEN_STORAGE_KEY) ?? null;
    return value === null || value.trim() === '' ? null : value;
  } catch {
    return null;
  }
}

/** Guarda el token recibido en un login correcto. Un token vacío no se guarda. */
export function saveAuthToken(token: string): void {
  if (token.trim() === '') return;
  try {
    storage()?.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  } catch {
    // Sin almacenamiento disponible: la sesión no puede persistir.
  }
  notify();
}

/** Elimina el token (logout o sesión caducada). Idempotente. */
export function clearAuthToken(): void {
  try {
    storage()?.removeItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // Nada que borrar.
  }
  notify();
}

/** Suscripción para `useSyncExternalStore`. Incluye los cambios hechos en otras pestañas. */
export function subscribeAuthToken(listener: Listener): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === AUTH_TOKEN_STORAGE_KEY) listener();
  };
  if (typeof window !== 'undefined') window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    if (typeof window !== 'undefined') window.removeEventListener('storage', onStorage);
  };
}
