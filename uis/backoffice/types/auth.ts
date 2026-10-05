// Contrato de autenticación que recibe y envía el backoffice (AUTH-02).
// Fuente: services/api/SPECS.md Parte C (§17–§18) y app/auth/models.py.
// Prohibido añadir campos que no estén en ese contrato.

export const USER_ROLES = ['admin', 'manager', 'user'] as const;
export type UserRole = (typeof USER_ROLES)[number];

/** Respuesta 200 de `POST /auth/login`. Solo se usa `access_token`. */
export interface AccessToken {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/** `Profile` (`GET /profiles/me`, `PUT /profiles/me` y dentro de `GET /auth/me`). */
export interface Profile {
  id: string;
  user_id: string;
  name: string | null;
  phone: string | null;
  address: string | null;
}

/** Respuesta 200 de `GET /auth/me`: credenciales públicas + perfil vinculado. */
export interface CurrentUser {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  profile: Profile | null;
}

/** Formulario de `/login` (el email viaja como `username` del formulario OAuth2). */
export interface LoginFormValues {
  email: string;
  password: string;
}

/** Formulario de `/register`: los campos de `UserCreate` (sin `role`). */
export interface RegisterFormValues {
  email: string;
  password: string;
  name: string;
  phone: string;
  address: string;
}

/** Formulario de `/account/profile`: los campos editables de `ProfileUpdate`. */
export interface ProfileFormValues {
  name: string;
  phone: string;
  address: string;
}

export type AuthField = 'email' | 'password' | 'name' | 'phone' | 'address';

/** Error de validación por campo (`null` = no corresponde a un campo concreto). */
export interface AuthFieldError {
  field: AuthField | null;
  message: string;
}

/** Errores que las vistas de autenticación y de cuenta saben presentar. */
export type AuthUiError =
  | { kind: 'validation'; source: 'client' | 'api'; errors: readonly AuthFieldError[] }
  | { kind: 'invalid_credentials' }
  /** El usuario se creó, pero el login posterior falló: debe entrar desde /login. */
  | { kind: 'registered_login_failed' }
  | { kind: 'session_expired' }
  | { kind: 'profile_not_found' }
  | { kind: 'request_invalid' }
  | { kind: 'server_error' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' };
