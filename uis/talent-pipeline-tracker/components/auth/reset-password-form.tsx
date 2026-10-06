'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { FORGOT_PASSWORD_PATH, LOGIN_PATH, RESET_PASSWORD_PATH } from '@/lib/auth-routes';
import { InvalidResetTokenError, resetPassword, validateResetPassword } from '@/services/auth.service';
import type { ResetPasswordFormValues } from '@/types/auth';

import { FormErrorMessage } from './form-error-message';

/** Destino tras restablecer: /login muestra el aviso de éxito (ver LoginForm). */
export const LOGIN_AFTER_RESET_PATH = `${LOGIN_PATH}?reset=success`;

// /reset-password (AUTH-03). El token llega en `?token=` desde el enlace del
// email: se lee una vez y se quita de la barra de direcciones. Con éxito →
// /login con aviso; si falta, no es válido, caducó o ya se usó → error y
// enlace a /forgot-password.
export function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [token] = useState(() => searchParams.get('token') ?? '');
  // El token es fijo durante la vida de la vista: la operación se crea una vez.
  const [operation] = useState(() => (values: ResetPasswordFormValues) => resetPassword(token, values));
  const { isSubmitting, errors, submit } = useAuthForm(operation, 'password', validateResetPassword);
  const [values, setValues] = useState<ResetPasswordFormValues>({ new_password: '', password_confirmation: '' });
  const [isDone, setIsDone] = useState(false);
  const linkIsInvalid = token === '' || errors.invalidResetToken === true;

  useEffect(() => {
    if (window.location.search !== '') window.history.replaceState(null, '', RESET_PASSWORD_PATH);
  }, []);

  function set(field: keyof ResetPasswordFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => {
      setIsDone(true);
      router.replace(LOGIN_AFTER_RESET_PATH);
    });
  }

  if (linkIsInvalid) {
    return (
      <div className="flex flex-col gap-4">
        <FormErrorMessage message={new InvalidResetTokenError().message} />
        <p className="text-sm">
          <Link href={FORGOT_PASSWORD_PATH} className="font-medium text-brand underline underline-offset-4">
            Solicitar un enlace nuevo
          </Link>
        </p>
      </div>
    );
  }

  const isBusy = isSubmitting || isDone;
  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <FormErrorMessage message={errors.form} />
      <Input
        label="Contraseña nueva (mínimo 8 caracteres)"
        type="password"
        autoComplete="new-password"
        value={values.new_password}
        onChange={(event) => set('new_password', event.target.value)}
        error={errors.fields.new_password}
      />
      <Input
        label="Repite la contraseña nueva"
        type="password"
        autoComplete="new-password"
        value={values.password_confirmation}
        onChange={(event) => set('password_confirmation', event.target.value)}
        error={errors.fields.password_confirmation}
      />
      <div>
        <Button type="submit" isLoading={isBusy}>
          {isBusy ? 'Guardando…' : 'Guardar contraseña'}
        </Button>
      </div>
    </form>
  );
}
