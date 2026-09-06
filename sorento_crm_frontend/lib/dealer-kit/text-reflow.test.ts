/**
 * The scale -> size conversion behind live text reflow (D8, S6).
 *
 * Konva's Transformer resizes a node by writing a SCALE, not a new width and
 * height - great for a shape, wrong for a text box, whose font must stay put
 * while the box it wraps inside changes shape. `reflowedTextSize` is the one
 * multiplication both the live `onTransform` handler and the existing
 * `onTransformEnd` commit have to agree on, pulled out so the corner-handle
 * and flip cases are pinned once rather than re-derived by hand in two
 * places.
 */

import { describe, expect, it } from 'vitest';

import { paddedBox, reflowedTextSize } from './text-reflow';

describe('reflowedTextSize', () => {
  it('is the identity at scale 1 (no drag yet)', () => {
    expect(reflowedTextSize(100, 40, 1, 1)).toEqual({ width: 100, height: 40 });
  });

  it('scales width and height independently for an edge handle', () => {
    // Middle-right: only X grows.
    expect(reflowedTextSize(100, 40, 1.5, 1)).toEqual({ width: 150, height: 40 });
    // Bottom-center: only Y grows.
    expect(reflowedTextSize(100, 40, 1, 0.5)).toEqual({ width: 100, height: 20 });
  });

  it('scales both axes together for a corner handle', () => {
    expect(reflowedTextSize(100, 40, 2, 2)).toEqual({ width: 200, height: 80 });
  });

  it('shrinks toward, but never crosses into, a degenerate size', () => {
    expect(reflowedTextSize(100, 40, 0.1, 0.1)).toEqual({ width: 10, height: 4 });
  });

  it('takes the absolute value of a flipped (negative) scale', () => {
    // Dragging a handle past the box's opposite edge flips Konva's scale
    // sign; the box itself never has negative width or height.
    expect(reflowedTextSize(100, 40, -1, 1)).toEqual({ width: 100, height: 40 });
    expect(reflowedTextSize(100, 40, 1, -0.5)).toEqual({ width: 100, height: 20 });
  });
});

describe('paddedBox (S3, AC-S3-1/2/3/4)', () => {
  it('is the whole box, at the origin, when there is no padding', () => {
    expect(paddedBox(100, 40, undefined)).toEqual({ x: 0, y: 0, width: 100, height: 40 });
    expect(paddedBox(100, 40, { top: 0, right: 0, bottom: 0, left: 0 })).toEqual({
      x: 0,
      y: 0,
      width: 100,
      height: 40,
    });
  });

  it('insets by each side, in the same units as width/height (AC-S3-1)', () => {
    expect(paddedBox(100, 40, { top: 2, right: 4, bottom: 6, left: 8 })).toEqual({
      x: 8,
      y: 2,
      width: 88,
      height: 32,
    });
  });

  it('scales the padding when the caller works in a different unit (px vs mm)', () => {
    // The canvas passes padding in mm and a px-per-mm scale; a 2mm pad at 3
    // px/mm insets by 6px on that side.
    expect(paddedBox(120, 60, { top: 2, right: 0, bottom: 0, left: 4 }, 3)).toEqual({
      x: 12,
      y: 6,
      width: 108,
      height: 54,
    });
  });

  it('clamps to a zero-size, zero-origin box rather than going negative (AC-S3-4)', () => {
    expect(paddedBox(20, 10, { top: 20, right: 20, bottom: 0, left: 0 })).toEqual({
      x: 0,
      y: 10,
      width: 0,
      height: 0,
    });
  });
});
