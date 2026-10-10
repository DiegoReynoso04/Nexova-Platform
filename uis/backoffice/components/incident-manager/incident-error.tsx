import { Alert } from '@/components/ui/alert';
import type { IncidentField, IncidentUiError } from '@/types/incident-manager';

interface ErrorCopy {
  title: string;
  body: string;
}

// Mensajes fijos en español por tipo de error. Nunca se muestra texto de la
// API: los errores de validación ya llegan con mensajes propios del frontend
// (services/incident-manager.service.ts).
export function copyFor(error: IncidentUiError): ErrorCopy {
  switch (error.kind) {
    case 'validation':
      return error.source === 'api'
        ? { title: 'El servidor rechazó los datos', body: 'Corrige los campos indicados y vuelve a intentarlo.' }
        : { title: 'Revisa los datos', body: 'Corrige los campos indicados antes de enviar.' };
    case 'invalid_transition':
      return {
        title: 'Ese cambio de estado no está permitido',
        body: 'El ciclo de vida de la incidencia no admite ese paso. Recarga el listado para ver su estado actual.',
      };
    case 'not_found':
      return { title: 'La incidencia ya no existe', body: 'Recarga el listado para ver el estado actual.' };
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
    case 'session_expired':
      return { title: 'La sesión ha caducado', body: 'Vuelve a iniciar sesión para continuar.' };
  }
}

/** Nombre visible de cada campo del formulario (los mismos que sus etiquetas). */
export const FIELD_LABELS: Readonly<Record<IncidentField, string>> = {
  title: 'Título',
  description: 'Descripción',
  category: 'Categoría',
  status: 'Estado',
  origin: 'Origen',
  branch: 'Sede',
};

export interface IncidentErrorProps {
  error: IncidentUiError;
  id?: string;
  /** Los errores de validación con campo se muestran junto a su campo; aquí solo los que no tienen. */
  hideFieldErrors?: boolean;
}

export function IncidentError({ error, id, hideFieldErrors = false }: IncidentErrorProps) {
  const { title, body } = copyFor(error);
  const listed =
    error.kind === 'validation'
      ? error.errors.filter((fieldError) => !hideFieldErrors || fieldError.field === null)
      : [];
  return (
    <Alert variant="error" title={title} id={id}>
      <p>{body}</p>
      {listed.length > 0 && (
        <ul className="mt-2 list-disc pl-5">
          {listed.map((fieldError, index) => (
            <li key={`${fieldError.field ?? 'general'}-${index}`}>
              {fieldError.field === null ? fieldError.message : `${FIELD_LABELS[fieldError.field]}: ${fieldError.message}`}
            </li>
          ))}
        </ul>
      )}
    </Alert>
  );
}
