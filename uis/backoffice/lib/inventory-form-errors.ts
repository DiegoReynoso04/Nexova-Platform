// Reparto de un error de envío entre los campos del formulario y el aviso
// general (formularios de entrada y salida del inventario). Módulo puro.
//
// - Errores de validación (cliente o 422): cada uno junto a su campo, con el
//   texto propio y, si lo hay, el `msg` de la API debajo (`apiMessage`). Los que
//   no corresponden a un campo del formulario van en el aviso general.
// - `api_error` con campo (`insufficient_stock` → `quantity`): junto al campo,
//   con el `detail` de la API como texto; sin aviso general.
// - Cualquier otro error: solo el aviso general (InventoryError).

import type { InventoryField, InventoryUiError } from '@/types/inventory';

export interface FieldMessage {
  message: string;
  /** El `msg` de la API, para mostrarlo debajo como texto secundario. */
  apiMessage?: string;
}

/** Mensajes que se muestran junto a `field`. */
export function fieldMessages(error: InventoryUiError | null, field: InventoryField): FieldMessage[] {
  if (error === null) return [];
  if (error.kind === 'validation') {
    return error.errors
      .filter((item) => item.field === field)
      .map((item) => (item.apiMessage === undefined ? { message: item.message } : { message: item.message, apiMessage: item.apiMessage }));
  }
  if (error.kind === 'api_error' && error.field === field) return [{ message: error.detail }];
  return [];
}

/**
 * El error que se muestra en el aviso general, o `null` si todo se muestra
 * junto a los campos (`api_error` con un campo del formulario).
 */
export function summaryError(error: InventoryUiError | null, formFields: readonly InventoryField[]): InventoryUiError | null {
  if (error === null) return null;
  if (error.kind === 'api_error' && error.field !== null && formFields.includes(error.field)) return null;
  return error;
}

/** Errores de validación sin un campo del formulario: se listan en el aviso general. */
export function unplacedMessages(error: InventoryUiError | null, formFields: readonly InventoryField[]): FieldMessage[] {
  if (error === null || error.kind !== 'validation') return [];
  return error.errors
    .filter((item) => item.field === null || !formFields.includes(item.field))
    .map((item) => (item.apiMessage === undefined ? { message: item.message } : { message: item.message, apiMessage: item.apiMessage }));
}
