// Entrada de activos (/inventory/orders/inbound): preselección por ?asset_id=,
// reparto de errores por campo (lib/inventory-form-errors.ts) y la sesión de
// hooks/use-inbound-form.ts con el servicio y el cliente reales sobre un
// transporte falso. Sin montar React.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_INBOUND_FORM_STATE,
  createInboundFormSession,
  inboundConfirmation,
  inboundFormReducer,
} from '../hooks/use-inbound-form.ts';
import { assetOptionLabel, formInitialAssetId, parseAssetIdParam, resolvePreselection } from '../lib/asset-preselection.ts';
import { createApiClient } from '../lib/api-client.ts';
import { fieldMessages, summaryError, unplacedMessages } from '../lib/inventory-form-errors.ts';
import { createInventoryService } from '../services/inventory.service.ts';
import { BASE_URL, LEAK, hangingFetch, jsonResponse, offlineFetch, recordingFetch, textResponse } from './support/http-fakes.mjs';
import { asset, errorBody, inboundOrder, inboundValues, selected } from './support/inventory-fakes.mjs';
import { validationBody } from './support/supplier-fakes.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const FORM_FIELDS = ['asset_id', 'quantity', 'supplier', 'office'];

function store() {
  let state = INITIAL_INBOUND_FORM_STATE;
  const actions = [];
  const dispatch = (action) => {
    actions.push(action);
    state = inboundFormReducer(state, action);
  };
  return { dispatch, actions, state: () => state };
}

/** Sesión con el servicio y el cliente reales sobre `fetch`. */
function sessionWith(fetch, timeoutMs = 1_000) {
  const client = createApiClient({ fetch, getBaseUrl: () => BASE_URL, getToken: () => 'synthetic-token' });
  const service = createInventoryService({ client, timeoutMs });
  const { dispatch, state, actions } = store();
  const session = createInboundFormSession(dispatch, { createInboundOrder: service.createInboundOrder });
  session.activate();
  return { session, state, actions };
}

async function submitWith(response, values = inboundValues()) {
  const transport = recordingFetch(response);
  const { session, state } = sessionWith(transport.fetch);
  await session.submit(values);
  return { state: state(), transport };
}

describe('?asset_id= y preselección', () => {
  test('lectura del parámetro', () => {
    assert.deepEqual(parseAssetIdParam(undefined), { requested: false });
    assert.deepEqual(parseAssetIdParam('3'), { requested: true, id: 3 });
    assert.deepEqual(parseAssetIdParam(' 12 '), { requested: true, id: 12 });
    for (const bad of ['', '0', '-1', '1.5', 'abc', '3abc', '99999999999999999999', ['1', '2']]) {
      assert.deepEqual(parseAssetIdParam(bad), { requested: true, id: null }, String(bad));
    }
  });

  test('sin parámetro, pendiente, encontrado y no encontrado', () => {
    const assets = [asset({ id: 1 }), asset({ id: 3, sku: 'SYN-PER-001' })];
    assert.deepEqual(resolvePreselection({ requested: false }, assets), { status: 'none' });
    assert.deepEqual(resolvePreselection({ requested: true, id: 3 }, null), { status: 'pending' });
    assert.deepEqual(resolvePreselection({ requested: true, id: 3 }, assets), { status: 'found', assetId: 3 });
    assert.deepEqual(resolvePreselection({ requested: true, id: 9 }, assets), { status: 'missing' });
    assert.deepEqual(resolvePreselection({ requested: true, id: null }, null), { status: 'missing' });
  });

  test('el formulario se monta con el activo de la URL, si existe', () => {
    assert.equal(formInitialAssetId({ status: 'found', assetId: 3 }), 3);
    for (const status of ['none', 'pending', 'missing']) assert.equal(formInitialAssetId({ status }), null, status);
  });

  test('las opciones muestran nombre — SKU (oficina), nunca el id', () => {
    const label = assetOptionLabel(asset({ id: 4242, name: 'Hub USB-C', sku: 'NXV-PER-002', office: 'Miami' }));
    assert.equal(label, 'Hub USB-C — NXV-PER-002 (Miami)');
    assert.equal(label.includes('4242'), false);
  });
});

