/**
 * FILTER-MULTISELECT: one dropdown filter, several values. The URL and the list's filter map carry
 * them comma-joined in one param; a single value from an old link reads as a one-value list.
 */
import { describe, it, expect } from 'vitest';
import { joinMulti, multiChipLabel, splitMulti } from './multiValue';

describe('splitMulti', () => {
  it.each([
    [undefined, []],
    [null, []],
    ['', []],
    [' , ', []],
    ['draft', ['draft']],
    ['draft,submitted', ['draft', 'submitted']],
    [' draft , submitted,draft ', ['draft', 'submitted']],
  ])('%j -> %j', (raw, expected) => {
    expect(splitMulti(raw as string | null | undefined)).toEqual(expected);
  });
});

describe('joinMulti', () => {
  it('joins with a comma and drops blanks and repeats', () => {
    expect(joinMulti(['draft', '', 'submitted', 'draft'])).toBe('draft,submitted');
  });
  it('is empty for no values, so the filter is absent', () => {
    expect(joinMulti([])).toBe('');
  });
  it('round-trips through splitMulti', () => {
    expect(splitMulti(joinMulti(['a', 'b']))).toEqual(['a', 'b']);
  });
});

describe('multiChipLabel', () => {
  it('names one value', () => {
    expect(multiChipLabel('Status', ['Draft'])).toBe('Status: Draft');
  });
  it('names two values', () => {
    expect(multiChipLabel('Status', ['Draft', 'Submitted'])).toBe('Status: Draft, Submitted');
  });
  it('names the first two and counts the rest', () => {
    expect(multiChipLabel('Status', ['Draft', 'Submitted', 'Approved', 'Void'])).toBe(
      'Status: Draft, Submitted +2',
    );
  });
});
