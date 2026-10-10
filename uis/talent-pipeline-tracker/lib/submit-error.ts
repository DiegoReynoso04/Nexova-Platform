// Clasificación del error al crear (POST /records) o editar (PUT
// /records/{id}) una candidatura (components/candidates/candidate-form.tsx).
// Función pura para poder probarla sin React.
//
// Lo importante es no inducir a duplicar candidaturas: si la API respondió
// 2xx pero su cuerpo no se pudo leer o no cumple el contrato, la candidatura
// YA está guardada aunque la vista no pueda mostrarla. Un timeout tampoco
// permite saber si se guardó. En esos casos el formulario no invita a
// reenviar: pide recargar el listado.

import {
  ResponseShapeError,
  TimeoutError,
  UnreadableResponseError,
  ValidationApiError,
  describeApiError,
} from '@/lib/api-client';
import type { ValidationError } from '@/types/api';

export const SAVED_BUT_UNREADABLE_MESSAGE = 'Se guardó, pero no se pudo leer la respuesta; recarga el listado.';
export const UNCERTAIN_OUTCOME_MESSAGE =
  'El servidor tardó demasiado y no sabemos si se guardó. Recarga el listado antes de volver a intentarlo.';

export type SubmitErrorOutcome =
  /** 422: errores por campo con el `msg` de la API (SPECS §5.4). */
  | { kind: 'validation'; detail: readonly ValidationError[] }
  /** 2xx con cuerpo ilegible o fuera de contrato: guardada; no reenviar. */
  | { kind: 'saved_unreadable'; message: string }
  /** Timeout: no se sabe si se guardó; no reenviar sin recargar. */
  | { kind: 'uncertain'; message: string }
  /** Red caída, 4xx o 5xx: no se guardó; se puede reintentar. */
  | { kind: 'not_saved'; message: string };

function isSuccessStatus(status: number): boolean {
  return status >= 200 && status < 300;
}

export function classifySubmitError(error: Error): SubmitErrorOutcome {
  if (error instanceof ValidationApiError) return { kind: 'validation', detail: error.detail };
  if (error instanceof ResponseShapeError) return { kind: 'saved_unreadable', message: SAVED_BUT_UNREADABLE_MESSAGE };
  if (error instanceof UnreadableResponseError && isSuccessStatus(error.status)) {
    return { kind: 'saved_unreadable', message: SAVED_BUT_UNREADABLE_MESSAGE };
  }
  if (error instanceof TimeoutError) return { kind: 'uncertain', message: UNCERTAIN_OUTCOME_MESSAGE };
  return { kind: 'not_saved', message: describeApiError(error) };
}
