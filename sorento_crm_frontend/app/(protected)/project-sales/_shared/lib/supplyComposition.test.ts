/**
 * Stage 1C - the line balance CS edits against, and everything that stops a Confirm.
 *
 * The rules here are the browser's copy of what the server rechecks against authoritative
 * facts, so what is pinned is exactness and wording: quantities compared in minor units at
 * four decimal places (10.1 + 20.2 balances 30.3, which it does not in binary floating
 * point), one sentence per blocker naming the line the way every other refusal on this
 * screen names it, and a payload that carries no component deciding nothing.
 */
import { describe, expect, it } from 'vitest';
import type { SupplyLine } from '../types/fulfilmentPlanning.types';
import {
  confirmLineFromDraft,
  draftBlockers,
  draftFromLine,
  fromMinor,
  lineBalance,
  lineBlockers,
  toMinor,
  type DraftLine,
} from './supplyComposition';
import { poolShareLimitsFromLine } from './poolShare';

const WAREHOUSE_BRW = 'a1000000-0000-4000-8000-000000000001';
const WAREHOUSE_HQ = 'a1000000-0000-4000-8000-000000000002';
const DONOR_PROJECT = 'b2000000-0000-4000-8000-000000000001';

function line(overrides: Partial<SupplyLine> = {}): SupplyLine {
  return {
    project_line_id: 'pl-1',
    line_no: 1,
    item_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    uom: 'UNIT',
    open_qty: '600',
    required_date: '2026-09-01',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    is_project_hot_selling: false,
    dealer_classified: false,
    project_classified: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '120',
    components: [],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [],
    ...overrides,
  };
}

function draft(overrides: Partial<DraftLine> = {}): DraftLine {
  return {
    project_line_id: 'pl-1',
    line_no: 1,
    item_code: 'CB6633',
    open_qty: '100',
    timely_spo_qty: '0',
    reserve: [],
    borrow: [],
    buy_qty: '100',
    buy_reason: '',
    is_discontinued: false,
    order_back: false,
    cited_document: '',
    ...overrides,
  };
}

function reserve(qty: string, key = 'r1', location = 'BRW-BB', warehouseId = WAREHOUSE_BRW) {
  return { key, location, warehouse_id: warehouseId, qty, reason: 'Free stock covers it.' };
}

function borrow(qty: string, reason: string, overrides: Record<string, unknown> = {}) {
  return {
    key: 'b1',
    source: 'other_location' as const,
    warehouse_code: 'HQ',
    warehouse_id: WAREHOUSE_HQ,
    qty,
    reason,
    donor_impact: { free_before: '80', free_after_full_borrow: '0', committed_qty: '140' },
    ...overrides,
  };
}

describe('toMinor and fromMinor', () => {
  it('keeps four decimal places, which is the widest UOM precision the plan allows', () => {
    expect(toMinor('10.1234')).toBe(101234);
    expect(fromMinor(101234)).toBe('10.1234');
  });

  it('reads a half-typed or absent quantity as zero rather than NaN', () => {
    expect(toMinor('')).toBe(0);
    expect(toMinor('-')).toBe(0);
    expect(toMinor(null)).toBe(0);
    expect(toMinor(undefined)).toBe(0);
  });

  it('drops trailing zeroes, so a quantity reads as a quantity', () => {
    expect(fromMinor(400000)).toBe('40');
    expect(fromMinor(0)).toBe('0');
  });
});

