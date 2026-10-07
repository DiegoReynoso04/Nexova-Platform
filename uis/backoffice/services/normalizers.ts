// Normalizadores: ÚNICA frontera del backoffice donde se acepta `unknown`
// procedente de la red (CLAUDE.md, "Frontera de confianza").
//
// - Validan la FORMA del contrato de services/api/SPECS.md (tipos y número
//   de entradas), no las reglas de negocio del CSV: eso es del backend.
//   Para proveedores (SPECS Parte B) además comprueban que país, moneda,
//   categorías y estado sean valores del vocabulario conocido: la UI los usa
//   para badges y filtros, y un valor desconocido indicaría un contrato roto.
//   Igual para el gestor de incidencias (SPECS Parte E): estados, orígenes,
//   categorías y sedes deben ser valores del CONTEXT, y el resumen debe traer
//   todas las claves de cada enumerado.
// - Construyen objetos nuevos campo a campo (whitelist). Nunca se hace spread
//   del objeto recibido, así que ninguna propiedad desconocida (p. ej. un
//   `customer_email` que la API enviase por error) llega al estado de la UI.
// - Los errores solo citan la ruta del campo y el tipo esperado/recibido,
//   nunca valores recibidos: no pueden contener PII.
//
// Los tests lo cargan con `node --test` (el alias `@/` lo resuelve
// tests/support/resolve-alias.mjs).

import {
  USER_ROLES,
  type AccessToken,
  type AuthField,
  type AuthFieldError,
  type CurrentUser,
  type Profile,
} from '@/types/auth';
import type {
  AnalysisResult,
  ApiErrorBody,
  DistributionItem,
  ExportInfo,
  RuleBreakdownItem,
  SatisfactionDistributionItem,
  SatisfactionResult,
  Totals,
} from '@/types/incidents';
import {
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  type CountItem,
  type Incident,
  type IncidentApiError,
  type IncidentSummary,
} from '@/types/incident-manager';
import {
  SUPPLIER_CATEGORIES,
  SUPPLIER_COUNTRIES,
  SUPPLIER_CURRENCIES,
  SUPPLIER_STATUSES,
  type FieldError,
  type Supplier,
  type SupplierCategory,
  type SupplierField,
} from '@/types/suppliers';

// Estructura fija del contrato (SPECS.md §3.1): siempre las 7 reglas, las 5
// categorías, los 3 estados y las puntuaciones 1–5, aunque valgan 0.
const RULE_COUNT = 7;
const CATEGORY_COUNT = 5;
const STATUS_COUNT = 3;
const SCORE_COUNT = 5;

/** La respuesta no tiene la forma del contrato. El mensaje no incluye valores recibidos. */
export class UnexpectedResponseError extends Error {
  readonly path: string;

  constructor(path: string, expected: string, received: string) {
    super(`Unexpected API response at ${path}: expected ${expected}, received ${received}`);
    this.name = 'UnexpectedResponseError';
    this.path = path;
  }
}

// ---------------------------------------------------------------------------
// Guards y lectores. Solo describen tipos, nunca valores.
// ---------------------------------------------------------------------------

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function describeType(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

function expectObject(value: unknown, path: string): JsonObject {
  if (!isObject(value)) throw new UnexpectedResponseError(path, 'object', describeType(value));
  return value;
}

function readString(source: JsonObject, key: string, path: string): string {
  const value = source[key];
  if (typeof value !== 'string') throw new UnexpectedResponseError(`${path}.${key}`, 'string', describeType(value));
  return value;
}

function readNullableString(source: JsonObject, key: string, path: string): string | null {
  const value = source[key];
  if (value !== null && typeof value !== 'string') {
    throw new UnexpectedResponseError(`${path}.${key}`, 'string | null', describeType(value));
  }
  return value;
}

/** Conteos y puntuaciones: enteros en el contrato (int en el backend). */
function readInteger(source: JsonObject, key: string, path: string): number {
  const value = source[key];
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    throw new UnexpectedResponseError(`${path}.${key}`, 'integer', describeType(value));
  }
  return value;
}

function readBoolean(source: JsonObject, key: string, path: string): boolean {
  const value = source[key];
  if (typeof value !== 'boolean') throw new UnexpectedResponseError(`${path}.${key}`, 'boolean', describeType(value));
  return value;
}

function readObject(source: JsonObject, key: string, path: string): JsonObject {
  return expectObject(source[key], `${path}.${key}`);
}

