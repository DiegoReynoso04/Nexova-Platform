// services/auth.service.ts: validación en cliente, bodies que se envían y el
// servicio con un cliente HTTP falso (qué se guarda y cómo se traducen los errores).

import { ApiNetworkError, ApiUnauthorizedError } from '@/lib/api-client';
import {
  AuthServiceError,
  buildChangePasswordPayload,
  buildLoginForm,
  buildProfilePayload,
  buildRegisterPayload,
  buildResetPasswordPayload,
  createAuthService,
  validateChangePasswordForm,
  validateForgotPasswordForm,
  validateLoginForm,
  validateRegisterForm,
  validateResetPasswordForm,
} from '@/services/auth.service';
import type { AuthUiError } from '@/types/auth';

import { createFakeApiClient, type Reply } from '../support/fake-api-client';

const PASSWORD = ' clave con espacios ';
const TOKEN_REPLY: Reply = { status: 200, body: { access_token: 'jwt-nuevo', token_type: 'bearer', expires_in: 1800 } };
const EMPTY_PROFILE = { name: '', phone: '', address: '' };

function fieldsOf(errors: readonly { field: string | null }[]): (string | null)[] {
  return errors.map((error) => error.field);
}

// ---------------------------------------------------------------------------
// Validación en cliente: solo requeridos y la confirmación (el resto lo valida la API)
// ---------------------------------------------------------------------------

describe('validateLoginForm / validateRegisterForm', () => {
  test('complete credentials pass', () => {
    expect(validateLoginForm({ email: 'ana@example.invalid', password: PASSWORD })).toEqual([]);
    expect(validateRegisterForm({ email: 'ana@example.invalid', password: PASSWORD, ...EMPTY_PROFILE })).toEqual([]);
  });

  test('a blank email and an empty password are both reported', () => {
    expect(fieldsOf(validateLoginForm({ email: '   ', password: '' }))).toEqual(['email', 'password']);
    expect(fieldsOf(validateRegisterForm({ email: '', password: '', ...EMPTY_PROFILE }))).toEqual(['email', 'password']);
  });
});

describe('validateForgotPasswordForm', () => {
  test('an email passes', () => {
    expect(validateForgotPasswordForm({ email: 'ana@example.invalid' })).toEqual([]);
  });

  test('a blank email is reported', () => {
    expect(fieldsOf(validateForgotPasswordForm({ email: '  ' }))).toEqual(['email']);
  });
});

describe('validateResetPasswordForm', () => {
  test('a new password with a matching confirmation passes', () => {
    expect(validateResetPasswordForm({ new_password: PASSWORD, password_confirmation: PASSWORD })).toEqual([]);
  });

  test('an empty new password or a different confirmation is reported on its field', () => {
    expect(fieldsOf(validateResetPasswordForm({ new_password: '', password_confirmation: '' }))).toEqual(['new_password']);
    // La confirmación se compara tal cual: un espacio de diferencia ya no coincide.
    expect(fieldsOf(validateResetPasswordForm({ new_password: PASSWORD, password_confirmation: PASSWORD.trim() }))).toEqual([
      'password_confirmation',
    ]);
  });
});

describe('validateChangePasswordForm', () => {
  test('current password and a confirmed new password pass', () => {
    expect(
      validateChangePasswordForm({ current_password: 'actual', new_password: PASSWORD, password_confirmation: PASSWORD })
    ).toEqual([]);
  });

  test('a missing current password and a mismatched confirmation are both reported', () => {
    expect(
      fieldsOf(validateChangePasswordForm({ current_password: '', new_password: PASSWORD, password_confirmation: 'otra' }))
    ).toEqual(['current_password', 'password_confirmation']);
  });
});

// ---------------------------------------------------------------------------
// Bodies: qué viaja a la API y qué no
// ---------------------------------------------------------------------------

describe('buildRegisterPayload', () => {
  test('trims the email and the profile fields but sends the password verbatim', () => {
    expect(
      buildRegisterPayload({ email: '  ana@example.invalid ', password: PASSWORD, name: ' Ana ', phone: '', address: '' })
    ).toEqual({ email: 'ana@example.invalid', password: PASSWORD, name: 'Ana' });
  });

  test('never sends a role, and leaves out empty optional fields', () => {
    // El backend fija siempre `role=user`; enviar `role` sería un 422 (D-AUTH-8).
    const payload = buildRegisterPayload({ email: 'ana@example.invalid', password: PASSWORD, ...EMPTY_PROFILE });
    expect(Object.keys(payload).sort()).toEqual(['email', 'password']);
  });
});

describe('buildProfilePayload', () => {
  test('sends the three fields trimmed', () => {
    expect(buildProfilePayload({ name: ' Ana ', phone: '000', address: 'Calle Ejemplo 1' })).toEqual({
      name: 'Ana',
      phone: '000',
      address: 'Calle Ejemplo 1',
    });
  });

  test('a blank field is sent as null, which clears it in the API', () => {
    expect(buildProfilePayload({ name: '   ', phone: '', address: 'x' })).toEqual({ name: null, phone: null, address: 'x' });
  });
});

