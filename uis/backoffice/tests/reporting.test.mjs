// Reporte semanal (/reporting): normalizadores, servicio con el cliente real y un transporte falso,
// y reducers y sesiones de los dos hooks, sin montar React. La presentación pura (formato, semanas,
// subtotales, frescura) la prueba Jest en __tests__/utils/reporting-format.test.ts.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_FRESHNESS_STATE,
  createFreshnessSession,
  freshnessReducer,
} from '../hooks/use-pipeline-freshness.ts';
import {
  INITIAL_WEEKLY_STATE,
  createWeeklySession,
  nextWeek,
  previousWeek,
  shownWeek,
  weeklyReducer,
  weeklyView,
} from '../hooks/use-weekly-performance.ts';
import { ApiAbortError, createApiClient } from '../lib/api-client.ts';
import { UnexpectedResponseError, normalizePipelineRun, normalizeWeeklyPerformance } from '../services/normalizers.ts';
import { ReportingServiceError, createReportingService } from '../services/reporting.service.ts';
import { BASE_URL, LEAK, hangingFetch, jsonResponse, offlineFetch, recordingFetch, textResponse } from './support/http-fakes.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));

function weeklyBody() {
  return {
    week_start: '2026-11-02',
    entries: [
      {
        office: 'valencia',
        programme_id: '_unassigned',
        total_material_cost: 16.5,
        kits_delivered_count: 2,
        shortage_events_count: 0,
        cost_variance_events_count: 1,
        currency: 'EUR',
      },
      {
        office: 'miami',
        programme_id: '_unassigned',
        total_material_cost: 0,
        kits_delivered_count: 1,
        shortage_events_count: 1,
        cost_variance_events_count: 0,
        currency: 'USD',
      },
    ],
  };
}

function runBody(overrides = {}) {
  return {
    run_id: '51e4476a-0ac6-4710-86d7-daa6e495839c',
    pipeline_name: 'weekly_office_program_performance',
    trigger: 'manual',
    prefect_flow_run_id: null,
    status: 'completed',
    phase: 'done',
    week_from: '2026-10-26',
    week_to: '2026-11-02',
    started_at: '2026-11-09T05:00:00Z',
    finished_at: '2026-11-09T05:00:07Z',
    source_rows_read: 9,
    rows_rejected: 0,
    duplicates_collapsed: 2,
    rows_upserted: 4,
    rows_deleted: 0,
    quality: {},
    error_class: null,
    schema_version: '1.0.0',
    ...overrides,
  };
}

function serviceWith(makeResponse) {
  const transport = recordingFetch(makeResponse);
  const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL, getToken: () => 'test-token' });
  return { service: createReportingService({ client, timeoutMs: 1_000 }), transport };
}

function clientWith(fetchImpl) {
  return createApiClient({ fetch: fetchImpl, getBaseUrl: () => BASE_URL, getToken: () => 'test-token' });
}

function expectUiError(expected) {
  return (error) => {
    assert.ok(error instanceof ReportingServiceError, `expected ReportingServiceError, got ${error?.name}`);
    assert.deepEqual(error.uiError, expected);
    return true;
  };
}