function readFixedArray<T>(
  source: JsonObject,
  key: string,
  path: string,
  length: number,
  parseItem: (item: unknown, itemPath: string) => T
): T[] {
  const value = source[key];
  const arrayPath = `${path}.${key}`;
  if (!Array.isArray(value)) throw new UnexpectedResponseError(arrayPath, 'array', describeType(value));
  if (value.length !== length) {
    throw new UnexpectedResponseError(arrayPath, `${length} items`, `${value.length} items`);
  }
  return value.map((item, index) => parseItem(item, `${arrayPath}[${index}]`));
}

// ---------------------------------------------------------------------------
// Piezas del contrato
// ---------------------------------------------------------------------------

function parseTotals(value: JsonObject, path: string): Totals {
  return {
    total_records: readInteger(value, 'total_records', path),
    valid_records: readInteger(value, 'valid_records', path),
    invalid_records: readInteger(value, 'invalid_records', path),
  };
}

function parseRuleItem(item: unknown, path: string): RuleBreakdownItem {
  const value = expectObject(item, path);
  return {
    code: readString(value, 'code', path),
    label: readString(value, 'label', path),
    count: readInteger(value, 'count', path),
  };
}

function parseDistributionItem(item: unknown, path: string): DistributionItem {
  const value = expectObject(item, path);
  return {
    code: readString(value, 'code', path),
    count: readInteger(value, 'count', path),
    percentage: readNullableString(value, 'percentage', path),
  };
}

function parseScoreItem(item: unknown, path: string): SatisfactionDistributionItem {
  const value = expectObject(item, path);
  return {
    score: readInteger(value, 'score', path),
    label: readString(value, 'label', path),
    count: readInteger(value, 'count', path),
  };
}

function parseSatisfaction(value: JsonObject, path: string): SatisfactionResult {
  return {
    closed_tickets: readInteger(value, 'closed_tickets', path),
    scored_tickets: readInteger(value, 'scored_tickets', path),
    average_score: readNullableString(value, 'average_score', path),
    distribution: readFixedArray(value, 'distribution', path, SCORE_COUNT, parseScoreItem),
  };
}

