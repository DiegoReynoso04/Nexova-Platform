// Servicio del inventario (Hito 5): única capa que llama al cliente HTTP para
// /inventory (los componentes nunca lo hacen). Contrato: services/api/SPECS.md
// Parte F (§37–§38). Usa `inventoryApiClient` (lib/inventory-api-client.ts):
// el mismo cliente de la app, con la base URL de `NEXT_PUBLIC_INVENTORY_API_URL`
// y el Bearer de la sesión en todas las peticiones.
//
// Todo error que sale de aquí es `InventoryServiceError` (con un
// `InventoryUiError` para mostrar), salvo la cancelación pedida por quien
// llama, que se propaga como `ApiAbortError` porque no es un fallo que mostrar.
//
// Errores (excepción acotada a /inventory, documentada en CLAUDE.md):
// - 4xx (salvo 401 y 422) o 5xx con un `detail` de texto legible → `api_error`
//   con ese `detail`, que la UI muestra como texto bajo un título propio.
//   `insufficient_stock` va al campo `quantity`.
// - Sin cuerpo legible (no es JSON, otra forma o un `detail` que no es texto)
//   → los textos fijos de siempre (`request_invalid` / `server_error`).
// - 422 → un texto propio en español por campo, según `loc` (el `msg` de la
//   API no se muestra).
// - 401 → `session_expired` (el cliente ya borró el token).
//
// Validación en cliente (UX, antes de enviar; si no pasa, no hay petición):
// activo elegido, cantidad entera entre 1 y QUANTITY_MAX, proveedor, tipo de
// salida y `assigned_to` con `allocation`. La API sigue siendo la autoridad.
//
// Body: `asset_id` y `quantity` como números (la API usa enteros estrictos:
// "5" da 422) y `office` siempre la del activo elegido, nunca escrita por el usuario.

import {
  ApiAbortError,
  ApiConfigError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiUnauthorizedError,
  ApiUnexpectedResponseError,
  type ApiClient,
  type ApiResponse,
  type JsonValue,
} from '@/lib/api-client';
import { inventoryApiClient } from '@/lib/inventory-api-client';
import {
  normalizeApiErrorBody,
  normalizeAsset,
  normalizeAssetList,
  normalizeInboundOrder,
  normalizeInventoryValidationErrors,
  normalizeOrderList,
  normalizeOutboundOrder,
} from '@/services/normalizers';
import {
  QUANTITY_MAX,
  TEXT_MAX_LENGTH,
  type Asset,
  type ExitType,
  type InboundFormValues,
  type InboundOrder,
  type InventoryField,
  type InventoryFieldError,
  type InventoryOrder,
  type InventoryUiError,
  type OutboundFormValues,
  type OutboundOrder,
  type SelectedAsset,
} from '@/types/inventory';

const PRODUCTS_PATH = '/inventory/products';
const ORDERS_PATH = '/inventory/orders';
const INBOUND_PATH = '/inventory/orders/inbound';
const OUTBOUND_PATH = '/inventory/orders/outbound';
export const INVENTORY_TIMEOUT_MS = 10_000;

/** El 400 de stock insuficiente se muestra junto a la cantidad. */
const FIELD_BY_ERROR_CODE: Readonly<Record<string, InventoryField>> = { insufficient_stock: 'quantity' };

/** Error del servicio con un `InventoryUiError`. El mensaje solo lleva el tipo de error. */
export class InventoryServiceError extends Error {
  readonly uiError: InventoryUiError;

  constructor(uiError: InventoryUiError) {
    super(`Inventory service error: ${uiError.kind}`);
    this.name = 'InventoryServiceError';
    this.uiError = uiError;
  }
}

export interface CallOptions {
  signal?: AbortSignal;
}

export interface InventoryService {
  listAssets(options?: CallOptions): Promise<Asset[]>;
  getAsset(id: number, options?: CallOptions): Promise<Asset>;
  createInboundOrder(values: InboundFormValues, options?: CallOptions): Promise<InboundOrder>;
  createOutboundOrder(values: OutboundFormValues, options?: CallOptions): Promise<OutboundOrder>;
  listOrders(options?: CallOptions): Promise<InventoryOrder[]>;
}

export interface InventoryServiceDependencies {
  client?: ApiClient;
  /** Solo para tests; en producción se usa INVENTORY_TIMEOUT_MS. */
  timeoutMs?: number;
}

// ---------------------------------------------------------------------------
// Validación en cliente y construcción del body
// ---------------------------------------------------------------------------

/** Longitud en caracteres, como la cuenta la API (un emoji vale 1, no 2). */
function characterCount(value: string): number {
  return [...value].length;
}

