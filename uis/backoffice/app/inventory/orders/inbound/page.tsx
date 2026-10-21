import type { Metadata } from 'next';

import { InboundFormView } from '@/components/inventory/inbound-form-view';
import { parseAssetIdParam } from '@/lib/asset-preselection';
import { ASSET_ID_PARAM } from '@/lib/inventory-routes';

// Server Component: exporta la metadata y lee `?asset_id=` (en Next 16,
// `searchParams` es una promesa: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/page.md).
// Leerlo hace la página dinámica. El valor ya interpretado se pasa a la vista.
export const metadata: Metadata = {
  title: 'Entrada de activos · Inventario · Nexova',
  description: 'Registro de una entrega recibida (entrada de activos) en el inventario de Nexova.',
};

const HEADING_ID = 'inbound-heading';

export default async function InventoryInboundPage({ searchParams }: PageProps<'/inventory/orders/inbound'>) {
  const params = await searchParams;
  const assetIdParam = parseAssetIdParam(params[ASSET_ID_PARAM]);

  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 id={HEADING_ID} className="text-lg font-semibold text-ink">
          Entrada de activos
        </h1>
        <p className="text-sm text-ink-muted">
          Registra una compra o entrega recibida. El stock del activo aumenta en la cantidad indicada; la oficina es la del
          activo.
        </p>
      </div>
      <InboundFormView assetIdParam={assetIdParam} labelledBy={HEADING_ID} />
    </>
  );
}
