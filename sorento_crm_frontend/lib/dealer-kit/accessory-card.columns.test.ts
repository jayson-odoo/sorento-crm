/**
 * PRICETAG-ACCESSORY-DESIGNER S6: `AccessoriesLayerProps.columns?: 'auto' | 1 | 2 | 3 | 4` on the card
 * path of `cardBoxLayout`. Plan: "S6 Layout flexibility / Columns". Written test-FIRST: `cardBoxLayout`
 * ignores `columns` today.
 *
 * Grid: cards fill left to right then wrap, rows left aligned, every card the same size. Auto =
 * floor((innerW + gap) / (cardW + gap)), at least 1, at most the item count. One uniform scale fits the
 * grid in width AND height (footer under the grid), never below 70%; below that whole cards drop in
 * reading order. Absent `columns` = today's vertical / horizontal behaviour.
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
const xs = (cards: { x_mm: number }[]) => cards.map((c) => c.x_mm);
const ys = (cards: { y_mm: number }[]) => cards.map((c) => c.y_mm);

describe('cardBoxLayout columns', () => {
  it('7 items in 4 columns wrap as 4 + 3, rows left aligned', () => {
    const out = cardBoxLayout(7, props({ columns: 4 }), 150, 200);
    expect(out.scale).toBe(1);
    expect(out.shown).toBe(7);
    expect(out.dropped).toBe(0);
    const row1 = out.cards.slice(0, 4);
    const row2 = out.cards.slice(4);
    expect(new Set(xs(row1)).size).toBe(4);
    expect(xs(row1)).toEqual([PAD, PAD + 30, PAD + 60, PAD + 90]);
    expect(row1.every((c) => Math.abs(c.y_mm - PAD) < 1e-6)).toBe(true);
    expect(row2).toHaveLength(3);
    expect(xs(row2)).toEqual([PAD, PAD + 30, PAD + 60]);
    expect(row2.every((c) => Math.abs(c.y_mm - (PAD + 20)) < 1e-6)).toBe(true);
    expect(out.cards.every((c) => c.width_mm === 30 && c.height_mm === 20)).toBe(true);
  });

  it('closes the box up around the grid', () => {
    const out = cardBoxLayout(7, props({ columns: 4 }), 150, 200);
    expect(out.boxHeight_mm).toBeCloseTo(PAD + 40 + PAD);
  });

  it('honours the gap between columns and rows', () => {
    const out = cardBoxLayout(4, props({ columns: 2, gap_mm: 2 }), 100, 200);
    expect(xs(out.cards)).toEqual([PAD, PAD + 32, PAD, PAD + 32]);
    expect(ys(out.cards)).toEqual([PAD, PAD, PAD + 22, PAD + 22]);
  });

  it('columns 1 stacks the cards', () => {
    const out = cardBoxLayout(3, props({ columns: 1 }), 60, 70);
    expect(xs(out.cards)).toEqual([PAD, PAD, PAD]);
    expect(ys(out.cards)).toEqual([PAD, PAD + 20, PAD + 40]);
    expect(out.scale).toBe(1);
  });

  it('auto picks floor((innerW + gap) / (cardW + gap)) columns', () => {
    // innerW 97, gap 2, card 30: floor(99 / 32) = 3 columns; 7 items = 3 + 3 + 1
    const out = cardBoxLayout(7, props({ columns: 'auto', gap_mm: 2 }), 100, 300);
    expect(out.scale).toBe(1);
    expect(xs(out.cards)).toEqual([PAD, PAD + 32, PAD + 64, PAD, PAD + 32, PAD + 64, PAD]);
    expect(ys(out.cards).filter((y) => Math.abs(y - PAD) < 1e-6)).toHaveLength(3);
  });

  it('auto is capped at the item count', () => {
    const out = cardBoxLayout(2, props({ columns: 'auto', gap_mm: 2 }), 100, 300);
    expect(xs(out.cards)).toEqual([PAD, PAD + 32]);
    expect(new Set(ys(out.cards)).size).toBe(1);
  });

  it('auto is at least 1 when not even one card fits at scale 1', () => {
    // innerW 29 < card 30: floor((29 + 2) / 32) = 0 -> 1 column, scaled to fit the width
    const out = cardBoxLayout(3, props({ columns: 'auto', gap_mm: 2 }), 32, 300);
    expect(new Set(xs(out.cards)).size).toBe(1);
    expect(out.cards).toHaveLength(3);
    expect(out.scale).toBeCloseTo(29 / 30);
  });

  it('a grid too wide shrinks every card by the same factor', () => {
    // 4 across need 120 mm, innerW is 97: 97 / 120
    const out = cardBoxLayout(4, props({ columns: 4 }), 100, 100);
    expect(out.scale).toBeCloseTo(97 / 120);
    expect(out.shown).toBe(4);
    for (const c of out.cards) {
      expect(c.width_mm).toBeCloseTo(30 * out.scale);
      expect(c.height_mm).toBeCloseTo(20 * out.scale);
    }
  });

  it('a grid too tall shrinks every card by the same factor', () => {
    // 6 items, 2 columns = 3 rows = 60 mm; avail 56 - 3 = 53
    const out = cardBoxLayout(6, props({ columns: 2 }), 100, 56);
    expect(out.scale).toBeGreaterThan(0.7);
    expect(out.scale).toBeLessThan(1);
    expect(out.scale).toBeCloseTo(53 / 60);
    expect(out.shown).toBe(6);
    expect(out.dropped).toBe(0);
    expect(out.cards.every((c) => Math.abs(c.height_mm - 20 * out.scale) < 1e-6)).toBe(true);
  });

  it('below 70% whole cards drop in reading order and the dropped are counted', () => {
    // 8 items, 2 columns = 4 rows. At 0.7 a row is 14 mm; avail 40 - 3 = 37 holds 2 rows = 4 cards
    const out = cardBoxLayout(8, props({ columns: 2 }), 100, 40);
    expect(out.scale).toBe(0.7);
    expect(out.shown).toBe(4);
    expect(out.dropped).toBe(4);
    expect(out.cards).toHaveLength(4);
    expect(xs(out.cards)).toEqual([PAD, PAD + 21, PAD, PAD + 21]);
    expect(ys(out.cards)).toEqual([PAD, PAD, PAD + 14, PAD + 14]);
  });

  it('a last row cut short keeps the cards that fit in reading order', () => {
    // 5 items in 2 columns at 0.7: 2 rows hold 4 cards, so the 5th is dropped
    const out = cardBoxLayout(5, props({ columns: 2 }), 100, 40);
    expect(out.scale).toBe(0.7);
    expect(out.shown).toBe(4);
    expect(out.dropped).toBe(1);
  });

  it('the footer sits under the grid', () => {
    const out = cardBoxLayout(4, props({ columns: 2, footer: { show: true, height_mm: 6, elements: [] } }), 100, 100);
    expect(out.footer).not.toBeNull();
    expect(out.footer!.y_mm).toBeCloseTo(PAD + 40);
    expect(out.footer!.height_mm).toBe(6);
    expect(out.footer!.x_mm).toBe(PAD);
    expect(out.boxHeight_mm).toBeCloseTo(PAD + 40 + 6 + PAD);
  });

  it('the footer height is part of the height the grid must fit', () => {
    const out = cardBoxLayout(6, props({ columns: 2, footer: { show: true, height_mm: 6, elements: [] } }), 100, 63);
    // rows need 60, avail = 63 - 1.5 - 1.5 - 6 = 54
    expect(out.scale).toBeCloseTo(54 / 60);
    expect(out.footer!.height_mm).toBe(6);
  });

  it('absent columns keeps today\'s vertical stack exactly', () => {
    const out = cardBoxLayout(3, props(), 60, 70);
    expect(xs(out.cards)).toEqual([PAD, PAD, PAD]);
    expect(ys(out.cards)).toEqual([PAD, PAD + 20, PAD + 40]);
    expect(out.scale).toBe(1);
    expect(out.boxWidth_mm).toBe(60);
    expect(out.boxHeight_mm).toBeCloseTo(63);
  });

  it('absent columns keeps today\'s horizontal row exactly', () => {
    const out = cardBoxLayout(
      3,
      props({ direction: 'horizontal', card: { width_mm: 20, height_mm: 20, elements: [] } }),
      70,
      40,
    );
    expect(xs(out.cards)).toEqual([PAD, PAD + 20, PAD + 40]);
    expect(out.boxWidth_mm).toBeCloseTo(63);
  });

  it('an explicit undefined columns equals a missing one', () => {
    expect(cardBoxLayout(5, props({ columns: undefined }), 80, 90)).toEqual(cardBoxLayout(5, props(), 80, 90));
  });
});
