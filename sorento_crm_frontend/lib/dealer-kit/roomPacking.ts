/**
 * Keeping two things out of the same space.
 *
 * A plan that shows a bathtub standing inside a vanity is not a plan, and until
 * now nothing stopped one: overlap was DETECTED (the clashing boxes turned red)
 * but never PREVENTED. You could drag one unit through another, and opening a
 * room from a catalogue's picks laid them out on a fixed 800mm grid regardless
 * of how big they actually are - so a 1,600mm bath arrived already inside its
 * neighbour, before the user had touched anything.
 *
 * Two entry points, for the two ways a box gets a position:
 *
 * * `resolveDrag` for a box somebody is moving. It never returns an overlapping
 *   position, and it never reverts one either - it SLIDES, so dragging along an
 *   obstacle follows the obstacle instead of freezing. Refusing outright makes
 *   a planner feel broken; refusing to overlap is the actual requirement.
 * * `packBoxes` for boxes arriving without a position of their own. It places
 *   what fits and REPORTS what it could not, because a room that quietly drops
 *   two of the seven things somebody chose is worse than one that says so.
 *
 * Pure geometry, no React: the same rules have to hold for the plan view and
 * the 3D view, and the only way to guarantee that is for neither to own them.
 */

import {
  boxFitsInRoom,
  boxesOverlap,
  clampBoxIntoRoom,
  roomBounds,
  snapToGrid,
  type Box,
  type Point,
} from './roomGeometry';

/**
 * How finely `packBoxes` looks for a gap.
 *
 * Coarser than the 50mm drag grid on purpose: this scans, and the scan is
 * O(positions x boxes). 100mm finds every gap a real bathroom fitting can use
 * and keeps a seven-item room instant.
 */
export const PACK_STEP_MM = 100;

/** A pure footprint, which is all either of these functions needs. */
type Footprint = Box & { id: string };

function collidesWithAny(candidate: Footprint, others: Footprint[]): boolean {
  return others.some(
    (other) => other.id !== candidate.id && boxesOverlap(candidate, other),
  );
}

/**
 * Where a dragged box may actually go.
 *
 * The candidate is tried first. If it would overlap, the two single-axis moves
 * are tried in turn, which is what makes a box slide along the thing it hit
 * rather than stop dead against it. If none of the three is legal the box keeps
 * the position it had, so an illegal drag simply does not happen - it is never
 * committed and then undone.
 *
 * `from` is where the box is NOW, not where the drag started: sliding has to
 * work continuously as the pointer moves.
 */
export function resolveDrag(
  from: Box & { id: string },
  candidate: { x: number; y: number; rotation: number },
  others: Footprint[],
  outline: Point[],
): { x: number; y: number; rotation: number } {
  const attempt = (x: number, y: number, rotation: number) => {
    // Tidied into the room first, exactly as a free drag is: half through a
    // wall is a clear intent the system can fix, and the fixed position is the
    // one that has to be checked for overlap.
    const inRoom = clampBoxIntoRoom({ ...from, x, y, rotation }, outline) as Footprint;
    return collidesWithAny(inRoom, others) ? null : inRoom;
  };

  const direct = attempt(candidate.x, candidate.y, candidate.rotation);
  if (direct) return { x: direct.x, y: direct.y, rotation: direct.rotation };

  // Slide: keep whichever axis is free. Rotation comes with the position (the
  // plan turns a unit when it backs onto a wall), so a rotation that would
  // overlap is refused with the move that carried it.
  const alongX = attempt(candidate.x, from.y, candidate.rotation);
  if (alongX) return { x: alongX.x, y: alongX.y, rotation: alongX.rotation };

  const alongY = attempt(from.x, candidate.y, candidate.rotation);
  if (alongY) return { x: alongY.x, y: alongY.y, rotation: alongY.rotation };

  // Nothing legal. The box stays exactly where it was, INCLUDING its rotation:
  // turning in place into a neighbour is the same illegal move.
  return { x: from.x, y: from.y, rotation: from.rotation };
}

/**
 * The first free spot for one box, scanning left to right and top to bottom.
 *
 * Returns null when the room has no gap that fits it, which is a real answer -
 * a 1.8m bath does not go in a 1.5m room and no amount of shuffling changes
 * that.
 */
export function findFreePosition(
  box: Footprint,
  others: Footprint[],
  outline: Point[],
  step: number = PACK_STEP_MM,
): { x: number; y: number } | null {
  if (outline.length < 3) return null;

  const bounds = roomBounds(outline);
  for (let y = bounds.minY; y <= bounds.maxY; y += step) {
    for (let x = bounds.minX; x <= bounds.maxX; x += step) {
      const candidate = { ...box, x: snapToGrid(x), y: snapToGrid(y) };
      // Both gates, in this order: inside the room is cheaper to reject than a
      // separating-axis test against every neighbour.
      if (!boxFitsInRoom(candidate, outline)) continue;
      if (collidesWithAny(candidate, others)) continue;
      return { x: candidate.x, y: candidate.y };
    }
  }
  return null;
}

export interface PackResult<T extends Footprint> {
  boxes: T[];
  /**
   * The ones the room could not hold, in the order they were asked for.
   *
   * They keep whatever position they arrived with and are handed back so the
   * caller can SAY so. Silently dropping them, or stacking them, are the two
   * things this module exists to prevent.
   */
  unplaced: T[];
}

/**
 * Give every box a position that overlaps nothing.
 *
 * Boxes named in `keep` are treated as fixed - they are somebody's decision and
 * this is not the place to overrule it - and everything else is placed around
 * them, largest first. Largest first matters: a bath placed after four taps has
 * nowhere left to go, while the same four taps fit around a bath easily.
 */
export function packBoxes<T extends Footprint>(
  boxes: T[],
  outline: Point[],
  keep: ReadonlySet<string> = new Set(),
): PackResult<T> {
  const fixed: T[] = boxes.filter((box) => keep.has(box.id));
  const toPlace = boxes
    .filter((box) => !keep.has(box.id))
    // Stable by construction: ties keep their original order, so the same room
    // packs the same way twice.
    .map((box, index) => ({ box, index }))
    .sort((a, b) => {
      const areaA = a.box.width * a.box.depth;
      const areaB = b.box.width * b.box.depth;
      return areaB - areaA || a.index - b.index;
    })
    .map((entry) => entry.box);

  const placed: T[] = [...fixed];
  const unplaced: T[] = [];
  const resolved = new Map<string, T>();

  for (const box of toPlace) {
    const spot = findFreePosition(box, placed, outline);
    if (spot === null) {
      unplaced.push(box);
      continue;
    }
    const settled = { ...box, x: spot.x, y: spot.y };
    placed.push(settled);
    resolved.set(box.id, settled);
  }

  return {
    // Returned in the ORDER THEY CAME IN, not in packing order: the caller's
    // list is the user's list, and reordering it would shuffle the room's
    // contents panel every time somebody added an item.
    boxes: boxes.map((box) => resolved.get(box.id) ?? box),
    unplaced,
  };
}
