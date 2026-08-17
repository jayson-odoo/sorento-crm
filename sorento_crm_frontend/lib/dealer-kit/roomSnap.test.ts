/**
 * Wall magnetism and clearance, written before the implementation.
 *
 * These two behaviours are the ones that separate a drawing toy from a planner.
 * IKEA's planner makes orientation the SYSTEM's job: a product dragged near a
 * wall backs onto it and turns to face the room, and dragging it toward a
 * different wall hops it across and re-orients it. The user never rotates
 * anything, so they can never leave a wash stand facing a wall.
 *
 * The clearance numbers are the other half: while an item is selected you are
 * told how much room is left either side of it, which answers "will it fit"
 * without a tape measure.
 *
 * Rooms here are in millimetres, drawn clockwise from the top-left, so the
 * inside of the room is to the RIGHT of each wall direction.
 */
import { describe, expect, it } from 'vitest';

import { clearances, snapToWall, WALL_SNAP_MM } from './roomSnap';
import type { Box, Point } from './roomGeometry';

/** A 4000 x 3000 room: (0,0) -> (4000,0) -> (4000,3000) -> (0,3000). */
const ROOM: Point[] = [
  { x: 0, y: 0 },
  { x: 4000, y: 0 },
  { x: 4000, y: 3000 },
  { x: 0, y: 3000 },
];

function box(overrides: Partial<Box> = {}): Box {
  return { x: 1000, y: 1000, width: 800, depth: 400, rotation: 0, ...overrides };
}

describe('snapToWall', () => {
  it('leaves a box alone when it is nowhere near a wall', () => {
    const middle = box({ x: 1600, y: 1300 });
    expect(snapToWall(middle, ROOM)).toBeNull();
  });

  it('backs a box onto the top wall and squares it to that wall', () => {
    // Its back edge is 60mm off the wall - inside the magnet range.
    const near = box({ x: 1000, y: 60 });
    const snapped = snapToWall(near, ROOM);

    expect(snapped).not.toBeNull();
    expect(snapped!.wallIndex).toBe(0);
    // Flush: the back edge sits ON the wall, so y is 0.
    expect(snapped!.box.y).toBe(0);
    // Unmoved along the wall - snapping is not repositioning.
    expect(snapped!.box.x).toBe(1000);
    expect(snapped!.box.rotation).toBe(0);
  });

  it('turns a box to face into the room from the left wall', () => {
    const near = box({ x: 40, y: 1200 });
    const snapped = snapToWall(near, ROOM);

    expect(snapped!.wallIndex).toBe(3);
    // Facing right, into the room. The footprint is 400 deep, so a box whose
    // back is on x=0 occupies 0..400 across, and its width runs down the wall.
    expect(snapped!.box.rotation).toBe(90);
    const corners = snappedCorners(snapped!.box);
    expect(Math.min(...corners.map((corner) => corner.x))).toBeCloseTo(0, 5);
  });

  it('hops to whichever wall is nearest, not the one it came from', () => {
    // Dragged across the room until it is closest to the bottom wall.
    const near = box({ x: 1000, y: 2620 });
    const snapped = snapToWall(near, ROOM);

    expect(snapped!.wallIndex).toBe(2);
    // Flush against the bottom wall: back edge on y=3000.
    const corners = snappedCorners(snapped!.box);
    expect(Math.max(...corners.map((corner) => corner.y))).toBeCloseTo(3000, 5);
  });

  it('slides a box back inside when it overhangs the end of its wall', () => {
    // Hard against the top-right corner, half of it past the end of the wall.
    const overhanging = box({ x: 3800, y: 20 });
    const snapped = snapToWall(overhanging, ROOM);

    const corners = snappedCorners(snapped!.box);
    expect(Math.max(...corners.map((corner) => corner.x))).toBeLessThanOrEqual(4000 + 1e-6);
    expect(Math.min(...corners.map((corner) => corner.x))).toBeGreaterThanOrEqual(-1e-6);
  });

  it('does not pretend to snap a box that is wider than the wall', () => {
    const tinyRoom: Point[] = [
      { x: 0, y: 0 },
      { x: 500, y: 0 },
      { x: 500, y: 500 },
      { x: 0, y: 500 },
    ];
    // 800 wide against a 500 wall: there is no position that fits, so leaving
    // it where the user put it beats jamming it and lying about the fit.
    expect(snapToWall(box({ x: 0, y: 20, width: 800, depth: 400 }), tinyRoom)).toBeNull();
  });

  it('ignores a degenerate outline instead of dividing by zero', () => {
    expect(snapToWall(box(), [])).toBeNull();
    expect(snapToWall(box(), [{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }])).toBeNull();
  });

  it('uses the documented magnet distance', () => {
    const justInside = box({ x: 1000, y: WALL_SNAP_MM - 1 });
    const justOutside = box({ x: 1000, y: WALL_SNAP_MM + 1 });

    expect(snapToWall(justInside, ROOM)).not.toBeNull();
    expect(snapToWall(justOutside, ROOM)).toBeNull();
  });
});

