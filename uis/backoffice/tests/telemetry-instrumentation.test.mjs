// Instrumentación del backoffice (ticket de captura): los 4 obligatorios que
// emite el frontend con la respuesta de la API (lib/inventory-telemetry.ts),
// el embudo de formularios (lib/form-telemetry.ts) y `page_viewed`
// (lib/page-view-telemetry.ts). Cada evento se valida contra event-schemas.json.

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import { ApiAbortError } from '../lib/api-client.ts';
import { authFormOutcome, observeAuthOperation } from '../lib/auth-telemetry.ts';
import { createFormTelemetry } from '../lib/form-telemetry.ts';
import { inventoryFormOutcome, observeInventorySubmit, trackInboundOrder, trackOutboundOrder } from '../lib/inventory-telemetry.ts';
import { PAGE_VIEW_DWELL_MS, createPageViewTelemetry } from '../lib/page-view-telemetry.ts';
import { AuthServiceError } from '../services/auth.service.ts';
import { InventoryServiceError, parseUnitCost } from '../services/inventory.service.ts';
import { eventErrors } from './support/event-contract.mjs';
import { inboundOrderCreated, outboundOrderCreated } from './support/inventory-fakes.mjs';

/** Recoge los `track(eventType, properties)` y los envuelve como lo haría el servicio. */
function recorder() {
  const events = [];
  const emit = (event_type, properties) =>
    events.push({
      eventId: '7735fc60-41a3-44d8-83a6-35daa9f5353f',
      timestamp: '2026-11-03T10:00:00.000Z',
      sessionId: 'a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e',
      userId: '3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c',
      event_type,
      schemaVersion: '1.0.0',
      requestId: 'd3b44331-fd6b-4796-8798-0b6d0edd1bb3',
      properties,
    });
  return { emit, events, types: () => events.map((event) => event.event_type) };
}

function assertValid(events) {
  for (const event of events) assert.deepEqual(eventErrors(event), [], event.event_type);
}

describe('obligatorios de la salida (la API calcula, el frontend emite)', () => {
  test('una salida sin cruce: solo outbound_order_created, con los campos mínimos y sin PII', () => {
    const { emit, events, types } = recorder();
    trackOutboundOrder(outboundOrderCreated({ office: 'Miami', currency: 'USD', stock_before: 13, stock_after: 11 }), 'hardware', emit);
    assert.deepEqual(types(), ['outbound_order_created']);
    assert.deepEqual(events[0].properties, {
      office: 'miami',
      product_id: 1,
      product_category: null,
      programme_id: null,
      quantity: 2,
      currency: 'USD',
      asset_category: 'hardware',
      outbound_order_id: 1,
      exit_type: 'allocation',
      stock_after: 11,
    });
    assert.doesNotMatch(JSON.stringify(events), /Synthetic employee|Synthetic laptop/);
    assertValid(events);
  });

  test('cruzar el mínimo (>= antes, < después) añade stock_threshold_triggered', () => {
    const { emit, events, types } = recorder();
    trackOutboundOrder(outboundOrderCreated({ stock_before: 6, stock_after: 4, quantity: 2 }), 'training_materials', emit);
    assert.deepEqual(types(), ['outbound_order_created', 'stock_threshold_triggered']);
    assert.equal(events[1].properties.min_stock, 5);
    assertValid(events);
  });

  test('sin cruce no hay umbral: ya estaba por debajo, se queda en el mínimo o el mínimo es 0', () => {
    for (const order of [
      outboundOrderCreated({ stock_before: 4, stock_after: 3 }),
      outboundOrderCreated({ stock_before: 7, stock_after: 5 }),
      outboundOrderCreated({ stock_before: 1, stock_after: 0, min_stock: 0 }),
    ]) {
      const { emit, types } = recorder();
      trackOutboundOrder(order, 'hardware', emit);
      assert.deepEqual(types(), ['outbound_order_created']);
    }
  });

  test('sin categoría conocida del activo no se emite nada', () => {
    const { emit, events } = recorder();
    trackOutboundOrder(outboundOrderCreated(), undefined, emit);
    assert.equal(events.length, 0);
  });
});

