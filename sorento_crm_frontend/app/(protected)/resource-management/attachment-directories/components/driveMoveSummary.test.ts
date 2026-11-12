/**
 * FILES-MOVE-DUPLICATE: one summary for a multi-item move. One file that cannot
 * move never fails the batch; it is named in plain words.
 */
import { describe, it, expect } from 'vitest';
import { summarizeMove } from './driveMoveSummary';

describe('summarizeMove', () => {
  it('everything moved: one success line', () => {
    expect(summarizeMove({ moved: 3, notMoved: [] })).toEqual({ ok: true, text: '3 moved.' });
  });

  it('one clash: the others move and the clash is named', () => {
    expect(
      summarizeMove({
        moved: 2,
        notMoved: [{ name: 'photo.jpg', reason: 'photo.jpg already exists in Folder B.' }],
      })
    ).toEqual({
      ok: false,
      text: '2 moved. 1 not moved: photo.jpg already exists in Folder B.',
    });
  });

  it('several not moved: every one is named', () => {
    expect(
      summarizeMove({
        moved: 1,
        notMoved: [
          { name: 'a.jpg', reason: 'a.jpg already exists in Folder B.' },
          { name: 'b.jpg', reason: 'b.jpg already exists in Folder B.' },
        ],
      }).text
    ).toBe('1 moved. 2 not moved: a.jpg already exists in Folder B. b.jpg already exists in Folder B.');
  });

  it('a reason without a full stop gets one, and a missing reason still names the file', () => {
    expect(
      summarizeMove({
        moved: 0,
        notMoved: [
          { name: 'a.jpg', reason: 'Not allowed' },
          { name: 'b.jpg', reason: '' },
        ],
      }).text
    ).toBe('0 moved. 2 not moved: a.jpg: Not allowed. b.jpg could not be moved.');
  });
});
