// Estado del formulario de registro de incidencias (/incident-manager/new).
// Solo consume services/incident-manager.service.ts (nunca HTTP directo).
//
// Tres piezas, igual que hooks/use-supplier-directory.ts:
//   1. `incidentFormReducer`: transiciones de estado puras.
//   2. `createIncidentFormSession`: envío, cancelación y carreras, sin React.
//   3. `useIncidentForm`: une ambas con hooks nativos de React.
//
// Tras un alta correcta `formKey` cambia: la vista lo usa como `key` del
// formulario, que se vuelve a montar vacío, y la confirmación se mantiene
// visible hasta el siguiente envío.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { IncidentServiceError, createIncident } from '@/services/incident-manager.service';
import type { Incident, IncidentFormValues, IncidentUiError } from '@/types/incident-manager';

export type SubmitState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success'; incident: Incident }
  | { status: 'error'; error: IncidentUiError };

export interface IncidentFormState {
  submit: SubmitState;
  /** Cambia con cada alta correcta: el formulario se vuelve a montar limpio. */
  formKey: number;
}

export type IncidentFormAction =
  | { type: 'submit_started' }
  | { type: 'submit_succeeded'; incident: Incident }
  | { type: 'submit_failed'; error: IncidentUiError };

export const INITIAL_INCIDENT_FORM_STATE: IncidentFormState = { submit: { status: 'idle' }, formKey: 0 };

export function incidentFormReducer(state: IncidentFormState, action: IncidentFormAction): IncidentFormState {
  switch (action.type) {
    case 'submit_started':
      return { ...state, submit: { status: 'submitting' } };
    case 'submit_succeeded':
      return { submit: { status: 'success', incident: action.incident }, formKey: state.formKey + 1 };
    case 'submit_failed':
      return { ...state, submit: { status: 'error', error: action.error } };
  }
}

export interface IncidentFormDependencies {
  createIncident: typeof createIncident;
}

export interface IncidentFormSession {
  activate(): void;
  /** Desmontaje: aborta el envío en curso y deja de despachar. */
  dispose(): void;
  submit(values: IncidentFormValues): Promise<void>;
}

const FALLBACK_ERROR: IncidentUiError = { kind: 'unexpected_response' };

export function createIncidentFormSession(
  dispatch: (action: IncidentFormAction) => void,
  dependencies: IncidentFormDependencies = { createIncident }
): IncidentFormSession {
  let active = false;
  let run = 0;
  let controller: AbortController | null = null;

  function emit(action: IncidentFormAction): void {
    if (active) dispatch(action);
  }

  return {
    activate() {
      active = true;
    },

    dispose() {
      active = false;
      run += 1;
      controller?.abort();
      controller = null;
    },

    async submit(values) {
      // Un envío a la vez: la vista deshabilita el botón mientras tanto.
      if (!active || controller !== null) return;
      run += 1;
      const current = run;
      const ownController = new AbortController();
      controller = ownController;
      emit({ type: 'submit_started' });

      try {
        const incident = await dependencies.createIncident(values, { signal: ownController.signal });
        if (!active || current !== run) return;
        emit({ type: 'submit_succeeded', incident });
      } catch (error) {
        if (!active || current !== run || error instanceof ApiAbortError) return;
        emit({ type: 'submit_failed', error: error instanceof IncidentServiceError ? error.uiError : FALLBACK_ERROR });
      } finally {
        if (controller === ownController) controller = null;
      }
    },
  };
}

export interface UseIncidentFormResult extends IncidentFormState {
  submitIncident: (values: IncidentFormValues) => void;
}

export function useIncidentForm(): UseIncidentFormResult {
  const [state, dispatch] = useReducer(incidentFormReducer, INITIAL_INCIDENT_FORM_STATE);
  const [session] = useState(() => createIncidentFormSession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const submitIncident = useCallback((values: IncidentFormValues) => void session.submit(values), [session]);

  return { ...state, submitIncident };
}
