import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { summaryDisplay, type SummaryDisplayCount, type SummaryLoadState } from '@/hooks/use-incident-summary';
import { BRANCH_LABELS, type IncidentSummary } from '@/types/incident-manager';

import { IncidentError } from './incident-error';

export interface IncidentSummaryPanelProps {
  summary: IncidentSummary | null;
  load: SummaryLoadState;
  onRetry: () => void;
}

// Panel de resumen (GET /api/incidents/summary). Tiene su propia carga y su
// propio error: si falla, el resto de la página (el listado) sigue funcionando.
// Mientras carga por primera vez pinta la misma rejilla con el esqueleto
// (summaryDisplay), para que el panel no crezca al llegar los datos.
export function IncidentSummaryPanel({ summary, load, onRetry }: IncidentSummaryPanelProps) {
  const isLoading = load.status === 'loading' || load.status === 'idle';
  const isFirstLoad = summary === null && isLoading;
  const display = summaryDisplay(summary);

  return (
    <section aria-labelledby="incident-summary-heading" className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="incident-summary-heading" className="text-base font-semibold text-ink">
          Resumen
        </h2>
        {display.total !== null && <p className="text-sm text-ink-muted">Total de incidencias: {display.total}</p>}
        {/* En el sitio del total y con su misma altura de línea. */}
        {isFirstLoad && (
          <p role="status" className="flex items-center gap-2 text-sm text-ink-muted">
            <LoadingSpinner size="sm" />
            Cargando resumen…
          </p>
        )}
      </div>

      {load.status === 'error' && (
        <div className="flex flex-col gap-2">
          <IncidentError error={load.error} />
          <div>
            <Button variant="secondary" onClick={onRetry}>
              Reintentar resumen
            </Button>
          </div>
          {summary !== null && <p className="text-xs text-ink-muted">Se sigue mostrando el último resumen recibido.</p>}
        </div>
      )}

      {(summary !== null || isFirstLoad) && (
        <div
          className={`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 ${isLoading ? 'opacity-60' : ''}`}
          aria-busy={isLoading}
        >
          <CountList title="Por estado" items={display.by_status} />
          <CountList title="Por categoría" items={display.by_category} />
          <CountList title="Por origen" items={display.by_origin} />
          <CountList title="Por sede" items={display.by_branch} label={(value) => BRANCH_LABELS[value]} />
        </div>
      )}
    </section>
  );
}

interface CountListProps<T extends string> {
  title: string;
  items: readonly SummaryDisplayCount<T>[];
  /** Texto visible de cada valor; por defecto, el valor literal. */
  label?: (value: T) => string;
}

function CountList<T extends string>({ title, items, label }: CountListProps<T>) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{title}</h3>
      <dl className="flex flex-col gap-1 text-sm">
        {items.map((item) => (
          <div key={item.value} className="flex items-baseline justify-between gap-2">
            <dt className={label === undefined ? 'font-mono text-xs text-ink' : 'text-ink'}>
              {label === undefined ? item.value : label(item.value)}
            </dt>
            {item.count === null ? (
              // Esqueleto: el número aún no se conoce; el estado lo anuncia «Cargando resumen…».
              <dd aria-hidden="true" className="tabular-nums text-ink-muted">
                —
              </dd>
            ) : (
              <dd className={`tabular-nums ${item.count === 0 ? 'text-ink-muted' : 'font-semibold text-ink'}`}>{item.count}</dd>
            )}
          </div>
        ))}
      </dl>
    </div>
  );
}
