// Estado de la sesión del backoffice (AUTH-02). Lo consume el guard global de
// rutas y la cabecera, a través de components/auth/session-provider.tsx.
//
// - El token sale de lib/auth-token.ts (`useSyncExternalStore`): en el
//   servidor y durante la hidratación no se conoce (`initializing`); en el
//   navegador es `null` (sin sesión) o el JWT guardado.
// - Con token, la sesión se valida una vez por token con `GET /auth/me`. Si la
//   API responde 401, lib/api-client.ts borra el token y el estado pasa solo a
//   `anonymous` (el guard redirige a /login). Un fallo de red no borra nada:
//   se muestra como `error` con opción de reintentar.
//
// Igual que los demás hooks: reducer puro + controlador sin React (probado con
// `node --test`) + el hook que los une.

import { useCallback, useEffect, useReducer, useState, useSyncExternalStore } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { clearAuthToken, readAuthToken, subscribeAuthToken } from '@/lib/auth-token';
import { AuthServiceError, getCurrentUser } from '@/services/auth.service';
import type { AuthUiError, CurrentUser } from '@/types/auth';

// ---------------------------------------------------------------------------
// Estado de la validación (por token)
// ---------------------------------------------------------------------------

export type ValidationState =
  | { status: 'idle' }
  | { status: 'authenticated'; token: string; user: CurrentUser }
  | { status: 'error'; token: string; error: AuthUiError };

export type ValidationAction =
  | { type: 'validated'; token: string; user: CurrentUser }
  | { type: 'failed'; token: string; error: AuthUiError };

export const INITIAL_VALIDATION_STATE: ValidationState = { status: 'idle' };

export function validationReducer(state: ValidationState, action: ValidationAction): ValidationState {
  switch (action.type) {
    case 'validated':
      return { status: 'authenticated', token: action.token, user: action.user };
    case 'failed':
      return { status: 'error', token: action.token, error: action.error };
  }
}

/** Estado visible de la sesión, combinando el token guardado y su validación. */
export type SessionStatus =
  | { status: 'initializing' }
  | { status: 'anonymous' }
  | { status: 'checking' }
  | { status: 'authenticated'; user: CurrentUser }
  | { status: 'error'; error: AuthUiError };

/** `token`: `undefined` = aún no leído (servidor/hidratación), `null` = sin sesión. */
export function deriveSessionStatus(token: string | null | undefined, validation: ValidationState): SessionStatus {
  if (token === undefined) return { status: 'initializing' };
  if (token === null) return { status: 'anonymous' };
  if (validation.status === 'authenticated' && validation.token === token) {
    return { status: 'authenticated', user: validation.user };
  }
  if (validation.status === 'error' && validation.token === token) return { status: 'error', error: validation.error };
  return { status: 'checking' };
}

// ---------------------------------------------------------------------------
// Controlador: validación asíncrona y carreras
// ---------------------------------------------------------------------------

export interface AuthSessionDependencies {
  getCurrentUser: typeof getCurrentUser;
}

export interface AuthSessionController {
  activate(): void;
  dispose(): void;
  /** Valida `token` si no se ha validado ya (o `force`). Solo cuenta el último token pedido. */
  validate(token: string, force?: boolean): Promise<void>;
  /** Sin token (logout o 401): cancela la validación en curso y olvida el último token pedido. */
  forget(): void;
}

const FALLBACK_ERROR: AuthUiError = { kind: 'unexpected_response' };

export function createAuthSessionController(
  dispatch: (action: ValidationAction) => void,
  dependencies: AuthSessionDependencies = { getCurrentUser }
): AuthSessionController {
  let active = false;
  let requestedToken: string | null = null;
  let controller: AbortController | null = null;

  function emit(action: ValidationAction): void {
    if (active) dispatch(action);
  }

  function forget(): void {
    requestedToken = null;
    controller?.abort();
    controller = null;
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
      controller?.abort();
      const current = new AbortController();
      controller = current;

      try {
        const user = await dependencies.getCurrentUser({ signal: current.signal });
        if (!active || controller !== current) return;
        emit({ type: 'validated', token, user });
      } catch (error) {
        if (!active || controller !== current || error instanceof ApiAbortError) return;
        const uiError = error instanceof AuthServiceError ? error.uiError : FALLBACK_ERROR;
        // 401: el token ya se borró y el estado pasa solo a `anonymous`.
        if (uiError.kind === 'session_expired') return;
        emit({ type: 'failed', token, error: uiError });
      } finally {
        if (controller === current) controller = null;
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export type AuthSession = SessionStatus & {
  /** Reintenta la validación tras un error de red. */
  retry: () => void;
  /** Elimina el token. La redirección a /login la hace quien llama (y el guard). */
  logout: () => void;
};

const getServerToken = (): undefined => undefined;

export function useAuthSession(): AuthSession {
  const token = useSyncExternalStore<string | null | undefined>(subscribeAuthToken, readAuthToken, getServerToken);
  const [validation, dispatch] = useReducer(validationReducer, INITIAL_VALIDATION_STATE);
  const [controller] = useState(() => createAuthSessionController(dispatch));

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
