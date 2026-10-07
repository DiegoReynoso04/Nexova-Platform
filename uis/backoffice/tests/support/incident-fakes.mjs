// Datos de prueba del gestor de incidencias (services/api/SPECS.md Parte E).
// Textos sintéticos; ningún dato real de Nexova.

export const INCIDENT_ID = '3f2b6c1e-8a4d-4c2b-9f1e-1234567890ab';

export function incident(overrides = {}) {
  return {
    id: INCIDENT_ID,
    title: 'Synthetic incident',
    description: 'Synthetic description',
    category: 'technical_failure',
    status: 'open',
    origin: 'internal',
    branch: 'central',
    created_at: '2026-10-07T09:00:00Z',
    updated_at: '2026-10-07T09:00:00Z',
    ...overrides,
  };
}

export function formValues(overrides = {}) {
  return {
    title: 'Synthetic incident',
    description: 'Synthetic description',
    category: 'technical_failure',
    origin: 'branch',
    branch: 'miami_office',
    ...overrides,
  };
}

/** Cuerpo de `GET /api/incidents/summary` con todas las claves (las no indicadas a 0). */
export function summaryBody(overrides = {}) {
  const zeros = (keys) => Object.fromEntries(keys.map((key) => [key, 0]));
  return {
    total: 0,
    by_status: zeros(['open', 'in_progress', 'resolved', 'discarded']),
    by_category: zeros([
      'technical_failure',
      'process_error',
      'client_complaint',
      'candidate_issue',
      'staff_issue',
      'sla_breach',
      'data_quality',
      'other',
    ]),
    by_origin: zeros(['customer', 'branch', 'internal']),
    by_branch: zeros(['central', 'valencia_operations', 'miami_office', 'remote']),
    ...overrides,
  };
}

/** Cuerpo 400 de la API: `{code, detail: [{field, error, message}]}`. */
export function fieldErrorBody(code, ...errors) {
  return { code, detail: errors.map(([field, error, message]) => ({ field, error, message })) };
}
