/**
 * ONE vocabulary for where supply comes from, keyed on the ENGINE'S RUNG and on nothing else.
 *
 * These tests were `boardSuggestion.test.ts`, and half of them pinned the bug: the file split
 * own from shared on the warehouse code's SITE PREFIX, so a pool draw from `BRW` on a line
 * fulfilled from `BRW-BB` read as "Use own location". The captain, on that exact cell: "Use own
 * location, 71 from BRW reads wrong. Own location is the line's -BB location. BRW is the SHARED
 * pool." So the cases that asserted the prefix rule are inverted here rather than deleted - they
 * are the regression.
 */
import { describe, expect, it } from 'vitest';
import {
  COLOURS,
  LABELS,
  cellSupply,
  contributionSupply,
  describe as describeSupply,
  dominantText,
  rowOf,
  rowText,
  segmentsOf,
  suggestionBreakdown,
} from './supplyVocabulary';
import type {
  BoardCell,
  BoardContribution,
  BoardDecision,
  BoardLineDecision,
  BoardSource,
} from '../types/fulfilmentPlanning.types';

function source(over: Partial<BoardSource> = {}): BoardSource {
  return { kind: 'reserve', qty: '10', reason: 'because', ...over };
}

function line(over: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:10',
    sales_order_id: 'so-1',
    so_number: 'SO416191',
    line_no: 10,
    item_code: 'CB2805A-DIY',
    qty: '13',
    qty_outstanding: '13',
    fulfilment_location: 'BRW-BB',
    unplannable: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...over,
  };
}

function cell(contributions: BoardContribution[]): BoardCell {
  return {
    item_code: 'CB2805A-DIY',
    bucket_key: '2026-09-01',
    total_qty: '13',
    locations: [],
    contributions,
    unplannable_count: 0,
    contested_count: 0,
  };
}

/** The row for a label, by its label. */
function row(rows: ReturnType<typeof suggestionBreakdown>, label: string) {
  const found = rows.find((entry) => entry.label === label);
  if (!found) throw new Error(`no row labelled ${label}`);
  return found;
}

/** Is this label on the card at all? A row with no quantity is not. */
function has(rows: ReturnType<typeof suggestionBreakdown>, label: string) {
  return rows.some((entry) => entry.label === label);
}

