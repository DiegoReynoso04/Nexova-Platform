// Salida de activos (/inventory/orders/outbound): stock reactivo, advertencia
// que no bloquea, «Asignado a» solo con una asignación, errores por campo y la
// sesión de hooks/use-outbound-form.ts. La lectura del stock se controla a
// mano; el envío usa el servicio y el cliente reales sobre un transporte falso.
// Sin montar React.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_OUTBOUND_FORM_STATE,
  createOutboundFormSession,
  knownStock,
  outboundConfirmation,
  outboundFormReducer,
  outboundFormValues,
  quantityEnabled,
} from '../hooks/use-outbound-form.ts';
import { createApiClient } from '../lib/api-client.ts';
import { ApiAbortError } from '../lib/api-client.ts';
import { fieldMessages, summaryError } from '../lib/inventory-form-errors.ts';
import { exceedsStock } from '../lib/stock-check.ts';
import { createInventoryService } from '../services/inventory.service.ts';
import { BASE_URL, jsonResponse, recordingFetch } from './support/http-fakes.mjs';
import { asset, errorBody, outboundOrder, outboundValues, selected } from './support/inventory-fakes.mjs';
import { validationBody } from './support/supplier-fakes.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const FORM_FIELDS = ['asset_id', 'quantity', 'exit_type', 'office', 'assigned_to'];

function store() {
  let state = INITIAL_OUTBOUND_FORM_STATE;
  const actions = [];
  const dispatch = (action) => {
    actions.push(action);
    state = outboundFormReducer(state, action);
  };
  return { dispatch, actions, state: () => state };
}

/** `getAsset` controlado a mano; rechaza con ApiAbortError al abortarse (como el servicio real). */
function controllableStock() {
  const calls = [];
  const fn = (id, options) =>
    new Promise((resolve, reject) => {
      const call = { id, resolve: (stock) => resolve(asset({ id, current_stock: stock })), reject, aborted: false };
      options.signal.addEventListener('abort', () => {
        call.aborted = true;
        reject(new ApiAbortError());
      });
      calls.push(call);
    });
  return { fn, calls };
}

/** Sesión con un `getAsset` controlado y el envío real sobre `fetch`. */
function sessionWith({ getAsset = controllableStock().fn, fetch = recordingFetch(() => jsonResponse(201, outboundOrder())).fetch } = {}) {
  const client = createApiClient({ fetch, getBaseUrl: () => BASE_URL, getToken: () => 'synthetic-token' });
  const service = createInventoryService({ client, timeoutMs: 1_000 });
  const { dispatch, state, actions } = store();
  const session = createOutboundFormSession(dispatch, { getAsset, createOutboundOrder: service.createOutboundOrder });
  session.activate();
  return { session, state, actions };
}

/** Sesión con el activo `id` elegido y su stock ya leído. */
async function withKnownStock(id, currentStock, fetch) {
  const stock = controllableStock();
  const context = sessionWith({ getAsset: stock.fn, fetch });
  void context.session.selectAsset(id);
  stock.calls[0].resolve(currentStock);
  await tick();
  return { ...context, stock };
}

