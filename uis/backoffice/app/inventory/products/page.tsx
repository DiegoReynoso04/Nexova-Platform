import type { Metadata } from 'next';

import { AssetListView } from '@/components/inventory/asset-list-view';

// Server Component: exporta la metadata (solo se permite en el servidor) y
// renderiza la vista interactiva, que es un Client Component ('use client').
export const metadata: Metadata = {
  title: 'Activos · Inventario · Nexova',
  description: 'Activos del inventario de Nexova con su stock actual y su nivel, para registrar entradas y salidas.',
};

const HEADING_ID = 'asset-list-heading';

export default function InventoryProductsPage() {
  return (
    <>
      <div className="flex flex-col gap-2">
        {/* Único título de la página: la sección del listado lo usa como etiqueta (aria-labelledby). */}
        <h1 id={HEADING_ID} className="text-lg font-semibold text-ink">
          Activos
        </h1>
        <p className="text-sm text-ink-muted">
          Equipos y materiales de las oficinas de Valencia y Miami con su stock actual (entradas menos salidas). Desde cada
          fila puedes registrar una entrada o una salida de ese activo.
        </p>
      </div>
      <AssetListView labelledBy={HEADING_ID} />
    </>
  );
}
