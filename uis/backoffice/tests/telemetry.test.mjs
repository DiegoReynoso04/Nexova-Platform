// Tests de lib/telemetry.ts (TelemetryService; ticket de captura). Ejecutar desde uis/backoffice:
//   node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test "tests/*.test.mjs"
//
// Temporizadores falsos del runner nativo (`mock.timers`): lote a los 10 s o
// con 20 eventos, reintentos a 1, 2 y 4 s, beacon al ocultar la pestaña y el
// throttle de 60 s. Cada evento enviado se valida contra event-schemas.json.

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import { ApiNetworkError, ApiTimeoutError } from '../lib/api-client.ts';
import {
  FLUSH_INTERVAL_MS,
  MAX_BATCH_SIZE,
  THROTTLE_WINDOW_MS,
  apiRouteTemplate,
  createTelemetryService,
  elapsedMs,
  pageRouteTemplate,
  reportTransportFailure,
} from '../lib/telemetry.ts';
import { eventErrors } from './support/event-contract.mjs';

const USER_ID = '3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c';
const SESSION_ID = 'a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e';
const NOW = new Date('2026-11-03T10:15:42.318Z');
const PAGE = { route_template: '/inventory/products', previous_route_template: null, entry: 'initial_load' };

let uuidCounter = 0;
function fakeUUID() {
  uuidCounter += 1;
  return `00000000-0000-4000-8000-${String(uuidCounter).padStart(12, '0')}`;
}

/** Cliente falso: cada envío espera la respuesta que decida el test (`reply`). */
function fakeClient() {
  const sends = [];
  const beacons = [];
  const client = {
    postJson(path, body, options, handle) {
      return new Promise((resolve, reject) => {
        sends.push({
          path,
          body,
          options,
          reply: (status) => handle({ status }).then(resolve, reject),
          fail: (error) => reject(error),
        });
      });
    },
    beaconJson(path, body) {
      beacons.push({ path, body });
      return true;
    },
  };
  return { client, sends, beacons };
}

function makeService(overrides = {}) {
  const fake = fakeClient();
  const service = createTelemetryService({
    client: fake.client,
    isEnabled: () => true,
    getIdentity: () => ({ userId: USER_ID, sessionId: SESSION_ID }),
    randomUUID: fakeUUID,
    now: () => NOW,
    ...overrides,
  });
  return { service, ...fake };
}

const settle = () => new Promise((resolve) => queueMicrotask(resolve)).then(() => new Promise((resolve) => queueMicrotask(resolve)));

async function tick(ms) {
  mock.timers.tick(ms);
  await settle();
}

beforeEach(() => {
  uuidCounter = 0;
  mock.timers.enable({ apis: ['setTimeout'] });
});

afterEach(() => mock.timers.reset());

describe('envelope automático', () => {
  test('quien llama solo pasa properties: el servicio rellena las 8 claves y valida contra el contrato', async () => {
    const { service, sends } = makeService();
    service.track('page_viewed', PAGE);
    service.flush();
    assert.equal(sends.length, 1);
    const [event] = sends[0].body.events;
    assert.deepEqual(Object.keys(event), ['eventId', 'timestamp', 'sessionId', 'userId', 'event_type', 'schemaVersion', 'requestId', 'properties']);
    assert.equal(event.timestamp, '2026-11-03T10:15:42.318Z');
    assert.equal(event.userId, USER_ID);
    assert.equal(event.sessionId, SESSION_ID);
    assert.equal(event.schemaVersion, '1.0.0');
    assert.match(event.eventId, /^[0-9a-f-]{36}$/);
    assert.notEqual(event.requestId, event.eventId);
    assert.deepEqual(eventErrors(event), []);
  });

  test('el timestamp es el de la captura, no el del envío', async () => {
    let clock = new Date('2026-11-03T10:00:00.000Z');
    const { service, sends } = makeService({ now: () => clock });
    service.track('page_viewed', PAGE);
    clock = new Date('2026-11-03T10:00:09.999Z');
    await tick(FLUSH_INTERVAL_MS);
    assert.equal(sends[0].body.events[0].timestamp, '2026-11-03T10:00:00.000Z');
  });

  test('sin sesión, userId y sessionId van como null', () => {
    const { service, sends } = makeService({ getIdentity: () => ({ userId: null, sessionId: null }) });
    service.track('page_viewed', { ...PAGE, route_template: '/login' });
    service.flush();
    const [event] = sends[0].body.events;
    assert.equal(event.userId, null);
    assert.equal(event.sessionId, null);
    assert.deepEqual(eventErrors(event), []);
  });

  test('el requestId de una petición asociada se respeta', () => {
    const { service, sends } = makeService();
    service.track('form_started', { form: 'inbound_order' }, { requestId: '11111111-1111-4111-8111-111111111111' });
    service.flush();
    assert.equal(sends[0].body.events[0].requestId, '11111111-1111-4111-8111-111111111111');
  });

  test('una clave fuera de la allowlist no se envía', () => {
    const { service, sends } = makeService();
    service.track('form_started', { form: 'login', email: 'leak@example.invalid' });
    service.flush();
    assert.deepEqual(sends[0].body.events[0].properties, { form: 'login' });
  });

  test('sin endpoint configurado no encola ni envía nada', async () => {
    const { service, sends, beacons } = makeService({ isEnabled: () => false });
    service.track('page_viewed', PAGE);
    assert.equal(service.pendingCount(), 0);
    await tick(FLUSH_INTERVAL_MS);
    service.flushWithBeacon();
    assert.equal(sends.length + beacons.length, 0);
  });

  test('track nunca lanza, aunque falle la identidad', () => {
    const { service } = makeService({ getIdentity: () => { throw new Error('boom'); } });
    assert.doesNotThrow(() => service.track('page_viewed', PAGE));
  });
});

