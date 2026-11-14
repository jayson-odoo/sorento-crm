/**
 * PRICETAG-DESIGNER-FEEDBACK B2, AC-5.2 and AC-5.3: Accessories box rows, never hide.
 *
 * AC-5.2 `rows?: 'auto' | 1 | 2 | 3 | 4` beside `columns`: Columns Auto + Rows 2 with 5 cards is
 * 2 rows (3 + 2) filled left to right; Columns 2 + Rows Auto with 5 cards is 3 rows (2, 2, 1).
 * AC-5.3 (owner Q4) every card is laid out: cards shrink to a minimum readable size, then the box
 * grows. No whole card is ever dropped.
 *
 * Through the public layout function every surface draws from (`cardBoxLayout`). Written
 * test-FIRST. NOTE for the coder: accessory-card.columns.test.ts "below 70% whole cards drop" and
 * "a last row cut short" assert the retired drop rule and must be updated with this slice.
 */
import { describe, expect, it } from 'vitest';

import { cardBoxLayout } from './accessory-card';
import { defaultAccessoriesProps, type AccessoriesLayerProps } from './tag-template-types';

function props(over: Record<string, unknown> = {}): AccessoriesLayerProps {
  return {
    ...defaultAccessoriesProps(),
    showHeader: false,
    headerText: '',
    showBadge: false,
    gap_mm: 0,
    card: { width_mm: 30, height_mm: 20, elements: [] },
    ...over,
  } as AccessoriesLayerProps;
}

const PAD = 1.5;
const rowsOf = (cards: { y_mm: number }[]) => {
  const counts = new Map<number, number>();
  for (const c of cards) {
    const key = Math.round(c.y_mm * 1e6) / 1e6;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => a[0] - b[0]).map(([, n]) => n);
};

describe('cardBoxLayout rows (AC-5.2)', () => {
  it('Columns Auto + Rows 2 with 5 cards: 3 then 2, left to right', () => {
    const out = cardBoxLayout(5, props({ columns: 'auto', rows: 2 }), 150, 200);
    expect(out.cards).toHaveLength(5);
    expect(rowsOf(out.cards)).toEqual([3, 2]);
    expect(out.columns).toBe(3);
    expect(out.cards.map((c) => c.x_mm)).toEqual([PAD, PAD + 30, PAD + 60, PAD, PAD + 30]);
    expect(out.cards.map((c) => c.y_mm)).toEqual([PAD, PAD, PAD, PAD + 20, PAD + 20]);
  });

  it('Columns 2 + Rows Auto with 5 cards: 2, 2, 1', () => {
    const out = cardBoxLayout(5, props({ columns: 2, rows: 'auto' }), 150, 200);
    expect(rowsOf(out.cards)).toEqual([2, 2, 1]);
  });

  it('Rows 1 puts every card on one row', () => {
    const out = cardBoxLayout(4, props({ columns: 'auto', rows: 1 }), 150, 200);
    expect(rowsOf(out.cards)).toEqual([4]);
  });

  it('Rows 3 with 7 cards: 3, 3, 1', () => {
    const out = cardBoxLayout(7, props({ columns: 'auto', rows: 3 }), 150, 200);
    expect(rowsOf(out.cards)).toEqual([3, 3, 1]);
  });

  it('Rows 2 without a Columns choice still lays a grid of 2 rows', () => {
    const out = cardBoxLayout(4, props({ rows: 2 }), 150, 200);
    expect(rowsOf(out.cards)).toEqual([2, 2]);
  });
});

describe('cardBoxLayout never hides a card (AC-5.3)', () => {
  it('8 cards in 2 columns in a short box: all 8 laid out, the box grows', () => {
    // Under the old rule only 4 were drawn and 4 dropped.
    const out = cardBoxLayout(8, props({ columns: 2 }), 100, 40);
    expect(out.cards).toHaveLength(8);
    expect(out.shown).toBe(8);
    expect(out.dropped).toBe(0);
    expect(out.scale).toBeGreaterThan(0);
    expect(out.boxHeight_mm).toBeGreaterThan(40);
    const bottom = Math.max(...out.cards.map((c) => c.y_mm + c.height_mm));
    expect(out.boxHeight_mm).toBeGreaterThanOrEqual(bottom);
  });

  it('shrinks no further than a readable minimum before growing', () => {
    const out = cardBoxLayout(20, props({ columns: 2 }), 100, 30);
    expect(out.cards).toHaveLength(20);
    expect(out.dropped).toBe(0);
    // Readable: never below the existing floor of the card designer.
    expect(out.scale).toBeGreaterThanOrEqual(0.35);
    for (const c of out.cards) expect(c.x_mm + c.width_mm).toBeLessThanOrEqual(100 - PAD + 1e-6);
  });

  it('a stacked box (no columns) too short for its cards draws them all', () => {
    const out = cardBoxLayout(6, props(), 40, 30);
    expect(out.cards).toHaveLength(6);
    expect(out.dropped).toBe(0);
  });
});
