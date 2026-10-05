// Tests de services/incidents.service.ts con el cliente real y un transporte falso.
// Ejecutar desde uis/backoffice:
//   node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --import ./tests/support/resolve-alias.mjs --test "tests/*.test.mjs"

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { ApiAbortError, createApiClient } from '../lib/api-client.ts';
import {
  ANALYZE_TIMEOUT_MS,
  CLIENT_MAX_FILE_BYTES,
  EXPORT_TIMEOUT_MS,
  IncidentServiceError,
  createIncidentsService,
  safeDownloadFilename,
  uiErrorFromHttp,
} from '../services/incidents.service.ts';
import {
  BASE_URL,
  LEAK,
  csvFile,
  hangingFetch,
  jsonResponse,
  offlineFetch,
  recordingFetch,
  textResponse,
  validAnalysis,
} from './support/http-fakes.mjs';

const ANALYSIS_ID = '7d3e0c2a-5b1f-4a57-9d0e-2f4c1b8a6e10';
const CSV_BODY = `metric,value\r\ntotal_records,13\r\nnote,${LEAK}\r\n`;

function serviceWith(makeResponse, extra = {}) {
  const transport = recordingFetch(makeResponse);
  const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => BASE_URL });
  return { service: createIncidentsService({ client, ...extra }), transport };
}

// Fragmentos de datos de filas o del CSV que nunca pueden aparecer en un error.
const PII_FRAGMENTS = [LEAK, 'leak', 'canary', 'customer_email', 'NXV-000001', 'Printer broken', 'ticket_id', 'description', 'rows'];
const ROW = { ticket_id: 'NXV-000001', customer_email: LEAK, description: 'Printer broken' };

/**
 * Comprueba el UiError y que el error no contiene datos filtrados: ni en el
 * mensaje ni en su serialización, y sin propiedades extra (cause, body, headers…).
 */
function expectUiError(expected, forbidden = PII_FRAGMENTS) {
  return (error) => {
    assert.ok(error instanceof IncidentServiceError, `expected IncidentServiceError, got ${error?.name}`);
    assert.deepEqual(error.uiError, expected);
    assert.equal(error.cause, undefined);
    const ownProperties = Object.getOwnPropertyNames(error).filter((name) => !['stack', 'message', 'name', 'uiError'].includes(name));
    assert.deepEqual(ownProperties, []);
    const exposed = [error.message, String(error), JSON.stringify(error), JSON.stringify(error.uiError)].join(' ');
    for (const value of forbidden) assert.equal(exposed.includes(value), false, `error exposes ${value}`);
    return true;
  };
}

describe('constantes acordadas', () => {
  test('timeouts de 30 s y 15 s y margen de 4 KiB bajo 1 MiB', () => {
    assert.equal(ANALYZE_TIMEOUT_MS, 30_000);
    assert.equal(EXPORT_TIMEOUT_MS, 15_000);
    assert.equal(CLIENT_MAX_FILE_BYTES, 1_048_576 - 4_096);
  });

  test('el servicio usa esos timeouts por defecto', async () => {
    const seen = [];
    const real = createApiClient({
      fetch: async (url) =>
        url.endsWith('/export')
          ? new Response('x', { status: 200, headers: { 'X-Analysis-Id': ANALYSIS_ID } })
          : jsonResponse(200, validAnalysis()),
      getBaseUrl: () => BASE_URL,
    });
    const spy = {
      get: (path, options, handle) => { seen.push(['GET', options.timeoutMs]); return real.get(path, options, handle); },
      postForm: (path, form, options, handle) => { seen.push(['POST', options.timeoutMs]); return real.postForm(path, form, options, handle); },
    };
    const service = createIncidentsService({ client: spy });
    await service.analyzeIncidentFile(csvFile());
    await service.exportIncidentResults(ANALYSIS_ID);
    assert.deepEqual(seen, [['POST', 30_000], ['GET', 15_000]]);
  });
});

