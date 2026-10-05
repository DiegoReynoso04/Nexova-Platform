// Envío de los formularios públicos `/login` y `/register` (AUTH-02). Un solo
// hook para ambos: cambia la operación del servicio (`login` o `register`),
// que ya comparten el paso de login y el guardado del token. La redirección
// tras el éxito la hace la vista. Evita envíos duplicados (REQ-5).

import { useCallback, useEffect, useRef, useState } from 'react';

import { describeAuthError, validateCredentials } from '@/services/auth.service';
import type { AuthFormErrors, LoginFormValues } from '@/types/auth';

const NO_ERRORS: AuthFormErrors = { fields: {}, form: null };

export interface UseAuthFormResult<V extends LoginFormValues> {
  isSubmitting: boolean;
  errors: AuthFormErrors;
  /** Valida en cliente, envía y llama a `onSuccess` si el token quedó guardado. */
  submit: (values: V, onSuccess: () => void) => void;
}

export function useAuthForm<V extends LoginFormValues>(
  operation: (values: V) => Promise<void>,
  context: 'login' | 'register'
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
      const clientErrors = validateCredentials(values);
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
    [operation, context]
  );

  return { isSubmitting, errors, submit };
}
