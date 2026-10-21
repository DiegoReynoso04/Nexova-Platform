// Estado del formulario de Salida de activos (/inventory/orders/outbound).
// Solo consume services/inventory.service.ts (nunca HTTP directo). La lista de
// activos del selector viene de hooks/use-inventory-assets.ts.
//
// Tres piezas, igual que hooks/use-inbound-form.ts:
//   1. `outboundFormReducer`: transiciones de estado puras.
//   2. `createOutboundFormSession`: lectura del stock, envío, cancelación y
//      carreras, sin React.
//   3. `useOutboundForm`: une ambas con hooks nativos de React.
//
// A diferencia de la entrada, el activo elegido vive aquí y no en el
// formulario, porque de él depende el stock:
// - al elegir o cambiar el activo se lee su `current_stock`
//   (`GET /inventory/products/{id}`), abortando la lectura anterior; una
//   respuesta tardía de otro activo se descarta aunque el servicio ignore la
//   cancelación;
// - Cantidad se habilita cuando se conoce el stock o cuando la lectura falla
//   (con el aviso «No se pudo consultar el stock»);
// - tras una salida correcta, el formulario se vuelve a montar limpio
//   (`key = formKey`) con el activo de la URL, si lo había, y se vuelve a leer
//   su stock; tras un 400 `insufficient_stock`, se vuelve a leer el del activo
//   elegido.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { InventoryServiceError, createOutboundOrder, getAsset } from '@/services/inventory.service';
import type { ExitType, InventoryUiError, OutboundFormValues, OutboundOrder, SelectedAsset } from '@/types/inventory';

export type StockState =
  | { status: 'idle' }
  /** `previous`: el stock ya conocido de ese activo mientras se vuelve a leer. */
  | { status: 'loading'; assetId: number; previous: number | null }
  | { status: 'known'; assetId: number; currentStock: number }
  | { status: 'error'; assetId: number };

export type OutboundSubmitState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success'; order: OutboundOrder }
  | { status: 'error'; error: InventoryUiError };

export interface OutboundFormState {
  /** Activo elegido en el selector. */
  assetId: number | null;
  stock: StockState;
  submit: OutboundSubmitState;
  /** Cambia con cada salida correcta: el formulario se vuelve a montar limpio. */
  formKey: number;
}

export type OutboundFormAction =
  | { type: 'asset_selected'; assetId: number | null }
  | { type: 'stock_requested'; assetId: number }
  | { type: 'stock_loaded'; assetId: number; currentStock: number }
  | { type: 'stock_failed'; assetId: number }
  | { type: 'submit_started' }
  | { type: 'submit_succeeded'; order: OutboundOrder; nextAssetId: number | null }
  | { type: 'submit_failed'; error: InventoryUiError };

export const INITIAL_OUTBOUND_FORM_STATE: OutboundFormState = {
  assetId: null,
  stock: { status: 'idle' },
  submit: { status: 'idle' },
  formKey: 0,
};

/** El stock que se muestra: el leído o, mientras se vuelve a leer, el anterior. */
export function knownStock(stock: StockState): number | null {
  if (stock.status === 'known') return stock.currentStock;
  if (stock.status === 'loading') return stock.previous;
  return null;
}

/** Cantidad se habilita cuando hay un stock que mostrar o cuando su lectura falló. */
export function quantityEnabled(stock: StockState): boolean {
  return stock.status === 'error' || knownStock(stock) !== null;
}

export function outboundFormReducer(state: OutboundFormState, action: OutboundFormAction): OutboundFormState {
  switch (action.type) {
    case 'asset_selected':
      return { ...state, assetId: action.assetId, stock: { status: 'idle' } };
    case 'stock_requested':
      if (state.assetId !== action.assetId) return state;
      return { ...state, stock: { status: 'loading', assetId: action.assetId, previous: knownStock(state.stock) } };
    case 'stock_loaded':
      if (state.assetId !== action.assetId) return state;
      return { ...state, stock: { status: 'known', assetId: action.assetId, currentStock: action.currentStock } };
    case 'stock_failed':
      if (state.assetId !== action.assetId) return state;
      return { ...state, stock: { status: 'error', assetId: action.assetId } };
    case 'submit_started':
      return { ...state, submit: { status: 'submitting' } };
    case 'submit_succeeded':
      return {
        assetId: action.nextAssetId,
        stock: { status: 'idle' },
        submit: { status: 'success', order: action.order },
        formKey: state.formKey + 1,
      };
    case 'submit_failed':
      return { ...state, submit: { status: 'error', error: action.error } };
  }
}

/** Confirmación visible tras una salida correcta. */
export function outboundConfirmation(order: OutboundOrder): string {
  return `Salida registrada: ${order.quantity} × ${order.asset.name} (${order.asset.sku})`;
}

