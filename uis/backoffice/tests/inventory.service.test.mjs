// Inventario (Hito 5): normalizadores (services/normalizers.ts), cliente del
// inventario (lib/inventory-api-client.ts) y servicio
// (services/inventory.service.ts), con el cliente real y un transporte falso.

import assert from 'node:assert/strict';
import { after, afterEach, before, beforeEach, describe, test } from 'node:test';

import { ApiAbortError, createApiClient } from '../lib/api-client.ts';
import { INVENTORY_BASE_URL_VARIABLE, createInventoryApiClient } from '../lib/inventory-api-client.ts';
import {
  InventoryServiceError,
  buildInboundPayload,
  buildOutboundPayload,
  createInventoryService,
} from '../services/inventory.service.ts';
import {
  UnexpectedResponseError,
  normalizeAsset,
  normalizeAssetList,
  normalizeInboundOrder,
  normalizeInventoryValidationErrors,
  normalizeOrderList,
  normalizeOutboundOrder,
} from '../services/normalizers.ts';
import { BASE_URL, LEAK, hangingFetch, jsonResponse, offlineFetch, recordingFetch, textResponse } from './support/http-fakes.mjs';
import {
  asset,
  errorBody,
  inboundOrder,
  inboundValues,
  outboundOrder,
  outboundValues,
  selected,
} from './support/inventory-fakes.mjs';
import { validationBody } from './support/supplier-fakes.mjs';

const TOKEN = 'synthetic-session-token';
const LITERAL_STOCK_MESSAGE = "Insufficient stock for asset 'Portátil 14\" Business'. Available: 13, requested: 20.";

// El cliente real del inventario (lib/inventory-api-client.ts), con la variable
// fijada para todo el archivo: así los tests cubren también de dónde sale la
// URL y que el Bearer llega a cada petición.
const savedInventoryUrl = process.env[INVENTORY_BASE_URL_VARIABLE];
before(() => {
  process.env[INVENTORY_BASE_URL_VARIABLE] = BASE_URL;
});
after(() => {
  if (savedInventoryUrl === undefined) delete process.env[INVENTORY_BASE_URL_VARIABLE];
  else process.env[INVENTORY_BASE_URL_VARIABLE] = savedInventoryUrl;
});

function serviceWith(makeResponse) {
  const transport = recordingFetch(makeResponse);
  const client = createInventoryApiClient({ fetch: transport.fetch, getToken: () => TOKEN });
  return { service: createInventoryService({ client, timeoutMs: 1_000 }), transport };
}

function expectUiError(expected) {
  return (error) => {
    assert.ok(error instanceof InventoryServiceError, `expected InventoryServiceError, got ${error?.name}`);
    assert.deepEqual(error.uiError, expected);
    return true;
  };
}

function sentJson(call) {
  return JSON.parse(call.init.body);
}

/** Las cinco operaciones, cada una con una respuesta correcta. */
const OPERATIONS = [
  ['listAssets', (service) => service.listAssets(), () => jsonResponse(200, [asset()])],
  ['getAsset', (service) => service.getAsset(1), () => jsonResponse(200, asset())],
  ['createInboundOrder', (service) => service.createInboundOrder(inboundValues()), () => jsonResponse(201, inboundOrder())],
  ['createOutboundOrder', (service) => service.createOutboundOrder(outboundValues()), () => jsonResponse(201, outboundOrder())],
  ['listOrders', (service) => service.listOrders(), () => jsonResponse(200, [inboundOrder(), outboundOrder()])],
];

