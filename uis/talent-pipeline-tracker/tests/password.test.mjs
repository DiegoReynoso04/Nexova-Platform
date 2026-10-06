// AUTH-03 (SPECS.md §9.4) — recuperación y cambio de contraseña contra
// services/api: servicio, validación en cliente, traducción de errores y
// protección de las rutas nuevas. Runner nativo de Node 24, sin dependencias.

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

// lib/api-client.ts exige ambas URLs al cargarse (SPECS.md §3.2 y §9).
const AUTH_API = 'http://auth.test';
process.env.NEXT_PUBLIC_API_URL = 'https://candidates.test/tracker/api/v1';
process.env.NEXT_PUBLIC_AUTH_API_URL = AUTH_API;

const { AUTH_TOKEN_STORAGE_KEY, saveAuthToken } = await import('../lib/auth-token.ts');
const auth = await import('../services/auth.service.ts');
const { isPublicPath, routeAccess } = await import('../lib/auth-routes.ts');

const OLD_PASSWORD = 'contraseña-actual-1';
const NEW_PASSWORD = 'contraseña-nueva-2';
const RESET_TOKEN = 'tok_enlace_123';

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

let storage;
let calls;
let respond;

beforeEach(() => {
  storage = new Map();
  globalThis.window = {
    localStorage: {
      getItem: (key) => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
    },
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  calls = [];
  respond = () => jsonResponse(200, { detail: 'ok' });
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return respond(url, init);
  };
});

afterEach(() => {
  delete globalThis.window;
});

function describePassword(error) {
  return auth.describeAuthError(error, 'password');
}

describe('POST /auth/forgot-password', () => {
  test('público: solo el email, sin token aunque haya sesión', async () => {
    saveAuthToken('jwt-guardado');
    await auth.requestPasswordReset({ email: '  ana@nexova.test ' });
    const [{ url, init }] = calls;
    assert.equal(url, `${AUTH_API}/auth/forgot-password`);
    assert.deepEqual(JSON.parse(init.body), { email: 'ana@nexova.test' });
    assert.equal(new Headers(init.headers).has('Authorization'), false);
  });

  test('email vacío → error en cliente', () => {
    assert.deepEqual(auth.validateForgotPassword({ email: ' ' }), { fields: { email: 'Introduce tu email.' }, form: null });
    assert.equal(auth.validateForgotPassword({ email: 'ana@nexova.test' }), null);
  });
});

describe('POST /auth/reset-password', () => {
  const VALUES = { new_password: NEW_PASSWORD, password_confirmation: NEW_PASSWORD };

  test('público: token y contraseña nueva, sin la confirmación', async () => {
    await auth.resetPassword(RESET_TOKEN, VALUES);
    const [{ url, init }] = calls;
    assert.equal(url, `${AUTH_API}/auth/reset-password`);
    assert.deepEqual(JSON.parse(init.body), { token: RESET_TOKEN, new_password: NEW_PASSWORD });
    assert.equal(new Headers(init.headers).has('Authorization'), false);
  });

  test('400 (inválido, caducado o ya usado) → enlace no válido, sin tocar la sesión', async () => {
    saveAuthToken('jwt-guardado');
    respond = () => jsonResponse(400, { code: 'invalid_reset_token', detail: 'reset token is invalid, expired or already used' });
    const error = await auth.resetPassword(RESET_TOKEN, VALUES).catch((caught) => caught);
    assert.ok(error instanceof auth.InvalidResetTokenError);
    const described = describePassword(error);
    assert.equal(described.invalidResetToken, true);
    assert.match(described.form, /no es válido o ha caducado/);
    assert.equal(storage.get(AUTH_TOKEN_STORAGE_KEY), 'jwt-guardado');
  });

  test('sin token en la URL → enlace no válido sin petición', async () => {
    await assert.rejects(auth.resetPassword('', VALUES), auth.InvalidResetTokenError);
    assert.equal(calls.length, 0);
  });

  test('422 de la contraseña nueva → error en su campo', async () => {
    respond = () =>
      jsonResponse(422, { detail: [{ loc: ['body', 'new_password'], msg: 'Value error, password must have at least 8 characters', type: 'value_error' }] });
    const error = await auth.resetPassword(RESET_TOKEN, { new_password: 'corta', password_confirmation: 'corta' }).catch((caught) => caught);
    assert.deepEqual(describePassword(error).fields, { new_password: 'password must have at least 8 characters' });
  });

  test('validación en cliente: requerida y confirmación coincidente', () => {
    assert.deepEqual(auth.validateResetPassword({ new_password: '', password_confirmation: '' }).fields, {
      new_password: 'Introduce la contraseña nueva.',
    });
    assert.deepEqual(auth.validateResetPassword({ new_password: NEW_PASSWORD, password_confirmation: 'otra' }).fields, {
      password_confirmation: 'La confirmación no coincide con la contraseña nueva.',
    });
    assert.equal(auth.validateResetPassword(VALUES), null);
  });
});

