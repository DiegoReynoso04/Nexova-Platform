// AUTH-02 (SPECS.md §9) — token de sesión, cliente HTTP (Bearer solo hacia
// services/api, 401), servicio de autenticación, normalizadores, sesión y
// protección de rutas. Runner nativo de Node 24, sin dependencias. Desde
// uis/talent-pipeline-tracker:
//   node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test "tests/*.test.mjs"

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

// lib/api-client.ts exige ambas URLs al cargarse (SPECS.md §3.2 y §9).
const CANDIDATES_API = 'https://candidates.test/tracker/api/v1';
const AUTH_API = 'http://auth.test';
process.env.NEXT_PUBLIC_API_URL = CANDIDATES_API;
process.env.NEXT_PUBLIC_AUTH_API_URL = `${AUTH_API}/`;

const { UnauthorizedError, ApiError, NetworkError, ValidationApiError, apiClient, authApiClient } = await import(
  '../lib/api-client.ts'
);
const { AUTH_TOKEN_STORAGE_KEY, clearAuthToken, readAuthToken, saveAuthToken, subscribeAuthToken } = await import(
  '../lib/auth-token.ts'
);
const auth = await import('../services/auth.service.ts');
const { normalizeAccessToken, normalizeCurrentUser } = await import('../services/normalizers.ts');
const { createAuthSessionController, deriveSessionStatus } = await import('../hooks/use-auth-session.ts');
const { isPublicPath, routeAccess } = await import('../lib/auth-routes.ts');

const TOKEN = { access_token: 'jwt-nuevo', token_type: 'bearer', expires_in: 1800 };
const PROFILE = { id: 'p-1', user_id: 'u-1', name: 'Ana', phone: null, address: null };
const ME = { id: 'u-1', email: 'ana@nexova.test', role: 'user', is_active: true, created_at: '2026-10-01T10:00:00Z', profile: PROFILE };
const PASSWORD = 'secreto-123';

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

let storage;
let calls;
let respond;

beforeEach(() => {
  storage = new Map();
  const listeners = new Set();
  globalThis.window = {
    localStorage: {
      getItem: (key) => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
    },
    addEventListener: (type, listener) => type === 'storage' && listeners.add(listener),
    removeEventListener: (type, listener) => type === 'storage' && listeners.delete(listener),
  };
  calls = [];
  respond = () => jsonResponse(200, {});
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return respond(url, init);
  };
});

afterEach(() => {
  delete globalThis.window;
});

describe('token en localStorage', () => {
  test('guarda, lee, borra y avisa a los suscriptores', () => {
    let changes = 0;
    const unsubscribe = subscribeAuthToken(() => (changes += 1));
    saveAuthToken('jwt-1');
    assert.equal(storage.get(AUTH_TOKEN_STORAGE_KEY), 'jwt-1');
    assert.equal(readAuthToken(), 'jwt-1');
    clearAuthToken();
    assert.equal(readAuthToken(), null);
    assert.equal(changes, 2);
    unsubscribe();
  });

  test('sin window (servidor) se comporta como sin sesión', () => {
    delete globalThis.window;
    assert.equal(readAuthToken(), null);
    assert.doesNotThrow(() => saveAuthToken('x'));
  });
});

describe('cliente HTTP', () => {
  test('la API de candidaturas de 4Geeks nunca recibe el token', async () => {
    saveAuthToken('jwt-secreto');
    await apiClient.get('/records', { page: 1 });
    await apiClient.post('/records', { a: 1 });
    for (const { url, init } of calls) {
      assert.ok(url.startsWith(CANDIDATES_API), url);
      assert.equal(init.headers?.Authorization, undefined);
      assert.equal(init.credentials, undefined);
    }
  });

  test('las rutas protegidas de services/api llevan Authorization: Bearer <token>', async () => {
    saveAuthToken('jwt-123');
    await authApiClient.get('/auth/me');
    await authApiClient.put('/profiles/me', { name: 'Ana' });
    assert.equal(calls[0].url, `${AUTH_API}/auth/me`);
    for (const { init } of calls) assert.equal(init.headers.Authorization, 'Bearer jwt-123');
    assert.equal(calls[1].init.method, 'PUT');
    assert.equal(calls[1].init.headers['Content-Type'], 'application/json');
  });

  test('login y registro no envían el token', async () => {
    saveAuthToken('jwt-123');
    await authApiClient.postFormPublic('/auth/login', new URLSearchParams({ username: 'a' }));
    await authApiClient.postPublic('/users', { email: 'a' });
    assert.equal(calls[0].init.headers, undefined);
    assert.equal(calls[1].init.headers.Authorization, undefined);
  });

  test('401 en una ruta protegida → borra el token y lanza UnauthorizedError', async () => {
    saveAuthToken('jwt-caducado');
    respond = () => jsonResponse(401, { code: 'not_authenticated' });
    await assert.rejects(authApiClient.get('/auth/me'), UnauthorizedError);
    assert.equal(readAuthToken(), null);
  });

  test('401 en el login (credenciales) no borra la sesión ni es UnauthorizedError', async () => {
    saveAuthToken('jwt-otro');
    respond = () => jsonResponse(401, { code: 'invalid_credentials' });
    await assert.rejects(authApiClient.postFormPublic('/auth/login', new URLSearchParams()), (error) => {
      assert.ok(error instanceof ApiError && !(error instanceof UnauthorizedError));
      assert.equal(error.status, 401);
      return true;
    });
    assert.equal(readAuthToken(), 'jwt-otro');
  });
});