describe('errores del formulario: campo o aviso general', () => {
  const validation = {
    kind: 'validation',
    source: 'api',
    errors: [
      { field: 'quantity', message: 'Cantidad', apiMessage: 'Input should be a valid integer' },
      { field: 'supplier', message: 'Proveedor' },
      { field: null, message: 'General', apiMessage: 'Body error' },
      { field: 'exit_type', message: 'No es de este formulario' },
    ],
  };

  test('422: cada error junto a su campo, con el msg de la API debajo', () => {
    assert.deepEqual(fieldMessages(validation, 'quantity'), [{ message: 'Cantidad', apiMessage: 'Input should be a valid integer' }]);
    assert.deepEqual(fieldMessages(validation, 'supplier'), [{ message: 'Proveedor' }]);
    assert.deepEqual(unplacedMessages(validation, FORM_FIELDS), [
      { message: 'General', apiMessage: 'Body error' },
      { message: 'No es de este formulario' },
    ]);
    assert.equal(summaryError(validation, FORM_FIELDS), validation);
  });

  test('api_error con campo del formulario: junto al campo y sin aviso general', () => {
    const stock = { kind: 'api_error', status: 400, code: 'insufficient_stock', detail: 'Insufficient stock…', field: 'quantity' };
    assert.deepEqual(fieldMessages(stock, 'quantity'), [{ message: 'Insufficient stock…' }]);
    assert.equal(summaryError(stock, FORM_FIELDS), null);
    assert.equal(summaryError(stock, ['asset_id']), stock);
  });

  test('el resto de errores: solo el aviso general', () => {
    for (const error of [
      { kind: 'api_error', status: 404, code: 'asset_not_found', detail: 'asset not found', field: null },
      { kind: 'network' },
      { kind: 'server_error' },
    ]) {
      assert.deepEqual(fieldMessages(error, 'quantity'), []);
      assert.equal(summaryError(error, FORM_FIELDS), error);
    }
    assert.equal(summaryError(null, FORM_FIELDS), null);
  });
});

