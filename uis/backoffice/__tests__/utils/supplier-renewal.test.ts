// lib/supplier-renewal.ts: proveedores que renuevan en los próximos 60 días
// (docs/ligthweight-storage-api.md, «Restricciones de negocio»). Es presentación
// con la fecha local del navegador. tests/suppliers-contract.test.mjs (node:test)
// ya cubre la ventana con una fecha de 2026; aquí, los límites del calendario.

import { RENEWAL_WINDOW_DAYS, daysUntil, renewalInfo } from '@/lib/supplier-renewal';

// 1 de enero de 2028 (año bisiesto), a media mañana en hora local.
const NEW_YEAR_2028 = new Date(2028, 0, 1, 10, 30);

describe('daysUntil', () => {
  test.each([
    ['2028-01-01', 0],
    ['2028-02-29', 59],
    ['2028-03-01', 60],
    ['2028-03-02', 61],
    ['2027-12-31', -1],
  ])('%s is %i days away from 2028-01-01', (date, expected) => {
    expect(daysUntil(date, NEW_YEAR_2028)).toBe(expected);
  });

  test('the time of day does not matter: only the local calendar date counts', () => {
    expect(daysUntil('2028-01-02', new Date(2028, 0, 1, 0, 0))).toBe(1);
    expect(daysUntil('2028-01-02', new Date(2028, 0, 1, 23, 59))).toBe(1);
  });

  test('daylight saving changes do not shift the count', () => {
    // En España el horario cambia el 29-03-2026 y el 25-10-2026: esos días duran 23 y 25 horas.
    expect(daysUntil('2026-03-30', new Date(2026, 2, 28, 23, 30))).toBe(2);
    expect(daysUntil('2026-10-26', new Date(2026, 9, 24, 12, 0))).toBe(2);
  });

  test.each(['2026-02-30', '2027-02-29', '2026-2-3', '2026-13-01', '2026-00-10', '2026-04-31', ' 2026-03-01', ''])(
    '%p is not a valid date',
    (date) => {
      expect(daysUntil(date, NEW_YEAR_2028)).toBeNull();
    }
  );
});

describe('renewalInfo', () => {
  test('today and up to day 60 (included) are upcoming, also across a 29 February', () => {
    expect(renewalInfo('2028-01-01', NEW_YEAR_2028)).toEqual({ kind: 'upcoming', daysLeft: 0 });
    expect(renewalInfo('2028-02-29', NEW_YEAR_2028)).toEqual({ kind: 'upcoming', daysLeft: 59 });
    expect(renewalInfo('2028-03-01', NEW_YEAR_2028)).toEqual({ kind: 'upcoming', daysLeft: RENEWAL_WINDOW_DAYS });
  });

  test('day 61 is later and yesterday is past', () => {
    expect(renewalInfo('2028-03-02', NEW_YEAR_2028)).toEqual({ kind: 'later' });
    expect(renewalInfo('2027-12-31', NEW_YEAR_2028)).toEqual({ kind: 'past' });
  });

  test.each([null, '2026-02-30', '2026-2-3'])('%p is not highlighted at all', (date) => {
    // Sin fecha o con una fecha imposible no hay nada que destacar (ni «pasada»).
    expect(renewalInfo(date, NEW_YEAR_2028)).toEqual({ kind: 'none' });
  });
});
