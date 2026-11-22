// Reporte técnico (/telemetry): normalizadores, servicio con el cliente real y un
// transporte falso, y reducer y sesión del hook, sin montar React.
//
// DEV-55 (parada 4): el reporte se encola (`GET /telemetry/report` → 202 `{task_id}`)
// y se sondea `GET /tasks/{task_id}` hasta `success` o `failure`. Los tests del
// servicio, del reducer y de la sesión se adaptaron a ese contrato; los del
// normalizador del reporte no cambian (es el `result` de la tarea).

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_TELEMETRY_REPORT_STATE,
  POLL_DELAYS_MS,
  POLL_TIMEOUT_MS,
  createTelemetryReportSession,
  pollDelayMs,
  reportView,
  telemetryReportReducer,
} from '../hooks/use-telemetry-report.ts';
import { ApiAbortError, createApiClient } from '../lib/api-client.ts';
import {
  UnexpectedResponseError,
  normalizeTaskAccepted,
  normalizeTelemetryReport,
  normalizeTelemetryReportTask,
} from '../services/normalizers.ts';
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

const TASK_ID = '9b1d3f2a-6c4e-4b8a-9d2f-1e3c5a7b9d0f';

function taskBody(status, result = null) {
  return { task_id: TASK_ID, status, result };
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

describe('normalizeTaskAccepted y normalizeTelemetryReportTask', () => {
  test('el 202 da el id de la tarea', () => {
    assert.equal(normalizeTaskAccepted({ task_id: TASK_ID }), TASK_ID);
  });

  test('un id que no es un UUID v4 rompe el contrato y el error no lo repite', () => {
    assert.throws(
      () => normalizeTaskAccepted({ task_id: LEAK }),
      (error) => error instanceof UnexpectedResponseError && !error.message.includes(LEAK)
    );
  });

  test('pending y started sin resultado', () => {
    assert.deepEqual(normalizeTelemetryReportTask(taskBody('pending'), TASK_ID), { status: 'pending' });
    assert.deepEqual(normalizeTelemetryReportTask(taskBody('started'), TASK_ID), { status: 'started' });
  });

  test('success trae el reporte normalizado (sin campos de más)', () => {
    const body = reportBody();
    body.metrics.dominant_event_types[0].user_id = LEAK;
    const task = normalizeTelemetryReportTask(taskBody('success', body), TASK_ID);
    assert.equal(task.status, 'success');
    assert.equal(task.report.metrics.auth_failure_rate[0].failure_rate, 0.5);
    assert.doesNotMatch(JSON.stringify(task), /leak|user_id/);
  });

  test('de un failure no se lee nada más', () => {
    assert.deepEqual(normalizeTelemetryReportTask(taskBody('failure', { code: 'task_failed', detail: LEAK }), TASK_ID), { status: 'failure' });
  });

  test('un estado desconocido, otro id o un resultado antes de terminar rompen el contrato', () => {
    assert.throws(() => normalizeTelemetryReportTask(taskBody('RETRY'), TASK_ID), UnexpectedResponseError);
    assert.throws(() => normalizeTelemetryReportTask({ ...taskBody('pending'), task_id: '00000000-0000-4000-8000-000000000000' }, TASK_ID), UnexpectedResponseError);
    assert.throws(() => normalizeTelemetryReportTask(taskBody('started', reportBody()), TASK_ID), UnexpectedResponseError);
    assert.throws(() => normalizeTelemetryReportTask(taskBody('success', { period: null }), TASK_ID), UnexpectedResponseError);
  });
});

describe('requestTelemetryReport (antes getTelemetryReport: ahora encola)', () => {
  test('pide la ventana por defecto, con el token, y devuelve el id de la tarea', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(202, { task_id: TASK_ID }));
    assert.equal(await service.requestTelemetryReport(), TASK_ID);
    assert.equal(transport.calls.length, 1);
    assert.equal(transport.calls[0].url, `${BASE_URL}/telemetry/report`);
  });

  test('un 200 síncrono ya no es el contrato: unexpected_response', async () => {
    const { service } = serviceWith(() => jsonResponse(200, reportBody()));
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'unexpected_response' }));
  });

  test('un 503 al encolar es queue_unavailable', async () => {
    const { service } = serviceWith(() => jsonResponse(503, { detail: 'the task queue is not available', code: 'task_queue_unavailable' }));
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'queue_unavailable' }));
  });

  test('otro 5xx es server_error', async () => {
    const { service } = serviceWith(() => textResponse(500, 'Internal Server Error'));
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'server_error' }));
  });

  test('un 422 es request_invalid', async () => {
    const { service } = serviceWith(() => jsonResponse(422, { detail: [], code: 'validation_error' }));
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'request_invalid' }));
  });

  test('un 401 es session_expired', async () => {
    const { service } = serviceWith(() => jsonResponse(401, { detail: 'x' }));
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'session_expired' }));
  });

  test('un 202 fuera de contrato es unexpected_response', async () => {
    const { service } = serviceWith(() => jsonResponse(202, { id: TASK_ID }));
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'unexpected_response' }));
  });

  test('sin red es network', async () => {
    const service = createTelemetryReportService({ client: clientWith(offlineFetch()), timeoutMs: 1_000 });
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'network' }));
  });

  test('sin respuesta a tiempo es timeout', async () => {
    const service = createTelemetryReportService({ client: clientWith(hangingFetch()), timeoutMs: 5 });
    await assert.rejects(service.requestTelemetryReport(), expectUiError({ kind: 'timeout' }));
  });

  test('una cancelación se propaga como ApiAbortError', async () => {
    const controller = new AbortController();
    const service = createTelemetryReportService({ client: clientWith(hangingFetch()), timeoutMs: 1_000 });
    const pending = service.requestTelemetryReport({ signal: controller.signal });
    controller.abort();
    await assert.rejects(pending, ApiAbortError);
  });
});

