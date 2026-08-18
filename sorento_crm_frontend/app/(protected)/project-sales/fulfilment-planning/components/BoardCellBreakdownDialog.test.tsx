/**
 * The breakdown behind one cell (PLAN section 13, journey step 4).
 *
 * A TABLE, on the shared DataGrid, not a stack of cards. The captain: "this needs to be more
 * table based instead of card based, so it is easier to see, and you need to show me the SO
 * order quantity, owed / outstanding quantity also in the table ... then need to show summary
 * row whenever relevant". So the columns are asserted by name, the quantity columns are
 * asserted to total in the table's own footer row, and the verbs are a row action.
 *
 * The balance for the whole cell is stated ONCE, at the TOP ("7 owed = 7 reserve + 0 incoming
 * + 0 buy" - the captain: "you should show at the top"), rather than repeated under every row.
 *
 * The verbs write into the DRAFT and nothing else. Nothing in this dialog claims a cell
 * committed anything: the commit is the per-order confirmation on the rail behind it (13.4).
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import type {
  BoardCell,
  BoardContribution,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

const TODAY = '2026-08-18';

function demand(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-a',
    so_number: 'SO403340',
    customer_name: 'SETIA-WOOD INDUSTRIES SDN BHD (PROJECT)',
    project_label: 'SETIA-WOOD INDUSTRIES/100U DSTH (DIMINA) @ SETIA',
    line_no: 1,
    item_code: 'WESERP10B',
    qty: '100',
    qty_ordered: '120',
    required_date: '2026-09-04',
    fulfilment_location: 'BRW-BB',
    priority: null,
    ...overrides,
  };
}

function cellOf(lines: BoardDemandLine[], freeStock: Record<string, string> = {}) {
  return buildBoard(lines, { today: TODAY, freeStock }).cells[0];
}

function renderDialog(
  lines: BoardDemandLine[],
  freeStock: Record<string, string> = {},
  draft: BoardDraft = {},
) {
  const onDecide = vi.fn();
  render(
    <BoardCellBreakdownDialog
      cell={cellOf(lines, freeStock)}
      bucketLabel="31 Aug 2026"
      draft={draft}
      onDecide={onDecide}
      onClose={vi.fn()}
    />,
  );
  return { onDecide };
}

/** The totals row the grid renders inside the table, under the columns it sums. */
function footerCells(): string[] {
  const table = screen.getByRole('table');
  const foot = table.querySelector('tfoot');
  return [...(foot?.querySelectorAll('td') ?? [])].map((cell) => cell.textContent ?? '');
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BoardCellBreakdownDialog: the cell summary, at the top', () => {
  it('states the whole cell balance once, above the table', () => {
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    const summary = screen.getByTestId('cell-balance');
    expect(summary.textContent).toBe('100 owed = 40 reserve + 0 incoming + 60 buy');
    // Above the table, which is what the captain asked for: the summary before the detail.
    expect(summary.compareDocumentPosition(screen.getByRole('table'))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it('sums the balance across every contributing line, not just the first', () => {
    renderDialog(
      [
        demand({ line_no: 1, qty: '60' }),
        demand({ line_no: 2, qty: '40', so_number: 'SO398322', sales_order_id: 'so-b' }),
      ],
      { 'WESERP10B|BRW-BB': '70' },
    );

    expect(screen.getByTestId('cell-balance').textContent).toBe(
      '100 owed = 70 reserve + 0 incoming + 30 buy',
    );
  });

  it('names the cell and how much of it is decided', () => {
    renderDialog([demand()]);
    expect(screen.getByText('WESERP10B · 31 Aug 2026')).toBeInTheDocument();
    expect(screen.getByText('100 across 1 line, 0 decided')).toBeInTheDocument();
  });
});

describe('BoardCellBreakdownDialog: the table', () => {
  it('carries the columns the captain named', () => {
    renderDialog([demand()]);

    const table = screen.getByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((node) => node.textContent ?? '');
    for (const title of [
      'Sales order',
      'Customer',
      'Project',
      'Ordered',
      'Owed',
      'Required',
      'Location',
      'Sourced from',
      'Rank',
    ]) {
      expect(headers.some((header) => header.includes(title))).toBe(true);
    }
  });

  it('shows the SO ordered quantity beside the owed quantity, both off the server', () => {
    renderDialog([demand({ qty_ordered: '120', qty: '100' })]);

    const row = screen.getByRole('table').querySelectorAll('tbody tr')[0];
    expect(within(row as HTMLElement).getByText('120')).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText('100')).toBeInTheDocument();
  });

  it('says so rather than guessing when the server has not stated the ordered quantity', () => {
    // Never derived by adding delivered to owed on the client: a number nobody sent is a
    // number nobody can be held to.
    renderDialog([demand({ qty_ordered: null })]);

    // Ordered and Delivered both state their absence rather than printing a 0.
    const row = screen.getByRole('table').querySelectorAll('tbody tr')[0];
    expect(within(row as HTMLElement).getAllByText('Not stated').length).toBeGreaterThan(0);
  });

  it('totals the quantity columns in a summary row inside the table', () => {
    renderDialog([
      demand({ line_no: 1, qty: '60', qty_ordered: '70' }),
      demand({ line_no: 2, qty: '40', qty_ordered: '50', so_number: 'SO398322', sales_order_id: 'so-b' }),
    ]);

    const cells = footerCells();
    expect(cells.some((cell) => cell === 'Total')).toBe(true);
    expect(cells).toContain('120');
    expect(cells).toContain('100');
  });

  it('carries the sales order, customer, project and location per row', () => {
    renderDialog([demand()]);

    expect(screen.getByText(/SO403340/)).toBeInTheDocument();
    expect(screen.getByText('SETIA-WOOD INDUSTRIES SDN BHD (PROJECT)')).toBeInTheDocument();
    expect(
      screen.getByText('SETIA-WOOD INDUSTRIES/100U DSTH (DIMINA) @ SETIA'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('BRW-BB').length).toBeGreaterThan(0);
  });

  it('shows where the quantity is sourced from, with the reason the rule wrote', () => {
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    expect(screen.getByText(/Reserve 40/)).toBeInTheDocument();
    expect(screen.getByText(/Buy 60/)).toBeInTheDocument();
    expect(
      screen.getByTitle(/Free unclaimed stock at BRW-BB covers this much by the required date\./),
    ).toBeInTheDocument();
  });

  it('says when the stock was already committed to earlier demand (13.5)', () => {
    renderDialog(
      [
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, qty: '100', required_date: '2026-09-04' }),
        demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2, qty: '100', required_date: '2026-09-02' }),
      ],
      { 'WESERP10B|BRW-BB': '100' },
    );

    expect(screen.getByText('Contested')).toBeInTheDocument();
  });

  it('lists the rows in the order the allocation rule served them', () => {
    renderDialog([
      demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, required_date: '2026-09-04' }),
      demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2, required_date: '2026-09-02' }),
    ]);

    const rows = screen.getByRole('table').querySelectorAll('tbody tr');
    expect(rows[0].textContent).toContain('SO398322');
    expect(rows[1].textContent).toContain('SO403340');
  });

  it('names a ranking factor in words, never as a database column', () => {
    renderDialog([demand()]);

    // In the tooltip now, not in the cell body - but still words, never a column name.
    const detail =
      screen.getByTestId('rank-factors-so-a|1|WESERP10B|2026-08-31').getAttribute('title') ?? '';
    expect(detail).toContain('Purchase order sequence');
    expect(detail).not.toContain('po_document_sequence');
    expect(detail).not.toContain('need_by_date');
  });
});

