import type { Metadata } from 'next';

import { OutboundFormView } from '@/components/inventory/outbound-form-view';
import { parseAssetIdParam } from '@/lib/asset-preselection';
import { ASSET_ID_PARAM } from '@/lib/inventory-routes';

// Server Component: exporta la metadata y lee `?asset_id=` (en Next 16,
// `searchParams` es una promesa: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/page.md).
// Leerlo hace la página dinámica. El valor ya interpretado se pasa a la vista.
export const metadata: Metadata = {
  title: 'Salida de activos · Inventario · Nexova',
  description: 'Registro de una asignación a un empleado o de un consumo (salida de activos) en el inventario de Nexova.',
};

const HEADING_ID = 'outbound-heading';

export default async function InventoryOutboundPage({ searchParams }: PageProps<'/inventory/orders/outbound'>) {
  const params = await searchParams;
  const assetIdParam = parseAssetIdParam(params[ASSET_ID_PARAM]);

  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 id={HEADING_ID} className="text-lg font-semibold text-ink">
          Salida de activos
        </h1>
        <p className="text-sm text-ink-muted">
          Registra una asignación a un empleado o un consumo. El stock del activo disminuye en la cantidad indicada; la
          oficina es la del activo.
        </p>
      </div>
      <OutboundFormView assetIdParam={assetIdParam} labelledBy={HEADING_ID} />
    </>
  );
}
