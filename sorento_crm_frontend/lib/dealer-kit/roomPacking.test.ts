/**
 * The overlap gate.
 *
 * The invariant is one sentence and every test here is a way of trying to break
 * it: NO TWO BOXES MAY OCCUPY THE SAME SPACE, however they got there. Overlap
 * used to be detected and coloured red, which is a report, not a rule.
 */
import { describe, expect, it } from 'vitest';

import { boxesOverlap, type Point } from './roomGeometry';
import { findFreePosition, packBoxes, resolveDrag } from './roomPacking';

/** A plain 4m x 3m room. */
const ROOM: Point[] = [
  { x: 0, y: 0 },
  { x: 4000, y: 0 },
  { x: 4000, y: 3000 },
  { x: 0, y: 3000 },
];

function box(id: string, x: number, y: number, width = 600, depth = 600, rotation = 0) {
  return { id, x, y, width, depth, rotation };
}

/** The invariant itself, asserted directly rather than trusted. */
function noneOverlap(boxes: ReturnType<typeof box>[]): boolean {
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      if (boxesOverlap(boxes[i], boxes[j])) return false;
    }
  }
  return true;
}

describe('resolveDrag', () => {
  it('allows a move into empty space', () => {
    const moving = box('a', 0, 0);
    const result = resolveDrag(moving, { x: 1500, y: 1500, rotation: 0 }, [moving], ROOM);

    expect(result).toEqual({ x: 1500, y: 1500, rotation: 0 });
  });

  it('refuses to land one box on top of another', () => {
    const moving = box('a', 0, 0);
    const blocker = box('b', 2000, 2000);

    const result = resolveDrag(
      moving,
      { x: 2000, y: 2000, rotation: 0 },
      [moving, blocker],
      ROOM,
    );

    expect(boxesOverlap({ ...moving, ...result }, blocker)).toBe(false);
  });

  it('slides along an obstacle rather than stopping dead against it', () => {
    // Dragging right and down when only the down component is blocked: the box
    // must keep travelling right. Freezing here is what makes a planner feel
    // broken even though it is technically obeying the rule.
    const moving = box('a', 1000, 1000);
    const blocker = box('b', 1000, 1600);

    const result = resolveDrag(
      moving,
      { x: 1600, y: 1600, rotation: 0 },
      [moving, blocker],
      ROOM,
    );

    expect(result.x).toBe(1600);
    expect(boxesOverlap({ ...moving, ...result }, blocker)).toBe(false);
  });

  it('leaves the box exactly where it was when nothing legal is available', () => {
    // Boxed in on both axes: the move simply does not happen. It is never
    // committed and then reverted, which is the difference the requirement
    // asks for.
    // One blocker straddling the target covers all three attempts: the direct
    // move, the x-only slide and the y-only slide.
    const moving = box('a', 1000, 1000);
    const blocker = box('b', 1500, 1500);

    const result = resolveDrag(
      moving,
      { x: 1600, y: 1600, rotation: 0 },
      [moving, blocker],
      ROOM,
    );

    expect(result).toEqual({ x: 1000, y: 1000, rotation: 0 });
  });

  it('refuses a rotation that would turn a box into its neighbour', () => {
    // Turning in place is the same illegal move as sliding into one, and it is
    // the one an axis-sliding fallback would miss.
    // The blocker sits clear of the unrotated footprint (x 1000-2600,
    // y 1000-1400) and inside the rotated one (x 1600-2000, y 400-2000), so
    // only the turn is illegal.
    const moving = box('a', 1000, 1000, 1600, 400);
    const blocker = box('b', 1700, 1500, 200, 400);

    const result = resolveDrag(
      moving,
      { x: 1000, y: 1000, rotation: 90 },
      [moving, blocker],
      ROOM,
    );

    expect(result.rotation).toBe(0);
    expect(boxesOverlap({ ...moving, ...result }, blocker)).toBe(false);
  });

  it('still pulls a box dropped through a wall back inside', () => {
    const moving = box('a', 1000, 1000);
    const result = resolveDrag(moving, { x: 3900, y: 1000, rotation: 0 }, [moving], ROOM);

    expect(result.x).toBeLessThanOrEqual(4000 - 600);
  });
});