/**
 * The real backend fields, which arrived after this table was first built against assumed
 * names. Three of them change what the screen may say rather than merely what it reads.
 */
describe('BoardCellBreakdownDialog: the facts the server sends', () => {
  /** A cell with the location stock facts the server now carries. */
  function stockedCell(location: Partial<BoardCell['locations'][number]>) {
    const cell = cellOf([demand()]);
    return { ...cell, locations: [{ ...cell.locations[0], ...location }] };
  }

  function renderCell(cell: BoardCell, rankingIsFlat = false) {
    render(
      <BoardCellBreakdownDialog
        cell={cell}
        bucketLabel="31 Aug 2026"
        draft={{}}
        rankingIsFlat={rankingIsFlat}
        onDecide={vi.fn()}
        onClose={vi.fn()}
      />,
    );
  }

  it('states what is actually at each location, on hand, free and incoming', () => {
    renderCell(
      stockedCell({
        location: 'BRW-BB',
        qty_on_hand: '500',
        qty_free: '120',
        qty_incoming: '80',
        incoming: [{ spo_number: '202601-S0003', arrival_date: '2026-09-12', qty: '80' }],
      }),
    );

    const strip = screen.getByTestId('cell-location-BRW-BB');
    expect(strip.textContent).toContain('500 on hand');
    expect(strip.textContent).toContain('120 free');
    expect(strip.textContent).toContain('80 incoming');
    // The document behind the incoming stock, because "80 incoming" from nowhere is a rumour.
    expect(strip.getAttribute('title')).toContain('202601-S0003');
  });

  it('says NOT STATED, never 0, when the sales order named no location', () => {
    // The opposite instruction: 0 free means do not look here, nothing is stated means
    // nobody has said where to look.
    renderCell(
      stockedCell({
        location: null,
        qty_on_hand: null,
        qty_free: null,
        qty_incoming: null,
      }),
    );

    const strip = screen.getByTestId('cell-location-none');
    expect(strip.textContent).toContain('Stock not stated');
    expect(strip.textContent).not.toContain('0 on hand');
    expect(strip.textContent).not.toContain('0 free');
  });

  it('carries delivered beside ordered and owed', () => {
    renderDialog([demand({ qty_ordered: '120', qty_delivered: '20', qty: '100' })]);

    const table = screen.getByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((node) => node.textContent ?? '');
    expect(headers.some((header) => header.includes('Delivered'))).toBe(true);
    const row = table.querySelectorAll('tbody tr')[0];
    expect(within(row as HTMLElement).getByText('20')).toBeInTheDocument();
  });

  it('shows the rank and NOTHING else, with the factors reachable as a tooltip', () => {
    const cell = cellOf([demand()]);
    const ranked = {
      ...cell,
      contributions: [
        {
          ...cell.contributions[0],
          rank_score: 0.72,
          rank_factors: [
            { key: 'need_by_date', weight: 3, value: 1, raw: '2026-09-03', present: true },
            { key: 'customer_credit', weight: 1, value: 0.5, raw: '45 days', present: true },
          ],
        },
      ],
    };
    renderCell(ranked);

    const rank = screen.getByTestId(`rank-factors-${cell.contributions[0].key}`);
    // The captain: "the word here is too long already, don't explain too much". The cell is
    // the number; the facts behind it are a tooltip, wanted only when comparing two rows.
    expect(rank.textContent).toBe('0.72');
    expect(rank.getAttribute('title')).toContain('Required date');
    expect(rank.getAttribute('title')).toContain('2026-09-03');
  });

  it('reads the number as a number: right-aligned, tabular figures', () => {
    const cell = cellOf([demand()]);
    renderCell(cell);

    const rank = screen.getByTestId(`rank-factors-${cell.contributions[0].key}`);
    expect(rank.className).toContain('tabular-nums');
    expect(rank.className).toContain('text-end');
  });

  it('sorts by rank, because comparing rows is the whole reason the column exists', () => {
    const cell = cellOf([
      demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a' }),
      demand({ line_no: 2, so_number: 'SO000002', sales_order_id: 'so-b' }),
    ]);
    const ranked = {
      ...cell,
      contributions: cell.contributions.map((entry, index) => ({
        ...entry,
        rank_score: index === 0 ? 0.9 : 0.2,
      })),
    };
    renderCell(ranked);

    // Opens in the order the allocation rule served, which is the order the stock was given
    // out in - never a sort of our own choosing.
    const before = [...screen.getByRole('table').querySelectorAll('tbody tr')].map(
      (row) => row.textContent ?? '',
    );
    expect(before[0]).toContain('0.90');

    fireEvent.click(screen.getByRole('button', { name: 'Rank' }));

    const after = [...screen.getByRole('table').querySelectorAll('tbody tr')].map(
      (row) => row.textContent ?? '',
    );
    expect(after[0]).toContain('0.20');
  });

  it('leads a rank factor with the RAW fact, not the normalised number', () => {
    const cell = cellOf([demand()]);
    const withRaw = {
      ...cell,
      contributions: [
        {
          ...cell.contributions[0],
          rank_score: 0.72,
          rank_factors: [
            { key: 'need_by_date', weight: 3, value: 1, raw: '2026-09-03', present: true },
            { key: 'customer_credit', weight: 1, value: 0.5, raw: '45 days', present: true },
          ],
        },
      ],
    };
    renderCell(withRaw);

    const rank = screen.getByTestId(`rank-factors-${cell.contributions[0].key}`);
    const detail = rank.getAttribute('title') ?? '';
    expect(detail).toContain('2026-09-03');
    expect(detail).toContain('45 days');
    // The weight never sits beside the value as a bare number: "need_by_date 1.00 x3" reads
    // to everybody as a weight of 1.00. It is named in the tooltip instead.
    expect(rank.textContent).not.toContain('x3');
    expect(detail).toContain('weighted 3');
  });

  it('prints no score at all when the server says the policy separates nothing', () => {
    const cell = cellOf([demand()]);
    renderCell(cell, true);

    // The live policy scores every row 0.00, and a column of 0.00 reads as a considered
    // ranking rather than as no ranking.
    const rank = screen.getByTestId(`rank-factors-${cell.contributions[0].key}`);
    expect(rank.textContent).toBe('Not ranked');
  });

  /**
   * The sentence was identical on all eleven rows because the FACTORS are identical there -
   * which is a fact about the POLICY, not about any row. Repeating it per row is eleven copies
   * of one sentence; it belongs once, at the top.
   */
  it('states a flat ranking ONCE at the top, never on every row', () => {
    const cell = cellOf([
      demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a' }),
      demand({ line_no: 2, so_number: 'SO000002', sales_order_id: 'so-b' }),
    ]);
    renderCell(cell, true);

    expect(
      screen.getByText('The active policy separates none of these rows.'),
    ).toBeInTheDocument();
    // Once, not once per row.
    expect(screen.getAllByText('The active policy separates none of these rows.')).toHaveLength(1);
    expect(screen.queryByText(/not recorded/)).not.toBeInTheDocument();
  });

  it('says nothing about the policy when it does rank', () => {
    renderCell(cellOf([demand()]), false);
    expect(
      screen.queryByText('The active policy separates none of these rows.'),
    ).not.toBeInTheDocument();
  });
});

