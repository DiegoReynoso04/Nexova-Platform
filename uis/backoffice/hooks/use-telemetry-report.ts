// Estado de /telemetry (`GET /telemetry/report`): reducer puro + sesión sin React
// (cancelación y carreras) + hook, como el resto de hooks del backoffice. Un fallo
// al recargar no borra el último reporte recibido.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { TelemetryReportServiceError, getTelemetryReport } from '@/services/telemetry-report.service';
import type { TelemetryReport, TelemetryReportUiError } from '@/types/telemetry-report';

export type TelemetryReportLoad =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; error: TelemetryReportUiError };

export interface TelemetryReportState {
  report: TelemetryReport | null;
  load: TelemetryReportLoad;
}

export type TelemetryReportAction =
  | { type: 'report_started' }
  | { type: 'report_succeeded'; report: TelemetryReport }
  | { type: 'report_failed'; error: TelemetryReportUiError };

export const INITIAL_TELEMETRY_REPORT_STATE: TelemetryReportState = { report: null, load: { status: 'idle' } };

export function telemetryReportReducer(state: TelemetryReportState, action: TelemetryReportAction): TelemetryReportState {
  switch (action.type) {
    case 'report_started':
      return { ...state, load: { status: 'loading' } };
    case 'report_succeeded':
      return { report: action.report, load: { status: 'success' } };
    case 'report_failed':
      return { ...state, load: { status: 'error', error: action.error } };
  }
}

/** Qué pinta la página. Con un reporte en pantalla, un fallo no lo esconde. */
export function reportView(state: TelemetryReportState): 'loading' | 'error' | 'data' {
  if (state.report !== null) return 'data';
  return state.load.status === 'error' ? 'error' : 'loading';
}

export interface TelemetryReportDependencies {
  getTelemetryReport: typeof getTelemetryReport;
}

export interface TelemetryReportSession {
  /** Habilita el despacho y carga el reporte (montaje). Compatible con StrictMode. */
  activate(): void;
  dispose(): void;
  reload(): Promise<void>;
}

const FALLBACK_ERROR: TelemetryReportUiError = { kind: 'unexpected_response' };

export function createTelemetryReportSession(
  dispatch: (action: TelemetryReportAction) => void,
  dependencies: TelemetryReportDependencies = { getTelemetryReport }
): TelemetryReportSession {
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
    dispatch({ type: 'report_started' });

    try {
      const report = await dependencies.getTelemetryReport({ signal: ownController.signal });
      if (!active || current !== run) return;
      dispatch({ type: 'report_succeeded', report });
    } catch (error) {
      if (!active || current !== run || error instanceof ApiAbortError) return;
      dispatch({ type: 'report_failed', error: error instanceof TelemetryReportServiceError ? error.uiError : FALLBACK_ERROR });
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

export interface UseTelemetryReportResult extends TelemetryReportState {
  view: 'loading' | 'error' | 'data';
  reload: () => void;
}

export function useTelemetryReport(): UseTelemetryReportResult {
  const [state, dispatch] = useReducer(telemetryReportReducer, INITIAL_TELEMETRY_REPORT_STATE);
  const [session] = useState(() => createTelemetryReportSession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const reload = useCallback(() => void session.reload(), [session]);

  return { ...state, view: reportView(state), reload };
}
