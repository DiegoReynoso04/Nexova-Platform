// lib/order-format.ts: presentación del Historial (/inventory/orders): la
// insignia por tipo, la fecha local legible y la columna Detalle.

import { ORDER_TYPE_BADGES, formatOrderDate, orderDetail } from '@/lib/order-format';
import type { InboundOrder, OutboundOrder } from '@/types/inventory';

const USER_UUID = '00000000-0000-4000-8000-000000000000';

function inbound(overrides: Partial<InboundOrder> = {}): InboundOrder {
  return {
    type: 'inbound',
    id: 1,
    asset: { id: 1, name: 'Synthetic laptop', sku: 'SYN-IT-001' },
    quantity: 10,
    supplier: 'Synthetic supplier',
    office: 'Valencia',
    created_at: '2026-10-18T20:55:11.366024Z',
    user_uuid: USER_UUID,
    ...overrides,
  };
}

function outbound(overrides: Partial<OutboundOrder> = {}): OutboundOrder {
  return {
    type: 'outbound',
    id: 1,
    asset: { id: 1, name: 'Synthetic laptop', sku: 'SYN-IT-001' },
    quantity: 2,
    exit_type: 'allocation',
    assigned_to: 'Synthetic employee',
    office: 'Valencia',
    created_at: '2026-10-18T20:55:11.548019Z',
    user_uuid: USER_UUID,
    ...overrides,
  };
}

describe('ORDER_TYPE_BADGES', () => {
  test('inbound is «Entrada» and outbound is «Salida»', () => {
    expect(ORDER_TYPE_BADGES.inbound.label).toBe('Entrada');
    expect(ORDER_TYPE_BADGES.outbound.label).toBe('Salida');
  });

  test('both types have a different label and icon (not only a colour)', () => {
    expect(ORDER_TYPE_BADGES.inbound.label).not.toBe(ORDER_TYPE_BADGES.outbound.label);
    expect(ORDER_TYPE_BADGES.inbound.icon).not.toBe(ORDER_TYPE_BADGES.outbound.icon);
    expect(ORDER_TYPE_BADGES.inbound.icon).not.toBe('');
    expect(ORDER_TYPE_BADGES.outbound.icon).not.toBe('');
  });
});

describe('formatOrderDate', () => {
  test('shows a readable date in Spanish in the given time zone, not the raw ISO', () => {
    const iso = '2026-10-18T20:55:11.366024Z';
    expect(formatOrderDate(iso, 'Europe/Madrid')).toBe('18 oct 2026, 22:55');
    expect(formatOrderDate(iso, 'America/New_York')).toBe('18 oct 2026, 16:55');
    expect(formatOrderDate(iso, 'UTC')).not.toContain('T');
  });

  test('crossing midnight changes the day in the local zone', () => {
    expect(formatOrderDate('2026-10-18T23:30:00Z', 'Europe/Madrid')).toBe('19 oct 2026, 1:30');
  });

  test('a date that cannot be parsed is shown as is', () => {
    expect(formatOrderDate('not a date', 'UTC')).toBe('not a date');
  });
});

describe('orderDetail', () => {
  test('an inbound order shows the supplier', () => {
    expect(orderDetail(inbound({ supplier: 'Office Depot Miami' }))).toBe('Proveedor: Office Depot Miami');
  });

  test('an allocation shows who received the asset', () => {
    expect(orderDetail(outbound({ assigned_to: 'Ana García' }))).toBe('Asignación → Ana García');
  });

  test('a consumption shows «Consumo»', () => {
    expect(orderDetail(outbound({ exit_type: 'consumption', assigned_to: null }))).toBe('Consumo');
  });
});
