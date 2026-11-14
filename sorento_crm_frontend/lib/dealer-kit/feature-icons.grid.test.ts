/**
 * PRICETAG-DESIGNER-FEEDBACK B1, AC-7.1 to AC-7.5: spec icon rows, the pure layout.
 *
 * `featureIconGrid(count, { iconSize_mm, gap_mm, align, columns?, rows? }, boxWidth_mm,
 * boxHeight_mm)` returns `{ positions: {x_mm, y_mm}[], iconSize_mm, height_mm, overflow }`,
 * row-major, left to right, rows stacked from the top. It never hides an icon (owner Q4): icons
 * shrink to a 4 mm minimum, then the grid grows past the box and says so. Written test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import * as featureIcons from './feature-icons';
import { featureIconRow } from './feature-icons';

type GridProps = {
  iconSize_mm: number;
  gap_mm: number;
  align: 'left' | 'center' | 'right';
  columns?: number;
  rows?: number;
};
type Grid = {
  positions: { x_mm: number; y_mm: number }[];
  iconSize_mm: number;
  height_mm: number;
  overflow: boolean;
};

function grid(count: number, props: GridProps, boxWidth_mm: number, boxHeight_mm: number): Grid {
  const fn = (featureIcons as unknown as Record<string, unknown>).featureIconGrid;
  expect(typeof fn, 'featureIconGrid is exported from lib/dealer-kit/feature-icons').toBe('function');
  return (fn as (...args: unknown[]) => Grid)(count, props, boxWidth_mm, boxHeight_mm);
}

const xs = (g: Grid) => g.positions.map((p) => p.x_mm);
const ys = (g: Grid) => g.positions.map((p) => p.y_mm);
const rowSizes = (g: Grid) => {
  const counts = new Map<number, number>();
  for (const p of g.positions) counts.set(p.y_mm, (counts.get(p.y_mm) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => a[0] - b[0]).map(([, n]) => n);
};
const close = (actual: number[], expected: number[]) => {
  expect(actual).toHaveLength(expected.length);
  actual.forEach((value, i) => expect(value, `index ${i}`).toBeCloseTo(expected[i], 6));
};

const base: GridProps = { iconSize_mm: 10, gap_mm: 2, align: 'left' };

describe('featureIconGrid: shape (AC-7.1)', () => {
  it('returns row-major positions, the icon size, the height and no overflow when it fits', () => {
    const g = grid(3, base, 100, 20);
    expect(g.positions).toEqual([
      { x_mm: 0, y_mm: 0 },
      { x_mm: 12, y_mm: 0 },
      { x_mm: 24, y_mm: 0 },
    ]);
    expect(g.iconSize_mm).toBe(10);
    expect(g.height_mm).toBeCloseTo(10, 6);
    expect(g.overflow).toBe(false);
  });

  it('no icons: no positions, no overflow', () => {
    const g = grid(0, base, 100, 20);
    expect(g.positions).toEqual([]);
    expect(g.overflow).toBe(false);
  });
});

describe('featureIconGrid: columns and rows (AC-7.2)', () => {
  it('columns fixes icons per row', () => {
    const g = grid(5, { ...base, columns: 2 }, 100, 100);
    close(xs(g), [0, 12, 0, 12, 0]);
    close(ys(g), [0, 0, 12, 12, 24]);
    expect(g.height_mm).toBeCloseTo(34, 6);
    expect(g.overflow).toBe(false);
  });

  it('rows fixes the row count: 7 icons in 2 rows is 4 then 3', () => {
    const g = grid(7, { ...base, rows: 2 }, 100, 100);
    expect(rowSizes(g)).toEqual([4, 3]);
    close(xs(g), [0, 12, 24, 36, 0, 12, 24]);
    close(ys(g), [0, 0, 0, 0, 12, 12, 12]);
    expect(g.height_mm).toBeCloseTo(22, 6);
  });

  it('both auto: as many per row as fit, then wrap', () => {
    // 50 mm holds 4 icons of 10 with gaps of 2 (46 mm), not 5 (58 mm).
    const g = grid(6, base, 50, 100);
    expect(rowSizes(g)).toEqual([4, 2]);
    close(xs(g), [0, 12, 24, 36, 0, 12]);
    close(ys(g), [0, 0, 0, 0, 12, 12]);
  });

  it('both auto: an icon that exactly fills the row is kept on it', () => {
    const g = grid(4, base, 46, 100);
    expect(rowSizes(g)).toEqual([4]);
  });
});

describe('featureIconGrid: never hide (AC-7.3)', () => {
  it('every icon gets a position', () => {
    for (const count of [1, 5, 9, 17, 40]) {
      expect(grid(count, base, 30, 10).positions).toHaveLength(count);
    }
  });

  it('shrinks the icons to fit the box height before growing', () => {
    // At 10 mm, 10 icons need 3 rows (34 mm) in a 16 mm tall box; at 7 mm, 5 per row in 2 rows fit.
    const g = grid(10, base, 50, 16);
    expect(g.positions).toHaveLength(10);
    expect(g.iconSize_mm).toBeLessThan(10);
    expect(g.iconSize_mm).toBeGreaterThanOrEqual(4);
    expect(g.overflow).toBe(false);
    expect(g.height_mm).toBeLessThanOrEqual(16 + 1e-6);
    for (const p of g.positions) {
      expect(p.x_mm + g.iconSize_mm).toBeLessThanOrEqual(50 + 1e-6);
      expect(p.y_mm + g.iconSize_mm).toBeLessThanOrEqual(16 + 1e-6);
    }
  });

  it('stops at 4 mm, then grows past the box and reports overflow', () => {
    const g = grid(30, base, 50, 10);
    expect(g.positions).toHaveLength(30);
    expect(g.iconSize_mm).toBeCloseTo(4, 6);
    expect(g.overflow).toBe(true);
    expect(g.height_mm).toBeGreaterThan(10);
    const bottom = Math.max(...g.positions.map((p) => p.y_mm)) + g.iconSize_mm;
    expect(g.height_mm).toBeCloseTo(bottom, 6);
    for (const p of g.positions) expect(p.x_mm + g.iconSize_mm).toBeLessThanOrEqual(50 + 1e-6);
  });

  it('does not shrink icons that already fit', () => {
    const g = grid(4, base, 100, 10);
    expect(g.iconSize_mm).toBe(10);
    expect(g.overflow).toBe(false);
  });
});

describe('featureIconGrid: align per row, rows from the top (AC-7.4)', () => {
  it('center aligns each row on its own', () => {
    // Row 1: 4 icons = 46 mm, start 27. Row 2: 3 icons = 34 mm, start 33.
    const g = grid(7, { ...base, rows: 2, align: 'center' }, 100, 100);
    close(xs(g), [27, 39, 51, 63, 33, 45, 57]);
    close(ys(g), [0, 0, 0, 0, 12, 12, 12]);
  });

  it('right aligns each row on its own', () => {
    const g = grid(7, { ...base, rows: 2, align: 'right' }, 100, 100);
    close(xs(g), [54, 66, 78, 90, 66, 78, 90]);
  });

  it('stacks rows from the top with gap_mm between them, not centred in a tall box', () => {
    const g = grid(3, { ...base, columns: 1, gap_mm: 5 }, 100, 200);
    close(ys(g), [0, 15, 30]);
    expect(g.height_mm).toBeCloseTo(40, 6);
  });
});

describe('featureIconRow keeps its behaviour (AC-7.5)', () => {
  it('still drops the icons that do not fit one row', () => {
    expect(featureIconRow(3, base, 30)).toEqual([0, 12]);
    expect(featureIconRow(3, { ...base, align: 'right' }, 100)).toEqual([66, 78, 90]);
  });
});
