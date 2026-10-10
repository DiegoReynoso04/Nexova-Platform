// Auditoría de gestión de errores (T2, T3, T4 y T6): textos fijos por tipo de
// error, timeout que cubre la lectura del cuerpo, clasificación del error al
// guardar una candidatura y reintento del guard con carga. Runner nativo de
// Node 24, sin dependencias. Desde uis/talent-pipeline-tracker:
//   node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test "tests/*.test.mjs"

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

// lib/api-client.ts exige ambas URLs al cargarse (SPECS.md §3.2 y §9).
process.env.NEXT_PUBLIC_API_URL = 'https://candidates.test/tracker/api/v1';
process.env.NEXT_PUBLIC_AUTH_API_URL = 'http://auth.test';

const {
  API_ERROR_MESSAGES,
  ApiError,
  NetworkError,
  NotFoundError,
  ResponseShapeError,
  TimeoutError,
  UnauthorizedError,
  UnknownClientError,
  UnreadableResponseError,
  ValidationApiError,
  apiClient,
  asError,
  classifyApiError,
  describeApiError,
} = await import('../lib/api-client.ts');
const { SAVED_BUT_UNREADABLE_MESSAGE, UNCERTAIN_OUTCOME_MESSAGE, classifySubmitError } = await import(
  '../lib/submit-error.ts'
);
const { createRecord } = await import('../services/records.service.ts');
const { normalizeRecord } = await import('../services/normalizers.ts');
const { createAuthSessionController, deriveSessionStatus, sessionErrorCopy } = await import(
  '../hooks/use-auth-session.ts'
);
const { routeAccess } = await import('../lib/auth-routes.ts');

