// `window` simulado para los tests de Jest (entorno `node`, sin jsdom): un
// Storage en memoria y los listeners de `addEventListener`/`removeEventListener`.

type StorageListener = (event: StorageEvent) => void;

export class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

export interface FakeWindow {
  localStorage: Storage;
  addEventListener(type: 'storage', listener: StorageListener): void;
  removeEventListener(type: 'storage', listener: StorageListener): void;
  /** Simula el evento `storage` que el navegador lanza cuando otra pestaña cambia el almacenamiento. */
  dispatchStorage(key: string | null): void;
  readonly storageListenerCount: number;
}

export function createFakeWindow(storage: Storage = new MemoryStorage()): FakeWindow {
  const listeners = new Set<StorageListener>();
  return {
    localStorage: storage,
    addEventListener: (_type, listener) => listeners.add(listener),
    removeEventListener: (_type, listener) => listeners.delete(listener),
    dispatchStorage(key) {
      for (const listener of listeners) listener({ key } as StorageEvent);
    },
    get storageListenerCount() {
      return listeners.size;
    },
  };
}

const globals = globalThis as { window?: unknown };

/** Instala `window` en el entorno global; `uninstallWindow` lo quita (el servidor no tiene `window`). */
export function installWindow(fake: FakeWindow | object): void {
  globals.window = fake;
}

export function uninstallWindow(): void {
  delete globals.window;
}
