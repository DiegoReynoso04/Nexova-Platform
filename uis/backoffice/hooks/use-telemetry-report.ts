// Estado de /telemetry: reducer puro + sesión sin React (cancelación, carreras y
// sondeo) + hook, como el resto de hooks del backoffice. Un fallo al recargar no
// borra el último reporte recibido.
//
// Desde DEV-55 (A16) el reporte es asíncrono: la sesión lo encola
// (`GET /telemetry/report` → 202) y sondea `GET /tasks/{id}` con espera creciente
// (1 s, 2 s y después 3 s) hasta `success` o `failure`, con un tope de 10 minutos
// (el peor caso: 4 ejecuciones de 150 s más las cuentas atrás). Al salir de la
// página (`dispose`) se cancela la petición en curso y no se programa ningún sondeo
// más. Fases que ve la página: «En cola» (`pending`) y «Calculando» (`started`).

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { TelemetryReportServiceError, getTelemetryReportTask, requestTelemetryReport } from '@/services/telemetry-report.service';
import type { TelemetryReport, TelemetryReportUiError } from '@/types/telemetry-report';

/** Esperas entre sondeos, en ms: la primera, la segunda y, a partir de ahí, la última. */
export const POLL_DELAYS_MS = [1_000, 2_000, 3_000] as const;
/** Tope de espera de una tarea desde que se encola. */
export const POLL_TIMEOUT_MS = 10 * 60 * 1_000;

export function pollDelayMs(poll: number): number {
  return POLL_DELAYS_MS[Math.min(poll, POLL_DELAYS_MS.length - 1)];
}

export type TelemetryReportLoad =
  | { status: 'idle' }
  /** Encolando, o en la cola sin worker libre (`pending`). */
  | { status: 'queued' }
  /** Un worker lo está calculando (`started`, también entre reintentos). */
  | { status: 'computing' }
  | { status: 'success' }
  | { status: 'error'; error: TelemetryReportUiError };

export interface TelemetryReportState {
  report: TelemetryReport | null;
  load: TelemetryReportLoad;
}

export type TelemetryReportAction =
  | { type: 'report_started' }
  | { type: 'report_computing' }
  | { type: 'report_succeeded'; report: TelemetryReport }
  | { type: 'report_failed'; error: TelemetryReportUiError };

export const INITIAL_TELEMETRY_REPORT_STATE: TelemetryReportState = { report: null, load: { status: 'idle' } };

export function telemetryReportReducer(state: TelemetryReportState, action: TelemetryReportAction): TelemetryReportState {
  switch (action.type) {
    case 'report_started':
      return { ...state, load: { status: 'queued' } };
    case 'report_computing':
      return { ...state, load: { status: 'computing' } };
    case 'report_succeeded':
      return { report: action.report, load: { status: 'success' } };
    case 'report_failed':
      return { ...state, load: { status: 'error', error: action.error } };
  }
}

export type TelemetryReportView = 'queued' | 'computing' | 'error' | 'data';

/** Qué pinta la página. Con un reporte en pantalla, ni la recarga ni un fallo lo esconden. */
export function reportView(state: TelemetryReportState): TelemetryReportView {
  if (state.report !== null) return 'data';
  if (state.load.status === 'error') return 'error';
  return state.load.status === 'computing' ? 'computing' : 'queued';
}

export interface TelemetryReportDependencies {
  requestTelemetryReport: typeof requestTelemetryReport;
  getTelemetryReportTask: typeof getTelemetryReportTask;
  /** Espera cancelable; los tests la sustituyen por una que avanza al momento. */
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  now?: () => number;
}

export interface TelemetryReportSession {
  /** Habilita el despacho y pide el reporte (montaje). Compatible con StrictMode. */
  activate(): void;
  /** Cancela la petición y el sondeo en curso; no despacha nada más. */
  dispose(): void;
  reload(): Promise<void>;
}

const FALLBACK_ERROR: TelemetryReportUiError = { kind: 'unexpected_response' };

function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new ApiAbortError());
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new ApiAbortError());
    }
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

export function createTelemetryReportSession(
  dispatch: (action: TelemetryReportAction) => void,
  dependencies: TelemetryReportDependencies = { requestTelemetryReport, getTelemetryReportTask }
): TelemetryReportSession {
  const sleep = dependencies.sleep ?? abortableSleep;
  const now = dependencies.now ?? Date.now;
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
    const { signal } = ownController;
    const isCurrent = () => active && current === run;
    dispatch({ type: 'report_started' });

    try {
      const taskId = await dependencies.requestTelemetryReport({ signal });
      const deadline = now() + POLL_TIMEOUT_MS;
      let computing = false;
      for (let poll = 0; ; poll += 1) {
        if (!isCurrent()) return;
        if (now() >= deadline) {
          dispatch({ type: 'report_failed', error: { kind: 'polling_timeout' } });
          return;
        }
        await sleep(pollDelayMs(poll), signal);
        if (!isCurrent()) return;
        const task = await dependencies.getTelemetryReportTask(taskId, { signal });
        if (!isCurrent()) return;
        if (task.status === 'success') {
          dispatch({ type: 'report_succeeded', report: task.report });
          return;
        }
        if (task.status === 'failure') {
          dispatch({ type: 'report_failed', error: { kind: 'task_failed' } });
          return;
        }
        if (task.status === 'started' && !computing) {
          computing = true;
          dispatch({ type: 'report_computing' });
        }
      }
    } catch (error) {
      if (!isCurrent() || error instanceof ApiAbortError) return;
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
  view: TelemetryReportView;
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
