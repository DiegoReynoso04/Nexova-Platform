// AUTH-02 — services/auth.service.ts y sus normalizadores, contra el contrato
// de services/api/SPECS.md Parte C (§17–§18), con transporte falso.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { createApiClient } from '../lib/api-client.ts';
import { AuthServiceError, createAuthService } from '../services/auth.service.ts';
import {
  UnexpectedResponseError,
  normalizeAccessToken,
  normalizeAuthValidationErrors,
  normalizeCurrentUser,
} from '../services/normalizers.ts';
import { BASE_URL, LEAK, jsonResponse, recordingFetch } from './support/http-fakes.mjs';

const TOKEN = { access_token: 'jwt-nuevo', token_type: 'bearer', expires_in: 1800 };
const PROFILE = { id: 'p-1', user_id: 'u-1', name: 'Ana', phone: null, address: null };
const ME = {
  id: 'u-1',
  email: 'ana@nexova.test',
  role: 'user',
  is_active: true,
  created_at: '2026-10-01T10:00:00Z',
  profile: PROFILE,
};
const PASSWORD = 'secreto-123';

/** Servicio con transporte falso. `routes`: "MÉTODO /ruta" → respuesta. */
function serviceWith(routes, { token = 'jwt-guardado' } = {}) {
  const transport = recordingFetch((url, init) => {
    const key = `${init.method} ${url.slice(BASE_URL.length)}`;
    const make = routes[key];
    if (make === undefined) throw new Error(`ruta no prevista: ${key}`);
    return make(init);
  });
  const saved = [];
  let cleared = 0;
  const client = createApiClient({
    fetch: transport.fetch,
    getBaseUrl: () => BASE_URL,
    getToken: () => token,
    onUnauthorized: () => (cleared += 1),
  });
  const service = createAuthService({ client, saveToken: (value) => saved.push(value) });
  return { service, transport, saved, cleared: () => cleared };
}

function expectUiError(expected) {
  return (error) => {
    assert.ok(error instanceof AuthServiceError, `expected AuthServiceError, got ${error?.name}`);
    assert.deepEqual(error.uiError, expected);
    const exposed = [error.message, String(error), JSON.stringify(error)].join(' ');
    assert.equal(exposed.includes(PASSWORD), false, 'error exposes the password');
    assert.equal(exposed.includes(LEAK), false, 'error exposes response data');
    return true;
  };
}

describe('login (POST /auth/login)', () => {
  test('envía el formulario OAuth2 sin token y guarda el access_token recibido', async () => {
    const { service, transport, saved } = serviceWith({ 'POST /auth/login': () => jsonResponse(200, TOKEN) });
    await service.login({ email: '  ana@nexova.test ', password: PASSWORD });
    const [{ init }] = transport.calls;
    assert.ok(init.body instanceof URLSearchParams);
    assert.equal(init.body.get('username'), 'ana@nexova.test');
    assert.equal(init.body.get('password'), PASSWORD);
    assert.equal(init.headers, undefined, 'no Authorization ni Content-Type manual');
    assert.deepEqual(saved, ['jwt-nuevo']);
  });

  test('credenciales incorrectas (401 invalid_credentials) → error claro y no se guarda nada ni se borra la sesión', async () => {
    const { service, saved, cleared } = serviceWith({
      'POST /auth/login': () => jsonResponse(401, { detail: 'incorrect email or password', code: 'invalid_credentials' }),
    });
    await assert.rejects(service.login({ email: 'ana@nexova.test', password: PASSWORD }), expectUiError({ kind: 'invalid_credentials' }));
    assert.deepEqual(saved, []);
    assert.equal(cleared(), 0);
  });

  test('una respuesta 200 sin token válido no se guarda', async () => {
    for (const body of [{ ...TOKEN, access_token: '' }, { token_type: 'bearer' }, 'jwt']) {
      const { service, saved } = serviceWith({ 'POST /auth/login': () => jsonResponse(200, body) });
      await assert.rejects(service.login({ email: 'a@b.co', password: PASSWORD }), expectUiError({ kind: 'unexpected_response' }));
      assert.deepEqual(saved, []);
    }
  });

  test('campos vacíos → validación en cliente, sin petición', async () => {
    const { service, transport } = serviceWith({});
    await assert.rejects(
      service.login({ email: ' ', password: '' }),
      expectUiError({
        kind: 'validation',
        source: 'client',
        errors: [
          { field: 'email', message: 'Introduce tu email.' },
          { field: 'password', message: 'Introduce tu contraseña.' },
        ],
      })
    );
    assert.equal(transport.calls.length, 0);
  });

  test('422 del formulario OAuth2: `username` se muestra en el campo email', async () => {
    const { service } = serviceWith({
      'POST /auth/login': () =>
        jsonResponse(422, { code: 'validation_error', detail: [{ loc: ['body', 'username'], msg: 'Field required', type: 'missing' }] }),
    });
    await assert.rejects(
      service.login({ email: 'a', password: 'b' }),
      expectUiError({ kind: 'validation', source: 'api', errors: [{ field: 'email', message: 'Field required' }] })
    );
  });

  test('errores de transporte y 5xx', async () => {
    const { service } = serviceWith({ 'POST /auth/login': () => jsonResponse(500, { detail: LEAK }) });
    await assert.rejects(service.login({ email: 'a@b.co', password: PASSWORD }), expectUiError({ kind: 'server_error' }));
    const offline = createAuthService({
      client: createApiClient({ fetch: async () => { throw new TypeError('Failed to fetch'); }, getBaseUrl: () => BASE_URL }),
      saveToken: () => assert.fail('no debe guardar'),
    });
    await assert.rejects(offline.login({ email: 'a@b.co', password: PASSWORD }), expectUiError({ kind: 'network' }));
    const unconfigured = createAuthService({ client: createApiClient({ getBaseUrl: () => undefined }) });
    await assert.rejects(unconfigured.login({ email: 'a@b.co', password: PASSWORD }), expectUiError({ kind: 'config' }));
  });
});

