/**
 * PRICETAG-DESIGNER-GAPS item 1: an image layer can be mirrored. One helper
 * per renderer, both read the same two flags, so canvas and print agree.
 */
import { describe, expect, it } from 'vitest';
import { cssFlipTransform, konvaFlip } from './image-flip';

describe('cssFlipTransform (print + preview)', () => {
  it('is undefined when the layer is not flipped (old documents unchanged)', () => {
    expect(cssFlipTransform({})).toBeUndefined();
    expect(cssFlipTransform({ flipX: false, flipY: false })).toBeUndefined();
  });

  it('mirrors left-right for flipX', () => {
    expect(cssFlipTransform({ flipX: true })).toBe('scale(-1, 1)');
  });

  it('mirrors top-bottom for flipY', () => {
    expect(cssFlipTransform({ flipY: true })).toBe('scale(1, -1)');
  });

  it('does both at once', () => {
    expect(cssFlipTransform({ flipX: true, flipY: true })).toBe('scale(-1, -1)');
  });
});

describe('konvaFlip (canvas)', () => {
  it('is null when the layer is not flipped', () => {
    expect(konvaFlip({}, 60, 20)).toBeNull();
  });

  it('mirrors in place about the box: flipX moves the origin to the right edge', () => {
    expect(konvaFlip({ flipX: true }, 60, 20)).toEqual({ x: 60, y: 0, scaleX: -1, scaleY: 1 });
  });

  it('flipY moves the origin to the bottom edge', () => {
    expect(konvaFlip({ flipY: true }, 60, 20)).toEqual({ x: 0, y: 20, scaleX: 1, scaleY: -1 });
  });
});
