// Estado del formulario de Entrada de activos (/inventory/orders/inbound).
// Solo consume services/inventory.service.ts (nunca HTTP directo). La lista de
// activos del selector viene de hooks/use-inventory-assets.ts.
//
// Tres piezas, igual que hooks/use-incident-form.ts:
//   1. `inboundFormReducer`: transiciones de estado puras.
//   2. `createInboundFormSession`: envío, cancelación y carreras, sin React.
//   3. `useInboundForm`: une ambas con hooks nativos de React.
//
// La validación en cliente la hace el servicio antes de enviar: si no pasa,
// devuelve un error de validación sin hacer ninguna petición.
//
// Tras una entrada correcta `formKey` cambia: la vista lo usa como `key` del
// formulario, que se vuelve a montar limpio (con el activo de la URL, si lo
// había), y la confirmación se mantiene visible hasta el siguiente envío.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { InventoryServiceError, createInboundOrder } from '@/services/inventory.service';
import type { InboundFormValues, InboundOrder, InventoryUiError } from '@/types/inventory';

export type InboundSubmitState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success'; order: InboundOrder }
  | { status: 'error'; error: InventoryUiError };

export interface InboundFormState {
  submit: InboundSubmitState;
  /** Cambia con cada entrada correcta: el formulario se vuelve a montar limpio. */
  formKey: number;
}

export type InboundFormAction =
  | { type: 'submit_started' }
  | { type: 'submit_succeeded'; order: InboundOrder }
  | { type: 'submit_failed'; error: InventoryUiError };

export const INITIAL_INBOUND_FORM_STATE: InboundFormState = { submit: { status: 'idle' }, formKey: 0 };

export function inboundFormReducer(state: InboundFormState, action: InboundFormAction): InboundFormState {
  switch (action.type) {
    case 'submit_started':
      return { ...state, submit: { status: 'submitting' } };
    case 'submit_succeeded':
      return { submit: { status: 'success', order: action.order }, formKey: state.formKey + 1 };
    case 'submit_failed':
      return { ...state, submit: { status: 'error', error: action.error } };
  }
}

/** Confirmación visible tras una entrada correcta. */
export function inboundConfirmation(order: InboundOrder): string {
  return `Entrada registrada: ${order.quantity} × ${order.asset.name} (${order.asset.sku})`;
}

export interface InboundFormDependencies {
  createInboundOrder: typeof createInboundOrder;
}

export interface InboundFormSession {
  activate(): void;
  /** Desmontaje: aborta el envío en curso y deja de despachar. */
  dispose(): void;
  submit(values: InboundFormValues): Promise<void>;
}

const FALLBACK_ERROR: InventoryUiError = { kind: 'unexpected_response' };

export function createInboundFormSession(
  dispatch: (action: InboundFormAction) => void,
  dependencies: InboundFormDependencies = { createInboundOrder }
): InboundFormSession {
  let active = false;
  let run = 0;
  let controller: AbortController | null = null;

  function emit(action: InboundFormAction): void {
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
      // Un envío a la vez: un segundo «Registrar» mientras tanto se ignora.
      if (!active || controller !== null) return;
      run += 1;
      const current = run;
      const ownController = new AbortController();
      controller = ownController;
      emit({ type: 'submit_started' });

      try {
        const order = await dependencies.createInboundOrder(values, { signal: ownController.signal });
        if (!active || current !== run) return;
        emit({ type: 'submit_succeeded', order });
      } catch (error) {
        if (!active || current !== run || error instanceof ApiAbortError) return;
        emit({ type: 'submit_failed', error: error instanceof InventoryServiceError ? error.uiError : FALLBACK_ERROR });
      } finally {
        if (controller === ownController) controller = null;
      }
    },
  };
}

export interface UseInboundFormResult extends InboundFormState {
  submitInbound: (values: InboundFormValues) => void;
}

export function useInboundForm(): UseInboundFormResult {
  const [state, dispatch] = useReducer(inboundFormReducer, INITIAL_INBOUND_FORM_STATE);
  const [session] = useState(() => createInboundFormSession(dispatch));

  useEffect(() => {
    session.activate();
    return () => session.dispose();
  }, [session]);

  const submitInbound = useCallback((values: InboundFormValues) => void session.submit(values), [session]);

  return { ...state, submitInbound };
}
