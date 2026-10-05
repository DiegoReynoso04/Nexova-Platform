// Contrato que recibe y envía el frontend del directorio de proveedores.
// Fuente: services/api/SPECS.md Parte B (§11–§12) y app/models.py del backend.
// Vocabulario del dominio: docs/ligthweight-storage-api.md ("Modelo de
// proveedor", "Categorías válidas", "Estados válidos"). Prohibido añadir
// campos o valores que no estén ahí.
//
// Excepción documentada en CLAUDE.md: a diferencia de /incidents, estas listas
// SÍ viven en el frontend, porque los filtros y el formulario necesitan
// ofrecerlas y la API no tiene un endpoint que las publique. Se muestran tal
// cual (en inglés) y el backend sigue siendo la autoridad: valida y responde 422.
// `tests/suppliers-contract.test.mjs` comprueba que coinciden con el CONTEXT.

export const SUPPLIER_COUNTRIES = ['Spain', 'USA'] as const;
export const SUPPLIER_CURRENCIES = ['EUR', 'USD'] as const;
export const SUPPLIER_CATEGORIES = [
  'job_boards',
  'ats_software',
  'assessment_tools',
  'training_platforms',
  'payroll_and_hr_software',
  'video_interview',
  'background_check',
  'office_and_facilities',
  'it_and_software_licenses',
] as const;
export const SUPPLIER_STATUSES = ['active', 'suspended'] as const;

export type SupplierCountry = (typeof SUPPLIER_COUNTRIES)[number];
export type SupplierCurrency = (typeof SUPPLIER_CURRENCIES)[number];
export type SupplierCategory = (typeof SUPPLIER_CATEGORIES)[number];
export type SupplierStatus = (typeof SUPPLIER_STATUSES)[number];

/** Proveedor tal como lo devuelve la API (`GET`, `POST`, `PATCH`). */
export interface Supplier {
  id: number;
  name: string;
  country: SupplierCountry;
  categories: readonly SupplierCategory[];
  monthly_rate: number;
  currency: SupplierCurrency;
  /** ISO 8601 UTC. Lo genera el sistema al crear y en cada cambio de tarifa. */
  updated_at: string;
  status: SupplierStatus;
  /** `YYYY-MM-DD` o `null`. */
  contract_renewal_date: string | null;
  contact_email: string | null;
  notes: string | null;
}

/** Filtros de `GET /suppliers` (`null` = sin filtro). Combinables. */
export interface SupplierFilters {
  country: SupplierCountry | null;
  category: SupplierCategory | null;
}

/**
 * Valores del formulario de alta tal como los escribe el usuario (strings de
 * los inputs). El servicio los valida (campos requeridos) y construye el body.
 */
export interface SupplierFormValues {
  name: string;
  country: SupplierCountry | '';
  categories: readonly SupplierCategory[];
  monthly_rate: string;
  currency: SupplierCurrency | '';
  status: SupplierStatus | '';
  contract_renewal_date: string;
  contact_email: string;
  notes: string;
}

/** Campos del formulario que pueden tener un error asociado. */
export type SupplierField =
  | 'name'
  | 'country'
  | 'categories'
  | 'monthly_rate'
  | 'currency'
  | 'status'
  | 'contract_renewal_date'
  | 'contact_email'
  | 'notes';

/**
 * Un error de validación: del cliente (campos requeridos) o de un 422 de la
 * API. `field` es `null` si no corresponde a un campo concreto (p. ej. la
 * coherencia país/moneda, que la API valida sobre el proveedor completo).
 */
export interface FieldError {
  field: SupplierField | null;
  message: string;
}

/** Errores que la UI del directorio sabe presentar. */
export type SupplierUiError =
  | { kind: 'validation'; source: 'client' | 'api'; errors: readonly FieldError[] }
  | { kind: 'not_found' }
  | { kind: 'request_invalid' }
  | { kind: 'server_error' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' }
  | { kind: 'session_expired' };