describe('servicio de autenticación', () => {
  test('login: formulario OAuth2 y guarda el token solo si la respuesta es válida', async () => {
    respond = () => jsonResponse(200, TOKEN);
    await auth.login({ email: ' ana@nexova.test ', password: PASSWORD });
    const body = calls[0].init.body;
    assert.equal(body.get('username'), 'ana@nexova.test');
    assert.equal(body.get('password'), PASSWORD);
    assert.equal(readAuthToken(), 'jwt-nuevo');

    clearAuthToken();
    respond = () => jsonResponse(200, { ...TOKEN, access_token: '' });
    await assert.rejects(auth.login({ email: 'a@b.co', password: PASSWORD }));
    assert.equal(readAuthToken(), null);
  });

  test('login incorrecto → mensaje claro y ningún token', async () => {
    respond = () => jsonResponse(401, { code: 'invalid_credentials', detail: 'incorrect email or password' });
    const error = await auth.login({ email: 'a@b.co', password: PASSWORD }).catch((caught) => caught);
    assert.deepEqual(auth.describeAuthError(error, 'login'), { fields: {}, form: 'Email o contraseña incorrectos.' });
    assert.equal(readAuthToken(), null);
  });

  test('registro: POST /users con perfil opcional (sin role) y después POST /auth/login', async () => {
    respond = (url) => (url.endsWith('/users') ? jsonResponse(201, {}) : jsonResponse(200, TOKEN));
    await auth.register({ email: 'ana@nexova.test', password: PASSWORD, name: ' Ana ', phone: '', address: 'Valencia' });
    assert.deepEqual(
      calls.map(({ url, init }) => `${init.method} ${url.slice(AUTH_API.length)}`),
      ['POST /users', 'POST /auth/login']
    );
    assert.deepEqual(JSON.parse(calls[0].init.body), { email: 'ana@nexova.test', password: PASSWORD, name: 'Ana', address: 'Valencia' });
    assert.equal(calls[1].init.body.get('username'), 'ana@nexova.test');
    assert.equal(readAuthToken(), 'jwt-nuevo');
  });

  test('registro: 422 y 409 se muestran por campo', async () => {
    respond = () =>
      jsonResponse(422, {
        detail: [
          { loc: ['body', 'password'], msg: 'Value error, password must have at least 8 characters', type: 'value_error' },
          { loc: ['body'], msg: 'Body error', type: 'x' },
        ],
      });
    let error = await auth.register({ email: 'a@b.co', password: 'x', name: '', phone: '', address: '' }).catch((e) => e);
    assert.ok(error instanceof ValidationApiError);
    assert.deepEqual(auth.describeAuthError(error, 'register'), {
      fields: { password: 'password must have at least 8 characters' },
      form: 'Body error',
    });

    respond = () => jsonResponse(409, { code: 'email_already_registered' });
    error = await auth.register({ email: 'a@b.co', password: PASSWORD, name: '', phone: '', address: '' }).catch((e) => e);
    assert.deepEqual(auth.describeAuthError(error, 'register'), {
      fields: { email: 'Ya existe una cuenta con este email.' },
      form: null,
    });
    assert.equal(calls.filter(({ url }) => url.endsWith('/auth/login')).length, 0);
  });

  test('perfil: GET /auth/me y PUT /profiles/me con null para los campos vacíos', async () => {
    saveAuthToken('jwt-123');
    respond = (url, init) => (init.method === 'GET' ? jsonResponse(200, { ...ME, hashed_password: 'x' }) : jsonResponse(200, PROFILE));
    assert.deepEqual(await auth.getCurrentUser(), ME);
    await auth.updateProfile({ name: ' Ana ', phone: '', address: '  ' });
    assert.deepEqual(JSON.parse(calls[1].init.body), { name: 'Ana', phone: null, address: null });
  });

  test('validación en cliente de campos requeridos', () => {
    assert.deepEqual(auth.validateCredentials({ email: ' ', password: '' }), {
      fields: { email: 'Introduce tu email.', password: 'Introduce tu contraseña.' },
      form: null,
    });
    assert.equal(auth.validateCredentials({ email: 'a', password: 'b' }), null);
  });
});