describe('rowOf reads the rung, never the warehouse code', () => {
  it('names every rung the engine can produce', () => {
    // The rung strings are `front_planning_engine.py`'s own constants. A rung this table does
    // not name is a rung the board would colour as nothing at all.
    expect(rowOf({ kind: 'reserve', rung: 'pool', qty: '1' })).toBe('shared');
    expect(rowOf({ kind: 'reserve', rung: 'group_take', qty: '1' })).toBe('own');
    expect(rowOf({ kind: 'borrow', rung: 'group_borrow', qty: '1' })).toBe('borrow_order');
    expect(rowOf({ kind: 'borrow', rung: 'cross_group_borrow', qty: '1' })).toBe(
      'borrow_other',
    );
    expect(rowOf({ kind: 'buy', rung: 'buy', qty: '1' })).toBe('buy');
    expect(rowOf({ kind: 'timely_spo', rung: 'incoming', qty: '1' })).toBe('incoming');
  });

  it('gives every kind a label and a colour, both a swatch and a text token', () => {
    for (const kind of [
      'buy',
      'shared',
      'own',
      'borrow_order',
      'borrow_other',
      'incoming',
    ] as const) {
      expect(LABELS[kind]).toBeTruthy();
      expect(COLOURS[kind].bar).toMatch(/^bg-/);
      expect(COLOURS[kind].text).toMatch(/^text-/);
    }
    expect(LABELS.shared).toBe('Use shared stock');
    expect(LABELS.own).toBe('Use own location');
    expect(LABELS.borrow_order).toBe('Borrow from another order');
    expect(LABELS.borrow_other).toBe('Borrow other location');
  });

  it('reads the pool as SHARED whatever site it is at, and however the line is coded', () => {
    // AC-A1, and the regression. `BRW` and `BRW-BB` share a prefix; they are not the same pile.
    expect(rowOf({ kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW' })).toBe('shared');
    expect(rowOf({ kind: 'reserve', rung: 'pool', qty: '4', location: 'MWH' })).toBe('shared');
  });

  it('reads a group take as the agent own location, whatever site the sibling is at', () => {
    expect(
      rowOf({ kind: 'reserve', rung: 'group_take', qty: '454', location: 'DC1-BB' }),
    ).toBe('own');
  });

  it('proposes nothing at all for a line the ladder was never walked for', () => {
    expect(rowOf({ kind: 'unplannable', qty: '13' })).toBeNull();
  });

  /**
   * A component with NO rung, which is every source and every decision row of a COVERED line:
   * the board rebuilds a frozen composition without carrying the rung the engine froze. Read
   * live off SO324132 rev 1 on 25 Aug - three reserve sources at DC1-BB / MWH-BB / WH3-BB, all
   * `rung: null`, on a BRW-BB line - which is what made AC-A2 read "Use shared stock".
   *
   * The reading is on the OWNERSHIP GROUP: the suffix after the first hyphen, the backend's own
   * rule (`sales_agent_service.group_of_warehouse_code`). Not the site (which called the shared
   * pool BRW the line's own stock) and not the exact code (which called the agent's own DC1-BB
   * somebody else's).
   */
  describe('a component with no rung of its own', () => {
    it('reads a sibling of the line own group as its own location (AC-A2)', () => {
      expect(rowOf({ kind: 'reserve', qty: '454', location: 'DC1-BB' }, 'BRW-BB')).toBe('own');
      expect(rowOf({ kind: 'reserve', qty: '267', location: 'MWH-BB' }, 'BRW-BB')).toBe('own');
      expect(rowOf({ kind: 'reserve', qty: '211', location: 'WH3-BB' }, 'BRW-BB')).toBe('own');
      // The line's own warehouse itself, which is the same group by definition.
      expect(rowOf({ kind: 'reserve', qty: '10', location: 'BRW-BB' }, 'BRW-BB')).toBe('own');
    });

    it('reads a bare site code as the shared pool (AC-A1)', () => {
      for (const pool of ['BRW', 'MWH', 'DC1', 'WH3', 'RSW']) {
        expect(rowOf({ kind: 'reserve', qty: '71', location: pool }, 'BRW-BB')).toBe('shared');
      }
    });

    it('reads another group warehouse as borrowing from another location', () => {
      expect(rowOf({ kind: 'reserve', qty: '9', location: 'BRW-HP' }, 'BRW-BB')).toBe(
        'borrow_other',
      );
      expect(rowOf({ kind: 'borrow', qty: '9', location: 'DC1-IB' }, 'BRW-BB')).toBe(
        'borrow_other',
      );
    });

    it('reads a borrow that names a donor order as a borrow from another order', () => {
      expect(
        rowOf({ kind: 'borrow', rung: 'group_borrow', qty: '3', location: 'BRW-BB' }, 'BRW-BB'),
      ).toBe('borrow_order');
    });

    it('reads a pool when the line own location is unknown, never as its own stock', () => {
      // Nothing to compare against is not a licence to claim the agent's group holds it.
      expect(rowOf({ kind: 'reserve', qty: '5', location: 'DC1-BB' })).toBe('borrow_other');
      expect(rowOf({ kind: 'reserve', qty: '5', location: 'BRW' })).toBe('shared');
    });

    it('still reads Buy and incoming off their kind, which never needed a location', () => {
      expect(rowOf({ kind: 'buy', qty: '5' })).toBe('buy');
      expect(rowOf({ kind: 'timely_spo', qty: '5' })).toBe('incoming');
    });
  });
});

describe('segmentsOf', () => {
  it('sums by kind and keeps only the kinds with a quantity, in the fixed order', () => {
    const segments = segmentsOf([
      { kind: 'reserve', rung: 'group_take', qty: '454', location: 'DC1-BB' },
      { kind: 'buy', rung: 'buy', qty: '3' },
      { kind: 'reserve', rung: 'group_take', qty: '267', location: 'MWH-BB' },
      { kind: 'reserve', rung: 'pool', qty: '0', location: 'BRW' },
    ]);

    expect(segments).toEqual([
      { kind: 'buy', qty: '3' },
      { kind: 'own', qty: '721' },
    ]);
  });

  it('names the largest kind in the fewest words a cell has room for', () => {
    expect(
      dominantText(
        segmentsOf([
          { kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW' },
          { kind: 'buy', rung: 'buy', qty: '4' },
        ]),
      ),
    ).toBe('Shared 71');
    expect(dominantText([])).toBe('');
  });
});

describe('describe', () => {
  it('renders a composition as one compact line, naming where each kind came from', () => {
    expect(
      describeSupply([
        { kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW' },
        { kind: 'buy', rung: 'buy', qty: '12' },
      ]),
    ).toBe('Buy 12 · Shared 71 (BRW)');
  });

  it('reads a SupplyComponent, which spells its warehouse source_location', () => {
    expect(
      describeSupply([
        { kind: 'reserve', rung: 'group_take', qty: '454', source_location: 'DC1-BB' },
        { kind: 'reserve', rung: 'group_take', qty: '267', source_location: 'MWH-BB' },
      ]),
    ).toBe('Own 721 (DC1-BB, MWH-BB)');
  });

  it('says nothing for a composition with nothing in it', () => {
    expect(describeSupply([])).toBe('');
    expect(describeSupply([{ kind: 'unplannable', qty: '13' }])).toBe('');
  });
});

describe('suggestionBreakdown', () => {
  it('states only the kinds with a quantity, keeping their fixed order', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'buy', rung: 'buy', qty: '3', location: null }),
            source({ kind: 'reserve', rung: 'pool', qty: '13', location: 'BRW' }),
          ],
        }),
      ]),
    );

    expect(rows.map((entry) => entry.label)).toEqual(['Buy', 'Use shared stock']);
  });

  it('says nothing at all for a cell the ladder proposes nothing for', () => {
    expect(suggestionBreakdown(cell([line()]))).toEqual([]);
  });

  it('reads a pool draw as shared stock, and names the pool it came from (AC-A1)', () => {
    // SRT382-6-DIY on SO415472: "Use shared stock 71 from BRW", never "Use own location".
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [source({ kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW' })],
        }),
      ]),
    );

    expect(row(rows, 'Use shared stock').qty).toBe('71');
    expect(rowText(row(rows, 'Use shared stock'))).toBe('71 from BRW');
    expect(has(rows, 'Use own location')).toBe(false);
  });

  it('names the quantity PER LOCATION on a group take (AC-A2)', () => {
    // CWCY605 on SO324132 rev 1. The split is the instruction: three movements of stock,
    // and somebody has to key each one.
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'reserve', rung: 'group_take', qty: '454', location: 'DC1-BB' }),
            source({ kind: 'reserve', rung: 'group_take', qty: '267', location: 'MWH-BB' }),
            source({ kind: 'reserve', rung: 'group_take', qty: '211', location: 'WH3-BB' }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Use own location').qty).toBe('932');
    expect(rowText(row(rows, 'Use own location'))).toBe(
      '454 from DC1-BB, 267 from MWH-BB, 211 from WH3-BB',
    );
  });

  it('tells the two borrows apart by rung, not by where they happen to be (AC-A3)', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'borrow', rung: 'group_borrow', qty: '3', location: 'BRW-BB' }),
            source({ kind: 'borrow', rung: 'cross_group_borrow', qty: '9', location: 'BRW-HP' }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Borrow from another order').qty).toBe('3');
    expect(row(rows, 'Borrow other location').qty).toBe('9');
    expect(has(rows, 'Use own location')).toBe(false);
  });

  it('reads a buy as a buy, and names no location because it is held nowhere yet', () => {
    const rows = suggestionBreakdown(
      cell([line({ sources: [source({ kind: 'buy', rung: 'buy', qty: '13', location: null })] })]),
    );

    expect(row(rows, 'Buy').places).toEqual([]);
    expect(rowText(row(rows, 'Buy'))).toBe('13');
  });

  it('sums across every line of the cell and totals each location once', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          key: 'a',
          sources: [source({ kind: 'reserve', rung: 'pool', qty: '5', location: 'BRW' })],
        }),
        line({
          key: 'b',
          sources: [
            source({ kind: 'reserve', rung: 'pool', qty: '8', location: 'BRW' }),
            source({ kind: 'reserve', rung: 'group_take', qty: '2', location: 'MWH-BB' }),
          ],
        }),
      ]),
    );

    expect(rowText(row(rows, 'Use shared stock'))).toBe('13 from BRW');
    expect(row(rows, 'Use own location').qty).toBe('2');
  });

  it('carries incoming supply as its own row, last, and only when there is some', () => {
    // Never folded into Buy: the incoming quantity is already bought and on its way, and
    // adding it to Buy would propose buying it twice.
    expect(has(suggestionBreakdown(cell([line()])), 'Incoming supply')).toBe(false);

    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'buy', rung: 'buy', qty: '2' }),
            source({ kind: 'timely_spo', rung: 'incoming', qty: '7', location: 'BRW-BB' }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Incoming supply').qty).toBe('7');
    expect(rows[rows.length - 1].label).toBe('Incoming supply');
  });

  it('carries the engine own sentence when every source on the row gives the same one', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({
              kind: 'buy',
              rung: 'buy',
              qty: '13',
              location: null,
              reason: 'Delivery date beyond the lead time window; stock kept for nearer orders',
            }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Buy').note).toBe(
      'Delivery date beyond the lead time window; stock kept for nearer orders',
    );
  });

  it('says nothing when the lines on a row disagree about why', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          key: 'a',
          sources: [source({ kind: 'buy', rung: 'buy', qty: '5', reason: 'one reason' })],
        }),
        line({
          key: 'b',
          sources: [source({ kind: 'buy', rung: 'buy', qty: '5', reason: 'another' })],
        }),
      ]),
    );

    expect(row(rows, 'Buy').qty).toBe('10');
    expect(row(rows, 'Buy').note).toBeUndefined();
  });

  it('says nothing can be sourced for a line whose order states no location', () => {
    const rows = suggestionBreakdown(
      cell([line({ unplannable: true, sources: [source({ kind: 'unplannable', qty: '13' })] })]),
    );

    expect(rows).toEqual([]);
  });
});

