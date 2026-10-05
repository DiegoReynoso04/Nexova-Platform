// Protección global de rutas (AUTH-02, SPECS.md §9): qué hace el guard del
// layout raíz en cada ruta según la sesión. Toda ruta es protegida salvo las
// de PUBLIC_PATHS, así que una vista nueva queda protegida por defecto.
//
// No se usa middleware/proxy de Next.js: corre en el servidor y no puede leer
// `localStorage`, donde vive el token (lib/auth-token.ts).

import type { SessionStatus } from '@/hooks/use-auth-session';

export const LOGIN_PATH = '/login';
export const REGISTER_PATH = '/register';
/** Vista principal autenticada: el listado de candidaturas. */
export const HOME_PATH = '/';
export const PROFILE_PATH = '/account/profile';

export const PUBLIC_PATHS: readonly string[] = [LOGIN_PATH, REGISTER_PATH];

export function isPublicPath(pathname: string): boolean {
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  return PUBLIC_PATHS.includes(normalized);
}

export type RouteAccess = 'render' | 'wait' | 'error' | 'redirect_login' | 'redirect_home';

export function routeAccess(pathname: string, session: SessionStatus['status']): RouteAccess {
  if (isPublicPath(pathname)) {
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