describe('getTelemetryReportTask', () => {
  test('lee /tasks/{id} con el token', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, taskBody('started')));
    assert.deepEqual(await service.getTelemetryReportTask(TASK_ID), { status: 'started' });
    assert.equal(transport.calls[0].url, `${BASE_URL}/tasks/${TASK_ID}`);
  });

  test('success trae el reporte', async () => {
    const { service } = serviceWith(() => jsonResponse(200, taskBody('success', reportBody())));
    const task = await service.getTelemetryReportTask(TASK_ID);
    assert.equal(task.status, 'success');
    assert.equal(task.report.period.to, '2026-11-05T12:00:00.000Z');
  });

  test('un 404 durante el sondeo es task_expired', async () => {
    const { service } = serviceWith(() => jsonResponse(404, { detail: 'task not found', code: 'task_not_found' }));
    await assert.rejects(service.getTelemetryReportTask(TASK_ID), expectUiError({ kind: 'task_expired' }));
  });

  test('un 503 durante el sondeo es queue_unavailable', async () => {
    const { service } = serviceWith(() => jsonResponse(503, { detail: 'x', code: 'task_queue_unavailable' }));
    await assert.rejects(service.getTelemetryReportTask(TASK_ID), expectUiError({ kind: 'queue_unavailable' }));
  });

  test('una respuesta de otra tarea es unexpected_response', async () => {
    const { service } = serviceWith(() => jsonResponse(200, { ...taskBody('pending'), task_id: '00000000-0000-4000-8000-000000000000' }));
    await assert.rejects(service.getTelemetryReportTask(TASK_ID), expectUiError({ kind: 'unexpected_response' }));
  });

  test('el id va codificado en la ruta', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(404, {}));
    await assert.rejects(service.getTelemetryReportTask('a/b?c'), expectUiError({ kind: 'task_expired' }));
    assert.equal(transport.calls[0].url, `${BASE_URL}/tasks/a%2Fb%3Fc`);
  });
});