describe('obligatorios de la entrada', () => {
  const variance = { reference_unit_cost: 18.5, variance_pct: 15.68, direction: 'increase', threshold_pct: 10, reference_window: 3 };

  test('inbound_order_created con coste, moneda y supplier_key; nunca el nombre del proveedor', () => {
    const { emit, events, types } = recorder();
    trackInboundOrder(inboundOrderCreated({ unit_cost: 21.4 }), 'hardware', emit);
    assert.deepEqual(types(), ['inbound_order_created']);
    assert.equal(events[0].properties.unit_cost, 21.4);
    assert.doesNotMatch(JSON.stringify(events), /Synthetic supplier/);
    assertValid(events);
  });

  test('con cost_variance de la API, además kit_cost_variance_detected', () => {
    const { emit, events, types } = recorder();
    trackInboundOrder(inboundOrderCreated({ office: 'Miami', currency: 'USD', unit_cost: 21.4, cost_variance: variance }), 'peripherals', emit);
    assert.deepEqual(types(), ['inbound_order_created', 'kit_cost_variance_detected']);
    assert.equal(events[1].properties.variance_pct, 15.68);
    assertValid(events);
  });

  test('sin supplier_key (API sin clave), sin coste o sin categoría no se emite', () => {
    for (const [order, category] of [
      [inboundOrderCreated({ supplier_key: null }), 'hardware'],
      [inboundOrderCreated({ unit_cost: null, currency: null }), 'hardware'],
      [inboundOrderCreated(), undefined],
    ]) {
      const { emit, events } = recorder();
      trackInboundOrder(order, category, emit);
      assert.equal(events.length, 0);
    }
  });
});

describe('embudo de formularios', () => {
  let clock;
  const funnel = (form = 'inbound_order') => {
    const { emit, events, types } = recorder();
    clock = 1_000;
    return { telemetry: createFormTelemetry(form, { track: emit, now: () => clock }), events, types };
  };

  test('form_started una vez, form_submitted con duración e intentos, y un éxito reinicia el embudo', () => {
    const { telemetry, events, types } = funnel();
    telemetry.fieldChanged('quantity');
    telemetry.fieldChanged('supplier');
    clock = 1_500;
    telemetry.submitted('api_rejected');
    clock = 4_250.4;
    telemetry.submitted('success');
    telemetry.fieldChanged('quantity');
    assert.deepEqual(types(), ['form_started', 'form_submitted', 'form_submitted', 'form_started']);
    assert.deepEqual(events[2].properties, { form: 'inbound_order', outcome: 'success', duration_ms: 3_250, attempt_number: 2 });
    assertValid(events);
  });

  test('form_abandoned con el último campo y lo que vio; nada si no empezó o tras un éxito', () => {
    const { telemetry, events, types } = funnel('outbound_order');
    telemetry.abandon();
    telemetry.fieldChanged('asset_id');
    telemetry.validationFailed(['quantity', 'quantity', 'exit_type', 'Not A Field']);
    telemetry.fieldChanged('quantity');
    clock = 9_000;
    telemetry.abandon();
    telemetry.abandon();
    assert.deepEqual(types(), ['form_started', 'form_validation_failed', 'form_abandoned']);
    assert.deepEqual(events[1].properties, { form: 'outbound_order', fields: ['quantity', 'exit_type'] });
    assert.deepEqual(events[2].properties, {
      form: 'outbound_order',
      last_field: 'quantity',
      had_validation_error: true,
      had_api_error: false,
      duration_ms: 8_000,
    });
    assertValid(events);
    telemetry.fieldChanged('quantity');
    telemetry.submitted('success');
    telemetry.abandon();
    assert.equal(types().at(-1), 'form_submitted');
  });

  test('el envío observado: validación en cliente, resultado por tipo de error y cancelación', async () => {
    const calls = [];
    const telemetry = { validationFailed: (fields) => calls.push(['validation', fields]), submitted: (outcome) => calls.push(['submitted', outcome]) };
    const created = [];
    const ok = observeInventorySubmit(async () => 'order', telemetry, (order, values) => created.push([order, values]));
    assert.equal(await ok('values'), 'order');
    const failWith = (error) => observeInventorySubmit(async () => { throw error; }, telemetry, () => {});
    const clientValidation = new InventoryServiceError({ kind: 'validation', source: 'client', errors: [{ field: 'unit_cost', message: 'x' }] });
    await assert.rejects(failWith(clientValidation)('v'), InventoryServiceError);
    await assert.rejects(failWith(new InventoryServiceError({ kind: 'api_error', status: 400, code: 'insufficient_stock', detail: 'd', field: 'quantity' }))('v'));
    await assert.rejects(failWith(new InventoryServiceError({ kind: 'network' }))('v'));
    await assert.rejects(failWith(new ApiAbortError())('v'), ApiAbortError);
    assert.deepEqual(created, [['order', 'values']]);
    assert.deepEqual(calls, [
      ['submitted', 'success'],
      ['validation', ['unit_cost']],
      ['submitted', 'api_rejected'],
      ['submitted', 'network_error'],
    ]);
  });

  test('outcome por tipo de error del servicio', () => {
    const cases = [
      [{ kind: 'validation', source: 'api', errors: [] }, 'validation_error'],
      [{ kind: 'api_error', status: 503, code: 'storage_unavailable', detail: 'd', field: null }, 'server_error'],
      [{ kind: 'request_invalid' }, 'api_rejected'],
      [{ kind: 'session_expired' }, 'session_expired'],
      [{ kind: 'timeout' }, 'network_error'],
      [{ kind: 'unexpected_response' }, 'server_error'],
    ];
    for (const [error, outcome] of cases) assert.equal(inventoryFormOutcome(error), outcome, error.kind);
  });
});

