// Contrato que recibe y envía el frontend del inventario (Hito 5).
// Fuente: services/api/SPECS.md Parte F (§37–§38) y
// services/api/app/modules/inventory/schemas.py. Entidades, campos y
// vocabulario: docs/context-nexova-gestion-inventario-hito-5.md. Prohibido
// añadir campos o valores que no estén ahí.
//
// Excepción documentada en CLAUDE.md (como en /suppliers): el vocabulario vive
// también en el frontend, porque los formularios y las etiquetas lo necesitan y
// la API no lo publica. Se muestra tal cual y la API sigue siendo la autoridad.
// `tests/inventory-contract.test.mjs` comprueba que coincide con el CONTEXT y
// con el backend.

export const ASSET_CATEGORIES = ['hardware', 'peripherals', 'office_supplies', 'training_materials'] as const;
export const OFFICES = ['Valencia', 'Miami'] as const;
export const EXIT_TYPES = ['allocation', 'consumption'] as const;
export const ORDER_TYPES = ['inbound', 'outbound'] as const;

/** Cantidad máxima de una orden: el máximo de `int4` que acepta la API (SPECS §35, F3-2). */
export const QUANTITY_MAX = 2_147_483_647;
/** Tope de los textos libres de la API (`supplier`, `assigned_to`; SPECS §35, F3-1). */
export const TEXT_MAX_LENGTH = 200;

export type AssetCategory = (typeof ASSET_CATEGORIES)[number];
export type Office = (typeof OFFICES)[number];
export type ExitType = (typeof EXIT_TYPES)[number];
export type OrderType = (typeof ORDER_TYPES)[number];

/** Activo tal como lo devuelve la API (`GET /inventory/products`, `GET /inventory/products/{id}`). */
export interface Asset {
  id: number;
  name: string;
  sku: string;
  category: AssetCategory;
  office: Office;
  /** Calculado por la API: entradas − salidas. Nunca se envía. */
  current_stock: number;
}

/** El activo embebido en cada orden. */
export interface AssetSummary {
  id: number;
  name: string;
  sku: string;
}

/** Entrada de activos (`AssetEntry`): una compra o entrega recibida. */
export interface InboundOrder {
  type: 'inbound';
  id: number;
  asset: AssetSummary;
  quantity: number;
  supplier: string;
  office: Office;
  /** ISO 8601 en UTC. */
  created_at: string;
  user_uuid: string;
}

/** Salida de activos (`AssetExit`): una asignación a un empleado o un consumo. */
export interface OutboundOrder {
  type: 'outbound';
  id: number;
  asset: AssetSummary;
  quantity: number;
  exit_type: ExitType;
  /** Obligatorio con `allocation`; `null` con `consumption`. */
  assigned_to: string | null;
  office: Office;
  /** ISO 8601 en UTC. */
  created_at: string;
  user_uuid: string;
}

/** Elemento de `GET /inventory/orders`, distinguido por `type`. */
export type InventoryOrder = InboundOrder | OutboundOrder;

/** Lo que el formulario necesita del activo elegido: su id y su oficina, que es la que se envía. */
export type SelectedAsset = Pick<Asset, 'id' | 'office'>;

/** Valores del formulario de entrada tal como los escribe el usuario. */
export interface InboundFormValues {
  asset: SelectedAsset | null;
  quantity: string;
  supplier: string;
}

/** Valores del formulario de salida tal como los escribe el usuario. */
export interface OutboundFormValues {
  asset: SelectedAsset | null;
  quantity: string;
  exit_type: ExitType | '';
  /** Solo se envía con `allocation`; con `consumption` se envía `null`. */
  assigned_to: string;
}

/** Campos que pueden tener un error asociado (los del request de la API). */
export type InventoryField = 'asset_id' | 'quantity' | 'supplier' | 'exit_type' | 'assigned_to' | 'office';

/**
 * Un error de validación, del cliente o de un 422 de la API. `message` es
 * siempre un texto propio en español (nunca el `msg` de la API); `field` es
 * `null` si no corresponde a un campo del formulario.
 */
export interface InventoryFieldError {
  field: InventoryField | null;
  message: string;
}

/** Errores que la UI del inventario sabe presentar. */
export type InventoryUiError =
  | { kind: 'validation'; source: 'client' | 'api'; errors: readonly InventoryFieldError[] }
  /**
   * 4xx (salvo 401 y 422) o 5xx con un cuerpo `{detail, code}` legible: la UI
   * muestra un título propio y el `detail` de la API como texto (excepción de
   * CLAUDE.md, solo para /inventory). `field` sitúa el error junto a un campo
   * (`insufficient_stock` → `quantity`).
   */
  | { kind: 'api_error'; status: number; code: string | null; detail: string; field: InventoryField | null }
  /** 4xx sin cuerpo legible. */
  | { kind: 'request_invalid' }
  /** 5xx sin cuerpo legible. */
  | { kind: 'server_error' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' }
  | { kind: 'session_expired' };
