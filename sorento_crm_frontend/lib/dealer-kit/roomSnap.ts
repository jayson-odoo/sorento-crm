/**
 * Wall magnetism, and how much room is left either side of a product.
 *
 * Orientation is the system's job, not the user's. A dealer laying out a
 * bathroom is not deciding "should this vanity face the wall or the room" - it
 * backs onto a wall, always. So a product dragged near a wall is squared to it
 * and slid inside its ends, and dragging on toward a different wall hops it
 * across and re-orients it. There is no rotate handle to get wrong.
 *
 * The clearance numbers are the other half of the same idea: while an item is
 * selected it says how much space is left on each side of it along its wall,
 * which answers "will the next one fit" without a tape measure.
 *
 * Everything is millimetres, in the same top-down space as the plan. Outlines
 * are wound clockwise on screen (y down), so the room's inside is to the RIGHT
 * of each wall's direction.
 */
import { boxCorners, type Box, type Point } from './roomGeometry';

/**
 * How close the nearest corner must come before a wall takes hold.
 *
 * 150mm is about a finger's width on screen at a normal room zoom: near enough
 * that grabbing a wall feels intentional, far enough that you do not have to
 * aim.
 */
export const WALL_SNAP_MM = 150;

export interface WallSnap {
  box: Box;
  wallIndex: number;
}

interface Wall {
  a: Point;
  /** Unit vector along the wall. */
  dx: number;
  dy: number;
  /** Unit normal pointing INTO the room. */
  nx: number;
  ny: number;
  length: number;
}

function walls(outline: Point[]): Wall[] {
  if (outline.length < 3) return [];

  const result: Wall[] = [];
  for (let index = 0; index < outline.length; index += 1) {
    const a = outline[index];
    const b = outline[(index + 1) % outline.length];
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    if (length < 1e-6) continue;
    const dx = (b.x - a.x) / length;
    const dy = (b.y - a.y) / length;
    // Rotating the direction a quarter turn gives the inward normal for a
    // clockwise outline in screen space.
    result.push({ a, dx, dy, nx: -dy, ny: dx, length });
  }
  return result;
}

/** Distance from a wall's line to the box corner nearest it. Never negative. */
function nearestCornerDistance(corners: Point[], wall: Wall): number {
  return Math.min(
    ...corners.map((corner) =>
      Math.abs((corner.x - wall.a.x) * wall.nx + (corner.y - wall.a.y) * wall.ny),
    ),
  );
}

/** Where a point sits ALONG a wall, measured from its start. */
function alongWall(point: Point, wall: Wall): number {
  return (point.x - wall.a.x) * wall.dx + (point.y - wall.a.y) * wall.dy;
}

/**
 * The angle a box takes when it backs onto a wall.
 *
 * Normalised into [0, 180) because a rectangle is the same shape half a turn
 * later: two walls facing each other should not produce footprints that differ
 * only by a number nobody can see.
 */
function wallAngleDegrees(wall: Wall): number {
  const raw = (Math.atan2(wall.dy, wall.dx) * 180) / Math.PI;
  return ((raw % 180) + 180) % 180;
}

/**
 * Back a box onto whichever wall is nearest, if any is near enough.
 *
 * Returns null when nothing is in range, when the outline is degenerate, or
 * when the box is simply wider than the wall - jamming a 2m vanity onto a 1.5m
 * wall would draw a lie, and the honest answer is to leave it where the user
 * put it.
 */
export function snapToWall(
  box: Box,
  outline: Point[],
  snapDistance: number = WALL_SNAP_MM,
): WallSnap | null {
  const candidates = walls(outline);
  if (candidates.length === 0) return null;

  const corners = boxCorners(box);
  let best: { wall: Wall; index: number; distance: number } | null = null;

  candidates.forEach((wall, index) => {
    const distance = nearestCornerDistance(corners, wall);
    if (!best || distance < best.distance) best = { wall, index, distance };
  });

  // TypeScript cannot see that the loop above always assigns.
  const chosen = best as { wall: Wall; index: number; distance: number } | null;
  if (!chosen || chosen.distance > snapDistance) return null;

  const { wall } = chosen;
  if (wall.length < box.width) return null;

  const centre = { x: box.x + box.width / 2, y: box.y + box.depth / 2 };
  // Slid inside the ends of its own wall: an item half off the end of a wall is
  // a drawing of something that cannot be installed.
  const along = Math.min(
    Math.max(alongWall(centre, wall), box.width / 2),
    wall.length - box.width / 2,
  );

  const snappedCentreX = wall.a.x + wall.dx * along + wall.nx * (box.depth / 2);
  const snappedCentreY = wall.a.y + wall.dy * along + wall.ny * (box.depth / 2);

  return {
    wallIndex: chosen.index,
    box: {
      ...box,
      x: snappedCentreX - box.width / 2,
      y: snappedCentreY - box.depth / 2,
      rotation: wallAngleDegrees(wall),
    },
  };
}

export interface Clearance {
  /** Millimetres back toward the start of the wall. */
  before: number;
  /** Millimetres on toward the end of the wall. */
  after: number;
}

/**
 * How much wall is free on each side of a box.
 *
 * Measured against neighbours ON THE SAME WALL and against the wall's own ends,
 * whichever comes first. Anything standing elsewhere in the room is not in the
 * way of sliding this item along its wall, so it is not counted.
 */
export function clearances(
  box: Box,
  others: Box[],
  outline: Point[],
  wallIndex: number | null,
  snapDistance: number = WALL_SNAP_MM,
): Clearance | null {
  if (wallIndex === null) return null;
  const candidates = walls(outline);
  const wall = candidates[wallIndex];
  if (!wall) return null;

  const span = (value: Box) => {
    const projected = boxCorners(value).map((corner) => alongWall(corner, wall));
    return { min: Math.min(...projected), max: Math.max(...projected) };
  };

  const mine = span(box);
  let before = mine.min;
  let after = wall.length - mine.max;

  for (const other of others) {
    if (nearestCornerDistance(boxCorners(other), wall) > snapDistance) continue;
    const theirs = span(other);
    if (theirs.max <= mine.min) {
      before = Math.min(before, mine.min - theirs.max);
    } else if (theirs.min >= mine.max) {
      after = Math.min(after, theirs.min - mine.max);
    } else {
      // Overlapping. Report no gap on the side it came from rather than a
      // negative number, which reads as a measurement instead of a collision.
      const theirCentre = (theirs.min + theirs.max) / 2;
      const myCentre = (mine.min + mine.max) / 2;
      if (theirCentre >= myCentre) after = 0;
      else before = 0;
    }
  }

  return {
    before: Math.max(0, Math.round(before)),
    after: Math.max(0, Math.round(after)),
  };
}

/**
 * Which wall a box is already standing against, if any.
 *
 * Needed on load: placements come back from the server as coordinates, and the
 * clearance chips have to know which wall to measure along without the user
 * dragging anything first.
 */
export function wallUnder(
  box: Box,
  outline: Point[],
  snapDistance: number = WALL_SNAP_MM,
): number | null {
  const candidates = walls(outline);
  if (candidates.length === 0) return null;

  const corners = boxCorners(box);
  let bestIndex: number | null = null;
  let bestDistance = Infinity;

  candidates.forEach((wall, index) => {
    const distance = nearestCornerDistance(corners, wall);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });

  return bestDistance <= snapDistance ? bestIndex : null;
}
