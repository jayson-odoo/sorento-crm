import { afterEach, describe, expect, it } from 'vitest';

import { getData, localStore, sessionStore, setData } from './storage';

const real = {
  local: Object.getOwnPropertyDescriptor(window, 'localStorage')!,
  session: Object.getOwnPropertyDescriptor(window, 'sessionStorage')!,
};

function block() {
  const deny = () => {
    throw new DOMException('The operation is insecure.', 'SecurityError');
  };
  Object.defineProperty(window, 'localStorage', { configurable: true, get: deny });
  Object.defineProperty(window, 'sessionStorage', { configurable: true, get: deny });
}

afterEach(() => {
  Object.defineProperty(window, 'localStorage', real.local);
  Object.defineProperty(window, 'sessionStorage', real.session);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('lib/storage', () => {
  it('reads and writes real storage when the browser allows it', () => {
    localStore.setItem('k', 'v');
    sessionStore.setItem('s', '1');
    expect(window.localStorage.getItem('k')).toBe('v');
    expect(localStore.getItem('k')).toBe('v');
    expect(localStore.keys()).toContain('k');
    expect(sessionStore.getItem('s')).toBe('1');
    localStore.removeItem('k');
    expect(localStore.getItem('k')).toBeNull();
  });

  it('never throws when Safari blocks storage, and keeps refused writes in memory', () => {
    block();
    expect(localStore.getItem('missing')).toBeNull();
    expect(() => localStore.setItem('pref', 'on')).not.toThrow();
    expect(localStore.getItem('pref')).toBe('on');
    expect(localStore.keys()).toContain('pref');
    localStore.removeItem('pref');
    expect(localStore.getItem('pref')).toBeNull();
    expect(() => sessionStore.setItem('x', '1')).not.toThrow();
    setData('json', { a: 1 });
    expect(getData('json')).toEqual({ a: 1 });
  });

  it('a value stored while storage worked does not resurface once it refuses', () => {
    localStore.setItem('dismissed', '1');
    block();
    expect(localStore.getItem('dismissed')).toBeNull();
  });
});