describe('lineBalance', () => {
  it('balances 10.1 + 20.2 against 30.3, which binary floating point does not', () => {
    const balance = lineBalance(
      draft({ open_qty: '30.3', reserve: [reserve('10.1')], buy_qty: '20.2' }),
    );

    expect(balance.balanced).toBe(true);
    expect(balance.differenceMinor).toBe(0);
  });

  it('adds up incoming, reserve, borrow and buy against the open quantity', () => {
    const balance = lineBalance(
      draft({
        open_qty: '600',
        timely_spo_qty: '100',
        reserve: [reserve('200')],
        borrow: [borrow('50', 'HQ has nothing booked before October.')],
        buy_qty: '250',
      }),
    );

    expect(balance.timelyMinor).toBe(toMinor('100'));
    expect(balance.reserveMinor).toBe(toMinor('200'));
    expect(balance.borrowMinor).toBe(toMinor('50'));
    expect(balance.buyMinor).toBe(toMinor('250'));
    expect(balance.balanced).toBe(true);
  });

  it('reports the difference signed: positive is over the need, negative is short', () => {
    expect(lineBalance(draft({ open_qty: '100', buy_qty: '120' })).differenceMinor).toBe(
      toMinor('20'),
    );
    expect(lineBalance(draft({ open_qty: '100', buy_qty: '80' })).differenceMinor).toBe(
      toMinor('-20'),
    );
  });

  it('sums two reserve legs at the same location', () => {
    const balance = lineBalance(
      draft({
        open_qty: '100',
        reserve: [reserve('60', 'r1'), reserve('40', 'r2', 'HQ', WAREHOUSE_HQ)],
        buy_qty: '0',
      }),
    );

    expect(balance.reserveMinor).toBe(toMinor('100'));
    expect(balance.balanced).toBe(true);
  });
});