describe('registro (POST /users + POST /auth/login)', () => {
  const VALUES = { email: 'ana@nexova.test', password: PASSWORD, name: ' Ana ', phone: '', address: 'Valencia' };

  test('crea el usuario con los campos de perfil y después hace login con las mismas credenciales', async () => {
    const { service, transport, saved } = serviceWith({
      'POST /users': () => jsonResponse(201, { id: 'u-1', email: 'ana@nexova.test', role: 'user', is_active: true, created_at: 'x' }),
      'POST /auth/login': () => jsonResponse(200, TOKEN),
    });
    await service.register(VALUES);
    assert.deepEqual(
      transport.calls.map(({ url, init }) => `${init.method} ${url.slice(BASE_URL.length)}`),
      ['POST /users', 'POST /auth/login']
    );
    const [register, login] = transport.calls;
    // UserCreate sin `role`; opcionales recortados y los vacíos no se envían.
    assert.deepEqual(JSON.parse(register.init.body), { email: 'ana@nexova.test', password: PASSWORD, name: 'Ana', address: 'Valencia' });
    assert.equal(register.init.headers.Authorization, undefined);
    assert.equal(login.init.body.get('username'), 'ana@nexova.test');
    assert.equal(login.init.body.get('password'), PASSWORD);
    assert.deepEqual(saved, ['jwt-nuevo']);
  });

  test('422 de la API → errores por campo; sin login ni token', async () => {
    const { service, transport, saved } = serviceWith({
      'POST /users': () =>
        jsonResponse(422, {
          code: 'validation_error',
          detail: [
            { loc: ['body', 'password'], msg: 'Value error, password must have at least 8 characters', type: 'value_error' },
            { loc: ['body', 'email'], msg: 'Value error, email must be a valid email address', type: 'value_error' },
            { loc: ['body'], msg: 'Body error', type: 'x' },
          ],
        }),
    });
    await assert.rejects(
      service.register({ ...VALUES, password: 'corta' }),
      expectUiError({
        kind: 'validation',
        source: 'api',
        errors: [
          { field: 'password', message: 'password must have at least 8 characters' },
          { field: 'email', message: 'email must be a valid email address' },
          { field: null, message: 'Body error' },
        ],
      })
    );
    assert.equal(transport.calls.length, 1);
    assert.deepEqual(saved, []);
  });

  test('409 email ya registrado → error en el campo email', async () => {
    const { service } = serviceWith({
      'POST /users': () => jsonResponse(409, { detail: 'email already registered', code: 'email_already_registered' }),
    });
    await assert.rejects(
      service.register(VALUES),
      expectUiError({ kind: 'validation', source: 'api', errors: [{ field: 'email', message: 'Ya existe una cuenta con este email.' }] })
    );
  });

  test('usuario creado pero login fallido → registered_login_failed y ningún token', async () => {
    const { service, saved } = serviceWith({
      'POST /users': () => jsonResponse(201, {}),
      'POST /auth/login': () => jsonResponse(500, {}),
    });
    await assert.rejects(service.register(VALUES), expectUiError({ kind: 'registered_login_failed' }));
    assert.deepEqual(saved, []);
  });
});

