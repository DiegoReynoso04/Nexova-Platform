'use client';

import { useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useProfile, type ProfileSaveState } from '@/hooks/use-profile';
import type { CurrentUser, ProfileFormValues } from '@/types/auth';

import { AuthError, fieldErrorFor } from './auth-error';

function formValuesFrom(user: CurrentUser): ProfileFormValues {
  return {
    name: user.profile?.name ?? '',
    phone: user.profile?.phone ?? '',
    address: user.profile?.address ?? '',
  };
}

function display(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : value;
}

// Vista de /account/profile: datos de `GET /auth/me` (email del User y
// nombre, teléfono y dirección del Profile) y edición con `PUT /profiles/me`.
export function ProfileView() {
  const { load, save: saveState, reload, saveProfile, resetSave } = useProfile();

  if (load.status === 'loading') return <LoadingSpinner label="Cargando tu perfil…" />;
  if (load.status === 'error') {
    return (
      <div className="flex flex-col gap-3">
        <AuthError error={load.error} />
        <div>
          <Button variant="secondary" onClick={reload}>
            Reintentar
          </Button>
        </div>
      </div>
    );
  }

  const { user } = load;
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="account-data" className="rounded-lg border border-border bg-surface p-6">
        <h2 id="account-data" className="text-sm font-semibold text-ink">
          Datos de la cuenta
        </h2>
        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">Email</dt>
            <dd className="text-sm break-all text-ink">{user.email}</dd>
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

      <section aria-labelledby="profile-edit" className="rounded-lg border border-border bg-surface p-6">
        <h2 id="profile-edit" className="text-sm font-semibold text-ink">
          Editar nombre y contacto
        </h2>
        {/* `key`: el formulario se reinicia con los datos guardados tras cada respuesta de la API. */}
        <ProfileForm
          key={`${user.profile?.name ?? ''}|${user.profile?.phone ?? ''}|${user.profile?.address ?? ''}`}
          initialValues={formValuesFrom(user)}
          saveState={saveState}
          onSave={saveProfile}
          onChange={resetSave}
        />
      </section>
    </div>
  );
}

interface ProfileFormProps {
  initialValues: ProfileFormValues;
  saveState: ProfileSaveState;
  onSave: (values: ProfileFormValues) => void;
  onChange: () => void;
}

function ProfileForm({ initialValues, saveState, onSave, onChange }: ProfileFormProps) {
  const [values, setValues] = useState<ProfileFormValues>(initialValues);
  const error = saveState.status === 'error' ? saveState.error : null;
  const isSaving = saveState.status === 'saving';

  function set(field: keyof ProfileFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    if (saveState.status === 'success' || saveState.status === 'error') onChange();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSave(values);
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mt-4 flex flex-col gap-4">
      {error !== null && <AuthError error={error} id="profile-errors" />}
      {saveState.status === 'success' && <Alert variant="info" title="Perfil actualizado" />}
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
      <p className="text-xs text-ink-muted">Deja un campo vacío para borrar ese dato.</p>
      <div>
        <Button type="submit" isLoading={isSaving}>
          {isSaving ? 'Guardando…' : 'Guardar cambios'}
        </Button>
      </div>
    </form>
  );
}
