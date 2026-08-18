/**
 * The board's arithmetic (PLAN section 13).
 *
 * Three things here are acceptance criteria rather than implementation detail, and each is
 * asserted directly: which column a line lands in (13.3), the order competing lines are served
 * in (13.5), and when an order becomes confirmable (13.4). None of them needs a grid mounted.
 */
import { describe, expect, it } from 'vitest';
import { amendNeedsReason, commitPreviewFor, standingsFor } from './fulfilmentBoard';
import {
  bucketKeyFor,
  buildBoard,
  compareContributions,
  DAY_WINDOW_COLUMNS,
  LIVE_POLICY,
  monthStart,
  PREVIEW_POLICY,
  rankScore,
  weekStart,
  type BoardDemandLine,
} from './__testsupport__/boardFixture';

const TODAY = '2026-08-18';

function line(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    customer_name: 'A CUSTOMER SDN BHD',
    project_label: 'A PROJECT',
    line_no: 1,
    item_code: 'WESERP10B',
    qty: '100',
    required_date: '2026-09-04',
    fulfilment_location: 'BRW-BB',
    priority: null,
    order_date: '2026-01-05',
    payment_terms_days: 30,
    demand_class: 'project',
    ...overrides,
  };
}

describe('weekStart / monthStart', () => {
  it('snaps to the Monday of the ISO week', () => {
    // 2026-09-04 is a Friday; its week begins Monday 2026-08-31.
    expect(weekStart('2026-09-04')).toBe('2026-08-31');
    expect(weekStart('2026-08-31')).toBe('2026-08-31');
    // A Sunday belongs to the week that started six days earlier, not the next one.
    expect(weekStart('2026-09-06')).toBe('2026-08-31');
  });

  it('snaps to the first of the month', () => {
    expect(monthStart('2026-09-04')).toBe('2026-09-01');
  });
});

describe('bucketKeyFor (13.3, captain: do not put overdue together)', () => {
  it('buckets a past date by its OWN date, never into one aggregate column', () => {
    // The captain, verbatim: "don't put overdue together, still split by the date, don't put
    // under overdue". A four-year-old required date is still a date, and collapsing it loses
    // the only thing that says how late it is.
    expect(bucketKeyFor('2022-07-03', TODAY, 'week')).toBe(weekStart('2022-07-03'));
    expect(bucketKeyFor('2026-08-17', TODAY, 'week')).toBe(weekStart('2026-08-17'));
    expect(bucketKeyFor('2022-07-03', TODAY, 'day')).toBe('2022-07-03');
    expect(bucketKeyFor('2022-07-03', TODAY, 'month')).toBe('2022-07-01');
  });

  it('keeps a line with no date in its own column rather than guessing one', () => {
    expect(bucketKeyFor(null, TODAY, 'week')).toBe('no_date');
    expect(bucketKeyFor(undefined, TODAY, 'week')).toBe('no_date');
  });

  it('buckets a future date by week or by month', () => {
    expect(bucketKeyFor('2026-09-04', TODAY, 'week')).toBe('2026-08-31');
    expect(bucketKeyFor('2026-09-04', TODAY, 'month')).toBe('2026-09-01');
  });

  it('buckets today itself like any other date', () => {
    expect(bucketKeyFor(TODAY, TODAY, 'week')).toBe(weekStart(TODAY));
  });
});

describe('rankScore (13.5, lifted from the reorder engine)', () => {
  it('is the weighted mean over the PRESENT factors', () => {
    expect(
      rankScore([
        { key: 'a', weight: 3, value: 1, present: true },
        { key: 'b', weight: 1, value: 0, present: true },
      ]),
    ).toBeCloseTo(0.75);
  });

  it('drops an absent factor from BOTH sums rather than scoring it zero', () => {
    // With the absent factor merely zeroed this would be 0.75; dropped, the present factor
    // stands alone. An unknown is not a bad score.
    expect(
      rankScore([
        { key: 'a', weight: 3, value: 1, present: true },
        { key: 'b', weight: 1, value: null, present: false },
      ]),
    ).toBeCloseTo(1);
  });

  it('is 0 when nothing is present, which is what the live policy produces here', () => {
    expect(rankScore([{ key: 'a', weight: 1, value: null, present: false }])).toBe(0);
  });
});

