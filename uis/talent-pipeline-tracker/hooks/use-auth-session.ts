// Estado de la sesión del tracker (AUTH-02, SPECS.md §9). Lo consumen el guard
// global de rutas y la cabecera, vía components/auth/session-provider.tsx.
//
// - El token sale de lib/auth-token.ts (`useSyncExternalStore`): en el
//   servidor y durante la hidratación no se conoce (`initializing`).
// - Con token, la sesión se valida una vez por token con `GET /auth/me` en
//   services/api. Es la llamada protegida que demuestra si la sesión sigue
//   siendo válida: los datos de candidaturas vienen de la API de 4Geeks, que
//   no usa el token. Un 401 borra el token (lib/api-client.ts) y la sesión
//   pasa sola a `anonymous`; un fallo de red se muestra con reintento.

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';

import { UnauthorizedError, describeApiError } from '@/lib/api-client';
import { clearAuthToken, readAuthToken, subscribeAuthToken } from '@/lib/auth-token';
import { getCurrentUser } from '@/services/auth.service';
import type { CurrentUser } from '@/types/auth';

export type ValidationState =
  | { status: 'idle' }
  | { status: 'authenticated'; token: string; user: CurrentUser }
  | { status: 'error'; token: string; message: string };

export type SessionStatus =
  | { status: 'initializing' }
  | { status: 'anonymous' }
  | { status: 'checking' }
  | { status: 'authenticated'; user: CurrentUser }
  | { status: 'error'; message: string };

/** `token`: `undefined` = aún no leído (servidor/hidratación), `null` = sin sesión. */
export function deriveSessionStatus(token: string | null | undefined, validation: ValidationState): SessionStatus {
  if (token === undefined) return { status: 'initializing' };
  if (token === null) return { status: 'anonymous' };
  if (validation.status === 'authenticated' && validation.token === token) {
    return { status: 'authenticated', user: validation.user };
  }
  if (validation.status === 'error' && validation.token === token) return { status: 'error', message: validation.message };
  return { status: 'checking' };
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
      try {
        const user = await fetchCurrentUser();
        if (!active || current !== run) return;
        onChange({ status: 'authenticated', token, user });
      } catch (error) {
        if (!active || current !== run) return;
        // 401: el token ya se borró y la sesión pasa sola a `anonymous`.
        if (error instanceof UnauthorizedError) return;
        onChange({ status: 'error', token, message: describeApiError(error) });
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
