// AUTH-02 — token de sesión (lib/auth-token.ts), cabecera Bearer y 401 en el
// cliente HTTP (lib/api-client.ts) y protección global de rutas
// (lib/auth-routes.ts). Ejecutar desde uis/backoffice (ver README, Validación).

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { ApiUnauthorizedError, createApiClient } from '../lib/api-client.ts';
import { isPublicPath, routeAccess } from '../lib/auth-routes.ts';
import {
  AUTH_TOKEN_STORAGE_KEY,
  clearAuthToken,
  readAuthToken,
  saveAuthToken,
  subscribeAuthToken,
} from '../lib/auth-token.ts';
import { BASE_URL, LEAK, jsonResponse, recordingFetch } from './support/http-fakes.mjs';

const OPTIONS = { timeoutMs: 1_000 };
const readStatus = async (response) => response.status;

/** `window` mínimo con un localStorage en memoria y eventos `storage`. */
function installFakeWindow() {
  const data = new Map();
  const listeners = new Set();
  globalThis.window = {
    localStorage: {
      getItem: (key) => (data.has(key) ? data.get(key) : null),
      setItem: (key, value) => data.set(key, String(value)),
      removeItem: (key) => data.delete(key),
    },
    addEventListener: (type, listener) => type === 'storage' && listeners.add(listener),
    removeEventListener: (type, listener) => type === 'storage' && listeners.delete(listener),
  };
  return {
    data,
    /** Simula un cambio hecho en otra pestaña. */
    fireStorage: (key) => {
      for (const listener of listeners) listener({ key });
    },
  };
}

describe('lib/auth-token.ts', () => {
  let fake;
  beforeEach(() => {
    fake = installFakeWindow();
  });
  afterEach(() => {
    delete globalThis.window;
  });

  test('guarda, lee y elimina el token en localStorage', () => {
    assert.equal(readAuthToken(), null);
    saveAuthToken('jwt-1');
    assert.equal(fake.data.get(AUTH_TOKEN_STORAGE_KEY), 'jwt-1');
    assert.equal(readAuthToken(), 'jwt-1');
    clearAuthToken();
    assert.equal(fake.data.has(AUTH_TOKEN_STORAGE_KEY), false);
    assert.equal(readAuthToken(), null);
  });

  test('un token vacío no se guarda y un valor en blanco se lee como sin sesión', () => {
    saveAuthToken('   ');
    assert.equal(fake.data.has(AUTH_TOKEN_STORAGE_KEY), false);
    fake.data.set(AUTH_TOKEN_STORAGE_KEY, ' ');
    assert.equal(readAuthToken(), null);
  });

  test('avisa a los suscriptores al guardar, borrar y por cambios en otra pestaña', () => {
    let calls = 0;
    const unsubscribe = subscribeAuthToken(() => (calls += 1));
    saveAuthToken('jwt-1');
    clearAuthToken();
    fake.fireStorage(AUTH_TOKEN_STORAGE_KEY);
    fake.fireStorage('otra-clave');
    assert.equal(calls, 3);
    unsubscribe();
    saveAuthToken('jwt-2');
    assert.equal(calls, 3);
  });

  test('sin window (servidor) o con almacenamiento bloqueado se comporta como sin sesión', () => {
    delete globalThis.window;
    assert.equal(readAuthToken(), null);
    assert.doesNotThrow(() => saveAuthToken('jwt'));
    assert.doesNotThrow(() => clearAuthToken());
    globalThis.window = {
      get localStorage() {
        throw new Error('SecurityError');
      },
      addEventListener() {},
      removeEventListener() {},
    };
    assert.equal(readAuthToken(), null);
    assert.doesNotThrow(() => saveAuthToken('jwt'));
  });
});