describe('the live policy cannot rank a board row (13.5, the blocker)', () => {
  const board = buildBoard(
    [
      line({ sales_order_id: 'so-a', so_number: 'SO000003', line_no: 1, required_date: '2026-09-04' }),
      line({ sales_order_id: 'so-b', so_number: 'SO000001', line_no: 2, required_date: '2026-09-02' }),
    ],
    { today: TODAY, policy: LIVE_POLICY },
  );

  it('scores every contributor 0, because it weights only a factor no sales-order line has', () => {
    expect(board.cells[0].contributions.map((entry) => entry.rank_score)).toEqual([0, 0]);
  });

  it('marks po_document_sequence absent rather than pretending it is zero', () => {
    const sequence = board.cells[0].contributions[0].rank_factors.find(
      (factor) => factor.key === 'po_document_sequence',
    );
    expect(sequence?.present).toBe(false);
    expect(sequence?.value).toBeNull();
  });

  it('degrades to sales-order order rather than to an arbitrary one', () => {
    expect(board.cells[0].contributions.map((entry) => entry.so_number)).toEqual([
      'SO000001',
      'SO000003',
    ]);
  });

  it('names the policy it ranked by, so a flat ranking is explainable', () => {
    expect(board.policy.name).toBe("Today's rule (PO document sequence)");
    expect(board.policy.is_preview).toBe(false);
  });
});

describe('the preview policy ranks on the captain\'s three factors (13.5)', () => {
  it('puts the sooner delivery date first, need_by_date being the heaviest', () => {
    const board = buildBoard(
      [
        // Same week, so they land in one cell and genuinely compete.
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1, required_date: '2026-09-04' }),
        line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 2, required_date: '2026-09-02' }),
      ],
      { today: TODAY, policy: PREVIEW_POLICY },
    );
    expect(board.cells[0].contributions[0].so_number).toBe('SO000002');
    expect(board.cells[0].contributions[0].rank_score).toBeGreaterThan(
      board.cells[0].contributions[1].rank_score,
    );
  });

  it('breaks a dead heat on document date, the older document winning', () => {
    const board = buildBoard(
      [
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1, order_date: '2026-07-01' }),
        line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 2, order_date: '2024-01-01' }),
      ],
      { today: TODAY, policy: PREVIEW_POLICY },
    );
    expect(board.cells[0].contributions[0].so_number).toBe('SO000002');
  });

  it('prefers the customer on shorter payment terms, all else equal', () => {
    const board = buildBoard(
      [
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1, payment_terms_days: 90 }),
        line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 2, payment_terms_days: 14 }),
      ],
      { today: TODAY, policy: PREVIEW_POLICY },
    );
    expect(board.cells[0].contributions[0].so_number).toBe('SO000002');
  });

  it('never ranks a customer with no terms as best or as worst: the factor is absent', () => {
    const board = buildBoard(
      [
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1, payment_terms_days: null }),
        line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 2, payment_terms_days: 30 }),
      ],
      { today: TODAY, policy: PREVIEW_POLICY },
    );
    const unknown = board.cells[0].contributions.find((entry) => entry.so_number === 'SO000001');
    const credit = unknown?.rank_factors.find((factor) => factor.key === 'customer_credit');
    expect(credit?.present).toBe(false);
    expect(credit?.value).toBeNull();
  });

  it('carries the factors that produced the score, so the planner can see WHY', () => {
    const board = buildBoard([line()], { today: TODAY, policy: PREVIEW_POLICY });
    const keys = board.cells[0].contributions[0].rank_factors.map((factor) => factor.key);
    expect(keys).toContain('need_by_date');
    expect(keys).toContain('document_age');
    expect(keys).toContain('customer_credit');
  });

  it('serves scarce stock down the ranking, not down the input order', () => {
    const board = buildBoard(
      [
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1, qty: '100', required_date: '2026-12-01' }),
        line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 2, qty: '100', required_date: '2026-09-02' }),
      ],
      { today: TODAY, policy: PREVIEW_POLICY, freeStock: { 'WESERP10B|BRW-BB': '100' } },
    );
    const cell = board.cells.find((entry) => entry.bucket_key === '2026-08-31');
    const winner = cell?.contributions.find((entry) => entry.so_number === 'SO000002');
    expect(winner?.sources.map((source) => source.kind)).toEqual(['reserve']);
  });
});

