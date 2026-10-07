// Estado del gestor de incidencias: reducers y sesiones de los hooks
// (use-incident-form, use-incident-board, use-incident-summary), sin montar
// React. La unión con React se valida con tsc/lint/build y en el navegador.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_INCIDENT_BOARD_STATE,
  boardView,
  createIncidentBoardSession,
  incidentBoardReducer,
} from '../hooks/use-incident-board.ts';
import {
  INITIAL_INCIDENT_FORM_STATE,
  createIncidentFormSession,
  incidentFormReducer,
} from '../hooks/use-incident-form.ts';
import {
  INITIAL_INCIDENT_SUMMARY_STATE,
  createIncidentSummarySession,
  incidentSummaryReducer,
} from '../hooks/use-incident-summary.ts';
import { ApiAbortError } from '../lib/api-client.ts';
import { IncidentServiceError } from '../services/incident-manager.service.ts';
import { formValues, incident } from './support/incident-fakes.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));

/** Operación asíncrona controlada a mano; rechaza con ApiAbortError al abortarse. */
function controllable() {
  const calls = [];
  const fn = (...args) => {
    const options = args[args.length - 1];
    return new Promise((resolve, reject) => {
      const call = { args, resolve, reject, aborted: false };
      options.signal.addEventListener('abort', () => {
        call.aborted = true;
        reject(new ApiAbortError());
      });
      calls.push(call);
    });
  };
  return { fn, calls };
}

function store(reducer, initial) {
  let state = initial;
  const actions = [];
  const dispatch = (action) => {
    actions.push(action);
    state = reducer(state, action);
  };
  return { dispatch, actions, state: () => state };
}

const serviceError = (uiError) => new IncidentServiceError(uiError);
const NETWORK = { kind: 'network' };

// ---------------------------------------------------------------------------

describe('formulario de registro', () => {
  function harness() {
    const create = controllable();
    const s = store(incidentFormReducer, INITIAL_INCIDENT_FORM_STATE);
    const session = createIncidentFormSession(s.dispatch, { createIncident: create.fn });
    session.activate();
    return { session, create, ...s };
  }

  test('envío: cargando y, al terminar, éxito con el formulario limpio', async () => {
    const h = harness();
    const pending = h.session.submit(formValues());
    assert.equal(h.state().submit.status, 'submitting');
    assert.equal(h.state().formKey, 0);
    h.create.calls[0].resolve(incident({ title: 'Created' }));
    await pending;
    assert.equal(h.state().submit.status, 'success');
    assert.equal(h.state().submit.incident.title, 'Created');
    // El formulario usa formKey como key: cambia → se vuelve a montar vacío.
    assert.equal(h.state().formKey, 1);
  });

  test('error de la API: se muestra y el formulario no se limpia', async () => {
    const h = harness();
    const pending = h.session.submit(formValues());
    const error = { kind: 'validation', source: 'api', errors: [{ field: 'branch', message: 'Selecciona la sede.' }] };
    h.create.calls[0].reject(serviceError(error));
    await pending;
    assert.deepEqual(h.state().submit, { status: 'error', error });
    assert.equal(h.state().formKey, 0);
  });

  test('un segundo envío mientras el primero está en curso se ignora', async () => {
    const h = harness();
    void h.session.submit(formValues());
    void h.session.submit(formValues());
    assert.equal(h.create.calls.length, 1);
  });

  test('al desmontar se aborta el envío y no se despacha nada', async () => {
    const h = harness();
    const pending = h.session.submit(formValues());
    h.session.dispose();
    await pending;
    assert.equal(h.create.calls[0].aborted, true);
    assert.deepEqual(h.actions.map((action) => action.type), ['submit_started']);
  });

  test('un fallo inesperado no reenvía su texto', async () => {
    const h = harness();
    const pending = h.session.submit(formValues());
    h.create.calls[0].reject(new Error('leak.canary@example.invalid'));
    await pending;
    assert.deepEqual(h.state().submit, { status: 'error', error: { kind: 'unexpected_response' } });
  });
});

// ---------------------------------------------------------------------------