describe('lineBlockers', () => {
  it('names a balanced line as nothing at all', () => {
    expect(lineBlockers(draft())).toEqual([]);
  });

  it('says by how much the components are short of the open quantity, naming the line', () => {
    expect(lineBlockers(draft({ open_qty: '100', buy_qty: '80' }))).toEqual([
      'Line 1, CB6633: the components are short of the open quantity by 20.',
    ]);
  });

  it('says by how much they are over it', () => {
    expect(lineBlockers(draft({ open_qty: '100', buy_qty: '130' }))).toEqual([
      'Line 1, CB6633: the components are over the open quantity by 30.',
    ]);
  });

  it('names the line by number alone when it carries no item code', () => {
    expect(
      lineBlockers(draft({ item_code: null, open_qty: '100', buy_qty: '80' })),
    ).toEqual(['Line 1: the components are short of the open quantity by 20.']);
  });

  it('puts a negative quantity first, because it is why the balance is wrong', () => {
    const blockers = lineBlockers(
      draft({ open_qty: '100', reserve: [reserve('-10')], buy_qty: '100' }),
    );

    expect(blockers[0]).toBe('Line 1, CB6633: a quantity is below zero.');
    expect(blockers).toHaveLength(2);
  });

  it('demands a reason for every borrow that carries a quantity, naming the donor', () => {
    const blockers = lineBlockers(
      draft({
        open_qty: '100',
        borrow: [
          borrow('40', '   '),
          borrow('60', '', {
            key: 'b2',
            source: 'other_project',
            warehouse_code: 'JB',
            donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
            donor_project_id: DONOR_PROJECT,
          }),
        ],
        buy_qty: '0',
      }),
    );

    expect(blockers).toEqual([
      'Line 1, CB6633: the borrow from HQ needs a reason.',
      'Line 1, CB6633: the borrow from PRJ-0052 Seri Emas Phase 2 needs a reason.',
    ]);
  });

  it('lets a zero-quantity borrow through without a reason: it decides nothing', () => {
    expect(
      lineBlockers(draft({ open_qty: '100', borrow: [borrow('0', '')], buy_qty: '100' })),
    ).toEqual([]);
  });

  it('demands a reason for buying a discontinued product, and only while it is bought', () => {
    expect(
      lineBlockers(draft({ is_discontinued: true, open_qty: '100', buy_qty: '100' })),
    ).toEqual(['Line 1, CB6633: buying a discontinued product needs a reason.']);

    expect(
      lineBlockers(
        draft({
          is_discontinued: true,
          open_qty: '100',
          reserve: [reserve('100')],
          buy_qty: '0',
        }),
      ),
    ).toEqual([]);

    expect(
      lineBlockers(
        draft({
          is_discontinued: true,
          open_qty: '100',
          buy_qty: '100',
          buy_reason: 'Customer accepted the last production batch in writing.',
        }),
      ),
    ).toEqual([]);
  });

  it('refuses a line that mixes stock with a Buy, and says what to do instead', () => {
    // AC-L5, the captain 25 August 2026: "a line is either wholly covered from stock (own
    // group, pools, borrow, incoming in any mix) or wholly Buy". The server refuses the mix
    // at confirm; this is the same rule said before the round trip.
    expect(
      lineBlockers(
        draft({ open_qty: '100', reserve: [reserve('40')], buy_qty: '60' }),
      ),
    ).toEqual([
      'Line 1, CB6633: a line is either met wholly from stock or wholly bought. ' +
        'This one mixes 40 from stock with a Buy of 60.',
    ]);
  });

  /**
   * D5 (captain, 3 Sep, SO419208 line 3). The ONE mix the rule allows, and the client used
   * to refuse the engine's own suggestion because of it: inside the immediate window a site
   * pool lends its share and the remainder is bought (R-B/R-C), so "BRW 62 + Buy 73" is a
   * composition the walk MAKES and the server's own confirm admits (`_is_pool_share_split`).
   *
   * The bound is the same one the server reads: each pool's own `available_for_project`, and
   * the five pools' net over all of them together.
   */
  it('admits a site pool share beside a Buy, inside that pool s own allowance', () => {
    expect(
      lineBlockers(
        draft({ open_qty: '135', reserve: [reserve('62')], buy_qty: '73' }),
        { allowanceByWarehouseId: { [WAREHOUSE_BRW]: '62' }, net: '400' },
      ),
    ).toEqual([]);
  });

  it('refuses a pool draw beyond what that pool may spare, and says the allowance', () => {
    expect(
      lineBlockers(
        draft({ open_qty: '135', reserve: [reserve('70')], buy_qty: '65' }),
        { allowanceByWarehouseId: { [WAREHOUSE_BRW]: '62' }, net: '400' },
      ),
    ).toEqual([
      'Line 1, CB6633: BRW-BB can spare 62 for this line, and 70 was asked for. Take ' +
        'the whole 135 from stock, or buy the whole 135.',
    ]);
  });

  it('refuses pool draws that together pass the five-pool net', () => {
    expect(
      lineBlockers(
        draft({
          open_qty: '135',
          reserve: [reserve('40'), reserve('40', 'r2', 'MWH', WAREHOUSE_HQ)],
          buy_qty: '55',
        }),
        {
          allowanceByWarehouseId: { [WAREHOUSE_BRW]: '62', [WAREHOUSE_HQ]: '62' },
          net: '60',
        },
      ),
    ).toEqual([
      'Line 1, CB6633: the site pools net 60 between them, and 80 was asked for. Take ' +
        'the whole 135 from stock, or buy the whole 135.',
    ]);
  });

  /**
   * AC-N.11 (`PLAN-scm-pool-chain-first.md`, ruling R-N, 3 Sep 2026). Step 0 walks the
   * WHOLE pool chain now, so the engine's own suggestion may hold a Reserve at TWO site
   * pools beside a Buy - AC-N.6's shape exactly: BRW spares 100, WH3 spares what is left
   * of the one five-pool net, and the remaining 30 is bought.
   *
   * Read through `poolShareLimitsFromLine`, because the per-order SHEET is the surface
   * that has no cell to read allowances off: its own line carries them (`pool_allowances`
   * / `pools_net`, the server's own figures), and a sheet refusing what the board accepts
   * would be the two screens disagreeing about one composition.
   */
  it('admits a TWO-pool step 0 composition beside a Buy, on the sheet s own limits', () => {
    expect(
      lineBlockers(
        draft({
          open_qty: '150',
          reserve: [reserve('100'), reserve('20', 'r2', 'WH3', WAREHOUSE_HQ)],
          buy_qty: '30',
        }),
        poolShareLimitsFromLine(
          line({
            pool_allowances: { [WAREHOUSE_BRW]: '100', [WAREHOUSE_HQ]: '20' },
            pools_net: '120',
          }),
        ),
      ),
    ).toEqual([]);
  });

  it('still holds each pool of the chain to its OWN allowance', () => {
    expect(
      lineBlockers(
        draft({
          open_qty: '150',
          reserve: [reserve('100'), reserve('30', 'r2', 'WH3', WAREHOUSE_HQ)],
          buy_qty: '20',
        }),
        poolShareLimitsFromLine(
          line({
            pool_allowances: { [WAREHOUSE_BRW]: '100', [WAREHOUSE_HQ]: '20' },
            pools_net: '120',
          }),
        ),
      ),
    ).toEqual([
      'Line 1, CB6633: WH3 can spare 20 for this line, and 30 was asked for. Take the ' +
        'whole 150 from stock, or buy the whole 150.',
    ]);
  });

  it('still refuses an OWN bin beside a Buy: only a site pool keeps a share back', () => {
    expect(
      lineBlockers(
        draft({ open_qty: '135', reserve: [reserve('62')], buy_qty: '73' }),
        // BRW-BB is this line's own bin here, so it states no allowance at all.
        { allowanceByWarehouseId: {}, net: '400' },
      ),
    ).toEqual([
      'Line 1, CB6633: a line is either met wholly from stock or wholly bought. ' +
        'This one mixes 62 from stock with a Buy of 73.',
    ]);
  });

  it('still refuses a BORROW beside a Buy, whatever the pool may spare', () => {
    expect(
      lineBlockers(
        draft({
          open_qty: '135',
          reserve: [reserve('42')],
          borrow: [borrow('20', 'SO400001 can wait.')],
          buy_qty: '73',
        }),
        { allowanceByWarehouseId: { [WAREHOUSE_BRW]: '62' }, net: '400' },
      ),
    ).toEqual([
      'Line 1, CB6633: a line is either met wholly from stock or wholly bought. ' +
        'This one mixes 62 from stock with a Buy of 73.',
    ]);
  });

  it('lets either pure composition through', () => {
    expect(
      lineBlockers(draft({ open_qty: '100', reserve: [reserve('100')], buy_qty: '0' })),
    ).toEqual([]);
    expect(lineBlockers(draft({ open_qty: '100', buy_qty: '100' }))).toEqual([]);
  });

  it('counts incoming supply as stock, so it cannot sit beside a Buy either', () => {
    expect(
      lineBlockers(draft({ open_qty: '100', timely_spo_qty: '10', buy_qty: '90' })),
    ).toEqual([
      'Line 1, CB6633: a line is either met wholly from stock or wholly bought. ' +
        'This one mixes 10 from stock with a Buy of 90.',
    ]);
  });

  it('says nothing about the mix on a line that does not add up: that comes first', () => {
    // One refusal at a time. A line short of its open quantity is told THAT, not a second
    // sentence about a composition it has not finished stating.
    expect(lineBlockers(draft({ open_qty: '100', reserve: [reserve('40')], buy_qty: '50' }))).toEqual([
      'Line 1, CB6633: the components are short of the open quantity by 10.',
    ]);
  });

  it('orders the blockers: below zero, then the imbalance, then the missing reasons', () => {
    const blockers = lineBlockers(
      draft({
        is_discontinued: true,
        open_qty: '100',
        reserve: [reserve('-5')],
        borrow: [borrow('10', '')],
        buy_qty: '50',
      }),
    );

    expect(blockers).toEqual([
      'Line 1, CB6633: a quantity is below zero.',
      'Line 1, CB6633: the components are short of the open quantity by 45.',
      'Line 1, CB6633: the borrow from HQ needs a reason.',
      'Line 1, CB6633: buying a discontinued product needs a reason.',
    ]);
  });
});

