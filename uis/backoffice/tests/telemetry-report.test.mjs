// Reporte técnico (/telemetry): normalizador, servicio con el cliente real y un
// transporte falso, y reducer y sesión del hook, sin montar React.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_TELEMETRY_REPORT_STATE,
  createTelemetryReportSession,
  reportView,
  telemetryReportReducer,
} from '../hooks/use-telemetry-report.ts';
import { ApiAbortError, createApiClient } from '../lib/api-client.ts';
import { UnexpectedResponseError, normalizeTelemetryReport } from '../services/normalizers.ts';
import { TelemetryReportServiceError, createTelemetryReportService } from '../services/telemetry-report.service.ts';
import { BASE_URL, LEAK, hangingFetch, jsonResponse, offlineFetch, recordingFetch, textResponse } from './support/http-fakes.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));

function reportBody() {
  return {
    period: { from: '2026-10-29T12:00:00.000Z', to: '2026-11-05T12:00:00.000Z' },
    metrics: {
      events_per_day: [{ day: '2026-11-05', service: 'backoffice', events: 55 }],
      error_rate_by_type: [
        { day: '2026-11-04', error_type: 'direct_stock_edit_rejected', error_class: 'rejected', errors: 1, total_events: 1, error_rate: 1.0 },
      ],
      page_load_latency_by_route: [
        { day: '2026-11-05', route_template: '/inventory/products', outcome: 'data', loads: 4, avg_ms: 478.75, max_ms: 674 },
      ],
      dominant_event_types: [{ event_type: 'page_viewed', service: 'backoffice', events: 21, share: 0.375 }],
      auth_failure_rate: [{ day: '2026-11-05', failed: 3, succeeded: 3, attempts: 6, failure_rate: 0.5 }],
    },
  };
}

function serviceWith(makeResponse) {
  const transport = recordingFetch(makeResponse);
  const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL, getToken: () => 'test-token' });
  return { service: createTelemetryReportService({ client, timeoutMs: 1_000 }), transport };
}

function clientWith(fetchImpl) {
  return createApiClient({ fetch: fetchImpl, getBaseUrl: () => BASE_URL, getToken: () => 'test-token' });
}

function expectUiError(expected) {
  return (error) => {
    assert.ok(error instanceof TelemetryReportServiceError, `expected TelemetryReportServiceError, got ${error?.name}`);
    assert.deepEqual(error.uiError, expected);
    return true;
  };
}

describe('normalizeTelemetryReport', () => {
  test('lee el contrato', () => {
    assert.deepEqual(normalizeTelemetryReport(reportBody()), reportBody());
  });

  test('las métricas vacías son listas vacías', () => {
    const body = reportBody();
    body.metrics.error_rate_by_type = [];
    assert.deepEqual(normalizeTelemetryReport(body).metrics.error_rate_by_type, []);
  });

  test('no deja pasar campos que el contrato no tiene', () => {
    const body = reportBody();
    body.metrics.dominant_event_types[0].user_id = LEAK;
    body.period.user_id = LEAK;
    assert.doesNotMatch(JSON.stringify(normalizeTelemetryReport(body)), /leak|user_id/);
  });

  test('una tasa nula rompe el contrato y el error no repite valores', () => {
    const body = reportBody();
    body.metrics.auth_failure_rate[0].failure_rate = null;
    assert.throws(() => normalizeTelemetryReport(body), UnexpectedResponseError);
  });

  test('una clase de error desconocida rompe el contrato', () => {
    const body = reportBody();
    body.metrics.error_rate_by_type[0].error_class = LEAK;
    assert.throws(
      () => normalizeTelemetryReport(body),
      (error) => error instanceof UnexpectedResponseError && !error.message.includes(LEAK)
    );
  });

  test('una métrica que falta rompe el contrato', () => {
    const body = reportBody();
    delete body.metrics.events_per_day;
    assert.throws(() => normalizeTelemetryReport(body), UnexpectedResponseError);
  });
});

