/**
 * Polygon geometry for the free-corner shape (S4, AC-S4-2/3/4/8).
 *
 * The path builder is the ONE place that decides what a polygon looks like -
 * the Konva canvas and the print page both draw the string it returns - so
 * the shape of that string, the radius clamp and the move clamps are pinned
 * here rather than through either renderer.
 */

import { describe, expect, it } from 'vitest';

import {
  DEFAULT_POLYGON_POINTS,
  moveEdge,
  movePoint,
  polygonPoints,
  roundedPolygonPath,
  scalePolygonPoints,
} from './polygon-path';

const SQUARE_PX = [
  { x: 0, y: 0 },
  { x: 100, y: 0 },
  { x: 100, y: 50 },
  { x: 0, y: 50 },
];

describe('polygonPoints (AC-S4-8)', () => {
  it('falls back to the four corners when a document carries no points', () => {
    expect(polygonPoints({})).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ]);
    expect(polygonPoints({ points: undefined })).toEqual(DEFAULT_POLYGON_POINTS);
  });

  it('keeps the layer own points when it has them', () => {
    const points = [
      { x: 0.2, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ];
    expect(polygonPoints({ points })).toEqual(points);
  });

  it('ignores a degenerate list that could not be drawn', () => {
    expect(polygonPoints({ points: [{ x: 0, y: 0 }, { x: 1, y: 1 }] })).toEqual(
      DEFAULT_POLYGON_POINTS,
    );
  });

  it('falls back to the box when a coordinate is not a finite number', () => {
    // A refit divides by the box size, so one zero-width axis anywhere
    // upstream writes NaN into the document. Drawing the box beats drawing
    // nothing at all, and beats a path string full of NaN.
    expect(
      polygonPoints({
        points: [
          { x: 0, y: 0 },
          { x: Number.NaN, y: 0 },
          { x: 1, y: 1 },
          { x: 0, y: 1 },
        ],
      }),
    ).toEqual(DEFAULT_POLYGON_POINTS);
    expect(
      polygonPoints({
        points: [
          { x: 0, y: 0 },
          { x: Number.POSITIVE_INFINITY, y: 0 },
          { x: 1, y: 1 },
        ],
      }),
    ).toEqual(DEFAULT_POLYGON_POINTS);
  });

  it('never hands back the shared default itself, so a caller cannot mutate it', () => {
    const first = polygonPoints({});
    expect(first).not.toBe(DEFAULT_POLYGON_POINTS);
    first[0].x = 0.5;
    expect(DEFAULT_POLYGON_POINTS[0]).toEqual({ x: 0, y: 0 });
    expect(polygonPoints({})[0]).toEqual({ x: 0, y: 0 });
  });

  it('copies the layer own points rather than aliasing them', () => {
    const points = [
      { x: 0.2, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
    ];
    const out = polygonPoints({ points });
    expect(out[0]).not.toBe(points[0]);
    out[0].x = 0.9;
    expect(points[0].x).toBe(0.2);
  });
});

describe('scalePolygonPoints', () => {
  it('maps normalized points onto a box, so both renderers scale identically', () => {
    expect(scalePolygonPoints(DEFAULT_POLYGON_POINTS, 100, 50)).toEqual(SQUARE_PX);
  });
});

