/**
 * Free-corner polygon geometry for a shape layer (S4).
 *
 * ONE path builder, two renderers: the Konva canvas draws the string this
 * returns and so does the print page's inline SVG, so the proof on screen and
 * the PDF cannot disagree about what a polygon looks like. Everything here is
 * pure - the editor's handles decide WHERE a corner goes, this decides what
 * that means.
 *
 * Points are normalized to [0, 1] against the layer's own box, which is what
 * lets the Transformer keep resizing a polygon layer exactly as it resizes a
 * rectangle, and what lets a document saved before S4 open with no `points`
 * at all: absent means the four corners.
 */

import type { PolygonPoint } from './tag-template-types';

/**
 * The box's own four corners: what a polygon looks like until one is moved.
 *
 * Read-only by convention. Nothing here ever hands it OUT - `polygonPoints`
 * and the movers copy it - because a caller that stored it straight into a
 * layer's props would give every unedited polygon in the document the same
 * four objects, and the first corner drag would move all of them at once.
 */
export const DEFAULT_POLYGON_POINTS: PolygonPoint[] = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
];

/** A fresh copy of the box's four corners, safe to store in a document. */
export function defaultPolygonPoints(): PolygonPoint[] {
  return DEFAULT_POLYGON_POINTS.map((point) => ({ x: point.x, y: point.y }));
}

/** Trim the float noise a division leaves, so a path string stays readable. */
function round(value: number) {
  return Number(value.toFixed(3));
}

/**
 * The points a polygon layer draws with.
 *
 * Anything that could not be drawn - absent, fewer than three corners, or a
 * coordinate that is not a finite number - falls back to the box, rather than
 * leaving the layer invisible or writing `NaN` into a path string. The refit
 * divides by the box size, so a zero-width axis anywhere upstream is exactly
 * how a `NaN` would get in.
 *
 * Always a fresh array of fresh points: the caller stores what it gets back
 * into a layer's props, and handing out the shared default would alias every
 * unedited polygon in the document onto the same four objects.
 */
export function polygonPoints(props: { points?: PolygonPoint[] | null }): PolygonPoint[] {
  const points = props.points;
  if (!Array.isArray(points) || points.length < 3) return defaultPolygonPoints();
  if (!points.every((point) => Number.isFinite(point?.x) && Number.isFinite(point?.y))) {
    return defaultPolygonPoints();
  }
  return points.map((point) => ({ x: point.x, y: point.y }));
}

/** Normalized points onto a box of `width` x `height`, in that box's own units. */
export function scalePolygonPoints(
  points: PolygonPoint[],
  width: number,
  height: number,
): PolygonPoint[] {
  return points.map((point) => ({ x: point.x * width, y: point.y * height }));
}

interface Vector {
  x: number;
  y: number;
}

/** `from` -> `to` shortened to `length`, or `from` itself for a zero-length edge. */
function along(from: Vector, to: Vector, length: number): Vector {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.hypot(dx, dy);
  if (distance === 0 || length === 0) return { x: from.x, y: from.y };
  const ratio = length / distance;
  return { x: from.x + dx * ratio, y: from.y + dy * ratio };
}

