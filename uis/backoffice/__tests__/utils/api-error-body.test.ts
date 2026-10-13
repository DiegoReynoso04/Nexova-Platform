// services/normalizers.ts → normalizeApiErrorBody: el `{code, detail}` de un error
// de la API, sin copiar nada más. tests/normalizers.test.mjs (node:test) ya cubre
// los cuerpos parciales y arbitrarios; aquí, los dos casos que faltaban.

import { normalizeApiErrorBody } from '@/services/normalizers';

describe('normalizeApiErrorBody', () => {
  test('keeps the code and the text detail of an error body', () => {
    expect(normalizeApiErrorBody({ code: 'supplier_not_found', detail: 'supplier not found' })).toEqual({
      code: 'supplier_not_found',
      detail: 'supplier not found',
    });
  });

  test('a structured detail (object, as in the incident manager 400) is dropped, never shown as text', () => {
    expect(normalizeApiErrorBody({ code: 'validation_error', detail: { field: 'title', message: 'x' } })).toEqual({
      code: 'validation_error',
      detail: null,
    });
  });
});