describe('roundedPolygonPath', () => {
  it('draws plain segments at radius 0', () => {
    expect(roundedPolygonPath(SQUARE_PX, 0)).toBe('M 0 0 L 100 0 L 100 50 L 0 50 Z');
  });

  it('rounds every vertex once a radius is set', () => {
    const d = roundedPolygonPath(SQUARE_PX, 10);
    // Four corners, four curves.
    expect(d.match(/Q/g)).toHaveLength(4);
    expect(d.startsWith('M ')).toBe(true);
    expect(d.endsWith('Z')).toBe(true);
    // The straight run along the top edge stops 10px short of each corner.
    expect(d).toContain('Q 100 0 100 10');
  });

  it('clamps the radius to half the shorter adjacent edge (AC-S4-4)', () => {
    // The 50px edges cap every vertex at 25, so an absurd radius draws the
    // same path as the largest usable one instead of an artefact.
    expect(roundedPolygonPath(SQUARE_PX, 9999)).toBe(roundedPolygonPath(SQUARE_PX, 25));
    expect(roundedPolygonPath(SQUARE_PX, 9999)).not.toContain('NaN');
  });

  it('never emits NaN for a collapsed polygon', () => {
    const collapsed = [
      { x: 5, y: 5 },
      { x: 5, y: 5 },
      { x: 5, y: 5 },
    ];
    expect(roundedPolygonPath(collapsed, 4)).not.toContain('NaN');
  });
});

describe('movePoint (AC-S4-2/3)', () => {
  it('moves only the dragged corner and returns a new array', () => {
    const next = movePoint(DEFAULT_POLYGON_POINTS, 1, -0.3, 0.25);
    expect(next[1]).toEqual({ x: 0.7, y: 0.25 });
    expect(next[0]).toEqual({ x: 0, y: 0 });
    expect(next[2]).toEqual({ x: 1, y: 1 });
    expect(next[3]).toEqual({ x: 0, y: 1 });
    expect(next).not.toBe(DEFAULT_POLYGON_POINTS);
    expect(DEFAULT_POLYGON_POINTS[1]).toEqual({ x: 1, y: 0 });
  });

  it('clamps the corner to the layer box', () => {
    const next = movePoint(DEFAULT_POLYGON_POINTS, 0, -5, 7);
    expect(next[0]).toEqual({ x: 0, y: 1 });
  });

  it('leaves the points alone for an index that is not there', () => {
    expect(movePoint(DEFAULT_POLYGON_POINTS, 9, 0.1, 0.1)).toEqual(DEFAULT_POLYGON_POINTS);
  });

  it('rebuilds every corner, so the result shares no object with its input', () => {
    const next = movePoint(DEFAULT_POLYGON_POINTS, 1, 0.1, 0);
    next.forEach((point, index) => expect(point).not.toBe(DEFAULT_POLYGON_POINTS[index]));
    expect(DEFAULT_POLYGON_POINTS[0]).toEqual({ x: 0, y: 0 });
  });
});

describe('moveEdge (AC-S4-2/3)', () => {
  it('moves both endpoints of the edge by the same delta', () => {
    const next = moveEdge(DEFAULT_POLYGON_POINTS, 0, 0, 0.4);
    expect(next[0]).toEqual({ x: 0, y: 0.4 });
    expect(next[1]).toEqual({ x: 1, y: 0.4 });
    // The other two corners stay where they were.
    expect(next[2]).toEqual({ x: 1, y: 1 });
    expect(next[3]).toEqual({ x: 0, y: 1 });
  });

  it('rebuilds every corner, so the result shares no object with its input', () => {
    const next = moveEdge(DEFAULT_POLYGON_POINTS, 0, 0, 0.1);
    next.forEach((point, index) => expect(point).not.toBe(DEFAULT_POLYGON_POINTS[index]));
  });

  it('wraps for the last edge, which closes the polygon', () => {
    const next = moveEdge(DEFAULT_POLYGON_POINTS, 3, 0.25, 0);
    expect(next[3]).toEqual({ x: 0.25, y: 1 });
    expect(next[0]).toEqual({ x: 0.25, y: 0 });
  });

  it('clamps the delta, not each endpoint, so the edge stays parallel to itself', () => {
    const slanted = [
      { x: 0, y: 0 },
      { x: 0.5, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ];
    // 0.9 to the right would push the 0.5 corner to 1.4; the whole edge can
    // only travel 0.5 before that corner hits the wall.
    const next = moveEdge(slanted, 0, 0.9, 0);
    expect(next[0]).toEqual({ x: 0.5, y: 0 });
    expect(next[1]).toEqual({ x: 1, y: 0 });
  });
});
