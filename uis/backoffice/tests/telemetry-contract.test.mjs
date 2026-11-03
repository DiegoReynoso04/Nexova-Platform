// El contrato de telemetría del frontend (types/telemetry.ts) frente a
// docs/telemetry/event-schemas.json: mismos eventos de emisor frontend, mismas
// claves, mismos enums y misma versión. Y la identidad del envelope desde el JWT
// (lib/session-identity.ts). Ticket de captura; plan §5.4 y D5.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { identityFromToken } from '../lib/session-identity.ts';
import {
  API_ROUTE_TEMPLATES,
  CLIENT_FAILURE_KINDS,
  ERROR_BOUNDARIES,
  FORM_OUTCOMES,
  HTTP_METHODS,
  LOADED_PAGE_ROUTE_TEMPLATES,
  LOGOUT_TRIGGERS,
  PAGE_ENTRIES,
  PAGE_LOAD_OUTCOMES,
  PAGE_ROUTE_TEMPLATES,
  PRODUCT_CATEGORIES,
  COST_DIRECTIONS,
  TELEMETRY_CURRENCIES,
  TELEMETRY_EVENT_KEYS,
  TELEMETRY_FORMS,
  TELEMETRY_OFFICES,
  TELEMETRY_SCHEMA_VERSION,
} from '../types/telemetry.ts';
import { DEFINITIONS, eventMeta } from './support/event-contract.mjs';

const props = (name) => DEFINITIONS[name].properties.properties;
const enumOf = (name, key) => props(name).properties[key].enum.filter((value) => value !== null);

describe('types/telemetry.ts sigue a event-schemas.json', () => {
  test('el frontend emite exactamente los eventos de emisor frontend del contrato', () => {
    const frontend = Object.keys(DEFINITIONS).filter((name) => name !== 'envelope' && eventMeta(name).emisor === 'frontend');
    assert.deepEqual(Object.keys(TELEMETRY_EVENT_KEYS).sort(), frontend.sort());
  });

  test('la allowlist de cada evento es la del contrato, en el mismo orden', () => {
    for (const [name, keys] of Object.entries(TELEMETRY_EVENT_KEYS)) {
      assert.deepEqual([...keys], Object.keys(props(name).properties), name);
      assert.deepEqual([...keys].sort(), [...props(name).required].sort(), `${name}: todas obligatorias`);
    }
  });

  test('la versión es la de todos los esquemas', () => {
    for (const name of Object.keys(TELEMETRY_EVENT_KEYS)) {
      assert.deepEqual(DEFINITIONS[name].properties.schemaVersion, { const: TELEMETRY_SCHEMA_VERSION }, name);
    }
  });

  test('los enums son los del contrato', () => {
    const pairs = [
      [PAGE_ROUTE_TEMPLATES, 'page_viewed', 'route_template'],
      [PAGE_ROUTE_TEMPLATES, 'page_viewed', 'previous_route_template'],
      [PAGE_ENTRIES, 'page_viewed', 'entry'],
      [PAGE_ROUTE_TEMPLATES, 'frontend_error_captured', 'route_template'],
      [ERROR_BOUNDARIES, 'frontend_error_captured', 'boundary'],
      [LOADED_PAGE_ROUTE_TEMPLATES, 'page_load_recorded', 'route_template'],
      [PAGE_LOAD_OUTCOMES, 'page_load_recorded', 'outcome'],
      [API_ROUTE_TEMPLATES, 'client_request_failed', 'api_route_template'],
      [CLIENT_FAILURE_KINDS, 'client_request_failed', 'kind'],
      [HTTP_METHODS, 'client_request_failed', 'http_method'],
      [TELEMETRY_FORMS, 'form_started', 'form'],
      [TELEMETRY_FORMS, 'form_submitted', 'form'],
      [FORM_OUTCOMES, 'form_submitted', 'outcome'],
      [LOGOUT_TRIGGERS, 'user_logged_out', 'trigger'],
      [TELEMETRY_OFFICES, 'outbound_order_created', 'office'],
      [TELEMETRY_CURRENCIES, 'inbound_order_created', 'currency'],
      [PRODUCT_CATEGORIES, 'stock_threshold_triggered', 'product_category'],
      [COST_DIRECTIONS, 'kit_cost_variance_detected', 'direction'],
    ];
    for (const [values, name, key] of pairs) assert.deepEqual([...values], enumOf(name, key), `${name}.${key}`);
  });
});

function token(payload) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.firma`;
}

describe('identidad del envelope desde el JWT', () => {
  const sub = '3f2b8c1e-5a7d-4e9b-8c2a-1d4e6f8a9b0c';
  const sid = 'a1c3e5f7-2b4d-4a6c-9e8f-0b1d3f5a7c9e';

  test('sub y sid del payload', () => {
    assert.deepEqual(identityFromToken(token({ sub, sid, iat: 1, exp: 2 })), { userId: sub, sessionId: sid });
  });

  test('un token anterior al claim sid da sessionId null', () => {
    assert.deepEqual(identityFromToken(token({ sub, iat: 1, exp: 2 })), { userId: sub, sessionId: null });
  });

  test('sin token, ilegible o con claims que no son UUID v4 → anónimo, sin lanzar', () => {
    const anonymous = { userId: null, sessionId: null };
    for (const value of [null, '', 'a.b', 'a..c', 'sin-puntos', token(['lista']), token({ sub: 'leak@example.invalid', sid: 7 })]) {
      assert.deepEqual(identityFromToken(value), anonymous, String(value));
    }
    assert.deepEqual(identityFromToken(token({ sub: sub.toUpperCase(), sid })), { userId: null, sessionId: sid });
  });
});
