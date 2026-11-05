import { afterEach, describe, expect, it, vi } from 'vitest';
import { clickToken } from './click-token';

describe('clickToken', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('works where crypto.randomUUID is missing (plain-http host)', () => {
    vi.stubGlobal('crypto', {});
    const a = clickToken();
    const b = clickToken();
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(a).not.toBe(b);
  });
});
