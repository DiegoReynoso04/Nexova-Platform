// Envío de los formularios de autenticación: `/login` y `/register` (AUTH-02) y
// los de contraseña de AUTH-03 (`/forgot-password`, `/reset-password`,
// `/account/change-password`). Un solo hook: la diferencia está en la operación
// del servicio (services/auth.service.ts). Qué hacer tras el éxito (redirigir o
// mostrar una confirmación) lo decide la vista.
//
// Reducer puro + controlador sin React (probado con `node --test`) + hook.
//
// Telemetría (ticket de captura): con `form`, el hook envuelve la operación
// (lib/auth-telemetry.ts) para `form_validation_failed` y `form_submitted`, y
// `form_abandoned` al salir. Estos formularios no avisan de cada campo: el
// embudo empieza en el primer envío.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { useFormTelemetry } from '@/hooks/use-form-telemetry';
import { ApiAbortError } from '@/lib/api-client';
import { observeAuthOperation } from '@/lib/auth-telemetry';
import { AuthServiceError } from '@/services/auth.service';
import type { AuthUiError } from '@/types/auth';
import type { TelemetryForm } from '@/types/telemetry';

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

export function useAuthForm<V>(operation: AuthOperation<V>, form: TelemetryForm): UseAuthFormResult<V> {
  const [state, dispatch] = useReducer(authFormReducer, INITIAL_AUTH_FORM_STATE);
  const telemetry = useFormTelemetry(form);
  // La operación (login o register) es fija para cada vista: el controlador se crea una vez.
  const [controller] = useState(() => createAuthFormController(dispatch, observeAuthOperation(operation, telemetry)));

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