describe('Entrada de activos: envío', () => {
  test('éxito: confirmación con cantidad, nombre y SKU, y formulario limpio (formKey + 1)', async () => {
    const order = inboundOrder({ quantity: 5, asset: { id: 1, name: 'Hub USB-C', sku: 'NXV-PER-002' } });
    const { state } = await submitWith(() => jsonResponse(201, order));
    assert.equal(state.submit.status, 'success');
    assert.equal(state.formKey, 1);
    assert.equal(inboundConfirmation(state.submit.order), 'Entrada registrada: 5 × Hub USB-C (NXV-PER-002)');
  });

  test('tras una entrada correcta, el formulario limpio conserva el activo de la URL', async () => {
    // La vista monta el formulario con `key = formKey-estado` e `initialAssetId = formInitialAssetId(preselección)`.
    const preselection = resolvePreselection(parseAssetIdParam('2'), [asset({ id: 1 }), asset({ id: 2, sku: 'SYN-IT-002' })]);
    const before = `${INITIAL_INBOUND_FORM_STATE.formKey}-${preselection.status}`;
    const { state } = await submitWith(() => jsonResponse(201, inboundOrder()), inboundValues({ asset: selected({ id: 2 }) }));
    assert.equal(state.submit.status, 'success');
    assert.notEqual(`${state.formKey}-${preselection.status}`, before);
    assert.equal(formInitialAssetId(preselection), 2);
  });

  test('body: asset_id y quantity como números y la oficina del activo elegido', async () => {
    const values = inboundValues({ asset: selected({ id: 4, office: 'Miami' }), quantity: '8', supplier: ' Office Depot Miami ' });
    const { transport } = await submitWith(() => jsonResponse(201, inboundOrder()), values);
    const body = JSON.parse(transport.calls[0].init.body);
    assert.deepEqual(body, { asset_id: 4, quantity: 8, supplier: 'Office Depot Miami', office: 'Miami' });
    assert.equal(transport.calls[0].url, `${BASE_URL}/inventory/orders/inbound`);
  });

  test('validación en cliente: errores por campo y ninguna petición', async () => {
    const { state, transport } = await submitWith(() => jsonResponse(201, inboundOrder()), inboundValues({ asset: null, quantity: 'cinco', supplier: '' }));
    assert.equal(transport.calls.length, 0);
    assert.equal(state.submit.status, 'error');
    assert.equal(state.submit.error.source, 'client');
    assert.deepEqual(state.submit.error.errors.map((item) => item.field), ['asset_id', 'quantity', 'supplier']);
    assert.equal(state.formKey, 0);
  });

  test('400, 404, 500 y 503 con detail: el detail de la API, en el aviso general', async () => {
    for (const [status, code, detail] of [
      [400, 'office_mismatch', 'order office does not match the asset office'],
      [404, 'asset_not_found', 'asset not found'],
      [500, 'internal_error', 'internal server error'],
      [503, 'storage_unavailable', 'storage is temporarily unavailable'],
    ]) {
      const { state } = await submitWith(() => jsonResponse(status, errorBody(code, detail)));
      assert.deepEqual(state.submit, { status: 'error', error: { kind: 'api_error', status, code, detail, field: null } }, code);
      assert.equal(summaryError(state.submit.error, FORM_FIELDS), state.submit.error);
    }
  });

  test('422: junto a cada campo, texto propio y el msg de la API', async () => {
    const { state } = await submitWith(() => jsonResponse(422, validationBody([['body', 'supplier'], 'String should have at most 200 characters'])));
    assert.deepEqual(fieldMessages(state.submit.error, 'supplier'), [
      { message: 'Indica el proveedor (máximo 200 caracteres).', apiMessage: 'String should have at most 200 characters' },
    ]);
  });

  test('red, timeout y respuesta ilegible: textos fijos', async () => {
    const offline = sessionWith(offlineFetch());
    await offline.session.submit(inboundValues());
    assert.deepEqual(offline.state().submit, { status: 'error', error: { kind: 'network' } });

    const slow = sessionWith(hangingFetch(), 20);
    await slow.session.submit(inboundValues());
    assert.deepEqual(slow.state().submit, { status: 'error', error: { kind: 'timeout' } });

    const { state } = await submitWith(() => textResponse(500, `<html>${LEAK}</html>`));
    assert.deepEqual(state.submit, { status: 'error', error: { kind: 'server_error' } });
  });

  test('un segundo envío mientras el primero está en curso se ignora', async () => {
    const transport = recordingFetch(() => new Promise(() => {}));
    const { session, actions } = sessionWith(transport.fetch, 10_000);
    void session.submit(inboundValues());
    void session.submit(inboundValues({ quantity: '9' }));
    await tick();
    assert.equal(transport.calls.length, 1);
    assert.deepEqual(actions.map((action) => action.type), ['submit_started']);
    session.dispose();
  });

  test('tras desmontar, el envío se aborta y no se despacha nada más', async () => {
    let aborted = false;
    const fetch = (url, init) =>
      new Promise((_, reject) => {
        init.signal.addEventListener('abort', () => {
          aborted = true;
          reject(new DOMException('aborted', 'AbortError'));
        });
      });
    const { session, actions } = sessionWith(fetch, 10_000);
    const pending = session.submit(inboundValues());
    session.dispose();
    await pending;
    assert.equal(aborted, true);
    assert.deepEqual(actions.map((action) => action.type), ['submit_started']);
  });
});
