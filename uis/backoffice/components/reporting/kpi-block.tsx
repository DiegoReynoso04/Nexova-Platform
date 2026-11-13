import { OfficeComparison } from '@/components/reporting/office-comparison';
import { kpiByOffice, weekPeriodLabel, type KpiDefinition } from '@/lib/reporting-format';
import type { WeeklyPerformance } from '@/types/reporting';

// Un bloque por KPI del BRIEFING (§2): su nombre, lo que mide, el período y Valencia frente a Miami.
export function KpiBlock({ kpi, report }: { kpi: KpiDefinition; report: WeeklyPerformance }) {
  return (
    <section className="flex flex-col gap-2">
      <div>
        <h2 className="text-base font-semibold text-ink">{kpi.title}</h2>
        <p className="text-sm text-ink-muted">{kpi.question}</p>
        <p className="text-xs text-ink-muted">{weekPeriodLabel(report.week_start)}</p>
      </div>
      <OfficeComparison kpi={kpi} offices={kpiByOffice(report.entries, kpi.key)} />
      {kpi.note !== undefined && <p className="text-xs text-ink-muted">{kpi.note}</p>}
    </section>
  );
}
