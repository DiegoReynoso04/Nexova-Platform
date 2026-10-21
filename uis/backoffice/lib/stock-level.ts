// Nivel de stock de un activo, para el indicador de /inventory/products. El
// brief pide código de color: «quiero ver de un vistazo qué está bajo».
//
// Umbrales propios (decisión D6 del plan del frontend, aprobada por el
// usuario; ni el CONTEXT ni la API los fijan). Se aplican igual a todas las
// categorías y oficinas, sobre el `current_stock` que calcula la API:
//
//   current_stock = 0        → «Agotado»    (rojo)
//   current_stock de 1 a 5   → «Bajo»       (ámbar)
//   current_stock de 6 o más → «Suficiente» (verde)
//
// Un valor negativo no debería llegar (la API rechaza las salidas que dejarían
// el stock en negativo); si llegase, se muestra como «Agotado».
//
// El color nunca va solo: el indicador lleva también un icono y el texto.

/** Último valor que cuenta como «Bajo». */
export const LOW_STOCK_MAX = 5;

export type StockLevel = 'out' | 'low' | 'ok';

export function stockLevel(currentStock: number): StockLevel {
  if (currentStock <= 0) return 'out';
  if (currentStock <= LOW_STOCK_MAX) return 'low';
  return 'ok';
}

export const STOCK_LEVEL_LABELS: Readonly<Record<StockLevel, string>> = {
  out: 'Agotado',
  low: 'Bajo',
  ok: 'Suficiente',
};
