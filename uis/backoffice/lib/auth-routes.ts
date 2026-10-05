// Protección global de rutas (AUTH-02): qué hace el guard del layout raíz en
// cada ruta según el estado de la sesión. Toda ruta es protegida salvo las de
// PUBLIC_PATHS, así que una vista nueva queda protegida por defecto.
//
// No se usa middleware/proxy de Next.js: se ejecuta en el servidor y no puede
// leer `localStorage`, donde vive el token (lib/auth-token.ts).

import type { SessionStatus } from '@/hooks/use-auth-session';

export const LOGIN_PATH = '/login';
export const REGISTER_PATH = '/register';
/** Vista principal autenticada: destino tras login, registro o al abrir /login con sesión. */
export const HOME_PATH = '/';
export const PROFILE_PATH = '/account/profile';

export const PUBLIC_PATHS: readonly string[] = [LOGIN_PATH, REGISTER_PATH];

export function isPublicPath(pathname: string): boolean {
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  return PUBLIC_PATHS.includes(normalized);
}

export type RouteAccess =
  /** Mostrar la vista. */
  | 'render'
  /** Aún no se sabe si hay sesión válida: indicador de carga, sin mostrar la vista. */
  | 'wait'
  /** No se pudo validar la sesión (p. ej. API caída): error con reintento. */
  | 'error'
  | 'redirect_login'
  | 'redirect_home';

export function routeAccess(pathname: string, session: SessionStatus['status']): RouteAccess {
  if (isPublicPath(pathname)) {
    // /login y /register son accesibles sin sesión; con sesión válida no tienen sentido.
    return session === 'authenticated' ? 'redirect_home' : 'render';
  }
  switch (session) {
    case 'authenticated':
      return 'render';
    case 'anonymous':
      return 'redirect_login';
    case 'error':
      return 'error';
    case 'initializing':
    case 'checking':
      return 'wait';
  }
}
