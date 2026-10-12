// services/incident-manager.service.ts: validación en cliente del formulario del
// gestor y textos de los errores de la API. tests/incident-manager.service.test.mjs
// (node:test) ya cubre los casos generales; aquí, los límites.

import { countCharacters, validateIncidentForm } from '@/services/incident-manager.service';
import type { IncidentFormValues } from '@/types/incident-manager';

function form(changes: Partial<IncidentFormValues> = {}): IncidentFormValues {
  return {
    title: 'Synthetic incident',
    description: 'Synthetic description',
    category: 'technical_failure',
    origin: 'branch',
    branch: 'central',
    ...changes,
  };
}

function titleErrors(title: string): string[] {
  return validateIncidentForm(form({ title }))
    .filter((error) => error.field === 'title')
    .map((error) => error.message);
}

describe('countCharacters', () => {
  test('counts characters like the API does, not UTF-16 units', () => {
    expect(countCharacters('abc')).toBe(3);
    // Un emoji son 2 unidades UTF-16 (`.length` = 2) pero 1 carácter para la API (`len()` de Python).
    expect(countCharacters('😀')).toBe(1);
    expect(countCharacters('ñandú')).toBe(5);
  });

  test('an empty text has no characters', () => {
    expect(countCharacters('')).toBe(0);
  });
});

describe('validateIncidentForm — title limit (120 characters, as the API counts them)', () => {
  test.each([
    ['120 ASCII characters', 'a'.repeat(120)],
    ['60 emojis', '😀'.repeat(60)],
    // El bug: 61 emojis son 122 unidades UTF-16, pero 61 caracteres; la API los acepta.
    ['61 emojis', '😀'.repeat(61)],
    ['120 emojis', '😀'.repeat(120)],
  ])('%s are accepted', (_case, title) => {
    expect(titleErrors(title)).toEqual([]);
  });

  test.each([
    ['121 ASCII characters', 'a'.repeat(121)],
    ['121 emojis', '😀'.repeat(121)],
  ])('%s are rejected', (_case, title) => {
    expect(titleErrors(title)).toEqual(['El título no puede superar los 120 caracteres.']);
  });
});
