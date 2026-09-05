/**
 * `ensureFontsLoaded` (price-tag-r4 S1): a rejecting face is reported back
 * rather than swallowed, and a resolving one loads exactly once.
 *
 * `FontFace` does not exist in jsdom, so every test installs a stub that
 * resolves or rejects on command - the same shape a real signed-but-CORS-
 * blocked URL produces (a `load()` promise that rejects).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { _resetLoadedFonts, ensureFontsLoaded, type TagFont } from './fonts';

class FakeFontFace {
  static behaviour: 'resolve' | 'reject' = 'resolve';
  family: string;
  source: string;
  constructor(family: string, source: string) {
    this.family = family;
    this.source = source;
  }
  load(): Promise<FakeFontFace> {
    return FakeFontFace.behaviour === 'resolve'
      ? Promise.resolve(this)
      : Promise.reject(new Error('font load failed'));
  }
}

function font(overrides: Partial<TagFont> = {}): TagFont {
  return { name: 'ZZT Brand', family: 'ZZT Brand', url: '/api/v1/public/dealer-kit/fonts/f1', ...overrides };
}

describe('ensureFontsLoaded', () => {
  const originalFontFace = (globalThis as { FontFace?: unknown }).FontFace;
  const added: unknown[] = [];

  beforeEach(() => {
    _resetLoadedFonts();
    added.length = 0;
    FakeFontFace.behaviour = 'resolve';
    (globalThis as { FontFace?: unknown }).FontFace = FakeFontFace;
    (document as unknown as { fonts: { add: (f: unknown) => void; ready: Promise<void> } }).fonts = {
      add: (f: unknown) => added.push(f),
      ready: Promise.resolve(),
    };
  });

  afterEach(() => {
    (globalThis as { FontFace?: unknown }).FontFace = originalFontFace;
    vi.restoreAllMocks();
  });

  it('reports a rejecting face in `failed`, by family', async () => {
    FakeFontFace.behaviour = 'reject';

    const result = await ensureFontsLoaded([font({ family: 'ZZT Broken' })]);

    expect(result.failed).toEqual(['ZZT Broken']);
    expect(added).toHaveLength(0);
  });

  it('adds a resolving face once and reports no failure', async () => {
    const result = await ensureFontsLoaded([font()]);

    expect(result.failed).toEqual([]);
    expect(added).toHaveLength(1);
  });

  it('is idempotent: a second call with the same family+url loads nothing again', async () => {
    await ensureFontsLoaded([font()]);
    added.length = 0;

    const result = await ensureFontsLoaded([font()]);

    expect(added).toHaveLength(0);
    expect(result.failed).toEqual([]);
  });

  it('a font that failed before is eligible to retry on the next call', async () => {
    FakeFontFace.behaviour = 'reject';
    await ensureFontsLoaded([font({ family: 'ZZT Retry' })]);

    FakeFontFace.behaviour = 'resolve';
    const result = await ensureFontsLoaded([font({ family: 'ZZT Retry' })]);

    expect(result.failed).toEqual([]);
    expect(added).toHaveLength(1);
  });

  it('skips a font with no url or no family, without failing', async () => {
    const result = await ensureFontsLoaded([
      font({ url: '' }),
      font({ family: '', name: '' }),
    ]);

    expect(result.failed).toEqual([]);
    expect(added).toHaveLength(0);
  });
});
