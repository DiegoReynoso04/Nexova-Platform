// services/inventory.service.ts: cantidad escrita por el usuario y validación en
// cliente de los formularios de entrada y salida. tests/inventory.service.test.mjs
// (node:test) cubre las peticiones y los errores; aquí, los límites.

import { parseQuantity, validateInboundForm, validateOutboundForm } from '@/services/inventory.service';
import { QUANTITY_MAX, TEXT_MAX_LENGTH, type InboundFormValues, type OutboundFormValues } from '@/types/inventory';

function inbound(changes: Partial<InboundFormValues> = {}): InboundFormValues {
  return { asset: { id: 1, office: 'Valencia' }, quantity: '5', supplier: 'Synthetic supplier', ...changes };
}

function outbound(changes: Partial<OutboundFormValues> = {}): OutboundFormValues {
  return {
    asset: { id: 1, office: 'Valencia' },
    quantity: '2',
    exit_type: 'allocation',
    assigned_to: 'Synthetic employee',
    ...changes,
  };
}

function fields(errors: readonly { field: string | null }[]): (string | null)[] {
  return errors.map((error) => error.field);
}

describe('parseQuantity', () => {
  test.each([
    ['1', 1],
    ['20', 20],
    ['  7  ', 7],
    ['007', 7],
    [String(QUANTITY_MAX), QUANTITY_MAX],
  ])('%p is a valid quantity (%p)', (input, expected) => {
    expect(parseQuantity(input)).toBe(expected);
  });

  test.each([
    '',
    '   ',
    '0',
    '-1',
    '1.5',
    '1,5',
    '2e3',
    '+3',
    '0x10',
    'cinco',
    '٣',
    String(QUANTITY_MAX + 1),
    '99999999999999999999',
  ])('%p is not a valid quantity', (input) => {
    // Enteros de 1 a QUANTITY_MAX escritos en dígitos ASCII: la API usa enteros estrictos.
    expect(parseQuantity(input)).toBeNull();
  });
});

describe('validateInboundForm', () => {
  test('a complete form has no errors', () => {
    expect(validateInboundForm(inbound())).toEqual([]);
  });

  test('every missing field is reported at once, in form order', () => {
    expect(fields(validateInboundForm(inbound({ asset: null, quantity: '', supplier: '   ' })))).toEqual([
      'asset_id',
      'quantity',
      'supplier',
    ]);
  });

  test('supplier up to the API limit, counted in characters (not UTF-16 units)', () => {
    expect(validateInboundForm(inbound({ supplier: 'x'.repeat(TEXT_MAX_LENGTH) }))).toEqual([]);
    expect(validateInboundForm(inbound({ supplier: '😀'.repeat(TEXT_MAX_LENGTH) }))).toEqual([]);
    expect(fields(validateInboundForm(inbound({ supplier: 'x'.repeat(TEXT_MAX_LENGTH + 1) })))).toEqual(['supplier']);
  });
});

describe('validateOutboundForm', () => {
  test('a complete allocation and a consumption without assigned_to are valid', () => {
    expect(validateOutboundForm(outbound())).toEqual([]);
    expect(validateOutboundForm(outbound({ exit_type: 'consumption', assigned_to: '' }))).toEqual([]);
  });

  test('allocation requires assigned_to', () => {
    expect(fields(validateOutboundForm(outbound({ assigned_to: '  ' })))).toEqual(['assigned_to']);
    expect(fields(validateOutboundForm(outbound({ assigned_to: 'x'.repeat(TEXT_MAX_LENGTH + 1) })))).toEqual(['assigned_to']);
  });

  test('a consumption ignores assigned_to (it is sent as null)', () => {
    expect(validateOutboundForm(outbound({ exit_type: 'consumption', assigned_to: 'x'.repeat(500) }))).toEqual([]);
  });

  test('every missing field is reported at once', () => {
    expect(fields(validateOutboundForm(outbound({ asset: null, quantity: '0', exit_type: '', assigned_to: '' })))).toEqual([
      'asset_id',
      'quantity',
      'exit_type',
    ]);
  });

  test('the client does not block a quantity above the stock: that is the API rule', () => {
    expect(validateOutboundForm(outbound({ quantity: '999999' }))).toEqual([]);
  });
});