describe('compareContributions', () => {
  it('puts the higher rank first', () => {
    expect(
      compareContributions(
        { rank_score: 0.9, so_number: 'SO000002', line_no: 1 },
        { rank_score: 0.4, so_number: 'SO000001', line_no: 1 },
      ),
    ).toBeLessThan(0);
  });

  it('is total, so the board cannot reshuffle between two renders', () => {
    const left = { rank_score: 0.5, so_number: 'SO000001', line_no: 1 };
    const right = { rank_score: 0.5, so_number: 'SO000002', line_no: 1 };
    expect(compareContributions(left, right)).toBeLessThan(0);
    expect(compareContributions(right, left)).toBeGreaterThan(0);
    expect(compareContributions(left, { ...left, line_no: 2 })).toBeLessThan(0);
  });
});

describe('buildBoard: the axes', () => {
  it('orders every dated bucket chronologically, past included, with No date pinned last', () => {
    const board = buildBoard(
      [
        line({ line_no: 1, required_date: '2026-09-04' }),
        line({ line_no: 2, required_date: '2022-07-03' }),
        line({ line_no: 3, required_date: null, fulfilment_location: null }),
        line({ line_no: 4, required_date: '2026-12-01' }),
      ],
      { today: TODAY },
    );
    expect(board.dateBuckets.map((bucket) => bucket.key)).toEqual([
      '2022-06-27',
      '2026-08-31',
      '2026-11-30',
      'no_date',
    ]);
    expect(board.dateBuckets[0].label).toBe('w/c 27 Jun 2022');
    expect(board.dateBuckets[3].label).toBe('No date');
    expect(board.dateBuckets.map((bucket) => bucket.kind)).toEqual([
      'dated',
      'dated',
      'dated',
      'no_date',
    ]);
  });

  /**
   * The past is TINTED, not merged. `is_past` is the server's verdict about a bucket that
   * lies entirely before `as_of`, and it is the only thing the grid may colour on: deriving
   * it here would make the tint disagree with the bucketing the server actually did.
   */
  it('marks a bucket that lies entirely before the as-of date as past, and leaves the rest alone', () => {
    const board = buildBoard(
      [
        line({ line_no: 1, required_date: '2022-07-03' }),
        line({ line_no: 2, required_date: '2026-09-04' }),
        line({ line_no: 3, required_date: null, fulfilment_location: null }),
      ],
      { today: TODAY },
    );
    expect(board.dateBuckets.map((bucket) => `${bucket.key} ${bucket.is_past}`)).toEqual([
      '2022-06-27 true',
      '2026-08-31 false',
      'no_date false',
    ]);
  });

  it('does not call the bucket holding the as-of date itself past', () => {
    const board = buildBoard([line({ required_date: TODAY })], { today: TODAY });
    expect(board.dateBuckets[0].is_past).toBe(false);
  });

  /**
   * A line's own lateness is a different question from its bucket's, and only the line-level
   * one can answer "how many lines are late": a line due two days ago sits in the week that
   * contains as_of, whose period has NOT ended.
   */
  it('marks a line past by its OWN required date, even when its bucket is not', () => {
    const board = buildBoard(
      [
        line({ line_no: 1, required_date: '2026-08-17' }),
        line({ line_no: 2, required_date: '2026-08-20' }),
      ],
      { today: TODAY },
    );
    expect(board.dateBuckets[0].is_past).toBe(false);
    expect(board.cells[0].past_count).toBe(1);
    expect(
      board.cells[0].contributions.map((entry) => `${entry.required_date} ${entry.is_past}`).sort(),
    ).toEqual(['2026-08-17 true', '2026-08-20 false']);
  });

  it('never calls an undated line past, because nobody said when it was due', () => {
    const board = buildBoard([line({ required_date: null, fulfilment_location: null })], {
      today: TODAY,
    });
    expect(board.cells[0].past_count).toBe(0);
    expect(board.cells[0].contributions[0].is_past).toBe(false);
  });

  it('produces NO cell for a product and date nobody owes, so the grid can render blank', () => {
    const board = buildBoard(
      [
        line({ item_code: 'AAA', required_date: '2026-09-04' }),
        line({ item_code: 'BBB', required_date: '2026-12-01', line_no: 2 }),
      ],
      { today: TODAY },
    );
    expect(board.productRows.map((row) => row.item_code)).toEqual(['AAA', 'BBB']);
    expect(board.cells).toHaveLength(2);
    expect(board.cells.find((cell) => cell.item_code === 'AAA' && cell.bucket_key === '2026-11-30')).toBeUndefined();
  });

  it('echoes the date it was built against, so the past tint is reproducible', () => {
    expect(buildBoard([line()], { today: TODAY }).as_of).toBe(TODAY);
  });
});

