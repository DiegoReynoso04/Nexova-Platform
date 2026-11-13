// Estado de la franja «Datos actualizados» de /reporting (`GET /reporting/pipeline-runs/latest`).
// Tiene su propia carga y su propio error: si falla, el reporte sigue visible (como el resumen de
// /incident-manager). Reducer puro + sesión sin React + hook.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { ReportingServiceError, getLatestPipelineRun } from '@/services/reporting.service';
import type { PipelineRun, ReportingUiError } from '@/types/reporting';

export type FreshnessLoad =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; error: ReportingUiError };

export interface FreshnessState {
  /** `null`: el pipeline todavía no ha corrido (o aún no se sabe). */
  run: PipelineRun | null;
  load: FreshnessLoad;
}

export type FreshnessAction =
  | { type: 'freshness_started' }
  | { type: 'freshness_loaded'; run: PipelineRun | null }
  | { type: 'freshness_failed'; error: ReportingUiError };

export const INITIAL_FRESHNESS_STATE: FreshnessState = { run: null, load: { status: 'idle' } };

export function freshnessReducer(state: FreshnessState, action: FreshnessAction): FreshnessState {
  switch (action.type) {
    case 'freshness_started':
      return { ...state, load: { status: 'loading' } };
    case 'freshness_loaded':
      return { run: action.run, load: { status: 'success' } };
    case 'freshness_failed':
      return { ...state, load: { status: 'error', error: action.error } };
  }
}

export interface FreshnessDependencies {
  getLatestPipelineRun: typeof getLatestPipelineRun;
}

export interface FreshnessSession {
  activate(): void;
  dispose(): void;
  reload(): Promise<void>;
}

const FALLBACK_ERROR: ReportingUiError = { kind: 'unexpected_response' };

export function createFreshnessSession(
  dispatch: (action: FreshnessAction) => void,
  dependencies: FreshnessDependencies = { getLatestPipelineRun }
): FreshnessSession {
  let active = false;
  let run = 0;
  let controller: AbortController | null = null;

  async function load(): Promise<void> {
    if (!active) return;
    run += 1;
    controller?.abort();
    const current = run;
    const ownController = new AbortController();
    controller = ownController;
    dispatch({ type: 'freshness_started' });

    try {
      const latest = await dependencies.getLatestPipelineRun({ signal: ownController.signal });
      if (!active || current !== run) return;
      dispatch({ type: 'freshness_loaded', run: latest });
    } catch (error) {
      if (!active || current !== run || error instanceof ApiAbortError) return;
      dispatch({
        type: 'freshness_failed',
        error: error instanceof ReportingServiceError ? error.uiError : FALLBACK_ERROR,
      });
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

export interface UsePipelineFreshnessResult extends FreshnessState {
  reload: () => void;
}

export function usePipelineFreshness(): UsePipelineFreshnessResult {
  const [state, dispatch] = useReducer(freshnessReducer, INITIAL_FRESHNESS_STATE);
  const [session] = useState(() => createFreshnessSession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const reload = useCallback(() => void session.reload(), [session]);

  return { ...state, reload };
}
