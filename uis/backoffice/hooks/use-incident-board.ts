// Estado del listado de /incident-manager: filtros, carga y cambio de estado
// por fila. Solo consume services/incident-manager.service.ts.
//
// Tres piezas, igual que hooks/use-supplier-directory.ts:
//   1. `incidentBoardReducer`: transiciones de estado puras (y `boardView`,
//      que decide cuál de los cuatro estados se muestra).
//   2. `createIncidentBoardSession`: operaciones asíncronas, cancelación y
//      carreras, sin React.
//   3. `useIncidentBoard`: une ambas con hooks nativos de React.
//
// Cambio de estado optimista: la fila muestra el estado nuevo al instante; si
// la API lo rechaza (o falla la red), vuelve al estado anterior y la fila
// muestra el error. Solo se piden transiciones del ciclo de vida
// (INCIDENT_TRANSITIONS); una por incidencia a la vez. Tras un cambio correcto
// se avisa a quien escucha (`onStatusChanged`: el panel de resumen se recarga).
//
// Carreras: cada carga nueva (cambio de filtro, reintento) aborta la anterior;
// si un estado cambia mientras se carga el listado, esa respuesta puede ser
// anterior al cambio y se vuelve a cargar. Tras desmontar no se despacha nada.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { IncidentServiceError, changeIncidentStatus, listIncidents } from '@/services/incident-manager.service';
import {
  INCIDENT_TRANSITIONS,
  type Incident,
  type IncidentFilters,
  type IncidentStatus,
  type IncidentUiError,
} from '@/types/incident-manager';

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------

export type BoardListState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; error: IncidentUiError };

export type BoardRowState =
  | { status: 'saving'; previous: IncidentStatus }
  | { status: 'error'; error: IncidentUiError; attempted: IncidentStatus };

export interface IncidentBoardState {
  filters: IncidentFilters;
  /** Último listado recibido (con los cambios de estado aplicados). Un fallo posterior no lo borra. */
  incidents: readonly Incident[];
  /** Si ya se recibió algún listado (distingue "vacío" de "aún no cargado"). */
  loaded: boolean;
  list: BoardListState;
  rows: Readonly<Record<string, BoardRowState>>;
}

export type IncidentBoardAction =
  | { type: 'filters_changed'; filters: IncidentFilters }
  | { type: 'list_started' }
  | { type: 'list_succeeded'; incidents: readonly Incident[] }
  | { type: 'list_failed'; error: IncidentUiError }
  | { type: 'status_change_started'; id: string; status: IncidentStatus; previous: IncidentStatus }
  | { type: 'status_change_succeeded'; incident: Incident }
  | { type: 'status_change_failed'; id: string; previous: IncidentStatus; attempted: IncidentStatus; error: IncidentUiError }
  | { type: 'row_cleared'; id: string };

export const NO_INCIDENT_FILTERS: IncidentFilters = { status: null, origin: null, branch: null };

export const INITIAL_INCIDENT_BOARD_STATE: IncidentBoardState = {
  filters: NO_INCIDENT_FILTERS,
  incidents: [],
  loaded: false,
  list: { status: 'idle' },
  rows: {},
};

function withoutRow(rows: Readonly<Record<string, BoardRowState>>, id: string): Record<string, BoardRowState> {
  const next = { ...rows };
  delete next[id];
  return next;
}

function withStatus(incidents: readonly Incident[], id: string, status: IncidentStatus): Incident[] {
  return incidents.map((incident) => (incident.id === id ? { ...incident, status } : incident));
}

export function incidentBoardReducer(state: IncidentBoardState, action: IncidentBoardAction): IncidentBoardState {
  switch (action.type) {
    case 'filters_changed':
      return { ...state, filters: action.filters };
    case 'list_started':
      return { ...state, list: { status: 'loading' } };
    case 'list_succeeded':
      return { ...state, incidents: action.incidents, loaded: true, list: { status: 'success' } };
    case 'list_failed':
      return { ...state, list: { status: 'error', error: action.error } };
    case 'status_change_started':
      // Optimista: la fila muestra ya el estado pedido.
      return {
        ...state,
        incidents: withStatus(state.incidents, action.id, action.status),
        rows: { ...state.rows, [action.id]: { status: 'saving', previous: action.previous } },
      };
    case 'status_change_succeeded':
      return {
        ...state,
        incidents: state.incidents.map((incident) => (incident.id === action.incident.id ? action.incident : incident)),
        rows: withoutRow(state.rows, action.incident.id),
      };
    case 'status_change_failed':
      // Reversión: vuelve el estado anterior y la fila muestra el error.
      return {
        ...state,
        incidents: withStatus(state.incidents, action.id, action.previous),
        rows: { ...state.rows, [action.id]: { status: 'error', error: action.error, attempted: action.attempted } },
      };
    case 'row_cleared':
      return { ...state, rows: withoutRow(state.rows, action.id) };
  }
}

/** Cuál de los cuatro estados del listado se muestra. El error manda; después, "aún no cargado". */
export type BoardView = 'loading' | 'error' | 'empty' | 'data';

export function boardView(state: IncidentBoardState): BoardView {
  if (state.list.status === 'error') return 'error';
  if (!state.loaded) return 'loading';
  return state.incidents.length === 0 ? 'empty' : 'data';
}