describe('buildBoard: aggregation across orders', () => {
  const shared: BoardDemandLine[] = [
    line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1, qty: '100', required_date: '2026-09-04' }),
    line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 2, qty: '50', required_date: '2026-09-02' }),
    line({ sales_order_id: 'so-c', so_number: 'SO000003', line_no: 3, qty: '25', required_date: '2026-09-01', fulfilment_location: 'BRW-IB' }),
  ];

  it('sums one cell across every contributing sales order', () => {
    const board = buildBoard(shared, { today: TODAY });
    const cell = board.cells.find((entry) => entry.bucket_key === '2026-08-31');
    expect(cell?.total_qty).toBe('175');
    expect(cell?.contributions).toHaveLength(3);
  });

  it('orders the contributions by the ranking, not by input order', () => {
    const board = buildBoard(shared, { today: TODAY, policy: PREVIEW_POLICY });
    const cell = board.cells.find((entry) => entry.bucket_key === '2026-08-31');
    expect(cell?.contributions.map((entry) => entry.so_number)).toEqual([
      'SO000003',
      'SO000002',
      'SO000001',
    ]);
  });

  it('reports one source-strip entry per distinct location, biggest first (13.7)', () => {
    const board = buildBoard(shared, { today: TODAY });
    const cell = board.cells.find((entry) => entry.bucket_key === '2026-08-31');
    expect(cell?.locations).toEqual([
      { location: 'BRW-BB', qty: '150' },
      { location: 'BRW-IB', qty: '25' },
    ]);
  });
});