describe('telemetryReportReducer y reportView', () => {
  const report = normalizeTelemetryReport(reportBody());

  test('en cola, calculando, datos y error', () => {
    const queued = telemetryReportReducer(INITIAL_TELEMETRY_REPORT_STATE, { type: 'report_started' });
    assert.equal(reportView(queued), 'queued');
    const computing = telemetryReportReducer(queued, { type: 'report_computing' });
    assert.equal(reportView(computing), 'computing');
    const loaded = telemetryReportReducer(computing, { type: 'report_succeeded', report });
    assert.equal(reportView(loaded), 'data');
    const failed = telemetryReportReducer(computing, { type: 'report_failed', error: { kind: 'task_failed' } });
    assert.equal(reportView(failed), 'error');
  });

  test('un fallo al recargar no borra el último reporte', () => {
    const loaded = telemetryReportReducer(INITIAL_TELEMETRY_REPORT_STATE, { type: 'report_succeeded', report });
    const failed = telemetryReportReducer(loaded, { type: 'report_failed', error: { kind: 'network' } });
    assert.equal(failed.report, report);
    assert.equal(reportView(failed), 'data');
    assert.equal(failed.load.status, 'error');
  });

  test('una recarga con un reporte en pantalla lo mantiene mientras se calcula el nuevo', () => {
    const loaded = telemetryReportReducer(INITIAL_TELEMETRY_REPORT_STATE, { type: 'report_succeeded', report });
    const reloading = telemetryReportReducer(loaded, { type: 'report_started' });
    assert.equal(reportView(reloading), 'data');
    assert.equal(reloading.load.status, 'queued');
  });
});

