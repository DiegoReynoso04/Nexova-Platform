// lib/stock-check.ts: advertencia de la Salida de activos cuando la cantidad
// supera el stock mostrado. Solo avisa; no bloquea el envío.

import { exceedsStock } from '@/lib/stock-check';

describe('exceedsStock', () => {
  test.each([
    ['6', 5, true],
    ['5', 5, false],
    ['4', 5, false],
    ['1', 0, true],
    [' 6 ', 5, true],
    ['2147483647', 13, true],
  ] as const)('quantity %p with a stock of %p → %p', (quantity, currentStock, expected) => {
    expect(exceedsStock(quantity, currentStock)).toBe(expected);
  });

  test('without a known stock there is no warning', () => {
    expect(exceedsStock('999', null)).toBe(false);
  });

  test.each(['', 'abc', '1.5', '-3', '6abc', '99999999999999999999'])(
    'a quantity that is not a safe integer (%p) gives no warning: the form validation handles it',
    (quantity) => {
      expect(exceedsStock(quantity, 0)).toBe(false);
    }
  );
});