describe('buildBoard: allocation and contest (13.5)', () => {
  it('serves the earliest line in full and buys the rest, naming the loser as contested', () => {
    const board = buildBoard(
      [
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1, qty: '100', required_date: '2026-09-04' }),
        line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 2, qty: '100', required_date: '2026-09-02' }),
      ],
      { today: TODAY, policy: PREVIEW_POLICY, freeStock: { 'WESERP10B|BRW-BB': '100' } },
    );
    const cell = board.cells[0];
    const [first, second] = cell.contributions;
    expect(first.so_number).toBe('SO000002');
    expect(first.sources.map((source) => `${source.kind} ${source.qty}`)).toEqual(['reserve 100']);
    expect(first.contested).toBe(false);
    expect(second.sources.map((source) => `${source.kind} ${source.qty}`)).toEqual(['buy 100']);
    expect(second.contested).toBe(true);
    expect(cell.contested_count).toBe(1);
  });

  it('splits one line into reserve plus buy when the pool runs out mid-line', () => {
    const board = buildBoard([line({ qty: '100' })], {
      today: TODAY,
      freeStock: { 'WESERP10B|BRW-BB': '40' },
    });
    expect(board.cells[0].contributions[0].sources.map((source) => `${source.kind} ${source.qty}`)).toEqual([
      'reserve 40',
      'buy 60',
    ]);
  });

  it('does NOT call a line contested when the location simply never held any stock', () => {
    const board = buildBoard([line({ qty: '100' })], { today: TODAY, freeStock: {} });
    const contribution = board.cells[0].contributions[0];
    expect(contribution.sources.map((source) => source.kind)).toEqual(['buy']);
    expect(contribution.contested).toBe(false);
  });

  it('never promises the same free stock on two different dates', () => {
    const board = buildBoard(
      [
        line({ line_no: 1, qty: '80', required_date: '2026-09-04' }),
        line({ line_no: 2, qty: '80', required_date: '2026-12-01' }),
      ],
      { today: TODAY, freeStock: { 'WESERP10B|BRW-BB': '100' } },
    );
    const reserved = board.cells
      .flatMap((cell) => cell.contributions)
      .flatMap((entry) => entry.sources)
      .filter((source) => source.kind === 'reserve')
      .reduce((total, source) => total + Number.parseFloat(source.qty), 0);
    expect(reserved).toBe(100);
  });

  it('allocates per location: stock at one cannot cover a line owed from another', () => {
    const board = buildBoard(
      [
        line({ line_no: 1, qty: '50', fulfilment_location: 'BRW-IB' }),
        line({ line_no: 2, qty: '50', fulfilment_location: 'BRW-BB' }),
      ],
      { today: TODAY, freeStock: { 'WESERP10B|BRW-IB': '50' } },
    );
    const byLocation = Object.fromEntries(
      board.cells[0].contributions.map((entry) => [
        entry.fulfilment_location,
        entry.sources.map((source) => source.kind).join('+'),
      ]),
    );
    expect(byLocation['BRW-IB']).toBe('reserve');
    expect(byLocation['BRW-BB']).toBe('buy');
  });
});

describe('buildBoard: a line with no location (AC-FP16)', () => {
  const board = buildBoard(
    [
      line({ line_no: 1, qty: '24', fulfilment_location: null }),
      line({ line_no: 2, qty: '10' }),
    ],
    { today: TODAY, freeStock: { 'WESERP10B|BRW-BB': '999' } },
  );
  const cell = board.cells[0];

  it('still contributes its quantity, so the demand is not hidden', () => {
    expect(cell.total_qty).toBe('34');
    expect(cell.unplannable_count).toBe(1);
  });

  it('is proposed nothing at all, rather than a Reserve of zero dressed up as a plan', () => {
    const blocked = cell.contributions.find((entry) => entry.unplannable);
    expect(blocked?.sources.map((source) => source.kind)).toEqual(['unplannable']);
    expect(blocked?.sources[0].reason).toContain('No fulfilment location');
  });

  it('gathers the location-less quantity under its own strip entry', () => {
    expect(cell.locations).toContainEqual({ location: null, qty: '24' });
  });
});