describe('findFreePosition', () => {
  it('finds a gap in a crowded room', () => {
    const others = [box('a', 0, 0, 2000, 2000)];
    const spot = findFreePosition(box('new', 0, 0), others, ROOM);

    expect(spot).not.toBeNull();
    expect(boxesOverlap({ ...box('new', 0, 0), ...spot! }, others[0])).toBe(false);
  });

  it('says so when nothing fits, rather than returning a wrong answer', () => {
    // A 5m unit does not go in a 4m room. "No" is the honest answer and the
    // caller has to be able to act on it.
    const spot = findFreePosition(box('huge', 0, 0, 5000, 500), [], ROOM);

    expect(spot).toBeNull();
  });
});

describe('packBoxes', () => {
  it('lays out picks without a single overlap', () => {
    // The real complaint: opening a room from a catalogue's picks put
    // everything on a fixed 800mm grid regardless of its actual size, so a
    // 1,600mm bath arrived already inside its neighbour.
    const picks = [
      box('bath', 200, 200, 1700, 750),
      box('vanity', 1000, 200, 900, 500),
      box('wc', 1800, 200, 700, 400),
      box('basin', 200, 1000, 600, 450),
    ];

    const { boxes, unplaced } = packBoxes(picks, ROOM);

    expect(unplaced).toEqual([]);
    expect(noneOverlap(boxes)).toBe(true);
  });

  it('keeps every box inside the room', () => {
    const picks = Array.from({ length: 6 }, (_, index) =>
      box(`p${index}`, 0, 0, 900, 700),
    );

    const { boxes } = packBoxes(picks, ROOM);

    for (const placed of boxes) {
      expect(placed.x).toBeGreaterThanOrEqual(0);
      expect(placed.y).toBeGreaterThanOrEqual(0);
      expect(placed.x + placed.width).toBeLessThanOrEqual(4000);
      expect(placed.y + placed.depth).toBeLessThanOrEqual(3000);
    }
  });

  it('reports what it could not fit instead of stacking or dropping it', () => {
    const tooMany = Array.from({ length: 40 }, (_, index) =>
      box(`p${index}`, 0, 0, 1200, 1200),
    );

    const { boxes, unplaced } = packBoxes(tooMany, ROOM);

    expect(unplaced.length).toBeGreaterThan(0);
    // And the ones it DID place still obey the rule.
    const settled = boxes.filter((candidate) => !unplaced.some((u) => u.id === candidate.id));
    expect(noneOverlap(settled)).toBe(true);
  });

  it('does not move a box somebody has already positioned', () => {
    const parked = box('parked', 3000, 2000);
    const arriving = box('new', 0, 0, 1000, 1000);

    const { boxes } = packBoxes([parked, arriving], ROOM, new Set(['parked']));

    expect(boxes.find((candidate) => candidate.id === 'parked')).toEqual(parked);
    expect(noneOverlap(boxes)).toBe(true);
  });

  it('places the largest first, so a bath is not shut out by four taps', () => {
    const taps = Array.from({ length: 4 }, (_, index) => box(`tap${index}`, 0, 0, 300, 300));
    const bath = box('bath', 0, 0, 1700, 750);

    const { unplaced } = packBoxes([...taps, bath], ROOM);

    expect(unplaced).toEqual([]);
  });

  it('hands the boxes back in the order they came in', () => {
    // The caller's list is the user's list. Reordering it would shuffle the
    // room's contents panel every time somebody added an item.
    const picks = [box('a', 0, 0, 300, 300), box('b', 0, 0, 1700, 750), box('c', 0, 0, 500, 500)];

    const { boxes } = packBoxes(picks, ROOM);

    expect(boxes.map((candidate) => candidate.id)).toEqual(['a', 'b', 'c']);
  });

  it('is deterministic - the same room packs the same way twice', () => {
    const picks = [box('a', 0, 0, 600, 600), box('b', 0, 0, 600, 600), box('c', 0, 0, 600, 600)];

    expect(packBoxes(picks, ROOM).boxes).toEqual(packBoxes(picks, ROOM).boxes);
  });
});
