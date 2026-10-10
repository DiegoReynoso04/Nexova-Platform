'use client';

import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { asError } from '@/lib/api-client';
import { classifySubmitError } from '@/lib/submit-error';
import { createRecord, updateRecord } from '@/services/records.service';
import { useToast } from '@/components/ui/toast-notification';
import type { RecordCreate, RecordOut } from '@/types/record';

export type CandidateFormMode =
  | { kind: 'create' }
  | { kind: 'edit'; id: string; initialValues: RecordCreate };

export interface CandidateFormProps {
  mode: CandidateFormMode;
  onSuccess: (record: RecordOut) => void;
  onCancel: () => void;
}

interface FormValues {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string;
  cv_url: string;
  experience_years: string;
}

type FieldErrors = Partial<Record<keyof FormValues, string>>;

const EMPTY_VALUES: FormValues = {
  full_name: '',
  email: '',
  phone: '',
  position: '',
  linkedin_url: '',
  cv_url: '',
  experience_years: '',
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function toFormValues(mode: CandidateFormMode): FormValues {
  if (mode.kind === 'create') return EMPTY_VALUES;
  const { initialValues } = mode;
  return {
    full_name: initialValues.full_name,
    email: initialValues.email,
    phone: initialValues.phone,
    position: initialValues.position,
    linkedin_url: initialValues.linkedin_url ?? '',
    cv_url: initialValues.cv_url ?? '',
    experience_years: String(initialValues.experience_years),
  };
}

// Obligatorios + formato de email + experience_years numérico y >= 0 (§4.3).
// linkedin_url/cv_url son opcionales aquí: su validación de URL es cosa de
// candidate-detail.tsx al renderizarlos, no de este formulario.
function validate(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};

  if (!values.full_name.trim()) errors.full_name = 'El nombre es obligatorio.';
  if (!values.email.trim()) {
    errors.email = 'El email es obligatorio.';
  } else if (!EMAIL_PATTERN.test(values.email.trim())) {
    errors.email = 'Introduce un email válido.';
  }
  if (!values.phone.trim()) errors.phone = 'El teléfono es obligatorio.';
  if (!values.position.trim()) errors.position = 'El puesto es obligatorio.';

  const experience = values.experience_years.trim();
  if (!experience) {
    errors.experience_years = 'Los años de experiencia son obligatorios.';
  } else if (!Number.isFinite(Number(experience)) || Number(experience) < 0) {
    errors.experience_years = 'Debe ser un número igual o mayor que 0.';
  }

  return errors;
}

function toRecordCreate(values: FormValues): RecordCreate {
  return {
    full_name: values.full_name.trim(),
    email: values.email.trim(),
    phone: values.phone.trim(),
    position: values.position.trim(),
    linkedin_url: values.linkedin_url.trim() || null,
    cv_url: values.cv_url.trim() || null,
    experience_years: Number(values.experience_years.trim()),
  };
}

// §5.4 — detail[].loc termina en el nombre del campo del body. RecordCreate
// no tiene campos anidados ni listas, así que siempre es el último elemento.
function fieldNameFromLoc(loc: Array<string | number>): keyof FormValues | null {
  const last = loc[loc.length - 1];
  return typeof last === 'string' && last in EMPTY_VALUES ? (last as keyof FormValues) : null;
}

// Único componente para crear (POST /records) y editar (PUT /records/{id}),
// REQ-4. Campos: exactamente los de RecordCreate (§4.3). Sin status/stage:
// PUT no puede modificarlos (§5.2, V-3); esos controles viven en el
// detalle mediante candidate-status-controls.tsx y PATCH.
export function CandidateForm({ mode, onSuccess, onCancel }: CandidateFormProps) {
  const [values, setValues] = useState<FormValues>(() => toFormValues(mode));
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Tras un 2xx ilegible o un timeout la candidatura puede estar ya guardada:
  // se bloquea el reenvío para no duplicarla (lib/submit-error.ts).
  const [resubmitBlocked, setResubmitBlocked] = useState(false);
  const { notifySuccess, notifyError } = useToast();

  function updateField(field: keyof FormValues, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting || resubmitBlocked) return;

    const errors = validate(values);
    setFieldErrors(errors);
    setFormError(null);
    if (Object.keys(errors).length > 0) return;

    setIsSubmitting(true);
    const body = toRecordCreate(values);

    try {
      const record =
        mode.kind === 'create' ? await createRecord(body) : await updateRecord(mode.id, body);
      notifySuccess(
        mode.kind === 'create'
          ? `Candidatura de ${record.full_name} creada correctamente.`
          : `Candidatura de ${record.full_name} actualizada correctamente.`
      );
      onSuccess(record);
    } catch (caught) {
      const outcome = classifySubmitError(asError(caught));
      if (outcome.kind === 'validation') {
        const nextFieldErrors: FieldErrors = {};
        const unmatched: string[] = [];
        for (const item of outcome.detail) {
          const field = fieldNameFromLoc(item.loc);
          if (field) {
            nextFieldErrors[field] = item.msg;
          } else {
            unmatched.push(item.msg);
          }
        }
        setFieldErrors(nextFieldErrors);
        setFormError(unmatched.length > 0 ? unmatched.join(' ') : null);
        notifyError('No se pudo guardar: revisa los campos marcados.');
      } else {
        if (outcome.kind !== 'not_saved') setResubmitBlocked(true);
        setFormError(outcome.message);
        notifyError(outcome.message);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && (
        <p
          role="alert"
          className="rounded-control border border-danger-ink/20 bg-danger-surface px-3 py-2 text-sm text-danger-ink"
        >
          {formError}
        </p>
      )}

      <Input
        label="Nombre completo"
        value={values.full_name}
        onChange={(event) => updateField('full_name', event.target.value)}
        error={fieldErrors.full_name}
        autoComplete="name"
      />
      <Input
        label="Email"
        type="email"
        value={values.email}
        onChange={(event) => updateField('email', event.target.value)}
        error={fieldErrors.email}
        autoComplete="email"
      />
      <Input
        label="Teléfono"
        type="tel"
        value={values.phone}
        onChange={(event) => updateField('phone', event.target.value)}
        error={fieldErrors.phone}
        autoComplete="tel"
      />
      <Input
        label="Puesto"
        value={values.position}
        onChange={(event) => updateField('position', event.target.value)}
        error={fieldErrors.position}
      />
      <Input
        label="LinkedIn (opcional)"
        type="url"
        value={values.linkedin_url}
        onChange={(event) => updateField('linkedin_url', event.target.value)}
        error={fieldErrors.linkedin_url}
      />
      <Input
        label="CV (opcional, URL)"
        type="url"
        value={values.cv_url}
        onChange={(event) => updateField('cv_url', event.target.value)}
        error={fieldErrors.cv_url}
      />
      <Input
        label="Años de experiencia"
        type="number"
        inputMode="decimal"
        min={0}
        step="any"
        value={values.experience_years}
        onChange={(event) => updateField('experience_years', event.target.value)}
        error={fieldErrors.experience_years}
      />

      <div className="mt-2 flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
          Cancelar
        </Button>
        <Button type="submit" isLoading={isSubmitting} disabled={isSubmitting || resubmitBlocked}>
          {mode.kind === 'create' ? 'Crear candidatura' : 'Guardar cambios'}
        </Button>
      </div>
    </form>
  );
}