describe('cliente HTTP: Authorization y 401', () => {
  function clientWith(makeResponse, { token = 'jwt-123', onUnauthorized = () => {} } = {}) {
    const transport = recordingFetch(makeResponse);
    let unauthorized = 0;
    const client = createApiClient({
      fetch: transport.fetch,
      getBaseUrl: () => BASE_URL,
      getToken: () => token,
      onUnauthorized: () => {
        unauthorized += 1;
        onUnauthorized();
      },
    });
    return { client, transport, unauthorized: () => unauthorized };
  }

  test('las peticiones protegidas envían Authorization: Bearer <token> en todos los métodos', async () => {
    const { client, transport } = clientWith(() => jsonResponse(200, {}));
    await client.get('/a', OPTIONS, readStatus);
    await client.postJson('/b', { x: 1 }, OPTIONS, readStatus);
    await client.patchJson('/c', { x: 1 }, OPTIONS, readStatus);
    await client.putJson('/d', { x: 1 }, OPTIONS, readStatus);
    await client.postForm('/e', new FormData(), OPTIONS, readStatus);
    for (const { init } of transport.calls) {
      assert.equal(init.headers.Authorization, 'Bearer jwt-123');
      assert.equal(init.credentials, undefined);
    }
    assert.equal(transport.calls[3].init.method, 'PUT');
    assert.equal(transport.calls[3].init.headers['Content-Type'], 'application/json');
    assert.equal(transport.calls[3].init.body, '{"x":1}');
    // Multipart: sin Content-Type manual (lo pone el navegador con el boundary).
    assert.equal(transport.calls[4].init.headers['Content-Type'], undefined);
  });

  test('skipAuth (login, registro) no envía el token', async () => {
    const { client, transport } = clientWith(() => jsonResponse(200, {}));
    await client.postForm('/auth/login', new URLSearchParams({ username: 'a@b.co' }), { ...OPTIONS, skipAuth: true }, readStatus);
    await client.postJson('/users', { email: 'a@b.co' }, { ...OPTIONS, skipAuth: true }, readStatus);
    assert.equal(transport.calls[0].init.headers, undefined);
    assert.equal(transport.calls[1].init.headers.Authorization, undefined);
    assert.ok(transport.calls[0].init.body instanceof URLSearchParams);
  });

  test('sin token la petición protegida sale sin cabecera (la API decide con su 401)', async () => {
    const { client, transport } = clientWith(() => jsonResponse(200, {}), { token: null });
    await client.get('/a', OPTIONS, readStatus);
    assert.equal(transport.calls[0].init.headers, undefined);
  });

  test('401 en una petición protegida → borra el token y lanza ApiUnauthorizedError sin llamar al handler', async () => {
    let handled = false;
    const { client, unauthorized } = clientWith(() => jsonResponse(401, { detail: LEAK, code: 'not_authenticated' }));
    await assert.rejects(
      client.get('/suppliers', OPTIONS, async () => {
        handled = true;
      }),
      (error) => {
        assert.ok(error instanceof ApiUnauthorizedError);
        assert.equal(String(error).includes(LEAK), false);
        return true;
      }
    );
    assert.equal(handled, false);
    assert.equal(unauthorized(), 1);
  });

  test('401 en una petición pública llega al servicio y no borra el token', async () => {
    const { client, unauthorized } = clientWith(() => jsonResponse(401, { code: 'invalid_credentials' }));
    const status = await client.postForm('/auth/login', new URLSearchParams(), { ...OPTIONS, skipAuth: true }, readStatus);
    assert.equal(status, 401);
    assert.equal(unauthorized(), 0);
  });

  test('por defecto un 401 elimina el token de localStorage', async () => {
    const fake = installFakeWindow();
    try {
      saveAuthToken('jwt-viejo');
      const transport = recordingFetch(() => jsonResponse(401, {}));
      const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
      await assert.rejects(client.get('/auth/me', OPTIONS, readStatus), ApiUnauthorizedError);
      assert.equal(transport.calls[0].init.headers.Authorization, 'Bearer jwt-viejo');
      assert.equal(fake.data.has(AUTH_TOKEN_STORAGE_KEY), false);
    } finally {
      delete globalThis.window;
    }
  });

  test('otros status (403, 404, 422, 500) no tocan la sesión', async () => {
    for (const status of [403, 404, 422, 500]) {
      const { client, unauthorized } = clientWith(() => jsonResponse(status, {}));
      assert.equal(await client.get('/x', OPTIONS, readStatus), status);
      assert.equal(unauthorized(), 0);
    }
  });
});

describe('lib/auth-routes.ts — protección global', () => {
  test('solo /login, /register y /forgot-password son públicas', () => {
    for (const path of ['/login', '/register', '/login/', '/forgot-password']) assert.equal(isPublicPath(path), true, path);
    for (const path of ['/', '/incidents', '/suppliers', '/account/profile', '/account/change-password', '/loginx', '/ruta-nueva']) {
      assert.equal(isPublicPath(path), false, path);
    }
  });

  test('vista protegida: sin token → /login; validando → espera; válida → se muestra; error → reintento', () => {
    for (const path of ['/', '/incidents', '/suppliers', '/account/profile', '/account/change-password']) {
      assert.equal(routeAccess(path, 'anonymous'), 'redirect_login');
      assert.equal(routeAccess(path, 'initializing'), 'wait');
      assert.equal(routeAccess(path, 'checking'), 'wait');
      assert.equal(routeAccess(path, 'authenticated'), 'render');
      assert.equal(routeAccess(path, 'error'), 'error');
    }
  });

  test('/login, /register y /forgot-password se muestran sin sesión y redirigen a la vista principal con sesión válida', () => {
    for (const path of ['/login', '/register', '/forgot-password']) {
      for (const status of ['initializing', 'anonymous', 'checking', 'error']) {
        assert.equal(routeAccess(path, status), 'render', `${path} ${status}`);
      }
      assert.equal(routeAccess(path, 'authenticated'), 'redirect_home');
    }
  });

  test('/reset-password (AUTH-03) se muestra con o sin sesión: el enlace del email siempre funciona', () => {
    for (const status of ['initializing', 'anonymous', 'checking', 'error', 'authenticated']) {
      assert.equal(routeAccess('/reset-password', status), 'render', status);
      assert.equal(routeAccess('/reset-password/', status), 'render', status);
    }
  });
});
