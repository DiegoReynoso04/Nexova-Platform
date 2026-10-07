'use client';

// Vista de /incident-manager: panel de resumen arriba y listado debajo.
// No hace HTTP: todo pasa por useIncidentSummary / useIncidentBoard →
// services/incident-manager.service.ts. Cada parte tiene su propia carga y su
// propio error: si el resumen falla, el listado sigue funcionando (y al revés).
// Tras un cambio de estado correcto, el listado pide recargar el resumen.

import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { hasActiveFilters, useIncidentBoard } from '@/hooks/use-incident-board';
import { useIncidentSummary } from '@/hooks/use-incident-summary';
import { NEW_INCIDENT_PATH } from '@/lib/incident-manager-routes';

import { IncidentError } from './incident-error';
import { IncidentFilterBar } from './incident-filters';
import { IncidentSummaryPanel } from './incident-summary-panel';
import { IncidentTable } from './incident-table';

export function IncidentBoardView() {
  const summary = useIncidentSummary();
  // `summary.reload` es estable (useCallback sobre la sesión).
  const board = useIncidentBoard(summary.reload);
  const { view, incidents, filters, rows, list, loaded } = board;
  const isLoading = list.status === 'loading';

  let liveMessage = '';
  if (view === 'loading') liveMessage = 'Cargando incidencias…';
  else if (view === 'empty') liveMessage = 'No hay incidencias que mostrar.';
  else if (view === 'data' && !isLoading) liveMessage = `Incidencias en el listado: ${incidents.length}.`;

  return (
    <>
      <p role="status" className="sr-only">
        {liveMessage}
      </p>

      <IncidentSummaryPanel summary={summary.summary} load={summary.load} onRetry={summary.reload} />

      <section aria-labelledby="incident-list-heading" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h2 id="incident-list-heading" className="text-base font-semibold text-ink">
              Incidencias
            </h2>
            {loaded && (
              <p className="text-sm text-ink-muted">
                {incidents.length === 1 ? '1 incidencia' : `${incidents.length} incidencias`}
                {hasActiveFilters(filters) ? ' con los filtros aplicados' : ''}
              </p>
            )}
          </div>
          <IncidentFilterBar filters={filters} onChange={board.setFilters} />
        </div>

        {view === 'error' && list.status === 'error' && (
          <div className="flex flex-col gap-2">
            <IncidentError error={list.error} />
            <div>
              <Button variant="secondary" onClick={board.reload}>
                Reintentar
              </Button>
            </div>
          </div>
        )}

        {view === 'loading' && (
          <div className="flex items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-6">
            <LoadingSpinner />
            <span className="text-sm text-ink-muted">Cargando incidencias…</span>
          </div>
        )}

        {view === 'empty' && (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-ink-muted">
            {hasActiveFilters(filters) ? (
              <p>Ninguna incidencia coincide con los filtros. Prueba a quitar alguno.</p>
            ) : (
              <>
                <p>Todavía no hay incidencias registradas.</p>
                <Link href={NEW_INCIDENT_PATH} className="font-medium text-brand underline underline-offset-2">
                  Registrar la primera incidencia
                </Link>
              </>
            )}
          </div>
        )}

        {view === 'data' && (
          <div className={isLoading ? 'opacity-60' : ''} aria-busy={isLoading}>
            <IncidentTable
              incidents={incidents}
              rows={rows}
              onChangeStatus={board.changeStatus}
              onDismissRowError={board.clearRow}
            />
          </div>
        )}
      </section>
    </>
  );
}
