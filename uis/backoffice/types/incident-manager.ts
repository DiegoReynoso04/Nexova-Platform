// Contrato que recibe y envía el frontend del gestor centralizado de incidencias.
// Fuente: services/api/SPECS.md Parte E (§28–§33). Vocabulario del dominio:
// docs/centralized-incident-manager.md ("Oficinas de Nexova", "Categorías de
// incidencias", "Estados y ciclo de vida", "Orígenes"). Prohibido añadir campos
// o valores que no estén ahí.
//
// Excepción documentada en CLAUDE.md (como types/suppliers.ts): estas listas,
// las etiquetas de sede y la tabla de transiciones viven en el frontend porque
// el formulario, los filtros y el selector de estado necesitan ofrecerlas y la
// API no las publica. Los valores se muestran tal cual; solo `branch` tiene
// etiquetas (las del CONTEXT). El backend sigue siendo la autoridad: valida y
// responde 400. `tests/incident-manager-contract.test.mjs` comprueba que todo
// coincide con el CONTEXT.

export const INCIDENT_STATUSES = ['open', 'in_progress', 'resolved', 'discarded'] as const;
export const INCIDENT_ORIGINS = ['customer', 'branch', 'internal'] as const;
export const INCIDENT_CATEGORIES = [
  'technical_failure',
  'process_error',
  'client_complaint',
  'candidate_issue',
  'staff_issue',
  'sla_breach',
  'data_quality',
  'other',
] as const;
export const INCIDENT_BRANCHES = ['central', 'valencia_operations', 'miami_office', 'remote'] as const;

export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];
export type IncidentOrigin = (typeof INCIDENT_ORIGINS)[number];
export type IncidentCategory = (typeof INCIDENT_CATEGORIES)[number];
export type IncidentBranch = (typeof INCIDENT_BRANCHES)[number];

/** "Nombre para mostrar" de cada sede, literal del CONTEXT. */
export const BRANCH_LABELS: Readonly<Record<IncidentBranch, string>> = {
  central: 'Central — Sede Valencia',
  valencia_operations: 'Valencia — Operaciones',
  miami_office: 'Miami Office',
  remote: 'Remoto (empleado sin sede fija)',
};

/**
 * Ciclo de vida del CONTEXT: estados a los que puede pasar cada uno.
 * `resolved` y `discarded` son finales (sin transiciones).
 */
export const INCIDENT_TRANSITIONS: Readonly<Record<IncidentStatus, readonly IncidentStatus[]>> = {
  open: ['in_progress', 'discarded'],
  in_progress: ['resolved', 'discarded'],
  resolved: [],
  discarded: [],
};

/** Toda incidencia nueva nace abierta; el formulario lo muestra en solo lectura. */
export const INITIAL_INCIDENT_STATUS: IncidentStatus = 'open';

/** Máximo del título (el mismo recorte que aplica el seed del CSV histórico). */
export const TITLE_MAX_LENGTH = 120;

/** Incidencia tal como la devuelve la API (`GET`, `POST`, `PATCH`). */
export interface Incident {
  /** UUID v4 generado por el sistema. */
  id: string;
  title: string;
  description: string;
  category: IncidentCategory;
  status: IncidentStatus;
  origin: IncidentOrigin;
  branch: IncidentBranch;
  /** ISO 8601 UTC, generado por el sistema. */
  created_at: string;
  /** ISO 8601 UTC; cambia con cada cambio de estado. */
  updated_at: string;
}

/** Un total del resumen: valor del vocabulario y número de incidencias. */
export interface CountItem<T extends string> {
  value: T;
  count: number;
}

/**
 * Respuesta de `GET /api/incidents/summary`. La API envía cada total como un
 * diccionario con todas las claves (aunque valgan 0); el normalizador lo
 * convierte en una lista en el orden del CONTEXT.
 */
export interface IncidentSummary {
  total: number;
  by_status: readonly CountItem<IncidentStatus>[];
  by_category: readonly CountItem<IncidentCategory>[];
  by_origin: readonly CountItem<IncidentOrigin>[];
  by_branch: readonly CountItem<IncidentBranch>[];
}

/** Filtros del listado (`null` = sin filtro). Se envían a la API y se combinan con AND. */
export interface IncidentFilters {
  status: IncidentStatus | null;
  origin: IncidentOrigin | null;
  branch: IncidentBranch | null;
}

/** Valores del formulario de registro tal como los escribe el usuario. */
export interface IncidentFormValues {
  title: string;
  description: string;
  category: IncidentCategory | '';
  origin: IncidentOrigin | '';
  branch: IncidentBranch | '';
}

/** Campos que pueden tener un error asociado. */
export type IncidentField = 'title' | 'description' | 'category' | 'status' | 'origin' | 'branch';

/**
 * Un error de validación, del cliente o de un 400 de la API. `message` es
 * siempre un texto propio del frontend (nunca el `message` del servidor);
 * `field` es `null` si no corresponde a un campo del formulario.
 */
export interface IncidentFieldError {
  field: IncidentField | null;
  message: string;
}

/** Errores que la UI del gestor sabe presentar. */
export type IncidentUiError =
  | { kind: 'validation'; source: 'client' | 'api'; errors: readonly IncidentFieldError[] }
  | { kind: 'invalid_transition' }
  | { kind: 'not_found' }
  | { kind: 'request_invalid' }
  | { kind: 'server_error' }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'unexpected_response' }
  | { kind: 'config' }
  | { kind: 'session_expired' };

/** Error de una respuesta 400/404 de la API tal como lo lee el frontend (sin `message`). */
export interface IncidentApiError {
  code: string | null;
  errors: readonly { field: string; error: string }[];
}
