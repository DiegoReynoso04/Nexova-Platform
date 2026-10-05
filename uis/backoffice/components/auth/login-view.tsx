'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { HOME_PATH, REGISTER_PATH } from '@/lib/auth-routes';
import { login } from '@/services/auth.service';
import type { LoginFormValues } from '@/types/auth';

import { AuthError, fieldErrorFor } from './auth-error';

// Formulario de /login: `POST /auth/login` (el servicio guarda el token solo
// si la respuesta es correcta) y, si va bien, la vista principal.
export function LoginView() {
  const router = useRouter();
  const { state, submit } = useAuthForm(login);
  const [values, setValues] = useState<LoginFormValues>({ email: '', password: '' });
  const error = state.status === 'error' ? state.error : null;
  const isBusy = state.status === 'submitting' || state.status === 'success';

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => router.replace(HOME_PATH));
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error !== null && <AuthError error={error} id="login-errors" />}
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        value={values.email}
        onChange={(event) => setValues((current) => ({ ...current, email: event.target.value }))}
        error={fieldErrorFor(error, 'email')}
      />
      <Input
        label="Contraseña"
        type="password"
        autoComplete="current-password"
        value={values.password}
        onChange={(event) => setValues((current) => ({ ...current, password: event.target.value }))}
        error={fieldErrorFor(error, 'password')}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" isLoading={isBusy}>
          {isBusy ? 'Entrando…' : 'Iniciar sesión'}
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
