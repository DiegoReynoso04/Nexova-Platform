// Estado de la sesión del tracker (AUTH-02, SPECS.md §9). Lo consumen el guard
// global de rutas y la cabecera, vía components/auth/session-provider.tsx.
//
// - El token sale de lib/auth-token.ts (`useSyncExternalStore`): en el
//   servidor y durante la hidratación no se conoce (`initializing`).
// - Con token, la sesión se valida una vez por token con `GET /auth/me` en
//   services/api. Es la llamada protegida que demuestra si la sesión sigue
//   siendo válida: los datos de candidaturas vienen de la API de 4Geeks, que
//   no usa el token. Un 401 borra el token (lib/api-client.ts) y la sesión
//   pasa sola a `anonymous`; cualquier otro fallo se muestra con un texto
//   según su tipo y reintento. Mientras se reintenta, el estado es
//   `retrying`: el guard mantiene el aviso y «Reintentar» muestra la carga.

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';

import { UnauthorizedError, classifyApiError, type ApiErrorKind } from '@/lib/api-client';
import { clearAuthToken, readAuthToken, subscribeAuthToken } from '@/lib/auth-token';
import { getCurrentUser } from '@/services/auth.service';
import type { CurrentUser } from '@/types/auth';

export type ValidationState =
  | { status: 'idle' }
  | { status: 'authenticated'; token: string; user: CurrentUser }
  | { status: 'error'; token: string; kind: ApiErrorKind }
  /** Reintento en curso tras un error: se conserva el tipo para seguir mostrando el aviso. */
  | { status: 'retrying'; token: string; kind: ApiErrorKind };

export type SessionStatus =
  | { status: 'initializing' }
  | { status: 'anonymous' }
  | { status: 'checking' }
  | { status: 'authenticated'; user: CurrentUser }
  | { status: 'error'; kind: ApiErrorKind }
  | { status: 'retrying'; kind: ApiErrorKind };

/** `token`: `undefined` = aún no leído (servidor/hidratación), `null` = sin sesión. */
export function deriveSessionStatus(token: string | null | undefined, validation: ValidationState): SessionStatus {
  if (token === undefined) return { status: 'initializing' };
  if (token === null) return { status: 'anonymous' };
  if (validation.status === 'authenticated' && validation.token === token) {
    return { status: 'authenticated', user: validation.user };
  }
  if (validation.status === 'error' && validation.token === token) return { status: 'error', kind: validation.kind };
  if (validation.status === 'retrying' && validation.token === token) return { status: 'retrying', kind: validation.kind };
  return { status: 'checking' };
}

/** Texto del guard cuando no se pudo comprobar la sesión, según el tipo de error. */
export interface SessionErrorCopy {
  title: string;
  body: string;
}

export function sessionErrorCopy(kind: ApiErrorKind): SessionErrorCopy {
  const title = 'No se pudo comprobar la sesión';
  switch (kind) {
    case 'network':
      return { title, body: 'No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.' };
    case 'timeout':
      return { title, body: 'El servidor tardó demasiado en responder. Inténtalo de nuevo.' };
    case 'server':
      return { title, body: 'El servidor tuvo un problema al comprobar tu sesión. Inténtalo de nuevo en unos minutos.' };
    case 'unreadable':
      return { title, body: 'El servidor respondió de forma inesperada. Inténtalo de nuevo; si se repite, avisa al equipo técnico.' };
    default:
      return { title, body: 'Inténtalo de nuevo o cierra la sesión y vuelve a entrar.' };
  }
}

export interface AuthSessionController {
  activate(): void;
  dispose(): void;
  /** Valida `token` si no se ha validado ya (o `force`). Solo cuenta el último token pedido. */
  validate(token: string, force?: boolean): Promise<void>;
  /** Sin token (logout o 401): olvida el último token pedido. */
  forget(): void;
}

export function createAuthSessionController(
  onChange: (state: ValidationState) => void,
  fetchCurrentUser: () => Promise<CurrentUser> = getCurrentUser
): AuthSessionController {
  let active = false;
  let requestedToken: string | null = null;
  let run = 0;
  // Último error mostrado: un reintento forzado del mismo token pasa a `retrying`.
  let lastError: { token: string; kind: ApiErrorKind } | null = null;

  function forget(): void {
    requestedToken = null;
    run += 1;
  }

  return {
    activate() {
      active = true;
    },

    dispose() {
      active = false;
      forget();
    },

    forget,

    async validate(token, force = false) {
      if (!active || (!force && token === requestedToken)) return;
      requestedToken = token;
      run += 1;
      const current = run;
      // Reintento explícito («Reintentar» del guard): la vista muestra la carga.
      if (force && lastError !== null && lastError.token === token) {
        onChange({ status: 'retrying', token, kind: lastError.kind });
      }
      try {
        const user = await fetchCurrentUser();
        if (!active || current !== run) return;
        lastError = null;
        onChange({ status: 'authenticated', token, user });
      } catch (error) {
        if (!active || current !== run) return;
        // 401: el token ya se borró y la sesión pasa sola a `anonymous`.
        if (error instanceof UnauthorizedError) return;
        lastError = { token, kind: classifyApiError(error) };
        onChange({ status: 'error', ...lastError });
      }
    },
  };
}

export type AuthSession = SessionStatus & {
  retry: () => void;
  /** Elimina el token. La redirección a /login la hace quien llama (y el guard). */
  logout: () => void;
};

const getServerToken = (): undefined => undefined;

export function useAuthSession(): AuthSession {
  const token = useSyncExternalStore<string | null | undefined>(subscribeAuthToken, readAuthToken, getServerToken);
  const [validation, setValidation] = useState<ValidationState>({ status: 'idle' });
  const [controller] = useState(() => createAuthSessionController(setValidation));

  useEffect(() => {
    controller.activate();
    return () => controller.dispose();
  }, [controller]);

  useEffect(() => {
    if (typeof token === 'string') void controller.validate(token);
    else if (token === null) controller.forget();
  }, [controller, token]);

  const retry = useCallback(() => {
    const current = readAuthToken();
    if (current !== null) void controller.validate(current, true);
  }, [controller]);

  const logout = useCallback(() => clearAuthToken(), []);

  return { ...deriveSessionStatus(token, validation), retry, logout };
}
