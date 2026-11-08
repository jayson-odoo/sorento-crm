/**
 * QUOTE-CERT-TAB red tests: pure geometry for the PdfViewer box overlay.
 *
 * Written BEFORE `components/common/pdf-viewer/box-geometry.ts`. Contract assumed here (the UAC pins
 * only the Box shape): a Box is `{ page, x, y, w, h, product_id }` where x/y/w/h are FRACTIONS (0..1)
 * of the page as displayed, origin top-left. `dx`/`dy` of moveBox/resizeBox are FRACTIONS of the page
 * too. `rectFromDrag` takes pixel points and the page size in pixels. Corners are 'nw' | 'ne' | 'sw' | 'se'.
 */
import { describe, expect, it } from 'vitest';

import { boxToStyle, moveBox, rectFromDrag, resizeBox } from '../box-geometry';

const box = { page: 1, x: 0.25, y: 0.5, w: 0.125, h: 0.0625, product_id: null as string | null };
const PAGE = { width: 600, height: 800 };

describe('boxToStyle', () => {
  it('maps fractions to percentage strings', () => {
    expect(boxToStyle(box)).toEqual({ left: '25%', top: '50%', width: '12.5%', height: '6.25%' });
  });

  it('maps the whole page to 100%', () => {
    expect(boxToStyle({ ...box, x: 0, y: 0, w: 1, h: 1 })).toEqual({
      left: '0%',
      top: '0%',
      width: '100%',
      height: '100%',
    });
  });
});

describe('rectFromDrag', () => {
  it('turns a drag in pixels into page fractions', () => {
    const r = rectFromDrag({ x: 60, y: 80 }, { x: 180, y: 160 }, PAGE);
    expect(r.x).toBeCloseTo(0.1);
    expect(r.y).toBeCloseTo(0.1);
    expect(r.w).toBeCloseTo(0.2);
    expect(r.h).toBeCloseTo(0.1);
  });

  it('normalises a drag up and to the left', () => {
    const r = rectFromDrag({ x: 180, y: 160 }, { x: 60, y: 80 }, PAGE);
    expect(r.x).toBeCloseTo(0.1);
    expect(r.y).toBeCloseTo(0.1);
    expect(r.w).toBeCloseTo(0.2);
    expect(r.h).toBeCloseTo(0.1);
  });

  it('clamps a drag that leaves the page to [0, 1]', () => {
    const r = rectFromDrag({ x: 540, y: 720 }, { x: 900, y: 1200 }, PAGE);
    expect(r.x).toBeCloseTo(0.9);
    expect(r.y).toBeCloseTo(0.9);
    expect(r.x + r.w).toBeLessThanOrEqual(1 + 1e-9);
    expect(r.y + r.h).toBeLessThanOrEqual(1 + 1e-9);
    const neg = rectFromDrag({ x: 30, y: 40 }, { x: -100, y: -100 }, PAGE);
    expect(neg.x).toBe(0);
    expect(neg.y).toBe(0);
    expect(neg.w).toBeCloseTo(0.05);
    expect(neg.h).toBeCloseTo(0.05);
  });
});

describe('moveBox', () => {
  it('moves by a fraction and keeps size and page', () => {
    const moved = moveBox(box, 0.1, -0.25);
    expect(moved.x).toBeCloseTo(0.35);
    expect(moved.y).toBeCloseTo(0.25);
    expect(moved.w).toBe(box.w);
    expect(moved.h).toBe(box.h);
    expect(moved.page).toBe(1);
  });

  it('never leaves the page', () => {
    const right = moveBox(box, 5, 5);
    expect(right.x + right.w).toBeLessThanOrEqual(1 + 1e-9);
    expect(right.y + right.h).toBeLessThanOrEqual(1 + 1e-9);
    const left = moveBox(box, -5, -5);
    expect(left.x).toBe(0);
    expect(left.y).toBe(0);
  });
});

describe('resizeBox', () => {
  it('the south-east corner grows width and height', () => {
    const r = resizeBox(box, 'se', 0.1, 0.1);
    expect(r.x).toBeCloseTo(0.25);
    expect(r.y).toBeCloseTo(0.5);
    expect(r.w).toBeCloseTo(0.225);
    expect(r.h).toBeCloseTo(0.1625);
  });

  it('the north-west corner moves the origin and keeps the opposite corner fixed', () => {
    const r = resizeBox(box, 'nw', -0.05, -0.05);
    expect(r.x).toBeCloseTo(0.2);
    expect(r.y).toBeCloseTo(0.45);
    expect(r.x + r.w).toBeCloseTo(0.375);
    expect(r.y + r.h).toBeCloseTo(0.5625);
  });

  it('never shrinks below 0.005', () => {
    const r = resizeBox(box, 'se', -5, -5);
    expect(r.w).toBeCloseTo(0.005);
    expect(r.h).toBeCloseTo(0.005);
    const nw = resizeBox(box, 'nw', 5, 5);
    expect(nw.w).toBeCloseTo(0.005);
    expect(nw.h).toBeCloseTo(0.005);
    expect(nw.x + nw.w).toBeCloseTo(0.375);
  });

  it('is clamped inside the page', () => {
    const r = resizeBox(box, 'se', 5, 5);
    expect(r.x + r.w).toBeLessThanOrEqual(1 + 1e-9);
    expect(r.y + r.h).toBeLessThanOrEqual(1 + 1e-9);
    const o = resizeBox(box, 'nw', -5, -5);
    expect(o.x).toBe(0);
    expect(o.y).toBe(0);
  });
});
