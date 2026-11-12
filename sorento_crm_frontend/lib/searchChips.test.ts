/** SEARCH-CHIPS slice 1 (UAC F2, F3, F9): the pure helpers behind the chips search box.
 * `splitPastedSearch` turns pasted text into chip values; `addSearchChips` appends, trims, dedupes
 * (case-insensitive) and caps at 200. Red first: `lib/searchChips.ts` does not exist yet. */
import { describe, expect, it } from 'vitest';
import { addSearchChips, splitPastedSearch } from './searchChips';

describe('splitPastedSearch (F3)', () => {
  it('splits on commas', () => {
    expect(splitPastedSearch('SO371334,SO371402, SO371500')).toEqual([
      'SO371334',
      'SO371402',
      'SO371500',
    ]);
  });

  it('splits on new lines (a column copied from a sheet)', () => {
    expect(splitPastedSearch('SO371334\nSO371402\r\nSO371500\n')).toEqual([
      'SO371334',
      'SO371402',
      'SO371500',
    ]);
  });

  it('splits on commas and new lines mixed, keeping spaces inside a piece', () => {
    expect(splitPastedSearch('Acme Trading, SO371334\nFakeco Holdings')).toEqual([
      'Acme Trading',
      'SO371334',
      'Fakeco Holdings',
    ]);
  });

  it('splits on spaces when every piece has a digit (document numbers)', () => {
    expect(splitPastedSearch('SO371334 SO371402')).toEqual(['SO371334', 'SO371402']);
    expect(splitPastedSearch('  SO371334   SO371402  DO88 ')).toEqual([
      'SO371334',
      'SO371402',
      'DO88',
    ]);
  });

  it('keeps a space-separated text without digits as ONE chip', () => {
    expect(splitPastedSearch('Acme Trading')).toEqual(['Acme Trading']);
  });

  it('keeps it as one chip when only SOME pieces have a digit', () => {
    expect(splitPastedSearch('Acme 88 Trading')).toEqual(['Acme 88 Trading']);
  });

  it('drops blank pieces', () => {
    expect(splitPastedSearch('SO1,, ,\n\nSO2,')).toEqual(['SO1', 'SO2']);
    expect(splitPastedSearch('   ')).toEqual([]);
    expect(splitPastedSearch('')).toEqual([]);
  });

  it('a single value is one chip', () => {
    expect(splitPastedSearch(' SO371334 ')).toEqual(['SO371334']);
  });
});

describe('addSearchChips (F2, F9)', () => {
  it('appends trimmed values in order', () => {
    expect(addSearchChips(['SO1'], ['  SO2 ', 'Acme Trading'])).toEqual({
      chips: ['SO1', 'SO2', 'Acme Trading'],
      capped: false,
    });
  });

  it('ignores blanks', () => {
    expect(addSearchChips(['SO1'], ['', '   '])).toEqual({ chips: ['SO1'], capped: false });
  });

  it('ignores case-insensitive duplicates, of existing chips and within the incoming list', () => {
    expect(addSearchChips(['SO1', 'Acme'], ['so1', 'ACME', 'SO2', 'so2'])).toEqual({
      chips: ['SO1', 'Acme', 'SO2'],
      capped: false,
    });
  });

  it('does not mutate the existing array', () => {
    const existing = ['SO1'];
    addSearchChips(existing, ['SO2']);
    expect(existing).toEqual(['SO1']);
  });

  it('caps at 200 by default, keeping the first 200, and says so', () => {
    const existing = Array.from({ length: 150 }, (_, i) => `A${i}`);
    const incoming = Array.from({ length: 100 }, (_, i) => `B${i}`);
    const out = addSearchChips(existing, incoming);
    expect(out.capped).toBe(true);
    expect(out.chips).toHaveLength(200);
    expect(out.chips.slice(0, 150)).toEqual(existing);
    expect(out.chips[150]).toBe('B0');
    expect(out.chips[199]).toBe('B49');
  });

  it('exactly 200 is not capped', () => {
    const incoming = Array.from({ length: 200 }, (_, i) => `V${i}`);
    expect(addSearchChips([], incoming)).toEqual({ chips: incoming, capped: false });
  });

  it('honours a custom cap', () => {
    expect(addSearchChips(['A'], ['B', 'C'], 2)).toEqual({ chips: ['A', 'B'], capped: true });
  });
});
