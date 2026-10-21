import { redirect } from 'next/navigation';

import { INVENTORY_PRODUCTS_PATH } from '@/lib/inventory-routes';

// `/inventory` no tiene vista propia: lleva a Activos. `redirect` en un Server
// Component (Next 16, node_modules/next/dist/docs/01-app/03-api-reference/04-functions/redirect.md)
// corta el render y sustituye la entrada del historial (`replace`).
export default function InventoryIndexPage() {
  redirect(INVENTORY_PRODUCTS_PATH);
}
