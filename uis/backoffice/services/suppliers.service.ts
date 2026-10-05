// Servicio del directorio de proveedores: única capa que llama al cliente HTTP
// para esta funcionalidad (los componentes nunca lo hacen). Contrato:
// services/api/SPECS.md Parte B (§11–§12) y §4 (formato de errores).
//
// Todo error que sale de aquí es `SupplierServiceError` (con un
// `SupplierUiError` para mostrar), salvo la cancelación pedida por quien
// llama, que se propaga como `ApiAbortError` porque no es un fallo que mostrar.
//
// Validación en cliente: solo campos requeridos y tarifa > 0 (UX, antes de
// enviar). Las reglas completas (país, moneda coherente, categorías, estado,
// fecha) las aplica la API y sus 422 se muestran tal cual por campo.
//
// No hay operación de borrado: `DELETE /suppliers/{id}` existe en la API pero
// la UI no lo expone (suspensión controlada; SPECS §10).

import {
  ApiAbortError,
  ApiConfigError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiUnauthorizedError,
  ApiUnexpectedResponseError,
  apiClient,
  type ApiClient,
  type ApiResponse,
  type JsonValue,
} from '@/lib/api-client';
import {
  normalizeApiErrorBody,
  normalizeSupplier,
  normalizeSupplierList,
  normalizeValidationErrors,
} from '@/services/normalizers';
import type {
  FieldError,
  Supplier,
  SupplierFilters,
  SupplierFormValues,
  SupplierStatus,
  SupplierUiError,
} from '@/types/suppliers';

const SUPPLIERS_PATH = '/suppliers';
export const SUPPLIERS_TIMEOUT_MS = 10_000;

/** Error del servicio con un `SupplierUiError`. El mensaje solo lleva el tipo de error. */
export class SupplierServiceError extends Error {
  readonly uiError: SupplierUiError;

  constructor(uiError: SupplierUiError) {
    super(`Supplier service error: ${uiError.kind}`);
    this.name = 'SupplierServiceError';
    this.uiError = uiError;
  }
}

export interface CallOptions {
  signal?: AbortSignal;
}

export interface SuppliersService {
  listSuppliers(filters: SupplierFilters, options?: CallOptions): Promise<Supplier[]>;
  createSupplier(values: SupplierFormValues, options?: CallOptions): Promise<Supplier>;
  updateSupplierRate(id: number, rateInput: string, options?: CallOptions): Promise<Supplier>;
  updateSupplierStatus(id: number, status: SupplierStatus, options?: CallOptions): Promise<Supplier>;
}

export interface SuppliersServiceDependencies {
  client?: ApiClient;
  /** Solo para tests; en producción se usa SUPPLIERS_TIMEOUT_MS. */
  timeoutMs?: number;
}

// ---------------------------------------------------------------------------
// Validación en cliente y construcción del body
// ---------------------------------------------------------------------------

/** Número > 0 escrito por el usuario (acepta coma decimal). `null` si no lo es. */
export function parseRate(input: string): number | null {
  const normalized = input.trim().replace(',', '.');
  if (normalized === '' || !/^\d+(\.\d+)?$/.test(normalized)) return null;
  const rate = Number(normalized);
  return Number.isFinite(rate) && rate > 0 ? rate : null;
}

const RATE_ERROR = 'Introduce una tarifa mensual mayor que 0.';

/** Campos requeridos del CONTEXT y tarifa > 0. Devuelve [] si se puede enviar. */
export function validateSupplierForm(values: SupplierFormValues): FieldError[] {
  const errors: FieldError[] = [];
  if (values.name.trim() === '') errors.push({ field: 'name', message: 'El nombre es obligatorio.' });
  if (values.country === '') errors.push({ field: 'country', message: 'Selecciona un país.' });
  if (values.categories.length === 0) errors.push({ field: 'categories', message: 'Selecciona al menos una categoría.' });
  if (parseRate(values.monthly_rate) === null) errors.push({ field: 'monthly_rate', message: RATE_ERROR });
  if (values.currency === '') errors.push({ field: 'currency', message: 'Selecciona una moneda.' });
  if (values.status === '') errors.push({ field: 'status', message: 'Selecciona un estado.' });
  return errors;
}

/**
 * Body de `POST /suppliers`, construido campo a campo. Los opcionales vacíos
 * no se envían (la API los guarda como `null`). Nunca incluye `id` ni
 * `updated_at`: los genera el sistema.
 */
export function buildSupplierPayload(values: SupplierFormValues, monthlyRate: number): { [key: string]: JsonValue } {
  const payload: { [key: string]: JsonValue } = {
    name: values.name.trim(),
    country: values.country,
    categories: [...values.categories],
    monthly_rate: monthlyRate,
    currency: values.currency,
    status: values.status,
  };
  const optional = {
    contract_renewal_date: values.contract_renewal_date.trim(),
    contact_email: values.contact_email.trim(),
    notes: values.notes.trim(),
  };
  for (const [key, value] of Object.entries(optional)) {
    if (value !== '') payload[key] = value;
  }
  return payload;
}

