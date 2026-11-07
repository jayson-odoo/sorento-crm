/**
 * The ONE way the app touches Web Storage (CLIENT-ERROR-REPORT).
 *
 * Safari with website storage blocked ("Block all cookies", some private modes)
 * throws SecurityError on ANY access, the bare `window.localStorage` reference
 * included. A single unguarded read in a provider or the protected shell took down
 * every page with "The app could not start". Every call here is guarded; a write the
 * browser refuses lives in memory for the rest of the page's life, so a preference
 * set this session still reads back while storage stays blocked.
 *
 * `components/rootProviders.safariGuard.test.ts` fails the build on any
 * `localStorage` / `sessionStorage` reference outside this file. The one exception
 * is `lib/chunk-load-error.ts`: its reload guard must know whether storage is REAL
 * (a memory fallback would forget the guard across the reload and loop).
 */

type Kind = 'local' | 'session';

export interface SafeStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
  /** Every key currently stored. */
  keys(): string[];
}

function backing(kind: Kind): Storage | null {
  if (typeof window === 'undefined') return null;
  return kind === 'local' ? window.localStorage : window.sessionStorage;
}

function makeStore(kind: Kind): SafeStorage {
  const memory = new Map<string, string>();
  return {
    getItem(key) {
      try {
        const store = backing(kind);
        if (store) return store.getItem(key);
      } catch {
        // blocked: fall through to memory
      }
      return memory.has(key) ? (memory.get(key) as string) : null;
    },
    setItem(key, value) {
      try {
        const store = backing(kind);
        if (store) {
          store.setItem(key, value);
          // Memory holds only what the browser refused, so a value stored while
          // storage worked never resurfaces after storage starts refusing.
          memory.delete(key);
          return;
        }
      } catch {
        // blocked or full: fall through
      }
      memory.set(key, value);
    },
    removeItem(key) {
      memory.delete(key);
      try {
        backing(kind)?.removeItem(key);
      } catch {
        // blocked
      }
    },
    keys() {
      try {
        const store = backing(kind);
        if (store) return Object.keys(store);
      } catch {
        // blocked
      }
      return [...memory.keys()];
    },
  };
}

export const localStore: SafeStorage = makeStore('local');
export const sessionStore: SafeStorage = makeStore('session');

/** JSON read from localStorage; undefined when absent, unreadable or not JSON. */
const getData = (key: string): unknown | undefined => {
  const data = localStore.getItem(key);
  if (!data) return undefined;
  try {
    return JSON.parse(data);
  } catch {
    return undefined;
  }
};

/** JSON write to localStorage. */
const setData = (key: string, value: unknown): void => {
  localStore.setItem(key, JSON.stringify(value));
};

export { getData, setData };