describe('analyzeIncidentFile — éxito y envío', () => {
  test('POST multipart a /api/incidents/analyze con el File en el campo file y sin Content-Type manual', async () => {
    const { service, transport } = serviceWith(() => jsonResponse(200, validAnalysis()));
    const file = csvFile('incidents.csv', 128);
    const result = await service.analyzeIncidentFile(file);

    assert.deepEqual(result, validAnalysis());
    const [{ url, init }] = transport.calls;
    assert.equal(url, `${BASE_URL}/api/incidents/analyze`);
    assert.equal(init.method, 'POST');
    assert.ok(init.body instanceof FormData);
    assert.equal(init.headers, undefined);
    assert.equal(init.credentials, undefined);
    const sent = init.body.get('file');
    assert.ok(sent instanceof File);
    assert.equal(sent.name, 'incidents.csv');
    assert.equal(sent.size, 128);
    assert.deepEqual([...init.body.keys()], ['file']);
  });

  test('el contenido del archivo nunca se lee en JavaScript', async () => {
    const { service } = serviceWith(() => jsonResponse(200, validAnalysis()));
    const file = csvFile();
    await service.analyzeIncidentFile(file);
    assert.equal(file.readAttempts, 0);
  });
});

describe('analyzeIncidentFile — prevalidación de UX', () => {
  test('.csv sin distinguir mayúsculas', async () => {
    for (const name of ['a.csv', 'A.CSV', 'report.Csv', ' spaced.csv ']) {
      const { service, transport } = serviceWith(() => jsonResponse(200, validAnalysis()));
      await service.analyzeIncidentFile(csvFile(name));
      assert.equal(transport.calls.length, 1, name);
    }
  });

  test('otra extensión → unsupported_file_type sin llamar a la API', async () => {
    for (const name of ['a.txt', 'a.csv.txt', 'csv', 'a.xlsx']) {
      const { service, transport } = serviceWith(() => jsonResponse(200, validAnalysis()));
      await assert.rejects(service.analyzeIncidentFile(csvFile(name)), expectUiError({ kind: 'unsupported_file_type' }));
      assert.equal(transport.calls.length, 0, name);
    }
  });

  test('tamaño exacto 1 MiB − 4 KiB se acepta; un byte más se rechaza sin llamar a la API', async () => {
    const ok = serviceWith(() => jsonResponse(200, validAnalysis()));
    await ok.service.analyzeIncidentFile(csvFile('a.csv', CLIENT_MAX_FILE_BYTES));
    assert.equal(ok.transport.calls.length, 1);

    const tooBig = serviceWith(() => jsonResponse(200, validAnalysis()));
    await assert.rejects(tooBig.service.analyzeIncidentFile(csvFile('a.csv', CLIENT_MAX_FILE_BYTES + 1)), expectUiError({ kind: 'file_too_large' }));
    assert.equal(tooBig.transport.calls.length, 0);
  });
});

