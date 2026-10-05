// Envío de los formularios públicos de autenticación (`/login` y `/register`).
// Un solo hook para los dos: la diferencia está en la operación del servicio
// (`login` o `register`), que ya comparten el paso de login y el guardado del
// token (services/auth.service.ts). La redirección tras el éxito la hace la vista.
//
// Reducer puro + controlador sin React (probado con `node --test`) + hook.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { AuthServiceError } from '@/services/auth.service';
import type { AuthUiError } from '@/types/auth';

export type AuthFormState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success' }
  | { status: 'error'; error: AuthUiError };

export type AuthFormAction =
  | { type: 'submit_started' }
  | { type: 'submit_succeeded' }
  | { type: 'submit_failed'; error: AuthUiError };

export const INITIAL_AUTH_FORM_STATE: AuthFormState = { status: 'idle' };

export function authFormReducer(_state: AuthFormState, action: AuthFormAction): AuthFormState {
  switch (action.type) {
    case 'submit_started':
      return { status: 'submitting' };
    case 'submit_succeeded':
      return { status: 'success' };
    case 'submit_failed':
      return { status: 'error', error: action.error };
  }
}

export type AuthOperation<V> = (values: V, options: { signal: AbortSignal }) => Promise<void>;

export interface AuthFormController<V> {
  activate(): void;
  dispose(): void;
  /** Ignorado si ya hay un envío en curso (evita envíos duplicados). Resuelve a `true` si tuvo éxito. */
  submit(values: V): Promise<boolean>;
}

const FALLBACK_ERROR: AuthUiError = { kind: 'unexpected_response' };

export function createAuthFormController<V>(
  dispatch: (action: AuthFormAction) => void,
  operation: AuthOperation<V>
): AuthFormController<V> {
  let active = false;
  let controller: AbortController | null = null;

  return {
    activate() {
      active = true;
    },

    dispose() {
      active = false;
      controller?.abort();
      controller = null;
    },

    async submit(values) {
      if (!active || controller !== null) return false;
      const current = new AbortController();
      controller = current;
      dispatch({ type: 'submit_started' });
      try {
        await operation(values, { signal: current.signal });
        if (!active) return false;
        dispatch({ type: 'submit_succeeded' });
        return true;
      } catch (error) {
        if (!active || error instanceof ApiAbortError) return false;
        dispatch({ type: 'submit_failed', error: error instanceof AuthServiceError ? error.uiError : FALLBACK_ERROR });
        return false;
      } finally {
        if (controller === current) controller = null;
      }
    },
  };
}

export interface UseAuthFormResult<V> {
  state: AuthFormState;
  /** Envía el formulario y llama a `onSuccess` si el token quedó guardado. */
  submit: (values: V, onSuccess: () => void) => void;
}

export function useAuthForm<V>(operation: AuthOperation<V>): UseAuthFormResult<V> {
  const [state, dispatch] = useReducer(authFormReducer, INITIAL_AUTH_FORM_STATE);
  // La operación (login o register) es fija para cada vista: el controlador se crea una vez.
  const [controller] = useState(() => createAuthFormController(dispatch, operation));

  useEffect(() => {
    controller.activate();
    return () => controller.dispose();
  }, [controller]);

  const submit = useCallback(
    (values: V, onSuccess: () => void) => {
      void controller.submit(values).then((succeeded) => {
        if (succeeded) onSuccess();
      });
    },
    [controller]
  );

  return { state, submit };
}
