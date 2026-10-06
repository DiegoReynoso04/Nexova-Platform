'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { LOGIN_PATH } from '@/lib/auth-routes';
import { requestPasswordReset, validateForgotPassword } from '@/services/auth.service';
import type { ForgotPasswordFormValues } from '@/types/auth';

import { FormErrorMessage } from './form-error-message';

// Mismo texto exista o no el email: la API responde 200 en ambos casos.
export const FORGOT_PASSWORD_CONFIRMATION = 'Si esa dirección está registrada, recibirás un enlace en breve';

// /forgot-password (AUTH-03): `POST /auth/forgot-password` en services/api.
// Tras enviarlo, el formulario queda desactivado (sin peticiones duplicadas)
// y se muestra la confirmación. Solo un fallo de red o del servidor permite reintentar.
export function ForgotPasswordForm() {
  const { isSubmitting, errors, submit } = useAuthForm(requestPasswordReset, 'password', validateForgotPassword);
  const [values, setValues] = useState<ForgotPasswordFormValues>({ email: '' });
  const [isSent, setIsSent] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => setIsSent(true));
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <FormErrorMessage message={errors.form} />
      {isSent && (
        <p role="status" className="rounded-control border border-border bg-surface px-4 py-3 text-sm text-ink">
          {FORGOT_PASSWORD_CONFIRMATION}.
        </p>
      )}
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={values.email}
        disabled={isSubmitting || isSent}
        onChange={(event) => setValues({ email: event.target.value })}
        error={errors.fields.email}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" isLoading={isSubmitting} disabled={isSent}>
          {isSubmitting ? 'Enviando…' : isSent ? 'Enlace solicitado' : 'Enviar enlace'}
        </Button>
        <Link href={LOGIN_PATH} className="text-sm font-medium text-brand underline underline-offset-4">
          Volver a iniciar sesión
        </Link>
      </div>
    </form>
  );
}
