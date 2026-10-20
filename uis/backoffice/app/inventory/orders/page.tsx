import type { Metadata } from 'next';

import { OrderHistoryView } from '@/components/inventory/order-history-view';

// Server Component: exporta la metadata (solo se permite en el servidor) y
// renderiza la vista interactiva, que es un Client Component ('use client').
export const metadata: Metadata = {
  title: 'Historial · Inventario · Nexova',
  description: 'Historial de entradas y salidas de activos del inventario de Nexova, de solo lectura.',
};

const HEADING_ID = 'order-history-heading';

export default function InventoryOrdersPage() {
  return (
    <>
      <div className="flex flex-col gap-2">
        {/* Único título de la página: la sección del historial lo usa como etiqueta (aria-labelledby). */}
        <h1 id={HEADING_ID} className="text-lg font-semibold text-ink">
          Historial
        </h1>
        <p className="text-sm text-ink-muted">
          Todas las entradas y salidas de activos, de la más reciente a la más antigua, con quién las registró. Es de solo
          lectura: las órdenes no se editan ni se borran.
        </p>
      </div>
      <OrderHistoryView labelledBy={HEADING_ID} />
    </>
  );
}
