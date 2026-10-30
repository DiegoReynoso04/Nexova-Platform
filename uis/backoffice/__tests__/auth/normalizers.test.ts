// services/normalizers.ts (parte de autenticación): única frontera donde entra
// `unknown` de la red. Valida la forma del contrato y copia solo campos conocidos.

import {
  UnexpectedResponseError,
  normalizeAccessToken,
  normalizeAuthValidationErrors,
  normalizeCurrentUser,
  normalizeProfile,
} from '@/services/normalizers';

const PROFILE = { name: 'Ana', phone: null, address: null };
const ME = { id: 'u-1', email: 'ana@example.invalid', role: 'user', created_at: '2026-10-01T10:00:00Z', profile: PROFILE };

describe('normalizeAccessToken', () => {
  test('accepts the login response', () => {
    expect(normalizeAccessToken({ access_token: 'jwt', token_type: 'bearer', expires_in: 1800 })).toEqual({
      access_token: 'jwt',
      token_type: 'bearer',
      expires_in: 1800,
    });
  });

  test.each([
    ['empty token', { access_token: '', token_type: 'bearer', expires_in: 1800 }],
    ['blank token', { access_token: '   ', token_type: 'bearer', expires_in: 1800 }],
    ['non-integer expires_in', { access_token: 'jwt', token_type: 'bearer', expires_in: 1.5 }],
    ['expires_in as text', { access_token: 'jwt', token_type: 'bearer', expires_in: '1800' }],
    ['not an object', ['jwt']],
  ])('rejects a response with %s', (_case, body) => {
    // Un token inválido nunca debe llegar a guardarse como sesión.
    expect(() => normalizeAccessToken(body)).toThrow(UnexpectedResponseError);
  });
});

describe('normalizeCurrentUser', () => {
  test('accepts the user with and without profile', () => {
    expect(normalizeCurrentUser(ME)).toEqual(ME);
    expect(normalizeCurrentUser({ ...ME, profile: null }).profile).toBeNull();
  });

  test('copies only contract fields, so a leaked credential never reaches the UI state', () => {
    expect(normalizeCurrentUser({ ...ME, hashed_password: '$2b$12$x' })).not.toHaveProperty('hashed_password');
  });

  test('drops the fields the API no longer sends, even if an old server still does', () => {
    // Auditoría de serialización (D2, D3): `/auth/me` sin `is_active` y el perfil sin `id` ni `user_id`.
    const legacy = { ...ME, is_active: true, profile: { ...PROFILE, id: 'p-1', user_id: 'u-1' } };
    expect(normalizeCurrentUser(legacy)).toEqual(ME);
  });

  test.each([
    ['an unknown role', { ...ME, role: 'superadmin' }],
    ['created_at as a number', { ...ME, created_at: 0 }],
    ['a malformed profile', { ...ME, profile: { ...PROFILE, name: 7 } }],
  ])('rejects a user with %s', (_case, body) => {
    expect(() => normalizeCurrentUser(body)).toThrow(UnexpectedResponseError);
  });

  test('the error names the field but never echoes received values', () => {
    expect(() => normalizeCurrentUser({ ...ME, email: 12345 })).toThrow(/response\.email/);
    expect(() => normalizeCurrentUser({ ...ME, email: 12345 })).not.toThrow(/12345/);
  });
});

describe('normalizeProfile', () => {
  test('accepts a profile with empty fields as null', () => {
    expect(normalizeProfile(PROFILE)).toEqual(PROFILE);
  });

  test('rejects a profile with a field of the wrong type', () => {
    expect(() => normalizeProfile({ ...PROFILE, name: 42 })).toThrow(UnexpectedResponseError);
  });
});

describe('normalizeAuthValidationErrors', () => {
  test('maps each 422 entry to its form field and strips the Pydantic prefix', () => {
    const detail = [
      { loc: ['body', 'username'], msg: 'Field required', type: 'missing' },
      { loc: ['body', 'new_password'], msg: 'Value error, password must have at least 8 characters', type: 'value_error' },
    ];
    expect(normalizeAuthValidationErrors({ detail })).toEqual([
      // El formulario OAuth2 del login llama `username` al email.
      { field: 'email', message: 'Field required' },
      { field: 'new_password', message: 'password must have at least 8 characters' },
    ]);
  });

  test('a field outside the form (or the client-only confirmation) has no field', () => {
    const detail = [
      { loc: ['body', 'password_confirmation'], msg: 'x', type: 'x' },
      { loc: ['body'], msg: 'Invalid JSON', type: 'json_invalid' },
    ];
    expect(normalizeAuthValidationErrors({ detail }).map((error) => error.field)).toEqual([null, null]);
  });

  test.each([null, 'texto', { detail: 'no es una lista' }, { detail: [{ loc: 'x', msg: 1 }] }])(
    'malformed input %p yields no errors instead of throwing',
    (input) => {
      expect(normalizeAuthValidationErrors(input)).toEqual([]);
    }
  );
});
