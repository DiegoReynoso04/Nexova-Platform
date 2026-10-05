import { Alert } from '@/components/ui/alert';
import type { FieldError, SupplierField, SupplierUiError } from '@/types/suppliers';

interface ErrorCopy {
  title: string;
  body: string;
}

// Mensajes fijos en español por tipo de error. Solo los errores de validación
// (422 de la API o del propio formulario) muestran mensajes por campo.
function copyFor(error: SupplierUiError): ErrorCopy {
  switch (error.kind) {
    case 'validation':
      return error.source === 'api'
        ? { title: 'La API rechazó los datos (422)', body: 'Corrige los campos indicados y vuelve a intentarlo.' }
        : { title: 'Revisa los datos', body: 'Corrige los campos indicados antes de enviar.' };
    case 'not_found':
      return { title: 'El proveedor ya no existe', body: 'Recarga el listado para ver el estado actual del directorio.' };
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
    case 'session_expired':
      return { title: 'La sesión ha caducado', body: 'Vuelve a iniciar sesión para continuar.' };
  }
}

/** Nombre visible de cada campo del formulario (los mismos que sus etiquetas). */
export const FIELD_LABELS: Record<SupplierField, string> = {
  name: 'Nombre',
  country: 'País',
  categories: 'Categorías',
  monthly_rate: 'Tarifa mensual',
  currency: 'Moneda',
  status: 'Estado',
  contract_renewal_date: 'Fecha de renovación',
  contact_email: 'Email de contacto',
  notes: 'Notas',
};

export function describeFieldError(error: FieldError): string {
  return error.field === null ? error.message : `${FIELD_LABELS[error.field]}: ${error.message}`;
}

export interface SupplierErrorProps {
  error: SupplierUiError;
  id?: string;
}

export function SupplierError({ error, id }: SupplierErrorProps) {
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
