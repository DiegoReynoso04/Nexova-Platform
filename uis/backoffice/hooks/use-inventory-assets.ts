// Estado del listado de activos de /inventory/products. Solo consume
// services/inventory.service.ts (nunca HTTP directo).
//
// Tres piezas, igual que hooks/use-incident-board.ts:
//   1. `inventoryAssetsReducer`: transiciones de estado puras (y `assetsView`,
//      que decide cuál de los cuatro estados se muestra).
//   2. `createInventoryAssetsSession`: carga, cancelación y carreras, sin React.
//   3. `useInventoryAssets`: une ambas con hooks nativos de React.
//
// Carreras: cada carga nueva («Reintentar») aborta la anterior, y una
// respuesta que llega tarde se descarta. Tras desmontar no se despacha nada.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { InventoryServiceError, listAssets } from '@/services/inventory.service';
import type { Asset, InventoryUiError } from '@/types/inventory';

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------

export type AssetsLoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; error: InventoryUiError };

export interface InventoryAssetsState {
  /** Último listado recibido. Un fallo posterior no lo borra. */
  assets: readonly Asset[];
  /** Si ya se recibió algún listado (distingue «vacío» de «aún no cargado»). */
  loaded: boolean;
  load: AssetsLoadState;
}

export type InventoryAssetsAction =
  | { type: 'load_started' }
  | { type: 'load_succeeded'; assets: readonly Asset[] }
  | { type: 'load_failed'; error: InventoryUiError };

export const INITIAL_INVENTORY_ASSETS_STATE: InventoryAssetsState = {
  assets: [],
  loaded: false,
  load: { status: 'idle' },
};

export function inventoryAssetsReducer(state: InventoryAssetsState, action: InventoryAssetsAction): InventoryAssetsState {
  switch (action.type) {
    case 'load_started':
      return { ...state, load: { status: 'loading' } };
    case 'load_succeeded':
      return { assets: action.assets, loaded: true, load: { status: 'success' } };
    case 'load_failed':
      return { ...state, load: { status: 'error', error: action.error } };
  }
}

/** Cuál de los cuatro estados se muestra. El error manda; después, «aún no cargado». */
export type AssetsView = 'loading' | 'error' | 'empty' | 'data';

export function assetsView(state: InventoryAssetsState): AssetsView {
  if (state.load.status === 'error') return 'error';
  if (!state.loaded) return 'loading';
  return state.assets.length === 0 ? 'empty' : 'data';
}

// ---------------------------------------------------------------------------
// Sesión: carga, cancelación y carreras
// ---------------------------------------------------------------------------

export interface InventoryAssetsDependencies {
  listAssets: typeof listAssets;
}

export interface InventoryAssetsSession {
  /** Habilita el despacho y carga el listado (montaje). Compatible con StrictMode. */
  activate(): void;
  /** Desmontaje: aborta la carga en curso y deja de despachar. */
  dispose(): void;
  reload(): Promise<void>;
}

const DEFAULT_DEPENDENCIES: InventoryAssetsDependencies = { listAssets };
const FALLBACK_ERROR: InventoryUiError = { kind: 'unexpected_response' };

export function createInventoryAssetsSession(
  dispatch: (action: InventoryAssetsAction) => void,
  dependencies: InventoryAssetsDependencies = DEFAULT_DEPENDENCIES
): InventoryAssetsSession {
  let active = false;
  let run = 0;
  let controller: AbortController | null = null;

  function emit(action: InventoryAssetsAction): void {
    if (active) dispatch(action);
  }

  async function load(): Promise<void> {
    if (!active) return;
    run += 1;
    controller?.abort();
    const current = run;
    const ownController = new AbortController();
    controller = ownController;
    emit({ type: 'load_started' });

    try {
      const assets = await dependencies.listAssets({ signal: ownController.signal });
      if (!active || current !== run) return;
      emit({ type: 'load_succeeded', assets });
    } catch (error) {
      if (!active || current !== run || error instanceof ApiAbortError) return;
      emit({ type: 'load_failed', error: error instanceof InventoryServiceError ? error.uiError : FALLBACK_ERROR });
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

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseInventoryAssetsResult extends InventoryAssetsState {
  view: AssetsView;
  reload: () => void;
}

export function useInventoryAssets(): UseInventoryAssetsResult {
  const [state, dispatch] = useReducer(inventoryAssetsReducer, INITIAL_INVENTORY_ASSETS_STATE);
  const [session] = useState(() => createInventoryAssetsSession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const reload = useCallback(() => void session.reload(), [session]);

  return { ...state, view: assetsView(state), reload };
}
