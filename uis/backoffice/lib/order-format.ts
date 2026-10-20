// Presentación de las órdenes del Historial (/inventory/orders). Módulo puro:
// lo usan la tabla y los tests.
//
// - Tipo: «Entrada» o «Salida», cada uno con su icono (además del color de la
//   insignia, que pone el componente): se distinguen sin depender del color.
// - Fecha: la API la da en ISO 8601 (UTC); se muestra en la zona horaria del
//   navegador con `Intl.DateTimeFormat('es-ES')`. El ISO completo va en el
//   `dateTime` del <time>.
// - Detalle: en una entrada, el proveedor; en una salida, «Asignación → a quién»
//   o «Consumo» (vocabulario del CONTEXT).

import type { InventoryOrder, OrderType } from '@/types/inventory';

export interface OrderTypeBadge {
  label: string;
  /** Decorativo (`aria-hidden`): el texto ya dice el tipo. */
  icon: string;
}

export const ORDER_TYPE_BADGES: Readonly<Record<OrderType, OrderTypeBadge>> = {
  inbound: { label: 'Entrada', icon: '↓' },
  outbound: { label: 'Salida', icon: '↑' },
};

/**
 * Fecha local legible, p. ej. «20 oct 2026, 12:55». `timeZone` solo para los
 * tests; en la UI se usa la del navegador. Una fecha que no se puede
 * interpretar se muestra tal cual (no debería llegar: la API da ISO 8601).
 */
export function formatOrderDate(iso: string, timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('es-ES', { dateStyle: 'medium', timeStyle: 'short', timeZone }).format(date);
}

/** Texto de la columna Detalle. */
export function orderDetail(order: InventoryOrder): string {
  if (order.type === 'inbound') return `Proveedor: ${order.supplier}`;
  if (order.exit_type === 'allocation') return `Asignación → ${order.assigned_to ?? ''}`.trimEnd();
  return 'Consumo';
}
