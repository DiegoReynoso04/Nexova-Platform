// Los 4 obligatorios del BRIEFING que emite el backoffice (decisión D1 «A
// ligera»): la API calcula y el frontend emite. Todo sale de la respuesta 201
// de la API (`InboundOrderCreated`, `OutboundOrderCreated`) y de la categoría
// del activo elegido: aquí no se calcula ni se inventa nada.
//
// - Salida → `outbound_order_created` y, si cruza el mínimo
//   (`stock_before >= min_stock` y `stock_after < min_stock`, plan D4),
//   `stock_threshold_triggered`.
// - Entrada → `inbound_order_created` y, si la API detectó una variación,
//   `kit_cost_variance_detected`. Sin `unit_cost` o sin `supplier_key` (la API
//   sin `TELEMETRY_SUPPLIER_KEY`) no se emiten: el esquema los exige.
// - `product_category` y `programme_id` van en `null` hasta que exista la
//   clasificación de activos (P1; el esquema lo admite, D1-a).
// - Nunca el nombre del activo, el proveedor ni `assigned_to` (PII, BRIEFING §3).
//
// `direct_stock_edit_rejected`, el quinto obligatorio, lo emite la API (P7).

import { ApiAbortError } from '@/lib/api-client';
import type { FormTelemetry } from '@/lib/form-telemetry';
import { track } from '@/lib/telemetry';
import { InventoryServiceError, type CallOptions } from '@/services/inventory.service';
import type {
  AssetCategory,
  Currency,
  InboundOrderCreated,
  InventoryUiError,
  Office,
  OutboundOrderCreated,
} from '@/types/inventory';
import type { FormOutcome, TelemetryEventProperties, TelemetryEventType, TelemetryOffice } from '@/types/telemetry';

type Track = <E extends TelemetryEventType>(eventType: E, properties: TelemetryEventProperties[E]) => void;

const ASSET_CATEGORY_VALUES: readonly AssetCategory[] = ['hardware', 'peripherals', 'office_supplies', 'training_materials'];

/** D6: la oficina en minúsculas. */
function officeLabel(office: Office): TelemetryOffice {
  return office === 'Valencia' ? 'valencia' : 'miami';
}

function minimum(order: { office: Office; asset: { id: number }; quantity: number }, currency: Currency, category: AssetCategory) {
  return {
    office: officeLabel(order.office),
    product_id: order.asset.id,
    product_category: null,
    programme_id: null,
    quantity: order.quantity,
    currency,
    asset_category: category,
  };
}

function knownCategory(category: AssetCategory | undefined): category is AssetCategory {
  return ASSET_CATEGORY_VALUES.some((value) => value === category);
}

/** Eventos de una salida registrada. */
export function trackOutboundOrder(order: OutboundOrderCreated, category: AssetCategory | undefined, emit: Track = track): void {
  if (!knownCategory(category)) return;
  const base = minimum(order, order.currency, category);
  emit('outbound_order_created', { ...base, outbound_order_id: order.id, exit_type: order.exit_type, stock_after: order.stock_after });
  if (order.min_stock > 0 && order.stock_before >= order.min_stock && order.stock_after < order.min_stock) {
    emit('stock_threshold_triggered', {
      ...base,
      outbound_order_id: order.id,
      stock_before: order.stock_before,
      stock_after: order.stock_after,
      min_stock: order.min_stock,
    });
  }
}

/** Eventos de una entrada registrada. */
export function trackInboundOrder(order: InboundOrderCreated, category: AssetCategory | undefined, emit: Track = track): void {
  const { unit_cost: unitCost, currency, supplier_key: supplierKey } = order;
  if (!knownCategory(category) || unitCost === null || currency === null || supplierKey === null) return;
  const base = { ...minimum(order, currency, category), inbound_order_id: order.id, supplier_key: supplierKey };
  emit('inbound_order_created', { ...base, unit_cost: unitCost });
  if (order.cost_variance !== null) {
    emit('kit_cost_variance_detected', { ...base, unit_cost: unitCost, ...order.cost_variance });
  }
}

// ---------------------------------------------------------------------------
// Embudo de los formularios de Entrada y Salida
// ---------------------------------------------------------------------------

/** `kind` del error del servicio → `outcome` de `form_submitted` (plan §6.5). */
export function inventoryFormOutcome(error: InventoryUiError): FormOutcome {
  switch (error.kind) {
    case 'validation':
      return 'validation_error';
    case 'api_error':
      return error.status >= 500 ? 'server_error' : 'api_rejected';
    case 'request_invalid':
      return 'api_rejected';
    case 'session_expired':
      return 'session_expired';
    case 'network':
    case 'timeout':
    case 'config':
      return 'network_error';
    case 'server_error':
    case 'unexpected_response':
      return 'server_error';
  }
}

/**
 * Envuelve el envío del servicio para la telemetría, sin cambiar lo que
 * devuelve ni lo que lanza: validación en cliente → `form_validation_failed`;
 * fin del envío → `form_submitted`; éxito → `onCreated` (los obligatorios).
 * Una cancelación (`ApiAbortError`) no es un envío terminado.
 */
export function observeInventorySubmit<V, R>(
  submit: (values: V, options?: CallOptions) => Promise<R>,
  telemetry: Pick<FormTelemetry, 'validationFailed' | 'submitted'>,
  onCreated: (order: R, values: V) => void
): (values: V, options?: CallOptions) => Promise<R> {
  return async (values, options) => {
    try {
      const order = await submit(values, options);
      telemetry.submitted('success');
      onCreated(order, values);
      return order;
    } catch (error) {
      if (error instanceof InventoryServiceError) {
        const uiError = error.uiError;
        if (uiError.kind === 'validation' && uiError.source === 'client') {
          telemetry.validationFailed(uiError.errors.map((item) => item.field ?? 'general'));
        } else {
          telemetry.submitted(inventoryFormOutcome(uiError));
        }
      } else if (!(error instanceof ApiAbortError)) {
        telemetry.submitted('server_error');
      }
      throw error;
    }
  };
}
