'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { FORGOT_PASSWORD_PATH, HOME_PATH, REGISTER_PATH } from '@/lib/auth-routes';
import { login, validateCredentials } from '@/services/auth.service';
import type { LoginFormValues } from '@/types/auth';

import { FormErrorMessage } from './form-error-message';

// /login: `POST /auth/login` en services/api; el servicio guarda el token
// solo si la respuesta es válida. Después, el listado de candidaturas. Con
// `?reset=success` (al volver de /reset-password, AUTH-03) muestra un aviso.
export function LoginForm() {
  const router = useRouter();
  const passwordWasReset = useSearchParams().get('reset') === 'success';
  const { isSubmitting, errors, submit } = useAuthForm(login, 'login', validateCredentials);
  const [values, setValues] = useState<LoginFormValues>({ email: '', password: '' });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => router.replace(HOME_PATH));
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <FormErrorMessage message={errors.form} />
      {passwordWasReset && errors.form === null && (
        <p role="status" className="rounded-control border border-border bg-surface px-4 py-3 text-sm text-ink">
          Contraseña restablecida. Ya puedes iniciar sesión con tu contraseña nueva.
        </p>
      )}
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={values.email}
        onChange={(event) => setValues((current) => ({ ...current, email: event.target.value }))}
        error={errors.fields.email}
      />
      <Input
        label="Contraseña"
        type="password"
        autoComplete="current-password"
        value={values.password}
        onChange={(event) => setValues((current) => ({ ...current, password: event.target.value }))}
        error={errors.fields.password}
      />
      <p className="text-sm">
        <Link href={FORGOT_PASSWORD_PATH} className="font-medium text-brand underline underline-offset-4">
          ¿Olvidaste tu contraseña?
        </Link>
      </p>
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" isLoading={isSubmitting}>
          {isSubmitting ? 'Entrando…' : 'Iniciar sesión'}
        </Button>
        <p className="text-sm text-ink-muted">
          ¿No tienes cuenta?{' '}
          <Link href={REGISTER_PATH} className="font-medium text-brand underline underline-offset-4">
            Crear cuenta
          </Link>
        </p>
      </div>
    </form>
  );
}