describe('normalizeWeeklyPerformance', () => {
  test('lee el contrato', () => {
    assert.deepEqual(normalizeWeeklyPerformance(weeklyBody()), weeklyBody());
  });

  test('una semana sin actividad es una lista vacía', () => {
    assert.deepEqual(normalizeWeeklyPerformance({ week_start: '2026-11-02', entries: [] }).entries, []);
  });

  test('no deja pasar campos que el contrato no tiene', () => {
    const body = weeklyBody();
    body.entries[0].customer_email = LEAK;
    body.user_id = LEAK;
    assert.doesNotMatch(JSON.stringify(normalizeWeeklyPerformance(body)), /leak|customer_email|user_id/);
  });

  test('una moneda que no es la de la oficina rompe el contrato: nunca se muestra mezclada', () => {
    const body = weeklyBody();
    body.entries[0].currency = 'USD';
    assert.throws(() => normalizeWeeklyPerformance(body), UnexpectedResponseError);
  });

  test('una oficina desconocida, un conteo no entero o una fecha mal formada rompen el contrato', () => {
    const office = weeklyBody();
    office.entries[0].office = 'madrid';
    assert.throws(() => normalizeWeeklyPerformance(office), UnexpectedResponseError);
    const count = weeklyBody();
    count.entries[0].kits_delivered_count = 1.5;
    assert.throws(() => normalizeWeeklyPerformance(count), UnexpectedResponseError);
    const cost = weeklyBody();
    cost.entries[0].total_material_cost = '16.5';
    assert.throws(() => normalizeWeeklyPerformance(cost), UnexpectedResponseError);
    const week = weeklyBody();
    week.week_start = 'noviembre';
    assert.throws(() => normalizeWeeklyPerformance(week), UnexpectedResponseError);
  });

  test('el error no repite valores recibidos', () => {
    const body = weeklyBody();
    body.entries[0].office = LEAK;
    assert.throws(
      () => normalizeWeeklyPerformance(body),
      (error) => error instanceof UnexpectedResponseError && !error.message.includes(LEAK)
    );
  });
});

describe('normalizePipelineRun', () => {
  test('solo lee estado, instantes y semanas: ni fase, ni contadores, ni error_class', () => {
    const run = normalizePipelineRun(runBody({ error_class: 'OperationalError' }));
    assert.deepEqual(run, {
      status: 'completed',
      started_at: '2026-11-09T05:00:00Z',
      finished_at: '2026-11-09T05:00:07Z',
      week_from: '2026-10-26',
      week_to: '2026-11-02',
    });
    assert.doesNotMatch(JSON.stringify(run), /OperationalError|phase|rows_|error_class/);
  });

  test('una corrida en marcha no tiene fin', () => {
    assert.equal(normalizePipelineRun(runBody({ status: 'running', finished_at: null })).finished_at, null);
  });

  test('un estado desconocido rompe el contrato', () => {
    assert.throws(() => normalizePipelineRun(runBody({ status: 'paused' })), UnexpectedResponseError);
  });
});

