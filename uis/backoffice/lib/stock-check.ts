// Advertencia de la Salida de activos: la cantidad escrita supera el stock que
// se muestra. Solo avisa y nunca bloquea el envío: la API es la autoridad (el
// stock puede haber cambiado desde que se leyó) y responde con el 400
// `insufficient_stock` si de verdad no alcanza. Módulo puro.

/**
 * `true` si `quantity` es un entero escrito en dígitos mayor que
 * `currentStock`. Sin stock conocido (`null`) o con una cantidad que no es un
 * entero, no hay advertencia: de eso se ocupa la validación del formulario.
 */
export function exceedsStock(quantity: string, currentStock: number | null): boolean {
  if (currentStock === null) return false;
  const normalized = quantity.trim();
  if (!/^\d+$/.test(normalized)) return false;
  const value = Number(normalized);
  return Number.isSafeInteger(value) && value > currentStock;
}