export function hasActiveFilters(filters: IncidentFilters): boolean {
  return filters.status !== null || filters.origin !== null || filters.branch !== null;
}

// ---------------------------------------------------------------------------
// Sesión: operaciones asíncronas, cancelación y carreras
// ---------------------------------------------------------------------------

export interface IncidentBoardDependencies {
  listIncidents: typeof listIncidents;
  changeIncidentStatus: typeof changeIncidentStatus;
}

export interface IncidentBoardSession {
  /** Habilita el despacho y carga el listado (montaje). Compatible con StrictMode. */
  activate(): void;
  dispose(): void;
  setFilters(filters: IncidentFilters): void;
  reload(): Promise<void>;
  /** Pide la transición `incident.status → target` si el ciclo de vida la permite. */
  changeStatus(incident: Incident, target: IncidentStatus): Promise<void>;
  clearRow(id: string): void;
}

const DEFAULT_DEPENDENCIES: IncidentBoardDependencies = { listIncidents, changeIncidentStatus };
const FALLBACK_ERROR: IncidentUiError = { kind: 'unexpected_response' };

export function createIncidentBoardSession(
  dispatch: (action: IncidentBoardAction) => void,
  dependencies: IncidentBoardDependencies = DEFAULT_DEPENDENCIES,
  onStatusChanged: () => void = () => {}
): IncidentBoardSession {
  let active = false;
  let filters = NO_INCIDENT_FILTERS;
  let listRun = 0;
  let listController: AbortController | null = null;
  const rowControllers = new Map<string, AbortController>();
  // Cambios de estado confirmados por la API. Si cambia durante una carga del
  // listado, esa carga puede traer datos anteriores al cambio.
  let mutations = 0;

  function emit(action: IncidentBoardAction): void {
    if (active) dispatch(action);
  }

  async function load(): Promise<void> {
    if (!active) return;
    listRun += 1;
    listController?.abort();
    const run = listRun;
    const controller = new AbortController();
    listController = controller;
    const mutationsAtStart = mutations;
    emit({ type: 'list_started' });

    try {
      const incidents = await dependencies.listIncidents(filters, { signal: controller.signal });
      if (!active || run !== listRun) return;
      if (mutations !== mutationsAtStart) {
        void load();
        return;
      }
      emit({ type: 'list_succeeded', incidents });
    } catch (error) {
      if (!active || run !== listRun || error instanceof ApiAbortError) return;
      emit({ type: 'list_failed', error: error instanceof IncidentServiceError ? error.uiError : FALLBACK_ERROR });
    } finally {
      if (listController === controller) listController = null;
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
      listRun += 1;
      listController?.abort();
      listController = null;
      for (const controller of rowControllers.values()) controller.abort();
      rowControllers.clear();
    },

    setFilters(next) {
      if (!active) return;
      filters = next;
      emit({ type: 'filters_changed', filters: next });
      void load();
    },

    reload: load,

    async changeStatus(incident, target) {
      const { id, status: previous } = incident;
      if (!active || rowControllers.has(id) || !INCIDENT_TRANSITIONS[previous].includes(target)) return;
      const controller = new AbortController();
      rowControllers.set(id, controller);
      emit({ type: 'status_change_started', id, status: target, previous });

      try {
        const updated = await dependencies.changeIncidentStatus(id, target, { signal: controller.signal });
        if (!active || rowControllers.get(id) !== controller) return;
        mutations += 1;
        emit({ type: 'status_change_succeeded', incident: updated });
        onStatusChanged();
      } catch (error) {
        if (!active || rowControllers.get(id) !== controller || error instanceof ApiAbortError) return;
        const uiError = error instanceof IncidentServiceError ? error.uiError : FALLBACK_ERROR;
        emit({ type: 'status_change_failed', id, previous, attempted: target, error: uiError });
      } finally {
        if (rowControllers.get(id) === controller) rowControllers.delete(id);
      }
    },

    clearRow(id) {
      if (!rowControllers.has(id)) emit({ type: 'row_cleared', id });
    },
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseIncidentBoardResult extends IncidentBoardState {
  view: BoardView;
  setFilters: (filters: IncidentFilters) => void;
  reload: () => void;
  changeStatus: (incident: Incident, target: IncidentStatus) => void;
  clearRow: (id: string) => void;
}

/** `onStatusChanged` debe ser estable (p. ej. el `reload` de useIncidentSummary): se fija al montar. */
export function useIncidentBoard(onStatusChanged?: () => void): UseIncidentBoardResult {
  const [state, dispatch] = useReducer(incidentBoardReducer, INITIAL_INCIDENT_BOARD_STATE);
  const [session] = useState(() => createIncidentBoardSession(dispatch, DEFAULT_DEPENDENCIES, onStatusChanged));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const setFilters = useCallback((filters: IncidentFilters) => session.setFilters(filters), [session]);
  const reload = useCallback(() => void session.reload(), [session]);
  const changeStatus = useCallback(
    (incident: Incident, target: IncidentStatus) => void session.changeStatus(incident, target),
    [session]
  );
  const clearRow = useCallback((id: string) => session.clearRow(id), [session]);

  return { ...state, view: boardView(state), setFilters, reload, changeStatus, clearRow };
}
