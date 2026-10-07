import type { ChangeEvent } from 'react';

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import type { BoardRowState } from '@/hooks/use-incident-board';
import { BRANCH_LABELS, INCIDENT_TRANSITIONS, type Incident, type IncidentStatus } from '@/types/incident-manager';

import { IncidentError } from './incident-error';

export interface IncidentTableProps {
  incidents: readonly Incident[];
  rows: Readonly<Record<string, BoardRowState>>;
  onChangeStatus: (incident: Incident, target: IncidentStatus) => void;
  onDismissRowError: (id: string) => void;
}

const DATE_TIME = new Intl.DateTimeFormat('es-ES', { dateStyle: 'medium', timeStyle: 'short' });

/** `created_at` (ISO 8601 UTC) en la hora local del navegador. */
function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_TIME.format(date);
}

// Listado de incidencias. El estado se cambia desde cada fila, solo con las
// transiciones del ciclo de vida; los estados finales no ofrecen selector.
export function IncidentTable({ incidents, rows, onChangeStatus, onDismissRowError }: IncidentTableProps) {
  return (
    // `relative`: los elementos `sr-only` de las filas (position: absolute) toman
    // este contenedor como bloque contenedor y quedan recortados por su
    // overflow. Sin él, ensanchaban el documento en móvil (scroll horizontal
    // de toda la página a 375 px).
    <div className="relative overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full min-w-[48rem] border-collapse text-left text-sm">
        <caption className="sr-only">Incidencias registradas</caption>
        <thead className="border-b border-border bg-canvas text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th scope="col" className="px-3 py-2 font-semibold">Incidencia</th>
            <th scope="col" className="px-3 py-2 font-semibold">Categoría</th>
            <th scope="col" className="px-3 py-2 font-semibold">Origen</th>
            <th scope="col" className="px-3 py-2 font-semibold">Sede</th>
            <th scope="col" className="px-3 py-2 font-semibold">Registrada</th>
            <th scope="col" className="px-3 py-2 font-semibold">Estado</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <IncidentRow
              key={incident.id}
              incident={incident}
              row={rows[incident.id]}
              onChangeStatus={onChangeStatus}
              onDismissRowError={onDismissRowError}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface IncidentRowProps {
  incident: Incident;
  row: BoardRowState | undefined;
  onChangeStatus: (incident: Incident, target: IncidentStatus) => void;
  onDismissRowError: (id: string) => void;
}

function IncidentRow({ incident, row, onChangeStatus, onDismissRowError }: IncidentRowProps) {
  const isSaving = row?.status === 'saving';
  const targets = INCIDENT_TRANSITIONS[incident.status];
  const selectId = `incident-status-${incident.id}`;

  function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    const target = targets.find((status) => status === event.target.value);
    if (target !== undefined) onChangeStatus(incident, target);
  }

  return (
    <>
      <tr className="border-b border-border align-top last:border-b-0">
        <th scope="row" className="px-3 py-3 font-normal">
          <span className="block font-semibold text-ink">{incident.title}</span>
          <span className="mt-1 line-clamp-2 block max-w-[24rem] text-xs text-ink-muted">{incident.description}</span>
        </th>
        <td className="px-3 py-3 font-mono text-xs">{incident.category}</td>
        <td className="px-3 py-3 font-mono text-xs">{incident.origin}</td>
        <td className="px-3 py-3">{BRANCH_LABELS[incident.branch]}</td>
        <td className="px-3 py-3 text-xs text-ink-muted">
          <time dateTime={incident.created_at}>{formatDateTime(incident.created_at)}</time>
        </td>
        <td className="px-3 py-3">
          <div className="flex flex-col items-start gap-2">
            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-canvas px-2 py-0.5 font-mono text-xs text-ink">
              {incident.status}
              {isSaving && <LoadingSpinner size="sm" label={`Guardando el estado de ${incident.title}`} />}
            </span>
            {targets.length === 0 ? (
              <span className="text-xs text-ink-muted">Estado final</span>
            ) : (
              <>
                <label htmlFor={selectId} className="sr-only">
                  Cambiar el estado de {incident.title}
                </label>
                <select
                  id={selectId}
                  value=""
                  disabled={isSaving}
                  onChange={handleChange}
                  className="rounded-control border border-border bg-surface px-2 py-1 text-xs text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-60"
                >
                  <option value="">Cambiar a…</option>
                  {targets.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
        </td>
      </tr>
      {row?.status === 'error' && (
        <tr className="border-b border-border">
          <td colSpan={6} className="px-3 pb-3">
            <div className="flex flex-col gap-2 pt-2">
              <p className="text-sm text-ink">
                No se pudo cambiar el estado de «{incident.title}» a «{row.attempted}»: se mantiene «{incident.status}».
              </p>
              <IncidentError error={row.error} />
              <div>
                <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => onDismissRowError(incident.id)}>
                  Cerrar aviso
                </Button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
