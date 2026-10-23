/**
 * SO-LINE-NUMBERS AC-7: a line left out of a Confirm is named by the number the customer's
 * sales order carries, never the planning order's own.
 */
import { describe, expect, it } from 'vitest';
import type { BoardContribution } from '../types/fulfilmentPlanning.types';
import { unpostableNotices } from './unpostableNotices';

function lineOf(over: Partial<BoardContribution>) {
  return {
    reason: 'no_mirror' as const,
    contribution: {
      key: 'k1',
      so_number: 'SO401624',
      line_no: 11,
      item_code: 'SRTWB242',
      ...over,
    } as BoardContribution,
  };
}

describe('unpostableNotices', () => {
  it('names the SO line number when AutoCount numbered the line', () => {
    const [notice] = unpostableNotices('no_mirror', [lineOf({ so_line_no: 224 })]);
    expect(notice.named.map((entry) => entry.label)).toEqual(['SRTWB242 line 224']);
  });

  it('falls back to the planning number when the core line carries none', () => {
    const [notice] = unpostableNotices('no_mirror', [lineOf({ so_line_no: null })]);
    expect(notice.named.map((entry) => entry.label)).toEqual(['SRTWB242 line 11']);
  });
});
