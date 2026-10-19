// Rutas del inventario (Hito 5) en el backoffice. Las cuatro páginas son las
// que fija el brief (docs/context-nexova-gestion-inventario-hito-5.md para el
// vocabulario) y quedan protegidas por el guard global: no están en
// PUBLIC_PATHS ni en OPEN_PATHS de lib/auth-routes.ts.

export const INVENTORY_PATH = '/inventory';
export const INVENTORY_PRODUCTS_PATH = '/inventory/products';
export const INVENTORY_INBOUND_PATH = '/inventory/orders/inbound';
export const INVENTORY_OUTBOUND_PATH = '/inventory/orders/outbound';
export const INVENTORY_ORDERS_PATH = '/inventory/orders';

/** Las cuatro páginas del inventario. */
export const INVENTORY_PAGES: readonly string[] = [
  INVENTORY_PRODUCTS_PATH,
  INVENTORY_INBOUND_PATH,
  INVENTORY_OUTBOUND_PATH,
  INVENTORY_ORDERS_PATH,
];

/** Parámetro con el que la página de activos preselecciona el activo en los formularios. */
export const ASSET_ID_PARAM = 'asset_id';

/** Formulario de entrada con el activo preseleccionado. */
export function inboundOrderHref(assetId: number): string {
  return `${INVENTORY_INBOUND_PATH}?${ASSET_ID_PARAM}=${assetId}`;
}

/** Formulario de salida con el activo preseleccionado. */
export function outboundOrderHref(assetId: number): string {
  return `${INVENTORY_OUTBOUND_PATH}?${ASSET_ID_PARAM}=${assetId}`;
}