describe('cuenta (GET /auth/me, PUT /profiles/me)', () => {
  test('GET /auth/me con Bearer y normalizado sin campos extra', async () => {
    const { service, transport } = serviceWith({
      'GET /auth/me': () => jsonResponse(200, { ...ME, hashed_password: LEAK }),
    });
    const user = await service.getCurrentUser();
    assert.deepEqual(user, ME);
    assert.equal(transport.calls[0].init.headers.Authorization, 'Bearer jwt-guardado');
  });

  test('PUT /profiles/me con Bearer, nombre/teléfono/dirección y null para los vacíos', async () => {
    const saved = { ...PROFILE, name: 'Ana Pérez', phone: '+34 600 000 000', address: null };
    const { service, transport } = serviceWith({ 'PUT /profiles/me': () => jsonResponse(200, saved) });
    const profile = await service.updateProfile({ name: ' Ana Pérez ', phone: '+34 600 000 000', address: '  ' });
    assert.deepEqual(profile, saved);
    const [{ init }] = transport.calls;
    assert.equal(init.method, 'PUT');
    assert.equal(init.headers.Authorization, 'Bearer jwt-guardado');
    assert.deepEqual(JSON.parse(init.body), { name: 'Ana Pérez', phone: '+34 600 000 000', address: null });
  });

  test('401 en una llamada protegida → session_expired y el cliente borra la sesión', async () => {
    for (const [route, call] of [
      ['GET /auth/me', (service) => service.getCurrentUser()],
      ['PUT /profiles/me', (service) => service.updateProfile({ name: '', phone: '', address: '' })],
    ]) {
      const h = serviceWith({ [route]: () => jsonResponse(401, { code: 'not_authenticated', detail: LEAK }) });
      await assert.rejects(call(h.service), expectUiError({ kind: 'session_expired' }));
      assert.equal(h.cleared(), 1, route);
    }
  });

  test('422 y 404 de PUT /profiles/me', async () => {
    let h = serviceWith({
      'PUT /profiles/me': () =>
        jsonResponse(422, { detail: [{ loc: ['body', 'phone'], msg: 'String should have at most 200 characters', type: 'string_too_long' }] }),
    });
    await assert.rejects(
      h.service.updateProfile({ name: '', phone: 'x'.repeat(201), address: '' }),
      expectUiError({ kind: 'validation', source: 'api', errors: [{ field: 'phone', message: 'String should have at most 200 characters' }] })
    );
    h = serviceWith({ 'PUT /profiles/me': () => jsonResponse(404, { code: 'profile_not_found', detail: 'profile not found' }) });
    await assert.rejects(h.service.updateProfile({ name: 'a', phone: '', address: '' }), expectUiError({ kind: 'profile_not_found' }));
  });
});

describe('normalizadores de autenticación', () => {
  test('normalizeAccessToken exige access_token, token_type y expires_in', () => {
    assert.deepEqual(normalizeAccessToken(TOKEN), TOKEN);
    assert.throws(() => normalizeAccessToken({ ...TOKEN, expires_in: '1800' }), UnexpectedResponseError);
  });

  test('normalizeCurrentUser valida el rol y admite profile null', () => {
    assert.deepEqual(normalizeCurrentUser({ ...ME, profile: null }), { ...ME, profile: null });
    assert.throws(() => normalizeCurrentUser({ ...ME, role: 'root' }), UnexpectedResponseError);
    assert.throws(() => normalizeCurrentUser({ ...ME, profile: { ...PROFILE, name: 3 } }), UnexpectedResponseError);
  });

  test('normalizeAuthValidationErrors ignora entradas mal formadas y nunca lanza', () => {
    assert.deepEqual(normalizeAuthValidationErrors(null), []);
    assert.deepEqual(normalizeAuthValidationErrors({ detail: 'x' }), []);
    assert.deepEqual(
      normalizeAuthValidationErrors({ detail: [{ loc: ['body', 'role'], msg: 'Extra inputs are not permitted' }, { msg: 1 }] }),
      [{ field: null, message: 'Extra inputs are not permitted' }]
    );
  });
});