describe('buildResetPasswordPayload / buildChangePasswordPayload', () => {
  test('send the token or the current password with the new password', () => {
    expect(buildResetPasswordPayload('tok', { new_password: PASSWORD, password_confirmation: PASSWORD })).toEqual({
      token: 'tok',
      new_password: PASSWORD,
    });
    expect(
      buildChangePasswordPayload({ current_password: 'actual', new_password: PASSWORD, password_confirmation: PASSWORD })
    ).toEqual({ current_password: 'actual', new_password: PASSWORD });
  });

  test('never send the confirmation, which only exists in the client', () => {
    expect(buildResetPasswordPayload('tok', { new_password: 'a', password_confirmation: 'b' })).not.toHaveProperty(
      'password_confirmation'
    );
    expect(
      buildChangePasswordPayload({ current_password: 'c', new_password: 'a', password_confirmation: 'b' })
    ).not.toHaveProperty('password_confirmation');
  });
});

describe('buildLoginForm', () => {
  test('sends the trimmed email as OAuth2 `username` and the password verbatim', () => {
    const form = buildLoginForm({ email: ' ana@example.invalid ', password: PASSWORD });
    expect(form.get('username')).toBe('ana@example.invalid');
    expect(form.get('password')).toBe(PASSWORD);
  });

  test('has no `email` field: the API only reads `username`', () => {
    expect([...buildLoginForm({ email: 'ana@example.invalid', password: PASSWORD }).keys()]).toEqual(['username', 'password']);
  });
});

// ---------------------------------------------------------------------------
// createAuthService
// ---------------------------------------------------------------------------

function serviceWith(replies: Record<string, Reply>) {
  const { client, calls } = createFakeApiClient(replies);
  const saved: string[] = [];
  const service = createAuthService({ client, saveToken: (token) => saved.push(token) });
  return { service, calls, saved };
}

async function uiErrorOf(promise: Promise<unknown>): Promise<AuthUiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof AuthServiceError) return error.uiError;
    throw error;
  }
  throw new Error('se esperaba un AuthServiceError');
}

describe('createAuthService — login', () => {
  test('a valid response stores the received token', async () => {
    const { service, saved, calls } = serviceWith({ 'POST /auth/login': TOKEN_REPLY });

    await service.login({ email: 'ana@example.invalid', password: PASSWORD });

    expect(saved).toEqual(['jwt-nuevo']);
    // Petición pública: su 401 significa «credenciales incorrectas», no «sesión caducada».
    expect(calls[0].options.skipAuth).toBe(true);
  });

  test.each([
    ['empty access_token', { access_token: '', token_type: 'bearer', expires_in: 1800 }],
    ['non-integer expires_in', { access_token: 'jwt', token_type: 'bearer', expires_in: 1.5 }],
  ])('a 200 with %s is an unexpected response and nothing is stored', async (_case, body) => {
    const { service, saved } = serviceWith({ 'POST /auth/login': { status: 200, body } });

    expect(await uiErrorOf(service.login({ email: 'ana@example.invalid', password: PASSWORD }))).toEqual({
      kind: 'unexpected_response',
    });
    expect(saved).toEqual([]);
  });

  test('wrong credentials are reported as such and nothing is stored', async () => {
    const { service, saved } = serviceWith({
      'POST /auth/login': { status: 401, body: { detail: 'incorrect email or password', code: 'invalid_credentials' } },
    });

    expect(await uiErrorOf(service.login({ email: 'ana@example.invalid', password: PASSWORD }))).toEqual({
      kind: 'invalid_credentials',
    });
    expect(saved).toEqual([]);
  });

  test('missing fields fail in the client without any request', async () => {
    const { service, calls } = serviceWith({});

    const error = await uiErrorOf(service.login({ email: '', password: '' }));

    expect(error.kind).toBe('validation');
    expect(calls).toEqual([]);
  });

  test('a network failure becomes a `network` error, never a raw exception', async () => {
    const { service } = serviceWith({ 'POST /auth/login': new ApiNetworkError() });
    expect(await uiErrorOf(service.login({ email: 'ana@example.invalid', password: PASSWORD }))).toEqual({ kind: 'network' });
  });
});

describe('createAuthService — register', () => {
  test('creates the account and then logs in with the same credentials', async () => {
    const { service, saved, calls } = serviceWith({ 'POST /users': { status: 201, body: {} }, 'POST /auth/login': TOKEN_REPLY });

    await service.register({ email: 'ana@example.invalid', password: PASSWORD, ...EMPTY_PROFILE });

    expect(calls.map((call) => call.key)).toEqual(['POST /users', 'POST /auth/login']);
    expect(saved).toEqual(['jwt-nuevo']);
  });

  test('an already registered email is shown on the email field and no login is attempted', async () => {
    const { service, calls } = serviceWith({
      'POST /users': { status: 409, body: { detail: 'email already registered', code: 'email_already_registered' } },
    });

    const error = await uiErrorOf(service.register({ email: 'ana@example.invalid', password: PASSWORD, ...EMPTY_PROFILE }));

    expect(error).toMatchObject({ kind: 'validation', source: 'api', errors: [{ field: 'email' }] });
    expect(calls.map((call) => call.key)).toEqual(['POST /users']);
  });
});

