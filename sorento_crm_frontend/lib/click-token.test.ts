import { afterEach, describe, expect, it, vi } from 'vitest';
import { clickToken } from './click-token';

describe('clickToken', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('works where crypto.randomUUID is missing (plain-http host)', () => {
    vi.stubGlobal('crypto', {});
    const a = clickToken();
    const b = clickToken();
    expect(a).toMatch(/^t-/);
    expect(a).not.toBe(b);
  });
});
