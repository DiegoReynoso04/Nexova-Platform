// Tests de lib/api-client.ts (transporte genérico). Ejecutar desde uis/backoffice:
//   node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test "tests/*.test.mjs"

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  ApiAbortError,
  ApiConfigError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiUnexpectedResponseError,
  createApiClient,
} from '../lib/api-client.ts';
import { BASE_URL, LEAK, hangingFetch, jsonResponse, offlineFetch, recordingFetch, textResponse } from './support/http-fakes.mjs';

const identity = (body) => body;
const readStatus = async (response) => response.status;
const OPTIONS = { timeoutMs: 1_000 };

function assertSafeError(error, ErrorClass) {
  assert.ok(error instanceof ErrorClass, `expected ${ErrorClass.name}, got ${error?.name}`);
  assert.equal(error.cause, undefined);
  const exposed = [error.message, String(error), JSON.stringify(error)].join(' ');
  assert.equal(exposed.includes(LEAK), false);
  return true;
}

describe('configuración perezosa de la URL base', () => {
  test('crear el cliente no lee ni valida la configuración', () => {
    let reads = 0;
    createApiClient({ getBaseUrl: () => { reads += 1; return undefined; } });
    assert.equal(reads, 0);
  });

  test('URL ausente, vacía o en blanco → ApiConfigError sin llamar a la red', async () => {
    for (const value of [undefined, '', '   ']) {
      const transport = recordingFetch(() => jsonResponse(200, {}));
      const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => value });
      await assert.rejects(client.get('/x', OPTIONS, readStatus), (error) => assertSafeError(error, ApiConfigError));
      assert.equal(transport.calls.length, 0);
    }
  });

  test('por defecto lee NEXT_PUBLIC_API_URL en cada petición', async () => {
    const previous = process.env.NEXT_PUBLIC_API_URL;
    try {
      const transport = recordingFetch(() => jsonResponse(200, {}));
      const client = createApiClient({ fetch: transport.fetch });
      delete process.env.NEXT_PUBLIC_API_URL;
      await assert.rejects(client.get('/x', OPTIONS, readStatus), ApiConfigError);
      process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8000/';
      await client.get('/api/x', OPTIONS, readStatus);
      assert.equal(transport.calls[0].url, 'http://localhost:8000/api/x');
    } finally {
      if (previous === undefined) delete process.env.NEXT_PUBLIC_API_URL;
      else process.env.NEXT_PUBLIC_API_URL = previous;
    }
  });
});

describe('peticiones', () => {
  test('GET sin credenciales ni cuerpo', async () => {
    const transport = recordingFetch(() => jsonResponse(200, {}));
    const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
    await client.get('/api/items', OPTIONS, readStatus);
    const [{ url, init }] = transport.calls;
    assert.equal(url, `${BASE_URL}/api/items`);
    assert.equal(init.method, 'GET');
    assert.equal(init.credentials, undefined);
    assert.equal(init.body, undefined);
    assert.ok(init.signal instanceof AbortSignal);
  });

  test('POST multipart envía el FormData tal cual y sin Content-Type manual', async () => {
    const transport = recordingFetch(() => jsonResponse(200, {}));
    const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
    const form = new FormData();
    form.append('file', new File(['a'], 'a.csv'));
    await client.postForm('/api/upload', form, OPTIONS, readStatus);
    const [{ init }] = transport.calls;
    assert.equal(init.method, 'POST');
    assert.equal(init.body, form);
    assert.equal(init.headers, undefined);
    assert.equal(init.credentials, undefined);
  });

  test('conserva status y cabeceras para el servicio', async () => {
    for (const status of [200, 400, 404, 405, 413, 415, 422, 500]) {
      const transport = recordingFetch(() => jsonResponse(status, {}, { 'X-Analysis-Id': 'abc' }));
      const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
      const seen = await client.get('/x', OPTIONS, async (response) => [response.status, response.header('x-analysis-id')]);
      assert.deepEqual(seen, [status, 'abc']);
    }
  });

  test('json() entrega el cuerpo al parser indicado', async () => {
    const transport = recordingFetch(() => jsonResponse(200, { a: 1 }));
    const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
    const result = await client.get('/x', OPTIONS, (response) => response.json((body) => ({ parsed: body.a })));
    assert.deepEqual(result, { parsed: 1 });
  });
});