function parseExportInfo(value: JsonObject, path: string): ExportInfo {
  return {
    available: readBoolean(value, 'available', path),
    url: readString(value, 'url', path),
    filename: readString(value, 'filename', path),
    format: readString(value, 'format', path),
  };
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

/**
 * Respuesta 200 de `POST /api/incidents/analyze` → `AnalysisResult`.
 * Lanza `UnexpectedResponseError` si la forma no coincide con el contrato.
 */
export function normalizeAnalysisResponse(input: unknown): AnalysisResult {
  const root = 'response';
  const body = expectObject(input, root);
  return {
    analysis_id: readString(body, 'analysis_id', root),
    analyzed_at: readString(body, 'analyzed_at', root),
    totals: parseTotals(readObject(body, 'totals', root), `${root}.totals`),
    invalid_breakdown: readFixedArray(body, 'invalid_breakdown', root, RULE_COUNT, parseRuleItem),
    categories: readFixedArray(body, 'categories', root, CATEGORY_COUNT, parseDistributionItem),
    statuses: readFixedArray(body, 'statuses', root, STATUS_COUNT, parseDistributionItem),
    satisfaction: parseSatisfaction(readObject(body, 'satisfaction', root), `${root}.satisfaction`),
    export: parseExportInfo(readObject(body, 'export', root), `${root}.export`),
  };
}

/**
 * Cuerpo de error de la API → `{code, detail}` con solo los campos que sean
 * string. Nunca lanza: ante cualquier forma inesperada devuelve `null` en el
 * campo correspondiente. No copia nada más del cuerpo.
 */
export function normalizeApiErrorBody(input: unknown): ApiErrorBody {
  if (!isObject(input)) return { code: null, detail: null };
  const { code, detail } = input;
  return {
    code: typeof code === 'string' ? code : null,
    detail: typeof detail === 'string' ? detail : null,
  };
}

// ---------------------------------------------------------------------------
// Directorio de proveedores (services/api/SPECS.md Parte B)
// ---------------------------------------------------------------------------

function isOneOf<T extends string>(values: readonly T[], value: unknown): value is T {
  return values.some((candidate) => candidate === value);
}

function readOneOf<T extends string>(source: JsonObject, key: string, path: string, values: readonly T[]): T {
  const value = source[key];
  if (!isOneOf(values, value)) throw new UnexpectedResponseError(`${path}.${key}`, values.join(' | '), describeType(value));
  return value;
}

function readFiniteNumber(source: JsonObject, key: string, path: string): number {
  const value = source[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new UnexpectedResponseError(`${path}.${key}`, 'number', describeType(value));
  }
  return value;
}

function readCategories(source: JsonObject, path: string): SupplierCategory[] {
  const value = source.categories;
  const arrayPath = `${path}.categories`;
  if (!Array.isArray(value)) throw new UnexpectedResponseError(arrayPath, 'array', describeType(value));
  return value.map((item, index) => {
    if (!isOneOf(SUPPLIER_CATEGORIES, item)) {
      throw new UnexpectedResponseError(`${arrayPath}[${index}]`, 'supplier category', describeType(item));
    }
    return item;
  });
}

function parseSupplier(input: unknown, path: string): Supplier {
  const value = expectObject(input, path);
  return {
    id: readInteger(value, 'id', path),
    name: readString(value, 'name', path),
    country: readOneOf(value, 'country', path, SUPPLIER_COUNTRIES),
    categories: readCategories(value, path),
    monthly_rate: readFiniteNumber(value, 'monthly_rate', path),
    currency: readOneOf(value, 'currency', path, SUPPLIER_CURRENCIES),
    updated_at: readString(value, 'updated_at', path),
    status: readOneOf(value, 'status', path, SUPPLIER_STATUSES),
    contract_renewal_date: readNullableString(value, 'contract_renewal_date', path),
    contact_email: readNullableString(value, 'contact_email', path),
    notes: readNullableString(value, 'notes', path),
  };
}

/** Respuesta 200/201 con un proveedor (`GET /suppliers/{id}`, `POST`, `PATCH`). */
export function normalizeSupplier(input: unknown): Supplier {
  return parseSupplier(input, 'response');
}

/** Respuesta 200 de `GET /suppliers`: lista de proveedores. */
export function normalizeSupplierList(input: unknown): Supplier[] {
  if (!Array.isArray(input)) throw new UnexpectedResponseError('response', 'array', describeType(input));
  return input.map((item, index) => parseSupplier(item, `response[${index}]`));
}

const SUPPLIER_FIELDS: readonly SupplierField[] = [
  'name',
  'country',
  'categories',
  'monthly_rate',
  'currency',
  'status',
  'contract_renewal_date',
  'contact_email',
  'notes',
];
// Pydantic antepone este prefijo a los errores de validadores propios.
const PYDANTIC_VALUE_ERROR_PREFIX = 'Value error, ';

/**
 * `detail` de un 422 (`[{loc, msg, type}]`, SPECS §4) → errores por campo.
 * `loc` = ["body", "<campo>", ...]; si el campo no es del formulario (p. ej.
 * un error de todo el body), `field` es `null`. Entradas mal formadas se
 * ignoran. Nunca lanza.
 */
export function normalizeValidationErrors(input: unknown): FieldError[] {
  return collectValidationErrors(input, (location) => (isOneOf(SUPPLIER_FIELDS, location) ? location : null));
}

/**
 * Recorre el `detail` de un 422 y traduce cada `loc` a un campo con `toField`.
 * Entradas mal formadas se ignoran. Nunca lanza.
 */
function collectValidationErrors<F extends string>(
  input: unknown,
  toField: (location: unknown) => F | null
): { field: F | null; message: string }[] {
  if (!isObject(input) || !Array.isArray(input.detail)) return [];
  const errors: { field: F | null; message: string }[] = [];
  for (const item of input.detail) {
    if (!isObject(item) || typeof item.msg !== 'string' || !Array.isArray(item.loc)) continue;
    const location = item.loc[0] === 'body' ? item.loc[1] : undefined;
    const message = item.msg.startsWith(PYDANTIC_VALUE_ERROR_PREFIX)
      ? item.msg.slice(PYDANTIC_VALUE_ERROR_PREFIX.length)
      : item.msg;
    errors.push({ field: toField(location), message });
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Autenticación y cuenta (services/api/SPECS.md Parte C, §17–§18 y §23)
// ---------------------------------------------------------------------------

// Campos que puede nombrar un 422 de la API. `password_confirmation` no: es solo del cliente.
const AUTH_FIELDS: readonly AuthField[] = ['email', 'password', 'name', 'phone', 'address', 'current_password', 'new_password'];

/** Respuesta 200 de `POST /auth/login`. Exige un `access_token` no vacío. */
export function normalizeAccessToken(input: unknown): AccessToken {
  const root = 'response';
  const body = expectObject(input, root);
  const accessToken = readString(body, 'access_token', root);
  if (accessToken.trim() === '') throw new UnexpectedResponseError(`${root}.access_token`, 'non-empty string', 'empty string');
  return {
    access_token: accessToken,
    token_type: readString(body, 'token_type', root),
    expires_in: readInteger(body, 'expires_in', root),
  };
}

function parseProfile(input: unknown, path: string): Profile {
  const value = expectObject(input, path);
  return {
    id: readString(value, 'id', path),
    user_id: readString(value, 'user_id', path),
    name: readNullableString(value, 'name', path),
    phone: readNullableString(value, 'phone', path),
    address: readNullableString(value, 'address', path),
  };
}

/** Respuesta 200 de `GET /profiles/me` y `PUT /profiles/me`. */
export function normalizeProfile(input: unknown): Profile {
  return parseProfile(input, 'response');
}

/** Respuesta 200 de `GET /auth/me`. Nunca copia campos fuera del contrato. */
export function normalizeCurrentUser(input: unknown): CurrentUser {
  const root = 'response';
  const body = expectObject(input, root);
  return {
    id: readString(body, 'id', root),
    email: readString(body, 'email', root),
    role: readOneOf(body, 'role', root, USER_ROLES),
    is_active: readBoolean(body, 'is_active', root),
    created_at: readString(body, 'created_at', root),
    profile: body.profile === null ? null : parseProfile(body.profile, `${root}.profile`),
  };
}

/**
 * `detail` de un 422 de `/auth/login`, `/users`, `/profiles/me` o de las rutas
 * de contraseña de AUTH-03 → errores por campo. El formulario OAuth2 del login
 * llama `username` al email.
 */
export function normalizeAuthValidationErrors(input: unknown): AuthFieldError[] {
  return collectValidationErrors(input, (location) => {
    if (location === 'username') return 'email';
    return isOneOf(AUTH_FIELDS, location) ? location : null;
  });
}

// ---------------------------------------------------------------------------
// Gestor centralizado de incidencias (services/api/SPECS.md Parte E)
// ---------------------------------------------------------------------------

function parseIncident(input: unknown, path: string): Incident {
  const value = expectObject(input, path);
  return {
    id: readString(value, 'id', path),
    title: readString(value, 'title', path),
    description: readString(value, 'description', path),
    category: readOneOf(value, 'category', path, INCIDENT_CATEGORIES),
    status: readOneOf(value, 'status', path, INCIDENT_STATUSES),
    origin: readOneOf(value, 'origin', path, INCIDENT_ORIGINS),
    branch: readOneOf(value, 'branch', path, INCIDENT_BRANCHES),
    created_at: readString(value, 'created_at', path),
    updated_at: readString(value, 'updated_at', path),
  };
}

/** Respuesta 200/201 con una incidencia (`GET /api/incidents/{id}`, `POST`, `PATCH …/status`). */
export function normalizeIncident(input: unknown): Incident {
  return parseIncident(input, 'response');
}

/** Respuesta 200 de `GET /api/incidents`: lista de incidencias. */
export function normalizeIncidentList(input: unknown): Incident[] {
  if (!Array.isArray(input)) throw new UnexpectedResponseError('response', 'array', describeType(input));
  return input.map((item, index) => parseIncident(item, `response[${index}]`));
}

/**
 * Diccionario de conteos → lista en el orden del vocabulario. Debe traer
 * exactamente una entrada entera por cada valor (la API envía todas, aunque valgan 0).
 */
function readCounts<T extends string>(source: JsonObject, key: string, path: string, values: readonly T[]): CountItem<T>[] {
  const counts = readObject(source, key, path);
  const countsPath = `${path}.${key}`;
  const received = Object.keys(counts).length;
  if (received !== values.length) {
    throw new UnexpectedResponseError(countsPath, `${values.length} keys`, `${received} keys`);
  }
  return values.map((value) => ({ value, count: readInteger(counts, value, countsPath) }));
}

/** Respuesta 200 de `GET /api/incidents/summary`. */
export function normalizeIncidentSummary(input: unknown): IncidentSummary {
  const value = expectObject(input, 'response');
  return {
    total: readInteger(value, 'total', 'response'),
    by_status: readCounts(value, 'by_status', 'response', INCIDENT_STATUSES),
    by_category: readCounts(value, 'by_category', 'response', INCIDENT_CATEGORIES),
    by_origin: readCounts(value, 'by_origin', 'response', INCIDENT_ORIGINS),
    by_branch: readCounts(value, 'by_branch', 'response', INCIDENT_BRANCHES),
  };
}

/**
 * Cuerpo de un 400/404 del gestor: `code` y, de `detail`, solo `field` y
 * `error` de cada elemento. El `message` del servidor se descarta: la UI
 * muestra sus propios textos. Nunca lanza: un cuerpo inesperado da `{code: null, errors: []}`.
 */
export function normalizeIncidentApiError(input: unknown): IncidentApiError {
  if (!isObject(input)) return { code: null, errors: [] };
  const { code, detail } = input;
  const errors = Array.isArray(detail)
    ? detail.flatMap((item) =>
        isObject(item) && typeof item.field === 'string' && typeof item.error === 'string'
          ? [{ field: item.field, error: item.error }]
          : []
      )
    : [];
  return { code: typeof code === 'string' ? code : null, errors };
}
