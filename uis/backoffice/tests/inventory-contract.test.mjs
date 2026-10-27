// El vocabulario del inventario del frontend (types/inventory.ts) coincide con
// el CONTEXT (docs/context-nexova-gestion-inventario-hito-5.md) y con el del
// backend (services/api/app/modules/inventory/vocabulary.py), y las rutas son
// las cuatro del brief, protegidas por el guard.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, test } from 'node:test';

import { routeAccess } from '../lib/auth-routes.ts';
import {
  INVENTORY_INBOUND_PATH,
  INVENTORY_ORDERS_PATH,
  INVENTORY_OUTBOUND_PATH,
  INVENTORY_PAGES,
  INVENTORY_PRODUCTS_PATH,
  inboundOrderHref,
  outboundOrderHref,
} from '../lib/inventory-routes.ts';
import { ASSET_CATEGORIES, EXIT_TYPES, OFFICES, QUANTITY_MAX, TEXT_MAX_LENGTH } from '../types/inventory.ts';

const CONTEXT = readFileSync(new URL('../../../docs/context-nexova-gestion-inventario-hito-5.md', import.meta.url), 'utf8');
const BACKEND = readFileSync(new URL('../../../services/api/app/modules/inventory/vocabulary.py', import.meta.url), 'utf8');

/** Valores entre comillas de la fila de la tabla del CONTEXT para `field`. */
function contextValues(field) {
  const row = CONTEXT.split('\n').find((line) => line.startsWith(`| \`${field}\` |`));
  assert.ok(row, `${field} not found in the CONTEXT`);
  return [...row.matchAll(/`"([^"]+)"`/g)].map((match) => match[1]);
}

/**
 * Valores de una enumeración `class Name(StrEnum)` del backend. `\r?\n`: con
 * `core.autocrlf=true` (Windows), la copia de trabajo de vocabulary.py tiene CRLF
 * aunque el índice esté en LF.
 */
function backendEnum(name) {
  const block = new RegExp(`class ${name}\\(StrEnum\\):\\r?\\n((?:    .+\\r?\\n)+)`).exec(BACKEND);
  assert.ok(block, `${name} not found in vocabulary.py`);
  return [...block[1].matchAll(/= "([^"]+)"/g)].map((match) => match[1]);
}

function backendConstant(name) {
  const match = new RegExp(`^${name} = ([\\d_]+)$`, 'm').exec(BACKEND);
  assert.ok(match, `${name} not found in vocabulary.py`);
  return Number(match[1].replaceAll('_', ''));
}

describe('vocabulario del inventario = CONTEXT y backend', () => {
  test('categorías, en el mismo orden', () => {
    assert.deepEqual([...ASSET_CATEGORIES], contextValues('category'));
    assert.deepEqual([...ASSET_CATEGORIES], backendEnum('AssetCategory'));
  });

  test('oficinas', () => {
    assert.deepEqual([...OFFICES], contextValues('office'));
    assert.deepEqual([...OFFICES], backendEnum('Office'));
  });

  test('tipos de salida', () => {
    assert.deepEqual([...EXIT_TYPES], contextValues('exit_type'));
    assert.deepEqual([...EXIT_TYPES], backendEnum('ExitType'));
  });

  test('límites técnicos iguales a los de la API', () => {
    assert.equal(QUANTITY_MAX, backendConstant('QUANTITY_MAX'));
    assert.equal(TEXT_MAX_LENGTH, backendConstant('TEXT_MAX_LENGTH'));
  });
});

describe('rutas del inventario', () => {
  test('las cuatro páginas del brief', () => {
    assert.deepEqual(
      [INVENTORY_PRODUCTS_PATH, INVENTORY_INBOUND_PATH, INVENTORY_OUTBOUND_PATH, INVENTORY_ORDERS_PATH],
      ['/inventory/products', '/inventory/orders/inbound', '/inventory/orders/outbound', '/inventory/orders']
    );
    assert.deepEqual([...INVENTORY_PAGES].sort(), [
      '/inventory/orders',
      '/inventory/orders/inbound',
      '/inventory/orders/outbound',
      '/inventory/products',
    ]);
  });

  test('sin sesión, las cuatro redirigen al login; con sesión, se muestran', () => {
    for (const path of INVENTORY_PAGES) {
      assert.equal(routeAccess(path, 'anonymous'), 'redirect_login', path);
      assert.equal(routeAccess(path, 'authenticated'), 'render', path);
      assert.equal(routeAccess(path, 'checking'), 'wait', path);
    }
  });

  test('enlaces con el activo preseleccionado', () => {
    assert.equal(inboundOrderHref(3), '/inventory/orders/inbound?asset_id=3');
    assert.equal(outboundOrderHref(5), '/inventory/orders/outbound?asset_id=5');
  });
});
