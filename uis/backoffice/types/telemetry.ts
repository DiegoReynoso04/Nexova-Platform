// Contrato de los eventos que emite el backoffice (ticket de captura).
// Fuente: docs/telemetry/telemetry-plan.md (fichas de §6) y
// docs/telemetry/event-schemas.json. Prohibido añadir eventos, propiedades o
// valores que no estén ahí: `tests/telemetry-contract.test.mjs` compara estas
// constantes con el JSON y valida contra él los eventos que emite el servicio.
//
// Son los 14 eventos de emisor frontend del plan: los 10 de navegación, flujos,
// errores, rendimiento y sesión, y 4 obligatorios del BRIEFING que el
// frontend emite con lo que devuelve la API (decisión D1 «A ligera»).

/** Versión de los esquemas (plan §5.4): global, la misma en todos los eventos. */
export const TELEMETRY_SCHEMA_VERSION = '1.0.0';

export const PAGE_ROUTE_TEMPLATES = [
  '/',
  '/login',
  '/register',
  '/forgot-password',
  '/reset-password',
  '/account/profile',
  '/account/change-password',
  '/incidents',
  '/suppliers',
  '/incident-manager',
  '/incident-manager/new',
  '/inventory/products',
  '/inventory/orders/inbound',
  '/inventory/orders/outbound',
  '/inventory/orders',
] as const;

export const LOADED_PAGE_ROUTE_TEMPLATES = ['/suppliers', '/incident-manager', '/inventory/products', '/inventory/orders'] as const;

export const API_ROUTE_TEMPLATES = [
  '/auth/login',
  '/auth/me',
  '/auth/forgot-password',
  '/auth/reset-password',
  '/auth/change-password',
  '/users',
  '/users/{user_id}',
  '/profiles/me',
  '/suppliers',
  '/suppliers/{supplier_id}',
  '/suppliers/{supplier_id}/rate',
  '/suppliers/{supplier_id}/status',
  '/api/incidents/analyze',
  '/api/incidents/results/export',
  '/api/incidents',
  '/api/incidents/summary',
  '/api/incidents/{incident_id}',
  '/api/incidents/{incident_id}/status',
  '/inventory/products',
  '/inventory/products/{id}',
  '/inventory/orders/inbound',
  '/inventory/orders/outbound',
  '/inventory/orders',
  '/telemetry/events',
] as const;

export const TELEMETRY_FORMS = [
  'login',
  'register',
  'forgot_password',
  'reset_password',
  'change_password',
  'profile',
  'supplier_create',
  'incident_create',
  'incident_analysis_upload',
  'inbound_order',
  'outbound_order',
] as const;

export const FORM_OUTCOMES = ['success', 'validation_error', 'api_rejected', 'session_expired', 'network_error', 'server_error'] as const;
export const PAGE_ENTRIES = ['initial_load', 'in_app_navigation'] as const;
export const PAGE_LOAD_OUTCOMES = ['data', 'empty', 'error'] as const;
export const ERROR_BOUNDARIES = ['route', 'global'] as const;
export const CLIENT_FAILURE_KINDS = ['network', 'timeout', 'config'] as const;
export const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;
export const LOGOUT_TRIGGERS = ['header_button', 'session_error_screen'] as const;
export const TELEMETRY_OFFICES = ['valencia', 'miami'] as const;
export const TELEMETRY_CURRENCIES = ['EUR', 'USD'] as const;
export const PRODUCT_CATEGORIES = ['training_kit', 'certification', 'onboarding_equipment'] as const;
export const COST_DIRECTIONS = ['increase', 'decrease'] as const;

export type PageRouteTemplate = (typeof PAGE_ROUTE_TEMPLATES)[number];
export type LoadedPageRouteTemplate = (typeof LOADED_PAGE_ROUTE_TEMPLATES)[number];
export type ApiRouteTemplate = (typeof API_ROUTE_TEMPLATES)[number];
export type TelemetryForm = (typeof TELEMETRY_FORMS)[number];
export type FormOutcome = (typeof FORM_OUTCOMES)[number];
export type PageEntry = (typeof PAGE_ENTRIES)[number];
export type PageLoadOutcome = (typeof PAGE_LOAD_OUTCOMES)[number];
export type ErrorBoundaryKind = (typeof ERROR_BOUNDARIES)[number];
export type ClientFailureKind = (typeof CLIENT_FAILURE_KINDS)[number];
export type HttpMethod = (typeof HTTP_METHODS)[number];
export type LogoutTrigger = (typeof LOGOUT_TRIGGERS)[number];
export type TelemetryOffice = (typeof TELEMETRY_OFFICES)[number];
export type TelemetryCurrency = (typeof TELEMETRY_CURRENCIES)[number];
export type ProductCategory = (typeof PRODUCT_CATEGORIES)[number];
export type CostDirection = (typeof COST_DIRECTIONS)[number];
type AssetCategoryValue = 'hardware' | 'peripherals' | 'office_supplies' | 'training_materials';

