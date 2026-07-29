/**
 * Room geometry for the designer (AC-R1 - AC-R5, AC-V4).
 *
 * **Everything is in millimetres.** Product dimensions are millimetres, walls
 * are millimetres, and converting at the boundaries is how a sink ends up a
 * metre wide. Area is the single exception, because nobody reads square
 * millimetres.
 *
 * A room is a POLYGON, not a rectangle and not a bitmap. Real rooms have
 * alcoves and chimney breasts, and a bounding box would happily let a user park
 * a wardrobe inside a wall. It is also why containment here is a real
 * point-in-polygon test rather than four comparisons.
 */

export interface Point {
  x: number;
  y: number;
}

/** An axis-aligned footprint before rotation. `x`/`y` is its near corner. */
export interface Box {
  x: number;
  y: number;
  width: number;
  depth: number;
  /** Degrees, clockwise. Only the footprint rotates; boxes stay upright. */
  rotation: number;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

const EPSILON = 1e-6;

/** Default snap. 50mm is fine enough to look deliberate, coarse enough to be easy. */
export const DEFAULT_GRID_MM = 50;

export function snapToGrid(value: number, grid: number = DEFAULT_GRID_MM): number {
  if (grid <= 0) return value;
  return Math.round(value / grid) * grid;
}

export function roomBounds(outline: Point[]): Bounds {
  if (outline.length === 0) return { minX: 0, minY: 0, maxX: 0, maxY: 0 };

  return outline.reduce<Bounds>(
    (bounds, point) => ({
      minX: Math.min(bounds.minX, point.x),
      minY: Math.min(bounds.minY, point.y),
      maxX: Math.max(bounds.maxX, point.x),
      maxY: Math.max(bounds.maxY, point.y),
    }),
    { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity },
  );
}

/**
 * Shoelace area, in square metres.
 *
 * The absolute value is taken deliberately: a user dragging walls anticlockwise
 * has not drawn a negative room.
 */
export function areaSquareMetres(outline: Point[]): number {
  if (outline.length < 3) return 0;

  let doubled = 0;
  for (let index = 0; index < outline.length; index += 1) {
    const current = outline[index];
    const next = outline[(index + 1) % outline.length];
    doubled += current.x * next.y - next.x * current.y;
  }

  // mm^2 -> m^2
  return Math.abs(doubled / 2) / 1_000_000;
}

/** The four corners of a box's footprint, rotated about its centre. */
export function boxCorners(box: Box): Point[] {
  const centreX = box.x + box.width / 2;
  const centreY = box.y + box.depth / 2;
  const radians = (box.rotation * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);

  return [
    { x: -box.width / 2, y: -box.depth / 2 },
    { x: box.width / 2, y: -box.depth / 2 },
    { x: box.width / 2, y: box.depth / 2 },
    { x: -box.width / 2, y: box.depth / 2 },
  ].map((corner) => ({
    x: centreX + corner.x * cos - corner.y * sin,
    y: centreY + corner.x * sin + corner.y * cos,
  }));
}

function isOnSegment(point: Point, a: Point, b: Point): boolean {
  const cross = (b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x);
  if (Math.abs(cross) > EPSILON * Math.max(1, Math.abs(b.x - a.x) + Math.abs(b.y - a.y))) {
    return false;
  }
  return (
    Math.min(a.x, b.x) - EPSILON <= point.x &&
    point.x <= Math.max(a.x, b.x) + EPSILON &&
    Math.min(a.y, b.y) - EPSILON <= point.y &&
    point.y <= Math.max(a.y, b.y) + EPSILON
  );
}

/**
 * Ray casting, with points ON the outline counted as inside.
 *
 * That last part is not a rounding concession: a worktop pushed flat against
 * the wall is the normal case, and rejecting it would make the common design
 * impossible.
 */
export function isPointInside(point: Point, outline: Point[]): boolean {
  if (outline.length < 3) return false;

  for (let index = 0; index < outline.length; index += 1) {
    const a = outline[index];
    const b = outline[(index + 1) % outline.length];
    if (isOnSegment(point, a, b)) return true;
  }

  let inside = false;
  for (let index = 0, previous = outline.length - 1; index < outline.length; previous = index, index += 1) {
    const a = outline[index];
    const b = outline[previous];
    const straddles = a.y > point.y !== b.y > point.y;
    if (!straddles) continue;

    const crossingX = ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y) + a.x;
    if (point.x < crossingX) inside = !inside;
  }
  return inside;
}

