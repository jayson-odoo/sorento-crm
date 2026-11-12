import { describe, expect, it } from 'vitest';
import type { TownShop, TownSnapshot } from '@/types/town.types';
import {
  SCENE_STALL_CAP, SCENE_TAG_CAP, boughtToday, compactCount, clampInView, placeTags, sceneSelection, separateLabels, tagLabel, tagName,
} from './townFormat';

function shop(i: number, kind: 'shop' | 'stall', docs: number, amount?: string): TownShop {
  return { key: `k${kind}${i}`, kind, account_label: null, today_docs: docs, rank: kind === 'shop' ? i : null, today_amount: amount };
}

function snapshot(shops: TownShop[], dealers: number): TownSnapshot {
  return {
    schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null,
    phase: 'day',
    today: { invoice_count: 1, credit_note_count: 0, customer_count: 1, dealer_customer_count: dealers },
    shops, warehouses: [], reorder: { below_count: 0, set_count: 0 },
    approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
  };
}

describe('sceneSelection', () => {
  const shops = Array.from({ length: 30 }, (_, i) => shop(i + 1, 'shop', i < 8 ? 1 + (i % 3) : 0));
  const stalls = Array.from({ length: 60 }, (_, i) => shop(i + 1, 'stall', 1 + (i % 7), String(10 + i)));
  const snap = snapshot([...shops, ...stalls], 68);

  it('draws all 30 shops and at most 5 stalls, the busiest first', () => {
    const { drawn } = sceneSelection(snap);
    expect(drawn.filter((s) => s.kind === 'shop')).toHaveLength(30);
    const drawnStalls = drawn.filter((s) => s.kind === 'stall');
    expect(drawnStalls).toHaveLength(SCENE_STALL_CAP);
    expect(Math.min(...drawnStalls.map((s) => s.today_docs))).toBe(7);
  });

  it('tags at most 3 lit buildings, busiest first, and counts the dealers it does not draw', () => {
    const { drawn, tagged, others } = sceneSelection(snap);
    expect(tagged).toHaveLength(SCENE_TAG_CAP);
    expect(tagged.every((s) => s.today_docs === 7)).toBe(true);
    const lit = drawn.filter((s) => s.today_docs > 0).length;
    expect(lit).toBe(8 + SCENE_STALL_CAP);
    expect(others).toBe(68 - lit);
  });

  it('never reports a negative number of other dealers', () => {
    expect(sceneSelection(snapshot([shop(1, 'shop', 1)], 0)).others).toBe(0);
  });

  it('breaks a tie on documents by today amount when it is present', () => {
    const tied = snapshot([shop(1, 'shop', 2, '5.00'), shop(2, 'shop', 2, '90.00')], 2);
    expect(sceneSelection(tied).tagged[0].key).toBe('kshop2');
  });
});

describe('boughtToday', () => {
  it('lists the busiest shops first', () => {
    const { bought } = boughtToday(snapshot([shop(1, 'shop', 1), shop(2, 'shop', 4), shop(3, 'shop', 0)], 3));
    expect(bought.map((s) => s.today_docs)).toEqual([4, 1]);
  });
});

describe('placeTags', () => {
  type Box = { x: number; y: number; w: number; h: number };
  const hits = (a: Box, b: Box) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;

  it('leaves a tag that is clear at its anchor', () => {
    expect(placeTags([{ x: 100, y: 100, w: 80, h: 20 }], [])).toEqual([{ x: 100, y: 100 }]);
  });

  it('nudges a tag off a label already placed, and never onto it', () => {
    const placed = [{ x: 100, y: 100, w: 80, h: 20 }];
    const [spot] = placeTags([{ x: 105, y: 102, w: 80, h: 20 }], placed);
    expect(spot).not.toBeNull();
    expect(hits({ ...(spot as { x: number; y: number }), w: 80, h: 20 }, placed[0])).toBe(false);
  });

  it('culls a tag with no clear spot rather than cover another, and keeps the ones before it', () => {
    const wall = Array.from({ length: 9 }, (_, i) => Array.from({ length: 9 }, (_, j) => ({ x: 20 + i * 40, y: 20 + j * 12, w: 40, h: 12 }))).flat();
    const spots = placeTags([{ x: 400, y: 400, w: 40, h: 12 }, { x: 180, y: 70, w: 40, h: 12 }], wall);
    expect(spots[0]).toEqual({ x: 400, y: 400 });
    expect(spots[1]).toBeNull();
  });

  it('pulls a tag at the stage edge back inside, so it is never clipped', () => {
    const view = { left: 0, right: 375, bottom: 0, top: 500 };
    const [spot] = placeTags([{ x: 360, y: 200, w: 150, h: 20 }], [], view);
    expect((spot as { x: number }).x + 75).toBeLessThanOrEqual(375);
    expect((spot as { y: number }).y).toBe(200);
  });

  it('places tags apart from each other in priority order, and skips one off screen', () => {
    const tags = [{ x: 50, y: 50, w: 60, h: 20 }, null, { x: 52, y: 50, w: 60, h: 20 }];
    const spots = placeTags(tags, []);
    expect(spots[1]).toBeNull();
    expect(spots[0]).toEqual({ x: 50, y: 50 });
    expect(hits({ ...(spots[2] as { x: number; y: number }), w: 60, h: 20 }, { x: 50, y: 50, w: 60, h: 20 })).toBe(false);
  });
});