/** Campos mínimos del BRIEFING en los eventos de inventario (plan §6). */
type InventoryMinimum = {
  office: TelemetryOffice;
  product_id: number;
  /** `null` mientras el activo no esté clasificado (P1 pendiente; D1-a). */
  product_category: ProductCategory | null;
  /** `null` mientras el activo no tenga programa (P1 pendiente). */
  programme_id: string | null;
  quantity: number;
  currency: TelemetryCurrency;
  asset_category: AssetCategoryValue;
};

/** `properties` de cada evento: exactamente su allowlist (plan §6). */
export interface TelemetryEventProperties {
  inbound_order_created: InventoryMinimum & { inbound_order_id: number; unit_cost: number; supplier_key: string };
  outbound_order_created: InventoryMinimum & { outbound_order_id: number; exit_type: 'allocation' | 'consumption'; stock_after: number };
  stock_threshold_triggered: InventoryMinimum & { outbound_order_id: number; stock_before: number; stock_after: number; min_stock: number };
  kit_cost_variance_detected: InventoryMinimum & {
    inbound_order_id: number;
    supplier_key: string;
    unit_cost: number;
    reference_unit_cost: number;
    variance_pct: number;
    direction: CostDirection;
    threshold_pct: number;
    reference_window: number;
  };
  user_logged_out: { trigger: LogoutTrigger };
  page_viewed: { route_template: PageRouteTemplate; previous_route_template: PageRouteTemplate | null; entry: PageEntry };
  page_not_found_viewed: { previous_route_template: PageRouteTemplate | null };
  form_started: { form: TelemetryForm };
  form_submitted: { form: TelemetryForm; outcome: FormOutcome; duration_ms: number; attempt_number: number };
  form_abandoned: { form: TelemetryForm; last_field: string | null; had_validation_error: boolean; had_api_error: boolean; duration_ms: number };
  form_validation_failed: { form: TelemetryForm; fields: string[] };
  frontend_error_captured: { boundary: ErrorBoundaryKind; route_template: PageRouteTemplate | null; suppressed_count: number };
  client_request_failed: {
    kind: ClientFailureKind;
    http_method: HttpMethod;
    api_route_template: ApiRouteTemplate;
    timeout_ms: number | null;
    suppressed_count: number;
  };
  page_load_recorded: { route_template: LoadedPageRouteTemplate; duration_ms: number; outcome: PageLoadOutcome };
}

export type TelemetryEventType = keyof TelemetryEventProperties;

/**
 * Allowlist en tiempo de ejecución: el servicio solo envía estas claves (una
 * clave de más se descarta, como en el emisor de la API, plan §2.2).
 */
export const TELEMETRY_EVENT_KEYS: { readonly [E in TelemetryEventType]: readonly (keyof TelemetryEventProperties[E])[] } = {
  inbound_order_created: ['office', 'product_id', 'product_category', 'programme_id', 'quantity', 'currency', 'inbound_order_id', 'unit_cost', 'supplier_key', 'asset_category'],
  outbound_order_created: ['office', 'product_id', 'product_category', 'programme_id', 'quantity', 'currency', 'outbound_order_id', 'exit_type', 'stock_after', 'asset_category'],
  stock_threshold_triggered: ['office', 'product_id', 'product_category', 'programme_id', 'quantity', 'currency', 'outbound_order_id', 'stock_before', 'stock_after', 'min_stock', 'asset_category'],
  kit_cost_variance_detected: [
    'office',
    'product_id',
    'product_category',
    'programme_id',
    'quantity',
    'currency',
    'inbound_order_id',
    'supplier_key',
    'unit_cost',
    'reference_unit_cost',
    'variance_pct',
    'direction',
    'threshold_pct',
    'reference_window',
    'asset_category',
  ],
  user_logged_out: ['trigger'],
  page_viewed: ['route_template', 'previous_route_template', 'entry'],
  page_not_found_viewed: ['previous_route_template'],
  form_started: ['form'],
  form_submitted: ['form', 'outcome', 'duration_ms', 'attempt_number'],
  form_abandoned: ['form', 'last_field', 'had_validation_error', 'had_api_error', 'duration_ms'],
  form_validation_failed: ['form', 'fields'],
  frontend_error_captured: ['boundary', 'route_template', 'suppressed_count'],
  client_request_failed: ['kind', 'http_method', 'api_route_template', 'timeout_ms', 'suppressed_count'],
  page_load_recorded: ['route_template', 'duration_ms', 'outcome'],
};

/** Envelope común (plan §5): lo rellena el servicio, nunca quien llama a `track()`. */
export type TelemetryEnvelope<E extends TelemetryEventType = TelemetryEventType> = {
  eventId: string;
  timestamp: string;
  sessionId: string | null;
  userId: string | null;
  event_type: E;
  schemaVersion: typeof TELEMETRY_SCHEMA_VERSION;
  requestId: string | null;
  properties: TelemetryEventProperties[E];
};
