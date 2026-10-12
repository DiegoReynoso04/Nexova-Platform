// services/suppliers.service.ts: tarifa escrita por el usuario y campos requeridos
// del alta. tests/suppliers.service.test.mjs (node:test) ya cubre los casos
// generales; aquí, los límites del formato de la tarifa.

import { parseRate, validateSupplierForm } from '@/services/suppliers.service';
import type { SupplierFormValues } from '@/types/suppliers';

function form(changes: Partial<SupplierFormValues> = {}): SupplierFormValues {
  return {
    name: 'Synthetic Supplier',
    country: 'Spain',
    categories: ['job_boards'],
    monthly_rate: '100',
    currency: 'EUR',
    status: 'active',
    contract_renewal_date: '',
    contact_email: '',
    notes: '',
    ...changes,
  };
}

describe('parseRate', () => {
  test.each([
    ['0,01', 0.01],
    ['1200.50', 1200.5],
    ['  75,5  ', 75.5],
  ])('%p is a valid monthly rate (%p)', (input, expected) => {
    // Se admite la coma decimal española.
    expect(parseRate(input)).toBe(expected);
  });

  test.each(['0,00', '0.0', '1.000,50', '1,5,0', '+5', '5 €', ',5', 'Infinity', 'NaN'])(
    '%p is not a valid monthly rate',
    (input) => {
      // Sin separador de miles ni signos: la tarifa es un número positivo simple.
      expect(parseRate(input)).toBeNull();
    }
  );
});

describe('validateSupplierForm', () => {
  test('a rate written with a decimal comma passes', () => {
    expect(validateSupplierForm(form({ monthly_rate: '99,90' }))).toEqual([]);
  });

  test('a zero rate written as "0,00" is reported on the rate field only', () => {
    expect(validateSupplierForm(form({ monthly_rate: '0,00' })).map((error) => error.field)).toEqual(['monthly_rate']);
  });

  test('optional fields are not validated in the client: the API decides their format', () => {
    expect(validateSupplierForm(form({ contract_renewal_date: '2026-2-30', contact_email: 'no-es-un-email' }))).toEqual([]);
  });
});
