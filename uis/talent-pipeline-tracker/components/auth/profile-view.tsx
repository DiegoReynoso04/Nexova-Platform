'use client';

import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useToast } from '@/components/ui/toast-notification';
import { useProfile } from '@/hooks/use-profile';
import type { AuthFormErrors, CurrentUser, ProfileFormValues } from '@/types/auth';

import { FormErrorMessage } from './form-error-message';

function formValuesFrom(user: CurrentUser): ProfileFormValues {
  return { name: user.profile?.name ?? '', phone: user.profile?.phone ?? '', address: user.profile?.address ?? '' };
}

function display(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : value;
}

// /account/profile: datos de `GET /auth/me` (email del User; nombre, teléfono
// y dirección del Profile) y edición con `PUT /profiles/me`.
export function ProfileView() {
  const { load, isSaving, saveErrors, reload, saveProfile } = useProfile();

  if (load.status === 'loading') return <LoadingSpinner label="Cargando tu perfil…" />;
  if (load.status === 'error') {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-control border border-danger-ink/20 bg-danger-surface p-6 text-danger-ink"
      >
        <p className="text-sm">No se pudo cargar tu perfil. {load.message}</p>
        <Button variant="secondary" onClick={reload}>
          Reintentar
        </Button>
      </div>
    );
  }

  const { user } = load;
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="account-data" className="rounded-control border border-border bg-surface p-6">
        <h2 id="account-data" className="text-sm font-semibold text-ink">
          Datos de la cuenta
        </h2>
        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">Email</dt>
            <dd className="break-all text-sm text-ink">{user.email}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">Nombre</dt>
            <dd className="text-sm text-ink">{display(user.profile?.name)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">Teléfono</dt>
            <dd className="text-sm text-ink">{display(user.profile?.phone)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">Dirección</dt>
            <dd className="text-sm text-ink">{display(user.profile?.address)}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="profile-edit" className="rounded-control border border-border bg-surface p-6">
        <h2 id="profile-edit" className="text-sm font-semibold text-ink">
          Editar nombre y contacto
        </h2>
        {/* `key`: el formulario se reinicia con los datos guardados tras cada respuesta de la API. */}
        <ProfileForm
          key={`${user.profile?.name ?? ''}|${user.profile?.phone ?? ''}|${user.profile?.address ?? ''}`}
          initialValues={formValuesFrom(user)}
          isSaving={isSaving}
          errors={saveErrors}
          onSave={saveProfile}
        />
      </section>
    </div>
  );
}

interface ProfileFormProps {
  initialValues: ProfileFormValues;
  isSaving: boolean;
  errors: AuthFormErrors | null;
  onSave: (values: ProfileFormValues) => Promise<boolean>;
}

function ProfileForm({ initialValues, isSaving, errors, onSave }: ProfileFormProps) {
  const { notifySuccess } = useToast();
  const [values, setValues] = useState<ProfileFormValues>(initialValues);

  function set(field: keyof ProfileFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onSave(values).then((saved) => {
      if (saved) notifySuccess('Perfil actualizado.');
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mt-4 flex flex-col gap-4">
      <FormErrorMessage message={errors?.form ?? null} />
      <Input
        label="Nombre"
        autoComplete="name"
        value={values.name}
        onChange={(event) => set('name', event.target.value)}
        error={errors?.fields.name}
      />
      <Input
        label="Teléfono"
        type="tel"
        autoComplete="tel"
        value={values.phone}
        onChange={(event) => set('phone', event.target.value)}
        error={errors?.fields.phone}
      />
      <Input
        label="Dirección"
        autoComplete="street-address"
        value={values.address}
        onChange={(event) => set('address', event.target.value)}
        error={errors?.fields.address}
      />
      <p className="text-xs text-ink-muted">Deja un campo vacío para borrar ese dato.</p>
      <div>
        <Button type="submit" isLoading={isSaving}>
          {isSaving ? 'Guardando…' : 'Guardar cambios'}
        </Button>
      </div>
    </form>
  );
}
