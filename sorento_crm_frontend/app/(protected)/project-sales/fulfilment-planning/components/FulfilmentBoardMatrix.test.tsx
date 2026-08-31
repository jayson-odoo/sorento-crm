/**
 * The board fills its container (A4, PLAN-demo-followups-19aug-ladder-v2.md).
 *
 * With the table at `w-max` and every date column pinned to `w-[150px]`, a two-week selection
 * occupied a third of the bordered container and left the rest blank. `w-full` on the table plus
 * a `min-w` FLOOR on the date columns (never a fixed width) lets them stretch to fill it; the
 * product column keeps its fixed width because it is not part of what should stretch. With many
 * columns the table still overflows past the floor, and the container's own `overflow-auto`
 * takes it from there - so this pins the class set at both ends: two columns and twenty.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FulfilmentBoardMatrix } from './FulfilmentBoardMatrix';
import { COLOURS } from '../../_shared/lib/supplyVocabulary';
import type {
  BoardAxisRow,
  BoardCell,
  BoardContribution,
  BoardDateBucket,
  BoardDraft,
  BoardLineDecision,
  BoardSource,
} from '../../_shared/types/fulfilmentPlanning.types';

function buckets(count: number): BoardDateBucket[] {
  return Array.from({ length: count }, (_unused, index) => ({
    key: `2026-0${(index % 9) + 1}-01`,
    kind: 'dated' as const,
    label: `Bucket ${index + 1}`,
    start: `2026-0${(index % 9) + 1}-01`,
    is_past: false,
  }));
}

const rows: BoardAxisRow[] = [{ key: 'ZZT-PRODUCT', label: 'ZZT-PRODUCT' }];

describe('FulfilmentBoardMatrix fills its container', () => {
  it('renders a w-full table with a min-w floor on the date columns, not a fixed width', () => {
    render(
      <FulfilmentBoardMatrix
        dateBuckets={buckets(2)}
        rows={rows}
        rowHeader="Product"
        cells={[]}
        draft={{}}
        onOpenCell={() => {}}
      />,
    );

    const table = screen.getByRole('table');
    expect(table.className).toContain('w-full');
    expect(table.className).not.toContain('w-max');

    for (const header of screen.getAllByRole('columnheader')) {
      if (header.textContent === 'Product') continue;
      // A floor, never a fixed or maximum width: those are what stopped the columns from
      // stretching in the first place.
      expect(header.className).toContain('min-w-[150px]');
      expect(header.className).not.toMatch(/(?<!min-)w-\[150px\]/);
      expect(header.className).not.toContain('max-w-[150px]');
    }
  });

  it('keeps the product column at a fixed width so it does not stretch with the rest', () => {
    render(
      <FulfilmentBoardMatrix
        dateBuckets={buckets(2)}
        rows={rows}
        rowHeader="Product"
        cells={[]}
        draft={{}}
        onOpenCell={() => {}}
      />,
    );

    const corner = screen.getByRole('columnheader', { name: 'Product' });
    expect(corner.className).toContain('w-[190px]');
    expect(corner.className).toContain('min-w-[190px]');
    expect(corner.className).toContain('max-w-[190px]');
  });

  it('still overflows into the scrollable container with twenty columns', () => {
    render(
      <FulfilmentBoardMatrix
        dateBuckets={buckets(20)}
        rows={rows}
        rowHeader="Product"
        cells={[]}
        draft={{}}
        onOpenCell={() => {}}
      />,
    );

    expect(screen.getAllByRole('columnheader')).toHaveLength(21); // 20 dates + the corner
    const container = screen.getByTestId('fulfilment-board-matrix');
    expect(container.className).toContain('overflow-auto');
    const table = screen.getByRole('table');
    expect(table.className).toContain('w-full');
    for (const header of screen.getAllByRole('columnheader')) {
      if (header.textContent === 'Product') continue;
      expect(header.className).toContain('min-w-[150px]');
    }
  });
});

/**
 * "Already settled", at a glance.
 *
 * The `n/m decided` badge counts the DRAFT - verdicts the planner has ticked but not
 * confirmed. That is a different statement from "supply for this cell is confirmed in the
 * database", and a cell of eleven confirmed lines showed `0/11 decided` because nothing had
 * been ticked in this session. The marker answers the second question, and only when EVERY
 * contribution in the cell carries an active decision: a partly-decided cell is not decided.
 */
function frozen(revisionNo: number): BoardLineDecision {
  return {
    revision_no: revisionNo,
    timely_spo_qty: '0',
    reserve: [],
    borrow: [],
    buy_qty: '10',
  };
}

function contribution(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: `so-1|1|ZZT-PRODUCT|2026-01-01`,
    sales_order_id: 'so-1',
    so_number: 'SO397450',
    line_no: 1,
    item_code: 'ZZT-PRODUCT',
    qty: '10',
    unplannable: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    contested: false,
    covered: false,
    decision: null,
    ...overrides,
  };
}

