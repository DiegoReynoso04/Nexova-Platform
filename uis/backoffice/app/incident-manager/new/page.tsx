import type { Metadata } from 'next';

import { IncidentFormView } from '@/components/incident-manager/incident-form-view';

// Server Component: exporta la metadata y renderiza el formulario (Client Component).
export const metadata: Metadata = {
  title: 'Registrar incidencia · Nexova',
  description: 'Alta de una incidencia en el gestor centralizado de incidencias de Nexova.',
};

export default function NewIncidentPage() {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold text-ink">Registrar incidencia</h1>
        <p className="text-sm text-ink-muted">
          Registra un fallo técnico, un error de proceso, una queja de cliente u otra incidencia. Se guarda con estado
          «open» y después se gestiona desde el panel de incidencias.
        </p>
      </div>
      <IncidentFormView />
    </>
  );
}
