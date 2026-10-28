// Estado del panel de resumen de /incident-manager (GET /api/incidents/summary).
// Independiente del listado: tiene su propia carga y su propio error, así que
// si el resumen falla el listado sigue funcionando (y al revés).
//
// Reducer puro + sesión sin React (cancelación y carreras) + hook, como el resto
// de hooks del backoffice. Una recarga aborta la anterior; mientras recarga se
// sigue mostrando el último resumen recibido.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { IncidentServiceError, getIncidentSummary } from '@/services/incident-manager.service';
import {
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  type IncidentBranch,
  type IncidentCategory,
  type IncidentOrigin,
  type IncidentStatus,
  type IncidentSummary,
  type IncidentUiError,
} from '@/types/incident-manager';

// ---------------------------------------------------------------------------
// Lo que pinta el panel
// ---------------------------------------------------------------------------

/** Un total del panel; `count: null` = aún sin datos (esqueleto). */
export interface SummaryDisplayCount<T extends string> {
  value: T;
  count: number | null;
}

export interface SummaryDisplay {
  total: number | null;
  by_status: readonly SummaryDisplayCount<IncidentStatus>[];
  by_category: readonly SummaryDisplayCount<IncidentCategory>[];
  by_origin: readonly SummaryDisplayCount<IncidentOrigin>[];
  by_branch: readonly SummaryDisplayCount<IncidentBranch>[];
}

function placeholderCounts<T extends string>(values: readonly T[]): SummaryDisplayCount<T>[] {
  return values.map((value) => ({ value, count: null }));
}

/**
 * Esqueleto del resumen mientras carga: una fila por valor del vocabulario, sin
 * números. El normalizador garantiza que la respuesta trae exactamente esas
 * filas, así que el panel ocupa lo mismo cargando que cargado y no desplaza el
 * listado al llegar los datos (CLS, H2 de AUDIT.md).
 */
export const SUMMARY_PLACEHOLDER: SummaryDisplay = {
  total: null,
  by_status: placeholderCounts(INCIDENT_STATUSES),
  by_category: placeholderCounts(INCIDENT_CATEGORIES),
  by_origin: placeholderCounts(INCIDENT_ORIGINS),
  by_branch: placeholderCounts(INCIDENT_BRANCHES),
};

/** El último resumen recibido o, si aún no hay ninguno, el esqueleto. */
export function summaryDisplay(summary: IncidentSummary | null): SummaryDisplay {
  return summary ?? SUMMARY_PLACEHOLDER;
}

export type SummaryLoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; error: IncidentUiError };

export interface IncidentSummaryState {
  /** Último resumen recibido; un fallo posterior no lo borra. */
  summary: IncidentSummary | null;
  load: SummaryLoadState;
}

export type IncidentSummaryAction =
  | { type: 'summary_started' }
  | { type: 'summary_succeeded'; summary: IncidentSummary }
  | { type: 'summary_failed'; error: IncidentUiError };

export const INITIAL_INCIDENT_SUMMARY_STATE: IncidentSummaryState = { summary: null, load: { status: 'idle' } };

export function incidentSummaryReducer(state: IncidentSummaryState, action: IncidentSummaryAction): IncidentSummaryState {
  switch (action.type) {
    case 'summary_started':
      return { ...state, load: { status: 'loading' } };
    case 'summary_succeeded':
      return { summary: action.summary, load: { status: 'success' } };
    case 'summary_failed':
      return { ...state, load: { status: 'error', error: action.error } };
  }
}

export interface IncidentSummaryDependencies {
  getIncidentSummary: typeof getIncidentSummary;
}

export interface IncidentSummarySession {
  /** Habilita el despacho y carga el resumen (montaje). Compatible con StrictMode. */
  activate(): void;
  dispose(): void;
  reload(): Promise<void>;
}

const FALLBACK_ERROR: IncidentUiError = { kind: 'unexpected_response' };

export function createIncidentSummarySession(
  dispatch: (action: IncidentSummaryAction) => void,
  dependencies: IncidentSummaryDependencies = { getIncidentSummary }
): IncidentSummarySession {
  let active = false;
  let run = 0;
  let controller: AbortController | null = null;

  function emit(action: IncidentSummaryAction): void {
    if (active) dispatch(action);
  }

  async function load(): Promise<void> {
    if (!active) return;
    run += 1;
    controller?.abort();
    const current = run;
    const ownController = new AbortController();
    controller = ownController;
    emit({ type: 'summary_started' });

    try {
      const summary = await dependencies.getIncidentSummary({ signal: ownController.signal });
      if (!active || current !== run) return;
      emit({ type: 'summary_succeeded', summary });
    } catch (error) {
      if (!active || current !== run || error instanceof ApiAbortError) return;
      emit({ type: 'summary_failed', error: error instanceof IncidentServiceError ? error.uiError : FALLBACK_ERROR });
    } finally {
      if (controller === ownController) controller = null;
    }
  }

  return {
    activate() {
      if (active) return;
      active = true;
      void load();
    },

    dispose() {
      active = false;
      run += 1;
      controller?.abort();
      controller = null;
    },

    reload: load,
  };
}

export interface UseIncidentSummaryResult extends IncidentSummaryState {
  reload: () => void;
}

export function useIncidentSummary(): UseIncidentSummaryResult {
  const [state, dispatch] = useReducer(incidentSummaryReducer, INITIAL_INCIDENT_SUMMARY_STATE);
  const [session] = useState(() => createIncidentSummarySession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const reload = useCallback(() => void session.reload(), [session]);

  return { ...state, reload };
}
