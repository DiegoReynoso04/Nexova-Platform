// Historial (/inventory/orders): estado y sesión de hooks/use-inventory-orders.ts
// (los cuatro estados, reintento, carreras de recargas y desmontaje). Sin
// montar React; la unión con React se valida con tsc/lint/build.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_INVENTORY_ORDERS_STATE,
  createInventoryOrdersSession,
  inventoryOrdersReducer,
  ordersView,
} from '../hooks/use-inventory-orders.ts';
import { ApiAbortError, createApiClient } from '../lib/api-client.ts';
import { createInventoryService } from '../services/inventory.service.ts';
import { BASE_URL, jsonResponse, recordingFetch } from './support/http-fakes.mjs';
import { errorBody, inboundOrder, outboundOrder } from './support/inventory-fakes.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));

/** Operación asíncrona controlada a mano; rechaza con ApiAbortError al abortarse. */
function controllable() {
  const calls = [];
  const fn = (options) =>
    new Promise((resolve, reject) => {
      const call = { resolve, reject, aborted: false };
      options.signal.addEventListener('abort', () => {
        call.aborted = true;
        reject(new ApiAbortError());
      });
      calls.push(call);
    });
  return { fn, calls };
}

function store() {
  let state = INITIAL_INVENTORY_ORDERS_STATE;
  const actions = [];
  const dispatch = (action) => {
    actions.push(action);
    state = inventoryOrdersReducer(state, action);
  };
  return { dispatch, actions, state: () => state };
}

function sessionWith(listOrders) {
  const { dispatch, state, actions } = store();
  const session = createInventoryOrdersSession(dispatch, { listOrders });
  session.activate();
  return { session, state, actions };
}

describe('Historial: los cuatro estados', () => {
  test('cargando hasta recibir el historial', () => {
    const list = controllable();
    const { state } = sessionWith(list.fn);
    assert.equal(ordersView(state()), 'loading');
  });

  test('con datos, en el orden de la API (la más reciente primero)', async () => {
    const list = controllable();
    const { state } = sessionWith(list.fn);
    const orders = [outboundOrder({ id: 2 }), inboundOrder({ id: 5 })];
    list.calls[0].resolve(orders);
    await tick();
    assert.equal(ordersView(state()), 'data');
    assert.deepEqual(state().orders.map((order) => `${order.type}-${order.id}`), ['outbound-2', 'inbound-5']);
  });

  test('vacío', async () => {
    const list = controllable();
    const { state } = sessionWith(list.fn);
    list.calls[0].resolve([]);
    await tick();
    assert.equal(ordersView(state()), 'empty');
  });

  test('error con el detail de la API (servicio y cliente reales), y «Reintentar» lo recupera', async () => {
    let status = 503;
    const transport = recordingFetch(() =>
      status === 503 ? jsonResponse(503, errorBody('storage_unavailable', 'storage is temporarily unavailable')) : jsonResponse(200, [inboundOrder()])
    );
    const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL, getToken: () => 'synthetic-token' });
    const service = createInventoryService({ client, timeoutMs: 1_000 });
    const { session, state } = sessionWith(service.listOrders);
    await tick();
    await tick();
    assert.equal(ordersView(state()), 'error');
    assert.deepEqual(state().load.error, {
      kind: 'api_error',
      status: 503,
      code: 'storage_unavailable',
      detail: 'storage is temporarily unavailable',
      field: null,
    });
    assert.equal(transport.calls[0].url, `${BASE_URL}/inventory/orders`);
    status = 200;
    await session.reload();
    assert.equal(ordersView(state()), 'data');
  });

  test('un fallo tras una carga correcta no borra el historial, pero manda el error', async () => {
    const list = controllable();
    const { session, state } = sessionWith(list.fn);
    list.calls[0].resolve([inboundOrder()]);
    await tick();
    void session.reload();
    list.calls[1].reject(new Error('boom'));
    await tick();
    assert.equal(ordersView(state()), 'error');
    assert.equal(state().orders.length, 1);
  });
});

describe('Historial: carreras y desmontaje', () => {
  test('una recarga aborta la anterior y solo se ve la última respuesta', async () => {
    const list = controllable();
    const { session, state } = sessionWith(list.fn);
    void session.reload();
    assert.equal(list.calls[0].aborted, true);
    list.calls[1].resolve([outboundOrder({ id: 9 })]);
    await tick();
    assert.deepEqual(state().orders.map((order) => order.id), [9]);
  });

  test('si el servicio ignora la cancelación, la respuesta tardía se descarta', async () => {
    const calls = [];
    const listOrders = () => new Promise((resolve) => calls.push(resolve));
    const { session, state } = sessionWith(listOrders);
    void session.reload();
    calls[1]([inboundOrder({ id: 2, supplier: 'New' })]);
    await tick();
    calls[0]([inboundOrder({ id: 1, supplier: 'Stale' })]);
    await tick();
    assert.deepEqual(state().orders.map((order) => order.supplier), ['New']);
  });

  test('tras desmontar, la carga se aborta y no se despacha nada más', async () => {
    const list = controllable();
    const { session, actions } = sessionWith(list.fn);
    session.dispose();
    assert.equal(list.calls[0].aborted, true);
    list.calls[0].resolve([inboundOrder()]);
    await tick();
    assert.deepEqual(actions.map((action) => action.type), ['load_started']);
    void session.reload();
    assert.equal(list.calls.length, 1);
  });
});