describe('analyzeIncidentFile — errores HTTP', () => {
  const cases = [
    ['400 invalid_csv conserva detail', 400, { detail: 'missing required columns: customer_email', code: 'invalid_csv' }, { kind: 'invalid_csv', detail: 'missing required columns: customer_email' }],
    ['400 invalid_csv sin detail string', 400, { detail: ['x'], code: 'invalid_csv' }, { kind: 'invalid_csv', detail: '' }],
    ['400 bad_request', 400, { detail: 'Bad Request', code: 'bad_request' }, { kind: 'request_invalid' }],
    ['404 not_found', 404, { detail: 'Not Found', code: 'not_found' }, { kind: 'request_invalid' }],
    ['405 method_not_allowed', 405, { detail: 'Method Not Allowed', code: 'method_not_allowed' }, { kind: 'request_invalid' }],
    ['413', 413, { detail: 'request body exceeds the 1048576 bytes limit', code: 'file_too_large' }, { kind: 'file_too_large' }],
    ['415', 415, { detail: 'only .csv files are accepted', code: 'unsupported_file_type' }, { kind: 'unsupported_file_type' }],
    ['422 con detail lista no se filtra', 422, { detail: [{ loc: ['body', 'file'], msg: `Field required ${LEAK}`, type: 'missing' }], code: 'validation_error' }, { kind: 'request_invalid' }],
    ['418 código desconocido', 418, { detail: `teapot ${LEAK}`, code: 'teapot' }, { kind: 'request_invalid' }],
    ['500 internal_error', 500, { detail: 'internal server error', code: 'internal_error' }, { kind: 'server_error' }],
    ['503 sin code', 503, { message: LEAK }, { kind: 'server_error' }],
  ];
  for (const [name, status, body, expected] of cases) {
    test(name, async () => {
      const { service } = serviceWith(() => jsonResponse(status, body));
      // El detail permitido de invalid_csv cita un nombre de columna; el resto de
      // fragmentos sensibles sigue prohibido.
      const forbidden = expected.kind === 'invalid_csv' ? [LEAK, 'leak', 'NXV-000001', 'Printer broken'] : PII_FRAGMENTS;
      await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError(expected, forbidden));
    });
  }

  test('ningún detail arbitrario de un 4xx se propaga (solo el de invalid_csv)', async () => {
    const piiDetail = `row 3: customer_email=${LEAK} ticket_id=NXV-000001 description=Printer broken`;
    // 401 ya no llega aquí como request_invalid: es una sesión caducada (test siguiente).
    for (const [status, code] of [[400, 'bad_request'], [400, 'unknown_code'], [403, 'forbidden'], [404, 'not_found'], [405, 'method_not_allowed'], [409, 'conflict'], [422, 'validation_error'], [429, null]]) {
      const { service } = serviceWith(() => jsonResponse(status, { detail: piiDetail, code, rows: [ROW] }));
      await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError({ kind: 'request_invalid' }));
    }
  });

  test('401 (AUTH-02) → session_expired, sin filtrar el cuerpo', async () => {
    const piiDetail = `row 3: customer_email=${LEAK}`;
    const { service } = serviceWith(() => jsonResponse(401, { detail: piiDetail, code: 'not_authenticated', rows: [ROW] }));
    await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError({ kind: 'session_expired' }));
  });

  test('422 con detail en forma de lista no filtra su contenido', async () => {
    const body = {
      detail: [
        { loc: ['body', 'file', LEAK], msg: `Field required: ${LEAK}`, type: 'missing', input: ROW },
        { loc: ['body', 'rows', 0], msg: 'Printer broken', type: 'value_error', ctx: { customer_email: LEAK } },
      ],
      code: 'validation_error',
    };
    const { service } = serviceWith(() => jsonResponse(422, body));
    await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError({ kind: 'request_invalid' }));
  });

  test('500 con PII en el body no filtra ningún fragmento', async () => {
    const body = { detail: `crash while reading ${LEAK} / NXV-000001 / Printer broken`, code: 'internal_error', rows: [ROW], customer_email: LEAK };
    for (const makeResponse of [() => jsonResponse(500, body), () => textResponse(500, JSON.stringify(body))]) {
      const { service } = serviceWith(makeResponse);
      await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError({ kind: 'server_error' }));
    }
  });

  test('errores con cuerpo no JSON se clasifican solo por status', async () => {
    for (const [status, expected] of [[502, { kind: 'server_error' }], [413, { kind: 'file_too_large' }], [400, { kind: 'request_invalid' }]]) {
      const { service } = serviceWith(() => textResponse(status, `<html>${LEAK}</html>`));
      await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError(expected));
    }
  });

  test('200 que no cumple el contrato → unexpected_response sin valores del body', async () => {
    const mutations = [
      (r) => { r.invalid_breakdown[0].count = LEAK; },
      (r) => { r.totals = { ...ROW }; },
      (r) => { r.categories = [ROW]; },
      (r) => { r.analysis_id = ROW; },
    ];
    for (const mutate of mutations) {
      const bad = validAnalysis();
      mutate(bad);
      bad.customer_email = LEAK;
      bad.rows = [ROW];
      const { service } = serviceWith(() => jsonResponse(200, bad));
      await assert.rejects(
        service.analyzeIncidentFile(csvFile()),
        expectUiError({ kind: 'unexpected_response' }, [...PII_FRAGMENTS, 'invalid_breakdown', 'totals', 'categories', 'analysis_id'])
      );
    }
  });

  test('200 no JSON → unexpected_response', async () => {
    const { service } = serviceWith(() => textResponse(200, LEAK));
    await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError({ kind: 'unexpected_response' }));
  });

  test('status 2xx/3xx inesperado → unexpected_response', async () => {
    const { service } = serviceWith(() => new Response(null, { status: 204 }));
    await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError({ kind: 'unexpected_response' }));
  });
});

