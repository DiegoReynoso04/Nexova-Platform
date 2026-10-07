// Gestor de incidencias: normalizadores (services/normalizers.ts) y servicio
// (services/incident-manager.service.ts) con el cliente real y un transporte falso.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { ApiAbortError, createApiClient } from '../lib/api-client.ts';
import {
  UnexpectedResponseError,
  normalizeIncident,
  normalizeIncidentApiError,
  normalizeIncidentList,
  normalizeIncidentSummary,
} from '../services/normalizers.ts';
import {
  IncidentServiceError,
  REQUIRED_MESSAGES,
  TITLE_TOO_LONG_MESSAGE,
  buildIncidentPayload,
  createIncidentManagerService,
  incidentsQuery,
  messageForApiError,
  validateIncidentForm,
} from '../services/incident-manager.service.ts';
import { BASE_URL, LEAK, hangingFetch, jsonResponse, offlineFetch, recordingFetch, textResponse } from './support/http-fakes.mjs';
import { INCIDENT_ID, fieldErrorBody, formValues, incident, summaryBody } from './support/incident-fakes.mjs';

const NO_FILTERS = { status: null, origin: null, branch: null };

function serviceWith(makeResponse) {
  const transport = recordingFetch(makeResponse);
  const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL, getToken: () => 'test-token' });
  return { service: createIncidentManagerService({ client, timeoutMs: 1_000 }), transport };
}

function expectUiError(expected) {
  return (error) => {
    assert.ok(error instanceof IncidentServiceError, `expected IncidentServiceError, got ${error?.name}`);
    assert.deepEqual(error.uiError, expected);
    return true;
  };
}

describe('normalizadores del gestor', () => {
  test('incidencia válida: whitelist de campos', () => {
    const input = { ...incident(), customer_email: LEAK, extra: 1 };
    assert.deepEqual(normalizeIncident(input), incident());
  });

  test('lista', () => {
    assert.deepEqual(normalizeIncidentList([incident(), incident({ id: 'b' })]).map((item) => item.id), [INCIDENT_ID, 'b']);
    assert.deepEqual(normalizeIncidentList([]), []);
    assert.throws(() => normalizeIncidentList({}), UnexpectedResponseError);
  });

  test('valores fuera del vocabulario o tipos incorrectos se rechazan', () => {
    for (const bad of [
      { status: 'closed' },
      { origin: 'client' },
      { branch: 'headquarters' },
      { category: 'TECHNICAL' },
      { title: 3 },
      { created_at: null },
    ]) {
      assert.throws(() => normalizeIncident(incident(bad)), UnexpectedResponseError, JSON.stringify(bad));
    }
  });

  test('resumen: listas en el orden del CONTEXT con todas las claves', () => {
    const summary = normalizeIncidentSummary(summaryBody({ total: 3, by_status: { open: 2, in_progress: 1, resolved: 0, discarded: 0 } }));
    assert.equal(summary.total, 3);
    assert.deepEqual(summary.by_status, [
      { value: 'open', count: 2 },
      { value: 'in_progress', count: 1 },
      { value: 'resolved', count: 0 },
      { value: 'discarded', count: 0 },
    ]);
    assert.deepEqual(summary.by_branch.map((item) => item.value), ['central', 'valencia_operations', 'miami_office', 'remote']);
    assert.equal(summary.by_category.length, 8);
  });

  test('resumen con claves de menos, de más o conteos no enteros → error de contrato', () => {
    const base = summaryBody();
    for (const bad of [
      { by_status: { open: 0, in_progress: 0, resolved: 0 } },
      { by_origin: { ...base.by_origin, partner: 0 } },
      { by_branch: { ...base.by_branch, central: 1.5 } },
      { total: '0' },
    ]) {
      assert.throws(() => normalizeIncidentSummary({ ...base, ...bad }), UnexpectedResponseError, JSON.stringify(bad));
    }
  });

  test('cuerpo de error: solo code, field y error; nunca el message del servidor', () => {
    const body = fieldErrorBody('validation_error', ['branch', 'missing', `branch is required ${LEAK}`]);
    const normalized = normalizeIncidentApiError(body);
    assert.deepEqual(normalized, { code: 'validation_error', errors: [{ field: 'branch', error: 'missing' }] });
    assert.ok(!JSON.stringify(normalized).includes('leak'));
    assert.deepEqual(normalizeIncidentApiError('nope'), { code: null, errors: [] });
    assert.deepEqual(normalizeIncidentApiError({ code: 1, detail: 'x' }), { code: null, errors: [] });
  });
});

