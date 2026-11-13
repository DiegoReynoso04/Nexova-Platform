'use client';

// /reporting: el «Reporte Semanal de Desempeño por Oficina y Programa» (BRIEFING §1) de
// `GET /reporting/weekly-office-program-performance`, para Laura (CEO) y Elena (L&D): números, no
// eventos. Tablas y barras de CSS, sin librería de gráficos. EUR y USD nunca se suman.

import { DataFreshness } from '@/components/reporting/data-freshness';
import { KpiBlock } from '@/components/reporting/kpi-block';
import { WeekPicker } from '@/components/reporting/week-picker';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useWeeklyPerformance } from '@/hooks/use-weekly-performance';
import { CURRENCY_NOTE, KPIS, UNASSIGNED_NOTE, allUnassigned, reportingErrorCopy } from '@/lib/reporting-format';
import type { ReportingUiError } from '@/types/reporting';

function ReportError({ error, onRetry }: { error: ReportingUiError; onRetry: () => void }) {
  const { title, body } = reportingErrorCopy(error);
  return (
    <div className="flex flex-col gap-2">
      <Alert variant="error" title={title}>
        {body}
      </Alert>
      <div>
        <Button variant="secondary" onClick={onRetry}>
          Reintentar
        </Button>
      </div>
    </div>
  );
}

// La misma rejilla que los datos (4 bloques de dos columnas), con alto fijo: sin layout shift al llegar.
function ReportSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-4">
        <LoadingSpinner />
        <span role="status" className="text-sm text-ink-muted">
          Cargando el reporte…
        </span>
      </div>
      {KPIS.map((kpi) => (
        <div key={kpi.key} aria-hidden="true" className="h-44 rounded-lg border border-dashed border-border bg-surface" />
      ))}
    </div>
  );
}

export function WeeklyPerformanceView() {
  const { state, view, week, previous, next, goToWeek, reload } = useWeeklyPerformance();
  const report = state.report;

  return (
    <div className="flex flex-col gap-6">
      <DataFreshness />
      <WeekPicker week={week} previous={previous} next={next} onGoToWeek={goToWeek} />

      {view === 'loading' && <ReportSkeleton />}

      {view === 'not_computed' && (
        <Alert variant="info" title={week === null ? 'El reporte todavía no se ha calculado' : 'Esta semana todavía no se ha calculado'}>
          {week === null
            ? 'Cuando se calcule la primera semana, aparecerá aquí.'
            : 'Prueba con una semana anterior o con la siguiente.'}
        </Alert>
      )}

      {view === 'error' && state.load.status === 'error' && <ReportError error={state.load.error} onRetry={reload} />}

      {view === 'empty' && (
        <p className="rounded-lg border border-dashed border-border bg-surface p-4 text-sm text-ink-muted">
          No hubo actividad registrada en esta semana.
        </p>
      )}

      {view === 'data' && report !== null && (
        <>
          <div className="flex flex-col gap-2">
            <p className="text-xs text-ink-muted">{CURRENCY_NOTE}</p>
            {allUnassigned(report.entries) && <Alert variant="info" title={UNASSIGNED_NOTE} />}
          </div>
          {KPIS.map((kpi) => (
            <KpiBlock key={kpi.key} kpi={kpi} report={report} />
          ))}
        </>
      )}
    </div>
  );
}