/** Entero entre 1 y QUANTITY_MAX escrito por el usuario. `null` si no lo es. */
export function parseQuantity(input: string): number | null {
  const normalized = input.trim();
  if (!/^\d+$/.test(normalized)) return null;
  const quantity = Number(normalized);
  return Number.isSafeInteger(quantity) && quantity >= 1 && quantity <= QUANTITY_MAX ? quantity : null;
}

const MESSAGES = {
  asset: 'Elige un activo.',
  quantity: `Introduce una cantidad entera entre 1 y ${QUANTITY_MAX.toLocaleString('es-ES')}.`,
  supplier: `Indica el proveedor (máximo ${TEXT_MAX_LENGTH} caracteres).`,
  exitType: 'Elige el tipo de salida: asignación o consumo.',
  assignedToRequired: `Indica a quién se asigna el activo (máximo ${TEXT_MAX_LENGTH} caracteres).`,
  assignedToForbidden: 'En un consumo no se indica a quién se asigna.',
  office: 'La oficina de la orden debe ser la del activo.',
  general: 'Revisa los datos de la orden.',
} as const;

function requiredText(value: string): boolean {
  const trimmed = value.trim();
  return trimmed !== '' && characterCount(trimmed) <= TEXT_MAX_LENGTH;
}

/** Activo, cantidad y proveedor. Devuelve [] si se puede enviar. */
export function validateInboundForm(values: InboundFormValues): InventoryFieldError[] {
  const errors: InventoryFieldError[] = [];
  if (values.asset === null) errors.push({ field: 'asset_id', message: MESSAGES.asset });
  if (parseQuantity(values.quantity) === null) errors.push({ field: 'quantity', message: MESSAGES.quantity });
  if (!requiredText(values.supplier)) errors.push({ field: 'supplier', message: MESSAGES.supplier });
  return errors;
}

/** Activo, cantidad, tipo de salida y, con `allocation`, a quién se asigna. Devuelve [] si se puede enviar. */
export function validateOutboundForm(values: OutboundFormValues): InventoryFieldError[] {
  const errors: InventoryFieldError[] = [];
  if (values.asset === null) errors.push({ field: 'asset_id', message: MESSAGES.asset });
  if (parseQuantity(values.quantity) === null) errors.push({ field: 'quantity', message: MESSAGES.quantity });
  if (values.exit_type === '') errors.push({ field: 'exit_type', message: MESSAGES.exitType });
  if (values.exit_type === 'allocation' && !requiredText(values.assigned_to)) {
    errors.push({ field: 'assigned_to', message: MESSAGES.assignedToRequired });
  }
  return errors;
}

/** Body de `POST /inventory/orders/inbound`, campo a campo. `office` es la del activo. */
export function buildInboundPayload(asset: SelectedAsset, quantity: number, supplier: string): { [key: string]: JsonValue } {
  return { asset_id: asset.id, quantity, supplier: supplier.trim(), office: asset.office };
}

/** Body de `POST /inventory/orders/outbound`. `assigned_to` es `null` en un consumo. */
export function buildOutboundPayload(
  asset: SelectedAsset,
  quantity: number,
  exitType: ExitType,
  assignedTo: string
): { [key: string]: JsonValue } {
  return {
    asset_id: asset.id,
    quantity,
    exit_type: exitType,
    assigned_to: exitType === 'allocation' ? assignedTo.trim() : null,
    office: asset.office,
  };
}

// ---------------------------------------------------------------------------
// Traducción de errores
// ---------------------------------------------------------------------------

function fail(uiError: InventoryUiError): InventoryServiceError {
  return new InventoryServiceError(uiError);
}

async function readJsonOrNull<T>(response: ApiResponse, parse: (body: JsonValue) => T): Promise<T | null> {
  try {
    return await response.json(parse);
  } catch (error) {
    if (error instanceof ApiUnexpectedResponseError) return null;
    throw error;
  }
}

/** Texto propio de un 422 según el campo. `exitType` decide el texto de `assigned_to`. */
function validationMessage(field: InventoryField | null, exitType: ExitType | null): string {
  switch (field) {
    case 'asset_id':
      return MESSAGES.asset;
    case 'quantity':
      return MESSAGES.quantity;
    case 'supplier':
      return MESSAGES.supplier;
    case 'exit_type':
      return MESSAGES.exitType;
    case 'assigned_to':
      return exitType === 'consumption' ? MESSAGES.assignedToForbidden : MESSAGES.assignedToRequired;
    case 'office':
      return MESSAGES.office;
    case null:
      return MESSAGES.general;
  }
}

