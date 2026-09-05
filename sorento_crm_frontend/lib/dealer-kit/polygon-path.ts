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

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value));
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

/** One corner moved by a normalized delta, clamped to the layer box. */
export function movePoint(
  points: PolygonPoint[],
  index: number,
  dx: number,
  dy: number,
): PolygonPoint[] {
  if (index < 0 || index >= points.length) return points.map((p) => ({ x: p.x, y: p.y }));
  return points.map((point, i) =>
    i === index
      ? { x: clamp01(point.x + dx), y: clamp01(point.y + dy) }
      : { x: point.x, y: point.y },
  );
}

/**
 * Edge `index` (vertex `index` to the next one, wrapping) moved by a
 * normalized delta.
 *
 * The DELTA is clamped, not each endpoint on its own: clamping them
 * separately would let one corner hit the wall while the other kept
 * travelling, which turns a parallel move into a rotation the user never
 * asked for (AC-S4-2 "moves that edge parallel to itself").
 */
export function moveEdge(
  points: PolygonPoint[],
  index: number,
  dx: number,
  dy: number,
): PolygonPoint[] {
  if (index < 0 || index >= points.length) return points.map((p) => ({ x: p.x, y: p.y }));
  const nextIndex = (index + 1) % points.length;
  const a = points[index];
  const b = points[nextIndex];
  const clampedX = Math.min(Math.min(1 - a.x, 1 - b.x), Math.max(Math.max(-a.x, -b.x), dx));
  const clampedY = Math.min(Math.min(1 - a.y, 1 - b.y), Math.max(Math.max(-a.y, -b.y), dy));
  return points.map((point, i) =>
    i === index || i === nextIndex
      ? { x: clamp01(point.x + clampedX), y: clamp01(point.y + clampedY) }
      : { x: point.x, y: point.y },
  );
}
