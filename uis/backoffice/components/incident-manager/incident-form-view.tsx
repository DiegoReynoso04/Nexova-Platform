'use client';

// Vista de /incident-manager/new: conecta useIncidentForm con el formulario.
// No hace HTTP: todo pasa por el hook → services/incident-manager.service.ts.

import Link from 'next/link';

import { Alert } from '@/components/ui/alert';
import { useIncidentForm } from '@/hooks/use-incident-form';
import { INCIDENT_MANAGER_PATH } from '@/lib/incident-manager-routes';

import { IncidentForm } from './incident-form';

export function IncidentFormView() {
  const { submit, formKey, submitIncident } = useIncidentForm();

  return (
    <section aria-labelledby="incident-form-heading" className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6">
      <h2 id="incident-form-heading" className="text-base font-semibold text-ink">
        Nueva incidencia
      </h2>

      {submit.status === 'success' && (
        <Alert variant="info" title="Incidencia registrada">
          <p>
            «{submit.incident.title}» se ha registrado con estado «{submit.incident.status}». El formulario está listo para
            otra incidencia.
          </p>
          <p className="mt-1">
            <Link href={INCIDENT_MANAGER_PATH} className="font-medium text-brand underline underline-offset-2">
              Ver el panel de incidencias
            </Link>
          </p>
        </Alert>
      )}

      {/* key: tras un alta correcta el formulario se vuelve a montar vacío. */}
      <IncidentForm key={formKey} submit={submit} onSubmit={submitIncident} />
    </section>
  );
}
