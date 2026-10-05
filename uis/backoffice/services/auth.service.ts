// Servicio de autenticación y cuenta (AUTH-02): única capa que llama al
// cliente HTTP para login, registro, usuario actual y perfil. Contrato:
// services/api/SPECS.md Parte C (§17–§18) y §4 (formato de errores).
//
// - `login` y `register` comparten `authenticate`: `POST /auth/login` y, si va
//   bien, guarda el token. Un token inválido o un login fallido nunca se guardan.
// - Login y registro son peticiones públicas (`skipAuth`): su 401 significa
//   "credenciales incorrectas", no "sesión caducada".
// - `getCurrentUser` y `updateProfile` son protegidas: el cliente adjunta el
//   Bearer y, ante un 401, borra el token (ver lib/api-client.ts).
//
// Todo error que sale de aquí es `AuthServiceError` (con un `AuthUiError`
// para mostrar), salvo la cancelación pedida por quien llama (`ApiAbortError`).
// Las contraseñas no se guardan ni aparecen en ningún error.

import {
  ApiAbortError,
  ApiConfigError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiUnauthorizedError,
  ApiUnexpectedResponseError,
  apiClient,
  type ApiClient,
  type ApiResponse,
  type JsonValue,
} from '@/lib/api-client';
import { saveAuthToken } from '@/lib/auth-token';
import {
  normalizeAccessToken,
  normalizeApiErrorBody,
  normalizeAuthValidationErrors,
  normalizeCurrentUser,
  normalizeProfile,
} from '@/services/normalizers';
import type {
  AuthFieldError,
  AuthUiError,
  CurrentUser,
  LoginFormValues,
  Profile,
  ProfileFormValues,
  RegisterFormValues,
} from '@/types/auth';

const LOGIN_PATH = '/auth/login';
const USERS_PATH = '/users';
const CURRENT_USER_PATH = '/auth/me';
const MY_PROFILE_PATH = '/profiles/me';
export const AUTH_TIMEOUT_MS = 10_000;

/** Error del servicio con un `AuthUiError`. El mensaje solo lleva el tipo de error. */
export class AuthServiceError extends Error {
  readonly uiError: AuthUiError;

  constructor(uiError: AuthUiError) {
    super(`Auth service error: ${uiError.kind}`);
    this.name = 'AuthServiceError';
    this.uiError = uiError;
  }
}

export interface CallOptions {
  signal?: AbortSignal;
}

export interface AuthService {
  /** `POST /auth/login` y guarda el token. */
  login(values: LoginFormValues, options?: CallOptions): Promise<void>;
  /** `POST /users` y, después, `POST /auth/login` con las mismas credenciales. */
  register(values: RegisterFormValues, options?: CallOptions): Promise<void>;
  /** `GET /auth/me`. */
  getCurrentUser(options?: CallOptions): Promise<CurrentUser>;
  /** `PUT /profiles/me` con nombre, teléfono y dirección. */
  updateProfile(values: ProfileFormValues, options?: CallOptions): Promise<Profile>;
}

export interface AuthServiceDependencies {
  client?: ApiClient;
  /** Dónde guardar el token tras un login correcto; por defecto `localStorage`. */
  saveToken?: (token: string) => void;
  /** Solo para tests; en producción se usa AUTH_TIMEOUT_MS. */
  timeoutMs?: number;
}

// ---------------------------------------------------------------------------
// Validación en cliente y construcción del body
// ---------------------------------------------------------------------------

/** Solo campos requeridos (UX). El formato del email y la longitud de la contraseña los valida la API. */
export function validateLoginForm(values: LoginFormValues): AuthFieldError[] {
  const errors: AuthFieldError[] = [];
  if (values.email.trim() === '') errors.push({ field: 'email', message: 'Introduce tu email.' });
  if (values.password === '') errors.push({ field: 'password', message: 'Introduce tu contraseña.' });
  return errors;
}

export function validateRegisterForm(values: RegisterFormValues): AuthFieldError[] {
  return validateLoginForm(values);
}

/** Texto opcional del perfil: recortado; vacío → `null` (la API lo guarda como "sin dato"). */
function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

/** Body de `POST /users`: `UserCreate` sin `role` (el backend fija siempre `user`). Opcionales vacíos no se envían. */
export function buildRegisterPayload(values: RegisterFormValues): { [key: string]: JsonValue } {
  const payload: { [key: string]: JsonValue } = { email: values.email.trim(), password: values.password };
  for (const key of ['name', 'phone', 'address'] satisfies readonly (keyof ProfileFormValues)[]) {
    const value = optionalText(values[key]);
    if (value !== null) payload[key] = value;
  }
  return payload;
}

/** Body de `PUT /profiles/me`: los tres campos, `null` para borrar un dato. */
export function buildProfilePayload(values: ProfileFormValues): { [key: string]: JsonValue } {
  return { name: optionalText(values.name), phone: optionalText(values.phone), address: optionalText(values.address) };
}

/** Formulario OAuth2 de `POST /auth/login`: `username` es el email. */
export function buildLoginForm(values: LoginFormValues): URLSearchParams {
  const form = new URLSearchParams();
  form.set('username', values.email.trim());
  form.set('password', values.password);
  return form;
}

