import type { Metadata } from 'next';

import { IncidentBoardView } from '@/components/incident-manager/incident-board-view';

// Server Component: exporta la metadata (solo se permite en el servidor) y
// renderiza la vista interactiva, que es un Client Component ('use client').
export const metadata: Metadata = {
  title: 'Incidencias · Nexova',
  description: 'Gestor centralizado de incidencias de Nexova: resumen, listado con filtros y cambio de estado.',
};

export default function IncidentManagerPage() {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold text-ink">Gestor de incidencias</h1>
        <p className="text-sm text-ink-muted">
          Registro centralizado de las incidencias técnicas y operativas de Nexova. Filtra por estado, origen o sede y
          avanza cada incidencia en su ciclo de vida: open → in_progress o discarded; in_progress → resolved o discarded.
        </p>
      </div>
      <IncidentBoardView />
    </>
  );
}