describe('getWeeklyPerformance', () => {
  test('sin semana, pide la última calculada, con el token', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, weeklyBody()));
    const result = await service.getWeeklyPerformance();
    assert.equal(result.status, 'computed');
    assert.equal(result.report.week_start, '2026-11-02');
    assert.equal(transport.calls.length, 1);
    assert.equal(transport.calls[0].url, `${BASE_URL}/reporting/weekly-office-program-performance`);
  });

  test('con semana, la pide por week_start', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, weeklyBody()));
    await service.getWeeklyPerformance({ weekStart: '2026-10-26' });
    assert.equal(transport.calls[0].url, `${BASE_URL}/reporting/weekly-office-program-performance?week_start=2026-10-26`);
  });

  test('un week_start que no es una fecha no sale a la red', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, weeklyBody()));
    await assert.rejects(service.getWeeklyPerformance({ weekStart: '2026-10-26&x=1' }), expectUiError({ kind: 'request_invalid' }));
    assert.equal(transport.calls.length, 0);
  });

  test('404 week_not_computed no es un error: la semana todavía no se calculó', async () => {
    const { service } = serviceWith(() => jsonResponse(404, { detail: 'no completed pipeline run covers this week', code: 'week_not_computed' }));
    assert.deepEqual(await service.getWeeklyPerformance({ weekStart: '2026-10-19' }), { status: 'not_computed' });
  });

  test('otro 404 es request_invalid', async () => {
    const { service } = serviceWith(() => jsonResponse(404, { detail: 'x', code: 'not_found' }));
    await assert.rejects(service.getWeeklyPerformance(), expectUiError({ kind: 'request_invalid' }));
  });

  test('503 storage_unavailable es storage_unavailable', async () => {
    const { service } = serviceWith(() => jsonResponse(503, { detail: 'storage is temporarily unavailable', code: 'storage_unavailable' }));
    await assert.rejects(service.getWeeklyPerformance(), expectUiError({ kind: 'storage_unavailable' }));
  });

  test('un 503 sin ese código, o un 5xx sin JSON, es server_error', async () => {
    const other = serviceWith(() => jsonResponse(503, { detail: 'x', code: 'pipeline_unavailable' }));
    await assert.rejects(other.service.getWeeklyPerformance(), expectUiError({ kind: 'server_error' }));
    const plain = serviceWith(() => textResponse(500, 'Internal Server Error'));
    await assert.rejects(plain.service.getWeeklyPerformance(), expectUiError({ kind: 'server_error' }));
    const noBody = serviceWith(() => textResponse(503, 'Service Unavailable'));
    await assert.rejects(noBody.service.getWeeklyPerformance(), expectUiError({ kind: 'server_error' }));
  });

  test('un 422 es request_invalid y un 401, session_expired', async () => {
    const invalid = serviceWith(() => jsonResponse(422, { detail: [], code: 'validation_error' }));
    await assert.rejects(invalid.service.getWeeklyPerformance(), expectUiError({ kind: 'request_invalid' }));
    const unauthorized = serviceWith(() => jsonResponse(401, { detail: 'x' }));
    await assert.rejects(unauthorized.service.getWeeklyPerformance(), expectUiError({ kind: 'session_expired' }));
  });

  test('una respuesta fuera de contrato es unexpected_response', async () => {
    const { service } = serviceWith(() => jsonResponse(200, { week_start: null }));
    await assert.rejects(service.getWeeklyPerformance(), expectUiError({ kind: 'unexpected_response' }));
  });

  test('sin red es network; sin respuesta a tiempo, timeout', async () => {
    const offline = createReportingService({ client: clientWith(offlineFetch()), timeoutMs: 1_000 });
    await assert.rejects(offline.getWeeklyPerformance(), expectUiError({ kind: 'network' }));
    const hanging = createReportingService({ client: clientWith(hangingFetch()), timeoutMs: 5 });
    await assert.rejects(hanging.getWeeklyPerformance(), expectUiError({ kind: 'timeout' }));
  });

  test('una cancelación se propaga como ApiAbortError', async () => {
    const controller = new AbortController();
    const service = createReportingService({ client: clientWith(hangingFetch()), timeoutMs: 1_000 });
    const pending = service.getWeeklyPerformance({ signal: controller.signal });
    controller.abort();
    await assert.rejects(pending, ApiAbortError);
  });
});

describe('getLatestPipelineRun', () => {
  test('lee la última corrida', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, runBody()));
    const run = await service.getLatestPipelineRun();
    assert.equal(run.status, 'completed');
    assert.equal(transport.calls[0].url, `${BASE_URL}/reporting/pipeline-runs/latest`);
  });

  test('404 pipeline_run_not_found: el pipeline todavía no ha corrido', async () => {
    const { service } = serviceWith(() => jsonResponse(404, { detail: 'the pipeline has not run yet', code: 'pipeline_run_not_found' }));
    assert.equal(await service.getLatestPipelineRun(), null);
  });

  test('otro 404 es request_invalid; un 503 de almacenamiento, storage_unavailable', async () => {
    const other = serviceWith(() => jsonResponse(404, { detail: 'x', code: 'week_not_computed' }));
    await assert.rejects(other.service.getLatestPipelineRun(), expectUiError({ kind: 'request_invalid' }));
    const storage = serviceWith(() => jsonResponse(503, { detail: 'x', code: 'storage_unavailable' }));
    await assert.rejects(storage.service.getLatestPipelineRun(), expectUiError({ kind: 'storage_unavailable' }));
  });
});

