'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { HOME_PATH, LOGIN_PATH } from '@/lib/auth-routes';
import { register } from '@/services/auth.service';
import type { AuthField, RegisterFormValues } from '@/types/auth';

import { AuthError, fieldErrorFor } from './auth-error';

const EMPTY_REGISTER_FORM: RegisterFormValues = { email: '', password: '', name: '', phone: '', address: '' };

// Formulario de /register: `POST /users` (con los datos de perfil opcionales
// que admite la API) y después `POST /auth/login` con las mismas credenciales.
// Los errores 422/409 de la API se muestran junto a su campo.
export function RegisterView() {
  const router = useRouter();
  const { state, submit } = useAuthForm(register);
  const [values, setValues] = useState<RegisterFormValues>(EMPTY_REGISTER_FORM);
  const error = state.status === 'error' ? state.error : null;
  const isBusy = state.status === 'submitting' || state.status === 'success';

  function set(field: AuthField, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => router.replace(HOME_PATH));
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <p className="text-xs text-ink-muted">Email y contraseña son obligatorios; el resto de datos es opcional.</p>
      {error !== null && <AuthError error={error} id="register-errors" />}
      <Input
        label="Email *"
        type="email"
        autoComplete="email"
        value={values.email}
        onChange={(event) => set('email', event.target.value)}
        error={fieldErrorFor(error, 'email')}
      />
      <Input
        label="Contraseña *"
        type="password"
        autoComplete="new-password"
        hint="Mínimo 8 caracteres."
        value={values.password}
        onChange={(event) => set('password', event.target.value)}
        error={fieldErrorFor(error, 'password')}
      />
      <Input
        label="Nombre"
        autoComplete="name"
        value={values.name}
        onChange={(event) => set('name', event.target.value)}
        error={fieldErrorFor(error, 'name')}
      />
      <Input
        label="Teléfono"
        type="tel"
        autoComplete="tel"
        value={values.phone}
        onChange={(event) => set('phone', event.target.value)}
        error={fieldErrorFor(error, 'phone')}
      />
      <Input
        label="Dirección"
        autoComplete="street-address"
        value={values.address}
        onChange={(event) => set('address', event.target.value)}
        error={fieldErrorFor(error, 'address')}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" isLoading={isBusy}>
          {isBusy ? 'Creando cuenta…' : 'Crear cuenta'}
        </Button>
        <p className="text-sm text-ink-muted">
          ¿Ya tienes cuenta?{' '}
          <Link href={LOGIN_PATH} className="font-medium text-brand underline underline-offset-4">
            Iniciar sesión
          </Link>
        </p>
      </div>
    </form>
  );
}
