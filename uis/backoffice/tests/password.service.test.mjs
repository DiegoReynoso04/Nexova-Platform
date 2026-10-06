// AUTH-03 — recuperación y cambio de contraseña en services/auth.service.ts,
// contra services/api/SPECS.md Parte C §23, con transporte falso.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { createApiClient } from '../lib/api-client.ts';
import {
  AuthServiceError,
  createAuthService,
  validateChangePasswordForm,
  validateResetPasswordForm,
} from '../services/auth.service.ts';
import { normalizeAuthValidationErrors } from '../services/normalizers.ts';
import { BASE_URL, LEAK, jsonResponse, recordingFetch } from './support/http-fakes.mjs';

const OLD_PASSWORD = 'contraseña-actual-1';
const NEW_PASSWORD = 'contraseña-nueva-2';
const RESET_TOKEN = 'tok_enlace_123';
const UPDATED = { detail: 'password updated' };

/** Servicio con transporte falso. `routes`: "MÉTODO /ruta" → respuesta. */
function serviceWith(routes, { token = 'jwt-guardado' } = {}) {
  const transport = recordingFetch((url, init) => {
    const key = `${init.method} ${url.slice(BASE_URL.length)}`;
    const make = routes[key];
    if (make === undefined) throw new Error(`ruta no prevista: ${key}`);
    return make(init);
  });
  let cleared = 0;
  const client = createApiClient({
    fetch: transport.fetch,
    getBaseUrl: () => BASE_URL,
    getToken: () => token,
    onUnauthorized: () => (cleared += 1),
  });
  return { service: createAuthService({ client, saveToken: () => {} }), transport, cleared: () => cleared };
}

function expectUiError(expected) {
  return (error) => {
    assert.ok(error instanceof AuthServiceError, `expected AuthServiceError, got ${error?.name}`);
    assert.deepEqual(error.uiError, expected);
    const exposed = [error.message, String(error), JSON.stringify(error)].join(' ');
    for (const secret of [OLD_PASSWORD, NEW_PASSWORD, RESET_TOKEN, LEAK]) {
      assert.equal(exposed.includes(secret), false, `error exposes ${secret}`);
    }
    return true;
  };
}

describe('POST /auth/forgot-password', () => {
  test('envía solo el email, sin token de sesión', async () => {
    const { service, transport } = serviceWith({
      'POST /auth/forgot-password': () => jsonResponse(200, { detail: 'if that email is registered, a reset link has been sent' }),
    });
    await service.requestPasswordReset({ email: '  ana@nexova.test ' });
    const [{ init }] = transport.calls;
    assert.deepEqual(JSON.parse(init.body), { email: 'ana@nexova.test' });
    assert.equal(init.headers.Authorization, undefined);
  });

  test('email vacío → validación en cliente, sin petición', async () => {
    const { service, transport } = serviceWith({});
    await assert.rejects(
      service.requestPasswordReset({ email: '  ' }),
      expectUiError({ kind: 'validation', source: 'client', errors: [{ field: 'email', message: 'Introduce tu email.' }] })
    );
    assert.equal(transport.calls.length, 0);
  });

  test('422 por formato → error en el campo email; fallo del servidor → server_error', async () => {
    let h = serviceWith({
      'POST /auth/forgot-password': () =>
        jsonResponse(422, { detail: [{ loc: ['body', 'email'], msg: 'Value error, email must be a valid email address' }] }),
    });
    await assert.rejects(
      h.service.requestPasswordReset({ email: 'no-es-email' }),
      expectUiError({
        kind: 'validation',
        source: 'api',
        errors: [{ field: 'email', message: 'email must be a valid email address' }],
      })
    );
    h = serviceWith({ 'POST /auth/forgot-password': () => jsonResponse(500, { code: 'internal_error', detail: LEAK }) });
    await assert.rejects(h.service.requestPasswordReset({ email: 'ana@nexova.test' }), expectUiError({ kind: 'server_error' }));
  });
});

