import type { Metadata } from 'next';

import { TelemetryReportView } from '@/components/telemetry/telemetry-report-view';

// Server Component: exporta la metadata y renderiza la vista interactiva.
export const metadata: Metadata = {
  title: 'Telemetría · Nexova',
  description: 'Reporte técnico de la telemetría del backoffice: volumen, errores, espera por página y logins fallidos.',
};

export default function TelemetryPage() {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold text-ink">Telemetría</h1>
        <p className="text-sm text-ink-muted">Reporte técnico de los últimos 7 días. Se actualiza como mucho una vez por minuto.</p>
      </div>
      <TelemetryReportView />
    </>
  );
}
