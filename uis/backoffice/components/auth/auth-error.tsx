import { Alert } from '@/components/ui/alert';
import type { AuthField, AuthFieldError, AuthUiError } from '@/types/auth';

interface ErrorCopy {
  title: string;
  body: string;
}

// Mensajes fijos en español por tipo de error. Solo los errores de validación
// muestran mensajes por campo (los del 422 de la API, tal cual: son reglas del
// modelo, sin datos personales). Nunca se muestra la contraseña ni el token.
function copyFor(error: AuthUiError): ErrorCopy {
  switch (error.kind) {
    case 'validation':
      return error.source === 'api'
        ? { title: 'La API rechazó los datos', body: 'Corrige los campos indicados y vuelve a intentarlo.' }
        : { title: 'Revisa los datos', body: 'Corrige los campos indicados antes de enviar.' };
    case 'invalid_credentials':
      return { title: 'Email o contraseña incorrectos', body: 'Comprueba tus credenciales y vuelve a intentarlo.' };
    case 'registered_login_failed':
      return {
        title: 'Cuenta creada, pero no se pudo iniciar sesión',
        body: 'Tu cuenta ya existe. Inicia sesión desde la página de acceso.',
      };
    case 'session_expired':
      return { title: 'La sesión ha caducado', body: 'Vuelve a iniciar sesión para continuar.' };
    case 'profile_not_found':
      return { title: 'No se encontró tu perfil', body: 'La API no tiene un perfil asociado a esta cuenta.' };
    case 'invalid_reset_token':
      return {
        title: 'El enlace no es válido o ha caducado',
        body: 'Los enlaces para restablecer la contraseña caducan y solo se pueden usar una vez. Solicita uno nuevo.',
      };
    case 'request_invalid':
      return { title: 'La solicitud no es válida', body: 'Revisa los datos e inténtalo de nuevo.' };
    case 'server_error':
      return { title: 'Error del servidor', body: 'La API no pudo completar la operación. Inténtalo de nuevo más tarde.' };
    case 'network':
      return {
        title: 'No se pudo conectar con la API',
        body: 'Comprueba que la API (services/api) está en marcha y es accesible desde este navegador.',
      };
    case 'timeout':
      return { title: 'La operación tardó demasiado', body: 'La API no respondió a tiempo. Inténtalo de nuevo.' };
    case 'unexpected_response':
      return {
        title: 'Respuesta inesperada de la API',
        body: 'La respuesta no tiene el formato esperado, así que no se muestra ningún dato.',
      };
    case 'config':
      return {
        title: 'Falta la configuración del backoffice',
        body: 'La dirección de la API (NEXT_PUBLIC_API_URL) no está configurada.',
      };
  }
}

export const AUTH_FIELD_LABELS: Record<AuthField, string> = {
  email: 'Email',
  password: 'Contraseña',
  name: 'Nombre',
  phone: 'Teléfono',
  address: 'Dirección',
  current_password: 'Contraseña actual',
  new_password: 'Contraseña nueva',
  password_confirmation: 'Confirmación',
};

function describeFieldError(error: AuthFieldError): string {
  return error.field === null ? error.message : `${AUTH_FIELD_LABELS[error.field]}: ${error.message}`;
}

/** Errores de validación de un campo concreto (para mostrarlos junto al campo). */
export function fieldErrorFor(error: AuthUiError | null, field: AuthField): string | null {
  if (error?.kind !== 'validation') return null;
  const messages = error.errors.filter((item) => item.field === field).map((item) => item.message);
  return messages.length > 0 ? messages.join(' ') : null;
}

export interface AuthErrorProps {
  error: AuthUiError;
  id?: string;
}

export function AuthError({ error, id }: AuthErrorProps) {
  const { title, body } = copyFor(error);
  return (
    <Alert variant="error" title={title} id={id}>
      <p>{body}</p>
      {error.kind === 'validation' && error.errors.length > 0 && (
        <ul className="mt-2 list-disc pl-5">
          {error.errors.map((fieldError, index) => (
            <li key={`${fieldError.field ?? 'general'}-${index}`}>{describeFieldError(fieldError)}</li>
          ))}
        </ul>
      )}
    </Alert>
  );
}