describe('listado: los cuatro estados', () => {
  function harness(onStatusChanged = () => {}) {
    const list = controllable();
    const change = controllable();
    const s = store(incidentBoardReducer, INITIAL_INCIDENT_BOARD_STATE);
    const session = createIncidentBoardSession(
      s.dispatch,
      { listIncidents: list.fn, changeIncidentStatus: change.fn },
      onStatusChanged
    );
    return { session, list, change, ...s, view: () => boardView(s.state()) };
  }

  test('cargando → con datos', async () => {
    const h = harness();
    assert.equal(h.view(), 'loading');
    h.session.activate();
    assert.equal(h.view(), 'loading');
    assert.deepEqual(h.list.calls[0].args[0], { status: null, origin: null, branch: null });
    h.list.calls[0].resolve([incident()]);
    await tick();
    assert.equal(h.view(), 'data');
  });

  test('vacío: lista sin incidencias (no una tabla vacía)', async () => {
    const h = harness();
    h.session.activate();
    h.list.calls[0].resolve([]);
    await tick();
    assert.equal(h.view(), 'empty');
  });

  test('error con reintento: el reintento vuelve a pedir el listado', async () => {
    const h = harness();
    h.session.activate();
    h.list.calls[0].reject(serviceError(NETWORK));
    await tick();
    assert.equal(h.view(), 'error');
    assert.deepEqual(h.state().list, { status: 'error', error: NETWORK });
    void h.session.reload();
    assert.equal(h.list.calls.length, 2);
    h.list.calls[1].resolve([incident()]);
    await tick();
    assert.equal(h.view(), 'data');
  });

  test('los filtros se envían a la API y la carga anterior se descarta', async () => {
    const h = harness();
    h.session.activate();
    const filters = { status: 'open', origin: 'branch', branch: 'remote' };
    h.session.setFilters(filters);
    assert.equal(h.list.calls[0].aborted, true);
    assert.deepEqual(h.list.calls[1].args[0], filters);
    assert.deepEqual(h.state().filters, filters);
    h.list.calls[1].resolve([]);
    await tick();
    assert.equal(h.view(), 'empty');
  });
});

describe('listado: cambio de estado optimista', () => {
  async function loaded(onStatusChanged) {
    const list = controllable();
    const change = controllable();
    const s = store(incidentBoardReducer, INITIAL_INCIDENT_BOARD_STATE);
    const session = createIncidentBoardSession(
      s.dispatch,
      { listIncidents: list.fn, changeIncidentStatus: change.fn },
      onStatusChanged
    );
    session.activate();
    list.calls[0].resolve([incident(), incident({ id: 'other', status: 'resolved' })]);
    await tick();
    return { session, list, change, ...s };
  }

  const statusOf = (h, id) => h.state().incidents.find((item) => item.id === id).status;

  test('la fila muestra el estado nuevo al instante y, tras el éxito, avisa al resumen', async () => {
    let summaryReloads = 0;
    const h = await loaded(() => (summaryReloads += 1));
    const target = h.state().incidents[0];
    const pending = h.session.changeStatus(target, 'in_progress');
    assert.equal(statusOf(h, target.id), 'in_progress');
    assert.equal(h.state().rows[target.id].status, 'saving');
    assert.deepEqual(h.change.calls[0].args.slice(0, 2), [target.id, 'in_progress']);
    h.change.calls[0].resolve(incident({ status: 'in_progress', updated_at: '2026-10-07T10:00:00Z' }));
    await pending;
    assert.equal(statusOf(h, target.id), 'in_progress');
    assert.equal(h.state().incidents[0].updated_at, '2026-10-07T10:00:00Z');
    assert.equal(h.state().rows[target.id], undefined);
    assert.equal(summaryReloads, 1);
  });

  test('si la API falla, el estado vuelve al anterior y se notifica en la fila', async () => {
    let summaryReloads = 0;
    const h = await loaded(() => (summaryReloads += 1));
    const target = h.state().incidents[0];
    const pending = h.session.changeStatus(target, 'discarded');
    assert.equal(statusOf(h, target.id), 'discarded');
    h.change.calls[0].reject(serviceError({ kind: 'invalid_transition' }));
    await pending;
    assert.equal(statusOf(h, target.id), 'open');
    assert.deepEqual(h.state().rows[target.id], {
      status: 'error',
      error: { kind: 'invalid_transition' },
      attempted: 'discarded',
    });
    assert.equal(summaryReloads, 0);
    h.session.clearRow(target.id);
    assert.equal(h.state().rows[target.id], undefined);
  });

  test('también se revierte si falla la red', async () => {
    const h = await loaded();
    const target = h.state().incidents[0];
    const pending = h.session.changeStatus(target, 'in_progress');
    h.change.calls[0].reject(serviceError(NETWORK));
    await pending;
    assert.equal(statusOf(h, target.id), 'open');
    assert.equal(h.state().rows[target.id].error.kind, 'network');
  });

  test('solo se piden transiciones del ciclo de vida; los estados finales no cambian', async () => {
    const h = await loaded();
    const [open, resolved] = h.state().incidents;
    await h.session.changeStatus(open, 'resolved');
    await h.session.changeStatus(open, 'open');
    await h.session.changeStatus(resolved, 'open');
    assert.equal(h.change.calls.length, 0);
    assert.equal(statusOf(h, open.id), 'open');
  });

  test('un cambio a la vez por incidencia', async () => {
    const h = await loaded();
    const target = h.state().incidents[0];
    void h.session.changeStatus(target, 'in_progress');
    void h.session.changeStatus(target, 'discarded');
    assert.equal(h.change.calls.length, 1);
  });

  test('un cambio confirmado durante una carga del listado fuerza otra carga', async () => {
    const h = await loaded();
    const target = h.state().incidents[0];
    void h.session.reload();
    const pending = h.session.changeStatus(target, 'in_progress');
    h.change.calls[0].resolve(incident({ status: 'in_progress' }));
    await pending;
    h.list.calls[1].resolve([incident()]);
    await tick();
    assert.equal(h.list.calls.length, 3, 'a stale list response triggers a new load');
  });
});