/** `?country=…&category=…` solo con los filtros activos. */
export function suppliersQuery(filters: SupplierFilters): string {
  const params = new URLSearchParams();
  if (filters.country !== null) params.set('country', filters.country);
  if (filters.category !== null) params.set('category', filters.category);
  const query = params.toString();
  return query === '' ? SUPPLIERS_PATH : `${SUPPLIERS_PATH}?${query}`;
}

// ---------------------------------------------------------------------------
// Traducción de errores
// ---------------------------------------------------------------------------

function fail(uiError: SupplierUiError): SupplierServiceError {
  return new SupplierServiceError(uiError);
}

function clientValidation(errors: readonly FieldError[]): SupplierServiceError {
  return fail({ kind: 'validation', source: 'client', errors });
}

async function readJsonOrNull<T>(response: ApiResponse, parse: (body: JsonValue) => T): Promise<T | null> {
  try {
    return await response.json(parse);
  } catch (error) {
    if (error instanceof ApiUnexpectedResponseError) return null;
    throw error;
  }
}

/** Status + cuerpo de error → `SupplierUiError`. Manda el status. */
async function failFromResponse(response: ApiResponse): Promise<never> {
  const { status } = response;
  if (status === 422) {
    const errors = (await readJsonOrNull(response, normalizeValidationErrors)) ?? [];
    throw fail(errors.length > 0 ? { kind: 'validation', source: 'api', errors } : { kind: 'request_invalid' });
  }
  if (status === 404) {
    const body = await readJsonOrNull(response, normalizeApiErrorBody);
    throw fail(body?.code === 'supplier_not_found' ? { kind: 'not_found' } : { kind: 'request_invalid' });
  }
  if (status >= 500) throw fail({ kind: 'server_error' });
  if (status >= 400) throw fail({ kind: 'request_invalid' });
  throw fail({ kind: 'unexpected_response' });
}

/** Ejecuta una operación y garantiza que solo salen SupplierServiceError o ApiAbortError. */
async function guarded<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof SupplierServiceError || error instanceof ApiAbortError) throw error;
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

export function createSuppliersService(dependencies: SuppliersServiceDependencies = {}): SuppliersService {
  const client = dependencies.client ?? apiClient;
  const timeoutMs = dependencies.timeoutMs ?? SUPPLIERS_TIMEOUT_MS;

  function expect<T>(successStatus: number, parse: (body: JsonValue) => T) {
    return async (response: ApiResponse): Promise<T> => {
      if (response.status !== successStatus) return failFromResponse(response);
      return response.json(parse);
    };
  }

  return {
    listSuppliers(filters, options = {}) {
      return guarded(() =>
        client.get(suppliersQuery(filters), { timeoutMs, signal: options.signal }, expect(200, normalizeSupplierList))
      );
    },

    createSupplier(values, options = {}) {
      return guarded(async () => {
        const errors = validateSupplierForm(values);
        const monthlyRate = parseRate(values.monthly_rate);
        if (errors.length > 0 || monthlyRate === null) throw clientValidation(errors);
        return client.postJson(
          SUPPLIERS_PATH,
          buildSupplierPayload(values, monthlyRate),
          { timeoutMs, signal: options.signal },
          expect(201, normalizeSupplier)
        );
      });
    },

    updateSupplierRate(id, rateInput, options = {}) {
      return guarded(async () => {
        const monthlyRate = parseRate(rateInput);
        if (monthlyRate === null) throw clientValidation([{ field: 'monthly_rate', message: RATE_ERROR }]);
        return client.patchJson(
          `${SUPPLIERS_PATH}/${id}/rate`,
          { monthly_rate: monthlyRate },
          { timeoutMs, signal: options.signal },
          expect(200, normalizeSupplier)
        );
      });
    },

    updateSupplierStatus(id, status, options = {}) {
      return guarded(() =>
        client.patchJson(
          `${SUPPLIERS_PATH}/${id}/status`,
          { status },
          { timeoutMs, signal: options.signal },
          expect(200, normalizeSupplier)
        )
      );
    },
  };
}

const defaultService = createSuppliersService();

export const listSuppliers: SuppliersService['listSuppliers'] = (filters, options) =>
  defaultService.listSuppliers(filters, options);
export const createSupplier: SuppliersService['createSupplier'] = (values, options) =>
  defaultService.createSupplier(values, options);
export const updateSupplierRate: SuppliersService['updateSupplierRate'] = (id, rateInput, options) =>
  defaultService.updateSupplierRate(id, rateInput, options);
export const updateSupplierStatus: SuppliersService['updateSupplierStatus'] = (id, status, options) =>
  defaultService.updateSupplierStatus(id, status, options);
