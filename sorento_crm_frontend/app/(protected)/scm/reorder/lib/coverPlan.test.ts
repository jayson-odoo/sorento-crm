/**
 * Buy, cover from elsewhere, or split - and never promise the same units twice.
 *
 * Modelled on MWC7624-RL-S10 from the live run:
 *   BRW-IB  needs 1    on hand 0   -> short 1   -> use 1 from BRW-BB
 *   DC1-BB  needs 419  on hand 231 -> short 188 -> use 6, buy 182
 * DC1-BB holds 231 and can give none of it: it is short itself.
 */
import { describe, it, expect } from 'vitest';
import {
  coverForLine,
  describeCover,
  proposeCover,
  remainingFree,
  type CoverableLine,
  type CoverSource,
} from './coverPlan';

const src = (code: string, qty: number, segment = 'project'): CoverSource => ({
  warehouse_id: `wh-${code}`,
  warehouse_code: code,
  segment,
  qty,
});
const fmt = (n: number) => String(n);

describe('proposeCover - the split', () => {
  it('covers outright when there is enough elsewhere', () => {
    const p = proposeCover(1, 'wh-BRW-IB', 'project', [src('BRW-BB', 5), src('PJ-SR', 1)]);
    expect(p).toMatchObject({ coverQty: 1, buyQty: 0, isSplit: false });
    expect(p.sources.map((s) => [s.warehouse_code, s.qty])).toEqual([['BRW-BB', 1]]);
  });

  it('splits when the free stock runs out', () => {
    const p = proposeCover(188, 'wh-DC1-BB', 'project', [src('BRW-BB', 5), src('PJ-SR', 1)]);
    expect(p).toMatchObject({ coverQty: 6, buyQty: 182, isSplit: true });
  });

  it('is a plain buy when nothing is free', () => {
    expect(proposeCover(188, 'wh-A', 'project', [])).toMatchObject({ coverQty: 0, buyQty: 188 });
  });

  it('never offers the line its own stock back', () => {
    // Already inside the net. This is the bug the whole module replaces.
    const p = proposeCover(10, 'wh-BRW-BB', 'project', [src('BRW-BB', 5), src('PJ-SR', 1)]);
    expect(p.sources.map((s) => s.warehouse_code)).toEqual(['PJ-SR']);
    expect(p.buyQty).toBe(9);
  });
});

describe('proposeCover - the pool is spent down', () => {
  it('does not offer units an earlier decision already took', () => {
    const free = [src('BRW-BB', 5)];
    expect(proposeCover(3, 'wh-A', 'project', free).coverQty).toBe(3);
    const second = proposeCover(3, 'wh-B', 'project', free, { 'wh-BRW-BB': 3 });
    expect(second).toMatchObject({ coverQty: 2, buyQty: 1 });
  });

  it('drops a source that has been used up entirely', () => {
    const p = proposeCover(5, 'wh-A', 'project', [src('BRW-BB', 5)], { 'wh-BRW-BB': 5 });
    expect(p.sources).toEqual([]);
    expect(p.buyQty).toBe(5);
  });
});

describe('proposeCover - segments', () => {
  it('prefers a smaller same-segment source over a bigger crossing', () => {
    const p = proposeCover(4, 'wh-A', 'project', [
      src('DEALER-BIG', 100, 'dealer'),
      src('PROJ-SMALL', 3, 'project'),
    ]);
    expect(p.sources.map((s) => s.warehouse_code)).toEqual(['PROJ-SMALL', 'DEALER-BIG']);
    expect(p.sources[0].cross_segment).toBe(false);
    expect(p.sources[1].cross_segment).toBe(true);
  });

  it('does not treat an unknown segment as a crossing', () => {
    const p = proposeCover(2, 'wh-A', null, [{ ...src('X', 10), segment: null }]);
    expect(p.sources[0].cross_segment).toBe(false);
  });
});

describe('describeCover - the suggestion is a sentence', () => {
  it('names the source and the split', () => {
    const p = proposeCover(188, 'wh-DC1-BB', 'project', [src('BRW-BB', 5), src('PJ-SR', 1)]);
    expect(describeCover(p, fmt)).toBe('Use 5 from BRW-BB, 1 from PJ-SR, and buy 182');
  });

  it('says buy when there is nothing to use', () => {
    expect(describeCover(proposeCover(10, 'wh-A', 'project', []), fmt)).toBe('Buy 10');
  });

  it('says use when the cover is complete', () => {
    expect(describeCover(proposeCover(3, 'wh-A', 'project', [src('B', 9)]), fmt)).toBe(
      'Use 3 from B',
    );
  });
});

describe('remainingFree', () => {
  it('is what no decision has spoken for yet', () => {
    expect(remainingFree([src('A', 5), src('B', 4)], { 'wh-A': 5 })).toBe(4);
  });

  it('never goes negative when more was taken than existed', () => {
    expect(remainingFree([src('A', 5)], { 'wh-A': 99 })).toBe(0);
  });
});

describe('coverForLine - a covered row reads its own pool, never a default buy', () => {
  // SIM-P002: rec_type=covered, "150 available in this pool covers 15 committed" - but the
  // grid defaulted the suggestion AND the decision cell to "Buy 15". Root cause: composing
  // a covered row through `proposeCover` (the cross-warehouse free pool) instead of the
  // row's own `covered_committed` / `covered_available` figures.
  const coveredLine = (over: Partial<CoverableLine['rec']> = {}): CoverableLine => ({
    order_qty: 15,
    warehouse: 'BRW',
    warehouse_id: 'wh-BRW',
    status: 'covered_by_stock',
    rec: { segment: 'dealer', covered_committed: 15, covered_available: 150, ...over },
  });

  it('is entirely a use-stock proposal when the pool covers the commitment', () => {
    const p = coverForLine(coveredLine(), []); // empty cross-warehouse pool: never needed
    expect(p).toMatchObject({ coverQty: 15, buyQty: 0, isSplit: false });
    expect(p.sources).toEqual([
      expect.objectContaining({ warehouse_code: 'BRW', qty: 15, cross_segment: false }),
    ]);
  });

  it('ignores the cross-warehouse free pool entirely - the covered figures are authoritative', () => {
    const elsewhere = [src('OTHER-WH', 999)];
    const p = coverForLine(coveredLine(), elsewhere, { 'wh-OTHER-WH': 0 });
    expect(p).toMatchObject({ coverQty: 15, buyQty: 0 });
  });

  it('buys the remainder when the pool falls short of the commitment', () => {
    const p = coverForLine(coveredLine({ covered_available: 4 }), []);
    expect(p).toMatchObject({ coverQty: 4, buyQty: 11, isSplit: true });
  });

  it('is a plain buy when the pool holds nothing', () => {
    const p = coverForLine(coveredLine({ covered_available: 0 }), []);
    expect(p).toMatchObject({ coverQty: 0, buyQty: 15 });
    expect(p.sources).toEqual([]);
  });

  it('falls back to order_qty when covered_committed is absent, never NaN/negative', () => {
    const p = coverForLine(coveredLine({ covered_committed: null, covered_available: 20 }), []);
    expect(p).toMatchObject({ coverQty: 15, buyQty: 0 });
  });

  it('an ordinary buy line still proposes against the cross-warehouse pool as before', () => {
    const buyLine: CoverableLine = {
      order_qty: 10, warehouse: 'DC1', warehouse_id: 'wh-DC1', status: 'buy',
      rec: { segment: 'project' },
    };
    const p = coverForLine(buyLine, [src('BRW-BB', 5)]);
    expect(p).toMatchObject({ coverQty: 5, buyQty: 5 });
  });
});
