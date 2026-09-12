/**
 * Image crop rect arithmetic (S8, PLAN D8, AC-S8-2/3/6).
 *
 * Normalised [0, 1] against the SOURCE image, applied BEFORE `fit`. Every
 * function here treats an absent `cropRect` as the whole image
 * (`FULL_CROP`), so a template saved before this round renders exactly as
 * it did (AC-S8-6) without a caller having to branch on it first.
 */

import { describe, expect, it } from 'vitest';

import {
  CROP_HANDLE_ANCHORS,
  FULL_CROP,
  cropPixels,
  cropRectFromDrag,
  cropWindowStyle,
  isCropped,
  panCropRect,
  resolvedCropRect,
  type CropRect,
} from './image-crop';

describe('resolvedCropRect (AC-S8-6)', () => {
  it('absent (undefined/null) resolves to the whole image', () => {
    expect(resolvedCropRect(undefined)).toEqual(FULL_CROP);
    expect(resolvedCropRect(null)).toEqual(FULL_CROP);
  });

  it('passes a valid in-bounds rect through unchanged', () => {
    const rect: CropRect = { x: 0.1, y: 0.2, width: 0.5, height: 0.4 };
    expect(resolvedCropRect(rect)).toEqual(rect);
  });

  it('clamps a rect that would run past the right/bottom edge back inside [0, 1]', () => {
    const rect = resolvedCropRect({ x: 0.8, y: 0.9, width: 0.5, height: 0.5 });
    expect(rect.x + rect.width).toBeLessThanOrEqual(1);
    expect(rect.y + rect.height).toBeLessThanOrEqual(1);
    expect(rect.width).toBe(0.5);
    expect(rect.x).toBeCloseTo(0.5);
  });

  it('clamps a negative origin back to 0', () => {
    const rect = resolvedCropRect({ x: -0.3, y: -0.1, width: 0.4, height: 0.4 });
    expect(rect.x).toBe(0);
    expect(rect.y).toBe(0);
  });

  it('never collapses to a zero-sized window', () => {
    const rect = resolvedCropRect({ x: 0.5, y: 0.5, width: 0, height: -0.2 });
    expect(rect.width).toBeGreaterThan(0);
    expect(rect.height).toBeGreaterThan(0);
  });
});

describe('isCropped', () => {
  it('is false for an absent cropRect', () => {
    expect(isCropped(undefined)).toBe(false);
    expect(isCropped(null)).toBe(false);
  });

  it('is false for a rect that IS the whole image', () => {
    expect(isCropped({ x: 0, y: 0, width: 1, height: 1 })).toBe(false);
  });

  it('is true for anything selecting less than the whole image', () => {
    expect(isCropped({ x: 0.1, y: 0, width: 0.8, height: 1 })).toBe(true);
    expect(isCropped({ x: 0, y: 0, width: 0.5, height: 0.5 })).toBe(true);
  });
});

describe('cropPixels (normalised -> source pixels)', () => {
  const image = { width: 2000, height: 1000 };

  it('absent cropRect is the FULL image in pixels', () => {
    expect(cropPixels(undefined, image)).toEqual({ x: 0, y: 0, width: 2000, height: 1000 });
  });

  it('scales a normalised rect by the source image dimensions', () => {
    expect(cropPixels({ x: 0.25, y: 0.5, width: 0.5, height: 0.25 }, image)).toEqual({
      x: 500,
      y: 500,
      width: 1000,
      height: 250,
    });
  });

  it('clamps an out-of-bounds rect before scaling', () => {
    const px = cropPixels({ x: 0.9, y: 0.9, width: 0.5, height: 0.5 }, image);
    expect(px.x + px.width).toBeLessThanOrEqual(2000);
    expect(px.y + px.height).toBeLessThanOrEqual(1000);
  });
});

