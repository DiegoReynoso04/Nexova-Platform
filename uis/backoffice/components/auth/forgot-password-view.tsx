'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { LOGIN_PATH } from '@/lib/auth-routes';
import { requestPasswordReset } from '@/services/auth.service';
import type { ForgotPasswordFormValues } from '@/types/auth';

import { AuthError, fieldErrorFor } from './auth-error';

// Mismo texto exista o no el email: la API responde 200 en ambos casos y la
// vista no puede (ni debe) distinguirlos.
export const FORGOT_PASSWORD_CONFIRMATION = 'Si esa dirección está registrada, recibirás un enlace en breve';

// Formulario de /forgot-password: `POST /auth/forgot-password`. Tras enviarlo,
// el formulario queda desactivado (sin peticiones duplicadas) y se muestra la
// confirmación. Solo un fallo de red o del servidor permite volver a enviarlo.
export function ForgotPasswordView() {
  const { state, submit } = useAuthForm(requestPasswordReset);
  const [values, setValues] = useState<ForgotPasswordFormValues>({ email: '' });
  const error = state.status === 'error' ? state.error : null;
  const isSent = state.status === 'success';
  const isDisabled = state.status === 'submitting' || isSent;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => undefined);
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error !== null && <AuthError error={error} id="forgot-password-errors" />}
      {isSent && (
        <Alert variant="info" title="Solicitud enviada">
          <p>{FORGOT_PASSWORD_CONFIRMATION}.</p>
        </Alert>
      )}
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={values.email}
        disabled={isDisabled}
        onChange={(event) => setValues({ email: event.target.value })}
        error={fieldErrorFor(error, 'email')}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" isLoading={state.status === 'submitting'} disabled={isSent}>
          {state.status === 'submitting' ? 'Enviando…' : isSent ? 'Enlace solicitado' : 'Enviar enlace'}
        </Button>
        <Link href={LOGIN_PATH} className="text-sm font-medium text-brand underline underline-offset-4">
          Volver a iniciar sesión
        </Link>
      </div>
    </form>
  );
}
