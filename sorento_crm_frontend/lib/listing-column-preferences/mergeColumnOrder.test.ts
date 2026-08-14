import { describe, expect, it } from 'vitest';

import { mergeColumnOrderWithLeafColumns } from './mergeColumnOrder';

describe('mergeColumnOrderWithLeafColumns', () => {
  it('keeps the saved order for columns the user has already arranged', () => {
    expect(mergeColumnOrderWithLeafColumns(['c', 'a', 'b'], ['a', 'b', 'c'])).toEqual([
      'c',
      'a',
      'b',
    ]);
  });

  it('drops ids that no longer exist as columns', () => {
    expect(mergeColumnOrderWithLeafColumns(['a', 'gone', 'b'], ['a', 'b'])).toEqual(['a', 'b']);
  });

  it('places a newly added column where the code defines it, not at the far right', () => {
    // The saved order predates `outbound`; the code defines it right after `last_name`.
    const saved = ['phone', 'first_name', 'last_name', 'created_at', 'updated_at', 'actions'];
    const leaves = [
      'phone',
      'first_name',
      'last_name',
      'outbound',
      'created_at',
      'updated_at',
      'actions',
    ];

    expect(mergeColumnOrderWithLeafColumns(saved, leaves)).toEqual([
      'phone',
      'first_name',
      'last_name',
      'outbound',
      'created_at',
      'updated_at',
      'actions',
    ]);
  });

  it('puts a new leading column first when nothing precedes it', () => {
    expect(mergeColumnOrderWithLeafColumns(['b', 'c'], ['a', 'b', 'c'])).toEqual(['a', 'b', 'c']);
  });

  it('keeps consecutive new columns in definition order', () => {
    expect(mergeColumnOrderWithLeafColumns(['a', 'd'], ['a', 'b', 'c', 'd'])).toEqual([
      'a',
      'b',
      'c',
      'd',
    ]);
  });

  it('anchors a new column to its neighbour even when the user moved that neighbour', () => {
    // User dragged `c` to the front; `b` is new and defined right after `a`.
    expect(mergeColumnOrderWithLeafColumns(['c', 'a'], ['a', 'b', 'c'])).toEqual(['c', 'a', 'b']);
  });

  it('returns the definition order when nothing was ever saved', () => {
    expect(mergeColumnOrderWithLeafColumns([], ['a', 'b', 'c'])).toEqual(['a', 'b', 'c']);
  });
});
