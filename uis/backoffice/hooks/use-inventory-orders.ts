// Estado del Historial de /inventory/orders (entradas y salidas, de solo
// lectura). Solo consume services/inventory.service.ts (nunca HTTP directo).
// Mismo patrón que hooks/use-inventory-assets.ts:
//   1. `inventoryOrdersReducer`: transiciones de estado puras (y `ordersView`,
//      que decide cuál de los cuatro estados se muestra).
//   2. `createInventoryOrdersSession`: carga, cancelación y carreras, sin React.
//   3. `useInventoryOrders`: une ambas con hooks nativos de React.
//
// Las órdenes se guardan en el orden de la API (la más reciente primero).
// Carreras: cada carga nueva («Reintentar») aborta la anterior, y una
// respuesta que llega tarde se descarta. Tras desmontar no se despacha nada.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { InventoryServiceError, listOrders } from '@/services/inventory.service';
import type { InventoryOrder, InventoryUiError } from '@/types/inventory';

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------

export type OrdersLoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; error: InventoryUiError };

export interface InventoryOrdersState {
  /** Último historial recibido. Un fallo posterior no lo borra. */
  orders: readonly InventoryOrder[];
  /** Si ya se recibió algún historial (distingue «vacío» de «aún no cargado»). */
  loaded: boolean;
  load: OrdersLoadState;
}

export type InventoryOrdersAction =
  | { type: 'load_started' }
  | { type: 'load_succeeded'; orders: readonly InventoryOrder[] }
  | { type: 'load_failed'; error: InventoryUiError };

export const INITIAL_INVENTORY_ORDERS_STATE: InventoryOrdersState = {
  orders: [],
  loaded: false,
  load: { status: 'idle' },
};

export function inventoryOrdersReducer(state: InventoryOrdersState, action: InventoryOrdersAction): InventoryOrdersState {
  switch (action.type) {
    case 'load_started':
      return { ...state, load: { status: 'loading' } };
    case 'load_succeeded':
      return { orders: action.orders, loaded: true, load: { status: 'success' } };
    case 'load_failed':
      return { ...state, load: { status: 'error', error: action.error } };
  }
}

/** Cuál de los cuatro estados se muestra. El error manda; después, «aún no cargado». */
export type OrdersView = 'loading' | 'error' | 'empty' | 'data';

export function ordersView(state: InventoryOrdersState): OrdersView {
  if (state.load.status === 'error') return 'error';
  if (!state.loaded) return 'loading';
  return state.orders.length === 0 ? 'empty' : 'data';
}

// ---------------------------------------------------------------------------
// Sesión: carga, cancelación y carreras
// ---------------------------------------------------------------------------

export interface InventoryOrdersDependencies {
  listOrders: typeof listOrders;
}

export interface InventoryOrdersSession {
  /** Habilita el despacho y carga el historial (montaje). Compatible con StrictMode. */
  activate(): void;
  /** Desmontaje: aborta la carga en curso y deja de despachar. */
  dispose(): void;
  reload(): Promise<void>;
}

const DEFAULT_DEPENDENCIES: InventoryOrdersDependencies = { listOrders };
const FALLBACK_ERROR: InventoryUiError = { kind: 'unexpected_response' };

export function createInventoryOrdersSession(
  dispatch: (action: InventoryOrdersAction) => void,
  dependencies: InventoryOrdersDependencies = DEFAULT_DEPENDENCIES
): InventoryOrdersSession {
  let active = false;
  let run = 0;
  let controller: AbortController | null = null;

  function emit(action: InventoryOrdersAction): void {
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
      const orders = await dependencies.listOrders({ signal: ownController.signal });
      if (!active || current !== run) return;
      emit({ type: 'load_succeeded', orders });
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

export interface UseInventoryOrdersResult extends InventoryOrdersState {
  view: OrdersView;
  reload: () => void;
}

export function useInventoryOrders(): UseInventoryOrdersResult {
  const [state, dispatch] = useReducer(inventoryOrdersReducer, INITIAL_INVENTORY_ORDERS_STATE);
  const [session] = useState(() => createInventoryOrdersSession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const reload = useCallback(() => void session.reload(), [session]);

  return { ...state, view: ordersView(state), reload };
}