/**
 * SO324132 rev 1, EXACTLY as the board sends it (read live off :8080 on 25 Aug).
 *
 * CWCY605 is a COVERED line, and `_apply_frozen` rebuilds its composition without the rung the
 * engine froze: three reserve sources at DC1-BB / MWH-BB / WH3-BB, `rung: null` on every one,
 * and a decision whose three reserve rows are the same. Both surfaces therefore read the
 * fallback, and both read "Use shared stock" until the fallback learned about ownership groups.
 */
describe('AC-A2: a covered line whose composition arrives with no rungs', () => {
  const unrunged = [
    { kind: 'reserve' as const, qty: '454', location: 'DC1-BB', reason: 'Reserved at DC1-BB.' },
    { kind: 'reserve' as const, qty: '267', location: 'MWH-BB', reason: 'Reserved at MWH-BB.' },
    { kind: 'reserve' as const, qty: '211', location: 'WH3-BB', reason: 'Reserved at WH3-BB.' },
  ];

  const covered = line({
    item_code: 'CWCY605',
    qty: '932',
    qty_outstanding: '932',
    fulfilment_location: 'BRW-BB',
    covered: true,
    sources: unrunged,
    decision: {
      revision_no: 1,
      timely_spo_qty: '0',
      reserve: [
        { warehouse_id: 'wh-dc1', location: 'DC1-BB', qty: '454' },
        { warehouse_id: 'wh-mwh', location: 'MWH-BB', qty: '267' },
        { warehouse_id: 'wh-wh3', location: 'WH3-BB', qty: '211' },
      ],
      borrow: [],
      buy_qty: '0',
    },
  });

  it('the Suggestion card reads Use own location, named per location', () => {
    const rows = suggestionBreakdown(cell([covered]));

    expect(rows.map((entry) => entry.label)).toEqual(['Use own location']);
    expect(rowText(rows[0])).toBe('454 from DC1-BB, 267 from MWH-BB, 211 from WH3-BB');
  });

  it('the decided bar reads own, solid, off the same composition', () => {
    const supply = contributionSupply(covered, null);

    expect(supply.segments).toEqual([{ kind: 'own', qty: '932' }]);
    expect(supply.decided).toBe(true);
  });

  it('a BRW pool draw on the same line still reads shared (AC-A1 is not undone)', () => {
    const pooled = line({
      fulfilment_location: 'BRW-BB',
      covered: true,
      sources: [{ kind: 'reserve', qty: '71', location: 'BRW', reason: 'Reserved at BRW.' }],
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [{ warehouse_id: 'wh-brw', location: 'BRW', qty: '71' }],
        borrow: [],
        buy_qty: '0',
      },
    });

    expect(suggestionBreakdown(cell([pooled]))[0].label).toBe('Use shared stock');
    expect(contributionSupply(pooled, null).segments).toEqual([{ kind: 'shared', qty: '71' }]);
  });

  it('resolves per contributing line, because a cell spans lines at different groups', () => {
    // DC1-BB is the agent's own group on a BRW-BB line and somebody else's on a BRW-IB one.
    const ib = line({
      key: 'ib',
      fulfilment_location: 'BRW-IB',
      sources: [{ kind: 'reserve', qty: '100', location: 'DC1-BB', reason: 'r' }],
    });

    const rows = suggestionBreakdown(cell([covered, ib]));

    expect(rows.map((entry) => entry.label)).toEqual([
      'Use own location',
      'Borrow other location',
    ]);
    expect(rows[0].qty).toBe('932');
    expect(rows[1].qty).toBe('100');
  });
});