describe('flujo de login completo (regresión: login 200 sin token guardado)', () => {
  test('200 con access_token → token en la clave que lee la sesión → /auth/me con Bearer → vista autenticada', async () => {
    respond = (url) => (url.endsWith('/auth/login') ? jsonResponse(200, TOKEN) : jsonResponse(200, ME));
    await auth.login({ email: 'ana@nexova.test', password: PASSWORD });

    // Misma clave que lee hooks/use-auth-session.ts (readAuthToken) y, por tanto, el guard.
    assert.equal(AUTH_TOKEN_STORAGE_KEY, 'nexova.tracker.access_token');
    assert.equal(storage.get('nexova.tracker.access_token'), 'jwt-nuevo');
    const token = readAuthToken();
    assert.equal(token, 'jwt-nuevo');

    const states = [];
    const controller = createAuthSessionController((state) => states.push(state));
    controller.activate();
    await controller.validate(token);
    const me = calls.find(({ url }) => url === `${AUTH_API}/auth/me`);
    assert.ok(me, 'tras el login se valida la sesión con GET /auth/me');
    assert.equal(me.init.headers.Authorization, 'Bearer jwt-nuevo');
    const session = deriveSessionStatus(token, states[0]);
    assert.equal(session.status, 'authenticated');
    assert.equal(routeAccess('/', session.status), 'render');
    assert.equal(routeAccess('/login', session.status), 'redirect_home');
  });

  test('respuesta bloqueada por el navegador (p. ej. CORS sin el origen 3001) → error de conexión y ningún token', async () => {
    // Con CORS mal configurado el servidor procesa el login (200), pero fetch() se rechaza.
    globalThis.fetch = async (url, init) => {
      calls.push({ url, init });
      throw new TypeError('Failed to fetch');
    };
    const error = await auth.login({ email: 'ana@nexova.test', password: PASSWORD }).catch((caught) => caught);
    assert.ok(error instanceof NetworkError);
    assert.equal(readAuthToken(), null);
    assert.deepEqual(auth.describeAuthError(error, 'login'), { fields: {}, form: 'No se pudo conectar con el servidor' });
    assert.equal(calls.some(({ url }) => url.endsWith('/auth/me')), false);
  });

  test('credenciales incorrectas siguen mostrando su error y no guardan token', async () => {
    respond = () => jsonResponse(401, { code: 'invalid_credentials', detail: 'incorrect email or password' });
    const error = await auth.login({ email: 'ana@nexova.test', password: 'mala-clave' }).catch((caught) => caught);
    assert.equal(auth.describeAuthError(error, 'login').form, 'Email o contraseña incorrectos.');
    assert.equal(storage.has('nexova.tracker.access_token'), false);
  });
});

describe('normalizadores', () => {
  test('rechazan respuestas fuera del contrato', () => {
    assert.throws(() => normalizeAccessToken({ token_type: 'bearer', expires_in: 1 }));
    assert.throws(() => normalizeCurrentUser({ ...ME, role: 'root' }));
    assert.deepEqual(normalizeCurrentUser({ ...ME, profile: null }), { ...ME, profile: null });
  });
});

describe('sesión y protección de rutas', () => {
  const tick = () => new Promise((resolve) => setImmediate(resolve));

  test('estado derivado del token y de su validación', () => {
    assert.equal(deriveSessionStatus(undefined, { status: 'idle' }).status, 'initializing');
    assert.equal(deriveSessionStatus(null, { status: 'idle' }).status, 'anonymous');
    assert.equal(deriveSessionStatus('t1', { status: 'idle' }).status, 'checking');
    assert.equal(deriveSessionStatus('t1', { status: 'authenticated', token: 't1', user: ME }).status, 'authenticated');
    assert.equal(deriveSessionStatus('t2', { status: 'authenticated', token: 't1', user: ME }).status, 'checking');
  });

  test('el controlador valida cada token una vez y un 401 no deja estado', async () => {
    const states = [];
    let fetches = 0;
    let fail = false;
    const controller = createAuthSessionController(
      (state) => states.push(state),
      async () => {
        fetches += 1;
        if (fail) throw new UnauthorizedError();
        return ME;
      }
    );
    controller.activate();
    await controller.validate('t1');
    await controller.validate('t1');
    assert.equal(fetches, 1);
    assert.deepEqual(states, [{ status: 'authenticated', token: 't1', user: ME }]);
    fail = true;
    await controller.validate('t2');
    await tick();
    assert.equal(states.length, 1);
  });

  test('todas las vistas son protegidas salvo /login y /register', () => {
    assert.equal(isPublicPath('/login'), true);
    assert.equal(isPublicPath('/register'), true);
    for (const path of ['/', '/candidates/abc', '/account/profile']) {
      assert.equal(isPublicPath(path), false);
      assert.equal(routeAccess(path, 'anonymous'), 'redirect_login');
      assert.equal(routeAccess(path, 'checking'), 'wait');
      assert.equal(routeAccess(path, 'authenticated'), 'render');
    }
    assert.equal(routeAccess('/login', 'anonymous'), 'render');
    assert.equal(routeAccess('/register', 'authenticated'), 'redirect_home');
  });
});
