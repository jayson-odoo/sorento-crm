import { describe, expect, it } from 'vitest';
import { snapElement } from './accessory-card';

const area = { width_mm: 40, height_mm: 30 };
const box = (x: number, y: number, w = 10, h = 5) => ({ x_mm: x, y_mm: y, width_mm: w, height_mm: h });

describe('snapElement', () => {
  it('pulls the left edge onto the card edge and the top onto the card top, with guides', () => {
    const out = snapElement(box(0.6, 0.4), [], area);
    expect(out.x_mm).toBeCloseTo(0);
    expect(out.y_mm).toBeCloseTo(0);
    expect(out.guides).toEqual([
      { orientation: 'vertical', position_mm: 0 },
      { orientation: 'horizontal', position_mm: 0 },
    ]);
  });

  it('snaps the centre onto the card centre line', () => {
    const out = snapElement(box(14.7, 12), [], area);
    expect(out.x_mm).toBeCloseTo(15);
  });

  it('snaps to another element edge, and the right edge to the card right', () => {
    const out = snapElement(box(20.5, 10), [box(5, 10, 15)], area);
    expect(out.x_mm).toBeCloseTo(20);
    expect(snapElement(box(29.4, 10), [], area).x_mm).toBeCloseTo(30);
  });

  it('leaves an element alone when nothing is within 1 mm', () => {
    const out = snapElement(box(7, 7), [], area);
    expect(out).toEqual({ x_mm: 7, y_mm: 7, guides: [] });
  });
});
