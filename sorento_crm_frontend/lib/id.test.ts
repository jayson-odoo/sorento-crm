import { afterEach, describe, expect, it, vi } from 'vitest';
import { randomId } from './id';

const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('randomId', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('uses crypto.randomUUID when the context offers it', () => {
    const native = vi.fn(() => '11111111-2222-4333-8444-555555555555');
    vi.stubGlobal('crypto', { randomUUID: native, getRandomValues: crypto.getRandomValues.bind(crypto) });
    expect(randomId()).toBe('11111111-2222-4333-8444-555555555555');
    expect(native).toHaveBeenCalledOnce();
  });

  it('returns a valid v4 where crypto.randomUUID is missing (plain-http origin)', () => {
    const real = globalThis.crypto;
    vi.stubGlobal('crypto', { getRandomValues: real.getRandomValues.bind(real) });
    const a = randomId();
    const b = randomId();
    expect(a).toMatch(V4);
    expect(b).toMatch(V4);
    expect(a).not.toBe(b);
  });

  it('still returns a v4 with no crypto at all', () => {
    vi.stubGlobal('crypto', undefined);
    const a = randomId();
    expect(a).toMatch(V4);
    expect(a).not.toBe(randomId());
  });
});