describe('POST /auth/reset-password', () => {
  const VALUES = { new_password: NEW_PASSWORD, password_confirmation: NEW_PASSWORD };

  test('envía token y contraseña nueva (sin la confirmación ni token de sesión)', async () => {
    const { service, transport } = serviceWith({ 'POST /auth/reset-password': () => jsonResponse(200, UPDATED) });
    await service.resetPassword(RESET_TOKEN, VALUES);
    const [{ init }] = transport.calls;
    assert.deepEqual(JSON.parse(init.body), { token: RESET_TOKEN, new_password: NEW_PASSWORD });
    assert.equal(init.headers.Authorization, undefined);
  });

  test('400 invalid_reset_token → invalid_reset_token (inválido, caducado o ya usado)', async () => {
    const { service, cleared } = serviceWith({
      'POST /auth/reset-password': () =>
        jsonResponse(400, { code: 'invalid_reset_token', detail: 'reset token is invalid, expired or already used' }),
    });
    await assert.rejects(service.resetPassword(RESET_TOKEN, VALUES), expectUiError({ kind: 'invalid_reset_token' }));
    assert.equal(cleared(), 0, 'una petición pública no toca la sesión');
  });

  test('sin token en la URL → invalid_reset_token sin petición', async () => {
    const { service, transport } = serviceWith({});
    await assert.rejects(service.resetPassword('', VALUES), expectUiError({ kind: 'invalid_reset_token' }));
    assert.equal(transport.calls.length, 0);
  });

  test('confirmación distinta → error en cliente, sin petición', async () => {
    const { service, transport } = serviceWith({});
    await assert.rejects(
      service.resetPassword(RESET_TOKEN, { new_password: NEW_PASSWORD, password_confirmation: 'otra-cosa' }),
      expectUiError({
        kind: 'validation',
        source: 'client',
        errors: [{ field: 'password_confirmation', message: 'La confirmación no coincide con la contraseña nueva.' }],
      })
    );
    assert.equal(transport.calls.length, 0);
  });

  test('422 de la contraseña nueva → error en su campo', async () => {
    const { service } = serviceWith({
      'POST /auth/reset-password': () =>
        jsonResponse(422, { detail: [{ loc: ['body', 'new_password'], msg: 'Value error, password must have at least 8 characters' }] }),
    });
    await assert.rejects(
      service.resetPassword(RESET_TOKEN, { new_password: 'corta', password_confirmation: 'corta' }),
      expectUiError({
        kind: 'validation',
        source: 'api',
        errors: [{ field: 'new_password', message: 'password must have at least 8 characters' }],
      })
    );
  });
});

describe('POST /auth/change-password', () => {
  const VALUES = { current_password: OLD_PASSWORD, new_password: NEW_PASSWORD, password_confirmation: NEW_PASSWORD };

  test('con Bearer, contraseña actual y nueva (sin la confirmación)', async () => {
    const { service, transport } = serviceWith({ 'POST /auth/change-password': () => jsonResponse(200, UPDATED) });
    await service.changePassword(VALUES);
    const [{ init }] = transport.calls;
    assert.equal(init.headers.Authorization, 'Bearer jwt-guardado');
    assert.deepEqual(JSON.parse(init.body), { current_password: OLD_PASSWORD, new_password: NEW_PASSWORD });
  });

  test('400 incorrect_password → error en el campo contraseña actual, sin cerrar la sesión', async () => {
    const { service, cleared } = serviceWith({
      'POST /auth/change-password': () => jsonResponse(400, { code: 'incorrect_password', detail: 'current password is incorrect' }),
    });
    await assert.rejects(
      service.changePassword(VALUES),
      expectUiError({
        kind: 'validation',
        source: 'api',
        errors: [{ field: 'current_password', message: 'La contraseña actual no es correcta.' }],
      })
    );
    assert.equal(cleared(), 0);
  });

  test('confirmación distinta → error en cliente, sin petición', async () => {
    const { service, transport } = serviceWith({});
    await assert.rejects(
      service.changePassword({ ...VALUES, password_confirmation: 'otra-cosa' }),
      expectUiError({
        kind: 'validation',
        source: 'client',
        errors: [{ field: 'password_confirmation', message: 'La confirmación no coincide con la contraseña nueva.' }],
      })
    );
    assert.equal(transport.calls.length, 0);
  });

  test('401 → session_expired y el cliente borra la sesión', async () => {
    const { service, cleared } = serviceWith({
      'POST /auth/change-password': () => jsonResponse(401, { code: 'not_authenticated', detail: LEAK }),
    });
    await assert.rejects(service.changePassword(VALUES), expectUiError({ kind: 'session_expired' }));
    assert.equal(cleared(), 1);
  });
});

describe('validación de los formularios de contraseña', () => {
  test('reset: contraseña nueva requerida y confirmación coincidente', () => {
    assert.deepEqual(validateResetPasswordForm({ new_password: '', password_confirmation: '' }), [
      { field: 'new_password', message: 'Introduce la contraseña nueva.' },
    ]);
    assert.deepEqual(validateResetPasswordForm({ new_password: 'abc', password_confirmation: 'abc' }), []);
  });

  test('cambio: también exige la contraseña actual', () => {
    assert.deepEqual(validateChangePasswordForm({ current_password: '', new_password: 'abc', password_confirmation: 'abd' }), [
      { field: 'current_password', message: 'Introduce tu contraseña actual.' },
      { field: 'password_confirmation', message: 'La confirmación no coincide con la contraseña nueva.' },
    ]);
  });

  test('los 422 de current_password y new_password se asignan a su campo', () => {
    assert.deepEqual(
      normalizeAuthValidationErrors({
        detail: [
          { loc: ['body', 'current_password'], msg: 'Field required' },
          { loc: ['body', 'new_password'], msg: 'Field required' },
          { loc: ['body', 'password_confirmation'], msg: 'no la envía el cliente' },
        ],
      }),
      [
        { field: 'current_password', message: 'Field required' },
        { field: 'new_password', message: 'Field required' },
        { field: null, message: 'no la envía el cliente' },
      ]
    );
  });
});