describe('clearances', () => {
  it('measures to the ends of the wall when nothing else is there', () => {
    const onTopWall = box({ x: 1000, y: 0 });
    const gaps = clearances(onTopWall, [], ROOM, 0);

    // 1000 to the left end, 4000 - 1800 = 2200 to the right end.
    expect(gaps).toEqual({ before: 1000, after: 2200 });
  });

  it('measures to a neighbour rather than past it to the wall end', () => {
    const onTopWall = box({ x: 1000, y: 0 });
    const neighbour = box({ x: 2200, y: 0, width: 600 });
    const gaps = clearances(onTopWall, [neighbour], ROOM, 0);

    // 2200 - 1800 = 400 to the neighbour, and the wall end is still 1000 back.
    expect(gaps).toEqual({ before: 1000, after: 400 });
  });

  it('reports zero rather than a negative when two items touch or overlap', () => {
    const onTopWall = box({ x: 1000, y: 0 });
    const touching = box({ x: 1700, y: 0, width: 600 });
    const gaps = clearances(onTopWall, [touching], ROOM, 0);

    expect(gaps!.after).toBe(0);
  });

  it('ignores items that are not on the same wall', () => {
    const onTopWall = box({ x: 1000, y: 0 });
    // Right across the room, so it constrains nothing along the top wall.
    const elsewhere = box({ x: 2000, y: 2600 });
    const gaps = clearances(onTopWall, [elsewhere], ROOM, 0);

    expect(gaps).toEqual({ before: 1000, after: 2200 });
  });

  it('measures along a vertical wall as readily as a horizontal one', () => {
    const onLeftWall = box({ x: 0, y: 1000, width: 800, depth: 400, rotation: 90 });
    const gaps = clearances(onLeftWall, [], ROOM, 3);

    // The left wall runs from (0,3000) up to (0,0), so "before" is measured
    // from the bottom end.
    expect(gaps!.before + gaps!.after).toBeCloseTo(3000 - 800, 5);
  });

  it('returns nothing for a box that is not against a wall', () => {
    expect(clearances(box(), [], ROOM, null)).toBeNull();
  });
});

/** Corner helper, kept local so the test does not depend on render code. */
function snappedCorners(value: Box): Point[] {
  const centreX = value.x + value.width / 2;
  const centreY = value.y + value.depth / 2;
  const radians = (value.rotation * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return [
    { x: -value.width / 2, y: -value.depth / 2 },
    { x: value.width / 2, y: -value.depth / 2 },
    { x: value.width / 2, y: value.depth / 2 },
    { x: -value.width / 2, y: value.depth / 2 },
  ].map((corner) => ({
    x: centreX + corner.x * cos - corner.y * sin,
    y: centreY + corner.x * sin + corner.y * cos,
  }));
}