describe('BoardCellBreakdownDialog: approve, amend, reject', () => {
  it('approves a row', () => {
    const { onDecide } = renderDialog([demand()]);
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', {
      verdict: 'approved',
    });
  });

  it('rejects a row, and a rejection carries a reason', () => {
    const { onDecide } = renderDialog([demand()]);
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', {
      verdict: 'rejected',
      reason: 'Rejected on the planning board.',
    });
  });

  it('takes an amendment at the proposed quantity without demanding a reason', () => {
    const { onDecide } = renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save the amendment' }));

    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', {
      verdict: 'amended',
      reserve_qty: '40',
      reason: undefined,
    });
  });

  it('demands a reason the moment the amendment displaces the rule, and blocks Save until it has one', () => {
    const { onDecide } = renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    const input = screen.getByLabelText('Reserve for SO403340 line 1');
    fireEvent.change(input, { target: { value: '10' } });

    const save = screen.getByRole('button', { name: 'Save the amendment' });
    expect(save).toBeDisabled();
    expect(onDecide).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Keeping 30 for the site that is already late.' },
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', {
      verdict: 'amended',
      reserve_qty: '10',
      reason: 'Keeping 30 for the site that is already late.',
    });
  });

  it('shows a decided row as decided, and lets it be undone', () => {
    const { onDecide } = renderDialog([demand()], {}, {
      'so-a|1|WESERP10B|2026-08-31': { verdict: 'approved' },
    });

    expect(screen.getByText('Approved')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', null);
  });

  it('states an amended row at the quantity it was amended to', () => {
    renderDialog([demand()], {}, {
      'so-a|1|WESERP10B|2026-08-31': { verdict: 'amended', reserve_qty: '12' },
    });

    expect(screen.getByText('Amended to reserve 12')).toBeInTheDocument();
  });
});

