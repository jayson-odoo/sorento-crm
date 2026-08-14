/**
 * The editor and the published page must agree about what a row is worth.
 *
 * They lay the same blocks out with different engines - react-grid-layout in
 * the builder, CSS grid on the page - and both derive a block's height from the
 * same row count. When the two constants drifted apart (24px in the builder,
 * 28px in the renderer) blocks that sat neatly with a gap in the builder
 * overlapped once published, which is the worst possible place to find out.
 */
import { describe, expect, it } from 'vitest';

import { ROW_GAP_PX, ROW_HEIGHT_PX, rowsForHeight, rowsToHeight } from './gridMetrics';

describe('grid metrics', () => {
  it('measures one row as the row unit alone', () => {
    expect(rowsToHeight(1)).toBe(ROW_HEIGHT_PX);
  });

  it('counts the gaps BETWEEN rows, not after the last one', () => {
    expect(rowsToHeight(3)).toBe(ROW_HEIGHT_PX * 3 + ROW_GAP_PX * 2);
  });

  it('round trips: the rows chosen for a height are tall enough to hold it', () => {
    for (const height of [1, 23, 24, 25, 100, 260, 999]) {
      expect(rowsToHeight(rowsForHeight(height))).toBeGreaterThanOrEqual(height);
    }
  });

  it('does not over-count by ignoring the gaps', () => {
    // Two rows hold 60px (24 + 12 + 24); asking for 60 must not demand three.
    expect(rowsForHeight(60)).toBe(2);
  });

  it('never asks for less than one row', () => {
    expect(rowsForHeight(0)).toBe(1);
    expect(rowsForHeight(-50)).toBe(1);
  });
});
