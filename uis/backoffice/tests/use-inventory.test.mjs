// Estado del inventario: reducer y sesión del listado de activos
// (hooks/use-inventory-assets.ts), sin montar React, y los textos de error de
// lib/inventory-error-copy.ts. La unión con React se valida con tsc/lint/build
// y en el navegador.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_INVENTORY_ASSETS_STATE,
  assetsView,
  createInventoryAssetsSession,
  inventoryAssetsReducer,
} from '../hooks/use-inventory-assets.ts';
import { ApiAbortError } from '../lib/api-client.ts';
import { inventoryErrorCopy } from '../lib/inventory-error-copy.ts';
import { InventoryServiceError } from '../services/inventory.service.ts';
import { asset } from './support/inventory-fakes.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));

/** Operación asíncrona controlada a mano; rechaza con ApiAbortError al abortarse. */
function controllable() {
  const calls = [];
  const fn = (...args) => {
    const options = args[args.length - 1];
    return new Promise((resolve, reject) => {
      const call = { args, resolve, reject, aborted: false };
      options.signal.addEventListener('abort', () => {
        call.aborted = true;
        reject(new ApiAbortError());
      });
      calls.push(call);
    });
  };
  return { fn, calls };
}

function store() {
  let state = INITIAL_INVENTORY_ASSETS_STATE;
  const actions = [];
  const dispatch = (action) => {
    actions.push(action);
    state = inventoryAssetsReducer(state, action);
  };
  return { dispatch, actions, state: () => state };
}

const NETWORK = { kind: 'network' };

describe('listado de activos: estados', () => {
  test('cargando, error, vacío y con datos', () => {
    let state = INITIAL_INVENTORY_ASSETS_STATE;
    assert.equal(assetsView(state), 'loading');
    state = inventoryAssetsReducer(state, { type: 'load_started' });
    assert.equal(assetsView(state), 'loading');
    state = inventoryAssetsReducer(state, { type: 'load_failed', error: NETWORK });
    assert.equal(assetsView(state), 'error');
    state = inventoryAssetsReducer(state, { type: 'load_started' });
    assert.equal(assetsView(state), 'loading');
    state = inventoryAssetsReducer(state, { type: 'load_succeeded', assets: [] });
    assert.equal(assetsView(state), 'empty');
    state = inventoryAssetsReducer(state, { type: 'load_succeeded', assets: [asset(), asset({ id: 2 })] });
    assert.equal(assetsView(state), 'data');
  });

  test('un fallo posterior conserva el último listado, pero muestra el error', () => {
    let state = inventoryAssetsReducer(INITIAL_INVENTORY_ASSETS_STATE, { type: 'load_succeeded', assets: [asset()] });
    state = inventoryAssetsReducer(state, { type: 'load_failed', error: NETWORK });
    assert.equal(state.assets.length, 1);
    assert.equal(assetsView(state), 'error');
    // «Reintentar» vuelve a mostrar los datos mientras carga.
    state = inventoryAssetsReducer(state, { type: 'load_started' });
    assert.equal(assetsView(state), 'data');
  });
});