describe('analyzeIncidentFile — transporte', () => {
  test('red → network', async () => {
    const client = createApiClient({ fetch: offlineFetch(), getBaseUrl: () => BASE_URL });
    await assert.rejects(createIncidentsService({ client }).analyzeIncidentFile(csvFile()), expectUiError({ kind: 'network' }));
  });

  test('timeout → timeout', async () => {
    const client = createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL });
    const service = createIncidentsService({ client, timeouts: { analyzeMs: 20, exportMs: 20 } });
    await assert.rejects(service.analyzeIncidentFile(csvFile()), expectUiError({ kind: 'timeout' }));
    await assert.rejects(service.exportIncidentResults(ANALYSIS_ID), expectUiError({ kind: 'timeout' }));
  });

  test('sin NEXT_PUBLIC_API_URL → config', async () => {
    const transport = recordingFetch(() => jsonResponse(200, validAnalysis()));
    const client = createApiClient({ fetch: transport.fetch, getBaseUrl: () => '' });
    await assert.rejects(createIncidentsService({ client }).analyzeIncidentFile(csvFile()), expectUiError({ kind: 'config' }));
    assert.equal(transport.calls.length, 0);
  });

  test('cancelación de quien llama → ApiAbortError (no es un UiError)', async () => {
    const client = createApiClient({ fetch: hangingFetch(), getBaseUrl: () => BASE_URL });
    const controller = new AbortController();
    const pending = createIncidentsService({ client }).analyzeIncidentFile(csvFile(), { signal: controller.signal });
    setTimeout(() => controller.abort(), 10);
    await assert.rejects(pending, ApiAbortError);
  });
});