describe('POST /auth/change-password', () => {
  const VALUES = { current_password: OLD_PASSWORD, new_password: NEW_PASSWORD, password_confirmation: NEW_PASSWORD };

  test('protegido: Bearer, contraseña actual y nueva (sin la confirmación)', async () => {
    saveAuthToken('jwt-guardado');
    await auth.changePassword(VALUES);
    const [{ url, init }] = calls;
    assert.equal(url, `${AUTH_API}/auth/change-password`);
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer jwt-guardado');
    assert.deepEqual(JSON.parse(init.body), { current_password: OLD_PASSWORD, new_password: NEW_PASSWORD });
  });

  test('400 → error en el campo contraseña actual; la sesión sigue', async () => {
    saveAuthToken('jwt-guardado');
    respond = () => jsonResponse(400, { code: 'incorrect_password', detail: 'current password is incorrect' });
    const error = await auth.changePassword(VALUES).catch((caught) => caught);
    assert.ok(error instanceof auth.IncorrectCurrentPasswordError);
    assert.deepEqual(describePassword(error), { fields: { current_password: 'La contraseña actual no es correcta.' }, form: null });
    assert.equal(storage.get(AUTH_TOKEN_STORAGE_KEY), 'jwt-guardado');
  });

  test('401 → se borra el token (sesión caducada)', async () => {
    saveAuthToken('jwt-viejo');
    respond = () => jsonResponse(401, { code: 'not_authenticated', detail: 'could not validate credentials' });
    await assert.rejects(auth.changePassword(VALUES));
    assert.equal(storage.has(AUTH_TOKEN_STORAGE_KEY), false);
  });

  test('validación en cliente: contraseña actual requerida y confirmación coincidente, sin petición', () => {
    assert.deepEqual(auth.validateChangePassword({ current_password: '', new_password: 'abc', password_confirmation: 'abd' }).fields, {
      current_password: 'Introduce tu contraseña actual.',
      password_confirmation: 'La confirmación no coincide con la contraseña nueva.',
    });
    assert.equal(auth.validateChangePassword(VALUES), null);
    assert.equal(calls.length, 0);
  });

  test('ningún error expone contraseñas ni el token del enlace', async () => {
    respond = () => jsonResponse(400, { code: 'incorrect_password', detail: OLD_PASSWORD });
    const described = JSON.stringify(describePassword(await auth.changePassword(VALUES).catch((caught) => caught)));
    for (const secret of [OLD_PASSWORD, NEW_PASSWORD, RESET_TOKEN]) assert.equal(described.includes(secret), false, secret);
  });
});

describe('rutas de AUTH-03', () => {
  test('/forgot-password es pública (redirige a / con sesión)', () => {
    assert.equal(isPublicPath('/forgot-password'), true);
    assert.equal(routeAccess('/forgot-password', 'anonymous'), 'render');
    assert.equal(routeAccess('/forgot-password', 'authenticated'), 'redirect_home');
  });

  test('/reset-password se muestra con o sin sesión', () => {
    for (const status of ['initializing', 'anonymous', 'checking', 'error', 'authenticated']) {
      assert.equal(routeAccess('/reset-password', status), 'render', status);
    }
  });

  test('/account/change-password es protegida', () => {
    assert.equal(isPublicPath('/account/change-password'), false);
    assert.equal(routeAccess('/account/change-password', 'anonymous'), 'redirect_login');
    assert.equal(routeAccess('/account/change-password', 'authenticated'), 'render');
  });
});