describe('cola y lotes (10 s / 20 eventos)', () => {
  test('un evento suelto sale a los 10 s, no antes', async () => {
    const { service, sends } = makeService();
    service.track('page_viewed', PAGE);
    await tick(FLUSH_INTERVAL_MS - 1);
    assert.equal(sends.length, 0);
    await tick(1);
    assert.equal(sends.length, 1);
    assert.equal(sends[0].body.events.length, 1);
  });

  test('al llegar a 20 eventos sale el lote sin esperar', () => {
    const { service, sends } = makeService();
    for (let index = 0; index < MAX_BATCH_SIZE - 1; index += 1) service.track('page_viewed', PAGE);
    assert.equal(sends.length, 0);
    service.track('page_viewed', PAGE);
    assert.equal(sends.length, 1);
    assert.equal(sends[0].body.events.length, MAX_BATCH_SIZE);
  });

  test('un envío lleva keepalive y no cierra la sesión ante un 401', () => {
    const { service, sends } = makeService();
    service.track('page_viewed', PAGE);
    service.flush();
    assert.equal(sends[0].path, '');
    assert.equal(sends[0].options.keepalive, true);
    assert.equal(sends[0].options.ignoreUnauthorized, true);
    assert.equal(sends[0].options.skipAuth, undefined);
  });

  test('un lote a la vez: lo que llega durante el envío espera al siguiente', async () => {
    const { service, sends } = makeService();
    service.track('page_viewed', PAGE);
    service.flush();
    service.track('form_started', { form: 'login' });
    service.flush();
    assert.equal(sends.length, 1);
    sends[0].reply(200);
    await settle();
    assert.equal(service.pendingCount(), 1);
    await tick(FLUSH_INTERVAL_MS);
    assert.equal(sends.length, 2);
    assert.equal(sends[1].body.events[0].event_type, 'form_started');
  });
});

describe('reintentos con backoff', () => {
  test('red caída: reintenta a 1, 2 y 4 s y después descarta el lote', async () => {
    const { service, sends } = makeService();
    service.track('page_viewed', PAGE);
    service.flush();
    sends[0].fail(new ApiNetworkError());
    await settle();
    for (const [index, delay] of [1_000, 2_000, 4_000].entries()) {
      await tick(delay - 1);
      assert.equal(sends.length, index + 1, `antes del reintento ${index + 1}`);
      await tick(1);
      assert.equal(sends.length, index + 2, `reintento ${index + 1}`);
      assert.deepEqual(sends[index + 1].body, sends[0].body);
      sends[index + 1].fail(new ApiTimeoutError());
      await settle();
    }
    await tick(60_000);
    assert.equal(sends.length, 4);
    assert.equal(service.pendingCount(), 0);
  });

  test('un 5xx o un 429 se reintentan y un éxito posterior termina el lote', async () => {
    for (const status of [503, 429]) {
      const { service, sends } = makeService();
      service.track('page_viewed', PAGE);
      service.flush();
      sends[0].reply(status);
      await settle();
      await tick(1_000);
      assert.equal(sends.length, 2, String(status));
      sends[1].reply(200);
      await settle();
      await tick(60_000);
      assert.equal(sends.length, 2, String(status));
    }
  });

  test('un 4xx (lote inválido, 401, 413) no se reintenta', async () => {
    for (const status of [400, 401, 413, 422]) {
      const { service, sends } = makeService();
      service.track('page_viewed', PAGE);
      service.flush();
      sends[0].reply(status);
      await settle();
      await tick(60_000);
      assert.equal(sends.length, 1, String(status));
    }
  });

  test('un error de configuración no se reintenta', async () => {
    const { service, sends } = makeService();
    service.track('page_viewed', PAGE);
    service.flush();
    const error = new Error('config');
    error.name = 'ApiConfigError';
    sends[0].fail(error);
    await settle();
    await tick(60_000);
    assert.equal(sends.length, 1);
  });
});

