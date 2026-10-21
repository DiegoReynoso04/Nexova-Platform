'use client';

// Vista de /inventory/orders (Historial): entradas y salidas, de solo lectura.
// No hace HTTP: todo pasa por useInventoryOrders → services/inventory.service.ts.

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useInventoryOrders } from '@/hooks/use-inventory-orders';

import { InventoryError } from './inventory-error';
import { OrderTable } from './order-table';

export interface OrderHistoryViewProps {
  /** Id del `h1` de la página, que da nombre a la sección (la vista no repite el título). */
  labelledBy: string;
}

export function OrderHistoryView({ labelledBy }: OrderHistoryViewProps) {
  const { view, orders, load, reload } = useInventoryOrders();
  const isLoading = load.status === 'loading';

  let liveMessage = '';
  if (view === 'loading') liveMessage = 'Cargando el historial…';
  else if (view === 'empty') liveMessage = 'Todavía no hay entradas ni salidas.';
  else if (view === 'data' && !isLoading) liveMessage = `Órdenes en el historial: ${orders.length}.`;

  return (
    <section aria-labelledby={labelledBy} className="flex flex-col gap-4">
      <p role="status" className="sr-only">
        {liveMessage}
      </p>

      {view === 'data' && (
        <p className="text-sm font-medium text-ink">{orders.length === 1 ? '1 orden' : `${orders.length} órdenes`}</p>
      )}

      {view === 'error' && load.status === 'error' && (
        <div className="flex flex-col gap-2">
          <InventoryError error={load.error} />
          <div>
            <Button variant="secondary" onClick={reload}>
              Reintentar
            </Button>
          </div>
        </div>
      )}

      {view === 'loading' && (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-6">
          <LoadingSpinner />
          <span className="text-sm text-ink-muted">Cargando el historial…</span>
        </div>
      )}

      {view === 'empty' && (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-ink-muted">
          <p>Todavía no hay entradas ni salidas.</p>
          <p>Cuando se registren, aparecerán aquí, de la más reciente a la más antigua.</p>
        </div>
      )}

      {view === 'data' && <OrderTable orders={orders} />}
    </section>
  );
}