/** Status + cuerpo de error → `InventoryUiError`. Manda el status. */
async function failFromResponse(response: ApiResponse, exitType: ExitType | null): Promise<never> {
  const { status } = response;
  if (status === 422) {
    const fields = (await readJsonOrNull(response, normalizeInventoryValidationErrors)) ?? [];
    const unique = [...new Set(fields)];
    throw fail(
      unique.length > 0
        ? { kind: 'validation', source: 'api', errors: unique.map((field) => ({ field, message: validationMessage(field, exitType) })) }
        : { kind: 'request_invalid' }
    );
  }
  if (status >= 400) {
    // `normalizeApiErrorBody` solo deja `detail` si es texto: un objeto o una lista se descartan.
    const body = await readJsonOrNull(response, normalizeApiErrorBody);
    const detail = body?.detail?.trim() ?? '';
    if (body !== null && detail !== '') {
      const code = body.code;
      const field = code === null ? null : (FIELD_BY_ERROR_CODE[code] ?? null);
      throw fail({ kind: 'api_error', status, code, detail, field });
    }
    throw fail(status >= 500 ? { kind: 'server_error' } : { kind: 'request_invalid' });
  }
  throw fail({ kind: 'unexpected_response' });
}

/** Ejecuta una operación y garantiza que solo salen InventoryServiceError o ApiAbortError. */
async function guarded<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof InventoryServiceError || error instanceof ApiAbortError) throw error;
    if (error instanceof ApiConfigError) throw fail({ kind: 'config' });
    // 401: el cliente ya borró el token; el guard de rutas redirige a /login.
    if (error instanceof ApiUnauthorizedError) throw fail({ kind: 'session_expired' });
    if (error instanceof ApiTimeoutError) throw fail({ kind: 'timeout' });
    if (error instanceof ApiNetworkError) throw fail({ kind: 'network' });
    throw fail({ kind: 'unexpected_response' });
  }
}

// ---------------------------------------------------------------------------
// Servicio
// ---------------------------------------------------------------------------

export function createInventoryService(dependencies: InventoryServiceDependencies = {}): InventoryService {
  const client = dependencies.client ?? inventoryApiClient;
  const timeoutMs = dependencies.timeoutMs ?? INVENTORY_TIMEOUT_MS;

  function expect<T>(successStatus: number, parse: (body: JsonValue) => T, exitType: ExitType | null = null) {
    return async (response: ApiResponse): Promise<T> => {
      if (response.status !== successStatus) return failFromResponse(response, exitType);
      return response.json(parse);
    };
  }

  return {
    listAssets(options = {}) {
      return guarded(() => client.get(PRODUCTS_PATH, { timeoutMs, signal: options.signal }, expect(200, normalizeAssetList)));
    },

    getAsset(id, options = {}) {
      return guarded(() =>
        client.get(`${PRODUCTS_PATH}/${id}`, { timeoutMs, signal: options.signal }, expect(200, normalizeAsset))
      );
    },

    createInboundOrder(values, options = {}) {
      return guarded(async () => {
        const errors = validateInboundForm(values);
        const quantity = parseQuantity(values.quantity);
        if (errors.length > 0 || values.asset === null || quantity === null) {
          throw fail({ kind: 'validation', source: 'client', errors });
        }
        return client.postJson(
          INBOUND_PATH,
          buildInboundPayload(values.asset, quantity, values.supplier),
          { timeoutMs, signal: options.signal },
          expect(201, normalizeInboundOrder)
        );
      });
    },

    createOutboundOrder(values, options = {}) {
      return guarded(async () => {
        const errors = validateOutboundForm(values);
        const quantity = parseQuantity(values.quantity);
        if (errors.length > 0 || values.asset === null || quantity === null || values.exit_type === '') {
          throw fail({ kind: 'validation', source: 'client', errors });
        }
        return client.postJson(
          OUTBOUND_PATH,
          buildOutboundPayload(values.asset, quantity, values.exit_type, values.assigned_to),
          { timeoutMs, signal: options.signal },
          expect(201, normalizeOutboundOrder, values.exit_type)
        );
      });
    },

    listOrders(options = {}) {
      return guarded(() => client.get(ORDERS_PATH, { timeoutMs, signal: options.signal }, expect(200, normalizeOrderList)));
    },
  };
}

const defaultService = createInventoryService();

export const listAssets: InventoryService['listAssets'] = (options) => defaultService.listAssets(options);
export const getAsset: InventoryService['getAsset'] = (id, options) => defaultService.getAsset(id, options);
export const createInboundOrder: InventoryService['createInboundOrder'] = (values, options) =>
  defaultService.createInboundOrder(values, options);
export const createOutboundOrder: InventoryService['createOutboundOrder'] = (values, options) =>
  defaultService.createOutboundOrder(values, options);
export const listOrders: InventoryService['listOrders'] = (options) => defaultService.listOrders(options);
