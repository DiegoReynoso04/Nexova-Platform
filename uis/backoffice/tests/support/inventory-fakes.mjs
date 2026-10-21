// Datos de prueba del inventario (services/api/SPECS.md Parte F, §37).
// Activos con el formato de la API; usuario y textos sintéticos.

export const USER_UUID = '00000000-0000-4000-8000-000000000000';

export function asset(overrides = {}) {
  return {
    id: 1,
    name: 'Synthetic laptop',
    sku: 'SYN-IT-001',
    category: 'hardware',
    office: 'Valencia',
    current_stock: 13,
    ...overrides,
  };
}

export function inboundOrder(overrides = {}) {
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

export function outboundOrder(overrides = {}) {
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

/** Activo elegido en un formulario: su id y su oficina. */
export function selected(overrides = {}) {
  return { id: 1, office: 'Valencia', ...overrides };
}

export function inboundValues(overrides = {}) {
  return { asset: selected(), quantity: '5', supplier: 'Synthetic supplier', ...overrides };
}

export function outboundValues(overrides = {}) {
  return { asset: selected(), quantity: '2', exit_type: 'allocation', assigned_to: 'Synthetic employee', ...overrides };
}

/** Cuerpo de error de la API (`{detail, code}`). */
export function errorBody(code, detail) {
  return { detail, code };
}
