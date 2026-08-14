import { beforeEach, describe, expect, it } from 'vitest';

import {
  MAX_PICKS,
  clearPicks,
  readPicks,
  togglePick,
  writePicks,
} from './cataloguePicks';

describe('catalogue picks', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('round trips what was ticked', () => {
    writePicks(['a', 'b']);
    expect(readPicks()).toEqual(['a', 'b']);
  });

  it('keeps each product once, however many times it was ticked', () => {
    writePicks(['a', 'b', 'a']);
    expect(readPicks()).toEqual(['a', 'b']);
  });

  it('forgets picks left from a previous day', () => {
    // A tab open since yesterday is a forgotten tab, not an intent to buy.
    const yesterday = Date.now() - 25 * 60 * 60 * 1000;
    writePicks(['a'], yesterday);
    expect(readPicks()).toEqual([]);
  });

  it('caps how many can be carried', () => {
    writePicks(Array.from({ length: MAX_PICKS + 10 }, (_, index) => `p${index}`));
    expect(readPicks()).toHaveLength(MAX_PICKS);
  });

  it('survives junk in its key rather than crashing the catalogue', () => {
    window.localStorage.setItem('dealer-kit:catalogue-picks', 'not json');
    expect(readPicks()).toEqual([]);
  });

  it('clears', () => {
    writePicks(['a']);
    clearPicks();
    expect(readPicks()).toEqual([]);
  });

  it('toggles on and off without reordering the rest', () => {
    expect(togglePick(['a', 'b'], 'c')).toEqual(['a', 'b', 'c']);
    expect(togglePick(['a', 'b', 'c'], 'b')).toEqual(['a', 'c']);
  });
});