describe('weeklyReducer, weeklyView y el paso entre semanas', () => {
  const report = normalizeWeeklyPerformance(weeklyBody());
  const empty = { week_start: '2026-10-12', entries: [] };

  test('carga, datos, vacío, sin calcular y error son estados exclusivos', () => {
    const loading = weeklyReducer(INITIAL_WEEKLY_STATE, { type: 'week_requested', week: null });
    assert.equal(weeklyView(loading), 'loading');
    assert.equal(weeklyView(weeklyReducer(loading, { type: 'week_loaded', week: null, report })), 'data');
    assert.equal(weeklyView(weeklyReducer(loading, { type: 'week_loaded', week: '2026-10-12', report: empty })), 'empty');
    assert.equal(weeklyView(weeklyReducer(loading, { type: 'week_not_computed', week: '2026-10-19' })), 'not_computed');
    assert.equal(weeklyView(weeklyReducer(loading, { type: 'week_failed', error: { kind: 'network' } })), 'error');
    assert.equal(weeklyView(INITIAL_WEEKLY_STATE), 'loading');
  });

  test('la primera carga fija la última semana calculada; las siguientes no la mueven', () => {
    const first = weeklyReducer(INITIAL_WEEKLY_STATE, { type: 'week_loaded', week: null, report });
    assert.equal(first.latestWeek, '2026-11-02');
    const older = weeklyReducer(
      weeklyReducer(first, { type: 'week_requested', week: '2026-10-26' }),
      { type: 'week_loaded', week: '2026-10-26', report: { week_start: '2026-10-26', entries: [] } }
    );
    assert.equal(older.latestWeek, '2026-11-02');
  });

  test('al cambiar de semana se descarta el reporte anterior', () => {
    const loaded = weeklyReducer(INITIAL_WEEKLY_STATE, { type: 'week_loaded', week: null, report });
    const requested = weeklyReducer(loaded, { type: 'week_requested', week: '2026-10-26' });
    assert.equal(requested.report, null);
    assert.equal(shownWeek(requested), '2026-10-26');
    const failed = weeklyReducer(loaded, { type: 'week_failed', error: { kind: 'server_error' } });
    assert.equal(failed.report, null);
    assert.equal(weeklyView(failed), 'error');
  });

  test('semana anterior y siguiente: la siguiente se detiene en la última calculada', () => {
    const latest = weeklyReducer(INITIAL_WEEKLY_STATE, { type: 'week_loaded', week: null, report });
    assert.equal(previousWeek(latest), '2026-10-26');
    assert.equal(nextWeek(latest), null);
    const older = weeklyReducer(latest, { type: 'week_not_computed', week: '2026-10-19' });
    assert.equal(shownWeek(older), '2026-10-19');
    assert.equal(previousWeek(older), '2026-10-12');
    assert.equal(nextWeek(older), '2026-10-26');
  });

  test('antes de conocer la última semana no hay semana anterior ni siguiente', () => {
    assert.equal(previousWeek(INITIAL_WEEKLY_STATE), null);
    assert.equal(nextWeek(INITIAL_WEEKLY_STATE), null);
  });
});

