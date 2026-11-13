// Estado de /reporting (`GET /reporting/weekly-office-program-performance`): reducer puro + sesión
// sin React (cancelación y carreras) + hook, como el resto de hooks del backoffice.
//
// La semana pedida (`null` = la última calculada) y la semana mostrada no son lo mismo: una semana
// sin calcular (404) no es un error, sigue en el selector. Al cambiar de semana se descarta el
// reporte anterior: mostrarlo bajo el título de otra semana confundiría.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { shiftWeek } from '@/lib/reporting-format';
import { ReportingServiceError, getWeeklyPerformance } from '@/services/reporting.service';
import type { ReportingUiError, WeeklyPerformance } from '@/types/reporting';

export type WeeklyLoad =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'not_computed' }
  | { status: 'error'; error: ReportingUiError };

export interface WeeklyState {
  /** Lunes pedido; `null` = la última semana calculada (la primera carga). */
  requestedWeek: string | null;
  report: WeeklyPerformance | null;
  /** La última semana calculada, conocida tras la primera carga: el tope del botón «siguiente». */
  latestWeek: string | null;
  load: WeeklyLoad;
}

export type WeeklyAction =
  | { type: 'week_requested'; week: string | null }
  | { type: 'week_loaded'; week: string | null; report: WeeklyPerformance }
  | { type: 'week_not_computed'; week: string | null }
  | { type: 'week_failed'; error: ReportingUiError };

export const INITIAL_WEEKLY_STATE: WeeklyState = {
  requestedWeek: null,
  report: null,
  latestWeek: null,
  load: { status: 'idle' },
};

export function weeklyReducer(state: WeeklyState, action: WeeklyAction): WeeklyState {
  switch (action.type) {
    case 'week_requested':
      return { ...state, requestedWeek: action.week, report: null, load: { status: 'loading' } };
    case 'week_loaded':
      return {
        requestedWeek: action.week,
        report: action.report,
        latestWeek: action.week === null ? action.report.week_start : state.latestWeek,
        load: { status: 'success' },
      };
    case 'week_not_computed':
      return { ...state, requestedWeek: action.week, report: null, load: { status: 'not_computed' } };
    case 'week_failed':
      return { ...state, report: null, load: { status: 'error', error: action.error } };
  }
}

export type WeeklyView = 'loading' | 'not_computed' | 'error' | 'empty' | 'data';

/** Qué pinta la página: cuatro estados exclusivos más el vacío de una semana sin actividad. */
export function weeklyView(state: WeeklyState): WeeklyView {
  switch (state.load.status) {
    case 'not_computed':
      return 'not_computed';
    case 'error':
      return 'error';
    case 'success':
      return state.report !== null && state.report.entries.length === 0 ? 'empty' : 'data';
    default:
      return 'loading';
  }
}

/** El lunes de la semana que se muestra o se está pidiendo; `null` mientras no se sabe cuál es la última. */
export function shownWeek(state: WeeklyState): string | null {
  return state.report?.week_start ?? state.requestedWeek;
}

export function previousWeek(state: WeeklyState): string | null {
  const week = shownWeek(state);
  return week === null ? null : shiftWeek(week, -1);
}

/** Hasta la última semana calculada (comparación de fechas ISO como texto). */
export function nextWeek(state: WeeklyState): string | null {
  const week = shownWeek(state);
  if (week === null || state.latestWeek === null || week >= state.latestWeek) return null;
  return shiftWeek(week, 1);
}

export interface WeeklyDependencies {
  getWeeklyPerformance: typeof getWeeklyPerformance;
}

export interface WeeklySession {
  /** Habilita el despacho y carga la última semana (montaje). Compatible con StrictMode. */
  activate(): void;
  dispose(): void;
  load(week: string | null): Promise<void>;
  reload(): Promise<void>;
}

const FALLBACK_ERROR: ReportingUiError = { kind: 'unexpected_response' };

export function createWeeklySession(
  dispatch: (action: WeeklyAction) => void,
  dependencies: WeeklyDependencies = { getWeeklyPerformance }
): WeeklySession {
  let active = false;
  let run = 0;
  let controller: AbortController | null = null;
  let currentWeek: string | null = null;

  async function load(week: string | null): Promise<void> {
    if (!active) return;
    currentWeek = week;
    run += 1;
    controller?.abort();
    const current = run;
    const ownController = new AbortController();
    controller = ownController;
    dispatch({ type: 'week_requested', week });

    try {
      const result = await dependencies.getWeeklyPerformance({
        ...(week === null ? {} : { weekStart: week }),
        signal: ownController.signal,
      });
      if (!active || current !== run) return;
      if (result.status === 'computed') dispatch({ type: 'week_loaded', week, report: result.report });
      else dispatch({ type: 'week_not_computed', week });
    } catch (error) {
      if (!active || current !== run || error instanceof ApiAbortError) return;
      dispatch({ type: 'week_failed', error: error instanceof ReportingServiceError ? error.uiError : FALLBACK_ERROR });
    } finally {
      if (controller === ownController) controller = null;
    }
  }

  return {
    activate() {
      if (active) return;
      active = true;
      void load(null);
    },

    dispose() {
      active = false;
      run += 1;
      controller?.abort();
      controller = null;
    },

    load,
    reload: () => load(currentWeek),
  };
}

export interface UseWeeklyPerformanceResult {
  state: WeeklyState;
  view: WeeklyView;
  week: string | null;
  previous: string | null;
  next: string | null;
  goToWeek: (week: string) => void;
  reload: () => void;
}

export function useWeeklyPerformance(): UseWeeklyPerformanceResult {
  const [state, dispatch] = useReducer(weeklyReducer, INITIAL_WEEKLY_STATE);
  const [session] = useState(() => createWeeklySession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const goToWeek = useCallback((week: string) => void session.load(week), [session]);
  const reload = useCallback(() => void session.reload(), [session]);

  return {
    state,
    view: weeklyView(state),
    week: shownWeek(state),
    previous: previousWeek(state),
    next: nextWeek(state),
    goToWeek,
    reload,
  };
}
