import Link from 'next/link';

import { TableScroll } from '@/components/ui/table-scroll';
import { inboundOrderHref, outboundOrderHref } from '@/lib/inventory-routes';
import type { Asset } from '@/types/inventory';

import { StockLevelBadge } from './stock-level-badge';

// Tabla de activos (presentacional). Los valores de categoría y oficina se
// muestran tal como los devuelve la API (vocabulario del CONTEXT).

const ACTION_LINK_CLASSES =
  'rounded-control border border-border px-2 py-1 text-xs font-medium text-brand outline-none hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand';

export interface AssetTableProps {
  assets: readonly Asset[];
}

export function AssetTable({ assets }: AssetTableProps) {
  return (
    <TableScroll framed>
      <table className="w-full min-w-[44rem] border-collapse text-left text-sm">
        <caption className="sr-only">Activos del inventario con su stock actual</caption>
        <thead className="border-b border-border bg-canvas text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th scope="col" className="px-3 py-2 font-semibold">Nombre</th>
            <th scope="col" className="px-3 py-2 font-semibold">SKU</th>
            <th scope="col" className="px-3 py-2 font-semibold">Categoría</th>
            <th scope="col" className="px-3 py-2 font-semibold">Oficina</th>
            <th scope="col" className="px-3 py-2 font-semibold">Stock actual</th>
            <th scope="col" className="px-3 py-2 font-semibold">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id} className="border-b border-border last:border-b-0">
              <th scope="row" className="px-3 py-3 font-medium text-ink">
                {asset.name}
              </th>
              {/* El SKU nunca se parte (p. ej. «NXV-IT-» / «001»). */}
              <td className="whitespace-nowrap px-3 py-3 font-mono text-xs">{asset.sku}</td>
              <td className="px-3 py-3 font-mono text-xs">{asset.category}</td>
              <td className="px-3 py-3">{asset.office}</td>
              <td className="px-3 py-3">
                {/* Número e indicador siempre en la misma línea, en todas las filas. */}
                <div className="flex items-center gap-2 whitespace-nowrap">
                  <span className="font-semibold tabular-nums">{asset.current_stock}</span>
                  <StockLevelBadge currentStock={asset.current_stock} />
                </div>
              </td>
              <td className="px-3 py-3">
                <div className="flex flex-wrap gap-2">
                  <Link href={inboundOrderHref(asset.id)} className={ACTION_LINK_CLASSES}>
                    Registrar entrada<span className="sr-only"> de {asset.name} ({asset.sku})</span>
                  </Link>
                  <Link href={outboundOrderHref(asset.id)} className={ACTION_LINK_CLASSES}>
                    Registrar salida<span className="sr-only"> de {asset.name} ({asset.sku})</span>
                  </Link>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
}
