/**
 * Doors and windows: holes in walls, not products.
 *
 * An opening has no price and never reaches a quote. It cannot exist anywhere
 * except inside a wall, so it is stored as an offset ALONG a wall rather than a
 * position in the room: move the wall and the door goes with it, shorten the
 * wall and the door slides inward or stops fitting.
 *
 * Everything is millimetres. `offsetMm` is measured from the wall's start
 * corner to the CENTRE of the opening, which is the number that stays put when
 * the width changes.
 */

import { DEFAULT_GRID_MM, snapToGrid } from './roomGeometry';

export type OpeningKind = 'door' | 'window' | 'opening';

export interface Opening {
  id: string;
  kind: OpeningKind;
  /** Index into the room outline: the wall this hole is cut into. */
  wallIndex: number;
  /** Centre of the opening, measured from the wall's start corner. */
  offsetMm: number;
  widthMm: number;
  heightMm: number;
  /** Height of the wall below the opening. Zero for a door. */
  sillMm: number;
}

/** A standard single leaf door, so stamping one and moving on is the normal case. */
export const DEFAULT_DOOR = { widthMm: 900, heightMm: 2100, sillMm: 0 };

/** A standard window: head level with a door, sill at worktop height. */
export const DEFAULT_WINDOW = { widthMm: 1200, heightMm: 1200, sillMm: 900 };

/** A doorway with no leaf: full height, no sill. */
export const DEFAULT_OPENING = { widthMm: 1000, heightMm: 2100, sillMm: 0 };

export function defaultsFor(kind: OpeningKind) {
  if (kind === 'window') return DEFAULT_WINDOW;
  if (kind === 'opening') return DEFAULT_OPENING;
  return DEFAULT_DOOR;
}

/**
 * Slide an opening inside its wall, or refuse it.
 *
 * Narrowing a 900 door so it fits a 700 wall would put a measurement in the
 * drawing that nobody chose, and somebody would order to it. Refusing is the
 * honest answer; the user widens the wall or picks a narrower door.
 */
export function fitOpening(opening: Opening, wallLength: number): Opening | null {
  if (!Number.isFinite(wallLength) || wallLength <= 0) return null;
  if (opening.widthMm > wallLength) return null;

  const half = opening.widthMm / 2;
  const offsetMm = Math.min(Math.max(opening.offsetMm, half), wallLength - half);
  return offsetMm === opening.offsetMm ? opening : { ...opening, offsetMm };
}

export interface Span {
  start: number;
  end: number;
}

/**
 * What is left of a wall once its openings are cut out.
 *
 * Used to draw the wall as pieces in both views - the cheap alternative to
 * boolean geometry, and the only one that stays fast while somebody drags.
 * Overlapping openings are merged rather than emitting a backwards span.
 */
export function openingSpans(wallLength: number, openings: Opening[]): Span[] {
  const holes = openings
    .map((opening) => ({
      start: opening.offsetMm - opening.widthMm / 2,
      end: opening.offsetMm + opening.widthMm / 2,
    }))
    .sort((a, b) => a.start - b.start);

  const merged: Span[] = [];
  for (const hole of holes) {
    const last = merged[merged.length - 1];
    if (last && hole.start <= last.end) last.end = Math.max(last.end, hole.end);
    else merged.push({ ...hole });
  }

  const spans: Span[] = [];
  let cursor = 0;
  for (const hole of merged) {
    if (hole.start > cursor) spans.push({ start: cursor, end: Math.min(hole.start, wallLength) });
    cursor = Math.max(cursor, hole.end);
  }
  if (cursor < wallLength) spans.push({ start: cursor, end: wallLength });

  return spans.filter((span) => span.end - span.start > 1e-6);
}

export interface Panel {
  bottom: number;
  top: number;
}

/**
 * The bits of wall left above and below an opening.
 *
 * A door leaves a lintel; a window leaves a lintel and a sill. Without these
 * the 3D view shows a slot cut from floor to ceiling, which reads as a missing
 * wall rather than a window.
 */
export function wallPanels(opening: Opening, wallHeightMm: number): Panel[] {
  const panels: Panel[] = [];
  const sill = Math.max(0, Math.min(opening.sillMm, wallHeightMm));
  const head = Math.min(sill + opening.heightMm, wallHeightMm);

  if (sill > 0) panels.push({ bottom: 0, top: sill });
  if (head < wallHeightMm) panels.push({ bottom: head, top: wallHeightMm });
  return panels;
}

