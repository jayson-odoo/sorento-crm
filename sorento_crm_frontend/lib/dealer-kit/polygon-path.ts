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

/** The box's own four corners: what a polygon looks like until one is moved. */
export const DEFAULT_POLYGON_POINTS: PolygonPoint[] = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
];

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
 * Anything that could not be drawn - absent, or fewer than three corners -
 * falls back to the box, rather than leaving the layer invisible.
 */
export function polygonPoints(props: { points?: PolygonPoint[] | null }): PolygonPoint[] {
  const points = props.points;
  if (!Array.isArray(points) || points.length < 3) return DEFAULT_POLYGON_POINTS;
  return points;
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
  if (index < 0 || index >= points.length) return points;
  return points.map((point, i) =>
    i === index ? { x: clamp01(point.x + dx), y: clamp01(point.y + dy) } : point,
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
  if (index < 0 || index >= points.length) return points;
  const nextIndex = (index + 1) % points.length;
  const a = points[index];
  const b = points[nextIndex];
  const clampedX = Math.min(Math.min(1 - a.x, 1 - b.x), Math.max(Math.max(-a.x, -b.x), dx));
  const clampedY = Math.min(Math.min(1 - a.y, 1 - b.y), Math.max(Math.max(-a.y, -b.y), dy));
  return points.map((point, i) =>
    i === index || i === nextIndex
      ? { x: clamp01(point.x + clampedX), y: clamp01(point.y + clampedY) }
      : point,
  );
}
