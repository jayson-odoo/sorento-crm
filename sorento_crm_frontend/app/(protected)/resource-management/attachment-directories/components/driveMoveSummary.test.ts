/**
 * FILES-MOVE-DUPLICATE: the one notice a move shows (hand test 12 Nov: counts for moved,
 * renamed, replaced and skipped; Cancel says nothing moved).
 */
import { describe, it, expect } from 'vitest';
import { summarizeMove, type MoveOutcome } from './driveMoveSummary';

const base: MoveOutcome = { cancelled: false, moved: 0, renamed: 0, replaced: 0, skipped: [], notMoved: [] };

describe('summarizeMove', () => {
  it('everything moved: one success line', () => {
    expect(summarizeMove({ ...base, moved: 3 })).toEqual({ ok: true, text: '3 moved.' });
  });

  it('counts renamed and replaced beside the plain moves', () => {
    expect(summarizeMove({ ...base, moved: 6, renamed: 3, replaced: 1 }).text).toBe(
      '6 moved, 3 renamed, 1 replaced.'
    );
  });

  it('skipped files are named; more than three are summed up', () => {
    expect(summarizeMove({ ...base, moved: 2, skipped: ['a.jpg'] })).toEqual({
      ok: true,
      text: '2 moved. 1 skipped: a.jpg.',
    });
    expect(
      summarizeMove({ ...base, moved: 0, skipped: ['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg', 'e.jpg'] }).text
    ).toBe('0 moved. 5 skipped: a.jpg, b.jpg, c.jpg and 2 more.');
  });

  it('a file that could not move is named with its reason', () => {
    expect(
      summarizeMove({
        ...base,
        moved: 2,
        notMoved: [{ name: 'photo.jpg', reason: 'photo.jpg already exists in Folder B.' }],
      })
    ).toEqual({ ok: false, text: '2 moved. 1 not moved: photo.jpg already exists in Folder B.' });
  });

  it('a reason without a full stop gets one, and a missing reason still names the file', () => {
    expect(
      summarizeMove({
        ...base,
        notMoved: [
          { name: 'a.jpg', reason: 'Not allowed' },
          { name: 'b.jpg', reason: '' },
        ],
      }).text
    ).toBe('0 moved. 2 not moved: a.jpg: Not allowed. b.jpg could not be moved.');
  });

  it('Cancel: says nothing was moved', () => {
    expect(summarizeMove({ ...base, cancelled: true })).toEqual({
      ok: true,
      text: 'Move cancelled. Nothing was moved.',
    });
  });

  it('restore reads "restored" throughout', () => {
    expect(summarizeMove({ ...base, moved: 2, renamed: 1 }, 'restored').text).toBe('2 restored, 1 renamed.');
    expect(summarizeMove({ ...base, cancelled: true }, 'restored').text).toBe('Restore cancelled. Nothing was restored.');
    expect(
      summarizeMove({ ...base, notMoved: [{ name: 'a.jpg', reason: 'Not allowed' }] }, 'restored').text
    ).toBe('0 restored. 1 not restored: a.jpg: Not allowed.');
  });
});
