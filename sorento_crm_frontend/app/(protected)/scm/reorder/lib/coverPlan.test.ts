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
  applySourceEdits,
  coverForLine,
  defaultSourceEdits,
  proposeCover,
  remainingFree,
  sourceEditsForTotal,
  sourcesInScope,
  type CoverableLine,
  type CoverSource,
} from './coverPlan';

const src = (code: string, qty: number, segment = 'project'): CoverSource => ({
  warehouse_id: `wh-${code}`,
  warehouse_code: code,
  segment,
  qty,
});

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

/**
 * Cover scope (AC-3.3).
 *
 * > "why am I allowed to use stock from other locations? It is either I use stock from BRW,
 * >  or buy."
 *
 * Three warehouses: A and B share pool A (one site), C is its own. A row sitting at A may
 * take from B under `own_pool`, and from B or C under `all_locations`.
 */
describe('cover scope - own site, or anywhere', () => {
  const POOL_A = 'wh-A';
  const inPoolA = (code: string, qty: number): CoverSource => ({
    warehouse_id: `wh-${code}`,
    warehouse_code: code,
    segment: 'project',
    qty,
    pool_warehouse_id: POOL_A,
  });
  const ownPoolC: CoverSource = {
    warehouse_id: 'wh-C',
    warehouse_code: 'C',
    segment: 'project',
    qty: 50,
    pool_warehouse_id: 'wh-C',
  };
  const free = [inPoolA('B', 5), ownPoolC];

  it('offers only the row own pool when the policy says own_pool', () => {
    const kept = sourcesInScope(free, { scope: 'own_pool', poolWarehouseId: POOL_A });
    expect(kept.map((s) => s.warehouse_code)).toEqual(['B']);
  });

  it('offers every location when the policy says all_locations', () => {
    const kept = sourcesInScope(free, { scope: 'all_locations', poolWarehouseId: POOL_A });
    expect(kept.map((s) => s.warehouse_code)).toEqual(['B', 'C']);
  });

  it('proposes against the scoped set, so the rest becomes a buy', () => {
    const own = proposeCover(60, POOL_A, 'project', free, {}, {
      scope: 'own_pool',
      poolWarehouseId: POOL_A,
    });
    expect(own).toMatchObject({ coverQty: 5, buyQty: 55 });
    expect(own.sources.map((s) => s.warehouse_code)).toEqual(['B']);

    const any = proposeCover(60, POOL_A, 'project', free, {}, {
      scope: 'all_locations',
      poolWarehouseId: POOL_A,
    });
    expect(any).toMatchObject({ coverQty: 55, buyQty: 5 });
    expect(any.sources.map((s) => s.warehouse_code)).toEqual(['C', 'B']);
  });

  it('treats a source with no pool of its own AS its own pool', () => {
    const loose: CoverSource = {
      warehouse_id: 'wh-D', warehouse_code: 'D', segment: 'project', qty: 9,
    };
    expect(sourcesInScope([loose], { scope: 'own_pool', poolWarehouseId: POOL_A })).toEqual([]);
    expect(sourcesInScope([loose], { scope: 'own_pool', poolWarehouseId: 'wh-D' })).toEqual([loose]);
  });

  it('does not scope a row whose own pool is unknown - narrowing is not deleting', () => {
    // A network row carries no warehouse, so there is no pool to compare against. Filtering
    // it to nothing would silently withdraw every option rather than narrow them.
    expect(sourcesInScope(free, { scope: 'own_pool', poolWarehouseId: null })).toEqual(free);
  });

  it('an absent scope reads as all_locations - the behaviour that shipped first', () => {
    expect(sourcesInScope(free, { poolWarehouseId: POOL_A })).toEqual(free);
  });

  it('coverForLine scopes an ordinary buy line the same way', () => {
    const buyLine: CoverableLine = {
      order_qty: 20, warehouse: 'A', warehouse_id: POOL_A, status: 'buy',
      rec: { segment: 'project' },
    };
    const p = coverForLine(buyLine, free, {}, { scope: 'own_pool', poolWarehouseId: POOL_A });
    expect(p).toMatchObject({ coverQty: 5, buyQty: 15 });
    expect(p.sources.map((s) => s.warehouse_code)).toEqual(['B']);
  });
});

