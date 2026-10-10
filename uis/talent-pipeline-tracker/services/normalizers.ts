// Normalizadores: única frontera del proyecto donde puede existir `unknown`
// procedente de la red (§3.1). Cada endpoint tiene su propio normalizador —
// la API usa tres envoltorios distintos entre endpoints (§4.8.4), así que
// está prohibido un normalizador genérico. Toda forma inesperada lanza un
// ResponseShapeError descriptivo (nunca se muestra al usuario); nunca se
// devuelven datos parciales en silencio (§3.1).

import { USER_ROLES, type AccessToken, type CurrentUser, type Profile, type UserRole } from '@/types/auth';
import type { Note, RecordListItem } from '@/types/record';
import type { NotesResponse, RecordsPage } from '@/types/api';
import { ResponseShapeError } from '@/lib/response-shape-error';

// ---------------------------------------------------------------------------
// Type guards
// ---------------------------------------------------------------------------

function isRecordObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function describeType(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

// ---------------------------------------------------------------------------
// Note (§4.8.3 — CONTRATO OBSERVADO)
// ---------------------------------------------------------------------------

function parseNote(value: unknown, context: string): Note {
  if (!isRecordObject(value)) {
    throw new ResponseShapeError(`${context}: se esperaba un objeto, se recibió ${describeType(value)}`);
  }

  const { id, record_id, content, created_at } = value;

  if (!isString(id)) {
    throw new ResponseShapeError(`${context}.id: se esperaba string, se recibió ${describeType(id)}`);
  }
  if (!isString(record_id)) {
    throw new ResponseShapeError(`${context}.record_id: se esperaba string, se recibió ${describeType(record_id)}`);
  }
  if (!isString(content)) {
    throw new ResponseShapeError(`${context}.content: se esperaba string, se recibió ${describeType(content)}`);
  }
  if (!isString(created_at)) {
    throw new ResponseShapeError(`${context}.created_at: se esperaba string, se recibió ${describeType(created_at)}`);
  }

  return { id, record_id, content, created_at };
}

function parseNoteArray(value: unknown, context: string): Note[] {
  if (!Array.isArray(value)) {
    throw new ResponseShapeError(`${context}: se esperaba un array, se recibió ${describeType(value)}`);
  }
  return value.map((item, index) => parseNote(item, `${context}[${index}]`));
}

/**
 * POST /records/{id}/notes -> devuelve la Note desnuda, sin envoltorio (§4.8.3).
 *
 * Test manual — éxito:
 *   normalizeNote({
 *     id: 'n-1', record_id: 'r-1',
 *     content: 'Primera llamada, buena impresión',
 *     created_at: '2026-08-25T16:59:42.755489Z',
 *   })
 *   -> { id: 'n-1', record_id: 'r-1', content: '...', created_at: '...' }
 *
 * Test manual — error:
 *   normalizeNote({ id: 'n-1', content: 'sin record_id' })
 *   -> throw Error('POST /records/{id}/notes.record_id: se esperaba string, se recibió undefined')
 */
export function normalizeNote(data: unknown): Note {
  return parseNote(data, 'POST /records/{id}/notes');
}

/**
 * GET /records/{id}/notes -> { data: Note[], meta: { total } } (§4.8.3).
 * `total` va anidado en `meta`, a diferencia de RecordsPage.
 *
 * Test manual — éxito:
 *   normalizeNotesResponse({
 *     data: [{ id: 'n-1', record_id: 'r-1', content: 'ok', created_at: '2026-08-25T16:59:42Z' }],
 *     meta: { total: 1 },
 *   })
 *   -> { data: [Note], meta: { total: 1 } }
 *
 * Test manual — error (envoltorio de otro endpoint, §4.8.4):
 *   normalizeNotesResponse({ total: 1, page: 1, limit: 20, data: [] })
 *   -> throw Error('GET /records/{id}/notes.meta: se esperaba un objeto, se recibió undefined')
 */
export function normalizeNotesResponse(data: unknown): NotesResponse {
  const context = 'GET /records/{id}/notes';

  if (!isRecordObject(data)) {
    throw new ResponseShapeError(`${context}: se esperaba un objeto, se recibió ${describeType(data)}`);
  }

  const { data: items, meta } = data;
  const notes = parseNoteArray(items, `${context}.data`);

  if (!isRecordObject(meta)) {
    throw new ResponseShapeError(`${context}.meta: se esperaba un objeto, se recibió ${describeType(meta)}`);
  }

  const { total } = meta;
  if (!isFiniteNumber(total)) {
    throw new ResponseShapeError(`${context}.meta.total: se esperaba number, se recibió ${describeType(total)}`);
  }

  return { data: notes, meta: { total } };
}

// ---------------------------------------------------------------------------
// Record (§4.2 OpenAPI + §4.8.1 / §4.8.2 observado)
// ---------------------------------------------------------------------------

function parseRecordListItem(value: unknown, context: string): RecordListItem {
  if (!isRecordObject(value)) {
    throw new ResponseShapeError(`${context}: se esperaba un objeto, se recibió ${describeType(value)}`);
  }

  const {
    id,
    full_name,
    email,
    phone,
    position,
    linkedin_url,
    cv_url,
    status,
    stage,
    experience_years,
    notes_count,
    applied_at,
    updated_at,
    notes,
  } = value;

  if (!isString(id)) {
    throw new ResponseShapeError(`${context}.id: se esperaba string, se recibió ${describeType(id)}`);
  }
  if (!isString(full_name)) {
    throw new ResponseShapeError(`${context}.full_name: se esperaba string, se recibió ${describeType(full_name)}`);
  }
  if (!isString(email)) {
    throw new ResponseShapeError(`${context}.email: se esperaba string, se recibió ${describeType(email)}`);
  }
  if (!isString(phone)) {
    throw new ResponseShapeError(`${context}.phone: se esperaba string, se recibió ${describeType(phone)}`);
  }
  if (!isString(position)) {
    throw new ResponseShapeError(`${context}.position: se esperaba string, se recibió ${describeType(position)}`);
  }
  if (!isNullableString(linkedin_url)) {
    throw new ResponseShapeError(`${context}.linkedin_url: se esperaba string o null, se recibió ${describeType(linkedin_url)}`);
  }
  if (!isNullableString(cv_url)) {
    throw new ResponseShapeError(`${context}.cv_url: se esperaba string o null, se recibió ${describeType(cv_url)}`);
  }
  if (!isString(status)) {
    throw new ResponseShapeError(`${context}.status: se esperaba string, se recibió ${describeType(status)}`);
  }
  if (!isString(stage)) {
    throw new ResponseShapeError(`${context}.stage: se esperaba string, se recibió ${describeType(stage)}`);
  }
  if (!isFiniteNumber(experience_years)) {
    throw new ResponseShapeError(`${context}.experience_years: se esperaba number, se recibió ${describeType(experience_years)}`);
  }
  if (!isFiniteNumber(notes_count)) {
    throw new ResponseShapeError(`${context}.notes_count: se esperaba number, se recibió ${describeType(notes_count)}`);
  }
  if (!isString(applied_at)) {
    throw new ResponseShapeError(`${context}.applied_at: se esperaba string, se recibió ${describeType(applied_at)}`);
  }
  if (!isString(updated_at)) {
    throw new ResponseShapeError(`${context}.updated_at: se esperaba string, se recibió ${describeType(updated_at)}`);
  }

  // `notes` es tolerante: ausente -> [] (§4.8.1, §4.8.2)
  const parsedNotes = notes === undefined ? [] : parseNoteArray(notes, `${context}.notes`);

  return {
    id,
    full_name,
    email,
    phone,
    position,
    linkedin_url,
    cv_url,
    status,
    stage,
    experience_years,
    notes_count,
    applied_at,
    updated_at,
    notes: parsedNotes,
  };
}

/**
 * GET /records/{id} -> RecordOut, con `notes` presente o ausente sin
 * garantía contractual (§4.8.2). Se tolera la ausencia devolviendo [].
 *
 * Test manual — éxito, sin notes:
 *   normalizeRecord({
 *     id: 'r-1', full_name: 'Ana Ruiz', email: 'ana@example.com',
 *     phone: '+34600000000', position: 'Asistente de Dirección',
 *     linkedin_url: null, cv_url: null, status: 'received', stage: 'pending',
 *     experience_years: 3, notes_count: 0,
 *     applied_at: '2026-08-20T10:00:00Z', updated_at: '2026-08-20T10:00:00Z',
 *   })
 *   -> { ...mismos campos, notes: [] }
 *
 * Test manual — error:
 *   normalizeRecord({ id: 'r-1' })
 *   -> throw Error('GET /records/{id}.full_name: se esperaba string, se recibió undefined')
 */
export function normalizeRecord(data: unknown): RecordListItem {
  return parseRecordListItem(data, 'GET /records/{id}');
}

/**
 * GET /records -> { total, page, limit, data } (§4.8.1). El array de
 * resultados se llama `data`, no `items`; cada elemento puede traer `notes`
 * incrustadas, no declaradas en el schema RecordOut del OpenAPI.
 *
 * Test manual — éxito:
 *   normalizeRecordsPage({
 *     total: 1, page: 1, limit: 20,
 *     data: [{
 *       id: 'r-1', full_name: 'Ana Ruiz', email: 'ana@example.com',
 *       phone: '+34600000000', position: 'Asistente de Dirección',
 *       linkedin_url: null, cv_url: null, status: 'received', stage: 'pending',
 *       experience_years: 3, notes_count: 1,
 *       applied_at: '2026-08-20T10:00:00Z', updated_at: '2026-08-20T10:00:00Z',
 *       notes: [{ id: 'n-1', record_id: 'r-1', content: 'ok', created_at: '2026-08-20T10:05:00Z' }],
 *     }],
 *   })
 *   -> RecordsPage con data[0].notes de longitud 1.
 *
 * Test manual — error (envoltorio equivocado, p.ej. el de notes, §4.8.4):
 *   normalizeRecordsPage({ data: [], meta: { total: 0 } })
 *   -> throw Error('GET /records.total: se esperaba number, se recibió undefined')
 */
export function normalizeRecordsPage(data: unknown): RecordsPage {
  const context = 'GET /records';

  if (!isRecordObject(data)) {
    throw new ResponseShapeError(`${context}: se esperaba un objeto, se recibió ${describeType(data)}`);
  }

  const { total, page, limit, data: items } = data;

  if (!isFiniteNumber(total)) {
    throw new ResponseShapeError(`${context}.total: se esperaba number, se recibió ${describeType(total)}`);
  }
  if (!isFiniteNumber(page)) {
    throw new ResponseShapeError(`${context}.page: se esperaba number, se recibió ${describeType(page)}`);
  }
  if (!isFiniteNumber(limit)) {
    throw new ResponseShapeError(`${context}.limit: se esperaba number, se recibió ${describeType(limit)}`);
  }
  if (!Array.isArray(items)) {
    throw new ResponseShapeError(`${context}.data: se esperaba un array, se recibió ${describeType(items)}`);
  }

  return {
    total,
    page,
    limit,
    data: items.map((item, index) => parseRecordListItem(item, `${context}.data[${index}]`)),
  };
}

// ---------------------------------------------------------------------------
// services/api de Nexova — autenticación (AUTH-02, SPECS.md §9). Contrato:
// services/api/SPECS.md Parte C §18. Cada respuesta se construye campo a campo:
// nunca se copian propiedades fuera del contrato.
// ---------------------------------------------------------------------------

function isUserRole(value: unknown): value is UserRole {
  return USER_ROLES.some((role) => role === value);
}

function requireString(source: Record<string, unknown>, key: string, context: string): string {
  const value = source[key];
  if (!isString(value)) {
    throw new ResponseShapeError(`${context}.${key}: se esperaba string, se recibió ${describeType(value)}`);
  }
  return value;
}

function requireNullableString(source: Record<string, unknown>, key: string, context: string): string | null {
  const value = source[key];
  if (!isNullableString(value)) {
    throw new ResponseShapeError(`${context}.${key}: se esperaba string o null, se recibió ${describeType(value)}`);
  }
  return value;
}

function parseProfile(value: unknown, context: string): Profile {
  if (!isRecordObject(value)) {
    throw new ResponseShapeError(`${context}: se esperaba un objeto, se recibió ${describeType(value)}`);
  }
  return {
    id: requireString(value, 'id', context),
    user_id: requireString(value, 'user_id', context),
    name: requireNullableString(value, 'name', context),
    phone: requireNullableString(value, 'phone', context),
    address: requireNullableString(value, 'address', context),
  };
}

/** POST /auth/login -> { access_token, token_type, expires_in }. Exige un token no vacío. */
export function normalizeAccessToken(data: unknown): AccessToken {
  const context = 'POST /auth/login';
  if (!isRecordObject(data)) {
    throw new ResponseShapeError(`${context}: se esperaba un objeto, se recibió ${describeType(data)}`);
  }
  const accessToken = requireString(data, 'access_token', context);
  if (accessToken.trim() === '') {
    throw new ResponseShapeError(`${context}.access_token: se esperaba un token no vacío`);
  }
  const { expires_in } = data;
  if (!isFiniteNumber(expires_in)) {
    throw new ResponseShapeError(`${context}.expires_in: se esperaba number, se recibió ${describeType(expires_in)}`);
  }
  return { access_token: accessToken, token_type: requireString(data, 'token_type', context), expires_in };
}

/** PUT /profiles/me -> Profile. */
export function normalizeProfile(data: unknown): Profile {
  return parseProfile(data, 'PUT /profiles/me');
}

/** GET /auth/me -> { id, email, role, is_active, created_at, profile }. */
export function normalizeCurrentUser(data: unknown): CurrentUser {
  const context = 'GET /auth/me';
  if (!isRecordObject(data)) {
    throw new ResponseShapeError(`${context}: se esperaba un objeto, se recibió ${describeType(data)}`);
  }
  const { role, is_active, profile } = data;
  if (!isUserRole(role)) {
    throw new ResponseShapeError(`${context}.role: se esperaba admin | manager | user, se recibió ${describeType(role)}`);
  }
  if (typeof is_active !== 'boolean') {
    throw new ResponseShapeError(`${context}.is_active: se esperaba boolean, se recibió ${describeType(is_active)}`);
  }
  return {
    id: requireString(data, 'id', context),
    email: requireString(data, 'email', context),
    role,
    is_active,
    created_at: requireString(data, 'created_at', context),
    profile: profile === null ? null : parseProfile(profile, `${context}.profile`),
  };
}
