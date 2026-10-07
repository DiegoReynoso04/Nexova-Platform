// El vocabulario del gestor de incidencias del frontend (types/incident-manager.ts)
// coincide exactamente con docs/centralized-incident-manager.md: enumerados,
// etiquetas de sede, tabla de transiciones y límite del título.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, test } from 'node:test';

import {
  BRANCH_LABELS,
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  INCIDENT_TRANSITIONS,
  INITIAL_INCIDENT_STATUS,
  TITLE_MAX_LENGTH,
} from '../types/incident-manager.ts';

const CONTEXT = readFileSync(new URL('../../../docs/centralized-incident-manager.md', import.meta.url), 'utf8');
const LINES = CONTEXT.split(/\r?\n/);

/** Filas de datos (sin cabecera) de la primera tabla Markdown tras la línea `marker`. */
function table(marker) {
  const start = LINES.indexOf(marker);
  assert.notEqual(start, -1, `${marker} not found in the CONTEXT`);
  const rows = [];
  for (const line of LINES.slice(start + 1)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('|')) {
      if (rows.length > 0) break;
      continue;
    }
    const cells = trimmed.replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim().replace(/^`|`$/g, '').trim());
    if (cells.every((cell) => /^-+$/.test(cell))) continue;
    rows.push(cells);
  }
  return rows.slice(1);
}

const firstColumn = (marker) => table(marker).map((row) => row[0]);

describe('vocabulario = CONTEXT', () => {
  test('sedes y sus etiquetas literales, en el mismo orden', () => {
    const rows = table('## Oficinas de Nexova');
    assert.deepEqual([...INCIDENT_BRANCHES], rows.map((row) => row[0]));
    assert.deepEqual({ ...BRANCH_LABELS }, Object.fromEntries(rows));
    assert.deepEqual(Object.keys(BRANCH_LABELS), [...INCIDENT_BRANCHES]);
  });

  test('categorías', () => {
    assert.deepEqual([...INCIDENT_CATEGORIES], firstColumn('## Categorías de incidencias'));
  });

  test('estados', () => {
    assert.deepEqual([...INCIDENT_STATUSES], firstColumn('## Estados y ciclo de vida'));
  });

  test('orígenes', () => {
    assert.deepEqual([...INCIDENT_ORIGINS], firstColumn('## Orígenes'));
  });

  test('el título admite hasta 120 caracteres (recorte del seed)', () => {
    assert.match(CONTEXT, /Primeros 120 caracteres de `description`/);
    assert.equal(TITLE_MAX_LENGTH, 120);
  });
});

describe('ciclo de vida = CONTEXT', () => {
  const line = LINES.find((item) => item.startsWith('Transiciones válidas:'));

  test('tabla de transiciones', () => {
    assert.ok(line, 'transitions line not found');
    const documented = [...line.matchAll(/`(\w+) → (\w+)`/g)].map((match) => `${match[1]}>${match[2]}`).sort();
    assert.equal(documented.length, 4);
    const implemented = Object.entries(INCIDENT_TRANSITIONS)
      .flatMap(([from, targets]) => targets.map((to) => `${from}>${to}`))
      .sort();
    assert.deepEqual(implemented, documented);
    assert.deepEqual(Object.keys(INCIDENT_TRANSITIONS), [...INCIDENT_STATUSES]);
  });

  test('los estados finales no tienen transiciones', () => {
    const finals = /Los estados `(\w+)` y `(\w+)` son finales/.exec(line);
    assert.ok(finals);
    for (const status of finals.slice(1)) assert.deepEqual(INCIDENT_TRANSITIONS[status], [], status);
  });

  test('las 16 combinaciones', () => {
    const allowed = new Set(['open>in_progress', 'open>discarded', 'in_progress>resolved', 'in_progress>discarded']);
    for (const from of INCIDENT_STATUSES) {
      for (const to of INCIDENT_STATUSES) {
        assert.equal(INCIDENT_TRANSITIONS[from].includes(to), allowed.has(`${from}>${to}`), `${from} → ${to}`);
      }
    }
  });

  test('toda incidencia nueva nace open', () => {
    assert.equal(INITIAL_INCIDENT_STATUS, 'open');
  });
});