describe('validación en cliente', () => {
  test('formulario completo → sin errores', () => {
    assert.deepEqual(validateIncidentForm(formValues()), []);
  });

  test('cada obligatorio vacío tiene su mensaje junto a su campo', () => {
    const errors = validateIncidentForm({ title: '  ', description: '', category: '', origin: '', branch: '' });
    assert.deepEqual(errors.map((error) => error.field), ['title', 'description', 'category', 'origin', 'branch']);
    assert.equal(errors[0].message, REQUIRED_MESSAGES.title);
  });

  test('título de más de 120 caracteres (tras recortar)', () => {
    assert.deepEqual(validateIncidentForm(formValues({ title: 'x'.repeat(121) })), [
      { field: 'title', message: TITLE_TOO_LONG_MESSAGE },
    ]);
    assert.deepEqual(validateIncidentForm(formValues({ title: ` ${'x'.repeat(120)} ` })), []);
  });

  test('el body lleva status open y textos recortados, sin id ni fechas', () => {
    assert.deepEqual(buildIncidentPayload(formValues({ title: '  T  ', description: ' D ' })), {
      title: 'T',
      description: 'D',
      category: 'technical_failure',
      status: 'open',
      origin: 'branch',
      branch: 'miami_office',
    });
  });

  test('query con solo los filtros activos', () => {
    assert.equal(incidentsQuery(NO_FILTERS), '/api/incidents');
    assert.equal(incidentsQuery({ status: 'open', origin: null, branch: 'remote' }), '/api/incidents?status=open&branch=remote');
  });
});

