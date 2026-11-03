// Embudo de los formularios de autenticación (login, registro y contraseñas)
// para la telemetría, en el hook compartido (hooks/use-auth-form.ts), no en
// cada página. Decisión D4 del ticket de captura: `login_failed` es de la API
// (plan §6.3); aquí el fallo del login queda en `form_submitted` con su
// `outcome` (`api_rejected` con credenciales incorrectas, `network_error` sin
// red). Nunca el email ni la contraseña: solo el resultado y nombres de campo.

import { ApiAbortError } from '@/lib/api-client';
import type { FormTelemetry } from '@/lib/form-telemetry';
import { AuthServiceError } from '@/services/auth.service';
import type { AuthUiError } from '@/types/auth';
import type { FormOutcome } from '@/types/telemetry';

/** `kind` del error del servicio de autenticación → `outcome` de `form_submitted`. */
export function authFormOutcome(error: AuthUiError): FormOutcome {
  switch (error.kind) {
    case 'validation':
      return 'validation_error';
    case 'invalid_credentials':
    case 'registered_login_failed':
    case 'profile_not_found':
    case 'invalid_reset_token':
    case 'request_invalid':
      return 'api_rejected';
    case 'session_expired':
      return 'session_expired';
    case 'network':
    case 'timeout':
    case 'config':
      return 'network_error';
    case 'server_error':
    case 'unexpected_response':
      return 'server_error';
  }
}

/** Envuelve la operación del servicio sin cambiar lo que devuelve ni lo que lanza. */
export function observeAuthOperation<V, O>(
  operation: (values: V, options: O) => Promise<void>,
  telemetry: Pick<FormTelemetry, 'validationFailed' | 'submitted'>
): (values: V, options: O) => Promise<void> {
  return async (values, options) => {
    try {
      await operation(values, options);
      telemetry.submitted('success');
    } catch (error) {
      if (error instanceof AuthServiceError) {
        const uiError = error.uiError;
        if (uiError.kind === 'validation' && uiError.source === 'client') {
          telemetry.validationFailed(uiError.errors.map((item) => item.field ?? 'general'));
        } else {
          telemetry.submitted(authFormOutcome(uiError));
        }
      } else if (!(error instanceof ApiAbortError)) {
        telemetry.submitted('server_error');
      }
      throw error;
    }
  };
}