function cellWith(contributions: BoardContribution[]): BoardCell {
  return {
    item_code: 'ZZT-PRODUCT',
    row_key: 'ZZT-PRODUCT',
    bucket_key: '2026-01-01',
    total_qty: '10',
    locations: [],
    contributions,
    unplannable_count: 0,
    contested_count: 0,
  };
}

function renderMatrix(cells: BoardCell[], draft: BoardDraft = {}) {
  return render(
    <FulfilmentBoardMatrix
      dateBuckets={buckets(2)}
      rows={rows}
      rowHeader="Product"
      cells={cells}
      draft={draft}
      onOpenCell={() => {}}
    />,
  );
}

function source(over: Partial<BoardSource> = {}): BoardSource {
  return { kind: 'reserve', qty: '10', reason: 'because', ...over };
}

describe('FulfilmentBoardMatrix marks a cell whose supply is already decided', () => {
  it('ticks the cell and names the revision, when every line is covered', () => {
    renderMatrix([
      cellWith([
        contribution({ covered: true, decision: frozen(3) }),
        contribution({ key: 'so-2|1|ZZT-PRODUCT|2026-01-01', covered: true, decision: frozen(3) }),
      ]),
    ]);

    expect(screen.getByTestId('board-decided-marker')).toHaveAttribute(
      'title',
      'Decided rev 3',
    );
  });

  it('names every revision when the cell spans orders decided at different ones', () => {
    // A cell cuts across sales orders and a revision belongs to ONE order, so naming a single
    // number would attribute the decision to the wrong document.
    renderMatrix([
      cellWith([
        contribution({ covered: true, decision: frozen(1) }),
        contribution({ key: 'so-2|1|ZZT-PRODUCT|2026-01-01', covered: true, decision: frozen(4) }),
      ]),
    ]);

    expect(screen.getByTestId('board-decided-marker')).toHaveAttribute(
      'title',
      'Decided rev 1, 4',
    );
  });

  it('does not tick a cell where one line is still open', () => {
    renderMatrix([
      cellWith([
        contribution({ covered: true, decision: frozen(3) }),
        contribution({ key: 'so-2|1|ZZT-PRODUCT|2026-01-01' }),
      ]),
    ]);

    expect(screen.queryByTestId('board-decided-marker')).not.toBeInTheDocument();
  });
});

/**
 * The cell says where its quantity is coming from BEFORE anybody opens it (PLAN section C).
 *
 * The captain, walking the live board: "on the board grid a cell says nothing about the
 * suggestion until it is opened". A bar plus the dominant kind in words is the answer, and the
 * whole point of it is that it changes the moment a decision does.
 */