/**
 * Per-location edits (AC-3.4). The toggle is on, the buyer types what to take from each
 * location, and the buy follows.
 */
describe('applySourceEdits - the buy follows the edit', () => {
  const proposal = proposeCover(188, 'wh-DC1-BB', 'project', [src('BRW-BB', 5), src('PJ-SR', 1)]);

  it('defaults to the proposal, so an untouched ledger records today answer', () => {
    const applied = applySourceEdits(proposal, defaultSourceEdits(proposal));
    expect(applied).toMatchObject({ coverQty: 6, buyQty: 182 });
    expect(applied.sources.map((s) => [s.warehouse_code, s.qty])).toEqual([
      ['BRW-BB', 5], ['PJ-SR', 1],
    ]);
  });

  it('taking less from one location grows the buy by exactly that much', () => {
    const applied = applySourceEdits(proposal, { 'wh-BRW-BB': 2, 'wh-PJ-SR': 1 });
    expect(applied).toMatchObject({ coverQty: 3, buyQty: 185 });
  });

  it('taking nothing anywhere buys the whole shortage', () => {
    expect(applySourceEdits(proposal, {})).toMatchObject({ coverQty: 0, buyQty: 188, sources: [] });
  });

  it('clamps above what a location actually has free', () => {
    const applied = applySourceEdits(proposal, { 'wh-BRW-BB': 999 });
    expect(applied).toMatchObject({ coverQty: 5, buyQty: 183 });
  });

  it('clamps a negative to zero and drops the row rather than recording an empty source', () => {
    const applied = applySourceEdits(proposal, { 'wh-BRW-BB': -4, 'wh-PJ-SR': 1 });
    expect(applied.coverQty).toBe(1);
    expect(applied.sources.map((s) => s.warehouse_code)).toEqual(['PJ-SR']);
  });

  it('ignores a warehouse the proposal never offered', () => {
    expect(applySourceEdits(proposal, { 'wh-SOMEWHERE': 100 })).toMatchObject({
      coverQty: 0, buyQty: 188,
    });
  });

  it('never returns a negative buy when the cover exceeds the gap', () => {
    const small = proposeCover(2, 'wh-A', 'project', [src('B', 50)]);
    expect(applySourceEdits(small, { 'wh-B': 50 })).toMatchObject({ buyQty: 0 });
  });

  it('a NaN input reads as nothing taken, never as NaN units', () => {
    const applied = applySourceEdits(proposal, { 'wh-BRW-BB': Number.NaN });
    expect(applied.coverQty).toBe(0);
  });
});

describe('sourceEditsForTotal - one figure spent from the front', () => {
  const proposal = proposeCover(188, 'wh-DC1-BB', 'project', [src('BRW-BB', 5), src('PJ-SR', 1)]);

  it('keeps the nearest bins first', () => {
    expect(sourceEditsForTotal(proposal, 4)).toEqual({ 'wh-BRW-BB': 4, 'wh-PJ-SR': 0 });
  });

  it('agrees with the per-location path for the same total', () => {
    const viaTotal = applySourceEdits(proposal, sourceEditsForTotal(proposal, 6));
    const viaEdits = applySourceEdits(proposal, { 'wh-BRW-BB': 5, 'wh-PJ-SR': 1 });
    expect(viaTotal).toEqual(viaEdits);
  });

  it('never hands out more than the proposal offered', () => {
    expect(applySourceEdits(proposal, sourceEditsForTotal(proposal, 999)).coverQty).toBe(6);
  });
});