describe('BoardCellBreakdownDialog: a line with no location (AC-FP16)', () => {
  it('offers no verdict at all, and says why', () => {
    renderDialog([demand({ fulfilment_location: null })]);

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.getByText('Needs a location')).toBeInTheDocument();
  });

  it('still shows its quantity, so the demand is not hidden from the reader', () => {
    renderDialog([
      demand({ line_no: 1, qty: '24', fulfilment_location: null }),
      demand({ line_no: 2, qty: '10' }),
    ]);

    expect(screen.getByText('34 across 2 lines, 0 decided')).toBeInTheDocument();
  });
});

/**
 * The blocker, measured in the browser: at a 560px-tall window the dialog footer painted OVER
 * the row's Approve button, so a planner on a laptop could not decide anything at all. The
 * modal mandate is the fix - the body scrolls in its own region with a max height, and the
 * footer sits OUTSIDE that region so it can never cover a control.
 */
describe('BoardCellBreakdownDialog: the actions can never be covered', () => {
  it('keeps the scrolling region that stops a row action being covered', () => {
    renderDialog([demand()]);

    const body = screen.getByTestId('cell-dialog-body');
    expect(body.className).toContain('overflow-y-auto');
    expect(body.className).toContain('min-h-0');
    expect(body.contains(screen.getByRole('table'))).toBe(true);
    expect(body.contains(screen.getAllByRole('button', { name: 'Approve' })[0])).toBe(true);
  });

  /**
   * The captain: "don't need this close button, the cross button at top right is enough". A
   * footer whose only content duplicated the X was a band of chrome earning nothing - and it
   * was the band that used to paint over the row actions. The scroll layout stays; the footer
   * does not.
   */
  it('has no footer, and the corner X still closes', () => {
    const onClose = vi.fn();
    render(
      <BoardCellBreakdownDialog
        cell={cellOf([demand()])}
        bucketLabel="31 Aug 2026"
        draft={{}}
        onDecide={vi.fn()}
        onClose={onClose}
      />,
    );

    expect(screen.queryByTestId('cell-dialog-footer')).not.toBeInTheDocument();
    const closers = screen.getAllByRole('button', { name: 'Close' });
    expect(closers).toHaveLength(1);
    fireEvent.click(closers[0]);
    expect(onClose).toHaveBeenCalled();
  });

  it('lays the dialog out as a column so the body is what shrinks, not the footer', () => {
    renderDialog([demand()]);

    const content = screen.getByTestId('cell-dialog-content');
    expect(content.className).toContain('flex');
    expect(content.className).toContain('flex-col');
    // A fixed max-height on the BODY was the bug: it let the content run past the footer.
    // The height belongs to the dialog, and the body takes what is left.
    expect(screen.getByTestId('cell-dialog-body').className).toContain('flex-1');
  });
});