const RECORD = {
  id: 'r-1',
  full_name: 'Ana Pérez',
  email: 'ana@example.invalid',
  phone: '600000000',
  position: 'Recruiter',
  linkedin_url: null,
  cv_url: null,
  status: 'received',
  stage: 'screening',
  experience_years: 3,
  applied_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
};
const RECORD_BODY = {
  full_name: 'Ana Pérez',
  email: 'ana@example.invalid',
  phone: '600000000',
  position: 'Recruiter',
  linkedin_url: null,
  cv_url: null,
  experience_years: 3,
};
// Lo que nunca puede aparecer en un texto para el usuario.
const TECHNICAL = /\b[1-5]\d\d\b|se esperaba|records\.|\.email|Error:|undefined|null|\[object/;

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

let respond;
beforeEach(() => {
  respond = () => jsonResponse(200, {});
  globalThis.fetch = async (url, init) => respond(url, init);
});

afterEach(() => {
  mock.timers.reset();
});

describe('cliente HTTP: timeout y errores sin el código HTTP', () => {
  test('un cuerpo que no termina de llegar acaba en TimeoutError (el timeout cubre response.json())', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    // El fetch responde enseguida, pero el cuerpo se queda colgado hasta que se aborta la petición.
    respond = (_url, init) =>
      new Response(
        new ReadableStream({
          start(controller) {
            init.signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')));
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    const pending = apiClient.get('/records').catch((error) => error);
    await tick();
    await tick();
    mock.timers.tick(20_000);
    const error = await pending;
    assert.ok(error instanceof TimeoutError, `se esperaba TimeoutError, llegó ${error?.name}`);
    assert.equal(describeApiError(error), API_ERROR_MESSAGES.timeout);
  });

  test('un fetch que no responde sigue acabando en TimeoutError', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    respond = (_url, init) =>
      new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
    const pending = apiClient.get('/records').catch((error) => error);
    await tick();
    mock.timers.tick(20_000);
    assert.ok((await pending) instanceof TimeoutError);
  });

  test('ningún error HTTP lleva el código en su mensaje ni en el texto para el usuario', async () => {
    for (const status of [400, 403, 405, 409, 429, 500, 502, 503]) {
      respond = () => jsonResponse(status, { detail: `fallo ${status} con leak@example.invalid` });
      const error = await apiClient.get('/records').catch((caught) => caught);
      assert.ok(error instanceof ApiError, String(status));
      assert.equal(error.status, status);
      assert.doesNotMatch(error.message, /\d{3}/, `${status}: ${error.message}`);
      const text = describeApiError(error);
      assert.doesNotMatch(text, TECHNICAL, `${status}: ${text}`);
      assert.equal(text, status >= 500 ? API_ERROR_MESSAGES.server : API_ERROR_MESSAGES.client);
    }
  });

  test('2xx con un cuerpo que no es JSON → UnreadableResponseError con su status', async () => {
    respond = () => new Response('<html>no json</html>', { status: 201 });
    const error = await apiClient.post('/records', {}).catch((caught) => caught);
    assert.ok(error instanceof UnreadableResponseError);
    assert.equal(error.status, 201);
    assert.equal(describeApiError(error), API_ERROR_MESSAGES.unreadable);
  });
});

describe('describeApiError: un texto fijo por tipo de error', () => {
  const cases = [
    ['network', new NetworkError(new TypeError('Failed to fetch'))],
    ['timeout', new TimeoutError()],
    ['unauthorized', new UnauthorizedError()],
    ['not_found', new NotFoundError()],
    ['client', new ApiError('x', 409)],
    ['server', new ApiError('x', 500)],
    ['unreadable', new UnreadableResponseError(200)],
    ['unknown', new UnknownClientError()],
  ];

  test('cada tipo se clasifica y tiene su propio texto', () => {
    for (const [kind, error] of cases) {
      assert.equal(classifyApiError(error), kind, kind);
      assert.equal(describeApiError(error), API_ERROR_MESSAGES[kind], kind);
    }
    const texts = cases.map(([kind]) => API_ERROR_MESSAGES[kind]);
    assert.equal(new Set(texts).size, texts.length, 'textos distintos');
  });

  test('ningún texto incluye dígitos de estado, rutas de normalizador ni «Error:»', () => {
    for (const text of Object.values(API_ERROR_MESSAGES)) assert.doesNotMatch(text, TECHNICAL, text);
  });

  test('el mensaje descriptivo de un normalizador nunca llega al usuario', () => {
    const error = (() => {
      try {
        normalizeRecord({ ...RECORD, email: 42 });
      } catch (caught) {
        return caught;
      }
    })();
    assert.ok(error instanceof ResponseShapeError);
    assert.match(error.message, /se esperaba/, 'el mensaje sigue siendo descriptivo para depurar');
    assert.equal(describeApiError(error), API_ERROR_MESSAGES.unreadable);
  });

  test('un valor lanzado que no es Error no se convierte en texto', () => {
    const error = asError('leak@example.invalid');
    assert.ok(error instanceof UnknownClientError);
    assert.equal(describeApiError(error), API_ERROR_MESSAGES.unknown);
    assert.doesNotMatch(error.message, /leak/);
    const original = new NotFoundError();
    assert.equal(asError(original), original, 'conserva la clase del error');
  });

  test('el 422 sigue mostrando los msg de la API (§5.4)', () => {
    const error = new ValidationApiError([{ loc: ['body', 'email'], msg: 'value is not a valid email address', type: 'value_error' }]);
    assert.equal(describeApiError(error), 'value is not a valid email address');
  });
});

describe('T4: clasificación del error al guardar una candidatura', () => {
  test('cada caso tiene su resultado', () => {
    const validation = new ValidationApiError([{ loc: ['body', 'email'], msg: 'm', type: 't' }]);
    assert.deepEqual(classifySubmitError(validation), { kind: 'validation', detail: validation.detail });
    for (const saved of [new ResponseShapeError('records.id: se esperaba string'), new UnreadableResponseError(201), new UnreadableResponseError(200)]) {
      assert.deepEqual(classifySubmitError(saved), { kind: 'saved_unreadable', message: SAVED_BUT_UNREADABLE_MESSAGE }, saved.name);
    }
    assert.deepEqual(classifySubmitError(new TimeoutError()), { kind: 'uncertain', message: UNCERTAIN_OUTCOME_MESSAGE });
    const notSaved = [
      [new NetworkError(new TypeError('x')), API_ERROR_MESSAGES.network],
      [new UnreadableResponseError(500), API_ERROR_MESSAGES.unreadable],
      [new ApiError('x', 500), API_ERROR_MESSAGES.server],
      [new ApiError('x', 400), API_ERROR_MESSAGES.client],
      [new UnknownClientError(), API_ERROR_MESSAGES.unknown],
    ];
    for (const [error, message] of notSaved) {
      assert.deepEqual(classifySubmitError(error), { kind: 'not_saved', message }, error.name);
    }
  });

  test('POST 201 con JSON ilegible o fuera de contrato → «se guardó»; red caída → no se guardó', async () => {
    const outcomeOf = async () => classifySubmitError(await createRecord(RECORD_BODY).then(() => assert.fail('debía fallar'), asError));
    respond = () => new Response('{"id": "r-1", "full_na', { status: 201, headers: { 'content-type': 'application/json' } });
    assert.equal((await outcomeOf()).kind, 'saved_unreadable');
    respond = () => jsonResponse(201, { ...RECORD, email: 42 });
    assert.equal((await outcomeOf()).kind, 'saved_unreadable');
    respond = () => {
      throw new TypeError('Failed to fetch');
    };
    assert.deepEqual(await outcomeOf(), { kind: 'not_saved', message: API_ERROR_MESSAGES.network });
  });
});

describe('T6: reintento del guard con carga y texto por tipo de error', () => {
  function harness() {
    const states = [];
    let next = () => Promise.reject(new NetworkError(new TypeError('x')));
    const controller = createAuthSessionController(
      (state) => states.push(state),
      () => next()
    );
    controller.activate();
    return { controller, states, setNext: (fn) => (next = fn) };
  }

  test('error → «Reintentar» pasa a retrying (carga) → sesión válida', async () => {
    const h = harness();
    await h.controller.validate('t1');
    assert.deepEqual(h.states.at(-1), { status: 'error', token: 't1', kind: 'network' });
    let resolveMe;
    h.setNext(() => new Promise((resolve) => (resolveMe = resolve)));
    const retry = h.controller.validate('t1', true);
    assert.deepEqual(h.states.at(-1), { status: 'retrying', token: 't1', kind: 'network' });
    assert.deepEqual(deriveSessionStatus('t1', h.states.at(-1)), { status: 'retrying', kind: 'network' });
    assert.equal(routeAccess('/', 'retrying'), 'error', 'el guard mantiene el aviso');
    resolveMe({ id: 'u-1' });
    await retry;
    assert.equal(h.states.at(-1).status, 'authenticated');
  });

  test('si el reintento vuelve a fallar, el error refleja el nuevo tipo', async () => {
    const h = harness();
    await h.controller.validate('t1');
    h.setNext(() => Promise.reject(new ApiError('x', 503)));
    await h.controller.validate('t1', true);
    assert.deepEqual(h.states.slice(-2), [
      { status: 'retrying', token: 't1', kind: 'network' },
      { status: 'error', token: 't1', kind: 'server' },
    ]);
  });

  test('la primera validación de un token y un 401 no pasan por retrying', async () => {
    const h = harness();
    h.setNext(() => Promise.reject(new UnauthorizedError()));
    await h.controller.validate('t1');
    await h.controller.validate('t1', true);
    assert.deepEqual(h.states, []);
  });

  test('cada tipo de error tiene su texto en el guard, sin detalles técnicos', () => {
    const kinds = ['network', 'timeout', 'server', 'unreadable'];
    const bodies = kinds.map((kind) => sessionErrorCopy(kind).body);
    assert.equal(new Set(bodies).size, kinds.length);
    for (const kind of [...kinds, 'client', 'unknown']) {
      const { title, body } = sessionErrorCopy(kind);
      assert.equal(title, 'No se pudo comprobar la sesión');
      assert.doesNotMatch(`${title} ${body}`, TECHNICAL, kind);
    }
  });
});