describe('normalizadores del inventario', () => {
  test('activo: whitelist de campos', () => {
    const input = { ...asset(), extra: 'ignored' };
    const { extra, ...expected } = input;
    assert.equal(extra, 'ignored');
    assert.deepEqual(normalizeAsset(input), expected);
    assert.deepEqual(normalizeAssetList([asset(), asset({ id: 2 })]).map((item) => item.id), [1, 2]);
    assert.deepEqual(normalizeAssetList([]), []);
    assert.throws(() => normalizeAssetList({}), UnexpectedResponseError);
  });

  test('activo fuera del contrato se rechaza', () => {
    for (const bad of [
      { category: 'furniture' },
      { office: 'Madrid' },
      { office: 'valencia' },
      { current_stock: '13' },
      { current_stock: 1.5 },
      { id: null },
      { name: 3 },
    ]) {
      assert.throws(() => normalizeAsset(asset(bad)), UnexpectedResponseError, JSON.stringify(bad));
    }
  });

  test('entradas y salidas, distinguidas por type', () => {
    const input = { ...inboundOrder(), extra: LEAK, asset: { ...inboundOrder().asset, extra: LEAK } };
    const inbound = normalizeInboundOrder(input);
    assert.deepEqual(inbound, inboundOrder());
    assert.equal(JSON.stringify(inbound).includes(LEAK), false);
    assert.deepEqual(normalizeOutboundOrder(outboundOrder()), outboundOrder());
    assert.deepEqual(normalizeOutboundOrder(outboundOrder({ exit_type: 'consumption', assigned_to: null })).assigned_to, null);
    const listed = normalizeOrderList([outboundOrder(), inboundOrder()]);
    assert.deepEqual(listed.map((order) => order.type), ['outbound', 'inbound']);
    assert.equal('supplier' in listed[0], false);
    assert.equal('exit_type' in listed[1], false);
  });

  test('órdenes fuera del contrato se rechazan', () => {
    for (const bad of [
      inboundOrder({ type: 'transfer' }),
      inboundOrder({ type: undefined }),
      inboundOrder({ supplier: null }),
      inboundOrder({ created_at: 1 }),
      inboundOrder({ user_uuid: null }),
      inboundOrder({ asset: null }),
      inboundOrder({ asset: { id: 1, name: 'x' } }),
      outboundOrder({ exit_type: 'loss' }),
      outboundOrder({ assigned_to: 3 }),
      outboundOrder({ quantity: '2' }),
    ]) {
      assert.throws(() => normalizeOrderList([bad]), UnexpectedResponseError, JSON.stringify(bad));
    }
    assert.throws(() => normalizeInboundOrder(outboundOrder()), UnexpectedResponseError);
    assert.throws(() => normalizeOutboundOrder(inboundOrder()), UnexpectedResponseError);
    assert.throws(() => normalizeOrderList({}), UnexpectedResponseError);
  });

  test('los errores del normalizador no contienen valores recibidos', () => {
    try {
      normalizeAsset(asset({ office: LEAK }));
      assert.fail('should throw');
    } catch (error) {
      assert.equal(error.message.includes(LEAK), false);
    }
  });

  test('422: solo el campo de cada error, nunca el msg de la API', () => {
    const body = validationBody([['body', 'assigned_to'], LEAK], [['body', 'quantity'], 'x'], [['body'], 'y'], [['query', 'x'], 'z']);
    assert.deepEqual(normalizeInventoryValidationErrors(body), ['assigned_to', 'quantity', null, null]);
    assert.deepEqual(normalizeInventoryValidationErrors({}), []);
    assert.deepEqual(normalizeInventoryValidationErrors(null), []);
  });
});

describe('cliente del inventario: NEXT_PUBLIC_INVENTORY_API_URL, sin reserva', () => {
  const saved = {};

  beforeEach(() => {
    for (const name of ['NEXT_PUBLIC_API_URL', INVENTORY_BASE_URL_VARIABLE]) saved[name] = process.env[name];
  });

  afterEach(() => {
    for (const [name, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  });

  test('usa la variable del inventario y le añade /inventory/...', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'http://other-api.test';
    process.env[INVENTORY_BASE_URL_VARIABLE] = 'http://inventory-api.test/';
    const transport = recordingFetch(() => jsonResponse(200, [asset()]));
    const service = createInventoryService({ client: createInventoryApiClient({ fetch: transport.fetch, getToken: () => TOKEN }) });
    await service.listAssets();
    assert.equal(transport.calls[0].url, 'http://inventory-api.test/inventory/products');
  });

  test('si falta, error de configuración aunque NEXT_PUBLIC_API_URL exista (y ninguna petición)', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'http://other-api.test';
    for (const value of [undefined, '', '   ']) {
      if (value === undefined) delete process.env[INVENTORY_BASE_URL_VARIABLE];
      else process.env[INVENTORY_BASE_URL_VARIABLE] = value;
      const transport = recordingFetch(() => jsonResponse(200, [asset()]));
      const service = createInventoryService({ client: createInventoryApiClient({ fetch: transport.fetch, getToken: () => TOKEN }) });
      await assert.rejects(service.listAssets(), expectUiError({ kind: 'config' }));
      assert.equal(transport.calls.length, 0);
    }
  });
});

