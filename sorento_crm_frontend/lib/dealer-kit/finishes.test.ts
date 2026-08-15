import { describe, expect, it } from 'vitest';

import {
  DEFAULT_FLOOR_FINISH,
  DEFAULT_WALL_FINISH,
  floorColor,
  floorFinishId,
  setFloorFinish,
  setWallFinish,
  wallColor,
  wallFinishId,
  WALL_FINISHES,
} from './finishes';

describe('finishes', () => {
  it('falls back to the default when a surface has never been chosen', () => {
    expect(wallFinishId(undefined, 0)).toBe(DEFAULT_WALL_FINISH);
    expect(floorFinishId(undefined)).toBe(DEFAULT_FLOOR_FINISH);
    expect(wallColor(undefined, 0)).toBe(WALL_FINISHES[0].color);
  });

  it('opens a design whose finish no longer exists rather than failing', () => {
    // A palette entry can be dropped between releases. The saved design must
    // still open - plainly, but open.
    const stale = { floor: 'sandstone-2019', walls: { '0': 'gone' } };

    expect(() => wallColor(stale, 0)).not.toThrow();
    expect(wallColor(stale, 0)).toBe(WALL_FINISHES[0].color);
    expect(floorColor(stale)).toBeTruthy();
  });

  it('sets one wall without touching the others or the floor', () => {
    const before = { floor: 'timber', walls: { '0': 'charcoal' } };
    const after = setWallFinish(before, 2, 'sage');

    expect(after.walls).toEqual({ '0': 'charcoal', '2': 'sage' });
    expect(after.floor).toBe('timber');
    // The original object is untouched, so an undo snapshot taken before this
    // still describes what the room looked like.
    expect(before.walls).toEqual({ '0': 'charcoal' });
  });

  it('sets the floor without touching the walls', () => {
    const after = setFloorFinish({ walls: { '1': 'sage' } }, 'slate');

    expect(after.floor).toBe('slate');
    expect(after.walls).toEqual({ '1': 'sage' });
  });

  it('keys walls by index as a string, because JSON has no numeric keys', () => {
    const after = setWallFinish(undefined, 3, 'charcoal');

    expect(after.walls).toEqual({ '3': 'charcoal' });
    expect(wallFinishId(after, 3)).toBe('charcoal');
  });
});