/** Valores del formulario para el servicio. «Asignado a» solo cuenta con una asignación. */
export function outboundFormValues(
  asset: SelectedAsset | null,
  quantity: string,
  exitType: ExitType | '',
  assignedTo: string
): OutboundFormValues {
  return { asset, quantity, exit_type: exitType, assigned_to: exitType === 'allocation' ? assignedTo : '' };
}

export interface OutboundFormDependencies {
  getAsset: typeof getAsset;
  createOutboundOrder: typeof createOutboundOrder;
}

export interface OutboundFormSession {
  activate(): void;
  /** Desmontaje: aborta la lectura del stock y el envío en curso y deja de despachar. */
  dispose(): void;
  /** Elige el activo (o ninguno) y lee su stock. */
  selectAsset(assetId: number | null): Promise<void>;
  /** `nextAssetId`: el activo con el que se vuelve a montar el formulario tras el éxito. */
  submit(values: OutboundFormValues, nextAssetId: number | null): Promise<void>;
}

const FALLBACK_ERROR: InventoryUiError = { kind: 'unexpected_response' };

export function createOutboundFormSession(
  dispatch: (action: OutboundFormAction) => void,
  dependencies: OutboundFormDependencies = { getAsset, createOutboundOrder }
): OutboundFormSession {
  let active = false;
  let stockRun = 0;
  let stockController: AbortController | null = null;
  let submitRun = 0;
  let submitController: AbortController | null = null;

  function emit(action: OutboundFormAction): void {
    if (active) dispatch(action);
  }

  /** Lee el stock de `assetId` y aborta la lectura anterior. `null` solo la cancela. */
  async function loadStock(assetId: number | null): Promise<void> {
    stockRun += 1;
    stockController?.abort();
    stockController = null;
    if (!active || assetId === null) return;
    const current = stockRun;
    const ownController = new AbortController();
    stockController = ownController;
    emit({ type: 'stock_requested', assetId });

    try {
      const asset = await dependencies.getAsset(assetId, { signal: ownController.signal });
      if (!active || current !== stockRun) return;
      emit({ type: 'stock_loaded', assetId, currentStock: asset.current_stock });
    } catch (error) {
      if (!active || current !== stockRun || error instanceof ApiAbortError) return;
      emit({ type: 'stock_failed', assetId });
    } finally {
      if (stockController === ownController) stockController = null;
    }
  }

  return {
    activate() {
      active = true;
    },

    dispose() {
      active = false;
      stockRun += 1;
      submitRun += 1;
      stockController?.abort();
      stockController = null;
      submitController?.abort();
      submitController = null;
    },

    async selectAsset(assetId) {
      if (!active) return;
      emit({ type: 'asset_selected', assetId });
      await loadStock(assetId);
    },

    async submit(values, nextAssetId) {
      // Una salida a la vez: un segundo «Registrar» mientras tanto se ignora.
      if (!active || submitController !== null) return;
      submitRun += 1;
      const current = submitRun;
      const ownController = new AbortController();
      submitController = ownController;
      emit({ type: 'submit_started' });

      let refresh: { assetId: number | null } | null = null;
      try {
        const order = await dependencies.createOutboundOrder(values, { signal: ownController.signal });
        if (!active || current !== submitRun) return;
        emit({ type: 'submit_succeeded', order, nextAssetId });
        refresh = { assetId: nextAssetId };
      } catch (error) {
        if (!active || current !== submitRun || error instanceof ApiAbortError) return;
        const uiError = error instanceof InventoryServiceError ? error.uiError : FALLBACK_ERROR;
        emit({ type: 'submit_failed', error: uiError });
        if (uiError.kind === 'api_error' && uiError.code === 'insufficient_stock' && values.asset !== null) {
          refresh = { assetId: values.asset.id };
        }
      } finally {
        if (submitController === ownController) submitController = null;
      }
      // Fuera del try y sin esperarla: la lectura del stock no es parte del envío.
      if (refresh !== null) void loadStock(refresh.assetId);
    },
  };
}

export interface UseOutboundFormResult extends OutboundFormState {
  selectAsset: (assetId: number | null) => void;
  submitOutbound: (values: OutboundFormValues, nextAssetId: number | null) => void;
}

export function useOutboundForm(): UseOutboundFormResult {
  const [state, dispatch] = useReducer(outboundFormReducer, INITIAL_OUTBOUND_FORM_STATE);
  const [session] = useState(() => createOutboundFormSession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const selectAsset = useCallback((assetId: number | null) => void session.selectAsset(assetId), [session]);
  const submitOutbound = useCallback(
    (values: OutboundFormValues, nextAssetId: number | null) => void session.submit(values, nextAssetId),
    [session]
  );

  return { ...state, selectAsset, submitOutbound };
}
