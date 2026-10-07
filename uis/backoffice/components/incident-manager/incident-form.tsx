import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import type { SubmitState } from '@/hooks/use-incident-form';
import { validateIncidentForm } from '@/services/incident-manager.service';
import {
  BRANCH_LABELS,
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INITIAL_INCIDENT_STATUS,
  TITLE_MAX_LENGTH,
  type IncidentField,
  type IncidentFieldError,
  type IncidentFormValues,
} from '@/types/incident-manager';

import { IncidentError } from './incident-error';

export const EMPTY_INCIDENT_FORM: IncidentFormValues = {
  title: '',
  description: '',
  category: '',
  origin: '',
  branch: '',
};

export interface IncidentFormProps {
  submit: SubmitState;
  onSubmit: (values: IncidentFormValues) => void;
}

const CONTROL_CLASSES =
  'w-full rounded-control border bg-surface px-3 py-2 text-sm text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand';

function pick<T extends string>(values: readonly T[], value: string): T | '' {
  return values.find((candidate) => candidate === value) ?? '';
}

function borderFor(error: string | null): string {
  return error === null ? 'border-border' : 'border-danger-ink';
}

// Formulario de registro (POST /api/incidents). Valida en cliente los campos
// obligatorios y el largo del título antes de enviar: si no pasa, no hay
// petición. Los errores de la API llegan ya con textos propios del frontend y,
// si identifican un campo, se muestran junto a él.
export function IncidentForm({ submit, onSubmit }: IncidentFormProps) {
  const [values, setValues] = useState<IncidentFormValues>(EMPTY_INCIDENT_FORM);
  // Errores de cliente del último intento; se recalculan al enviar.
  const [clientErrors, setClientErrors] = useState<readonly IncidentFieldError[]>([]);
  const [attempt, setAttempt] = useState(0);
  const isSubmitting = submit.status === 'submitting';
  const apiError = submit.status === 'error' ? submit.error : null;
  const fieldErrors: readonly IncidentFieldError[] =
    clientErrors.length > 0 ? clientErrors : apiError?.kind === 'validation' ? apiError.errors : [];
  const summaryError =
    clientErrors.length > 0 ? { kind: 'validation' as const, source: 'client' as const, errors: clientErrors } : apiError;
  const reportsFromBranch = values.origin === 'branch';

  function set<K extends keyof IncidentFormValues>(key: K, value: IncidentFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validation = validateIncidentForm(values);
    setClientErrors(validation);
    setAttempt((current) => current + 1);
    if (validation.length === 0) onSubmit(values);
  }

  function errorFor(field: IncidentField): string | null {
    return fieldErrors.find((error) => error.field === field)?.message ?? null;
  }

  function describedBy(field: IncidentField, ...extra: string[]): string | undefined {
    const ids = [...extra, ...(errorFor(field) !== null ? [`incident-${field}-error`] : [])];
    return ids.length > 0 ? ids.join(' ') : undefined;
  }

  // Tras un intento fallido (cliente o API) el foco va al resumen de errores.
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasSummary = summaryError !== null;
  useEffect(() => {
    if (attempt > 0 && hasSummary) summaryRef.current?.focus();
  }, [attempt, hasSummary, apiError]);

  const titleLength = values.title.trim().length;

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4" aria-describedby="incident-form-help">
      <p id="incident-form-help" className="text-xs text-ink-muted">
        Los campos marcados con * son obligatorios.
      </p>

      {summaryError !== null && (
        <div ref={summaryRef} tabIndex={-1} className="outline-none">
          <IncidentError error={summaryError} id="incident-form-errors" hideFieldErrors />
        </div>
      )}

      <Field label="Título *" htmlFor="incident-title" error={errorFor('title')}>
        <input
          id="incident-title"
          value={values.title}
          onChange={(event) => set('title', event.target.value)}
          aria-invalid={errorFor('title') !== null}
          aria-describedby={describedBy('title', 'incident-title-count')}
          className={`${CONTROL_CLASSES} ${borderFor(errorFor('title'))}`}
        />
        <p
          id="incident-title-count"
          className={`text-xs ${titleLength > TITLE_MAX_LENGTH ? 'font-medium text-danger-ink' : 'text-ink-muted'}`}
        >
          {titleLength} / {TITLE_MAX_LENGTH} caracteres
        </p>
      </Field>

      <Field label="Descripción *" htmlFor="incident-description" error={errorFor('description')}>
        <textarea
          id="incident-description"
          rows={4}
          value={values.description}
          onChange={(event) => set('description', event.target.value)}
          aria-invalid={errorFor('description') !== null}
          aria-describedby={describedBy('description')}
          className={`${CONTROL_CLASSES} ${borderFor(errorFor('description'))}`}
        />
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Categoría *" htmlFor="incident-category" error={errorFor('category')}>
          <select
            id="incident-category"
            value={values.category}
            onChange={(event) => set('category', pick(INCIDENT_CATEGORIES, event.target.value))}
            aria-invalid={errorFor('category') !== null}
            aria-describedby={describedBy('category')}
            className={`${CONTROL_CLASSES} ${borderFor(errorFor('category'))}`}
          >
            <option value="">Selecciona…</option>
            {INCIDENT_CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Origen *" htmlFor="incident-origin" error={errorFor('origin')}>
          <select
            id="incident-origin"
            value={values.origin}
            onChange={(event) => set('origin', pick(INCIDENT_ORIGINS, event.target.value))}
            aria-invalid={errorFor('origin') !== null}
            aria-describedby={describedBy('origin')}
            className={`${CONTROL_CLASSES} ${borderFor(errorFor('origin'))}`}
          >
            <option value="">Selecciona…</option>
            {INCIDENT_ORIGINS.map((origin) => (
              <option key={origin} value={origin}>
                {origin}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {/* La sede es siempre visible y obligatoria. Con origin = branch se resalta
          (borde, fondo y un texto de ayuda: no solo color). */}
      <div
        data-highlighted={reportsFromBranch || undefined}
        className={`rounded-control ${reportsFromBranch ? 'border border-l-4 border-info-ink/40 border-l-info-ink bg-info-surface p-3' : ''}`}
      >
        <Field label="Sede *" htmlFor="incident-branch" error={errorFor('branch')}>
          <select
            id="incident-branch"
            value={values.branch}
            onChange={(event) => set('branch', pick(INCIDENT_BRANCHES, event.target.value))}
            aria-invalid={errorFor('branch') !== null}
            aria-describedby={describedBy('branch', 'incident-branch-help')}
            className={`${CONTROL_CLASSES} ${borderFor(errorFor('branch'))} ${reportsFromBranch ? 'border-2' : ''}`}
          >
            <option value="">Selecciona…</option>
            {INCIDENT_BRANCHES.map((branch) => (
              <option key={branch} value={branch}>
                {BRANCH_LABELS[branch]}
              </option>
            ))}
          </select>
          <p id="incident-branch-help" className={`text-xs ${reportsFromBranch ? 'font-medium text-info-ink' : 'text-ink-muted'}`}>
            {reportsFromBranch
              ? 'Estás reportando desde una sede de Nexova: indica en qué oficina se produce la incidencia.'
              : 'Usa «Central — Sede Valencia» cuando la incidencia no corresponda a una oficina concreta.'}
          </p>
        </Field>
      </div>

      <Field label="Estado" htmlFor="incident-status" error={errorFor('status')}>
        <input
          id="incident-status"
          value={INITIAL_INCIDENT_STATUS}
          readOnly
          aria-describedby={describedBy('status', 'incident-status-help')}
          className={`${CONTROL_CLASSES} border-border bg-canvas font-mono text-ink-muted`}
        />
        <p id="incident-status-help" className="text-xs text-ink-muted">
          Toda incidencia nueva se registra como «{INITIAL_INCIDENT_STATUS}»; el estado se cambia después desde el listado.
        </p>
      </Field>

      <div>
        <Button type="submit" isLoading={isSubmitting}>
          {isSubmitting ? 'Registrando…' : 'Registrar incidencia'}
        </Button>
      </div>
    </form>
  );
}

interface FieldProps {
  label: string;
  htmlFor: string;
  error: string | null;
  children: ReactNode;
}

function Field({ label, htmlFor, error, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {error !== null && (
        <p id={`${htmlFor}-error`} className="text-xs font-medium text-danger-ink">
          {error}
        </p>
      )}
    </div>
  );
}