export interface EdgeGaps {
  before: number;
  after: number;
}

/**
 * How much wall is left each side of an opening.
 *
 * The same question the clearance chips answer for products, and the one that
 * decides whether a vanity actually fits beside the door.
 */
export function openingEdgeGaps(
  opening: Opening,
  wallLength: number,
  others: Opening[],
): EdgeGaps {
  const start = opening.offsetMm - opening.widthMm / 2;
  const end = opening.offsetMm + opening.widthMm / 2;

  let before = start;
  let after = wallLength - end;

  for (const other of others) {
    if (other.wallIndex !== opening.wallIndex || other.id === opening.id) continue;
    const theirStart = other.offsetMm - other.widthMm / 2;
    const theirEnd = other.offsetMm + other.widthMm / 2;
    if (theirEnd <= start) before = Math.min(before, start - theirEnd);
    else if (theirStart >= end) after = Math.min(after, theirStart - end);
    else if (other.offsetMm >= opening.offsetMm) after = 0;
    else before = 0;
  }

  return { before: Math.max(0, Math.round(before)), after: Math.max(0, Math.round(after)) };
}

/**
 * Keep every opening inside the wall it belongs to.
 *
 * Called after any change to the outline: dragging a wall shorter must not
 * leave a door hanging in space, and one that no longer fits at all is dropped
 * rather than drawn somewhere it cannot be built.
 */
export function fitOpenings(openings: Opening[], wallLengths: number[]): Opening[] {
  return openings
    .map((opening) => {
      const length = wallLengths[opening.wallIndex];
      return length === undefined ? null : fitOpening(opening, length);
    })
    .filter((opening): opening is Opening => opening !== null);
}

/** Wall lengths, in outline order, so callers need no geometry of their own. */
export function wallLengths(outline: { x: number; y: number }[]): number[] {
  if (outline.length < 3) return [];
  return outline.map((point, index) => {
    const next = outline[(index + 1) % outline.length];
    return Math.hypot(next.x - point.x, next.y - point.y);
  });
}

/**
 * Where a dragged opening lands: nearest wall, snapped, and made to fit.
 *
 * The door goes to whichever wall the pointer is nearest, not only the one it
 * started on. Dragging a door round a corner is a thing people do - the plan
 * was right and the wall was wrong - and refusing to cross means deleting it
 * and stamping a new one.
 *
 * This lives here, not in a view, because BOTH views drag openings and they
 * must agree: the same drag in the plan and in 3D has to land on the same wall
 * at the same offset. Two copies of "nearest wall" would drift, and the user
 * would be the one to find out.
 *
 * Returns null when no wall can hold the opening - a wall too short is refused
 * rather than the door being narrowed to a size nobody chose.
 */
export function placeOpeningOnNearestWall(
  opening: Opening,
  outline: { x: number; y: number }[],
  point: { x: number; y: number },
  gridMm: number = DEFAULT_GRID_MM,
): Opening | null {
  if (outline.length < 3) return null;

  let best: { index: number; distance: number; along: number; length: number } | null = null;
  for (let index = 0; index < outline.length; index += 1) {
    const start = outline[index];
    const end = outline[(index + 1) % outline.length];
    const length = Math.hypot(end.x - start.x, end.y - start.y);
    if (length < 1e-6) continue;
    // Distance to the SEGMENT, not the infinite line: past a corner, the wall
    // you are nearest is the one whose end you are near.
    const along =
      ((point.x - start.x) * (end.x - start.x) + (point.y - start.y) * (end.y - start.y)) / length;
    const clamped = Math.min(Math.max(along, 0), length);
    const nearestX = start.x + ((end.x - start.x) / length) * clamped;
    const nearestY = start.y + ((end.y - start.y) / length) * clamped;
    const distance = Math.hypot(point.x - nearestX, point.y - nearestY);
    if (!best || distance < best.distance) best = { index, distance, along, length };
  }
  if (!best) return null;

  return fitOpening(
    { ...opening, wallIndex: best.index, offsetMm: snapToGrid(best.along, gridMm) },
    best.length,
  );
}
