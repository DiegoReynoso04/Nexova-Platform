import { TableScroll } from '@/components/ui/table-scroll';
import type { RuleBreakdownItem } from '@/types/incidents';

export interface InvalidBreakdownTableProps {
  items: readonly RuleBreakdownItem[];
}

// Las 7 reglas siempre, en el orden de la API y con su etiqueta original
// (vocabulario del dominio, no se traduce). Los valores son activaciones de
// regla: una fila puede activar varias, así que no suman los inválidos.
export function InvalidBreakdownTable({ items }: InvalidBreakdownTableProps) {
  return (
    <section aria-labelledby="invalid-breakdown-heading" className="rounded-lg border border-border bg-surface p-4 sm:p-6">
      <h3 id="invalid-breakdown-heading" className="text-sm font-semibold text-ink">
        Reglas de invalidación
      </h3>
      <p className="mt-1 text-xs text-ink-muted">
        Una fila puede activar varias reglas, así que la suma de esta tabla puede ser mayor que el número de registros
        inválidos.
      </p>
      <TableScroll className="mt-4">
        <table className="w-full text-sm">
          <caption className="sr-only">Registros que activan cada regla de invalidación</caption>
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
              <th scope="col" className="py-2 pr-4 font-medium">
                Regla
              </th>
              <th scope="col" className="py-2 text-right font-medium">
                Registros
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.code} className="border-b border-border last:border-b-0">
                <th scope="row" className="py-2 pr-4 text-left font-normal text-ink">
                  {item.label}
                </th>
                <td className={`py-2 text-right tabular-nums ${item.count === 0 ? 'text-ink-muted' : 'font-medium text-ink'}`}>
                  {item.count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
    </section>
  );
}