// ---------------------------------------------------------------------------
// Traducción de errores
// ---------------------------------------------------------------------------

function fail(uiError: AuthUiError): AuthServiceError {
  return new AuthServiceError(uiError);
}

function clientValidation(errors: readonly AuthFieldError[]): AuthServiceError {
  return fail({ kind: 'validation', source: 'client', errors });
}

async function readJsonOrNull<T>(response: ApiResponse, parse: (body: JsonValue) => T): Promise<T | null> {
  try {
    return await response.json(parse);
  } catch (error) {
    if (error instanceof ApiUnexpectedResponseError) return null;
    throw error;
  }
}

/** Status + cuerpo de error → `AuthUiError`. Manda el status; el `code` solo distingue casos concretos. */
async function failFromResponse(response: ApiResponse): Promise<never> {
  const { status } = response;
  if (status === 422) {
    const errors = (await readJsonOrNull(response, normalizeAuthValidationErrors)) ?? [];
    throw fail(errors.length > 0 ? { kind: 'validation', source: 'api', errors } : { kind: 'request_invalid' });
  }
  const body = await readJsonOrNull(response, normalizeApiErrorBody);
  if (status === 401 && body?.code === 'invalid_credentials') throw fail({ kind: 'invalid_credentials' });
  if (status === 409 && body?.code === 'email_already_registered') {
    throw fail({
      kind: 'validation',
      source: 'api',
      errors: [{ field: 'email', message: 'Ya existe una cuenta con este email.' }],
    });
  }
  if (status === 404 && body?.code === 'profile_not_found') throw fail({ kind: 'profile_not_found' });
  if (status >= 500) throw fail({ kind: 'server_error' });
  if (status >= 400) throw fail({ kind: 'request_invalid' });
  throw fail({ kind: 'unexpected_response' });
}

/** Ejecuta una operación y garantiza que solo salen AuthServiceError o ApiAbortError. */
async function guarded<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof AuthServiceError || error instanceof ApiAbortError) throw error;
    if (error instanceof ApiUnauthorizedError) throw fail({ kind: 'session_expired' });
    if (error instanceof ApiConfigError) throw fail({ kind: 'config' });
    if (error instanceof ApiTimeoutError) throw fail({ kind: 'timeout' });
    if (error instanceof ApiNetworkError) throw fail({ kind: 'network' });
    throw fail({ kind: 'unexpected_response' });
  }
}

// ---------------------------------------------------------------------------
// Servicio
// ---------------------------------------------------------------------------

export function createAuthService(dependencies: AuthServiceDependencies = {}): AuthService {
  const client = dependencies.client ?? apiClient;
  const saveToken = dependencies.saveToken ?? saveAuthToken;
  const timeoutMs = dependencies.timeoutMs ?? AUTH_TIMEOUT_MS;

  function expect<T>(successStatus: number, parse: (body: JsonValue) => T) {
    return async (response: ApiResponse): Promise<T> => {
      if (response.status !== successStatus) return failFromResponse(response);
      return response.json(parse);
    };
  }

  /** Login común a `/login` y `/register`: el token solo se guarda si la respuesta es válida. */
  async function authenticate(values: LoginFormValues, options: CallOptions): Promise<void> {
    const token = await client.postForm(
      LOGIN_PATH,
      buildLoginForm(values),
      { timeoutMs, signal: options.signal, skipAuth: true },
      expect(200, normalizeAccessToken)
    );
    saveToken(token.access_token);
  }

  return {
    login(values, options = {}) {
      return guarded(async () => {
        const errors = validateLoginForm(values);
        if (errors.length > 0) throw clientValidation(errors);
        await authenticate(values, options);
      });
    },

    register(values, options = {}) {
      return guarded(async () => {
        const errors = validateRegisterForm(values);
        if (errors.length > 0) throw clientValidation(errors);
        await client.postJson(
          USERS_PATH,
          buildRegisterPayload(values),
          { timeoutMs, signal: options.signal, skipAuth: true },
          expect(201, () => null)
        );
        try {
          await authenticate(values, options);
        } catch (error) {
          if (error instanceof ApiAbortError) throw error;
          // La cuenta ya existe: el usuario debe entrar desde /login.
          throw fail({ kind: 'registered_login_failed' });
        }
      });
    },

    getCurrentUser(options = {}) {
      return guarded(() =>
        client.get(CURRENT_USER_PATH, { timeoutMs, signal: options.signal }, expect(200, normalizeCurrentUser))
      );
    },

    updateProfile(values, options = {}) {
      return guarded(() =>
        client.putJson(
          MY_PROFILE_PATH,
          buildProfilePayload(values),
          { timeoutMs, signal: options.signal },
          expect(200, normalizeProfile)
        )
      );
    },
  };
}

const defaultService = createAuthService();

export const login: AuthService['login'] = (values, options) => defaultService.login(values, options);
export const register: AuthService['register'] = (values, options) => defaultService.register(values, options);
export const getCurrentUser: AuthService['getCurrentUser'] = (options) => defaultService.getCurrentUser(options);
export const updateProfile: AuthService['updateProfile'] = (values, options) =>
  defaultService.updateProfile(values, options);
