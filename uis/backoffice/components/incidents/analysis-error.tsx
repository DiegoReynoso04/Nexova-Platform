import { Alert } from '@/components/ui/alert';
import type { UiError } from '@/types/incidents';

interface ErrorCopy {
  title: string;
  body: string;
}

// Mensajes fijos en español por tipo de error. Nunca se interpola texto de la
// API salvo el `detail` de `invalid_csv`, permitido por contrato (cita columnas
// o números de fila, nunca valores del CSV).
function copyFor(error: UiError): ErrorCopy {
  switch (error.kind) {
    case 'invalid_csv':
      return {
        title: 'El archivo no se pudo analizar',
        body: 'Comprueba que es el CSV de incidentes exportado del helpdesk, en UTF-8 y con su fila de cabecera.',
      };
    case 'unsupported_file_type':
      return { title: 'Tipo de archivo no soportado', body: 'Selecciona un archivo con extensión .csv.' };
    case 'file_too_large':
      return {
        title: 'El archivo es demasiado grande',
        body: 'Supera el tamaño máximo que acepta el servidor (aproximadamente 1 MiB).',
      };
    case 'request_invalid':
      return { title: 'La solicitud no es válida', body: 'Vuelve a seleccionar el archivo e inténtalo de nuevo.' };
    case 'no_analysis':
      return { title: 'No hay ningún análisis disponible', body: 'Analiza un archivo antes de exportar los resultados.' };
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
    case 'export_mismatch':
      return {
        title: 'La exportación ya no corresponde al análisis mostrado',
        body: 'El servidor tiene un análisis más reciente (de otra sesión o tras un reinicio). Vuelve a analizar el archivo para exportar sus resultados.',
      };
  }
}

export interface AnalysisErrorProps {
  error: UiError;
  id?: string;
}

export function AnalysisError({ error, id }: AnalysisErrorProps) {
  const { title, body } = copyFor(error);
  return (
    <Alert variant="error" title={title} id={id}>
      <p>{body}</p>
      {error.kind === 'invalid_csv' && error.detail !== '' && (
        <p className="mt-1">
          Detalle del servidor: <span className="font-mono text-xs">{error.detail}</span>
        </p>
      )}
    </Alert>
  );
}