describe('listado de activos: sesión', () => {
  test('al activar carga una vez (también con StrictMode) y muestra los activos', async () => {
    const list = controllable();
    const { dispatch, state } = store();
    const session = createInventoryAssetsSession(dispatch, { listAssets: list.fn });
    session.activate();
    session.activate();
    assert.equal(list.calls.length, 1);
    list.calls[0].resolve([asset()]);
    await tick();
    assert.equal(assetsView(state()), 'data');
    assert.deepEqual(state().assets, [asset()]);
  });

  test('error del servicio → su uiError; error desconocido → unexpected_response', async () => {
    for (const [thrown, expected] of [
      [new InventoryServiceError({ kind: 'api_error', status: 503, code: 'storage_unavailable', detail: 'storage is temporarily unavailable', field: null }), { kind: 'api_error', status: 503, code: 'storage_unavailable', detail: 'storage is temporarily unavailable', field: null }],
      [new Error('boom'), { kind: 'unexpected_response' }],
    ]) {
      const list = controllable();
      const { dispatch, state } = store();
      createInventoryAssetsSession(dispatch, { listAssets: list.fn }).activate();
      list.calls[0].reject(thrown);
      await tick();
      assert.deepEqual(state().load, { status: 'error', error: expected });
    }
  });

  test('«Reintentar» tras un error vuelve a cargar', async () => {
    const list = controllable();
    const { dispatch, state } = store();
    const session = createInventoryAssetsSession(dispatch, { listAssets: list.fn });
    session.activate();
    list.calls[0].reject(new InventoryServiceError(NETWORK));
    await tick();
    assert.equal(assetsView(state()), 'error');
    void session.reload();
    assert.equal(list.calls.length, 2);
    list.calls[1].resolve([asset()]);
    await tick();
    assert.equal(assetsView(state()), 'data');
  });

  test('carrera: una carga nueva aborta la anterior y su respuesta tardía se descarta', async () => {
    const list = controllable();
    const { dispatch, state, actions } = store();
    const session = createInventoryAssetsSession(dispatch, { listAssets: list.fn });
    session.activate();
    void session.reload();
    assert.equal(list.calls.length, 2);
    assert.equal(list.calls[0].aborted, true);
    list.calls[1].resolve([asset({ id: 2, name: 'Second' })]);
    // Aunque la primera llegase después, no pisa la segunda.
    list.calls[0].resolve([asset({ id: 1, name: 'Stale' })]);
    await tick();
    assert.deepEqual(state().assets.map((item) => item.name), ['Second']);
    assert.equal(actions.filter((action) => action.type === 'load_failed').length, 0);
  });

  test('carrera: si el servicio ignora la cancelación, la respuesta antigua igualmente se descarta', async () => {
    const calls = [];
    const listAssets = () => new Promise((resolve) => calls.push(resolve));
    const { dispatch, state } = store();
    const session = createInventoryAssetsSession(dispatch, { listAssets });
    session.activate();
    void session.reload();
    calls[1]([asset({ id: 2, name: 'Second' })]);
    await tick();
    calls[0]([asset({ id: 1, name: 'Stale' })]);
    await tick();
    assert.deepEqual(state().assets.map((item) => item.name), ['Second']);
  });

  test('tras desmontar, ninguna respuesta se despacha y la carga se aborta', async () => {
    const list = controllable();
    const { dispatch, actions } = store();
    const session = createInventoryAssetsSession(dispatch, { listAssets: list.fn });
    session.activate();
    session.dispose();
    assert.equal(list.calls[0].aborted, true);
    list.calls[0].resolve([asset()]);
    await tick();
    assert.deepEqual(actions.map((action) => action.type), ['load_started']);
    void session.reload();
    assert.equal(list.calls.length, 1);
  });
});

describe('textos de error del inventario', () => {
  test('un 4xx/5xx con detail muestra el detail de la API bajo un título en español', () => {
    const stock = "Insufficient stock for asset 'Portátil 14\" Business'. Available: 13, requested: 20.";
    for (const [error, title] of [
      [{ kind: 'api_error', status: 400, code: 'insufficient_stock', detail: stock, field: 'quantity' }, 'No hay stock suficiente'],
      [{ kind: 'api_error', status: 400, code: 'office_mismatch', detail: 'order office does not match the asset office', field: null }, 'La oficina no coincide con la del activo'],
      [{ kind: 'api_error', status: 404, code: 'asset_not_found', detail: 'asset not found', field: null }, 'El activo no existe'],
      [{ kind: 'api_error', status: 409, code: 'sku_already_exists', detail: 'an asset with this sku already exists', field: null }, 'Ya existe un activo con ese SKU'],
      [{ kind: 'api_error', status: 500, code: 'internal_error', detail: 'internal server error', field: null }, 'Error del servidor'],
      [{ kind: 'api_error', status: 503, code: 'storage_unavailable', detail: 'storage is temporarily unavailable', field: null }, 'Error del servidor'],
      [{ kind: 'api_error', status: 400, code: null, detail: 'Bad things', field: null }, 'La API rechazó la operación'],
    ]) {
      assert.deepEqual(inventoryErrorCopy(error), { title, body: error.detail }, error.code ?? String(error.status));
    }
  });

  test('sin cuerpo legible: textos fijos, sin códigos HTTP ni detalles técnicos', () => {
    for (const kind of ['request_invalid', 'server_error', 'network', 'timeout', 'unexpected_response', 'config', 'session_expired']) {
      const { title, body } = inventoryErrorCopy({ kind });
      assert.ok(title.length > 0 && body.length > 0, kind);
      assert.doesNotMatch(`${title} ${body}`, /\d{3}|NEXT_PUBLIC_|services\/api|\{|\}/, kind);
    }
  });
});
