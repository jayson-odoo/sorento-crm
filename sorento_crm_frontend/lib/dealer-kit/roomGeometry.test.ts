import { describe, expect, it } from 'vitest';

import {
  areaSquareMetres,
  boxFitsInRoom,
  boxesOverlap,
  clampBoxIntoRoom,
  isPointInside,
  roomBounds,
  snapToGrid,
  type Box,
  type Point,
} from './roomGeometry';

/**
 * Golden set for room geometry, written BEFORE the implementation (AC-T1).
 *
 * Everything here is in MILLIMETRES, because that is what product dimensions
 * are and converting at the edges is how a sink ends up a metre wide. Area is
 * the one exception: nobody reads square millimetres.
 *
 * A 4m x 3m room, as a closed polygon in reading order.
 */
const ROOM: Point[] = [
  { x: 0, y: 0 },
  { x: 4000, y: 0 },
  { x: 4000, y: 3000 },
  { x: 0, y: 3000 },
];

/** An L-shape: the 4x3 room with a 1m x 1m bite out of the far corner. */
const L_ROOM: Point[] = [
  { x: 0, y: 0 },
  { x: 4000, y: 0 },
  { x: 4000, y: 2000 },
  { x: 3000, y: 2000 },
  { x: 3000, y: 3000 },
  { x: 0, y: 3000 },
];

function box(x: number, y: number, width = 600, depth = 600): Box {
  return { x, y, width, depth, rotation: 0 };
}

describe('areaSquareMetres', () => {
  it('measures a rectangle', () => {
    expect(areaSquareMetres(ROOM)).toBeCloseTo(12, 5);
  });

  it('measures a concave outline', () => {
    // 12 sq m minus the 1 sq m bite.
    expect(areaSquareMetres(L_ROOM)).toBeCloseTo(11, 5);
  });

  it('does not care which way the outline was drawn', () => {
    // A user dragging anticlockwise has not made a negative room.
    expect(areaSquareMetres([...ROOM].reverse())).toBeCloseTo(12, 5);
  });

  it('is zero for a degenerate outline', () => {
    expect(areaSquareMetres([])).toBe(0);
    expect(areaSquareMetres([{ x: 0, y: 0 }, { x: 100, y: 100 }])).toBe(0);
  });
});

describe('isPointInside', () => {
  it('accepts a point in the middle', () => {
    expect(isPointInside({ x: 2000, y: 1500 }, ROOM)).toBe(true);
  });

  it('rejects a point outside', () => {
    expect(isPointInside({ x: 5000, y: 1500 }, ROOM)).toBe(false);
  });

  it('rejects a point in the bite of a concave room', () => {
    // The case a bounding-box test gets wrong, which is why this is not one.
    expect(isPointInside({ x: 3500, y: 2500 }, L_ROOM)).toBe(false);
    expect(isPointInside({ x: 3500, y: 1000 }, L_ROOM)).toBe(true);
  });

  it('treats a point on the wall as inside', () => {
    // A worktop pushed flat against the wall is the normal case, not an error.
    expect(isPointInside({ x: 0, y: 1500 }, ROOM)).toBe(true);
    expect(isPointInside({ x: 4000, y: 1500 }, ROOM)).toBe(true);
  });
});

describe('boxFitsInRoom', () => {
  it('accepts a box well inside', () => {
    expect(boxFitsInRoom(box(1000, 1000), ROOM)).toBe(true);
  });

  it('rejects a box hanging through a wall', () => {
    expect(boxFitsInRoom(box(3900, 1000), ROOM)).toBe(false);
  });

  it('accepts a box flush against a wall', () => {
    expect(boxFitsInRoom(box(0, 0), ROOM)).toBe(true);
  });

  it('rejects a box in the bite of a concave room', () => {
    expect(boxFitsInRoom(box(3200, 2200), L_ROOM)).toBe(false);
  });

  it('accounts for rotation', () => {
    // A 1600 x 400 unit fits across a 2m gap only when it is turned.
    const longUnit = { x: 0, y: 0, width: 1600, depth: 400, rotation: 0 };
    expect(boxFitsInRoom({ ...longUnit, x: 2500, y: 2600 }, ROOM)).toBe(false);
    expect(boxFitsInRoom({ ...longUnit, x: 2500, y: 1000, rotation: 90 }, ROOM)).toBe(true);
  });
});

describe('boxesOverlap', () => {
  it('detects two boxes in the same place', () => {
    expect(boxesOverlap(box(1000, 1000), box(1000, 1000))).toBe(true);
  });

  it('allows two boxes side by side', () => {
    expect(boxesOverlap(box(0, 0), box(600, 0))).toBe(false);
  });

  it('allows boxes that merely touch', () => {
    // Units pushed together in a run is a design, not a collision.
    expect(boxesOverlap(box(0, 0, 600, 600), box(600, 0, 600, 600))).toBe(false);
  });

  it('detects a partial overlap', () => {
    expect(boxesOverlap(box(0, 0), box(300, 300))).toBe(true);
  });

  it('accounts for rotation', () => {
    const wide = { x: 0, y: 0, width: 2000, depth: 400, rotation: 0 };
    const turned = { x: 500, y: 0, width: 2000, depth: 400, rotation: 90 };
    expect(boxesOverlap(wide, turned)).toBe(true);
  });
});

describe('clampBoxIntoRoom', () => {
  it('leaves a box that already fits alone', () => {
    const placed = box(1000, 1000);
    expect(clampBoxIntoRoom(placed, ROOM)).toEqual(placed);
  });

  it('pulls a box back inside rather than refusing the drag', () => {
    // Dropping a unit half through a wall should tidy it, not undo the move -
    // the user's intent was clear.
    const clamped = clampBoxIntoRoom(box(3900, 1000), ROOM);
    expect(clamped.x + clamped.width).toBeLessThanOrEqual(4000);
    expect(boxFitsInRoom(clamped, ROOM)).toBe(true);
  });

  it('clamps against the near walls too', () => {
    const clamped = clampBoxIntoRoom(box(-500, -500), ROOM);
    expect(clamped.x).toBeGreaterThanOrEqual(0);
    expect(clamped.y).toBeGreaterThanOrEqual(0);
  });
});

describe('snapToGrid', () => {
  it('snaps to the nearest 50mm by default', () => {
    // 1024 is 24 from 1000 and 26 from 1050, so it snaps down.
    expect(snapToGrid(1024)).toBe(1000);
    expect(snapToGrid(1030)).toBe(1050);
    expect(snapToGrid(1010)).toBe(1000);
  });

  it('honours a different grid', () => {
    expect(snapToGrid(1024, 100)).toBe(1000);
    expect(snapToGrid(1051, 100)).toBe(1100);
  });

  it('leaves an exact value alone', () => {
    expect(snapToGrid(1000)).toBe(1000);
  });
});

describe('roomBounds', () => {
  it('reports the extent of the outline', () => {
    expect(roomBounds(ROOM)).toEqual({ minX: 0, minY: 0, maxX: 4000, maxY: 3000 });
  });

  it('survives an empty outline without throwing', () => {
    expect(roomBounds([])).toEqual({ minX: 0, minY: 0, maxX: 0, maxY: 0 });
  });
});
