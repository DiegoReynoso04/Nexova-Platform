// Envío de los formularios de cuenta: `/login` y `/register` (AUTH-02) y los
// de contraseña de AUTH-03. Cambian la operación del servicio y su validación
// en cliente (`validate`). Qué hacer tras el éxito
// (redirigir o confirmar) lo decide la vista. Evita envíos duplicados (REQ-5).

import { useCallback, useEffect, useRef, useState } from 'react';

import { describeAuthError } from '@/services/auth.service';
import type { AuthFormErrors } from '@/types/auth';

const NO_ERRORS: AuthFormErrors = { fields: {}, form: null };

export interface UseAuthFormResult<V> {
  isSubmitting: boolean;
  errors: AuthFormErrors;
  /** Valida en cliente, envía y llama a `onSuccess` si la operación terminó bien. */
  submit: (values: V, onSuccess: () => void) => void;
}

export function useAuthForm<V>(
  operation: (values: V) => Promise<void>,
  context: 'login' | 'register' | 'password',
  validate: (values: V) => AuthFormErrors | null
): UseAuthFormResult<V> {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<AuthFormErrors>(NO_ERRORS);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const submit = useCallback(
    (values: V, onSuccess: () => void) => {
      if (inFlight.current) return;
      const clientErrors = validate(values);
      if (clientErrors !== null) {
        setErrors(clientErrors);
        return;
      }
      inFlight.current = true;
      setIsSubmitting(true);
      setErrors(NO_ERRORS);
      operation(values)
        .then(() => {
          if (mounted.current) onSuccess();
        })
        .catch((error: unknown) => {
          if (mounted.current) setErrors(describeAuthError(error, context));
        })
        .finally(() => {
          inFlight.current = false;
          if (mounted.current) setIsSubmitting(false);
        });
    },
    [operation, context, validate]
  );

  return { isSubmitting, errors, submit };
}
