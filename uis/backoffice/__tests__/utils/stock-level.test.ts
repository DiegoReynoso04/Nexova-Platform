// lib/stock-level.ts: umbrales del indicador de nivel de stock (D6).
// 0 → Agotado; de 1 a 5 → Bajo; 6 o más → Suficiente.

import { LOW_STOCK_MAX, STOCK_LEVEL_LABELS, stockLevel } from '@/lib/stock-level';

describe('stockLevel', () => {
  test.each([
    [0, 'out'],
    [1, 'low'],
    [5, 'low'],
    [6, 'ok'],
    [13, 'ok'],
    [2_147_483_647, 'ok'],
  ] as const)('a current stock of %p is %p', (currentStock, expected) => {
    expect(stockLevel(currentStock)).toBe(expected);
  });

  test('a negative stock (the API never returns it) is shown as out of stock', () => {
    expect(stockLevel(-1)).toBe('out');
  });

  test('the low threshold is 5', () => {
    expect(LOW_STOCK_MAX).toBe(5);
    expect(stockLevel(LOW_STOCK_MAX)).toBe('low');
    expect(stockLevel(LOW_STOCK_MAX + 1)).toBe('ok');
  });

  test('every level has a Spanish label (text, not only colour)', () => {
    expect(STOCK_LEVEL_LABELS).toEqual({ out: 'Agotado', low: 'Bajo', ok: 'Suficiente' });
  });
});