describe('FulfilmentBoardMatrix colours a cell by its supply', () => {
  it('draws the proposal, faded, and names the dominant kind in words', () => {
    renderMatrix([
      cellWith([
        contribution({
          sources: [source({ kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW' })],
        }),
      ]),
    ]);

    const bar = screen.getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    expect(bar.querySelector('span[data-kind="shared"]')).not.toBeNull();
    expect(screen.getByTestId('cell-supply-lead').textContent).toBe('BRW 71');
  });

  it('flips rose to sky when the draft amends a Buy to the shared pool, and back (AC-C2)', () => {
    const line = contribution({
      sources: [
        source({ kind: 'buy', rung: 'buy', qty: '71', location: null }),
        source({
          kind: 'reserve',
          rung: 'pool',
          qty: '0',
          location: 'BRW',
          warehouse_id: 'wh-brw',
        }),
      ],
    });

    const suggested = renderMatrix([cellWith([line])]);
    expect(
      screen.getByTestId('supply-bar').querySelector('span[data-kind="buy"]'),
    ).not.toBeNull();
    expect(screen.getByTestId('cell-supply-lead').className).toContain(COLOURS.buy.text);
    suggested.unmount();

    renderMatrix([cellWith([line])], {
      [line.key]: {
        verdict: 'amended',
        reserve: [{ warehouse_id: 'wh-brw', location: 'BRW', qty: '71' }],
        borrow: [],
        buy_qty: '0',
        reason: 'The pool can cover it',
      },
    });

    const bar = screen.getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'true');
    expect(bar.querySelector('span[data-kind="shared"]')).not.toBeNull();
    expect(bar.querySelector('span[data-kind="buy"]')).toBeNull();
    expect(screen.getByTestId('cell-supply-lead').className).toContain(COLOURS.shared.text);
  });
});

/**
 * Rose on a cell means Buy and nothing else (AC-C4).
 *
 * The past tint used to be painted on the cell BODY as well as on the header, so a column of
 * late lines read as a column of Buys the moment the supply bar landed beside it. The header
 * already says "Already past", which is where the fact belongs.
 */
describe('FulfilmentBoardMatrix tints the past on the column header only', () => {
  function pastBuckets(): BoardDateBucket[] {
    return [
      {
        key: '2026-01-01',
        kind: 'dated',
        label: 'Bucket 1',
        start: '2026-01-01',
        is_past: true,
      },
    ];
  }

  it('tints the header and leaves the cell bodies of that column untinted', () => {
    render(
      <FulfilmentBoardMatrix
        dateBuckets={pastBuckets()}
        rows={rows}
        rowHeader="Product"
        cells={[cellWith([contribution()])]}
        draft={{}}
        onOpenCell={() => {}}
      />,
    );

    const header = screen
      .getAllByRole('columnheader')
      .find((candidate) => candidate.getAttribute('data-past') === 'true');
    expect(header?.className).toContain('destructive');
    expect(header?.textContent).toContain('Already past');

    const body = document.querySelector('td[data-cell="ZZT-PRODUCT|2026-01-01"]');
    expect(body).not.toBeNull();
    expect(body?.className).not.toContain('destructive');
  });
});

/**
 * AC-L6, the captain 25 August 2026: the donor's cell reads "71 lent to SO415472". A borrow
 * was visible on the taking side and invisible on the giving side, so the agent whose stock
 * moved found out when the delivery did not.
 */
describe('FulfilmentBoardMatrix: what was lent off a line', () => {
  it('says how much was lent, and to which order', () => {
    renderMatrix([
      cellWith([
        contribution({ lent_to: [{ qty: '71', so_number: 'SO415472', line_no: 3 }] }),
      ]),
    ]);

    expect(screen.getByTestId('cell-lent-out')).toHaveTextContent('71 lent to SO415472');
  });

  it('lists every borrow taken off the cell, one order per phrase', () => {
    renderMatrix([
      cellWith([
        contribution({
          lent_to: [
            { qty: '71', so_number: 'SO415472', line_no: 3 },
            { qty: '4', so_number: 'SO394803', line_no: 1 },
          ],
        }),
      ]),
    ]);

    expect(screen.getByTestId('cell-lent-out')).toHaveTextContent(
      '71 lent to SO415472 · 4 lent to SO394803',
    );
  });

  it('says nothing at all when nothing was lent', () => {
    renderMatrix([cellWith([contribution()])]);

    expect(screen.queryByTestId('cell-lent-out')).not.toBeInTheDocument();
  });
});

/**
 * AC-RB1 (`PLAN-scm-oi-handshake.md` section 11): purchasing refused an instruction for a
 * line in this cell, so the cell says so and the hover names who and why.
 *
 * A BADGE, not the sentence: the column is 150px wide and the reason is somebody's own
 * words, so printed in full it was a truncated fragment - "Rejected by Joey: no supp...".
 */
describe('FulfilmentBoardMatrix: a refused line', () => {
  const refused = () =>
    contribution({
      order_inquiry: {
        inquiry_no: 'OI-000101',
        state: 'raised',
        ack_state: 'rejected',
        rejected_by_name: 'Joey',
        rejected_reason: 'No supplier until November',
      },
    });

  it('reads Rejected, and the title names who refused it and why', () => {
    renderMatrix([cellWith([refused()])]);

    const badge = screen.getByTestId('cell-rejected');
    expect(badge).toHaveTextContent('Rejected');
    expect(badge).toHaveAttribute('title', 'Rejected by Joey: No supplier until November');
  });

  it('says nothing on a cell nobody refused', () => {
    renderMatrix([cellWith([contribution()])]);

    expect(screen.queryByTestId('cell-rejected')).toBeNull();
  });

  it('falls back rather than printing an empty sentence when neither is recorded', () => {
    renderMatrix([
      cellWith([
        contribution({
          order_inquiry: {
            inquiry_no: 'OI-000101',
            state: 'raised',
            ack_state: 'rejected',
            rejected_by_name: null,
            rejected_reason: null,
          },
        }),
      ]),
    ]);

    expect(screen.getByTestId('cell-rejected')).toHaveAttribute(
      'title',
      'Rejected by purchasing: no reason given',
    );
  });
});

/**
 * AC-3.1/3.8: the WHOLE cell is the click target, and it says so before the pointer ever
 * reaches the small text inside it (mockup round 2, the captain: "no separate small link").
 */
describe('FulfilmentBoardMatrix: the whole cell is the click target', () => {
  it('carries a pointer cursor and a hover ring across the whole button, not a corner of it', () => {
    renderMatrix([cellWith([contribution()])]);

    const button = screen.getByRole('button');
    expect(button.className).toContain('cursor-pointer');
    expect(button.className).toContain('hover:ring-1');
    // Fills the cell (the `td` gives it no padding of its own to fill).
    expect(button.className).toContain('w-full');
  });

  it('one click anywhere in the cell opens it - no separate small link inside', () => {
    const onOpenCell = vi.fn();
    render(
      <FulfilmentBoardMatrix
        dateBuckets={buckets(2)}
        rows={rows}
        rowHeader="Product"
        cells={[cellWith([contribution()])]}
        draft={{}}
        onOpenCell={onOpenCell}
      />,
    );

    fireEvent.click(screen.getByRole('button'));
    expect(onOpenCell).toHaveBeenCalledTimes(1);
  });
});
