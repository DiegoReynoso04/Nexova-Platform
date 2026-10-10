// Protección global de rutas (AUTH-02): qué hace el guard del layout raíz en
// cada ruta según el estado de la sesión. Toda ruta es protegida salvo las de
// PUBLIC_PATHS y OPEN_PATHS, así que una vista nueva queda protegida por defecto.
//
// No se usa middleware/proxy de Next.js: se ejecuta en el servidor y no puede
// leer `localStorage`, donde vive el token (lib/auth-token.ts).

import type { SessionStatus } from '@/hooks/use-auth-session';

export const LOGIN_PATH = '/login';
export const REGISTER_PATH = '/register';
/** Vista principal autenticada: destino tras login, registro o al abrir /login con sesión. */
export const HOME_PATH = '/';
export const PROFILE_PATH = '/account/profile';
// AUTH-03
export const FORGOT_PASSWORD_PATH = '/forgot-password';
export const RESET_PASSWORD_PATH = '/reset-password';
export const CHANGE_PASSWORD_PATH = '/account/change-password';

/** Solo sin sesión: con sesión válida redirigen a la vista principal. */
export const PUBLIC_PATHS: readonly string[] = [LOGIN_PATH, REGISTER_PATH, FORGOT_PASSWORD_PATH];
/**
 * Accesibles con o sin sesión. `/reset-password` se abre desde el enlace del
 * email: si el navegador tiene otra sesión abierta, el enlace debe seguir funcionando.
 */
export const OPEN_PATHS: readonly string[] = [RESET_PASSWORD_PATH];

function normalizePath(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
}

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.includes(normalizePath(pathname));
}

export function isOpenPath(pathname: string): boolean {
  return OPEN_PATHS.includes(normalizePath(pathname));
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
  if (isOpenPath(pathname)) return 'render';
  if (isPublicPath(pathname)) {
    // /login, /register y /forgot-password son accesibles sin sesión; con sesión válida no tienen sentido.
    return session === 'authenticated' ? 'redirect_home' : 'render';
  }
  switch (session) {
    case 'authenticated':
      return 'render';
    case 'anonymous':
      return 'redirect_login';
    case 'error':
    case 'retrying':
      return 'error';
    case 'initializing':
    case 'checking':
      return 'wait';
  }
}