describe('exportIncidentResults', () => {
  const csvHeaders = (extra = {}) => ({
    'content-type': 'text/csv; charset=utf-8',
    'content-disposition': 'attachment; filename="results.csv"',
    'x-analysis-id': ANALYSIS_ID,
    ...extra,
  });

  test('GET al export y devuelve blob, analysisId y filename', async () => {
    const { service, transport } = serviceWith(() => new Response(CSV_BODY, { status: 200, headers: csvHeaders() }));
    const result = await service.exportIncidentResults(ANALYSIS_ID);
    assert.equal(transport.calls[0].url, `${BASE_URL}/api/incidents/results/export`);
    assert.equal(transport.calls[0].init.method, 'GET');
    assert.equal(result.analysisId, ANALYSIS_ID);
    assert.equal(result.filename, 'results.csv');
    assert.ok(result.blob instanceof Blob);
    assert.equal(result.blob.size, new Blob([CSV_BODY]).size);
  });

  test('exige X-Analysis-Id y no descarga el cuerpo si falta o no coincide', async () => {
    for (const headers of [csvHeaders({ 'x-analysis-id': '' }), { 'content-type': 'text/csv' }, csvHeaders({ 'x-analysis-id': 'other-analysis' })]) {
      const { service, transport } = serviceWith(() => new Response(CSV_BODY, { status: 200, headers }));
      await assert.rejects(service.exportIncidentResults(ANALYSIS_ID), expectUiError({ kind: 'export_mismatch' }, [LEAK, 'total_records']));
      assert.equal(transport.responses[0].bodyUsed, false);
    }
  });

  test('un id esperado vacío nunca coincide', async () => {
    const { service } = serviceWith(() => new Response(CSV_BODY, { status: 200, headers: csvHeaders({ 'x-analysis-id': '' }) }));
    await assert.rejects(service.exportIncidentResults(''), expectUiError({ kind: 'export_mismatch' }));
  });

  test('sin Content-Disposition usa results.csv', async () => {
    const headers = csvHeaders();
    delete headers['content-disposition'];
    const { service } = serviceWith(() => new Response(CSV_BODY, { status: 200, headers }));
    assert.equal((await service.exportIncidentResults(ANALYSIS_ID)).filename, 'results.csv');
  });

  test('404 no_analysis → no_analysis; otros errores según contrato, sin contenido del cuerpo', async () => {
    const cases = [
      [() => jsonResponse(404, { detail: 'no analysis available yet', code: 'no_analysis' }), { kind: 'no_analysis' }],
      [() => jsonResponse(500, { detail: 'internal server error', code: 'internal_error' }), { kind: 'server_error' }],
      [() => textResponse(500, CSV_BODY), { kind: 'server_error' }],
      [() => jsonResponse(405, { detail: 'Method Not Allowed', code: 'method_not_allowed' }), { kind: 'request_invalid' }],
    ];
    for (const [makeResponse, expected] of cases) {
      const { service } = serviceWith(makeResponse);
      await assert.rejects(service.exportIncidentResults(ANALYSIS_ID), expectUiError(expected, [LEAK, 'total_records']));
    }
  });
});

describe('safeDownloadFilename', () => {
  test('nombres seguros se conservan', () => {
    assert.equal(safeDownloadFilename('attachment; filename="results.csv"'), 'results.csv');
    assert.equal(safeDownloadFilename('attachment; filename=metrics-2026.csv'), 'metrics-2026.csv');
    assert.equal(safeDownloadFilename('attachment; filename="..\\\\dir\\\\report.csv"'), 'report.csv');
    assert.equal(safeDownloadFilename('attachment; filename="/tmp/x/Report 1.CSV"'), 'Report 1.CSV');
  });

  test('nombres peligrosos o no .csv → results.csv', () => {
    for (const header of [
      null,
      'attachment',
      'attachment; filename=""',
      'attachment; filename="../../etc/passwd"',
      'attachment; filename="evil.exe"',
      'attachment; filename="a<b>.csv"',
      'attachment; filename=".hidden.csv"',
      'attachment; filename="a..csv"',
      `attachment; filename="${'x'.repeat(200)}.csv"`,
      'attachment; filename="con\u0000trol.csv"',
    ]) {
      assert.equal(safeDownloadFilename(header), 'results.csv', String(header));
    }
  });
});

describe('uiErrorFromHttp', () => {
  test('solo invalid_csv transporta texto de la API', () => {
    const body = { code: 'whatever', detail: LEAK };
    for (const status of [400, 401, 403, 404, 405, 409, 413, 415, 422, 429, 500, 502, 503]) {
      const uiError = uiErrorFromHttp(status, body);
      assert.equal(JSON.stringify(uiError).includes(LEAK), false, String(status));
    }
    assert.deepEqual(uiErrorFromHttp(400, { code: 'invalid_csv', detail: 'the file is not valid UTF-8' }), {
      kind: 'invalid_csv',
      detail: 'the file is not valid UTF-8',
    });
  });

  test('invalid_csv o no_analysis con status que no corresponde no se aceptan', () => {
    assert.deepEqual(uiErrorFromHttp(500, { code: 'invalid_csv', detail: 'x' }), { kind: 'server_error' });
    assert.deepEqual(uiErrorFromHttp(422, { code: 'invalid_csv', detail: 'x' }), { kind: 'request_invalid' });
    assert.deepEqual(uiErrorFromHttp(400, { code: 'no_analysis', detail: null }), { kind: 'request_invalid' });
  });
});