describe('page_viewed (1 s en la página)', () => {
  beforeEach(() => mock.timers.enable({ apis: ['setTimeout'] }));
  afterEach(() => mock.timers.reset());

  test('una redirección no cuenta; la página anterior y la entrada sí', () => {
    const { emit, events } = recorder();
    const views = createPageViewTelemetry(emit);
    views.navigated('/inventory');
    views.navigated('/inventory/products');
    mock.timers.tick(PAGE_VIEW_DWELL_MS);
    views.navigated('/reset-password?token=secreto');
    mock.timers.tick(PAGE_VIEW_DWELL_MS - 1);
    assert.equal(events.length, 1);
    mock.timers.tick(1);
    assert.deepEqual(
      events.map((event) => event.properties),
      [
        { route_template: '/inventory/products', previous_route_template: null, entry: 'initial_load' },
        { route_template: '/reset-password', previous_route_template: '/inventory/products', entry: 'in_app_navigation' },
      ]
    );
    assert.doesNotMatch(JSON.stringify(events), /secreto/);
    assertValid(events);
    assert.equal(views.previous(), '/reset-password');
  });

  test('una ruta desconocida (404) no cuenta como page_viewed y dispose cancela', () => {
    const { emit, events } = recorder();
    const views = createPageViewTelemetry(emit);
    views.navigated('/no-existe');
    views.navigated('/suppliers');
    views.dispose();
    mock.timers.tick(10 * PAGE_VIEW_DWELL_MS);
    assert.equal(events.length, 0);
  });
});

describe('coste unitario escrito por el usuario (P3)', () => {
  test('positivo, coma o punto, dos decimales como máximo y el tope de NUMERIC(12,2)', () => {
    assert.equal(parseUnitCost('18,50'), 18.5);
    assert.equal(parseUnitCost(' 21.4 '), 21.4);
    assert.equal(parseUnitCost('9999999999.99'), 9_999_999_999.99);
    for (const value of ['', '0', '0,00', '-1', '1.234', '1e3', 'abc', '10000000000', '1.000,50']) {
      assert.equal(parseUnitCost(value), null, value);
    }
  });
});

describe('embudo de los formularios de autenticación (D4)', () => {
  test('el fallo del login queda en form_submitted, sin el email ni la contraseña', async () => {
    const calls = [];
    const telemetry = { validationFailed: (fields) => calls.push(['validation', fields]), submitted: (outcome) => calls.push(['submitted', outcome]) };
    const failWith = (uiError) => observeAuthOperation(async () => { throw new AuthServiceError(uiError); }, telemetry);
    const credentials = { email: 'leak@example.invalid', password: 'secreta-123' };
    await observeAuthOperation(async () => {}, telemetry)(credentials, {});
    await assert.rejects(failWith({ kind: 'invalid_credentials' })(credentials, {}), AuthServiceError);
    await assert.rejects(failWith({ kind: 'network' })(credentials, {}), AuthServiceError);
    await assert.rejects(failWith({ kind: 'validation', source: 'client', errors: [{ field: 'email', message: 'x' }] })(credentials, {}));
    assert.deepEqual(calls, [
      ['submitted', 'success'],
      ['submitted', 'api_rejected'],
      ['submitted', 'network_error'],
      ['validation', ['email']],
    ]);
    assert.doesNotMatch(JSON.stringify(calls), /leak@example|secreta/);
  });

  test('outcome por tipo de error del servicio de autenticación', () => {
    const cases = [
      ['session_expired', 'session_expired'],
      ['invalid_reset_token', 'api_rejected'],
      ['timeout', 'network_error'],
      ['server_error', 'server_error'],
    ];
    for (const [kind, outcome] of cases) assert.equal(authFormOutcome({ kind }), outcome, kind);
  });
});
