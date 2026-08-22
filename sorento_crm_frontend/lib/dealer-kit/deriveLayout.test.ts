import { describe, it, expect } from 'vitest';

import {
  BREAKPOINT_COLUMNS,
  deriveLayout,
  type BlockLayout,
  type BlockPlacementMap,
} from './deriveLayout';

/**
 * Golden set for layout derivation (AC-C6 / AC-K2).
 *
 * Written BEFORE the implementation. Derivation is a pure function: given the
 * desktop placement map and a target column count, produce the smaller
 * breakpoint's placement. Rules under test:
 *
 *  1. reading order is top-left -> bottom-right, ties broken by block id so the
 *     output is stable regardless of object key order
 *  2. every block goes full width at the target column count
 *  3. rowSpan is preserved, rowStart is the running cumulative total
 *  4. colSpan is clamped to the target column count, never carried over from 12
 *
 * Tile density inside a collection block is NOT derivation's job - that lives on
 * the block's own `columns` prop per breakpoint. Derivation places blocks only.
 */

const b = (
  colStart: number,
  colSpan: number,
  rowStart: number,
  rowSpan = 1,
): BlockLayout => ({ colStart, colSpan, rowStart, rowSpan });

describe('BREAKPOINT_COLUMNS', () => {
  it('is 12 / 8 / 4 for desktop / tablet / mobile', () => {
    expect(BREAKPOINT_COLUMNS).toEqual({ desktop: 12, tablet: 8, mobile: 4 });
  });
});

describe('deriveLayout', () => {
  it('returns an empty map for an empty layout', () => {
    expect(deriveLayout({}, 4)).toEqual({});
  });

  it('stretches a single block to the full target width at row 1', () => {
    const source: BlockPlacementMap = { a: b(4, 5, 1) };

    expect(deriveLayout(source, 4)).toEqual({ a: b(1, 4, 1) });
    expect(deriveLayout(source, 8)).toEqual({ a: b(1, 8, 1) });
  });

  it('stacks a side-by-side pair in reading order', () => {
    const source: BlockPlacementMap = {
      left: b(1, 6, 1),
      right: b(7, 6, 1),
    };

    expect(deriveLayout(source, 4)).toEqual({
      left: b(1, 4, 1),
      right: b(1, 4, 2),
    });
  });

  it('orders by column when blocks share a row, regardless of key order', () => {
    // `right` is declared first on purpose - insertion order must not leak.
    const source: BlockPlacementMap = {
      right: b(9, 4, 1),
      middle: b(5, 4, 1),
      left: b(1, 4, 1),
    };

    const derived = deriveLayout(source, 4);

    expect(derived.left.rowStart).toBe(1);
    expect(derived.middle.rowStart).toBe(2);
    expect(derived.right.rowStart).toBe(3);
  });

  it('orders by row before column', () => {
    const source: BlockPlacementMap = {
      secondRowLeft: b(1, 6, 2),
      firstRowRight: b(7, 6, 1),
    };

    const derived = deriveLayout(source, 8);

    expect(derived.firstRowRight.rowStart).toBe(1);
    expect(derived.secondRowLeft.rowStart).toBe(2);
  });

  it('preserves rowSpan and accumulates rowStart from it', () => {
    const source: BlockPlacementMap = {
      tall: b(1, 6, 1, 3),
      next: b(7, 6, 1, 1),
      last: b(1, 12, 2, 2),
    };

    expect(deriveLayout(source, 4)).toEqual({
      tall: b(1, 4, 1, 3),
      next: b(1, 4, 4, 1),
      last: b(1, 4, 5, 2),
    });
  });

  it('clamps a full-width desktop block down to the target width', () => {
    const source: BlockPlacementMap = { hero: b(1, 12, 1) };

    expect(deriveLayout(source, 4).hero.colSpan).toBe(4);
    expect(deriveLayout(source, 8).hero.colSpan).toBe(8);
  });

  it('breaks ties on block id so output is deterministic', () => {
    const source: BlockPlacementMap = {
      zebra: b(1, 6, 1),
      alpha: b(1, 6, 1),
    };

    const derived = deriveLayout(source, 4);

    expect(derived.alpha.rowStart).toBe(1);
    expect(derived.zebra.rowStart).toBe(2);
  });

  it('is pure - it does not mutate the source layout', () => {
    const source: BlockPlacementMap = { a: b(3, 6, 2, 2) };
    const snapshot = structuredClone(source);

    deriveLayout(source, 4);

    expect(source).toEqual(snapshot);
  });

  it('is idempotent - deriving an already-derived layout changes nothing', () => {
    const source: BlockPlacementMap = {
      a: b(1, 6, 1),
      c: b(7, 6, 1),
      e: b(1, 12, 2, 2),
    };

    const once = deriveLayout(source, 4);
    const twice = deriveLayout(once, 4);

    expect(twice).toEqual(once);
  });

  it('never emits a placement that overflows the target grid', () => {
    const source: BlockPlacementMap = {
      a: b(11, 2, 1),
      bb: b(1, 12, 2),
      c: b(6, 4, 3, 4),
    };

    for (const columns of [4, 8, 12]) {
      for (const placement of Object.values(deriveLayout(source, columns))) {
        expect(placement.colStart).toBeGreaterThanOrEqual(1);
        expect(placement.colStart + placement.colSpan - 1).toBeLessThanOrEqual(columns);
        expect(placement.rowStart).toBeGreaterThanOrEqual(1);
        expect(placement.rowSpan).toBeGreaterThanOrEqual(1);
      }
    }
  });
});