describe('tagLabel', () => {
  const shop = (name: string, amount?: string) =>
    ({ key: 'k', kind: 'shop', account_label: null, today_docs: 1, name, today_amount: amount }) as never;

  it('caps a long name at 22 characters with an ellipsis and keeps the amount', () => {
    const text = tagLabel(shop('ZZT Very Long Fictional Sanitaryware Trading Company [A/C III]', '1234.4'));
    const [name] = text.split('  RM');
    expect(name.length).toBeLessThanOrEqual(22);
    expect(name.endsWith('\u2026')).toBe(true);
    expect(text.endsWith('RM 1,234')).toBe(true);
  });

  it('leaves a short name whole and shows no amount for a viewer without one', () => {
    expect(tagLabel(shop('ZZT Small Shop', '50'))).toBe('ZZT Small Shop  RM 50');
    expect(tagLabel(shop('ZZT Small Shop'))).toBe('ZZT Small Shop');
  });

  it('gives the capped name alone for the pill, which shows the amount beside it', () => {
    expect(tagName(shop('ZZT Small Shop', '50'))).toBe('ZZT Small Shop');
    expect(tagName(shop('ZZT Very Long Fictional Sanitaryware Trading Company'))).toHaveLength(22);
  });
});

describe('compactCount', () => {
  it('is exact up to 999 and compact above', () => {
    expect(compactCount(7)).toBe('7');
    expect(compactCount(999)).toBe('999');
    expect(compactCount(1000)).toBe('1k');
    expect(compactCount(2202)).toBe('2.2k');
    expect(compactCount(12500)).toBe('12.5k');
  });
});

describe('clampInView', () => {
  const view = { left: -30, right: 30, bottom: -20, top: 20 };

  it('leaves a box that is inside the view where it is', () => {
    expect(clampInView({ x: 5, y: 3, w: 10, h: 2 }, view)).toEqual({ x: 5, y: 3 });
  });

  it('pulls a box that sticks out of the right or top edge back inside, by the least', () => {
    const spot = clampInView({ x: 28, y: 19.5, w: 10, h: 2 }, view, 0.5);
    expect(spot.x + 5).toBeCloseTo(30 - 0.5, 5);
    expect(spot.y + 1).toBeCloseTo(20 - 0.5, 5);
  });

  it('pulls a box that sticks out of the left or bottom edge back inside', () => {
    const spot = clampInView({ x: -33, y: -21, w: 10, h: 2 }, view, 0.5);
    expect(spot.x - 5).toBeCloseTo(-30 + 0.5, 5);
    expect(spot.y - 1).toBeCloseTo(-20 + 0.5, 5);
  });

  it('centres a box wider than the view', () => {
    expect(clampInView({ x: 7, y: 0, w: 100, h: 2 }, view).x).toBe(0);
  });
});

describe('separateLabels', () => {
  const view = { left: -30, right: 30, bottom: -20, top: 20 };
  const board = { x: 0, y: 8, w: 16, h: 5 };
  const hits = (a: { x: number; y: number; w: number; h: number }, b: typeof a) =>
    Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;

  it('moves a label sitting on the scoreboard clear of it, and leaves one that is clear alone', () => {
    const [onBoard, apart] = separateLabels(
      [{ x: 2, y: 8, w: 10, h: 2 }, { x: 20, y: -5, w: 8, h: 2 }],
      board,
      view,
    );
    expect(hits({ ...onBoard, w: 10, h: 2 }, board)).toBe(false);
    expect(apart).toEqual({ x: 20, y: -5 });
  });

  it('moves labels that sit on each other apart, and drops none', () => {
    const labels = [0, 1, 2, 3].map(() => ({ x: 25, y: 0, w: 9, h: 2 }));
    const spots = separateLabels(labels, board, view);
    expect(spots).toHaveLength(4);
    const boxes = spots.map((s, i) => ({ ...s, w: labels[i].w, h: labels[i].h }));
    for (let i = 0; i < boxes.length; i++) {
      expect(hits(boxes[i], board)).toBe(false);
      for (let j = i + 1; j < boxes.length; j++) expect(hits(boxes[i], boxes[j])).toBe(false);
    }
  });

  it('goes below the scoreboard when there is no room above it inside the view', () => {
    const [spot] = separateLabels([{ x: 0, y: 17, w: 10, h: 2 }], { x: 0, y: 17, w: 16, h: 5 }, view);
    expect(spot.y).toBeLessThan(17 - 2.5); // below the scoreboard
    expect(spot.y + 1).toBeLessThanOrEqual(20);
    expect(hits({ ...spot, w: 10, h: 2 }, { x: 0, y: 17, w: 16, h: 5 })).toBe(false);
  });

  it('keeps every label inside the view', () => {
    const [spot] = separateLabels([{ x: 40, y: 30, w: 10, h: 2 }], board, view);
    expect(spot.x + 5).toBeLessThanOrEqual(30);
    expect(spot.y + 1).toBeLessThanOrEqual(20);
  });
});
