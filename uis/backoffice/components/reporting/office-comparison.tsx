import {
  barPercent,
  commonScale,
  formatCount,
  formatMoney,
  type KpiDefinition,
  type OfficeKpi,
} from '@/lib/reporting-format';

function formatValue(kpi: KpiDefinition, office: OfficeKpi, value: number): string {
  return kpi.kind === 'money' ? formatMoney(value, office.currency) : formatCount(value);
}

function OfficeColumn({ kpi, office, scale }: { kpi: KpiDefinition; office: OfficeKpi; scale: number }) {
  return (
    <section aria-label={`${kpi.title}: ${office.officeLabel}`} className="rounded-lg border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">
        {office.officeLabel} <span className="font-normal text-ink-muted">({office.currency})</span>
      </h3>
      {!office.hasActivity ? (
        <p className="mt-2 text-sm text-ink-muted">Sin actividad esta semana</p>
      ) : (
        <>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-ink">{formatValue(kpi, office, office.total)}</p>
          {/* Barra solo en los conteos, con la escala común de las dos oficinas. El costo va en monedas
              distintas: una barra común sugeriría una comparación que no existe. Decorativa: el número ya está. */}
          {kpi.kind === 'count' && (
            <div aria-hidden="true" className="mt-2 h-2 rounded bg-canvas">
              <div className="h-2 rounded bg-brand" style={{ width: `${barPercent(office.total, scale)}%` }} />
            </div>
          )}
          {office.programmes.length > 1 ? (
            <ul className="mt-3 flex flex-col gap-1 border-t border-border pt-2 text-sm">
              {office.programmes.map((programme) => (
                <li key={programme.programmeId} className="flex justify-between gap-3">
                  <span className="text-ink">{programme.label}</span>
                  <span className="tabular-nums text-ink">{formatValue(kpi, office, programme.value)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-ink-muted">{office.programmes[0]?.label}</p>
          )}
        </>
      )}
    </section>
  );
}

// Valencia y Miami lado a lado (apiladas en pantallas estrechas). Nunca hay un total entre oficinas.
export function OfficeComparison({ kpi, offices }: { kpi: KpiDefinition; offices: readonly OfficeKpi[] }) {
  const scale = commonScale(offices);
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {offices.map((office) => (
        <OfficeColumn key={office.office} kpi={kpi} office={office} scale={scale} />
      ))}
    </div>
  );
}
