import type { ChangeEvent } from 'react';

import { Button } from '@/components/ui/button';
import { hasActiveFilters } from '@/hooks/use-incident-board';
import {
  BRANCH_LABELS,
  INCIDENT_BRANCHES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  type IncidentFilters,
} from '@/types/incident-manager';

export interface IncidentFilterBarProps {
  filters: IncidentFilters;
  onChange: (filters: IncidentFilters) => void;
}

const SELECT_CLASSES =
  'rounded-control border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand';

function toValue<T extends string>(values: readonly T[], value: string): T | null {
  return values.find((candidate) => candidate === value) ?? null;
}

// Cada cambio pide a la API el listado filtrado
// (GET /api/incidents?status=&origin=&branch=), sin recargar la página.
export function IncidentFilterBar({ filters, onChange }: IncidentFilterBarProps) {
  return (
    <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Filtros del listado de incidencias">
      <label className="flex flex-col gap-1 text-sm font-medium text-ink">
        Estado
        <select
          className={SELECT_CLASSES}
          value={filters.status ?? ''}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            onChange({ ...filters, status: toValue(INCIDENT_STATUSES, event.target.value) })
          }
        >
          <option value="">Todos los estados</option>
          {INCIDENT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium text-ink">
        Origen
        <select
          className={SELECT_CLASSES}
          value={filters.origin ?? ''}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            onChange({ ...filters, origin: toValue(INCIDENT_ORIGINS, event.target.value) })
          }
        >
          <option value="">Todos los orígenes</option>
          {INCIDENT_ORIGINS.map((origin) => (
            <option key={origin} value={origin}>
              {origin}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium text-ink">
        Sede
        <select
          className={SELECT_CLASSES}
          value={filters.branch ?? ''}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            onChange({ ...filters, branch: toValue(INCIDENT_BRANCHES, event.target.value) })
          }
        >
          <option value="">Todas las sedes</option>
          {INCIDENT_BRANCHES.map((branch) => (
            <option key={branch} value={branch}>
              {BRANCH_LABELS[branch]}
            </option>
          ))}
        </select>
      </label>
      {hasActiveFilters(filters) && (
        <Button variant="secondary" onClick={() => onChange({ status: null, origin: null, branch: null })}>
          Quitar filtros
        </Button>
      )}
    </div>
  );
}
