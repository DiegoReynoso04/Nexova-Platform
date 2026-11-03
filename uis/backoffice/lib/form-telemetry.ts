// Embudo de un formulario para la telemetría (plan §6.5): `form_started`,
// `form_validation_failed`, `form_submitted` y `form_abandoned`, sin React.
// Lo usa hooks/use-form-telemetry.ts; los formularios solo avisan de qué campo
// cambia y los hooks de envío, del resultado. Nunca se envía un valor escrito:
// solo nombres de campo y el resultado.

import { elapsedMs, track } from '@/lib/telemetry';
import type { FormOutcome, TelemetryEventProperties, TelemetryEventType, TelemetryForm } from '@/types/telemetry';

/** Topes del esquema de `duration_ms` y `attempt_number` (event-schemas.json). */
const DURATION_MAX_MS = 86_400_000;
const ATTEMPT_MAX = 1_000;
/** Nombre de campo admitido por el esquema (`^[a-z_]+$`, 40 como máximo). */
const FIELD_NAME = /^[a-z_]{1,40}$/;
const FIELDS_MAX = 20;

export interface FormTelemetry {
  /** Un campo cambió: el primero desde el montaje o el último éxito emite `form_started`. */
  fieldChanged(field: string): void;
  /** La validación en cliente bloqueó el envío (sin petición). */
  validationFailed(fields: readonly string[]): void;
  /** Terminó un envío. `success` cierra el embudo: el siguiente cambio vuelve a empezar. */
  submitted(outcome: FormOutcome): void;
  /** Desmontaje o `pagehide` con el formulario empezado y sin éxito: `form_abandoned`. */
  abandon(): void;
}

export interface FormTelemetryDependencies {
  track: <E extends TelemetryEventType>(eventType: E, properties: TelemetryEventProperties[E]) => void;
  /** `performance.now()`. */
  now: () => number;
}

function browserNow(): number {
  return typeof performance === 'undefined' ? Date.now() : performance.now();
}

const DEFAULT_DEPENDENCIES: FormTelemetryDependencies = { track, now: browserNow };

function safeField(field: string): string | null {
  return FIELD_NAME.test(field) ? field : null;
}

export function createFormTelemetry(form: TelemetryForm, dependencies: FormTelemetryDependencies = DEFAULT_DEPENDENCIES): FormTelemetry {
  let startedAt: number | null = null;
  let attempts = 0;
  let lastField: string | null = null;
  let hadValidationError = false;
  let hadApiError = false;

  function start(): number {
    if (startedAt === null) {
      startedAt = dependencies.now();
      attempts = 0;
      hadValidationError = false;
      hadApiError = false;
      dependencies.track('form_started', { form });
    }
    return startedAt;
  }

  return {
    fieldChanged(field) {
      start();
      lastField = safeField(field) ?? lastField;
    },

    validationFailed(fields) {
      start();
      hadValidationError = true;
      const names = [...new Set(fields.map(safeField).filter((name) => name !== null))].slice(0, FIELDS_MAX);
      dependencies.track('form_validation_failed', { form, fields: names });
    },

    submitted(outcome) {
      const since = start();
      attempts = Math.min(attempts + 1, ATTEMPT_MAX);
      if (outcome === 'validation_error') hadValidationError = true;
      else if (outcome !== 'success') hadApiError = true;
      dependencies.track('form_submitted', {
        form,
        outcome,
        duration_ms: elapsedMs(since, dependencies.now(), DURATION_MAX_MS),
        attempt_number: attempts,
      });
      if (outcome === 'success') {
        startedAt = null;
        lastField = null;
      }
    },

    abandon() {
      if (startedAt === null) return;
      dependencies.track('form_abandoned', {
        form,
        last_field: lastField,
        had_validation_error: hadValidationError,
        had_api_error: hadApiError,
        duration_ms: elapsedMs(startedAt, dependencies.now(), DURATION_MAX_MS),
      });
      startedAt = null;
      lastField = null;
    },
  };
}