describe('createAuthService — register (API rejections)', () => {
  test('a 422 from the API is shown next to its field', async () => {
    const detail = [{ loc: ['body', 'password'], msg: 'Value error, password must have at least 8 characters', type: 'value_error' }];
    const { service } = serviceWith({ 'POST /users': { status: 422, body: { detail, code: 'validation_error' } } });

    const error = await uiErrorOf(service.register({ email: 'ana@example.invalid', password: 'corta', ...EMPTY_PROFILE }));

    expect(error).toEqual({
      kind: 'validation',
      source: 'api',
      errors: [{ field: 'password', message: 'password must have at least 8 characters' }],
    });
  });

  test('if the account is created but the follow-up login fails, the user is told to log in', async () => {
    // La cuenta ya existe: repetir el registro daría «email ya registrado».
    const { service, saved } = serviceWith({ 'POST /users': { status: 201, body: {} }, 'POST /auth/login': new ApiNetworkError() });

    expect(await uiErrorOf(service.register({ email: 'ana@example.invalid', password: PASSWORD, ...EMPTY_PROFILE }))).toEqual({
      kind: 'registered_login_failed',
    });
    expect(saved).toEqual([]);
  });
});

describe('createAuthService — passwords', () => {
  test('reset with a valid link sends the token and the new password', async () => {
    const { service, calls } = serviceWith({ 'POST /auth/reset-password': { status: 200, body: { detail: 'password updated' } } });

    await service.resetPassword('tok', { new_password: PASSWORD, password_confirmation: PASSWORD });

    expect(calls[0].body).toEqual({ token: 'tok', new_password: PASSWORD });
  });

  test('reset without a token in the URL is an invalid link and makes no request', async () => {
    const { service, calls } = serviceWith({});
    expect(await uiErrorOf(service.resetPassword('  ', { new_password: PASSWORD, password_confirmation: PASSWORD }))).toEqual({
      kind: 'invalid_reset_token',
    });
    expect(calls).toEqual([]);
  });

  test('a wrong current password is shown on its field, not as an expired session', async () => {
    const { service } = serviceWith({
      'POST /auth/change-password': { status: 400, body: { detail: 'current password is incorrect', code: 'incorrect_password' } },
    });

    const error = await uiErrorOf(
      service.changePassword({ current_password: 'mal', new_password: PASSWORD, password_confirmation: PASSWORD })
    );

    expect(error).toMatchObject({ kind: 'validation', errors: [{ field: 'current_password' }] });
  });
});

describe('createAuthService — account', () => {
  test('getCurrentUser returns the normalized user', async () => {
    const me = { id: 'u-1', email: 'ana@example.invalid', role: 'user', created_at: '2026-10-01T10:00:00Z', profile: null };
    const { service, calls } = serviceWith({ 'GET /auth/me': { status: 200, body: me } });

    expect(await service.getCurrentUser()).toEqual(me);
    // Petición protegida: el cliente adjunta el Bearer.
    expect(calls[0].options.skipAuth).toBeUndefined();
  });

  test('a 401 on a protected request is an expired session', async () => {
    // lib/api-client.ts ya borró el token; el servicio solo lo traduce.
    const { service } = serviceWith({ 'GET /auth/me': new ApiUnauthorizedError() });
    expect(await uiErrorOf(service.getCurrentUser())).toEqual({ kind: 'session_expired' });
  });

  test('updateProfile sends the trimmed fields and returns the saved profile', async () => {
    const profile = { name: 'Ana', phone: null, address: null };
    const { service, calls } = serviceWith({ 'PUT /profiles/me': { status: 200, body: profile } });

    expect(await service.updateProfile({ name: ' Ana ', phone: '', address: '' })).toEqual(profile);
    expect(calls[0].body).toEqual({ name: 'Ana', phone: null, address: null });
  });

  test('updateProfile for a user without profile reports it explicitly', async () => {
    const { service } = serviceWith({
      'PUT /profiles/me': { status: 404, body: { detail: 'profile not found', code: 'profile_not_found' } },
    });
    expect(await uiErrorOf(service.updateProfile(EMPTY_PROFILE))).toEqual({ kind: 'profile_not_found' });
  });

  test('requestPasswordReset sends the trimmed email as a public request', async () => {
    const { service, calls } = serviceWith({ 'POST /auth/forgot-password': { status: 200, body: { detail: 'ok' } } });

    await service.requestPasswordReset({ email: ' ana@example.invalid ' });

    expect(calls[0]).toMatchObject({ body: { email: 'ana@example.invalid' }, options: { skipAuth: true } });
  });

  test('requestPasswordReset with a server error says so, without details', async () => {
    const { service } = serviceWith({ 'POST /auth/forgot-password': { status: 500, body: { detail: 'boom', code: 'internal_error' } } });
    expect(await uiErrorOf(service.requestPasswordReset({ email: 'ana@example.invalid' }))).toEqual({ kind: 'server_error' });
  });
});