describe('servicio', () => {
  test('alta inválida en cliente: ninguna petición de red', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(201, incident()));
    await assert.rejects(
      service.createIncident(formValues({ branch: '' })),
      expectUiError({ kind: 'validation', source: 'client', errors: [{ field: 'branch', message: REQUIRED_MESSAGES.branch }] })
    );
    assert.equal(transport.calls.length, 0);
  });

  test('alta correcta: POST con el body construido y la incidencia normalizada', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(201, incident({ origin: 'branch', branch: 'miami_office' })));
    const created = await service.createIncident(formValues());
    assert.equal(created.branch, 'miami_office');
    assert.equal(transport.calls[0].url, `${BASE_URL}/api/incidents`);
    assert.equal(transport.calls[0].init.method, 'POST');
    assert.equal(JSON.parse(transport.calls[0].init.body).status, 'open');
    assert.equal(transport.calls[0].init.headers.Authorization, 'Bearer test-token');
  });

  test('400 de la API: error por campo con texto propio, nunca el del servidor', async () => {
    const body = fieldErrorBody(
      'validation_error',
      ['branch', 'missing', `branch is required ${LEAK}`],
      ['title', 'too_long', `title must be at most 120 characters ${LEAK}`],
      ['priority', 'unknown_field', `this field is not accepted ${LEAK}`]
    );
    const { service } = serviceWith(() => jsonResponse(400, body));
    await assert.rejects(service.createIncident(formValues()), (error) => {
      assert.ok(error instanceof IncidentServiceError);
      assert.deepEqual(error.uiError, {
        kind: 'validation',
        source: 'api',
        errors: [
          { field: 'branch', message: REQUIRED_MESSAGES.branch },
          { field: 'title', message: TITLE_TOO_LONG_MESSAGE },
          { field: null, message: 'La solicitud incluye un dato que no se admite.' },
        ],
      });
      const shown = JSON.stringify(error.uiError) + error.message;
      assert.ok(!shown.includes('leak'));
      assert.ok(!shown.includes('is required'));
      return true;
    });
  });

  test('textos por código de error', () => {
    assert.deepEqual(messageForApiError('category', 'invalid_choice'), {
      field: 'category',
      message: 'Selecciona una de las opciones de la lista.',
    });
    assert.deepEqual(messageForApiError('description', 'blank'), { field: 'description', message: REQUIRED_MESSAGES.description });
    assert.equal(messageForApiError('body', 'invalid_body').field, null);
    assert.equal(messageForApiError('title', 'something_new').message, 'El valor no es válido.');
  });

  test('400 sin el formato esperado → solicitud no válida', async () => {
    for (const response of [() => jsonResponse(400, { detail: 'x' }), () => textResponse(400, LEAK)]) {
      const { service } = serviceWith(response);
      await assert.rejects(service.createIncident(formValues()), expectUiError({ kind: 'request_invalid' }));
    }
  });

  test('listado con filtros', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, [incident()]));
    const incidents = await service.listIncidents({ status: 'open', origin: 'branch', branch: null });
    assert.equal(incidents.length, 1);
    assert.equal(transport.calls[0].url, `${BASE_URL}/api/incidents?status=open&origin=branch`);
  });

  test('resumen', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, summaryBody({ total: 0 })));
    const summary = await service.getIncidentSummary();
    assert.equal(summary.total, 0);
    assert.equal(transport.calls[0].url, `${BASE_URL}/api/incidents/summary`);
  });

  test('cambio de estado: PATCH solo con status', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, incident({ status: 'in_progress' })));
    const updated = await service.changeIncidentStatus(INCIDENT_ID, 'in_progress');
    assert.equal(updated.status, 'in_progress');
    assert.equal(transport.calls[0].url, `${BASE_URL}/api/incidents/${INCIDENT_ID}/status`);
    assert.equal(transport.calls[0].init.method, 'PATCH');
    assert.deepEqual(JSON.parse(transport.calls[0].init.body), { status: 'in_progress' });
  });

  test('transición rechazada, incidencia inexistente y error del servidor', async () => {
    const cases = [
      [() => jsonResponse(400, fieldErrorBody('invalid_status_transition', ['status', 'invalid_transition', LEAK])), { kind: 'invalid_transition' }],
      [() => jsonResponse(404, { code: 'incident_not_found', detail: 'incident not found' }), { kind: 'not_found' }],
      [() => jsonResponse(404, { code: 'not_found', detail: 'Not Found' }), { kind: 'request_invalid' }],
      [() => jsonResponse(500, { code: 'internal_error', detail: 'internal server error' }), { kind: 'server_error' }],
      [() => jsonResponse(200, { unexpected: true }), { kind: 'unexpected_response' }],
    ];
    for (const [response, expected] of cases) {
      const { service } = serviceWith(response);
      await assert.rejects(service.changeIncidentStatus(INCIDENT_ID, 'resolved'), expectUiError(expected), expected.kind);
    }
  });

  test('401 → sesión caducada; red caída, timeout y configuración', async () => {
    const unauthorized = serviceWith(() => jsonResponse(401, { code: 'not_authenticated' }));
    await assert.rejects(unauthorized.service.listIncidents(NO_FILTERS), expectUiError({ kind: 'session_expired' }));

    const offline = createIncidentManagerService({
      client: createApiClient({ fetch: offlineFetch(), getBaseUrl: () => BASE_URL }),
      timeoutMs: 1_000,
    });
    await assert.rejects(offline.getIncidentSummary(), expectUiError({ kind: 'network' }));

    const slow = createIncidentManagerService({
      client: createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL }),
      timeoutMs: 10,
    });
    await assert.rejects(slow.listIncidents(NO_FILTERS), expectUiError({ kind: 'timeout' }));

    const unconfigured = createIncidentManagerService({
      client: createApiClient({ fetch: hangingFetch(), getBaseUrl: () => undefined }),
    });
    await assert.rejects(unconfigured.listIncidents(NO_FILTERS), expectUiError({ kind: 'config' }));
  });

  test('la cancelación se propaga como ApiAbortError', async () => {
    const service = createIncidentManagerService({
      client: createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL }),
      timeoutMs: 1_000,
    });
    const controller = new AbortController();
    const pending = service.listIncidents(NO_FILTERS, { signal: controller.signal });
    controller.abort();
    await assert.rejects(pending, ApiAbortError);
  });
});