function distance(a: Vector, b: Vector) {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/**
 * The SVG `d` for a polygon, with `radiusPx` rounding every vertex.
 *
 * The radius is clamped PER VERTEX to half the shorter of its two edges, so a
 * corner radius larger than the shape can carry draws the roundest polygon
 * that still exists rather than the self-crossing artefact an unclamped
 * radius produces (AC-S4-4).
 */
export function roundedPolygonPath(points: PolygonPoint[], radiusPx: number): string {
  if (points.length < 3) return '';

  if (!(radiusPx > 0)) {
    const [first, ...rest] = points;
    return `M ${round(first.x)} ${round(first.y)} ${rest
      .map((point) => `L ${round(point.x)} ${round(point.y)}`)
      .join(' ')} Z`;
  }

  const corners = points.map((current, index) => {
    const previous = points[(index - 1 + points.length) % points.length];
    const next = points[(index + 1) % points.length];
    const radius = Math.min(
      radiusPx,
      distance(previous, current) / 2,
      distance(current, next) / 2,
    );
    return {
      enter: along(current, previous, radius),
      corner: current,
      exit: along(current, next, radius),
    };
  });

  const segments = corners.map((corner, index) => {
    const nextEnter = corners[(index + 1) % corners.length].enter;
    return (
      `Q ${round(corner.corner.x)} ${round(corner.corner.y)}` +
      ` ${round(corner.exit.x)} ${round(corner.exit.y)}` +
      ` L ${round(nextEnter.x)} ${round(nextEnter.y)}`
    );
  });

  return `M ${round(corners[0].enter.x)} ${round(corners[0].enter.y)} ${segments.join(' ')} Z`;
}

/**
 * The smallest a refit will let either axis of a layer box become, in mm.
 *
 * A polygon whose corners all line up has a zero-width bounding box, and a
 * zero-width box is a division by zero one line later - and a layer nobody can
 * grab again. Matches the Transformer's own 2mm floor (`TagCanvasEditor.tsx`)
 * so a refit never produces a box the Transformer would immediately reject.
 */
export const MIN_POLYGON_BOX_MM = 2;

export interface PolygonBox {
  /** The layer's own position and size, in millimetres. */
  x: number;
  y: number;
  width: number;
  height: number;
  /** Degrees, the layer's `rotation_deg`. */
  rotation: number;
  /** Corners normalized against the CURRENT box - possibly outside [0, 1]. */
  points: PolygonPoint[];
}

/** Round to micrometres, so a rotation's float noise never reaches the doc. */
function roundMm(value: number) {
  return Number(value.toFixed(3));
}

/** Round a normalized coordinate, same reason, one more digit of room. */
function roundUnit(value: number) {
  return Number(value.toFixed(6));
}

/**
 * Re-fit a layer's BOX around corners that have been dragged out of it (r4b).
 *
 * A corner is normalized against the box, so a drag past the wall means a
 * coordinate outside [0, 1] - which would otherwise draw outside the layer,
 * where the Transformer, the snap guides and the Inspector's W/H all still
 * describe the old box. Growing the box instead keeps every one of those
 * telling the truth, and is what the user asked for: "dragging a corner past
 * the layer box grows the box".
 *
 * The origin moves along the layer's OWN axes, not the page's: a rotated
 * polygon whose x/y were shifted in page space visibly jumped on release,
 * because the box grew in one frame of reference and moved in another.
 */
export function refitPolygon(box: PolygonBox): {
  x: number;
  y: number;
  width: number;
  height: number;
  points: PolygonPoint[];
} {
  const local = box.points.map((point) => ({
    x: point.x * box.width,
    y: point.y * box.height,
  }));
  const xs = local.map((point) => point.x);
  const ys = local.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const width = Math.max(Math.max(...xs) - minX, MIN_POLYGON_BOX_MM);
  const height = Math.max(Math.max(...ys) - minY, MIN_POLYGON_BOX_MM);

  const radians = (box.rotation * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);

  return {
    x: roundMm(box.x + minX * cos - minY * sin),
    y: roundMm(box.y + minX * sin + minY * cos),
    width: roundMm(width),
    height: roundMm(height),
    points: local.map((point) => ({
      x: roundUnit((point.x - minX) / width),
      y: roundUnit((point.y - minY) / height),
    })),
  };
}

/**
 * One corner moved by a normalized delta.
 *
 * NOT clamped to [0, 1] (r4b): a corner dragged past the wall grows the box
 * instead of stopping at it - `refitPolygon` above is where that happens, on
 * drag end. The clamp was the first design, and the user's test of it was
 * simply that the corner stopped following the cursor.
 */
export function movePoint(
  points: PolygonPoint[],
  index: number,
  dx: number,
  dy: number,
): PolygonPoint[] {
  if (index < 0 || index >= points.length) return points.map((p) => ({ x: p.x, y: p.y }));
  return points.map((point, i) =>
    i === index ? { x: point.x + dx, y: point.y + dy } : { x: point.x, y: point.y },
  );
}

/**
 * Edge `index` (vertex `index` to the next one, wrapping) moved by a
 * normalized delta.
 *
 * Both endpoints take the SAME delta and neither is clamped, so the edge
 * stays parallel to itself (AC-S4-2) and the box grows to follow it exactly
 * as it does for a single corner. Clamping each endpoint on its own would
 * have let one corner hit a wall while the other kept travelling, which turns
 * a parallel move into a rotation nobody asked for.
 */
export function moveEdge(
  points: PolygonPoint[],
  index: number,
  dx: number,
  dy: number,
): PolygonPoint[] {
  if (index < 0 || index >= points.length) return points.map((p) => ({ x: p.x, y: p.y }));
  const nextIndex = (index + 1) % points.length;
  return points.map((point, i) =>
    i === index || i === nextIndex
      ? { x: point.x + dx, y: point.y + dy }
      : { x: point.x, y: point.y },
  );
}