describe('stock: valor mostrado y Cantidad', () => {
  test('Cantidad se habilita solo con el stock conocido o si su lectura falló', () => {
    assert.equal(quantityEnabled({ status: 'idle' }), false);
    assert.equal(quantityEnabled({ status: 'loading', assetId: 1, previous: null }), false);
    assert.equal(quantityEnabled({ status: 'loading', assetId: 1, previous: 4 }), true);
    assert.equal(quantityEnabled({ status: 'known', assetId: 1, currentStock: 0 }), true);
    assert.equal(quantityEnabled({ status: 'error', assetId: 1 }), true);
    assert.equal(knownStock({ status: 'loading', assetId: 1, previous: 4 }), 4);
    assert.equal(knownStock({ status: 'error', assetId: 1 }), null);
  });

  test('elegir un activo lanza la lectura de su stock y la muestra', async () => {
    const stock = controllableStock();
    const { session, state } = sessionWith({ getAsset: stock.fn });
    void session.selectAsset(2);
    assert.deepEqual(stock.calls.map((call) => call.id), [2]);
    assert.deepEqual(state().stock, { status: 'loading', assetId: 2, previous: null });
    assert.equal(quantityEnabled(state().stock), false);
    stock.calls[0].resolve(7);
    await tick();
    assert.equal(state().assetId, 2);
    assert.deepEqual(state().stock, { status: 'known', assetId: 2, currentStock: 7 });
    assert.equal(quantityEnabled(state().stock), true);
  });

  test('cambiar de A a B aborta la lectura de A y solo se ve el stock de B', async () => {
    const stock = controllableStock();
    const { session, state } = sessionWith({ getAsset: stock.fn });
    void session.selectAsset(1);
    void session.selectAsset(2);
    assert.equal(stock.calls[0].aborted, true);
    stock.calls[1].resolve(9);
    await tick();
    assert.deepEqual(state().stock, { status: 'known', assetId: 2, currentStock: 9 });
  });

  test('con un servicio que ignora la cancelación, la respuesta tardía de A se descarta', async () => {
    const pending = [];
    const getAsset = (id) => new Promise((resolve) => pending.push({ id, resolve }));
    const { session, state } = sessionWith({ getAsset });
    void session.selectAsset(1);
    void session.selectAsset(2);
    pending[1].resolve(asset({ id: 2, current_stock: 9 }));
    await tick();
    pending[0].resolve(asset({ id: 1, current_stock: 100 }));
    await tick();
    assert.deepEqual(state().stock, { status: 'known', assetId: 2, currentStock: 9 });
  });

  test('A → B → A con un servicio que ignora la cancelación: la primera lectura de A no pisa la última', async () => {
    const pending = [];
    const getAsset = (id) => new Promise((resolve) => pending.push({ id, resolve }));
    const { session, state } = sessionWith({ getAsset });
    void session.selectAsset(1);
    void session.selectAsset(2);
    void session.selectAsset(1);
    pending[0].resolve(asset({ id: 1, current_stock: 100 }));
    await tick();
    assert.deepEqual(state().stock, { status: 'loading', assetId: 1, previous: null });
    pending[2].resolve(asset({ id: 1, current_stock: 4 }));
    await tick();
    assert.deepEqual(state().stock, { status: 'known', assetId: 1, currentStock: 4 });
  });

  test('si la lectura falla, Cantidad se habilita (con el aviso en la vista)', async () => {
    const stock = controllableStock();
    const { session, state } = sessionWith({ getAsset: stock.fn });
    void session.selectAsset(3);
    stock.calls[0].reject(new Error('boom'));
    await tick();
    assert.deepEqual(state().stock, { status: 'error', assetId: 3 });
    assert.equal(quantityEnabled(state().stock), true);
  });

  test('sin activo, no hay lectura ni stock', async () => {
    const stock = controllableStock();
    const { session, state } = sessionWith({ getAsset: stock.fn });
    void session.selectAsset(1);
    void session.selectAsset(null);
    assert.equal(stock.calls[0].aborted, true);
    assert.equal(stock.calls.length, 1);
    assert.deepEqual(state().stock, { status: 'idle' });
    assert.equal(state().assetId, null);
  });
});

describe('advertencia de stock', () => {
  test('aparece si la cantidad supera el stock mostrado', () => {
    assert.equal(exceedsStock('6', 5), true);
    assert.equal(exceedsStock('5', 5), false);
    assert.equal(exceedsStock('6', null), false);
  });

  test('no bloquea el envío: la salida llega a la API', async () => {
    const transport = recordingFetch(() => jsonResponse(201, outboundOrder()));
    const { session, state } = await withKnownStock(1, 5, transport.fetch);
    const values = outboundValues({ quantity: '8' });
    assert.equal(exceedsStock(values.quantity, knownStock(state().stock)), true);
    await session.submit(values, null);
    assert.equal(transport.calls.length, 1);
    assert.equal(JSON.parse(transport.calls[0].init.body).quantity, 8);
    assert.equal(state().submit.status, 'success');
  });
});

describe('«Asignado a» solo con una asignación', () => {
  test('en los valores del formulario', () => {
    const chosen = selected();
    assert.equal(outboundFormValues(chosen, '2', 'allocation', 'Synthetic employee').assigned_to, 'Synthetic employee');
    assert.equal(outboundFormValues(chosen, '2', 'consumption', 'Synthetic employee').assigned_to, '');
    assert.equal(outboundFormValues(chosen, '2', '', 'Synthetic employee').assigned_to, '');
  });

  test('en el body: el texto con una asignación y null en un consumo', async () => {
    for (const [exitType, expected] of [
      ['allocation', 'Synthetic employee'],
      ['consumption', null],
    ]) {
      const transport = recordingFetch(() => jsonResponse(201, outboundOrder()));
      const { session } = sessionWith({ fetch: transport.fetch });
      await session.submit(outboundFormValues(selected({ id: 4, office: 'Miami' }), '2', exitType, ' Synthetic employee '), null);
      assert.deepEqual(JSON.parse(transport.calls[0].init.body), {
        asset_id: 4,
        quantity: 2,
        exit_type: exitType,
        assigned_to: expected,
        office: 'Miami',
      });
      assert.equal(transport.calls[0].url, `${BASE_URL}/inventory/orders/outbound`);
    }
  });

  test('validación en cliente: asignación sin «Asignado a», ninguna petición', async () => {
    const transport = recordingFetch(() => jsonResponse(201, outboundOrder()));
    const { session, state } = sessionWith({ fetch: transport.fetch });
    await session.submit(outboundFormValues(selected(), '2', 'allocation', ' '), null);
    assert.equal(transport.calls.length, 0);
    assert.deepEqual(state().submit.error.errors.map((item) => item.field), ['assigned_to']);
  });
});

