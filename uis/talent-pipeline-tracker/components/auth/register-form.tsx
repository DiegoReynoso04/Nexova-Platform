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

import { FormErrorMessage } from './form-error-message';

const EMPTY_REGISTER_FORM: RegisterFormValues = { email: '', password: '', name: '', phone: '', address: '' };

// /register: `POST /users` (con los datos de perfil opcionales que admite la
// API) y después `POST /auth/login` con las mismas credenciales. Los errores
// 422/409 se muestran junto a su campo.
export function RegisterForm() {
  const router = useRouter();
  const { isSubmitting, errors, submit } = useAuthForm(register, 'register');
  const [values, setValues] = useState<RegisterFormValues>(EMPTY_REGISTER_FORM);

  function set(field: AuthField, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(values, () => router.replace(HOME_PATH));
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <p className="text-xs text-ink-muted">Email y contraseña son obligatorios (mínimo 8 caracteres); el resto es opcional.</p>
      <FormErrorMessage message={errors.form} />
      <Input
        label="Email *"
        type="email"
        autoComplete="email"
        value={values.email}
        onChange={(event) => set('email', event.target.value)}
        error={errors.fields.email}
      />
      <Input
        label="Contraseña *"
        type="password"
        autoComplete="new-password"
        value={values.password}
        onChange={(event) => set('password', event.target.value)}
        error={errors.fields.password}
      />
      <Input
        label="Nombre"
        autoComplete="name"
        value={values.name}
        onChange={(event) => set('name', event.target.value)}
        error={errors.fields.name}
      />
      <Input
        label="Teléfono"
        type="tel"
        autoComplete="tel"
        value={values.phone}
        onChange={(event) => set('phone', event.target.value)}
        error={errors.fields.phone}
      />
      <Input
        label="Dirección"
        autoComplete="street-address"
        value={values.address}
        onChange={(event) => set('address', event.target.value)}
        error={errors.fields.address}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" isLoading={isSubmitting}>
          {isSubmitting ? 'Creando cuenta…' : 'Crear cuenta'}
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
