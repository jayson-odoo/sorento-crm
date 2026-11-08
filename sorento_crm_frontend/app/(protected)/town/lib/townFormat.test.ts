import { describe, expect, it } from 'vitest';
import type { TownShop, TownSnapshot } from '@/types/town.types';
import { SCENE_STALL_CAP, SCENE_TAG_CAP, boughtToday, sceneSelection, townFrame } from './townFormat';

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

  it('tags at most 5 lit buildings, busiest first, and counts the dealers it does not draw', () => {
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
  it('fits the island width at every canvas shape, wide or narrow', () => {
    for (const aspect of [0.5, 0.67, 1, 1.5, 2, 2.5]) {
      for (const small of [false, true]) {
        const half = townFrame(aspect, small);
        expect(half * aspect).toBeGreaterThanOrEqual(small ? 42 : 36);
        expect(half).toBeGreaterThanOrEqual(30);
      }
    }
  });

  it('is not zoomed out further than the island needs on a wide canvas', () => {
    expect(townFrame(2.5, false)).toBe(30);
  });
});
