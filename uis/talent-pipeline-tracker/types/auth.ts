// Contrato de autenticación con services/api de Nexova (AUTH-02 y AUTH-03, SPECS.md §9).
// Fuente: services/api/SPECS.md Parte C (§17–§18, §23). No es la API de 4Geeks:
// prohibido añadir campos que no estén en ese contrato.

export const USER_ROLES = ['admin', 'manager', 'user'] as const;
export type UserRole = (typeof USER_ROLES)[number];

/** Respuesta 200 de `POST /auth/login`. Solo se usa `access_token`. */
export interface AccessToken {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/** `Profile` (`PUT /profiles/me` y dentro de `GET /auth/me`). */
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

export interface LoginFormValues {
  email: string;
  password: string;
}

/** Campos de `UserCreate` (sin `role`: el backend fija siempre `user`). */
export interface RegisterFormValues extends LoginFormValues {
  name: string;
  phone: string;
  address: string;
}

/** Campos editables de `ProfileUpdate`. */
export interface ProfileFormValues {
  name: string;
  phone: string;
  address: string;
}

/** Formulario de `/forgot-password` (`POST /auth/forgot-password`). */
export interface ForgotPasswordFormValues {
  email: string;
}

/** Formulario de `/reset-password`. El token no es un campo: viene de la URL. */
export interface ResetPasswordFormValues {
  new_password: string;
  password_confirmation: string;
}

/** Formulario de `/account/change-password` (`POST /auth/change-password`). */
export interface ChangePasswordFormValues extends ResetPasswordFormValues {
  current_password: string;
}

/** `password_confirmation` solo existe en el cliente: la API no la recibe. */
export type AuthField =
  | 'email'
  | 'password'
  | 'name'
  | 'phone'
  | 'address'
  | 'current_password'
  | 'new_password'
  | 'password_confirmation';

/** Errores de un formulario de cuenta: por campo y uno general. */
export interface AuthFormErrors {
  fields: Partial<Record<AuthField, string>>;
  form: string | null;
  /** AUTH-03: el enlace de restablecimiento falta, no es válido, caducó o ya se usó. */
  invalidResetToken?: boolean;
}