describe('BoardCellBreakdownDialog: the real board’s sources', () => {
  /** A contribution built by hand, in exactly the shape seam B returns. */
  function serverCell(sources: BoardContribution['sources']) {
    const cell = cellOf([demand({ qty: '15' })]);
    return {
      ...cell,
      contributions: [{ ...cell.contributions[0], sources }],
    };
  }

  function renderServerCell(sources: BoardContribution['sources']) {
    render(
      <BoardCellBreakdownDialog
        cell={serverCell(sources)}
        bucketLabel="28 Sep 2026"
        draft={{}}
        onDecide={vi.fn()}
        onClose={vi.fn()}
      />,
    );
  }

  /**
   * Deviation 3: the real board emits `timely_spo`, which the Phase 1 fixtures never produced.
   * It has to read as incoming stock rather than falling through to a bare code.
   */
  it('renders a timely SPO source as Incoming', () => {
    renderServerCell([
      {
        kind: 'timely_spo',
        qty: '15',
        location: 'BRW-BB',
        reason: 'SPO 202601-S0003 arrives at BRW-BB on 12 Sep 2026, before the required date.',
        spo_number: null,
        arrival_date: null,
      },
    ]);

    expect(screen.getByText(/Incoming 15/)).toBeInTheDocument();
  });

  /**
   * Deviation 2: `spo_number` and `arrival_date` are always null, because the SPO and its date
   * are inside the engine's own sentence. So the sentence is what must be reachable, and
   * nothing may render a placeholder where the null fields would have gone.
   */
  it('keeps the engine’s sentence reachable, and never renders a blank for the null fields', () => {
    renderServerCell([
      {
        kind: 'timely_spo',
        qty: '15',
        location: 'BRW-BB',
        reason: 'SPO 202601-S0003 arrives at BRW-BB on 12 Sep 2026, before the required date.',
        spo_number: null,
        arrival_date: null,
      },
    ]);

    expect(
      screen.getByTitle(
        /SPO 202601-S0003 arrives at BRW-BB on 12 Sep 2026, before the required date\./,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('null')).not.toBeInTheDocument();
    expect(screen.queryByText('undefined')).not.toBeInTheDocument();
  });

  /** Deviation 8: Pool and Borrow never reach the board; they cross locations. */
  it('counts a timely SPO into the cell balance as incoming, not as reserve', () => {
    renderServerCell([
      { kind: 'timely_spo', qty: '10', location: 'BRW-BB', reason: 'Incoming covers 10.' },
      { kind: 'buy', qty: '5', location: null, reason: 'The residual is bought.' },
    ]);

    expect(screen.getByTestId('cell-balance').textContent).toBe(
      '15 owed = 0 reserve + 10 incoming + 5 buy',
    );
  });
});

/**
 * Bulk decisions (the captain, pointing at the users list: "I should have a bulk decision
 * function ... so I can bulk approve / reject, like I can select all then approve / reject").
 *
 * The screenshot behind it was eleven identical rows: deciding those one at a time is eleven
 * presses to say one thing. Same idiom as `/user-management/users` - `buildSelectColumn` with a
 * header select-all, and the actions appearing in a strip while rows are selected.
 *
 * AMEND stays per row, and I agree with the instruction: an amendment is a quantity and a
 * reason for ONE line, and a single quantity applied to eleven different owed quantities is not
 * a decision anybody meant to make.
 */
describe('BoardCellBreakdownDialog: bulk approve and reject', () => {
  function threeLines() {
    return [
      demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a' }),
      demand({ line_no: 2, so_number: 'SO000002', sales_order_id: 'so-b' }),
      demand({ line_no: 3, so_number: 'SO000003', sales_order_id: 'so-c' }),
    ];
  }

  function selectAll() {
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));
  }

  it('offers no bulk action until something is selected', () => {
    renderDialog(threeLines());
    expect(screen.queryByRole('button', { name: 'Approve selected' })).not.toBeInTheDocument();
  });

  it('approves every selected row in one press, and says how many are selected', () => {
    const { onDecide } = renderDialog(threeLines());

    selectAll();
    expect(screen.getByText('3 selected')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve selected' }));

    expect(onDecide).toHaveBeenCalledTimes(3);
    for (const call of onDecide.mock.calls) {
      expect(call[1]).toEqual({ verdict: 'approved' });
    }
  });

  it('rejects every selected row in one press, with the same reason a single reject carries', () => {
    const { onDecide } = renderDialog(threeLines());

    selectAll();
    fireEvent.click(screen.getByRole('button', { name: 'Reject selected' }));

    expect(onDecide).toHaveBeenCalledTimes(3);
    for (const call of onDecide.mock.calls) {
      expect(call[1]).toEqual({
        verdict: 'rejected',
        reason: 'Rejected on the planning board.',
      });
    }
  });

  it('clears the selection once the bulk decision is made', () => {
    renderDialog(threeLines());

    selectAll();
    fireEvent.click(screen.getByRole('button', { name: 'Approve selected' }));

    expect(screen.queryByText('3 selected')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve selected' })).not.toBeInTheDocument();
  });

  it('select-all covers exactly the rows of this cell', () => {
    const { onDecide } = renderDialog(threeLines());

    selectAll();
    fireEvent.click(screen.getByRole('button', { name: 'Approve selected' }));

    const keys = onDecide.mock.calls.map((call) => call[0]).sort();
    expect(keys).toEqual(
      [
        'so-a|1|WESERP10B|2026-08-31',
        'so-b|2|WESERP10B|2026-08-31',
        'so-c|3|WESERP10B|2026-08-31',
      ].sort(),
    );
  });

  it('will not select a line that cannot be decided, and says why on its own checkbox', () => {
    const { onDecide } = renderDialog([
      demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a' }),
      demand({ line_no: 2, so_number: 'SO000002', sales_order_id: 'so-b', fulfilment_location: null }),
    ]);

    selectAll();
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    // Twice on purpose: on the checkbox that will not tick, and on the Decision cell that
    // offers no verb. buildSelectColumn's own rule - the SAME string, so the two cannot drift
    // into two explanations of one rule.
    expect(
      screen.getAllByTitle(
        'This line cannot be decided here: its sales order states no fulfilment location.',
      ),
    ).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Approve selected' }));
    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(onDecide.mock.calls[0][0]).toBe('so-a|1|WESERP10B|2026-08-31');
  });

  it('leaves the per-row verbs alone: bulk is an addition, not a replacement', () => {
    const { onDecide } = renderDialog(threeLines());

    fireEvent.click(screen.getAllByRole('button', { name: 'Approve' })[0]);
    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole('button', { name: 'Amend' })).toHaveLength(3);
  });
});