describe('createWeeklySession', () => {
  function controllable() {
    const calls = [];
    const fn = ({ weekStart, signal }) =>
      new Promise((resolve, reject) => {
        calls.push({ weekStart, resolve, reject });
        signal.addEventListener('abort', () => reject(new ApiAbortError()));
      });
    return { fn, calls };
  }

  const computed = (report) => ({ status: 'computed', report });

  test('carga la última semana al activarse, una sola vez', async () => {
    const operation = controllable();
    const actions = [];
    const session = createWeeklySession((action) => actions.push(action), { getWeeklyPerformance: operation.fn });
    session.activate();
    session.activate();
    assert.equal(operation.calls.length, 1);
    assert.equal(operation.calls[0].weekStart, undefined);
    operation.calls[0].resolve(computed('r'));
    await tick();
    assert.deepEqual(actions, [
      { type: 'week_requested', week: null },
      { type: 'week_loaded', week: null, report: 'r' },
    ]);
  });

  test('pedir una semana la envía, y una semana sin calcular llega como tal', async () => {
    const operation = controllable();
    const actions = [];
    const session = createWeeklySession((action) => actions.push(action), { getWeeklyPerformance: operation.fn });
    session.activate();
    void session.load('2026-10-19');
    assert.equal(operation.calls[1].weekStart, '2026-10-19');
    operation.calls[1].resolve({ status: 'not_computed' });
    await tick();
    assert.deepEqual(actions.at(-1), { type: 'week_not_computed', week: '2026-10-19' });
  });

  test('una respuesta tardía de otra semana se descarta', async () => {
    const operation = controllable();
    const actions = [];
    const session = createWeeklySession((action) => actions.push(action), { getWeeklyPerformance: operation.fn });
    session.activate();
    void session.load('2026-10-26');
    void session.load('2026-10-19');
    operation.calls[2].resolve(computed('tercera'));
    await tick();
    operation.calls[1].resolve(computed('segunda'));
    await tick();
    assert.deepEqual(actions.filter((action) => action.type === 'week_loaded'), [
      { type: 'week_loaded', week: '2026-10-19', report: 'tercera' },
    ]);
  });

  test('recargar repite la semana actual', async () => {
    const operation = controllable();
    const session = createWeeklySession(() => {}, { getWeeklyPerformance: operation.fn });
    session.activate();
    void session.load('2026-10-26');
    void session.reload();
    assert.equal(operation.calls.at(-1).weekStart, '2026-10-26');
  });

  test('tras dispose no despacha nada; un fallo llega con su error', async () => {
    const disposed = controllable();
    const actions = [];
    const session = createWeeklySession((action) => actions.push(action), { getWeeklyPerformance: disposed.fn });
    session.activate();
    session.dispose();
    await tick();
    assert.deepEqual(actions, [{ type: 'week_requested', week: null }]);

    const failing = controllable();
    const failures = [];
    const second = createWeeklySession((action) => failures.push(action), { getWeeklyPerformance: failing.fn });
    second.activate();
    failing.calls[0].reject(new ReportingServiceError({ kind: 'storage_unavailable' }));
    await tick();
    assert.deepEqual(failures.at(-1), { type: 'week_failed', error: { kind: 'storage_unavailable' } });
  });
});

describe('freshnessReducer y createFreshnessSession', () => {
  const run = normalizePipelineRun(runBody());

  test('la franja tiene su propia carga y su propio error', () => {
    const loading = freshnessReducer(INITIAL_FRESHNESS_STATE, { type: 'freshness_started' });
    assert.equal(loading.load.status, 'loading');
    const loaded = freshnessReducer(loading, { type: 'freshness_loaded', run });
    assert.equal(loaded.run, run);
    const failed = freshnessReducer(loaded, { type: 'freshness_failed', error: { kind: 'network' } });
    assert.equal(failed.load.status, 'error');
    assert.equal(failed.run, run);
    assert.equal(freshnessReducer(loading, { type: 'freshness_loaded', run: null }).run, null);
  });

  test('carga al activarse, descarta lo que llega tras dispose y no repite errores ajenos', async () => {
    const calls = [];
    const fn = ({ signal }) =>
      new Promise((resolve, reject) => {
        calls.push({ resolve, reject });
        signal.addEventListener('abort', () => reject(new ApiAbortError()));
      });
    const actions = [];
    const session = createFreshnessSession((action) => actions.push(action), { getLatestPipelineRun: fn });
    session.activate();
    session.activate();
    assert.equal(calls.length, 1);
    calls[0].resolve(run);
    await tick();
    assert.deepEqual(actions, [{ type: 'freshness_started' }, { type: 'freshness_loaded', run }]);
    void session.reload();
    session.dispose();
    await tick();
    assert.equal(actions.length, 3);
  });
});