describe('sendBeacon al ocultar la pestaña', () => {
  test('lo pendiente sale por el beacon y la cola queda vacía', () => {
    const { service, sends, beacons } = makeService();
    service.track('page_viewed', PAGE);
    service.track('form_started', { form: 'outbound_order' });
    service.flushWithBeacon();
    assert.equal(sends.length, 0);
    assert.equal(beacons.length, 1);
    assert.equal(beacons[0].path, '');
    assert.equal(beacons[0].body.events.length, 2);
    for (const event of beacons[0].body.events) assert.deepEqual(eventErrors(event), []);
    assert.equal(service.pendingCount(), 0);
  });

  test('más de 20 pendientes van en varios beacons de 20 como máximo', () => {
    const { service, beacons, sends } = makeService();
    for (let index = 0; index < 45; index += 1) service.track('page_viewed', PAGE);
    // Los 20 primeros están en vuelo por fetch (keepalive) y los 25 restantes, en cola.
    service.flushWithBeacon();
    const beaconed = beacons.reduce((total, beacon) => total + beacon.body.events.length, 0);
    assert.ok(beacons.every((beacon) => beacon.body.events.length <= MAX_BATCH_SIZE));
    assert.equal(beaconed + sends[0].body.events.length, 45);
  });

  test('un lote esperando su reintento sale por el beacon y no se reintenta después', async () => {
    const { service, sends, beacons } = makeService();
    service.track('page_viewed', PAGE);
    service.flush();
    sends[0].fail(new ApiNetworkError());
    await settle();
    service.track('form_started', { form: 'login' });
    service.flushWithBeacon();
    assert.equal(beacons[0].body.events.length, 2);
    await tick(60_000);
    assert.equal(sends.length, 1);
  });

  test('sin nada pendiente no hay beacon', () => {
    const { service, beacons } = makeService();
    service.flushWithBeacon();
    assert.equal(beacons.length, 0);
  });
});

describe('throttle de pestaña (60 s por clave)', () => {
  const failure = (suppressed) => ({
    kind: 'network',
    http_method: 'GET',
    api_route_template: '/inventory/products',
    timeout_ms: null,
    suppressed_count: suppressed,
  });

  test('el primero sale, los demás se cuentan y el último sale al cerrar la ventana', async () => {
    const { service, sends } = makeService();
    for (let index = 0; index < 4; index += 1) service.trackThrottled('network:/inventory/products', 'client_request_failed', failure);
    service.flush();
    sends[0].reply(200);
    await settle();
    const first = sends[0].body.events;
    assert.equal(first.length, 1);
    assert.equal(first[0].properties.suppressed_count, 0);
    await tick(THROTTLE_WINDOW_MS);
    service.flush();
    const last = sends[1].body.events;
    assert.equal(last.length, 1);
    assert.equal(last[0].properties.suppressed_count, 3);
    for (const event of [...first, ...last]) assert.deepEqual(eventErrors(event), []);
  });

  test('claves distintas no se pisan', () => {
    const { service, sends } = makeService();
    service.trackThrottled('a', 'client_request_failed', failure);
    service.trackThrottled('b', 'client_request_failed', failure);
    service.flush();
    assert.equal(sends[0].body.events.length, 2);
  });

  test('un fallo de transporte se convierte en client_request_failed con la plantilla, nunca el path real', () => {
    const { service, sends } = makeService();
    reportTransportFailure({ kind: 'timeout', method: 'GET', path: '/inventory/products/42?x=1', timeoutMs: 8_000 }, service);
    reportTransportFailure({ kind: 'network', method: 'POST', path: '/no/es/una/ruta', timeoutMs: null }, service);
    service.flush();
    const events = sends[0].body.events;
    assert.equal(events.length, 1);
    assert.deepEqual(events[0].properties, {
      kind: 'timeout',
      http_method: 'GET',
      api_route_template: '/inventory/products/{id}',
      timeout_ms: 8_000,
      suppressed_count: 0,
    });
    assert.deepEqual(eventErrors(events[0]), []);
  });
});

describe('plantillas de ruta y duraciones', () => {
  test('páginas: solo las del plan, sin query string ni barra final', () => {
    assert.equal(pageRouteTemplate('/inventory/products'), '/inventory/products');
    assert.equal(pageRouteTemplate('/inventory/products/'), '/inventory/products');
    assert.equal(pageRouteTemplate('/reset-password?token=secreto'), '/reset-password');
    assert.equal(pageRouteTemplate('/'), '/');
    assert.equal(pageRouteTemplate('/no-existe'), null);
  });

  test('API: ids y UUID → plantilla; las rutas literales ganan', () => {
    const uuid = 'a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e';
    assert.equal(apiRouteTemplate('/inventory/products/7'), '/inventory/products/{id}');
    assert.equal(apiRouteTemplate('/api/incidents/summary'), '/api/incidents/summary');
    assert.equal(apiRouteTemplate(`/api/incidents/${uuid}/status`), '/api/incidents/{incident_id}/status');
    assert.equal(apiRouteTemplate('/suppliers/3/rate'), '/suppliers/{supplier_id}/rate');
    assert.equal(apiRouteTemplate('/suppliers?status=active'), '/suppliers');
    assert.equal(apiRouteTemplate('/inventory/orders/inbound'), '/inventory/orders/inbound');
    assert.equal(apiRouteTemplate(''), null);
  });

  test('elapsedMs: entero, no negativo y acotado', () => {
    assert.equal(elapsedMs(100, 350.6, 1_000), 251);
    assert.equal(elapsedMs(500, 100, 1_000), 0);
    assert.equal(elapsedMs(0, 5_000, 1_000), 1_000);
  });
});
