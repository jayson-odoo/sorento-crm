/**
 * The client half of R-K (`PLAN-scm-fulfilment-feedback-2sep.md` S2, AC-2.6b).
 *
 * The SERVER states `available_for_project` on every site-pool row; this helper exists for
 * the two figures it has no row for - the Stock tab's pool subtotal and the expanded
 * ledger's running column - and it has to give the SAME answer the engine's own
 * `available_for_project` does, or the lightbox would argue with the walk it is explaining.
 *
 * The case that earns the test: WHOLE units. "BRW 47 free reads 23" (R-K), never 23.5 -
 * quantities here are counted in minor units four decimal places wide, so flooring in that
 * space would have printed the half unit nobody can ship.
 */
import { describe, expect, it } from 'vitest';

import {
  availableForProject,
  DEFAULT_POOL_SHARE_PCT,
  poolShareLimitsOf,
} from './poolShare';
import type { BoardCellLocation } from '../types/fulfilmentPlanning.types';

describe('availableForProject', () => {
  it('floors the share to whole units', () => {
    expect(availableForProject('47', '900', 50)).toBe('23');
    expect(availableForProject('590', '900', 50)).toBe('295');
  });

  it('does its arithmetic in integers, as the server does (review round 1, S2)', () => {
    // 90 x 70 / 100 = 62.99999... in floating point and 63 in integers. The server floors
    // an exact Decimal, so a client flooring a float would print one unit less than the
    // number the walk obeyed - on the figure a planner decides against.
    expect(availableForProject('90', '900', 30)).toBe('63');
    expect(availableForProject('29', '900', 30)).toBe('20');
    expect(availableForProject('7', '900', 30)).toBe('4');
  });

  it('is capped by the five-pool net, which is the bound the walk obeyed (R-D)', () => {
    expect(availableForProject('3034', '1', 50)).toBe('1');
    expect(availableForProject('590', '-1', 50)).toBe('0');
  });

  it('answers 0 rather than a negative for an oversold pool', () => {
    expect(availableForProject('-103', '-102', 50)).toBe('0');
  });

  it('reads the share it is given, and the policy default when it is given none', () => {
    expect(availableForProject('590', '900', 0)).toBe('590');
    expect(availableForProject('590', '900', 100)).toBe('0');
    expect(availableForProject('590', '900')).toBe(
      availableForProject('590', '900', DEFAULT_POOL_SHARE_PCT),
    );
  });

  it('has nothing to share out of an unstated figure', () => {
    expect(availableForProject(null, '900', 50)).toBeNull();
    expect(availableForProject(undefined, '900', 50)).toBeNull();
  });
});

/**
 * N1 (fix round 5). `net` on a `BoardCellLocation` is the DISPLAYED subtotal - this line's
 * own demand added back in, so the subtotal reads "what is left for me" - while the
 * server's own confirm-time guard (`_is_pool_share_split`) and `stock-detail` bound a
 * pool-share split by the RAW net (`net_raw`), without that addition. `poolShareLimitsOf`
 * must read the raw figure, or it admits a split the server refuses.
 */
describe('poolShareLimitsOf', () => {
  it('reads net_raw, never the displayed net that has this line s own demand added back in', () => {
    const locations: BoardCellLocation[] = [
      {
        location: 'BRW',
        warehouse_id: 'wh-brw',
        where: 'site_pool',
        qty: '0',
        available_for_project: '62',
        // The displayed subtotal (this line's own 20 added back to a raw net of 100).
        net: '120',
        net_raw: '100',
      },
    ];

    expect(poolShareLimitsOf(locations).net).toBe('100');
  });

  it('has no allowance to read when the server sends no net_raw at all', () => {
    const locations: BoardCellLocation[] = [
      {
        location: 'BRW',
        warehouse_id: 'wh-brw',
        where: 'site_pool',
        qty: '0',
        available_for_project: '62',
        net: '120',
      },
    ];

    expect(poolShareLimitsOf(locations).net).toBeNull();
  });
});
