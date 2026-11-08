import { describe, expect, it } from 'vitest';
import type { TownShop, TownSnapshot } from '@/types/town.types';
import {
  SCENE_STALL_CAP, SCENE_TAG_CAP, TAG_HEIGHT_MAX, TAG_SCREEN_SCALE, TAG_TIER_GAP, boughtToday, sceneSelection, tagTiers, townFrame,
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

describe('townFrame', () => {
  it('fits the island and its labels at 90% of the limiting dimension at every canvas shape', () => {
    for (const aspect of [0.67, 1, 1.16, 1.5, 2, 2.5]) {
      for (const small of [false, true]) {
        const half = townFrame(aspect, small);
        // the content (half height 21, half width 31 or 35) is inside the view, and fills 90% of the tighter side
        expect(half).toBeGreaterThanOrEqual(21 / 0.9 - 1e-9);
        expect(half * aspect).toBeGreaterThanOrEqual((small ? 35 : 31) / 0.9 - 1e-9);
        const fillH = 21 / half;
        const fillW = (small ? 35 : 31) / (half * aspect);
        expect(Math.max(fillH, fillW)).toBeCloseTo(0.9, 5);
      }
    }
  });

  it('is height limited on a wide canvas and width limited on a narrow one', () => {
    expect(townFrame(3, false)).toBeCloseTo(21 / 0.9, 5);
    expect(townFrame(1, true)).toBeCloseTo(35 / 0.9, 5);
  });
});

describe('tagTiers', () => {
  const at = (deg: number) => ({ x: Math.cos((deg * Math.PI) / 180) * 20, z: Math.sin((deg * Math.PI) / 180) * 20, deg });

  it('deals tiers 0, 1, 2 in angle order so neighbours never share a height', () => {
    const placed = tagTiers([at(40), at(-70), at(10), at(70), at(-20)]);
    expect(placed.map((p) => p.item.deg)).toEqual([-70, -20, 10, 40, 70]);
    expect(placed.map((p) => p.tier)).toEqual([0, 1, 2, 0, 1]);
    for (let i = 1; i < placed.length; i++) expect(placed[i].tier).not.toBe(placed[i - 1].tier);
  });

  it('is stable for the same buildings in any input order', () => {
    const a = tagTiers([at(40), at(-70), at(10)]).map((p) => [p.item.deg, p.tier]);
    const b = tagTiers([at(10), at(40), at(-70)]).map((p) => [p.item.deg, p.tier]);
    expect(a).toEqual(b);
  });

  it('keeps tiers at least one tag height apart ON SCREEN (the camera foreshortens height)', () => {
    expect(TAG_TIER_GAP * TAG_SCREEN_SCALE).toBeGreaterThanOrEqual(TAG_HEIGHT_MAX);
  });

  it('gives every tag its own tier, so no two tags share a height', () => {
    const at3 = tagTiers([at(-40), at(0), at(40)].slice(0, SCENE_TAG_CAP)).map((p) => p.tier);
    expect(new Set(at3).size).toBe(at3.length);
  });
});