describe('servicio del inventario: peticiones', () => {
  for (const [name, call, respond] of OPERATIONS) {
    test(`${name} lleva Authorization: Bearer`, async () => {
      const { service, transport } = serviceWith(respond);
      await call(service);
      assert.equal(transport.calls.length, 1);
      assert.equal(transport.calls[0].init.headers.Authorization, `Bearer ${TOKEN}`);
    });
  }

  test('rutas y métodos', async () => {
    const seen = [];
    for (const [, call, respond] of OPERATIONS) {
      const { service, transport } = serviceWith(respond);
      await call(service);
      seen.push(`${transport.calls[0].init.method} ${transport.calls[0].url.replace(BASE_URL, '')}`);
    }
    assert.deepEqual(seen, [
      'GET /inventory/products',
      'GET /inventory/products/1',
      'POST /inventory/orders/inbound',
      'POST /inventory/orders/outbound',
      'GET /inventory/orders',
    ]);
  });

  test('entrada: números, proveedor recortado y la oficina del activo', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(201, inboundOrder({ office: 'Miami' })));
    const values = inboundValues({ asset: selected({ id: 4, office: 'Miami' }), quantity: ' 8 ', supplier: '  Office Depot Miami ' });
    const order = await service.createInboundOrder(values);
    assert.equal(order.type, 'inbound');
    const body = sentJson(transport.calls[0]);
    assert.deepEqual(body, { asset_id: 4, quantity: 8, supplier: 'Office Depot Miami', office: 'Miami' });
    assert.equal(typeof body.asset_id, 'number');
    assert.equal(typeof body.quantity, 'number');
  });

  test('salida: allocation con assigned_to recortado; consumption con null', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(201, outboundOrder()));
    await service.createOutboundOrder(outboundValues({ quantity: '3', assigned_to: '  EMPLEADO-FICTICIO-01 ' }));
    await service.createOutboundOrder(
      outboundValues({ asset: selected({ id: 4, office: 'Miami' }), exit_type: 'consumption', assigned_to: 'ignored' })
    );
    assert.deepEqual(sentJson(transport.calls[0]), {
      asset_id: 1,
      quantity: 3,
      exit_type: 'allocation',
      assigned_to: 'EMPLEADO-FICTICIO-01',
      office: 'Valencia',
    });
    assert.deepEqual(sentJson(transport.calls[1]), {
      asset_id: 4,
      quantity: 2,
      exit_type: 'consumption',
      assigned_to: null,
      office: 'Miami',
    });
  });

  test('el body nunca lleva user_uuid ni current_stock', () => {
    for (const body of [
      buildInboundPayload(selected(), 1, 'x'),
      buildOutboundPayload(selected(), 1, 'allocation', 'x'),
      buildOutboundPayload(selected(), 1, 'consumption', 'x'),
    ]) {
      assert.deepEqual(Object.keys(body).filter((key) => ['user_uuid', 'current_stock', 'id'].includes(key)), []);
    }
  });

  test('validación en cliente: sin petición y con los errores por campo', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(201, inboundOrder()));
    await assert.rejects(
      service.createInboundOrder(inboundValues({ asset: null, quantity: '0', supplier: '  ' })),
      (error) => {
        assert.equal(error.uiError.kind, 'validation');
        assert.equal(error.uiError.source, 'client');
        assert.deepEqual(error.uiError.errors.map((item) => item.field), ['asset_id', 'quantity', 'supplier']);
        return true;
      }
    );
    await assert.rejects(service.createOutboundOrder(outboundValues({ exit_type: 'allocation', assigned_to: ' ' })), (error) => {
      assert.deepEqual(error.uiError.errors.map((item) => item.field), ['assigned_to']);
      return true;
    });
    await assert.rejects(service.createOutboundOrder(outboundValues({ exit_type: '' })), (error) => {
      assert.deepEqual(error.uiError.errors.map((item) => item.field), ['exit_type']);
      return true;
    });
    assert.equal(transport.calls.length, 0);
  });
});