describe('Salida de activos: errores del envío', () => {
  test('400 insufficient_stock: el detail junto a Cantidad, sin aviso general, y se vuelve a leer el stock', async () => {
    const detail = 'Insufficient stock: requested 8, available 5';
    const transport = recordingFetch(() => jsonResponse(400, errorBody('insufficient_stock', detail)));
    const { session, state, stock } = await withKnownStock(1, 5, transport.fetch);
    await session.submit(outboundValues({ quantity: '8' }), 1);
    const { error } = state().submit;
    assert.deepEqual(error, { kind: 'api_error', status: 400, code: 'insufficient_stock', detail, field: 'quantity' });
    assert.deepEqual(fieldMessages(error, 'quantity'), [{ message: detail }]);
    assert.equal(summaryError(error, FORM_FIELDS), null);
    // Se vuelve a leer el stock del activo elegido, sin vaciar el valor conocido.
    assert.deepEqual(stock.calls.map((call) => call.id), [1, 1]);
    assert.deepEqual(state().stock, { status: 'loading', assetId: 1, previous: 5 });
    assert.equal(state().formKey, 0);
  });

  test('422 de assigned_to: en su campo, con el texto según el tipo y el msg de la API', async () => {
    const body = validationBody([['body', 'assigned_to'], 'Value error, assigned_to is required for allocation']);
    const transport = recordingFetch(() => jsonResponse(422, body));
    const { session, state } = sessionWith({ fetch: transport.fetch });
    await session.submit(outboundValues({ exit_type: 'allocation' }), null);
    assert.deepEqual(fieldMessages(state().submit.error, 'assigned_to'), [
      { message: 'Indica a quién se asigna el activo (máximo 200 caracteres).', apiMessage: 'assigned_to is required for allocation' },
    ]);
  });

  test('otros errores con detail: el aviso general, como en la entrada', async () => {
    const transport = recordingFetch(() => jsonResponse(404, errorBody('asset_not_found', 'asset not found')));
    const { session, state } = sessionWith({ fetch: transport.fetch });
    await session.submit(outboundValues(), null);
    const { error } = state().submit;
    assert.equal(summaryError(error, FORM_FIELDS), error);
    assert.deepEqual(fieldMessages(error, 'quantity'), []);
  });
});

describe('Salida de activos: éxito, doble envío y desmontaje', () => {
  test('éxito: confirmación, formulario limpio con el activo de la URL y stock leído de nuevo', async () => {
    const order = outboundOrder({ quantity: 2, asset: { id: 1, name: 'Hub USB-C', sku: 'NXV-PER-002' } });
    const transport = recordingFetch(() => jsonResponse(201, order));
    const { session, state, stock } = await withKnownStock(1, 5, transport.fetch);
    await session.submit(outboundValues(), 1);
    assert.equal(state().submit.status, 'success');
    assert.equal(outboundConfirmation(state().submit.order), 'Salida registrada: 2 × Hub USB-C (NXV-PER-002)');
    assert.equal(state().formKey, 1);
    assert.equal(state().assetId, 1);
    assert.deepEqual(stock.calls.map((call) => call.id), [1, 1]);
    stock.calls[1].resolve(3);
    await tick();
    assert.deepEqual(state().stock, { status: 'known', assetId: 1, currentStock: 3 });
  });

  test('éxito sin activo en la URL: el formulario queda sin activo y no se lee stock', async () => {
    const { session, state, stock } = await withKnownStock(2, 5);
    await session.submit(outboundValues({ asset: selected({ id: 2 }) }), null);
    assert.equal(state().formKey, 1);
    assert.equal(state().assetId, null);
    assert.deepEqual(state().stock, { status: 'idle' });
    assert.equal(stock.calls.length, 1);
  });

  test('un segundo envío mientras el primero está en curso se ignora', async () => {
    const transport = recordingFetch(() => new Promise(() => {}));
    const { session, actions } = sessionWith({ fetch: transport.fetch });
    void session.submit(outboundValues(), null);
    void session.submit(outboundValues({ quantity: '9' }), null);
    await tick();
    assert.equal(transport.calls.length, 1);
    assert.deepEqual(actions.map((action) => action.type), ['submit_started']);
    session.dispose();
  });

  test('tras desmontar, la lectura del stock se aborta y no se despacha nada más', async () => {
    const stock = controllableStock();
    const { session, actions } = sessionWith({ getAsset: stock.fn });
    void session.selectAsset(1);
    session.dispose();
    assert.equal(stock.calls[0].aborted, true);
    await tick();
    void session.selectAsset(2);
    assert.equal(stock.calls.length, 1);
    assert.deepEqual(actions.map((action) => action.type), ['asset_selected', 'stock_requested']);
  });
});
