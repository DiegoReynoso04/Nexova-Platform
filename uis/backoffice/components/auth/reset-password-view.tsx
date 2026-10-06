'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm, type AuthOperation } from '@/hooks/use-auth-form';
import { FORGOT_PASSWORD_PATH, LOGIN_PATH, RESET_PASSWORD_PATH } from '@/lib/auth-routes';
import { resetPassword } from '@/services/auth.service';
import type { ResetPasswordFormValues } from '@/types/auth';

import { AuthError, fieldErrorFor } from './auth-error';

/** Destino tras restablecer: /login muestra el aviso de éxito (ver LoginView). */
export const LOGIN_AFTER_RESET_PATH = `${LOGIN_PATH}?reset=success`;

// Formulario de /reset-password. El token llega en `?token=` desde el enlace
// del email: se lee una vez y se quita de la barra de direcciones (no queda en
// el historial ni se envía como Referer). Con éxito → /login con aviso; si el
// token falta, no es válido, caducó o ya se usó → error y enlace a /forgot-password.
export function ResetPasswordView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [token] = useState(() => searchParams.get('token') ?? '');
  // El token es fijo durante la vida de la vista: la operación se crea una vez.
  const [operation] = useState(() => {
    const send: AuthOperation<ResetPasswordFormValues> = (values, options) => resetPassword(token, values, options);
    return send;
  });
  const { state, submit } = useAuthForm(operation);
  const [values, setValues] = useState<ResetPasswordFormValues>({ new_password: '', password_confirmation: '' });
  const error = state.status === 'error' ? state.error : null;
  const isBusy = state.status === 'submitting' || state.status === 'success';
  const linkIsInvalid = token === '' || error?.kind === 'invalid_reset_token';

  useEffect(() => {
    if (window.location.search !== '') window.history.replaceState(null, '', RESET_PASSWORD_PATH);
  }, []);

  function set(field: keyof ResetPasswordFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => router.replace(LOGIN_AFTER_RESET_PATH));
  }

  if (linkIsInvalid) {
    return (
      <div className="flex flex-col gap-4">
        <AuthError error={{ kind: 'invalid_reset_token' }} id="reset-password-errors" />
        <p className="text-sm">
          <Link href={FORGOT_PASSWORD_PATH} className="font-medium text-brand underline underline-offset-4">
            Solicitar un enlace nuevo
          </Link>
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error !== null && <AuthError error={error} id="reset-password-errors" />}
      <Input
        label="Contraseña nueva"
        type="password"
        autoComplete="new-password"
        value={values.new_password}
        onChange={(event) => set('new_password', event.target.value)}
        error={fieldErrorFor(error, 'new_password')}
        hint="Mínimo 8 caracteres."
      />
      <Input
        label="Repite la contraseña nueva"
        type="password"
        autoComplete="new-password"
        value={values.password_confirmation}
        onChange={(event) => set('password_confirmation', event.target.value)}
        error={fieldErrorFor(error, 'password_confirmation')}
      />
      <div>
        <Button type="submit" isLoading={isBusy}>
          {isBusy ? 'Guardando…' : 'Guardar contraseña'}
        </Button>
      </div>
    </form>
  );
}