describe('draftBlockers', () => {
  it('gathers every line, in line order, so the foot of the sheet reads top to bottom', () => {
    expect(
      draftBlockers([
        draft({ line_no: 1, open_qty: '100', buy_qty: '90' }),
        draft({ line_no: 2, item_code: 'SRT501-CP', open_qty: '70', buy_qty: '70' }),
        draft({ line_no: 3, item_code: 'CB2201', open_qty: '200', buy_qty: '210' }),
      ]),
    ).toEqual([
      'Line 1, CB6633: the components are short of the open quantity by 10.',
      'Line 3, CB2201: the components are over the open quantity by 10.',
    ]);
  });
});

describe('draftFromLine', () => {
  it('opens on the engine proposal unedited, one draft row per proposed component', () => {
    const result = draftFromLine(
      line({
        components: [
          {
            kind: 'timely_spo',
            qty: '100',
            reason: 'SPO-2026-0311 arrives at BRW-BB on the delivery date.',
            source_location: 'BRW-BB',
            source_warehouse_id: WAREHOUSE_BRW,
          },
          {
            kind: 'reserve',
            qty: '200',
            reason: 'Free stock at BRW-BB covers the need by the delivery date.',
            source_location: 'BRW-BB',
            source_warehouse_id: WAREHOUSE_BRW,
          },
          { kind: 'buy', qty: '300', reason: 'Remaining uncovered need.' },
        ],
      }),
    );

    expect(result.open_qty).toBe('600');
    expect(result.timely_spo_qty).toBe('100');
    expect(result.reserve).toHaveLength(1);
    expect(result.reserve[0]).toMatchObject({
      location: 'BRW-BB',
      warehouse_id: WAREHOUSE_BRW,
      qty: '200',
      reason: 'Free stock at BRW-BB covers the need by the delivery date.',
    });
    expect(result.buy_qty).toBe('300');
    expect(lineBalance(result).balanced).toBe(true);
  });

  it('adds up several timely incoming legs into the one quantity CS never types', () => {
    const result = draftFromLine(
      line({
        open_qty: '150',
        components: [
          { kind: 'timely_spo', qty: '50.5', reason: 'SPO-2026-0311 arrives in time.' },
          { kind: 'timely_spo', qty: '49.5', reason: 'SPO-2026-0402 arrives in time.' },
          { kind: 'buy', qty: '50', reason: 'Remaining uncovered need.' },
        ],
      }),
    );

    expect(result.timely_spo_qty).toBe('100');
    expect(lineBalance(result).balanced).toBe(true);
  });

  it('keeps two reserve legs apart, each with its own location and key', () => {
    const result = draftFromLine(
      line({
        open_qty: '100',
        components: [
          {
            kind: 'reserve',
            qty: '60',
            reason: 'Free stock at BRW-BB covers 60 of the need.',
            source_location: 'BRW-BB',
            source_warehouse_id: WAREHOUSE_BRW,
          },
          {
            kind: 'reserve',
            qty: '40',
            reason: 'Free stock at HQ covers the rest.',
            source_location: 'HQ',
            source_warehouse_id: WAREHOUSE_HQ,
          },
        ],
      }),
    );

    expect(result.reserve.map((row) => row.location)).toEqual(['BRW-BB', 'HQ']);
    expect(result.reserve.map((row) => row.warehouse_id)).toEqual([
      WAREHOUSE_BRW,
      WAREHOUSE_HQ,
    ]);
    expect(new Set(result.reserve.map((row) => row.key)).size).toBe(2);
    expect(result.buy_qty).toBe('0');
  });

  it('carries a borrow already on the line back in, with the reason CS typed for it', () => {
    const result = draftFromLine(
      line({
        open_qty: '100',
        components: [
          {
            kind: 'borrow',
            qty: '40',
            reason: 'Held by PRJ-0052 Seri Emas Phase 2.',
            source_location: 'JB',
            source_warehouse_id: WAREHOUSE_HQ,
            donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
            donor_project_id: DONOR_PROJECT,
            cs_reason: 'Their hand-over is in December.',
          },
          {
            kind: 'reserve',
            qty: '60',
            reason: 'Free stock covers it.',
            source_location: 'BRW-BB',
            source_warehouse_id: WAREHOUSE_BRW,
          },
        ],
      }),
    );

    expect(result.borrow).toHaveLength(1);
    expect(result.borrow[0]).toMatchObject({
      source: 'other_project',
      warehouse_code: 'JB',
      donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
      donor_project_id: DONOR_PROJECT,
      qty: '40',
      reason: 'Their hand-over is in December.',
    });
    // A borrow read back from a component states no donor impact: that figure belongs to
    // the candidate it was taken from, and it has moved since.
    expect(result.borrow[0].donor_impact).toEqual({
      free_before: '0',
      free_after_full_borrow: '0',
      committed_qty: '0',
    });
    expect(lineBlockers(result)).toEqual([]);
  });

  it('opens an engine-proposed borrow on the ENGINE’s own sentence, so nothing blocks it', () => {
    // The drawer refused SO406804 line 19 until somebody retyped the sentence the engine had
    // already written: an engine proposal carries no `cs_reason` (nobody has typed anything),
    // and a borrow with no reason cannot be confirmed (AC-B09). The board has always seeded
    // the engine's sentence here, and the two surfaces compose on this same draft.
    const result = draftFromLine(
      line({
        open_qty: '4',
        components: [
          {
            kind: 'borrow',
            qty: '4',
            reason:
              'Take 4 on order (PO 202606-S0006 line 5, arriving about 2 Sep 2026)',
            source_location: 'BRW-IB',
            source_warehouse_id: WAREHOUSE_BRW,
            rung: 'supply_borrow',
            cs_reason: null,
            supply_key: 'po:f09bdfcf-7fb7-489c-a8d0-7ce2380c0f05',
            supply_document: 'PO 202606-S0006 line 5',
            arrival_date: '2026-09-02',
          },
        ],
      }),
    );

    expect(result.borrow[0]).toMatchObject({
      qty: '4',
      reason: 'Take 4 on order (PO 202606-S0006 line 5, arriving about 2 Sep 2026)',
      supply_key: 'po:f09bdfcf-7fb7-489c-a8d0-7ce2380c0f05',
      supply_document: 'PO 202606-S0006 line 5',
      arrival_date: '2026-09-02',
    });
    expect(lineBlockers(result)).toEqual([]);
  });

  it('carries the donor’s own delivery date, which is the order-back’s urgency', () => {
    const result = draftFromLine(
      line({
        open_qty: '50',
        components: [
          {
            kind: 'borrow',
            qty: '50',
            reason:
              'Borrow 50 arriving 15 Sep 2026 (SPO 202607-S0105) from SO414285 line 4 ' +
              '(JEREMY, due 12 Nov 2026); its debt lands in Nov 2026',
            source_location: 'BRW-IB',
            source_warehouse_id: WAREHOUSE_BRW,
            rung: 'supply_borrow',
            donor_so_number: 'SO414285',
            donor_line_no: 4,
            donor_agent_code: 'JEREMY',
            donor_required_date: '2026-11-12',
            supply_key: 'spo:9f2c1a44-1111-4c11-8c11-111111111111',
            supply_document: 'SPO 202607-S0105',
            arrival_date: '2026-09-15',
          },
        ],
      }),
    );

    expect(result.borrow[0].donor_required_date).toBe('2026-11-12');
    expect(confirmLineFromDraft(result).borrow[0].donor_required_date).toBe('2026-11-12');
  });

  it('reads a borrow with no donor project as one from another location', () => {
    const result = draftFromLine(
      line({
        open_qty: '40',
        components: [
          {
            kind: 'borrow',
            qty: '40',
            reason: 'Free stock at HQ, outside the reserve pool for this location.',
            source_location: 'HQ',
            source_warehouse_id: WAREHOUSE_HQ,
            cs_reason: 'HQ has no delivery booked before October.',
          },
        ],
      }),
    );

    expect(result.borrow[0].source).toBe('other_location');
  });

  it('opens a line with nothing proposed on a zero buy rather than an empty string', () => {
    const result = draftFromLine(line({ open_qty: '0', components: [] }));

    expect(result.buy_qty).toBe('0');
    expect(result.timely_spo_qty).toBe('0');
    expect(result.buy_reason).toBe('');
  });

  it('carries the discontinued buy reason back in', () => {
    const result = draftFromLine(
      line({
        open_qty: '25',
        is_discontinued: true,
        components: [
          {
            kind: 'buy',
            qty: '25',
            reason: 'Remaining uncovered need.',
            cs_reason: 'Customer accepted the last production batch in writing.',
          },
        ],
      }),
    );

    expect(result.buy_reason).toBe('Customer accepted the last production batch in writing.');
    expect(lineBlockers(result)).toEqual([]);
  });
});