describe('standingsFor and commitPreviewFor (13.4)', () => {
  // Built through buildBoard so the contributions carry REAL keys, which is the only kind the
  // counter reads now.
  const board = buildBoard(
    [
      line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1 }),
      line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 2, item_code: 'TPE-9204' }),
      line({ sales_order_id: 'so-b', so_number: 'SO000002', line_no: 3 }),
    ],
    { today: TODAY },
  );
  const contributions = board.cells.flatMap((cell) => cell.contributions);

  it('counts the lines of each order inside the selection', () => {
    expect(
      standingsFor(contributions, {}).map(
        (entry) => `${entry.so_number} ${entry.decided_count}/${entry.line_count}`,
      ),
    ).toEqual(['SO000001 0/2', 'SO000002 0/1']);
  });

  it('counts a verdict against the order whose contribution it was', () => {
    const key = contributions.find((entry) => entry.so_number === 'SO000001')!.key;
    const standings = standingsFor(contributions, { [key]: { verdict: 'approved' } });
    expect(standings[0].decided_count).toBe(1);
    expect(standings[1].decided_count).toBe(0);
  });

  it('states what a partial confirmation would commit and what it would leave', () => {
    const key = contributions.find((entry) => entry.so_number === 'SO000001')!.key;
    const standings = standingsFor(contributions, { [key]: { verdict: 'approved' } });
    // Confirm is NOT gated on completeness (13.4): the planner commits what they decided and
    // the rest keeps flowing to reorder planning, so the screen owes the consequence.
    expect(commitPreviewFor(standings[0])).toEqual({
      committing: 1,
      leaving_undecided: 1,
      blocked: 0,
    });
  });

  it('has nothing to commit before anything is decided', () => {
    expect(commitPreviewFor(standingsFor(contributions, {})[0]).committing).toBe(0);
  });

  it('counts a line that can never be decided here as left behind, and names it as blocked', () => {
    const withBlocked = buildBoard(
      [
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 1 }),
        line({ sales_order_id: 'so-a', so_number: 'SO000001', line_no: 9, fulfilment_location: null }),
      ],
      { today: TODAY },
    );
    const preview = commitPreviewFor(
      standingsFor(withBlocked.cells.flatMap((cell) => cell.contributions), {})[0],
    );
    expect(preview.leaving_undecided).toBe(2);
    expect(preview.blocked).toBe(1);
  });
});

describe('day granularity (13.3)', () => {
  it('keys on the exact date', () => {
    expect(bucketKeyFor('2026-09-04', TODAY, 'day')).toBe('2026-09-04');
  });

  it('renders a fixed window rather than a column per distinct date', () => {
    const board = buildBoard(
      [
        line({ line_no: 1, required_date: '2026-09-04' }),
        line({ line_no: 2, required_date: '2027-06-01' }),
      ],
      { today: TODAY, granularity: 'day' },
    );
    const dated = board.dateBuckets.filter((bucket) => bucket.kind === 'dated');
    expect(dated).toHaveLength(DAY_WINDOW_COLUMNS);
  });

  it('renders an empty day inside the window, because the gap is the information', () => {
    const board = buildBoard([line({ required_date: '2026-09-04' })], {
      today: TODAY,
      granularity: 'day',
      dayWindowStart: '2026-09-01',
    });
    const keys = board.dateBuckets.map((bucket) => bucket.key);
    expect(keys).toContain('2026-09-02');
    expect(board.cells.some((cell) => cell.bucket_key === '2026-09-02')).toBe(false);
  });

  it('still pins No date last, and starts the window at the earliest date owed', () => {
    const board = buildBoard(
      [
        line({ line_no: 1, required_date: '2026-09-04' }),
        line({ line_no: 2, required_date: '2022-07-03' }),
        line({ line_no: 3, required_date: null, fulfilment_location: null }),
      ],
      { today: TODAY, granularity: 'day' },
    );
    expect(board.dateBuckets[0].key).toBe('2022-07-03');
    expect(board.dateBuckets[0].is_past).toBe(true);
    expect(board.dateBuckets[board.dateBuckets.length - 1].key).toBe('no_date');
  });
});

