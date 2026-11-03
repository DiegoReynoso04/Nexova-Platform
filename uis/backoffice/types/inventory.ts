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
/** Moneda de las entradas: la de la oficina, la pone la API (P3 del plan de telemetría). */
export const CURRENCIES = ['EUR', 'USD'] as const;

/** Cantidad máxima de una orden: el máximo de `int4` que acepta la API (SPECS §35, F3-2). */
export const QUANTITY_MAX = 2_147_483_647;
/** Tope de los textos libres de la API (`supplier`, `assigned_to`; SPECS §35, F3-1). */
export const TEXT_MAX_LENGTH = 200;
/** Coste unitario máximo que acepta la API: `NUMERIC(12,2)` (P3). */
export const UNIT_COST_MAX = 9_999_999_999.99;

export type AssetCategory = (typeof ASSET_CATEGORIES)[number];
export type Office = (typeof OFFICES)[number];
export type ExitType = (typeof EXIT_TYPES)[number];
export type OrderType = (typeof ORDER_TYPES)[number];
export type Currency = (typeof CURRENCIES)[number];

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
  /** Coste unitario (P3); `null` en las entradas anteriores al coste y en las del seed. */
  unit_cost: number | null;
  currency: Currency | null;
}

/** Variación del coste frente a la media de las entradas anteriores del mismo activo y proveedor (P10). */
export interface CostVariance {
  reference_unit_cost: number;
  variance_pct: number;
  direction: 'increase' | 'decrease';
  threshold_pct: number;
  reference_window: number;
}

/** Respuesta 201 de una entrada: además, lo que el frontend necesita para la telemetría (D1 «A ligera»). */
export interface InboundOrderCreated extends InboundOrder {
  /** HMAC del proveedor (P9); `null` si la API no tiene la clave configurada. */
  supplier_key: string | null;
  cost_variance: CostVariance | null;
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

/** Respuesta 201 de una salida: el stock que calculó la API (bajo `FOR UPDATE`) y el mínimo configurado. */
export interface OutboundOrderCreated extends OutboundOrder {
  stock_before: number;
  stock_after: number;
  min_stock: number;
  currency: Currency;
}

/** Elemento de `GET /inventory/orders`, distinguido por `type`. */
export type InventoryOrder = InboundOrder | OutboundOrder;

/**
 * Lo que el formulario necesita del activo elegido: su id y su oficina, que es
 * la que se envía. La categoría no se envía: la usa la telemetría.
 */
export type SelectedAsset = Pick<Asset, 'id' | 'office' | 'category'>;

/** Valores del formulario de entrada tal como los escribe el usuario. */
export interface InboundFormValues {
  asset: SelectedAsset | null;
  quantity: string;
  supplier: string;
  /** Coste unitario tal como lo escribe el usuario (admite coma decimal). */
  unit_cost: string;
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
export type InventoryField = 'asset_id' | 'quantity' | 'supplier' | 'unit_cost' | 'exit_type' | 'assigned_to' | 'office';

/**
 * Un error de validación, del cliente o de un 422 de la API. `message` es
 * siempre un texto propio en español; `field` es `null` si no corresponde a un
 * campo del formulario. En un 422, `apiMessage` es el `msg` de la API (sin el
 * prefijo `Value error, `, solo si es texto no vacío de hasta 300 caracteres),
 * que la UI muestra debajo, como texto secundario plano (decisión del usuario,
 * opción 3: el brief pide mostrar el mensaje del cuerpo).
 */
export interface InventoryFieldError {
  field: InventoryField | null;
  message: string;
  apiMessage?: string;
}

/** Longitud máxima del `msg` de un 422 que se muestra; uno más largo se descarta. */
export const API_MESSAGE_MAX_LENGTH = 300;

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