describe('confirmLineFromDraft', () => {
  it('sends the whole composition under the key names the backend takes', () => {
    const payload = confirmLineFromDraft(
      draft({
        open_qty: '600',
        timely_spo_qty: '100',
        reserve: [reserve('200')],
        borrow: [borrow('50', 'HQ has nothing booked before October.')],
        buy_qty: '250',
      }),
    );

    expect(payload).toEqual({
      project_line_id: 'pl-1',
      timely_spo_qty: '100',
      reserve: [{ warehouse_id: WAREHOUSE_BRW, qty: '200' }],
      borrow: [
        {
          source: 'other_location',
          warehouse_id: WAREHOUSE_HQ,
          donor_project_id: null,
          qty: '50',
          reason: 'HQ has nothing booked before October.',
          donor_core_line_id: null,
          donor_so_number: null,
          donor_line_no: null,
          donor_agent_code: null,
          same_agent: false,
          donor_required_date: null,
          // Ladder v7.1 step 3 (S4): null on every borrow that is not a DOCUMENT, and sent
          // rather than omitted, so a payload built from a draft and one built from a
          // proposal have the same shape.
          supply_key: null,
          supply_document: null,
          arrival_date: null,
        },
      ],
      buy_qty: '250',
      buy_reason: null,
    });
  });

  it('drops a zero reserve and a zero borrow: they decide nothing', () => {
    const payload = confirmLineFromDraft(
      draft({
        open_qty: '100',
        reserve: [reserve('0'), reserve('100', 'r2')],
        borrow: [borrow('0', '')],
        buy_qty: '0',
      }),
    );

    expect(payload.reserve).toEqual([{ warehouse_id: WAREHOUSE_BRW, qty: '100' }]);
    expect(payload.borrow).toEqual([]);
    // Buy stays at 0 rather than disappearing: it is one quantity, not a list.
    expect(payload.buy_qty).toBe('0');
  });

  it('trims the reasons, so a space bar is not a reason', () => {
    const payload = confirmLineFromDraft(
      draft({
        open_qty: '100',
        borrow: [borrow('40', '  Their hand-over is in December.  ')],
        buy_qty: '60',
        buy_reason: '   Customer accepted the last batch.   ',
      }),
    );

    expect(payload.borrow[0].reason).toBe('Their hand-over is in December.');
    expect(payload.buy_reason).toBe('Customer accepted the last batch.');
  });

  it('sends no buy reason at all when only whitespace was typed', () => {
    expect(confirmLineFromDraft(draft({ buy_reason: '   ' })).buy_reason).toBeNull();
  });

  it('normalises what was typed, so 010.10 travels as 10.1', () => {
    const payload = confirmLineFromDraft(
      draft({ open_qty: '30.3', reserve: [reserve('010.10')], buy_qty: '20.20' }),
    );

    expect(payload.reserve[0].qty).toBe('10.1');
    expect(payload.buy_qty).toBe('20.2');
  });

  it('carries the donor project on a cross-project borrow', () => {
    const payload = confirmLineFromDraft(
      draft({
        open_qty: '40',
        borrow: [
          borrow('40', 'Their hand-over is in December.', {
            source: 'other_project',
            donor_project_id: DONOR_PROJECT,
            donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
          }),
        ],
        buy_qty: '0',
      }),
    );

    expect(payload.borrow[0]).toMatchObject({
      source: 'other_project',
      donor_project_id: DONOR_PROJECT,
    });
  });
});
