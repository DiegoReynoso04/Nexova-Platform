'use client';

import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthForm } from '@/hooks/use-auth-form';
import { changePassword, validateChangePassword } from '@/services/auth.service';
import type { ChangePasswordFormValues } from '@/types/auth';

import { FormErrorMessage } from './form-error-message';

const EMPTY_VALUES: ChangePasswordFormValues = { current_password: '', new_password: '', password_confirmation: '' };

// /account/change-password (protegida, AUTH-03): `POST /auth/change-password`.
// Que la nueva y la confirmación coincidan se comprueba antes de llamar a la
// API. Una contraseña actual incorrecta (400) se muestra junto a su campo.
export function ChangePasswordForm() {
  const { isSubmitting, errors, submit } = useAuthForm(changePassword, 'password', validateChangePassword);
  const [values, setValues] = useState<ChangePasswordFormValues>(EMPTY_VALUES);
  const [isSaved, setIsSaved] = useState(false);

  function set(field: keyof ChangePasswordFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setIsSaved(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaved(false);
    // Con éxito se vacían los campos: las contraseñas no se quedan en el estado.
    submit(values, () => {
      setValues(EMPTY_VALUES);
      setIsSaved(true);
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <FormErrorMessage message={errors.form} />
      {isSaved && (
        <p role="status" className="rounded-control border border-border bg-surface px-4 py-3 text-sm text-ink">
          Contraseña actualizada. Usa la contraseña nueva la próxima vez que inicies sesión.
        </p>
      )}
      <Input
        label="Contraseña actual"
        type="password"
        autoComplete="current-password"
        value={values.current_password}
        onChange={(event) => set('current_password', event.target.value)}
        error={errors.fields.current_password}
      />
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
        <Button type="submit" isLoading={isSubmitting}>
          {isSubmitting ? 'Guardando…' : 'Cambiar contraseña'}
        </Button>
      </div>
    </form>
  );
}
