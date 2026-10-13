// hooks/use-auth-session.ts: las piezas sin React del estado de la sesión (el
// reducer de la validación, el estado derivado que usa el guard, sus textos y el
// controlador que valida cada token con GET /auth/me). El hook en sí necesita React.

import { ApiAbortError } from '@/lib/api-client';
import {
  INITIAL_VALIDATION_STATE,
  createAuthSessionController,
  deriveSessionStatus,
  sessionErrorCopy,
  validationReducer,
  type ValidationAction,
  type ValidationState,
} from '@/hooks/use-auth-session';
import { AuthServiceError } from '@/services/auth.service';
import type { AuthUiError, CurrentUser } from '@/types/auth';

const USER: CurrentUser = {
  id: 'u-1',
  email: 'ana@example.invalid',
  role: 'user',
  is_active: true,
  created_at: '2026-10-01T10:00:00Z',
  profile: null,
};
const NETWORK: AuthUiError = { kind: 'network' };

describe('validationReducer', () => {
  test('a validated token becomes the authenticated session', () => {
    expect(validationReducer(INITIAL_VALIDATION_STATE, { type: 'validated', token: 'a', user: USER })).toEqual({
      status: 'authenticated',
      token: 'a',
      user: USER,
    });
  });

  test('retrying the same token after an error keeps the error visible while it retries', () => {
    const failed = validationReducer(INITIAL_VALIDATION_STATE, { type: 'failed', token: 'a', error: NETWORK });
    expect(validationReducer(failed, { type: 'validation_started', token: 'a' })).toEqual({
      status: 'retrying',
      token: 'a',
      error: NETWORK,
    });
  });

  test('a validation started for another token does not change the state', () => {
    // La primera validación de un token ya se ve como `checking` (estado derivado).
    const failed: ValidationState = { status: 'error', token: 'a', error: NETWORK };
    expect(validationReducer(failed, { type: 'validation_started', token: 'b' })).toBe(failed);
    expect(validationReducer(INITIAL_VALIDATION_STATE, { type: 'validation_started', token: 'a' })).toBe(
      INITIAL_VALIDATION_STATE
    );
  });
});

describe('deriveSessionStatus', () => {
  test('a validated token is an authenticated session', () => {
    expect(deriveSessionStatus('a', { status: 'authenticated', token: 'a', user: USER })).toEqual({
      status: 'authenticated',
      user: USER,
    });
  });

  test('before reading the token (server, hydration) it is initializing; without a token it is anonymous', () => {
    expect(deriveSessionStatus(undefined, INITIAL_VALIDATION_STATE)).toEqual({ status: 'initializing' });
    expect(deriveSessionStatus(null, { status: 'authenticated', token: 'a', user: USER })).toEqual({ status: 'anonymous' });
  });

  test('a validation of a previous token never authenticates the current one', () => {
    // Tras un nuevo login, el usuario validado del token anterior no vale: se vuelve a comprobar.
    expect(deriveSessionStatus('b', { status: 'authenticated', token: 'a', user: USER })).toEqual({ status: 'checking' });
    expect(deriveSessionStatus('b', { status: 'error', token: 'a', error: NETWORK })).toEqual({ status: 'checking' });
  });

  test('an error or a retry of the current token is shown as such', () => {
    expect(deriveSessionStatus('a', { status: 'error', token: 'a', error: NETWORK })).toEqual({ status: 'error', error: NETWORK });
    expect(deriveSessionStatus('a', { status: 'retrying', token: 'a', error: NETWORK })).toEqual({
      status: 'retrying',
      error: NETWORK,
    });
  });
});

describe('sessionErrorCopy', () => {
  test.each(['network', 'timeout', 'server_error', 'config', 'unexpected_response'] as const)(
    '%s has its own explanation',
    (kind) => {
      const copy = sessionErrorCopy({ kind });
      expect(copy.title).toBe('No se pudo comprobar la sesión');
      expect(copy.body).not.toBe(sessionErrorCopy({ kind: 'session_expired' }).body);
    }
  );

  test('any other error falls back to a neutral text with no technical details', () => {
    const { body } = sessionErrorCopy({ kind: 'invalid_credentials' });
    expect(body).toBe('Inténtalo de nuevo o cierra la sesión y vuelve a entrar.');
    expect(body).not.toMatch(/NEXT_PUBLIC|\d{3}|services\/api/);
  });
});

describe('createAuthSessionController', () => {
  function controllerWith(getCurrentUser: () => Promise<CurrentUser>) {
    const actions: ValidationAction[] = [];
    const calls = jest.fn(getCurrentUser);
    const controller = createAuthSessionController((action) => actions.push(action), { getCurrentUser: calls });
    controller.activate();
    return { controller, actions, calls };
  }

  test('validates a token once and reports the user', async () => {
    const { controller, actions, calls } = controllerWith(async () => USER);

    await controller.validate('a');
    await controller.validate('a');

    expect(calls).toHaveBeenCalledTimes(1);
    expect(actions).toEqual([{ type: 'validated', token: 'a', user: USER }]);
  });

  test('a network failure is reported so the guard can offer «Reintentar»', async () => {
    const { controller, actions } = controllerWith(async () => {
      throw new AuthServiceError(NETWORK);
    });

    await controller.validate('a');

    expect(actions).toEqual([{ type: 'failed', token: 'a', error: NETWORK }]);
  });

  test('an expired session (401) is not reported: the token is already gone and the state becomes anonymous', async () => {
    const { controller, actions } = controllerWith(async () => {
      throw new AuthServiceError({ kind: 'session_expired' });
    });

    await controller.validate('a');

    expect(actions).toEqual([]);
  });

  test('the result of an older token is ignored once a newer one is being validated', async () => {
    let resolveFirst: (user: CurrentUser) => void = () => undefined;
    const firstResponse = new Promise<CurrentUser>((resolve) => (resolveFirst = resolve));
    let call = 0;
    const { controller, actions } = controllerWith(() => (++call === 1 ? firstResponse : Promise.resolve(USER)));

    const first = controller.validate('a');
    await controller.validate('b');
    resolveFirst(USER);
    await first;

    expect(actions).toEqual([{ type: 'validated', token: 'b', user: USER }]);
  });

  test('after dispose (unmounted view) it neither calls the API nor dispatches', async () => {
    const { controller, actions, calls } = controllerWith(async () => USER);
    controller.dispose();

    await controller.validate('a');

    expect(calls).not.toHaveBeenCalled();
    expect(actions).toEqual([]);
  });

  test('a cancelled request (ApiAbortError) is silent', async () => {
    const { controller, actions } = controllerWith(async () => {
      throw new ApiAbortError();
    });

    await controller.validate('a');

    expect(actions).toEqual([]);
  });
});