describe('amendNeedsReason', () => {
  const board = buildBoard([line({ qty: '100' })], {
    today: TODAY,
    freeStock: { 'WESERP10B|BRW-BB': '40' },
  });
  const contribution = board.cells[0].contributions[0];

  it('does not demand a reason for accepting the proposal unchanged', () => {
    expect(amendNeedsReason(contribution, '40')).toBe(false);
  });

  it('demands one for any quantity that displaces the rule', () => {
    expect(amendNeedsReason(contribution, '10')).toBe(true);
    expect(amendNeedsReason(contribution, '100')).toBe(true);
  });
});

/**
 * Phase 2, deviation 5: the contribution key is the SERVER's, and the counter must use it.
 *
 * The server derives `line_no` (core `sales_order_lines` carries none) and pins the key format
 * `${sales_order_id}|${line_no}|${item_code}|${bucket_key}` with a test of its own. The client
 * used to REBUILD that key from a line plus a re-derived bucket, which means any disagreement
 * about bucketing - a different `as_of`, a granularity the client resolved differently, a
 * timezone - makes every rebuilt key miss. The failure is silent: the draft still records
 * verdicts, and the per-order counter simply never moves off zero.
 *
 * So the counter reads the key the server sent, and these tests exist to stop anyone
 * reintroducing the rebuild.
 */
describe('standingsFor reads the server key (deviation 5)', () => {
  const contributions = [
    {
      key: '41125fbc-4176-4044-b819-c196c9f6467f|1|CSK11A|2026-09-28',
      sales_order_id: '41125fbc-4176-4044-b819-c196c9f6467f',
      so_number: 'SO396488',
      customer_name: 'PP CHIN HIN SDN BHD (PROJECT)',
      fulfilment_location: 'BRW-BB',
    },
    {
      key: '41125fbc-4176-4044-b819-c196c9f6467f|2|CSK11A|2026-10-05',
      sales_order_id: '41125fbc-4176-4044-b819-c196c9f6467f',
      so_number: 'SO396488',
      customer_name: 'PP CHIN HIN SDN BHD (PROJECT)',
      fulfilment_location: 'BRW-BB',
    },
    {
      key: 'aaaaaaaa-0000-0000-0000-000000000001|1|WESERP10B|2022-06-27',
      sales_order_id: 'aaaaaaaa-0000-0000-0000-000000000001',
      so_number: 'SO345418',
      customer_name: 'PEMBINAAN YUEN SENG SDN BHD (PROJECT)',
      fulfilment_location: null,
    },
  ];

  it('counts a verdict against the order whose contribution it was', () => {
    const standings = standingsFor(contributions, {
      '41125fbc-4176-4044-b819-c196c9f6467f|1|CSK11A|2026-09-28': { verdict: 'approved' },
    });
    const chin = standings.find((entry) => entry.so_number === 'SO396488');
    expect(chin?.decided_count).toBe(1);
    expect(chin?.line_count).toBe(2);
  });

  it('counts nothing when the draft key is not one the server sent', () => {
    // This is the exact shape of the rebuild bug: a plausible key that no contribution has.
    const standings = standingsFor(contributions, {
      '41125fbc-4176-4044-b819-c196c9f6467f|1|CSK11A|2026-09-27': { verdict: 'approved' },
    });
    expect(standings.every((entry) => entry.decided_count === 0)).toBe(true);
  });

  it('still counts a line the sales order gave no location as unplannable', () => {
    const standings = standingsFor(contributions, {});
    const yuen = standings.find((entry) => entry.so_number === 'SO345418');
    expect(yuen?.unplannable_count).toBe(1);
  });

  it('ignores the server decided_count, which is always 0 (deviation 4)', () => {
    const standings = standingsFor(contributions, {
      'aaaaaaaa-0000-0000-0000-000000000001|1|WESERP10B|2022-06-27': { verdict: 'rejected' },
    });
    expect(standings.find((entry) => entry.so_number === 'SO345418')?.decided_count).toBe(1);
  });
});
