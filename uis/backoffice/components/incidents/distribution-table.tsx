import { TableScroll } from '@/components/ui/table-scroll';
import type { DistributionItem } from '@/types/incidents';

export interface DistributionTableProps {
  headingId: string;
  title: string;
  /** Cabecera de la primera columna ("Categoría", "Estado"). */
  codeLabel: string;
  items: readonly DistributionItem[];
  note: string;
}

// Categorías o estados con su porcentaje sobre registros válidos. El código y
// el porcentaje se muestran exactamente como llegan de la API (el porcentaje
// es un string ya redondeado por el backend; `null` = no calculable).
export function DistributionTable({ headingId, title, codeLabel, items, note }: DistributionTableProps) {
  return (
    <section aria-labelledby={headingId} className="rounded-lg border border-border bg-surface p-4 sm:p-6">
      <h3 id={headingId} className="text-sm font-semibold text-ink">
        {title}
      </h3>
      <p className="mt-1 text-xs text-ink-muted">{note}</p>
      <TableScroll className="mt-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
              <th scope="col" className="py-2 pr-4 font-medium">
                {codeLabel}
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-medium">
                Registros
              </th>
              <th scope="col" className="py-2 text-right font-medium">
                Porcentaje
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.code} className="border-b border-border last:border-b-0">
                <th scope="row" className="py-2 pr-4 text-left font-mono text-xs font-normal text-ink">
                  {item.code}
                </th>
                <td className="py-2 pr-4 text-right tabular-nums text-ink">{item.count}</td>
                <td className="py-2 text-right tabular-nums text-ink">
                  {item.percentage === null ? '—' : `${item.percentage} %`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
    </section>
  );
}