describe('getTelemetryReport', () => {
  test('pide la ventana por defecto, con el token', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, reportBody()));
    const report = await service.getTelemetryReport();
    assert.equal(report.metrics.auth_failure_rate[0].failure_rate, 0.5);
    assert.equal(transport.calls.length, 1);
    assert.equal(transport.calls[0].url, `${BASE_URL}/telemetry/report`);
  });

  test('un 5xx es server_error', async () => {
    const { service } = serviceWith(() => textResponse(500, 'Internal Server Error'));
    await assert.rejects(service.getTelemetryReport(), expectUiError({ kind: 'server_error' }));
  });

  test('un 422 es request_invalid', async () => {
    const { service } = serviceWith(() => jsonResponse(422, { detail: [], code: 'validation_error' }));
    await assert.rejects(service.getTelemetryReport(), expectUiError({ kind: 'request_invalid' }));
  });

  test('un 401 es session_expired', async () => {
    const { service } = serviceWith(() => jsonResponse(401, { detail: 'x' }));
    await assert.rejects(service.getTelemetryReport(), expectUiError({ kind: 'session_expired' }));
  });

  test('una respuesta fuera de contrato es unexpected_response', async () => {
    const { service } = serviceWith(() => jsonResponse(200, { period: null }));
    await assert.rejects(service.getTelemetryReport(), expectUiError({ kind: 'unexpected_response' }));
  });

  test('sin red es network', async () => {
    const service = createTelemetryReportService({ client: clientWith(offlineFetch()), timeoutMs: 1_000 });
    await assert.rejects(service.getTelemetryReport(), expectUiError({ kind: 'network' }));
  });

  test('sin respuesta a tiempo es timeout', async () => {
    const service = createTelemetryReportService({ client: clientWith(hangingFetch()), timeoutMs: 5 });
    await assert.rejects(service.getTelemetryReport(), expectUiError({ kind: 'timeout' }));
  });

  test('una cancelación se propaga como ApiAbortError', async () => {
    const controller = new AbortController();
    const service = createTelemetryReportService({ client: clientWith(hangingFetch()), timeoutMs: 1_000 });
    const pending = service.getTelemetryReport({ signal: controller.signal });
    controller.abort();
    await assert.rejects(pending, ApiAbortError);
  });
});

describe('telemetryReportReducer y reportView', () => {
  const report = normalizeTelemetryReport(reportBody());

  test('carga, datos y error', () => {
    const loading = telemetryReportReducer(INITIAL_TELEMETRY_REPORT_STATE, { type: 'report_started' });
    assert.equal(reportView(loading), 'loading');
    const loaded = telemetryReportReducer(loading, { type: 'report_succeeded', report });
    assert.equal(reportView(loaded), 'data');
    const failed = telemetryReportReducer(loading, { type: 'report_failed', error: { kind: 'network' } });
    assert.equal(reportView(failed), 'error');
  });

  test('un fallo al recargar no borra el último reporte', () => {
    const loaded = telemetryReportReducer(INITIAL_TELEMETRY_REPORT_STATE, { type: 'report_succeeded', report });
    const failed = telemetryReportReducer(loaded, { type: 'report_failed', error: { kind: 'network' } });
    assert.equal(failed.report, report);
    assert.equal(reportView(failed), 'data');
    assert.equal(failed.load.status, 'error');
  });
});

describe('createTelemetryReportSession', () => {
  function controllable() {
    const calls = [];
    const fn = ({ signal }) =>
      new Promise((resolve, reject) => {
        calls.push({ resolve, reject });
        signal.addEventListener('abort', () => reject(new ApiAbortError()));
      });
    return { fn, calls };
  }

  test('carga al activarse, una sola vez', async () => {
    const operation = controllable();
    const actions = [];
    const session = createTelemetryReportSession((action) => actions.push(action), { getTelemetryReport: operation.fn });
    session.activate();
    session.activate();
    assert.equal(operation.calls.length, 1);
    operation.calls[0].resolve('report');
    await tick();
    assert.deepEqual(actions, [{ type: 'report_started' }, { type: 'report_succeeded', report: 'report' }]);
  });

  test('tras dispose no despacha nada', async () => {
    const operation = controllable();
    const actions = [];
    const session = createTelemetryReportSession((action) => actions.push(action), { getTelemetryReport: operation.fn });
    session.activate();
    session.dispose();
    await tick();
    assert.deepEqual(actions, [{ type: 'report_started' }]);
  });

  test('una recarga descarta la respuesta anterior', async () => {
    const operation = controllable();
    const actions = [];
    const session = createTelemetryReportSession((action) => actions.push(action), { getTelemetryReport: operation.fn });
    session.activate();
    void session.reload();
    operation.calls[1].resolve('nuevo');
    await tick();
    assert.deepEqual(actions.at(-1), { type: 'report_succeeded', report: 'nuevo' });
    assert.equal(actions.filter((action) => action.type === 'report_failed').length, 0);
  });

  test('un fallo llega con su error', async () => {
    const operation = controllable();
    const actions = [];
    const session = createTelemetryReportSession((action) => actions.push(action), { getTelemetryReport: operation.fn });
    session.activate();
    operation.calls[0].reject(new TelemetryReportServiceError({ kind: 'server_error' }));
    await tick();
    assert.deepEqual(actions.at(-1), { type: 'report_failed', error: { kind: 'server_error' } });
  });
});
