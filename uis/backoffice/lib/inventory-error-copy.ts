// Textos de error del inventario (excepción acotada a /inventory, CLAUDE.md):
// un 4xx/5xx con un `detail` de texto legible muestra ese mensaje de la API
// como texto plano, bajo un título propio en español; el resto de errores usa
// los textos fijos del backoffice. Módulo puro: lo usan los componentes y los tests.

import type { InventoryUiError } from '@/types/inventory';

export interface ErrorCopy {
  title: string;
  body: string;
}

function apiErrorTitle(status: number, code: string | null): string {
  if (code === 'insufficient_stock') return 'No hay stock suficiente';
  if (code === 'office_mismatch') return 'La oficina no coincide con la del activo';
  if (code === 'asset_not_found' || status === 404) return 'El activo no existe';
  if (code === 'sku_already_exists' || status === 409) return 'Ya existe un activo con ese SKU';
  if (status >= 500) return 'Error del servidor';
  return 'La API rechazó la operación';
}

export function inventoryErrorCopy(error: InventoryUiError): ErrorCopy {
  switch (error.kind) {
    case 'api_error':
      return { title: apiErrorTitle(error.status, error.code), body: error.detail };
    case 'validation':
      return error.source === 'api'
        ? { title: 'El servidor rechazó los datos', body: 'Corrige los campos indicados y vuelve a intentarlo.' }
        : { title: 'Revisa los datos', body: 'Corrige los campos indicados antes de enviar.' };
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
      return { title: 'La aplicación no está bien configurada', body: 'Avisa al equipo técnico para que la revise.' };
    case 'session_expired':
      return { title: 'La sesión ha caducado', body: 'Vuelve a iniciar sesión para continuar.' };
  }
}