describe('cropRectFromDrag (S8, AC-S8-2)', () => {
  const base: CropRect = { x: 0.2, y: 0.2, width: 0.4, height: 0.4 };

  it('the middle of an axis (fx or fy 0.5) is left untouched by that axis', () => {
    const centerLeft = CROP_HANDLE_ANCHORS.find((a) => a.name === 'middle-left')!;
    const next = cropRectFromDrag(base, centerLeft, 0.1, 0.5);
    // fy is 0.5 for a middle-* handle - the y/height are untouched by dy.
    expect(next.y).toBe(base.y);
    expect(next.height).toBe(base.height);
  });

  it('a left-edge handle (fx 0) moves x and shrinks width by the same delta', () => {
    const topLeft = CROP_HANDLE_ANCHORS.find((a) => a.name === 'top-left')!;
    const next = cropRectFromDrag(base, topLeft, 0.1, 0.1);
    expect(next.x).toBeCloseTo(0.3);
    expect(next.width).toBeCloseTo(0.3);
    expect(next.y).toBeCloseTo(0.3);
    expect(next.height).toBeCloseTo(0.3);
  });

  it('a right-edge handle (fx 1) grows width without moving x', () => {
    const middleRight = CROP_HANDLE_ANCHORS.find((a) => a.name === 'middle-right')!;
    const next = cropRectFromDrag(base, middleRight, 0.1, 0);
    expect(next.x).toBe(base.x);
    expect(next.width).toBeCloseTo(0.5);
  });

  it('a bottom-edge handle (fy 1) grows height without moving y', () => {
    const bottomCenter = CROP_HANDLE_ANCHORS.find((a) => a.name === 'bottom-center')!;
    const next = cropRectFromDrag(base, bottomCenter, 0, 0.1);
    expect(next.y).toBe(base.y);
    expect(next.height).toBeCloseTo(0.5);
  });

  it('every handle stays clamped inside the source bounds, never inverting', () => {
    const bottomRight = CROP_HANDLE_ANCHORS.find((a) => a.name === 'bottom-right')!;
    // Drag WAY past the opposite corner.
    const next = cropRectFromDrag(base, bottomRight, 5, 5);
    expect(next.x + next.width).toBeLessThanOrEqual(1);
    expect(next.y + next.height).toBeLessThanOrEqual(1);
    expect(next.width).toBeGreaterThan(0);
    expect(next.height).toBeGreaterThan(0);
  });

  it('covers all 8 named anchors', () => {
    expect(CROP_HANDLE_ANCHORS.map((a) => a.name).sort()).toEqual(
      [
        'top-left',
        'top-center',
        'top-right',
        'middle-left',
        'middle-right',
        'bottom-left',
        'bottom-center',
        'bottom-right',
      ].sort(),
    );
  });
});

describe('panCropRect (S8, AC-S8-2)', () => {
  it('moves the window without changing its size', () => {
    const base: CropRect = { x: 0.2, y: 0.2, width: 0.3, height: 0.3 };
    const next = panCropRect(base, 0.1, -0.05);
    expect(next.width).toBe(base.width);
    expect(next.height).toBe(base.height);
    expect(next.x).toBeCloseTo(0.3);
    expect(next.y).toBeCloseTo(0.15);
  });

  it('cannot pan the window past the source bounds', () => {
    const base: CropRect = { x: 0.8, y: 0.8, width: 0.3, height: 0.3 };
    const next = panCropRect(base, 0.5, 0.5);
    expect(next.x + next.width).toBeLessThanOrEqual(1);
    expect(next.y + next.height).toBeLessThanOrEqual(1);
  });
});

describe('cropWindowStyle (print path, S8)', () => {
  it('the whole image (FULL_CROP) is a 100%-sized window at 0,0', () => {
    const layout = cropWindowStyle(undefined, { width: 800, height: 400 });
    expect(layout.img).toEqual({ width: '100%', height: '100%', left: '0%', top: '0%' });
    expect(layout.aspectRatio).toBe('800 / 400');
  });

  it('a cropped rect scales the img beyond 100% and offsets it negatively', () => {
    const layout = cropWindowStyle(
      { x: 0.25, y: 0, width: 0.5, height: 1 },
      { width: 800, height: 400 },
    );
    // Cropped to half the width - the underlying image is drawn at 200% so
    // that half fills the window.
    expect(layout.img.width).toBe('200%');
    expect(layout.img.height).toBe('100%');
    expect(layout.img.left).toBe('-50%');
    // `${-0}` stringifies as "0" in JS, not "-0" - y is 0 here (no vertical
    // crop), so the offset really is exactly zero, just written positive.
    expect(layout.img.top).toBe('0%');
    expect(layout.aspectRatio).toBe('400 / 400');
  });
});
