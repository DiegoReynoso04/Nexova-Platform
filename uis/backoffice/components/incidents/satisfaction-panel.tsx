import { TableScroll } from '@/components/ui/table-scroll';
import type { SatisfactionResult } from '@/types/incidents';

export interface SatisfactionPanelProps {
  satisfaction: SatisfactionResult;
}

// Índice de satisfacción de los tickets CLOSED. La media se muestra tal cual
// llega (string ya redondeado por la API). Las barras son solo visuales,
// escaladas al mayor conteo de la distribución; el número siempre se muestra.
export function SatisfactionPanel({ satisfaction }: SatisfactionPanelProps) {
  const { distribution } = satisfaction;
  const maxCount = distribution.reduce((max, item) => Math.max(max, item.count), 0);

  const stats = [
    { label: 'Tickets cerrados', value: String(satisfaction.closed_tickets) },
    { label: 'Tickets cerrados con puntuación', value: String(satisfaction.scored_tickets) },
    { label: 'Puntuación media', value: satisfaction.average_score ?? '—' },
  ];

  return (
    <section aria-labelledby="satisfaction-heading" className="rounded-lg border border-border bg-surface p-4 sm:p-6">
      <h3 id="satisfaction-heading" className="text-sm font-semibold text-ink">
        Satisfacción
      </h3>
      <p className="mt-1 text-xs text-ink-muted">Solo tickets en estado CLOSED.</p>

      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {stats.map((stat) => (
          <div key={stat.label}>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">{stat.label}</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums text-ink">{stat.value}</dd>
          </div>
        ))}
      </dl>

      <TableScroll className="mt-6">
        <table className="w-full text-sm">
          <caption className="sr-only">Distribución de puntuaciones de satisfacción</caption>
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
              <th scope="col" className="py-2 pr-4 font-medium">
                Puntuación
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Tickets
              </th>
              <th scope="col" className="w-2/5 py-2 font-medium">
                <span className="sr-only">Distribución</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {distribution.map((item) => {
              const width = maxCount === 0 ? 0 : (item.count / maxCount) * 100;
              return (
                <tr key={item.score} className="border-b border-border last:border-b-0">
                  <th scope="row" className="py-2 pr-4 text-left font-normal text-ink">
                    <span className="tabular-nums font-medium">{item.score}</span>{' '}
                    <span className="text-ink-muted">({item.label})</span>
                  </th>
                  <td className="py-2 pr-4 text-right tabular-nums text-ink">{item.count}</td>
                  <td className="py-2">
                    <div aria-hidden="true" className="h-2 w-full overflow-hidden rounded-full border border-border bg-canvas">
                      <div className="h-full rounded-full bg-brand" style={{ width: `${width}%` }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableScroll>
    </section>
  );
}
