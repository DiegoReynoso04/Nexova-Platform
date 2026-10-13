// lib/auth-token.ts: almacén del JWT en localStorage y suscripción para el guard.
// El módulo guarda sus suscriptores en una variable de módulo: cada test lo
// carga de nuevo con jest.isolateModules para empezar sin suscriptores.

import { MemoryStorage, createFakeWindow, installWindow, uninstallWindow, type FakeWindow } from '../support/fake-browser';

type AuthTokenModule = typeof import('@/lib/auth-token');

function loadAuthToken(): AuthTokenModule {
  let loaded: AuthTokenModule | undefined;
  jest.isolateModules(() => {
    loaded = jest.requireActual<AuthTokenModule>('@/lib/auth-token');
  });
  if (loaded === undefined) throw new Error('lib/auth-token no se cargó');
  return loaded;
}

/** Storage cuyas operaciones lanzan, como en modo privado o con el almacenamiento bloqueado. */
class ThrowingStorage extends MemoryStorage {
  getItem(): string | null {
    throw new Error('SecurityError');
  }

  setItem(): void {
    throw new Error('QuotaExceededError');
  }

  removeItem(): void {
    throw new Error('SecurityError');
  }
}

let fakeWindow: FakeWindow;
let tokens: AuthTokenModule;

beforeEach(() => {
  fakeWindow = createFakeWindow();
  installWindow(fakeWindow);
  tokens = loadAuthToken();
});

afterEach(() => {
  uninstallWindow();
});

describe('readAuthToken', () => {
  test('returns the saved token', () => {
    fakeWindow.localStorage.setItem(tokens.AUTH_TOKEN_STORAGE_KEY, 'jwt-guardado');
    expect(tokens.readAuthToken()).toBe('jwt-guardado');
  });

  test('a token made only of spaces counts as no session', () => {
    fakeWindow.localStorage.setItem(tokens.AUTH_TOKEN_STORAGE_KEY, '   ');
    expect(tokens.readAuthToken()).toBeNull();
  });

  test('a storage that throws counts as no session instead of breaking the page', () => {
    installWindow(createFakeWindow(new ThrowingStorage()));
    expect(tokens.readAuthToken()).toBeNull();
  });

  test('an inaccessible localStorage property counts as no session', () => {
    installWindow({
      get localStorage(): Storage {
        throw new Error('SecurityError');
      },
    });
    expect(tokens.readAuthToken()).toBeNull();
  });

  test('on the server (no window) there is no session', () => {
    uninstallWindow();
    expect(tokens.readAuthToken()).toBeNull();
  });
});

describe('saveAuthToken', () => {
  test('stores the token and notifies subscribers once', () => {
    const listener = jest.fn();
    tokens.subscribeAuthToken(listener);

    tokens.saveAuthToken('jwt-nuevo');

    expect(fakeWindow.localStorage.getItem(tokens.AUTH_TOKEN_STORAGE_KEY)).toBe('jwt-nuevo');
    expect(listener).toHaveBeenCalledTimes(1);
  });

  test('a blank token is neither stored nor notified', () => {
    const listener = jest.fn();
    tokens.subscribeAuthToken(listener);

    tokens.saveAuthToken('  ');

    expect(fakeWindow.localStorage.length).toBe(0);
    expect(listener).not.toHaveBeenCalled();
  });

  test('if setItem fails, subscribers are still notified so they re-read the (missing) session', () => {
    installWindow(createFakeWindow(new ThrowingStorage()));
    const listener = jest.fn();
    tokens.subscribeAuthToken(listener);

    expect(() => tokens.saveAuthToken('jwt-nuevo')).not.toThrow();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(tokens.readAuthToken()).toBeNull();
  });
});

describe('clearAuthToken', () => {
  test('removes the token and notifies subscribers', () => {
    fakeWindow.localStorage.setItem(tokens.AUTH_TOKEN_STORAGE_KEY, 'jwt-guardado');
    const listener = jest.fn();
    tokens.subscribeAuthToken(listener);

    tokens.clearAuthToken();

    expect(tokens.readAuthToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  test('a storage that throws on remove does not break logout and still notifies', () => {
    installWindow(createFakeWindow(new ThrowingStorage()));
    const listener = jest.fn();
    tokens.subscribeAuthToken(listener);

    expect(() => tokens.clearAuthToken()).not.toThrow();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('subscribeAuthToken', () => {
  test('reacts to changes of the token made in another tab, including a full clear', () => {
    const listener = jest.fn();
    tokens.subscribeAuthToken(listener);

    fakeWindow.dispatchStorage(tokens.AUTH_TOKEN_STORAGE_KEY);
    // `key: null` es `localStorage.clear()` en otra pestaña: también borra el token.
    fakeWindow.dispatchStorage(null);

    expect(listener).toHaveBeenCalledTimes(2);
  });

  test('ignores storage events for other keys', () => {
    const listener = jest.fn();
    tokens.subscribeAuthToken(listener);

    fakeWindow.dispatchStorage('otra.clave');

    expect(listener).not.toHaveBeenCalled();
  });

  test('unsubscribing stops both local and cross-tab notifications', () => {
    const listener = jest.fn();
    const unsubscribe = tokens.subscribeAuthToken(listener);
    expect(fakeWindow.storageListenerCount).toBe(1);

    unsubscribe();
    tokens.saveAuthToken('jwt-nuevo');

    expect(fakeWindow.storageListenerCount).toBe(0);
    expect(listener).not.toHaveBeenCalled();
  });
});
