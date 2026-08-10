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
  describeCover,
  proposeCover,
  remainingFree,
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
