'use client';

import { useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { changePassword } from '@/services/auth.service';
import type { ChangePasswordFormValues } from '@/types/auth';

import { AuthError, fieldErrorFor } from './auth-error';

const EMPTY_VALUES: ChangePasswordFormValues = { current_password: '', new_password: '', password_confirmation: '' };

// Formulario de /account/change-password (ruta protegida): `POST
// /auth/change-password`. Que la nueva y la confirmación coincidan se comprueba
// antes de llamar a la API (services/auth.service.ts). Una contraseña actual
// incorrecta (400) se muestra junto a su campo; la sesión sigue abierta.
export function ChangePasswordView() {
  const { state, submit } = useAuthForm(changePassword);
  const [values, setValues] = useState<ChangePasswordFormValues>(EMPTY_VALUES);
  const error = state.status === 'error' ? state.error : null;
  const isSaving = state.status === 'submitting';

  function set(field: keyof ChangePasswordFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Con éxito se vacían los campos: las contraseñas no se quedan en el estado.
    submit(values, () => setValues(EMPTY_VALUES));
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error !== null && <AuthError error={error} id="change-password-errors" />}
      {state.status === 'success' && (
        <Alert variant="info" title="Contraseña actualizada">
          <p>Usa la contraseña nueva la próxima vez que inicies sesión.</p>
        </Alert>
      )}
      <Input
        label="Contraseña actual"
        type="password"
        autoComplete="current-password"
        value={values.current_password}
        onChange={(event) => set('current_password', event.target.value)}
        error={fieldErrorFor(error, 'current_password')}
      />
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
        <Button type="submit" isLoading={isSaving}>
          {isSaving ? 'Guardando…' : 'Cambiar contraseña'}
        </Button>
      </div>
    </form>
  );
}
