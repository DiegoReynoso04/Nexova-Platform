// Servicio de autenticación y cuenta contra services/api de Nexova (AUTH-02,
// SPECS.md §9). Contrato: services/api/SPECS.md Parte C §18.
//
// - `login` y `register` comparten `authenticate`: `POST /auth/login` y, solo
//   si la respuesta es válida, guarda el token. Ambos son públicos (sin token).
// - `getCurrentUser` y `updateProfile` son protegidos: lib/api-client.ts
//   adjunta el Bearer y, ante un 401, borra el token (UnauthorizedError).
// - `describeAuthError` traduce cualquier error a mensajes por campo y uno
//   general, para que las vistas no repitan esa lógica.

import { ApiError, UnauthorizedError, ValidationApiError, authApiClient, describeApiError } from '@/lib/api-client';
import { saveAuthToken } from '@/lib/auth-token';
import { normalizeAccessToken, normalizeCurrentUser, normalizeProfile } from '@/services/normalizers';
import type {
  AuthField,
  AuthFormErrors,
  CurrentUser,
  LoginFormValues,
  Profile,
  ProfileFormValues,
  RegisterFormValues,
} from '@/types/auth';

/** El usuario se creó, pero el login posterior falló: debe entrar desde /login. */
export class RegisteredLoginFailedError extends Error {
  constructor() {
    super('Tu cuenta se ha creado, pero no se pudo iniciar sesión. Entra desde la página de acceso.');
    this.name = 'RegisteredLoginFailedError';
  }
}

/** Texto opcional del perfil: recortado; vacío → `null` ("sin dato" en la API). */
function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

/** Formulario OAuth2 de `POST /auth/login`: `username` es el email. */
export function buildLoginForm(values: LoginFormValues): URLSearchParams {
  const form = new URLSearchParams();
  form.set('username', values.email.trim());
  form.set('password', values.password);
  return form;
}

/** Body de `POST /users` (`UserCreate`, sin `role`). Los opcionales vacíos no se envían. */
export function buildRegisterBody(values: RegisterFormValues): Record<string, string> {
  const body: Record<string, string> = { email: values.email.trim(), password: values.password };
  for (const key of ['name', 'phone', 'address'] satisfies (keyof ProfileFormValues)[]) {
    const value = optionalText(values[key]);
    if (value !== null) body[key] = value;
  }
  return body;
}

/** Body de `PUT /profiles/me`: los tres campos, `null` para borrar un dato. */
export function buildProfileBody(values: ProfileFormValues): Record<string, string | null> {
  return { name: optionalText(values.name), phone: optionalText(values.phone), address: optionalText(values.address) };
}

/** Solo campos requeridos (UX). El resto de reglas las valida la API (422). */
export function validateCredentials(values: LoginFormValues): AuthFormErrors | null {
  const fields: AuthFormErrors['fields'] = {};
  if (values.email.trim() === '') fields.email = 'Introduce tu email.';
  if (values.password === '') fields.password = 'Introduce tu contraseña.';
  return Object.keys(fields).length > 0 ? { fields, form: null } : null;
}

async function authenticate(values: LoginFormValues): Promise<void> {
  const data: unknown = await authApiClient.postFormPublic('/auth/login', buildLoginForm(values));
  // El normalizador lanza si no hay un token válido: nunca se guarda uno inválido.
  saveAuthToken(normalizeAccessToken(data).access_token);
}

export async function login(values: LoginFormValues): Promise<void> {
  await authenticate(values);
}

export async function register(values: RegisterFormValues): Promise<void> {
  await authApiClient.postPublic('/users', buildRegisterBody(values));
  try {
    await authenticate(values);
  } catch {
    throw new RegisteredLoginFailedError();
  }
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const data: unknown = await authApiClient.get('/auth/me');
  return normalizeCurrentUser(data);
}

export async function updateProfile(values: ProfileFormValues): Promise<Profile> {
  const data: unknown = await authApiClient.put('/profiles/me', buildProfileBody(values));
  return normalizeProfile(data);
}

const AUTH_FIELDS: readonly AuthField[] = ['email', 'password', 'name', 'phone', 'address'];

// §5.4 — `loc` termina en el nombre del campo del body. El formulario OAuth2
// del login llama `username` al email.
function fieldFromLoc(loc: Array<string | number>): AuthField | null {
  const last = loc[loc.length - 1];
  if (last === 'username') return 'email';
  return AUTH_FIELDS.find((field) => field === last) ?? null;
}

const PYDANTIC_VALUE_ERROR_PREFIX = 'Value error, ';

/**
 * Cualquier error de este servicio → mensajes por campo y uno general.
 * `context`: login (401 = credenciales incorrectas) o cuenta (401 = sesión caducada).
 */
export function describeAuthError(error: unknown, context: 'login' | 'register' | 'account'): AuthFormErrors {
  if (error instanceof ValidationApiError) {
    const fields: AuthFormErrors['fields'] = {};
    const unmatched: string[] = [];
    for (const item of error.detail) {
      const message = item.msg.startsWith(PYDANTIC_VALUE_ERROR_PREFIX)
        ? item.msg.slice(PYDANTIC_VALUE_ERROR_PREFIX.length)
        : item.msg;
      const field = fieldFromLoc(item.loc);
      if (field !== null) fields[field] = fields[field] ? `${fields[field]} ${message}` : message;
      else unmatched.push(message);
    }
    return { fields, form: unmatched.length > 0 ? unmatched.join(' ') : 'Revisa los campos marcados.' };
  }
  if (error instanceof UnauthorizedError) return { fields: {}, form: error.message };
  if (error instanceof ApiError && error.status === 401 && context !== 'account') {
    return { fields: {}, form: 'Email o contraseña incorrectos.' };
  }
  if (error instanceof ApiError && error.status === 409 && context === 'register') {
    return { fields: { email: 'Ya existe una cuenta con este email.' }, form: null };
  }
  if (error instanceof RegisteredLoginFailedError) return { fields: {}, form: error.message };
  return { fields: {}, form: describeApiError(error) };
}
