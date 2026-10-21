'use client';

// Vista de /inventory/products: activos con su stock actual y su nivel.
// No hace HTTP: todo pasa por useInventoryAssets → services/inventory.service.ts.

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useInventoryAssets } from '@/hooks/use-inventory-assets';
import { LOW_STOCK_MAX } from '@/lib/stock-level';

import { AssetTable } from './asset-table';
import { InventoryError } from './inventory-error';

export interface AssetListViewProps {
  /** Id del `h1` de la página, que da nombre a la sección (la vista no repite el título). */
  labelledBy: string;
}

export function AssetListView({ labelledBy }: AssetListViewProps) {
  const { view, assets, load, loaded, reload } = useInventoryAssets();
  const isLoading = load.status === 'loading';

  let liveMessage = '';
  if (view === 'loading') liveMessage = 'Cargando activos…';
  else if (view === 'empty') liveMessage = 'No hay activos registrados.';
  else if (view === 'data' && !isLoading) liveMessage = `Activos en el listado: ${assets.length}.`;

  return (
    <section aria-labelledby={labelledBy} className="flex flex-col gap-4">
      <p role="status" className="sr-only">
        {liveMessage}
      </p>

      <div className="flex flex-wrap items-end justify-between gap-4">
        {loaded ? (
          <p className="text-sm font-medium text-ink">{assets.length === 1 ? '1 activo' : `${assets.length} activos`}</p>
        ) : (
          <span />
        )}
        <p className="text-xs text-ink-muted">
          Nivel de stock: Agotado (0) · Bajo (de 1 a {LOW_STOCK_MAX}) · Suficiente (más de {LOW_STOCK_MAX}).
        </p>
      </div>

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
          <span className="text-sm text-ink-muted">Cargando activos…</span>
        </div>
      )}

      {view === 'empty' && (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm text-ink-muted">
          <p>Todavía no hay activos registrados.</p>
          <p>Cuando se den de alta en el inventario, aparecerán aquí con su stock.</p>
        </div>
      )}

      {view === 'data' && <AssetTable assets={assets} />}
    </section>
  );
}