describe('errores de transporte', () => {
  test('timeout → ApiTimeoutError', async () => {
    const client = createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL });
    await assert.rejects(client.get('/x', { timeoutMs: 20 }, readStatus), (error) => assertSafeError(error, ApiTimeoutError));
  });

  test('cancelación de quien llama → ApiAbortError (antes y durante la petición)', async () => {
    const client = createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL });
    const early = new AbortController();
    early.abort();
    await assert.rejects(client.get('/x', { timeoutMs: 1_000, signal: early.signal }, readStatus), ApiAbortError);

    const late = new AbortController();
    const pending = client.get('/x', { timeoutMs: 1_000, signal: late.signal }, readStatus);
    setTimeout(() => late.abort(), 10);
    await assert.rejects(pending, (error) => assertSafeError(error, ApiAbortError));
  });

  test('fallo de red → ApiNetworkError sin el error original', async () => {
    const client = createApiClient({ fetch: offlineFetch(), getBaseUrl: () => BASE_URL });
    await assert.rejects(client.get('/x', OPTIONS, readStatus), (error) => assertSafeError(error, ApiNetworkError));
  });

  test('cuerpo no JSON cuando se espera JSON → ApiUnexpectedResponseError sin el cuerpo', async () => {
    const jsonHeaders = { 'content-type': 'application/json' };
    const cases = [
      () => textResponse(200, `plain text with ${LEAK}`),
      () => new Response(`{"broken": "${LEAK}"`, { status: 200, headers: jsonHeaders }),
      // JSON.parse de V8 cita un fragmento del cuerpo en su mensaje ("leak.canar"...).
      () => new Response(`${LEAK},x,y`, { status: 200, headers: jsonHeaders }),
      () => new Response(`${LEAK},x,y`, { status: 200 }),
    ];
    for (const makeResponse of cases) {
      const transport = recordingFetch(makeResponse);
      const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
      await assert.rejects(
        client.get('/x', OPTIONS, (response) => response.json(identity)),
        (error) => {
          assertSafeError(error, ApiUnexpectedResponseError);
          assert.equal(error.message, 'The API returned a response that is not valid JSON');
          assert.equal(/leak|canar/i.test(JSON.stringify(error) + String(error)), false);
          return true;
        }
      );
    }
  });

  test('en 4xx/5xx el cliente no interpreta el cuerpo ni lanza errores con su contenido', async () => {
    const body = { detail: `row 3: ${LEAK}`, code: 'whatever', rows: [{ customer_email: LEAK }] };
    // El 401 de una petición protegida lo intercepta el cliente (AUTH-02, tests/auth-client.test.mjs);
    // en una petición pública (`skipAuth`) llega al parser como cualquier otro status.
    for (const status of [400, 403, 404, 405, 409, 413, 415, 422, 429, 500, 503]) {
      const transport = recordingFetch(() => jsonResponse(status, body));
      const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
      // El status no lo decide el cliente: entrega el JSON al parser de quien llama.
      const delivered = await client.get('/x', OPTIONS, (response) => response.json((parsed) => parsed));
      assert.deepEqual(delivered, body, String(status));
    }
    const transport = recordingFetch(() => jsonResponse(401, body));
    const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
    const delivered = await client.get('/x', { ...OPTIONS, skipAuth: true }, (response) => response.json((parsed) => parsed));
    assert.deepEqual(delivered, body, '401 (skipAuth)');
  });

  // B4 de la auditoría: blob() trata los fallos de lectura igual que json().
  function bodyStream(onStart) {
    return new ReadableStream({ start: onStart });
  }

  test('fallo de red al leer el blob → ApiNetworkError sin el error original', async () => {
    const failing = () =>
      new Response(bodyStream((controller) => controller.error(new TypeError(`connection reset ${LEAK}`))), { status: 200 });
    const client = createApiClient({ fetch: recordingFetch(failing).fetch, getBaseUrl: () => BASE_URL });
    await assert.rejects(client.get('/x', OPTIONS, (response) => response.blob()), (error) => assertSafeError(error, ApiNetworkError));
  });

  test('abort o timeout mientras se lee el blob → se relanza como abort o timeout, no como fallo de red', async () => {
    // Cuerpo que no termina nunca y se corta, como en un fetch real, al abortar la petición.
    const endless = async (_input, init) =>
      new Response(
        bodyStream((controller) => {
          init.signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')));
        }),
        { status: 200 }
      );
    const client = createApiClient({ fetch: endless, getBaseUrl: () => BASE_URL });

    const caller = new AbortController();
    const pending = client.get('/x', { timeoutMs: 1_000, signal: caller.signal }, (response) => response.blob());
    setTimeout(() => caller.abort(), 10);
    await assert.rejects(pending, (error) => assertSafeError(error, ApiAbortError));

    await assert.rejects(client.get('/x', { timeoutMs: 20 }, (response) => response.blob()), (error) =>
      assertSafeError(error, ApiTimeoutError)
    );
  });

  test('los errores lanzados por el handler se propagan sin transformar', async () => {
    const transport = recordingFetch(() => jsonResponse(200, {}));
    const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
    class HandlerError extends Error {}
    await assert.rejects(client.get('/x', OPTIONS, async () => { throw new HandlerError('x'); }), HandlerError);
  });
});