// ---------------------------------------------------------------------------

describe('resumen independiente del listado', () => {
  test('cargando → éxito, y una recarga mantiene el último resumen', async () => {
    const summary = controllable();
    const s = store(incidentSummaryReducer, INITIAL_INCIDENT_SUMMARY_STATE);
    const session = createIncidentSummarySession(s.dispatch, { getIncidentSummary: summary.fn });
    session.activate();
    assert.equal(s.state().load.status, 'loading');
    summary.calls[0].resolve({ total: 1 });
    await tick();
    assert.deepEqual(s.state(), { summary: { total: 1 }, load: { status: 'success' } });
    void session.reload();
    assert.equal(s.state().load.status, 'loading');
    assert.deepEqual(s.state().summary, { total: 1 });
  });

  test('si el resumen falla, el listado sigue funcionando', async () => {
    const summary = controllable();
    const list = controllable();
    const change = controllable();
    const summaryStore = store(incidentSummaryReducer, INITIAL_INCIDENT_SUMMARY_STATE);
    const boardStore = store(incidentBoardReducer, INITIAL_INCIDENT_BOARD_STATE);
    const summarySession = createIncidentSummarySession(summaryStore.dispatch, { getIncidentSummary: summary.fn });
    const boardSession = createIncidentBoardSession(
      boardStore.dispatch,
      { listIncidents: list.fn, changeIncidentStatus: change.fn },
      () => void summarySession.reload()
    );
    summarySession.activate();
    boardSession.activate();

    summary.calls[0].reject(serviceError({ kind: 'server_error' }));
    list.calls[0].resolve([incident()]);
    await tick();
    assert.deepEqual(summaryStore.state().load, { status: 'error', error: { kind: 'server_error' } });
    assert.equal(summaryStore.state().summary, null);
    assert.equal(boardView(boardStore.state()), 'data');

    // El listado sigue operativo: un cambio de estado funciona y pide otro resumen.
    const pending = boardSession.changeStatus(boardStore.state().incidents[0], 'in_progress');
    change.calls[0].resolve(incident({ status: 'in_progress' }));
    await pending;
    assert.equal(boardStore.state().incidents[0].status, 'in_progress');
    assert.equal(summary.calls.length, 2);
  });

  test('al desmontar se aborta y no se despacha nada', async () => {
    const summary = controllable();
    const s = store(incidentSummaryReducer, INITIAL_INCIDENT_SUMMARY_STATE);
    const session = createIncidentSummarySession(s.dispatch, { getIncidentSummary: summary.fn });
    session.activate();
    session.dispose();
    await tick();
    assert.equal(summary.calls[0].aborted, true);
    assert.deepEqual(s.actions.map((action) => action.type), ['summary_started']);
  });
});