describe('servicio del inventario: errores', () => {
  test('400 insufficient_stock: el detail de la API, junto a la cantidad', async () => {
    const { service } = serviceWith(() => jsonResponse(400, errorBody('insufficient_stock', LITERAL_STOCK_MESSAGE)));
    await assert.rejects(
      service.createOutboundOrder(outboundValues({ quantity: '20' })),
      expectUiError({ kind: 'api_error', status: 400, code: 'insufficient_stock', detail: LITERAL_STOCK_MESSAGE, field: 'quantity' })
    );
  });

  test('400 office_mismatch, 404 y 409: el detail, sin campo', async () => {
    for (const [status, code, detail] of [
      [400, 'office_mismatch', 'order office does not match the asset office'],
      [404, 'asset_not_found', 'asset not found'],
      [409, 'sku_already_exists', 'an asset with this sku already exists'],
    ]) {
      const { service } = serviceWith(() => jsonResponse(status, errorBody(code, detail)));
      await assert.rejects(service.createInboundOrder(inboundValues()), expectUiError({ kind: 'api_error', status, code, detail, field: null }));
    }
  });

  test('500 y 503 con detail: el detail de la API, visible', async () => {
    for (const [status, code, detail] of [
      [500, 'internal_error', 'internal server error'],
      [503, 'storage_unavailable', 'storage is temporarily unavailable'],
    ]) {
      const { service } = serviceWith(() => jsonResponse(status, errorBody(code, detail)));
      await assert.rejects(service.listAssets(), expectUiError({ kind: 'api_error', status, code, detail, field: null }));
    }
  });

  test('sin cuerpo legible → textos fijos', async () => {
    for (const [status, respond, kind] of [
      [500, () => textResponse(500, `<html>${LEAK}</html>`), 'server_error'],
      [502, () => new Response(null, { status: 502 }), 'server_error'],
      [400, () => textResponse(400, LEAK), 'request_invalid'],
      [500, () => jsonResponse(500, { detail: { message: LEAK }, code: 'x' }), 'server_error'],
      [400, () => jsonResponse(400, { detail: [LEAK], code: 'x' }), 'request_invalid'],
      [404, () => jsonResponse(404, { detail: '   ', code: 'x' }), 'request_invalid'],
      [500, () => jsonResponse(500, [LEAK]), 'server_error'],
    ]) {
      const { service } = serviceWith(respond);
      await assert.rejects(service.listOrders(), expectUiError({ kind }), `${status} ${kind}`);
    }
  });

  test('un detail sin code se muestra igualmente, con code null', async () => {
    const { service } = serviceWith(() => jsonResponse(400, { detail: 'Bad things' }));
    await assert.rejects(service.listAssets(), expectUiError({ kind: 'api_error', status: 400, code: null, detail: 'Bad things', field: null }));
  });

  test('422: texto propio en español por campo, sin el msg de la API', async () => {
    const { service } = serviceWith(() =>
      jsonResponse(422, validationBody([['body', 'assigned_to'], LEAK], [['body', 'quantity'], LEAK], [['body', 'quantity'], LEAK]))
    );
    await assert.rejects(service.createOutboundOrder(outboundValues()), (error) => {
      const { uiError } = error;
      assert.equal(uiError.kind, 'validation');
      assert.equal(uiError.source, 'api');
      assert.deepEqual(uiError.errors.map((item) => item.field), ['assigned_to', 'quantity']);
      assert.match(uiError.errors[0].message, /^Indica a quién se asigna/);
      assert.equal(JSON.stringify(uiError).includes(LEAK), false);
      return true;
    });
  });

  test('422 de assigned_to en un consumo: el texto del consumo', async () => {
    const { service } = serviceWith(() => jsonResponse(422, validationBody([['body', 'assigned_to'], 'x'])));
    await assert.rejects(service.createOutboundOrder(outboundValues({ exit_type: 'consumption' })), (error) => {
      assert.equal(error.uiError.errors[0].message, 'En un consumo no se indica a quién se asigna.');
      return true;
    });
  });

  test('422 sin errores legibles → request_invalid', async () => {
    const { service } = serviceWith(() => textResponse(422, LEAK));
    await assert.rejects(service.createInboundOrder(inboundValues()), expectUiError({ kind: 'request_invalid' }));
  });

  test('401 → session_expired (el token ya se borró)', async () => {
    let cleared = 0;
    const transport = recordingFetch(() => jsonResponse(401, errorBody('not_authenticated', 'could not validate credentials')));
    const client = createApiClient({
      fetch: transport.fetch,
      getBaseUrl: () => BASE_URL,
      getToken: () => TOKEN,
      onUnauthorized: () => {
        cleared += 1;
      },
    });
    await assert.rejects(createInventoryService({ client }).listAssets(), expectUiError({ kind: 'session_expired' }));
    assert.equal(cleared, 1);
  });

  test('red, timeout, respuesta fuera de contrato y cancelación', async () => {
    const offline = createInventoryService({ client: createApiClient({ fetch: offlineFetch(), getBaseUrl: () => BASE_URL }) });
    await assert.rejects(offline.listAssets(), expectUiError({ kind: 'network' }));

    const slow = createInventoryService({ client: createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL }), timeoutMs: 20 });
    await assert.rejects(slow.listAssets(), expectUiError({ kind: 'timeout' }));

    const { service } = serviceWith(() => jsonResponse(200, [asset({ office: 'Madrid' })]));
    await assert.rejects(service.listAssets(), expectUiError({ kind: 'unexpected_response' }));

    const { service: wrongStatus } = serviceWith(() => jsonResponse(200, inboundOrder()));
    await assert.rejects(wrongStatus.createInboundOrder(inboundValues()), expectUiError({ kind: 'unexpected_response' }));

    const hanging = createInventoryService({ client: createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL }) });
    const controller = new AbortController();
    const pending = hanging.getAsset(1, { signal: controller.signal });
    controller.abort();
    await assert.rejects(pending, ApiAbortError);
  });

  test('ningún error del servicio lleva datos de la respuesta en su mensaje', async () => {
    const { service } = serviceWith(() => jsonResponse(400, errorBody('insufficient_stock', LEAK)));
    await assert.rejects(service.createOutboundOrder(outboundValues()), (error) => {
      assert.equal(error.message.includes(LEAK), false);
      return true;
    });
  });
});