/**
 * Every corner inside the outline.
 *
 * Corners only, which is exact for a convex room and correct for the concave
 * cases that matter here (a box spanning a notch has a corner in it). A full
 * polygon-polygon clip would be the rigorous version and is not worth its cost
 * until rooms grow curved walls.
 */
export function boxFitsInRoom(box: Box, outline: Point[]): boolean {
  if (outline.length < 3) return false;
  return boxCorners(box).every((corner) => isPointInside(corner, outline));
}

function projectionRange(corners: Point[], axis: Point): { min: number; max: number } {
  let min = Infinity;
  let max = -Infinity;
  for (const corner of corners) {
    const projected = corner.x * axis.x + corner.y * axis.y;
    min = Math.min(min, projected);
    max = Math.max(max, projected);
  }
  return { min, max };
}

/**
 * Separating axis test.
 *
 * Boxes that merely TOUCH do not overlap: units pushed together into a run is a
 * design, not a collision, and treating it as one would make the most ordinary
 * kitchen layout impossible to draw.
 */
export function boxesOverlap(a: Box, b: Box): boolean {
  const cornersA = boxCorners(a);
  const cornersB = boxCorners(b);

  for (const corners of [cornersA, cornersB]) {
    for (let index = 0; index < corners.length; index += 1) {
      const current = corners[index];
      const next = corners[(index + 1) % corners.length];
      const edge = { x: next.x - current.x, y: next.y - current.y };
      const length = Math.hypot(edge.x, edge.y) || 1;
      const axis = { x: -edge.y / length, y: edge.x / length };

      const rangeA = projectionRange(cornersA, axis);
      const rangeB = projectionRange(cornersB, axis);
      if (rangeA.max <= rangeB.min + EPSILON || rangeB.max <= rangeA.min + EPSILON) {
        return false;
      }
    }
  }
  return true;
}

/**
 * Pull a box back inside the room.
 *
 * Tidying beats refusing: dropping a unit half through a wall is a clear
 * intent, and undoing the whole drag punishes the user for imprecision the
 * system can simply fix.
 */
export function clampBoxIntoRoom(box: Box, outline: Point[]): Box {
  if (outline.length < 3 || boxFitsInRoom(box, outline)) return box;

  const bounds = roomBounds(outline);
  const corners = boxCorners(box);
  const footprint = roomBounds(corners);

  let dx = 0;
  let dy = 0;
  if (footprint.minX < bounds.minX) dx = bounds.minX - footprint.minX;
  if (footprint.maxX > bounds.maxX) dx = bounds.maxX - footprint.maxX;
  if (footprint.minY < bounds.minY) dy = bounds.minY - footprint.minY;
  if (footprint.maxY > bounds.maxY) dy = bounds.maxY - footprint.maxY;

  return { ...box, x: box.x + dx, y: box.y + dy };
}

/**
 * Move a whole WALL, keeping it parallel to itself.
 *
 * Dragging corners alone makes the common edit hard: "this wall is 200mm too far
 * out" means moving two corners by hand and hoping the wall stayed straight.
 * Dragging the wall itself is what a person actually means, and it is the
 * interaction every floor-plan tool has.
 *
 * Both endpoints move by the component of the drag PERPENDICULAR to the wall.
 * Sliding a wall along its own length would change nothing about the room while
 * silently dragging its neighbours out of square, so that component is dropped.
 */
export function moveWall(
  outline: Point[],
  wallIndex: number,
  deltaX: number,
  deltaY: number,
  grid: number = DEFAULT_GRID_MM,
): Point[] {
  if (outline.length < 3) return outline;

  const start = outline[wallIndex];
  const end = outline[(wallIndex + 1) % outline.length];

  const alongX = end.x - start.x;
  const alongY = end.y - start.y;
  const length = Math.hypot(alongX, alongY);
  if (length === 0) return outline;

  // Unit normal to the wall.
  const normalX = -alongY / length;
  const normalY = alongX / length;

  // How far the drag went along that normal.
  const distance = deltaX * normalX + deltaY * normalY;
  const shiftX = normalX * distance;
  const shiftY = normalY * distance;

  const nextIndex = (wallIndex + 1) % outline.length;
  return outline.map((point, index) => {
    if (index !== wallIndex && index !== nextIndex) return point;
    return {
      x: snapToGrid(point.x + shiftX, grid),
      y: snapToGrid(point.y + shiftY, grid),
    };
  });
}