describe('createTelemetryReportSession (encolar y sondear)', () => {
  // Una petición controlable: cada llamada queda pendiente hasta resolverla o rechazarla.
  function controllable() {
    const calls = [];
    const fn = (...args) =>
      new Promise((resolve, reject) => {
        const options = args.at(-1) ?? {};
        calls.push({ args, resolve, reject });
        options.signal?.addEventListener('abort', () => reject(new ApiAbortError()));
      });
    return { fn, calls };
  }

  // Reloj y esperas falsos: cada espera avanza el reloj lo que dura y resuelve en el acto.
  function fakeClock() {
    const clock = { now: 0, sleeps: [] };
    clock.sleep = (ms, signal) => {
      clock.sleeps.push(ms);
      if (signal.aborted) return Promise.reject(new ApiAbortError());
      clock.now += ms;
      return Promise.resolve();
    };
    return clock;
  }

  function sessionWith({ request, task, clock = fakeClock() }) {
    const actions = [];
    const session = createTelemetryReportSession((action) => actions.push(action), {
      requestTelemetryReport: request,
      getTelemetryReportTask: task,
      sleep: clock.sleep,
      now: () => clock.now,
    });
    return { session, actions, clock };
  }

  async function settle() {
    for (let i = 0; i < 20; i += 1) await tick();
  }

  test('las esperas crecen: 1 s, 2 s y después 3 s', () => {
    assert.deepEqual(POLL_DELAYS_MS, [1_000, 2_000, 3_000]);
    assert.deepEqual([0, 1, 2, 3, 10].map(pollDelayMs), [1_000, 2_000, 3_000, 3_000, 3_000]);
  });

  test('en cola → calculando → reporte, una sola petición de encolado', async () => {
    const statuses = [{ status: 'pending' }, { status: 'started' }, { status: 'started' }, { status: 'success', report: 'report' }];
    const taskCalls = [];
    const { session, actions, clock } = sessionWith({
      request: async () => TASK_ID,
      task: async (taskId) => {
        taskCalls.push(taskId);
        return statuses.shift();
      },
    });
    session.activate();
    session.activate();
    await settle();
    assert.deepEqual(actions, [{ type: 'report_started' }, { type: 'report_computing' }, { type: 'report_succeeded', report: 'report' }]);
    assert.deepEqual(taskCalls, [TASK_ID, TASK_ID, TASK_ID, TASK_ID]);
    assert.deepEqual(clock.sleeps, [1_000, 2_000, 3_000, 3_000]);
  });

  test('una tarea fallida es task_failed', async () => {
    const { session, actions } = sessionWith({ request: async () => TASK_ID, task: async () => ({ status: 'failure' }) });
    session.activate();
    await settle();
    assert.deepEqual(actions.at(-1), { type: 'report_failed', error: { kind: 'task_failed' } });
  });

  test('un 404 durante el sondeo (tarea caducada) es task_expired y no se sigue sondeando', async () => {
    let calls = 0;
    const { session, actions } = sessionWith({
      request: async () => TASK_ID,
      task: async () => {
        calls += 1;
        throw new TelemetryReportServiceError({ kind: 'task_expired' });
      },
    });
    session.activate();
    await settle();
    assert.deepEqual(actions.at(-1), { type: 'report_failed', error: { kind: 'task_expired' } });
    assert.equal(calls, 1);
  });

  test('un 503 al encolar es queue_unavailable, sin sondeo', async () => {
    let polled = false;
    const { session, actions } = sessionWith({
      request: async () => {
        throw new TelemetryReportServiceError({ kind: 'queue_unavailable' });
      },
      task: async () => {
        polled = true;
        return { status: 'pending' };
      },
    });
    session.activate();
    await settle();
    assert.deepEqual(actions, [{ type: 'report_started' }, { type: 'report_failed', error: { kind: 'queue_unavailable' } }]);
    assert.equal(polled, false);
  });

  test('a los 10 minutos sin terminar es polling_timeout', async () => {
    let calls = 0;
    const { session, actions, clock } = sessionWith({
      request: async () => TASK_ID,
      task: async () => {
        calls += 1;
        return { status: 'started' };
      },
    });
    session.activate();
    for (let i = 0; i < 400 && actions.at(-1)?.type !== 'report_failed'; i += 1) await tick();
    assert.equal(POLL_TIMEOUT_MS, 600_000);
    assert.deepEqual(actions.at(-1), { type: 'report_failed', error: { kind: 'polling_timeout' } });
    assert.ok(clock.now >= POLL_TIMEOUT_MS);
    // El tope se mira antes de cada espera: 1 + 2 + 3·198 = 597 s tras 200 sondeos, y el 201.º cae en 600 s.
    assert.equal(calls, 201);
  });

  test('tras dispose (salir de la página) no despacha nada ni sigue sondeando', async () => {
    const task = controllable();
    const { session, actions } = sessionWith({ request: async () => TASK_ID, task: task.fn });
    session.activate();
    await settle();
    assert.equal(task.calls.length, 1);
    session.dispose();
    await settle();
    assert.deepEqual(actions, [{ type: 'report_started' }]);
    assert.equal(task.calls.length, 1);
  });

  test('dispose durante una espera la corta: no hay más peticiones', async () => {
    const sleeps = [];
    let taskCalls = 0;
    const actions = [];
    const session = createTelemetryReportSession((action) => actions.push(action), {
      requestTelemetryReport: async () => TASK_ID,
      getTelemetryReportTask: async () => {
        taskCalls += 1;
        return { status: 'pending' };
      },
      sleep: (ms, signal) =>
        new Promise((resolve, reject) => {
          sleeps.push(ms);
          signal.addEventListener('abort', () => reject(new ApiAbortError()));
        }),
      now: () => 0,
    });
    session.activate();
    await settle();
    assert.equal(sleeps.length, 1);
    session.dispose();
    await settle();
    assert.equal(taskCalls, 0);
    assert.deepEqual(actions, [{ type: 'report_started' }]);
  });

  test('una recarga descarta el sondeo anterior', async () => {
    const request = controllable();
    const { session, actions } = sessionWith({ request: request.fn, task: async () => ({ status: 'success', report: 'nuevo' }) });
    session.activate();
    void session.reload();
    request.calls[1].resolve(TASK_ID);
    await settle();
    assert.deepEqual(actions.at(-1), { type: 'report_succeeded', report: 'nuevo' });
    assert.equal(actions.filter((action) => action.type === 'report_failed').length, 0);
  });

  test('un fallo de red durante el sondeo llega con su error', async () => {
    const { session, actions } = sessionWith({
      request: async () => TASK_ID,
      task: async () => {
        throw new TelemetryReportServiceError({ kind: 'network' });
      },
    });
    session.activate();
    await settle();
    assert.deepEqual(actions.at(-1), { type: 'report_failed', error: { kind: 'network' } });
  });
});
