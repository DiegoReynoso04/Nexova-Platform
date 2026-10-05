// AUTH-02 — estado de la sesión, de los formularios de login/registro y del
// perfil (hooks/use-auth-session.ts, use-auth-form.ts, use-profile.ts), sin
// montar React. La unión con React se valida con tsc/lint/build y en el navegador.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  INITIAL_VALIDATION_STATE,
  createAuthSessionController,
  deriveSessionStatus,
  validationReducer,
} from '../hooks/use-auth-session.ts';
import { INITIAL_AUTH_FORM_STATE, authFormReducer, createAuthFormController } from '../hooks/use-auth-form.ts';
import { INITIAL_PROFILE_STATE, createProfileController, profileReducer } from '../hooks/use-profile.ts';
import { ApiAbortError } from '../lib/api-client.ts';
import { AuthServiceError } from '../services/auth.service.ts';

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

function recorder(reducer, initial) {
  let state = initial;
  const actions = [];
  return {
    dispatch: (action) => {
      actions.push(action);
      state = reducer(state, action);
    },
    actions,
    state: () => state,
  };
}

const USER = { id: 'u-1', email: 'ana@nexova.test', role: 'user', is_active: true, created_at: 'x', profile: null };

describe('sesión: estado derivado', () => {
  test('sin leer el token (servidor/hidratación), sin token, validando, válida y error', () => {
    assert.deepEqual(deriveSessionStatus(undefined, INITIAL_VALIDATION_STATE), { status: 'initializing' });
    assert.deepEqual(deriveSessionStatus(null, INITIAL_VALIDATION_STATE), { status: 'anonymous' });
    assert.deepEqual(deriveSessionStatus('t1', INITIAL_VALIDATION_STATE), { status: 'checking' });
    const valid = validationReducer(INITIAL_VALIDATION_STATE, { type: 'validated', token: 't1', user: USER });
    assert.deepEqual(deriveSessionStatus('t1', valid), { status: 'authenticated', user: USER });
    const failed = validationReducer(valid, { type: 'failed', token: 't1', error: { kind: 'network' } });
    assert.deepEqual(deriveSessionStatus('t1', failed), { status: 'error', error: { kind: 'network' } });
  });

  test('una validación de otro token no vale para el token actual', () => {
    const valid = validationReducer(INITIAL_VALIDATION_STATE, { type: 'validated', token: 't1', user: USER });
    assert.deepEqual(deriveSessionStatus('t2', valid), { status: 'checking' });
    // Tras un logout (sin token) nunca se considera autenticado.
    assert.deepEqual(deriveSessionStatus(null, valid), { status: 'anonymous' });
  });
});

describe('sesión: controlador', () => {
  function harness() {
    const me = controllable();
    const r = recorder(validationReducer, INITIAL_VALIDATION_STATE);
    const controller = createAuthSessionController(r.dispatch, { getCurrentUser: me.fn });
    controller.activate();
    return { controller, me, ...r };
  }

  test('valida cada token una sola vez con GET /auth/me', async () => {
    const h = harness();
    void h.controller.validate('t1');
    void h.controller.validate('t1');
    assert.equal(h.me.calls.length, 1);
    h.me.calls[0].resolve(USER);
    await tick();
    assert.deepEqual(h.state(), { status: 'authenticated', token: 't1', user: USER });
    void h.controller.validate('t1');
    assert.equal(h.me.calls.length, 1);
  });

  test('un token nuevo aborta la validación anterior y solo cuenta la última', async () => {
    const h = harness();
    void h.controller.validate('t1');
    void h.controller.validate('t2');
    assert.equal(h.me.calls[0].aborted, true);
    h.me.calls[1].resolve(USER);
    await tick();
    assert.equal(h.state().token, 't2');
  });

  test('401 (session_expired) no despacha nada: el token ya se borró y la sesión pasa a anónima', async () => {
    const h = harness();
    void h.controller.validate('t1');
    h.me.calls[0].reject(new AuthServiceError({ kind: 'session_expired' }));
    await tick();
    assert.deepEqual(h.actions, []);
  });

  test('error de red → estado de error y reintento forzado', async () => {
    const h = harness();
    void h.controller.validate('t1');
    h.me.calls[0].reject(new AuthServiceError({ kind: 'network' }));
    await tick();
    assert.deepEqual(h.state(), { status: 'error', token: 't1', error: { kind: 'network' } });
    void h.controller.validate('t1', true);
    assert.equal(h.me.calls.length, 2);
  });

  test('forget (logout) permite volver a validar el mismo token y dispose cancela', async () => {
    const h = harness();
    void h.controller.validate('t1');
    h.controller.forget();
    assert.equal(h.me.calls[0].aborted, true);
    void h.controller.validate('t1');
    assert.equal(h.me.calls.length, 2);
    h.controller.dispose();
    assert.equal(h.me.calls[1].aborted, true);
    await tick();
    assert.deepEqual(h.actions, []);
  });
});

