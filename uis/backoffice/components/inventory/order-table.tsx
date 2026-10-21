import { formatOrderDate, orderDetail } from '@/lib/order-format';
import type { InventoryOrder } from '@/types/inventory';

import { OrderTypeBadge } from './order-type-badge';

// Tabla del Historial (presentacional y de solo lectura: sin acciones). Las
// filas van en el orden de la API, la más reciente primero. La oficina se
// muestra tal como la devuelve la API (vocabulario del CONTEXT).

export interface OrderTableProps {
  orders: readonly InventoryOrder[];
}

export function OrderTable({ orders }: OrderTableProps) {
  return (
    // `relative`: recorta los elementos sr-only absolutos de dentro (sin scroll horizontal en la página a 375 px).
    <div className="relative overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full min-w-[56rem] border-collapse text-left text-sm">
        <caption className="sr-only">Historial de entradas y salidas de activos, de la más reciente a la más antigua</caption>
        <thead className="border-b border-border bg-canvas text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th scope="col" className="px-3 py-2 font-semibold">Tipo</th>
            <th scope="col" className="px-3 py-2 font-semibold">Activo</th>
            <th scope="col" className="px-3 py-2 font-semibold">Cantidad</th>
            <th scope="col" className="px-3 py-2 font-semibold">Oficina</th>
            <th scope="col" className="px-3 py-2 font-semibold">Detalle</th>
            <th scope="col" className="px-3 py-2 font-semibold">Fecha</th>
            <th scope="col" className="px-3 py-2 font-semibold">Usuario</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            // Entradas y salidas tienen ids independientes: la clave lleva también el tipo.
            <tr key={`${order.type}-${order.id}`} className="border-b border-border align-top last:border-b-0">
              <td className="px-3 py-3">
                <OrderTypeBadge type={order.type} />
              </td>
              <th scope="row" className="px-3 py-3 font-medium text-ink">
                <span className="block">{order.asset.name}</span>
                <span className="block whitespace-nowrap font-mono text-xs font-normal text-ink-muted">{order.asset.sku}</span>
              </th>
              <td className="px-3 py-3 font-semibold tabular-nums">{order.quantity}</td>
              <td className="px-3 py-3">{order.office}</td>
              <td className="px-3 py-3">{orderDetail(order)}</td>
              <td className="whitespace-nowrap px-3 py-3">
                <time dateTime={order.created_at}>{formatOrderDate(order.created_at)}</time>
              </td>
              <td className="px-3 py-3 font-mono text-xs break-all">{order.user_uuid}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