describe('what the bar is drawn from', () => {
  const buyProposal = line({
    sources: [
      source({ kind: 'buy', rung: 'buy', qty: '71', location: null }),
      source({ kind: 'reserve', rung: 'pool', qty: '0', location: 'BRW', warehouse_id: 'wh-brw' }),
    ],
  });

  it('draws the engine proposal, faded, while nothing has been decided', () => {
    const supply = contributionSupply(buyProposal, null);

    expect(supply.segments).toEqual([{ kind: 'buy', qty: '71' }]);
    expect(supply.decided).toBe(false);
  });

  it('flips Buy to Shared the moment an amend is ticked, and back when it is cleared (AC-C2)', () => {
    const amended: BoardDecision = {
      verdict: 'amended',
      reserve: [{ warehouse_id: 'wh-brw', location: 'BRW', qty: '71' }],
      borrow: [],
      buy_qty: '0',
      reason: 'The pool can cover it',
    };

    const ticked = contributionSupply(buyProposal, amended);
    expect(ticked.segments).toEqual([{ kind: 'shared', qty: '71' }]);
    expect(ticked.decided).toBe(true);

    const cleared = contributionSupply(buyProposal, null);
    expect(cleared.segments).toEqual([{ kind: 'buy', qty: '71' }]);
    expect(cleared.decided).toBe(false);
  });

  it('keeps the proposal on an approval, because an approval is the proposal', () => {
    const supply = contributionSupply(buyProposal, { verdict: 'approved' });

    expect(supply.segments).toEqual([{ kind: 'buy', qty: '71' }]);
    expect(supply.decided).toBe(true);
  });

  it('leaves a rejection faded: a rejection settles no supply', () => {
    const supply = contributionSupply(buyProposal, {
      verdict: 'rejected',
      reason: 'Rejected on the planning board.',
    });

    expect(supply.decided).toBe(false);
  });

  it('draws a confirmed revision solid, in the words its own rungs give it', () => {
    const frozen: BoardLineDecision = {
      revision_no: 1,
      timely_spo_qty: '0',
      reserve: [
        { warehouse_id: 'wh-dc1', location: 'DC1-BB', qty: '454' },
        { warehouse_id: 'wh-mwh', location: 'MWH-BB', qty: '267' },
      ],
      borrow: [],
      buy_qty: '0',
    };
    const covered = line({
      covered: true,
      decision: frozen,
      sources: [
        source({
          kind: 'reserve',
          rung: 'group_take',
          qty: '454',
          location: 'DC1-BB',
          warehouse_id: 'wh-dc1',
        }),
        source({
          kind: 'reserve',
          rung: 'group_take',
          qty: '267',
          location: 'MWH-BB',
          warehouse_id: 'wh-mwh',
        }),
      ],
    });

    const supply = contributionSupply(covered, null);

    expect(supply.segments).toEqual([{ kind: 'own', qty: '721' }]);
    expect(supply.decided).toBe(true);
  });

  it('names a drafted borrow that cites a donor order as a borrow from another order', () => {
    const supply = contributionSupply(buyProposal, {
      verdict: 'amended',
      reserve: [],
      borrow: [
        {
          source: 'other_location',
          warehouse_id: 'wh-x',
          warehouse_code: 'BRW-BB',
          qty: '71',
          reason: 'Authorised by agent',
          donor_so_number: 'SO394803',
        },
      ],
      buy_qty: '0',
    });

    expect(supply.segments).toEqual([{ kind: 'borrow_order', qty: '71' }]);
  });

  it('is solid for a cell only once EVERY contributing line is settled', () => {
    const a = line({ key: 'a', sources: [source({ kind: 'buy', rung: 'buy', qty: '10' })] });
    const b = line({
      key: 'b',
      sources: [source({ kind: 'reserve', rung: 'pool', qty: '30', location: 'BRW' })],
    });

    const half = cellSupply(cell([a, b]), { a: { verdict: 'approved' } });
    expect(half.decided).toBe(false);
    expect(half.segments).toEqual([
      { kind: 'buy', qty: '10' },
      { kind: 'shared', qty: '30' },
    ]);

    const whole = cellSupply(cell([a, b]), {
      a: { verdict: 'approved' },
      b: { verdict: 'approved' },
    });
    expect(whole.decided).toBe(true);
  });
});
