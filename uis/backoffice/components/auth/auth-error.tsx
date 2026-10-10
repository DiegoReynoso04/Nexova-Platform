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
        ? { title: 'El servidor rechazó los datos', body: 'Corrige los campos indicados y vuelve a intentarlo.' }
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
      return { title: 'No se encontró tu perfil', body: 'Tu cuenta no tiene un perfil asociado. Avisa al equipo técnico.' };
    case 'invalid_reset_token':
      return {
        title: 'El enlace no es válido o ha caducado',
        body: 'Los enlaces para restablecer la contraseña caducan y solo se pueden usar una vez. Solicita uno nuevo.',
      };
    case 'request_invalid':
      return { title: 'La solicitud no es válida', body: 'Revisa los datos e inténtalo de nuevo.' };
    case 'server_error':
      return { title: 'Error del servidor', body: 'El servidor no pudo completar la operación. Inténtalo de nuevo en unos minutos.' };
    case 'network':
      return {
        title: 'No se pudo conectar con el servidor',
        body: 'Comprueba tu conexión e inténtalo de nuevo. Si el problema continúa, avisa al equipo técnico.',
      };
    case 'timeout':
      return { title: 'La operación tardó demasiado', body: 'El servidor no respondió a tiempo. Inténtalo de nuevo.' };
    case 'unexpected_response':
      return {
        title: 'Respuesta inesperada del servidor',
        body: 'La respuesta no tiene el formato esperado, así que no se muestra ningún dato.',
      };
    case 'config':
      return {
        title: 'La aplicación no está bien configurada',
        body: 'Avisa al equipo técnico para que la revise.',
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