describe('formularios de login y registro', () => {
  function harness() {
    const op = controllable();
    const r = recorder(authFormReducer, INITIAL_AUTH_FORM_STATE);
    const controller = createAuthFormController(r.dispatch, op.fn);
    controller.activate();
    return { controller, op, ...r };
  }

  test('éxito → success y resuelve true (la vista redirige)', async () => {
    const h = harness();
    const result = h.controller.submit({ email: 'a', password: 'b' });
    assert.deepEqual(h.state(), { status: 'submitting' });
    h.op.calls[0].resolve();
    assert.equal(await result, true);
    assert.deepEqual(h.state(), { status: 'success' });
  });

  test('no permite envíos duplicados mientras hay uno en curso', async () => {
    const h = harness();
    void h.controller.submit({});
    assert.equal(await h.controller.submit({}), false);
    assert.equal(h.op.calls.length, 1);
  });

  test('error del servicio → estado de error con su AuthUiError', async () => {
    const h = harness();
    const result = h.controller.submit({});
    h.op.calls[0].reject(new AuthServiceError({ kind: 'invalid_credentials' }));
    assert.equal(await result, false);
    assert.deepEqual(h.state(), { status: 'error', error: { kind: 'invalid_credentials' } });
  });

  test('al desmontar se aborta y no se despacha nada más', async () => {
    const h = harness();
    const result = h.controller.submit({});
    h.controller.dispose();
    assert.equal(h.op.calls[0].aborted, true);
    assert.equal(await result, false);
    assert.deepEqual(h.actions, [{ type: 'submit_started' }]);
  });
});

describe('perfil', () => {
  function harness() {
    const me = controllable();
    const update = controllable();
    const r = recorder(profileReducer, INITIAL_PROFILE_STATE);
    const controller = createProfileController(r.dispatch, { getCurrentUser: me.fn, updateProfile: update.fn });
    return { controller, me, update, ...r };
  }

  const PROFILE = { id: 'p-1', user_id: 'u-1', name: 'Ana', phone: null, address: null };

  test('al activarse carga GET /auth/me', async () => {
    const h = harness();
    h.controller.activate();
    assert.equal(h.me.calls.length, 1);
    h.me.calls[0].resolve({ ...USER, profile: PROFILE });
    await tick();
    assert.deepEqual(h.state().load, { status: 'success', user: { ...USER, profile: PROFILE } });
  });

  test('guardar reemplaza el perfil mostrado por el de la respuesta', async () => {
    const h = harness();
    h.controller.activate();
    h.me.calls[0].resolve({ ...USER, profile: PROFILE });
    await tick();
    const values = { name: 'Ana Pérez', phone: '600', address: '' };
    void h.controller.save(values);
    assert.deepEqual(h.update.calls[0].args[0], values);
    assert.deepEqual(h.state().save, { status: 'saving' });
    const saved = { ...PROFILE, name: 'Ana Pérez', phone: '600' };
    h.update.calls[0].resolve(saved);
    await tick();
    assert.deepEqual(h.state(), { load: { status: 'success', user: { ...USER, profile: saved } }, save: { status: 'success' } });
  });

  test('error al guardar no borra los datos mostrados', async () => {
    const h = harness();
    h.controller.activate();
    h.me.calls[0].resolve({ ...USER, profile: PROFILE });
    await tick();
    void h.controller.save({ name: '', phone: '', address: '' });
    const error = { kind: 'validation', source: 'api', errors: [{ field: 'phone', message: 'too long' }] };
    h.update.calls[0].reject(new AuthServiceError(error));
    await tick();
    assert.deepEqual(h.state().save, { status: 'error', error });
    assert.equal(h.state().load.status, 'success');
  });

  test('error al cargar y recarga', async () => {
    const h = harness();
    h.controller.activate();
    h.me.calls[0].reject(new AuthServiceError({ kind: 'server_error' }));
    await tick();
    assert.deepEqual(h.state().load, { status: 'error', error: { kind: 'server_error' } });
    void h.controller.reload();
    assert.equal(h.me.calls.length, 2);
  });
});
