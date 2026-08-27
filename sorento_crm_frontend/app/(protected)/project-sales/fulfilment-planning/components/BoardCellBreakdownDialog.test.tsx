/**
 * The breakdown behind one cell (PLAN section 13, journey step 4).
 *
 * A TABLE, on the shared DataGrid, not a stack of cards. The captain: "this needs to be more
 * table based instead of card based, so it is easier to see, and you need to show me the SO
 * order quantity, outstanding quantity also in the table ... then need to show summary
 * row whenever relevant". So the columns are asserted by name, the quantity columns are
 * asserted to total in the table's own footer row, and the verbs are a row action.
 *
 * ONE VOCABULARY: what is still to go out is **outstanding**, and the summary of it is the
 * table's own footer. The balance equation that used to sit at the top said the same figures
 * again, in the word this screen no longer uses.
 *
 * The verbs write into the DRAFT and nothing else. Nothing in this dialog claims a cell
 * committed anything: the commit is the per-order confirmation on the rail behind it (13.4).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

/** Only reached when a location row is expanded - the stock table's own documents panel. */
const getStockDetail = vi.fn();
/** Only reached when the trail's own "View the queue" is pressed. */
const getPileQueue = vi.fn();
/** Only reached when a chip's Proof button is pressed - nothing in this file does. */
const getClassificationEvidence = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: (...args: unknown[]) => getStockDetail(...args),
  getPileQueue: (...args: unknown[]) => getPileQueue(...args),
  getClassificationEvidence: (...args: unknown[]) => getClassificationEvidence(...args),
}));

import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { boardAxis } from '../../_shared/lib/fulfilmentBoard';
import {
  buildBoard,
  PREVIEW_POLICY,
  type BoardDemandLine,
} from '../../_shared/lib/__testsupport__/boardFixture';
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

/**
 * Opens the info icon beside one row's source strip and reads the sentence(s) behind it (A3,
 * PLAN-demo-followups-19aug-ladder-v2.md): the rung reason and the fair-share note used to be
 * a `title` attribute and a always-visible line under the strip; both now live in one Radix
 * Tooltip, reached the same way a mouse would - `pointerEnter` the trigger, then read the
 * ACCESSIBLE copy of its content (`role="tooltip"`), which Radix mounts as a second,
 * visually-hidden node alongside the visible one so a plain `.textContent` on the visible copy
 * would double the text.
 *
 * Opened via `focus` rather than a pointer event: Radix's trigger only opens on `pointermove`
 * (never `pointerenter`, which jsdom does not synthesize the same way a real mouse does) unless
 * it is delay-gated, while `focus` calls the tooltip's own `onOpen` directly - keyboard users
 * reach the same tooltip this way, so it is also the more honest simulation.
 */
async function sourceNoteOf(key: string): Promise<string> {
  fireEvent.focus(screen.getByTestId(`source-info-${key}`));
  const tooltip = await screen.findByRole('tooltip');
  return tooltip.textContent ?? '';
}

function renderDialog(
  lines: BoardDemandLine[],
  freeStock: Record<string, string> = {},
  draft: BoardDraft = {},
) {
  const onDecide = vi.fn();
  // A client is needed even here (nothing in this describe block opens a query itself): every
  // item-flag chip now carries a Proof button (`ClassificationProofPopover`), and `useQuery`
  // requires a provider in the tree to mount at all, whether or not it is `enabled`.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <BoardCellBreakdownDialog
        cell={cellOf(lines, freeStock)}
        bucketLabel="31 Aug 2026"
        draft={draft}
        onDecide={onDecide}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  );
  return { onDecide };
}

/**
 * The CONTRIBUTING LINES table.
 *
 * The dialog now holds two tables: the stock position per location in the header (its own
 * component, `CellStockTable`), and the lines beneath it. The lines table is always the last
 * one, because the stock table sits above it and its expansions are nested inside it.
 */
function contributionTable(): HTMLElement {
  const tables = screen.getAllByRole('table');
  return tables[tables.length - 1];
}

/** The totals row the grid renders inside the table, under the columns it sums. */
function footerCells(): string[] {
  const table = contributionTable();
  const foot = table.querySelector('tfoot');
  return [...(foot?.querySelectorAll('td') ?? [])].map((cell) => cell.textContent ?? '');
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BoardCellBreakdownDialog: the cell summary, at the top', () => {
  /**
   * The balance equation is GONE. It restated the heading's own figure and then split it into
   * four terms the table below already carries under Outstanding and Sourced from - a second
   * arithmetic of the same facts, in a vocabulary ("owed") this screen no longer uses.
   */
  it('states no balance equation above the table', () => {
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    expect(screen.queryByTestId('cell-balance')).not.toBeInTheDocument();
    expect(screen.queryByText(/owed =/)).not.toBeInTheDocument();
  });

  it('sums the outstanding quantity in the table footer instead', () => {
    renderDialog(
      [
        demand({ line_no: 1, qty: '60' }),
        demand({ line_no: 2, qty: '40', so_number: 'SO398322', sales_order_id: 'so-b' }),
      ],
      { 'WESERP10B|BRW-BB': '70' },
    );

    expect(footerCells()).toContain('100');
  });

  it('names the cell, and leads with what is needed and how much is decided', () => {
    // "across 1 line" is gone: the Contributing lines table below IS the lines, and the
    // quantity is what the planner opened this for.
    renderDialog([demand()]);

    expect(screen.getByText('WESERP10B · 31 Aug 2026')).toBeInTheDocument();
    const needed = screen.getByTestId('cell-quantity-needed');
    expect(needed).toHaveTextContent('Quantity needed');
    expect(needed).toHaveTextContent('100');
    expect(needed).toHaveTextContent('0 decided');
    expect(screen.queryByText('100 across 1 line, 0 decided')).not.toBeInTheDocument();
  });
});

describe('BoardCellBreakdownDialog: the Suggestion card', () => {
  /**
   * The dialog opens on a DECISION, so the decision leads: what is needed, and what the ladder
   * proposes to do about it, broken down by kind of source. It used to open on a sentence and a
   * table of lines, and working out what the whole cell was being asked to do meant reading a
   * source strip per row.
   */
  const row = (key: string) => screen.getByTestId(`suggestion-${key}`);

  it('states only the kinds it proposes something for, in one order', () => {
    // 100 outstanding, 40 free at the line's own location: Buy and Use own location, and
    // nothing else. The card used to list all four always and mute the empty ones, and on a
    // real cell that was three lines of nothing around the line that said what to do.
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    const labels = [...screen.getByTestId('cell-suggestion').querySelectorAll('[data-testid^="suggestion-"]')]
      .map((node) => node.textContent ?? '');
    expect(labels).toHaveLength(2);
    // Ladder v5's own order (AC-V7): the questions first, Buy last.
    expect(labels[0]).toContain('Use own location');
    expect(labels[1]).toContain('Buy');
  });

  it('splits the cell between what is taken and what is bought, and says from where', () => {
    // 100 outstanding, 40 free at the line's own location: the ladder reserves 40 there and
    // buys the rest, and the card says exactly that without anybody opening a row.
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    expect(row('own')).toHaveTextContent('Use own location');
    expect(row('own')).toHaveTextContent('40 from BRW-BB');
    expect(row('buy')).toHaveTextContent('60');
  });

  it('names no location on a Buy, because it is not held anywhere yet', () => {
    renderDialog([demand({ qty: '100' })]);

    expect(row('buy')).toHaveTextContent('100');
    expect(row('buy')).not.toHaveTextContent('from');
  });

  it('sums across every line of the cell', () => {
    renderDialog(
      [
        demand({ line_no: 1, qty: '60' }),
        demand({ line_no: 2, qty: '40', so_number: 'SO398322', sales_order_id: 'so-b' }),
      ],
      { 'WESERP10B|BRW-BB': '70' },
    );

    // 70 free serves the first line whole and 10 of the second; the rest is bought.
    expect(row('own')).toHaveTextContent('70 from BRW-BB');
    expect(row('buy')).toHaveTextContent('30');
  });

  it('leaves out the kinds with no quantity, rather than reading 0 at them', () => {
    renderDialog([demand({ qty: '100' })]);

    expect(screen.queryByTestId('suggestion-shared')).not.toBeInTheDocument();
    expect(screen.queryByTestId('suggestion-borrow_other')).not.toBeInTheDocument();
    expect(row('buy')).toHaveTextContent('100');
  });
});

describe('BoardCellBreakdownDialog: the Product column', () => {
  it('is not shown when the cell holds one product - the title already names it', () => {
    renderDialog([demand({ line_no: 1 }), demand({ line_no: 2 })]);

    const table = contributionTable();
    expect(within(table).queryByRole('columnheader', { name: 'Product' })).not.toBeInTheDocument();
  });
});

describe('BoardCellBreakdownDialog: the table', () => {
  it('carries the columns the captain named', () => {
    renderDialog([demand()]);

    const table = contributionTable();
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((node) => node.textContent ?? '');
    for (const title of [
      'Sales order',
      'Customer',
      'Project',
      'Ordered',
      'Outstanding',
      'Delivery date',
      'Location',
      'Sourced from',
      'Rank',
    ]) {
      expect(headers.some((header) => header.includes(title))).toBe(true);
    }
  });

  it('shows the SO ordered quantity beside the owed quantity, both off the server', () => {
    renderDialog([demand({ qty_ordered: '120', qty: '100' })]);

    const row = contributionTable().querySelectorAll('tbody tr')[0];
    expect(within(row as HTMLElement).getByText('120')).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText('100')).toBeInTheDocument();
  });

  it('says so rather than guessing when the server has not stated the ordered quantity', () => {
    // Never derived by adding delivered to owed on the client: a number nobody sent is a
    // number nobody can be held to.
    renderDialog([demand({ qty_ordered: null })]);

    // Ordered and Delivered both state their absence rather than printing a 0.
    const row = contributionTable().querySelectorAll('tbody tr')[0];
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

  it('shows where the quantity is sourced from, with the reason the rule wrote', async () => {
    const lines = [demand({ qty: '100' })];
    const freeStock = { 'WESERP10B|BRW-BB': '40' };
    const key = cellOf(lines, freeStock).contributions[0].key;
    renderDialog(lines, freeStock);

    // SECTION 2'S word for the rung, off `SHORT_LABELS` - the same word the bar, the
    // legend and the Suggestion card use for this quantity. The strip used to speak
    // ladder v2's own names (Group take) beside a card saying "Own" about the same 40.
    expect(screen.getByText(/Own 40/)).toBeInTheDocument();
    expect(screen.getByText(/Buy 60/)).toBeInTheDocument();
    // The rule's own sentence is behind the info icon now, not a plain `title` - so the
    // numbers above stay directly readable and only the prose needs a hover.
    expect(await sourceNoteOf(key)).toContain(
      'Free unclaimed stock at BRW-BB covers this much by the delivery date.',
    );
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

    const rows = contributionTable().querySelectorAll('tbody tr');
    expect(rows[0].textContent).toContain('SO398322');
    expect(rows[1].textContent).toContain('SO403340');
  });

  it('names a ranking factor in words, never as a database column', () => {
    renderDialog([demand()]);

    // In the calculation popover now, not in the cell body - but still words, never a
    // column name.
    fireEvent.click(screen.getByTestId('rank-info-so-a|1|WESERP10B|2026-08-31'));
    const detail =
      screen.getByTestId('rank-calculation-so-a|1|WESERP10B|2026-08-31').textContent ?? '';
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

  function renderCell(cell: BoardCell) {
    render(
      <BoardCellBreakdownDialog
        cell={cell}
        bucketLabel="31 Aug 2026"
        draft={{}}
        onDecide={vi.fn()}
        onClose={vi.fn()}
      />,
    );
  }

  /** The cells of one location's row in the stock table, in column order. */
  function stockRow(location: string): string[] {
    return [...screen.getByTestId(`cell-location-${location}`).querySelectorAll('td')].map(
      (cell) => cell.textContent ?? '',
    );
  }

  /**
   * AutoCount's own figures, in AutoCount's own words - as a ROW of a table rather than as the
   * run-on sentence a pill had to be (the captain: "can be more tabulated and structured like
   * AutoCount, with expandable details instead of clicking in"). The columns themselves are
   * `CellStockTable`'s tests; what the dialog owes is that the position is on screen at all.
   */
  it('leads with On hand, SO qty, SPO qty and Available', () => {
    renderCell(
      stockedCell({
        location: 'BRW-BB',
        qty_on_hand: '478',
        so_qty: '47009',
        spo_qty: '0',
        available_qty: '-46531',
      }),
    );

    // Location, On hand, SO qty, SPO qty, Available, PO qty, Taken - after the chevron cell,
    // which carries no text. No demand column: the table below says that per line. No
    // Reserved and no Free either: Free was `On hand - Reserved`, and Reserved itself was read
    // by nothing on this screen once `Available` turned out not to use it.
    expect(stockRow('BRW-BB').slice(1)).toEqual([
      'BRW-BB',
      'Own location',
      '478',
      '47009',
      '0',
      // A negative available is the whole point: it is the shortfall, and clamping it to zero
      // would turn the one number that says "this cannot be met" into one that says it can.
      '-46531',
      // PO qty and Taken: the server stated neither, and a row that names a location reads 0.
      '0',
      '0',
    ]);
  });

  /**
   * Measured on the live board: a location can carry `so_qty` while `qty_on_hand` is null.
   * Gating the whole position on on-hand hid the SO figure the planner came for.
   */
  it('shows whichever of the four the server stated, not all-or-nothing', () => {
    renderCell(
      stockedCell({
        location: 'BRW-IB',
        qty_on_hand: null,
        so_qty: '10805',
        spo_qty: '0',
        available_qty: null,
      }),
    );

    const row = stockRow('BRW-IB');
    expect(row[4]).toBe('10805');
    expect(row[5]).toBe('0');
    // A stated location with no figure of its own reads 0 (AC-B2): an absent stock row means
    // the last upload counted none there. Only a line with NO location keeps its blanks.
    expect(row[3]).toBe('0');
    expect(row[6]).toBe('0');
  });

  it('leaves the figures blank when the sales order named no location', () => {
    // The one row AC-B2's zero rule does not reach: 0 at a location means do not look there,
    // and this row has no location to look at.
    renderCell(
      stockedCell({
        location: null,
        qty_on_hand: null,
        so_qty: null,
        spo_qty: null,
        available_qty: null,
        qty_free: null,
        qty_incoming: null,
      }),
    );

    const row = stockRow('none');
    expect(row[1]).toBe('No location');
    expect(row.slice(3)).toEqual(['-', '-', '-', '-', '-', '-']);
    expect(row).not.toContain('0');
  });

  it('carries delivered beside ordered and outstanding', () => {
    renderDialog([demand({ qty_ordered: '120', qty_delivered: '20', qty: '100' })]);

    const table = contributionTable();
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
    renderCell({ ...ranked, rank_separates: true });

    const rank = screen.getByTestId(`rank-factors-${cell.contributions[0].key}`);
    // The captain: "the word here is too long already, don't explain too much". The cell is
    // the number; the facts behind it are behind the icon, wanted only when comparing rows.
    expect(rank.textContent).toBe('0.72');
    fireEvent.click(screen.getByTestId(`rank-info-${cell.contributions[0].key}`));
    const detail =
      screen.getByTestId(`rank-calculation-${cell.contributions[0].key}`).textContent ?? '';
    expect(detail).toContain('Delivery date');
    expect(detail).toContain('2026-09-03');
  });

  it('reads the number as a number: right-aligned, tabular figures', () => {
    const cell = cellOf([demand()]);
    renderCell({ ...cell, rank_separates: true });

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
      rank_separates: true,
      contributions: cell.contributions.map((entry, index) => ({
        ...entry,
        rank_score: index === 0 ? 0.9 : 0.2,
      })),
    };
    renderCell(ranked);

    // Opens in the order the allocation rule served, which is the order the stock was given
    // out in - never a sort of our own choosing.
    const before = [...contributionTable().querySelectorAll('tbody tr')].map(
      (row) => row.textContent ?? '',
    );
    expect(before[0]).toContain('0.90');

    fireEvent.click(screen.getByRole('button', { name: 'Rank' }));

    const after = [...contributionTable().querySelectorAll('tbody tr')].map(
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
    renderCell({ ...withRaw, rank_separates: true });

    const rank = screen.getByTestId(`rank-factors-${cell.contributions[0].key}`);
    fireEvent.click(screen.getByTestId(`rank-info-${cell.contributions[0].key}`));
    const detail =
      screen.getByTestId(`rank-calculation-${cell.contributions[0].key}`).textContent ?? '';
    expect(detail).toContain('2026-09-03');
    expect(detail).toContain('45 days');
    // The weight never sits beside the value as a bare number: "need_by_date 1.00 x3" reads
    // to everybody as a weight of 1.00. It gets its own column in the calculation instead.
    expect(rank.textContent).not.toContain('x3');
    expect(detail).toContain('Weighted');
  });

  it('prints no score at all when the server says the policy separates nothing', () => {
    const cell = cellOf([demand()]);
    renderCell({ ...cell, rank_separates: false, distinct_order_count: 2 });

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
  /**
   * The four cases, from one place. "The active policy separates none of these rows" is true
   * whenever nothing separated them, but under the fair policy the usual cause is that one
   * order's lines in one week share their date, document date and terms - which is not a policy
   * failure, and reading it as one sent people hunting a broken weighting.
   */
  it('says nothing at all about a cell holding one line', () => {
    // "Only line in this cell" restated the single row underneath it. Removed 25 August 2026:
    // the Rank column still reads "Not ranked", because a flat 0.00 there would claim a
    // ranking nobody ran, but no sentence is printed for it.
    const cell = cellOf([demand()]);
    renderCell({ ...cell, rank_separates: false, distinct_order_count: 1 });

    expect(screen.queryByText('Only line in this cell')).not.toBeInTheDocument();
    expect(
      screen.queryByText(/The active policy separates none of these rows/),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId(`rank-factors-${cell.contributions[0].key}`).textContent,
    ).toBe('Not ranked');
  });

  it('says nothing when one sales order is competing with itself (ladder v4)', () => {
    const cell = cellOf([
      demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a' }),
      demand({ line_no: 2, so_number: 'SO000001', sales_order_id: 'so-a' }),
    ]);
    renderCell({ ...cell, rank_separates: false, distinct_order_count: 1 });

    expect(
      screen.queryByText('Same sales order; line order decided which line was served first'),
    ).toBeNull();
  });

  it('keeps the policy sentence for a real tie between different orders', () => {
    const cell = cellOf([
      demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a' }),
      demand({ line_no: 2, so_number: 'SO000002', sales_order_id: 'so-b' }),
    ]);
    renderCell({ ...cell, rank_separates: false, distinct_order_count: 2 });

    expect(
      screen.getByText('The active policy separates none of these rows'),
    ).toBeInTheDocument();
  });

  it('shows each line\'s own score on a pivoted cell, which states no ranking of its own', () => {
    // A sales-order, customer or project cell is built on the client from the server's product
    // cells and spans several piles: it carries neither flag, and used to print "Not ranked" on
    // every row for it. The lines keep the score the server gave them.
    const board = buildBoard(
      [
        demand({ line_no: 1, item_code: 'AAA', sales_order_id: 'so-a', so_number: 'SO000001' }),
        demand({ line_no: 2, item_code: 'BBB', sales_order_id: 'so-a', so_number: 'SO000001' }),
      ],
      { today: TODAY, policy: PREVIEW_POLICY },
    );
    const { cells } = boardAxis(
      'sales_order',
      board.cells.map((cell) => ({ ...cell, rank_separates: false, distinct_order_count: 1 })),
    );
    expect(cells).toHaveLength(1);
    renderCell(cells[0]);

    for (const contribution of cells[0].contributions) {
      expect(screen.getByTestId(`rank-factors-${contribution.key}`).textContent).toBe(
        contribution.rank_score.toFixed(2),
      );
    }
    expect(screen.queryByText(/Not ranked/)).not.toBeInTheDocument();
    expect(screen.queryByText(/line order decided/)).not.toBeInTheDocument();
  });

  it('says nothing about the ranking, and shows it, when the policy does separate the rows', () => {
    const cell = cellOf([demand()]);
    renderCell({ ...cell, rank_separates: true, distinct_order_count: 1 });

    expect(screen.queryByText(/Only line in this cell/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/The active policy separates none of these rows/),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId(`rank-factors-${cell.contributions[0].key}`).textContent).toBe(
      '0.00',
    );
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

  /**
   * The captain, 18 August 2026: "the amend is not working, I should be able to amend the
   * decision and quantity, like I can decide to reserve, or buy, or borrow".
   *
   * Amend now OPENS SOMETHING. It used to reveal a one-input panel under a 25-row table, in
   * the same scroll region, with no focus moved to it: pressing the button moved nothing the
   * planner could see, so the form was never found and the verb read as broken.
   */
  it('opens the amendment as a dialog of its own', () => {
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));

    expect(screen.getByText('Amend SO403340 · line 1 · WESERP10B')).toBeInTheDocument();
    // Its own dialog, over the breakdown, rather than a panel inside it.
    expect(screen.getAllByRole('dialog').length).toBeGreaterThan(1);
  });

  it('takes the proposal as it stands, and carries the whole composition into the draft', () => {
    // Wholly from stock (AC-L5), which is what the engine can propose: a mix of stock and a
    // Buy on one line is refused by `lineBlockers` and by the confirmation alike.
    const { onDecide } = renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '100' });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save the amendment' }));

    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', {
      verdict: 'amended',
      reserve_qty: '100',
      timely_spo_qty: '0',
      reserve: [{ warehouse_id: 'wh-BRW-BB', location: 'BRW-BB', qty: '100' }],
      borrow: [],
      buy_qty: '0',
      reason: undefined,
    });
  });

  it('demands a reason the moment the amendment displaces the rule, and blocks Save until it has one', () => {
    const { onDecide } = renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '100' });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    // Buy is a whole-line switch (AC-L5): on, the stock rows clear and the whole 100 is
    // bought, which is exactly the amendment that displaces the proposal.
    fireEvent.click(screen.getByLabelText('Buy the whole line'));

    const save = screen.getByRole('button', { name: 'Save the amendment' });
    expect(save).toBeDisabled();
    expect(onDecide).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The site wants new stock, not what is standing there.' },
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', {
      verdict: 'amended',
      reserve_qty: '0',
      timely_spo_qty: '0',
      reserve: [],
      borrow: [],
      buy_qty: '100',
      reason: 'The site wants new stock, not what is standing there.',
    });
  });

  it('shuts the editor again when the amendment is cancelled', () => {
    const { onDecide } = renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText('Amend SO403340 · line 1 · WESERP10B')).not.toBeInTheDocument();
    expect(onDecide).not.toHaveBeenCalled();
  });

  it('shows a decided row as decided, and lets it be undone', () => {
    const { onDecide } = renderDialog([demand()], {}, {
      'so-a|1|WESERP10B|2026-08-31': { verdict: 'approved' },
    });

    expect(screen.getByText('Approved')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(onDecide).toHaveBeenCalledWith('so-a|1|WESERP10B|2026-08-31', null);
  });

  /**
   * A decision is not a dead end. Undo-then-Amend is two presses and loses the composition
   * the planner had already made; the verb they want is on the row.
   */
  it('lets a decided row be amended again, without undoing it first', () => {
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' }, {
      'so-a|1|WESERP10B|2026-08-31': { verdict: 'approved' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    expect(screen.getByText('Amend SO403340 · line 1 · WESERP10B')).toBeInTheDocument();
  });

  it('states an amended row as the composition it was amended to', () => {
    renderDialog([demand()], {}, {
      'so-a|1|WESERP10B|2026-08-31': {
        verdict: 'amended',
        reserve_qty: '20',
        timely_spo_qty: '0',
        reserve: [{ warehouse_id: 'wh-BRW-BB', location: 'BRW-BB', qty: '20' }],
        borrow: [
          {
            source: 'other_location',
            warehouse_id: 'wh-ib',
            warehouse_code: 'BRW-IB',
            qty: '10',
            reason: 'Agreed with the other site.',
          },
        ],
        buy_qty: '13',
      },
    });

    expect(
      screen.getByText('Own 20 BRW-BB · Borrow (other) 10 BRW-IB · Buy 13'),
    ).toBeInTheDocument();
  });

  it('still states a decision taken before the editor existed', () => {
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

    expect(screen.getByTestId('cell-quantity-needed')).toHaveTextContent('34');
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
    expect(body.contains(contributionTable())).toBe(true);
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
    const cell = serverCell(sources);
    render(
      <BoardCellBreakdownDialog
        cell={cell}
        bucketLabel="28 Sep 2026"
        draft={{}}
        onDecide={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    return cell;
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
        reason: 'SPO 202601-S0003 arrives at BRW-BB on 12 Sep 2026, before the delivery date.',
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
  it('keeps the engine’s sentence reachable, and never renders a blank for the null fields', async () => {
    const cell = renderServerCell([
      {
        kind: 'timely_spo',
        qty: '15',
        location: 'BRW-BB',
        reason: 'SPO 202601-S0003 arrives at BRW-BB on 12 Sep 2026, before the delivery date.',
        spo_number: null,
        arrival_date: null,
      },
    ]);

    expect(await sourceNoteOf(cell.contributions[0].key)).toContain(
      'SPO 202601-S0003 arrives at BRW-BB on 12 Sep 2026, before the delivery date.',
    );
    expect(screen.queryByText('null')).not.toBeInTheDocument();
    expect(screen.queryByText('undefined')).not.toBeInTheDocument();
  });

  /** Deviation 8: Pool and Borrow never reach the board; they cross locations. */
  it('reads a timely SPO as Incoming in the row strip, not as a Reserve', () => {
    renderServerCell([
      { kind: 'timely_spo', qty: '10', location: 'BRW-BB', reason: 'Incoming covers 10.' },
      { kind: 'buy', qty: '5', location: null, reason: 'The residual is bought.' },
    ]);

    expect(screen.getByText('Incoming 10 at BRW-BB · Buy 5')).toBeInTheDocument();
    expect(screen.queryByText(/Reserve 10/)).not.toBeInTheDocument();
  });
});

/**
 * WHY the Reserve is the size it is (PLAN 13.7, the fair-share amendment).
 *
 * A line may reserve from its own location only what is left after the demand the active policy
 * ranks ahead of it there, so the row has to say who was ahead and what remained. Three numbers
 * live near each other and NONE may be printed as another: the strip's `available_qty` is the
 * whole pile's position, `available_to_this_line` is what was left for THIS line at its own
 * location, and `qty_proposed_reserve` is what it actually took - which can exceed the second,
 * because the shared pool is a second source with a queue of its own.
 */
describe('BoardCellBreakdownDialog: what was left for this line', () => {
  /** The captain's own card, live: B2154-NL at BRW-BB on SO369758. */
  function captainsCell(overrides: Partial<BoardContribution> = {}) {
    const cell = cellOf([demand()]);
    return {
      ...cell,
      contributions: [
        {
          ...cell.contributions[0],
          fulfilment_location: 'BRW-BB',
          so_qty_ahead: '388',
          lines_ahead: 6,
          available_to_this_line: '627',
          sources: [
            {
              kind: 'reserve' as const,
              qty: '80',
              location: 'BRW-BB',
              warehouse_id: 'wh-BRW-BB',
              reason: 'Free unclaimed stock at BRW-BB covers this much by the delivery date.',
            },
          ],
          ...overrides,
        },
      ],
    };
  }

  function renderCell(cell: BoardCell) {
    render(
      <BoardCellBreakdownDialog
        cell={cell}
        bucketLabel="31 Aug 2026"
        draft={{}}
        onDecide={vi.fn()}
        onClose={vi.fn()}
      />,
    );
  }

  /**
   * The share note now lives inside the same tooltip the rung reason does (A3), reached by the
   * shared `sourceNoteOf` helper - so a `.toContain` rather than `.toBe` where the reason is
   * also present, and both sentences may show up in the one tooltip.
   */
  function shareNoteOf(cell: BoardCell): Promise<string> {
    return sourceNoteOf(cell.contributions[0].key);
  }

  it('says how many lines were ahead, what they wanted, and what was left here', async () => {
    const cell = captainsCell();
    renderCell(cell);

    expect(await shareNoteOf(cell)).toContain(
      '6 lines ahead wanting 388 · 627 left for this line at BRW-BB',
    );
  });

  it('says the line was first in the queue when nothing was ahead of it', async () => {
    const cell = captainsCell({
      so_qty_ahead: '0',
      lines_ahead: 0,
      available_to_this_line: '1015',
    });
    renderCell(cell);

    expect(await shareNoteOf(cell)).toContain('First in the queue at BRW-BB · 1015 left for this line');
  });

  it('counts a single line ahead in the singular', async () => {
    const cell = captainsCell({ so_qty_ahead: '60', lines_ahead: 1, available_to_this_line: '40' });
    renderCell(cell);

    expect(await shareNoteOf(cell)).toContain('1 line ahead wanting 60 · 40 left for this line at BRW-BB');
  });

  /**
   * The reserve MAY exceed what was left at the line's own location, because the shared pool is a
   * second source with its own queue. Live: a line reading "0 left for it" still reserved 9 from
   * the pool. So the sentence states what remained and claims nothing about what may be taken.
   */
  it('states both when the reserve exceeds what was left at this line’s own location', async () => {
    const cell = captainsCell({
      so_qty_ahead: '1015',
      lines_ahead: 12,
      available_to_this_line: '0',
      sources: [
        {
          kind: 'reserve',
          qty: '9',
          location: 'BRW',
          warehouse_id: 'wh-BRW',
          reason: 'The shared pool at BRW covers this much within its cap.',
        },
      ],
    });
    renderCell(cell);

    // A bare site code is the shared pool, whatever the line's own location is.
    expect(screen.getByText(/Shared 9 at BRW/)).toBeInTheDocument();
    const note = await shareNoteOf(cell);
    expect(note).toContain('12 lines ahead wanting 1015 · 0 left for this line at BRW-BB');
    // Never a verdict on the reserve: the pool is a second source, so "0 left" does not mean
    // nothing may be reserved.
    expect(note).not.toContain('cannot');
  });

  /**
   * The whole pile and this line's share are different numbers and are never shown under one
   * label - the captain's card reads Available -8013 at BRW-BB and 627 left for this line.
   */
  it('never prints the pile’s Available as the line’s share, or the other way round', async () => {
    const cell = {
      ...captainsCell(),
      locations: [
        {
          location: 'BRW-BB',
          qty: '100',
          qty_on_hand: '1015',
          so_qty: '9028',
          spo_qty: '0',
          available_qty: '-8013',
        },
      ],
    };
    renderCell(cell);

    const position = screen.getByTestId('cell-location-BRW-BB').textContent ?? '';
    expect(position).toContain('-8013');
    expect(position).not.toContain('627');
    expect(position).not.toContain('left for this line');

    const note = await shareNoteOf(cell);
    expect(note).toContain('627 left for this line');
    expect(note).not.toContain('Available');
    expect(note).not.toContain('-8013');
  });

  /**
   * Absent is absent: a line the server sent no SHARE for gets no share sentence, never a 0 -
   * even though the row still carries the rule's own reason and so still shows the icon.
   */
  it('says nothing at all when the server sent no share for the line', async () => {
    const cell = captainsCell({
      so_qty_ahead: undefined,
      lines_ahead: undefined,
      available_to_this_line: undefined,
    });
    renderCell(cell);

    expect(await shareNoteOf(cell)).not.toContain('left for this line');
  });

  /** A line with no location has no own pile to be queued at, so it has nothing to say here. */
  it('says nothing for a line whose sales order states no location', async () => {
    const cell = cellOf([demand({ fulfilment_location: null })]);
    const unplannable = {
      ...cell,
      contributions: [
        {
          ...cell.contributions[0],
          so_qty_ahead: '0',
          lines_ahead: 0,
          available_to_this_line: '0',
        },
      ],
    };
    renderCell(unplannable);

    expect(await shareNoteOf(unplannable)).not.toContain('left for this line');
  });

  /** The fixture emits the same three fields, queued the way the server queues them. */
  it('reads the queue the board fixture built, line by line', async () => {
    const cell = cellOf(
      [
        demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a', qty: '60' }),
        demand({ line_no: 2, so_number: 'SO000002', sales_order_id: 'so-b', qty: '40' }),
      ],
      { 'WESERP10B|BRW-BB': '100' },
    );
    renderCell(cell);

    expect(await sourceNoteOf(cell.contributions[0].key)).toContain(
      'First in the queue at BRW-BB · 100 left for this line',
    );
    expect(await sourceNoteOf(cell.contributions[1].key)).toContain(
      '1 line ahead wanting 60 · 40 left for this line at BRW-BB',
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

/**
 * HOW the rank was calculated (the captain: "how is the rank calculated? can have an
 * information tooltip to show the calculation").
 *
 * A TABLE behind an icon, not hover text: the same instruction that turned this dialog from
 * cards into rows applies to the explanation of a number nobody can otherwise check. Every row
 * is one factor with the fact behind it, its normalised score, the policy's weight and the
 * product of the two; the footer is the division that produces the number in the cell.
 */
describe('BoardCellBreakdownDialog: how the rank was calculated', () => {
  function rankedCell(factors: BoardContribution['rank_factors'], score: number): BoardCell {
    const cell = cellOf([demand()]);
    return {
      ...cell,
      rank_separates: true,
      contributions: [{ ...cell.contributions[0], rank_score: score, rank_factors: factors }],
    };
  }

  function renderCell(cell: BoardCell) {
    render(
      <BoardCellBreakdownDialog
        cell={cell}
        bucketLabel="31 Aug 2026"
        draft={{}}
        onDecide={vi.fn()}
        onClose={vi.fn()}
      />,
    );
  }

  const FACTORS = [
    { key: 'need_by_date', weight: 3, value: 1, raw: '2026-09-03', present: true },
    { key: 'customer_credit', weight: 1, value: 0.5, raw: '45 days', present: true },
    { key: 'po_document_sequence', weight: 1, value: null, raw: null, present: false },
  ];

  function openRank(cell: BoardCell) {
    fireEvent.click(
      screen.getByTestId(`rank-info-${cell.contributions[0].key}`),
    );
  }

  it('opens the calculation from an icon on the Rank cell, not from hover text', () => {
    const cell = rankedCell(FACTORS, 0.875);
    renderCell(cell);

    const button = screen.getByTestId(`rank-info-${cell.contributions[0].key}`);
    expect(button).toHaveAttribute('aria-label', 'How this rank was calculated');
    // The prose title the captain rejected is gone; the structure replaces it.
    expect(
      screen.getByTestId(`rank-factors-${cell.contributions[0].key}`).getAttribute('title'),
    ).toBeNull();

    fireEvent.click(button);
    for (const heading of ['Factor', 'Fact', 'Score', 'Weight', 'Weighted']) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
  });

  it('gives every factor a row: the fact, its score, its weight and the product', () => {
    const cell = rankedCell(FACTORS, 0.875);
    renderCell(cell);
    openRank(cell);

    const row = screen.getByTestId('rank-factor-need_by_date');
    expect([...row.querySelectorAll('td')].map((node) => node.textContent)).toEqual([
      'Delivery date',
      '2026-09-03',
      '1.00',
      '3',
      '3.00',
    ]);
    // Named in words, never as the database column it comes from.
    expect(screen.queryByText('need_by_date')).not.toBeInTheDocument();
  });

  it('adds up to the number in the cell, and shows the division that got there', () => {
    // (3 x 1.00 + 1 x 0.50) / (3 + 1) = 0.875, which the cell prints as 0.88.
    const cell = rankedCell(FACTORS, 0.875);
    renderCell(cell);
    openRank(cell);

    expect(screen.getByTestId(`rank-total-${cell.contributions[0].key}`).textContent).toBe(
      '3.50 / 4 = 0.88',
    );
    expect(screen.getByTestId(`rank-factors-${cell.contributions[0].key}`).textContent).toBe(
      '0.88',
    );
  });

  it('leaves an absent fact out of the sums rather than scoring it zero', () => {
    const cell = rankedCell(FACTORS, 0.875);
    renderCell(cell);
    openRank(cell);

    const row = screen.getByTestId('rank-factor-po_document_sequence');
    expect([...row.querySelectorAll('td')].map((node) => node.textContent)).toEqual([
      'Purchase order sequence',
      '-',
      'not recorded',
      '1',
      '-',
    ]);
    // Its weight of 1 is in neither sum: the divisor is 4, the three weighted factors' 3 + 1.
    expect(screen.getByTestId(`rank-total-${cell.contributions[0].key}`).textContent).toContain(
      '/ 4 =',
    );
    expect(
      screen.getByText(
        'Score 1.00 = best in this cell; absent facts are left out, not counted as zero',
      ),
    ).toBeInTheDocument();
  });

  it('still shows the calculation on a cell the policy could not rank', () => {
    const base = rankedCell(FACTORS, 0);
    const cell = {
      ...base,
      rank_separates: false,
      distinct_order_count: 2,
      // TWO lines, because that is the case the sentence is about: a cell holding one line
      // says nothing at all about its ranking any more, and this test is about the sentence.
      contributions: [
        base.contributions[0],
        { ...base.contributions[0], key: 'so-b|1|WESERP10B|2026-08-31', sales_order_id: 'so-b' },
      ],
    };
    renderCell(cell);
    openRank(cell);

    // The cell says Not ranked; the popover says WHY - the cell's own sentence, from
    // `rankingNote`, so the two can never drift - and still shows the arithmetic.
    expect(screen.getByTestId(`rank-factors-${cell.contributions[0].key}`).textContent).toBe(
      'Not ranked',
    );
    expect(
      within(screen.getByTestId(`rank-calculation-${cell.contributions[0].key}`)).getByText(
        'The active policy separates none of these rows',
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('rank-factor-need_by_date')).toBeInTheDocument();
  });
});

/**
 * HOW the decision was reached (the captain: "can you justify how you arrive at the buy, like
 * what's the process you have gone through: checking the available quantity first, deciding
 * whether to reserve it or not, then checking the SPO quantity, then checking whether can
 * borrow ... need more justification", then "the justification needs to be STRUCTURED instead
 * of plain text explaining, you can put it under the tooltip").
 *
 * So the ladder is a table of STEPS, every rung of it, including the rungs that gave nothing.
 */
describe('BoardCellBreakdownDialog: how the decision was reached', () => {
  function openTrail(key: string) {
    fireEvent.click(screen.getByTestId(`trail-info-${key}`));
  }

  function stepCells(key: string, kind: string): (string | null)[] {
    return [
      ...screen.getByTestId(`trail-step-${key}-${kind}`).querySelectorAll('td'),
    ].map((node) => node.textContent);
  }

  it('asks the four questions in order, and then Buy (AC-V1)', () => {
    const cell = cellOf([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '100' });
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '100' });
    const key = cell.contributions[0].key;

    const button = screen.getByTestId(`trail-info-${key}`);
    expect(button).toHaveAttribute('aria-label', 'How this decision was reached');
    openTrail(key);

    const questions = [
      ...screen.getByTestId(`trail-${key}`).querySelectorAll('tbody tr[data-step]'),
    ].map((row) => row.querySelectorAll('td')[1]?.textContent);
    expect(questions).toEqual([
      'Can we use our location?',
      'Can we take from the pool?',
      'Can we borrow from another location?',
      "Can we borrow from the same agent's other order in this group?",
      'Buy the rest?',
    ]);
  });

  it('answers each question with a word, a quantity and a place', () => {
    // The whole-line rule: the pool holds exactly what is owed, so it is proposed in full
    // and Buy answers No rather than showing a partial mix.
    const cell = cellOf([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '100' });
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '100' });
    const key = cell.contributions[0].key;
    openTrail(key);

    // # | Question | Answer | Took | From
    expect(stepCells(key, 'pool')).toEqual([
      '2',
      'Can we take from the pool?',
      'Yes',
      '100',
      'BRW-BB',
    ]);
    expect(stepCells(key, 'buy')).toEqual(['5', 'Buy the rest?', 'No', '0', '-']);
  });

  it('carries the queue on question 1, and on no other question', () => {
    // The read-only own-location strip is folded into question 1 under ladder v5: it is the
    // one question with a queue, and the one `QueueLink`'s dialog can open.
    const lines = [
      demand({ line_no: 1, so_number: 'SO000001', sales_order_id: 'so-a', qty: '60' }),
      demand({ line_no: 2, so_number: 'SO000002', sales_order_id: 'so-b', qty: '40' }),
    ];
    const cell = cellOf(lines, { 'WESERP10B|BRW-BB': '70' });
    renderDialog(lines, { 'WESERP10B|BRW-BB': '70' });
    const second = cell.contributions[1].key;
    openTrail(second);

    expect(stepCells(second, 'own').slice(1, 3)).toEqual([
      'Can we use our location?',
      'No',
    ]);
    expect(screen.getByTestId(`trail-queue-${second}`).textContent).toBe(
      'View the queue (1 ahead)',
    );
    expect(screen.getAllByTestId(`trail-queue-${second}`)).toHaveLength(1);
  });

  it('answers a question a rule skipped rather than leaving it out', () => {
    const cell = cellOf([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    const key = cell.contributions[0].key;
    openTrail(key);

    expect(stepCells(key, 'own')).toContain('No');
    expect(
      screen.getByTestId(`trail-why-${key}-own`).textContent,
    ).toContain('no ownership group');
  });

  it('says there is no plan at all for a line whose order states no location', () => {
    const cell = cellOf([demand({ fulfilment_location: null })]);
    renderDialog([demand({ fulfilment_location: null })]);
    const key = cell.contributions[0].key;
    openTrail(key);

    expect(screen.getByTestId(`trail-${key}`).textContent).toContain(
      'No plan: No fulfilment location on the sales order line, so nothing can be sourced for it.',
    );
  });

  /**
   * WHY each rung ended that way, and a press away to WHO is in the queue.
   *
   * The captain, reading the numbers: "what does this mean? why do the orders stand ahead of me?
   * why? and why is the donor offered but I did not take, why?" So every rung carries one plain
   * sentence naming the count and the reason; the rung with a queue also opens the whole thing,
   * because a plain sentence cannot show rank ("why do the orders stand ahead of me?").
   */
  function rankedCell(lines: BoardDemandLine[], freeStock: Record<string, string> = {}) {
    return buildBoard(lines, { today: TODAY, freeStock, policy: PREVIEW_POLICY }).cells[0];
  }

  function renderCell(cell: BoardCell) {
    // The queue the trail offers is a READ, so this branch needs a client. The rest of the
    // suite deliberately renders without one: nothing else here fetches.
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <BoardCellBreakdownDialog
          cell={cell}
          bucketLabel="31 Aug 2026"
          draft={{}}
          onDecide={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
  }

  function queueOfFive() {
    return [1, 2, 3, 4, 5].map((index) =>
      demand({
        sales_order_id: `so-${index}`,
        so_number: `SO40000${index}`,
        line_no: index,
        qty: '100',
        required_date: `2026-09-0${index}`,
      }),
    );
  }

  it('says in words why each question ended the way it did', () => {
    const cell = rankedCell(queueOfFive(), { 'WESERP10B|BRW-BB': '40' });
    renderCell(cell);
    const last = cell.contributions[cell.contributions.length - 1].key;
    openTrail(last);

    expect(screen.getByTestId(`trail-why-${last}-own`).textContent).toContain(
      'no ownership group',
    );
    expect(screen.getByTestId(`trail-why-${last}-buy`).textContent).toBe(
      'Nothing left to take, so the remainder is bought.',
    );
  });

  it('does not repeat the queue as a list - the link already gives the count', () => {
    // The captain: "the explanation ... Ahead of this line ... is not needed, cause you already
    // told me how many lines ahead, that's fine" - the count stays, the repeated list goes.
    const cell = rankedCell(queueOfFive(), { 'WESERP10B|BRW-BB': '40' });
    renderCell(cell);
    const last = cell.contributions[cell.contributions.length - 1].key;
    openTrail(last);

    const trail = screen.getByTestId(`trail-${last}`);
    expect(trail.textContent).not.toContain('Ahead of this line');
    expect(trail.querySelectorAll('[data-testid^="trail-ahead-line-"]')).toHaveLength(0);
    expect(screen.queryByTestId(`trail-ahead-${last}`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`trail-queue-${last}`)).toBeInTheDocument();
  });

  it('offers the whole queue rather than only the three it names', async () => {
    getPileQueue.mockReturnValue(new Promise(() => {}));
    const cell = rankedCell(queueOfFive(), { 'WESERP10B|BRW-BB': '40' });
    const asking = cell.contributions[cell.contributions.length - 1];
    renderCell(cell);
    openTrail(asking.key);

    const button = screen.getByTestId(`trail-queue-${asking.key}`);
    expect(button.textContent).toBe('View the queue (4 ahead)');

    fireEvent.click(button);

    // Asked by IDS and on BEHALF of this line: both change what comes back.
    await waitFor(() =>
      expect(getPileQueue).toHaveBeenCalledWith(
        asking.product_id,
        asking.fulfilment_warehouse_id,
        asking.line_id,
      ),
    );
  });

  it('says a Borrow was found and left alone, and names the donors', () => {
    const cell = cellOf([demand({ qty: '100' })]);
    const contribution = cell.contributions[0];
    const borrow = contribution.trail?.find((step) => step.kind === 'cross_group_borrow');
    Object.assign(borrow ?? {}, {
      note: 'MWH-IB 20 · BRW 5',
      why: 'Borrowing is never automatic: a person names the donor and the reason. Use Amend to borrow.',
    });
    renderCell(cell);
    openTrail(contribution.key);

    const why = screen.getByTestId(`trail-why-${contribution.key}-cross_group_borrow`);
    expect(why.textContent).toContain('Use Amend to borrow');
    expect(screen.getByText('MWH-IB 20 · BRW 5')).toBeInTheDocument();
  });

  it('leaves the source strip, the share note and the Contested chip exactly as they were', async () => {
    const lines = [
      demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, qty: '100', required_date: '2026-09-04' }),
      demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2, qty: '100', required_date: '2026-09-02' }),
    ];
    const freeStock = { 'WESERP10B|BRW-BB': '100' };
    const cell = cellOf(lines, freeStock);
    renderDialog(lines, freeStock);

    expect(screen.getByText(/Own 100/)).toBeInTheDocument();
    expect(screen.getByText('Contested')).toBeInTheDocument();
    // Both rows still carry a share sentence, now behind the icon rather than always visible.
    expect(await sourceNoteOf(cell.contributions[0].key)).toContain('left for this line');
    expect(await sourceNoteOf(cell.contributions[1].key)).toContain('left for this line');
  });

  /**
   * The flags the ladder judged the item on, and the pool pile behind rung 2.
   *
   * The captain, 19 August 2026: "where is the consideration of dealer hot selling / project hot
   * selling / discontinued, to see if we can take from BRW?" - and, on `Pool BRW | Had 0` beside
   * an Inventory screen showing `Available 1`: "why it shows 0?"
   */
  it('opens the pool rung with no hot-selling verdict in words, and shows no chip for an ordinary item', () => {
    const cell = cellOf([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    const key = cell.contributions[0].key;
    openTrail(key);

    expect(screen.getByTestId(`trail-why-${key}-pool`).textContent).toBe(
      'BRW-BB offers 40; this line takes 40.',
    );
    // An unflagged item is the ordinary case: no badge saying so.
    expect(screen.queryByTestId(`trail-flags-${key}`)).not.toBeInTheDocument();
  });

  it('shows the item flags as chips beside the title, each naming its evidence', () => {
    const cell = cellOf([demand({ qty: '100' })]);
    const contribution = cell.contributions[0];
    contribution.item_flags = {
      dealer_hot_selling: true,
      dealer_hot_selling_where: ['BRW', 'BRW-IB'],
      project_hot_selling: false,
      project_hot_selling_where: [],
      dealer_classified: true,
      project_classified: false,
      discontinued: true,
      retail_classification_available: true,
    };
    renderCell(cell);
    openTrail(contribution.key);

    const chips = screen.getByTestId(`trail-flags-${contribution.key}`);
    expect(chips.textContent).toBe('Dealer hot-sellingDiscontinued');
    expect(
      screen.getByTestId(`trail-flag-${contribution.key}-dealer-hot-selling`),
    ).toHaveAttribute(
      'title',
      'Dealer hot-selling at BRW, BRW-IB. The shared pool is kept for retail, not offered.',
    );
    expect(
      screen.queryByTestId(`trail-flag-${contribution.key}-not-classified`),
    ).not.toBeInTheDocument();
    expect(chips.textContent).not.toMatch(/ABC/);
  });

  it('shows a project hot-selling chip alongside the dealer one when both flags are set', () => {
    const cell = cellOf([demand({ qty: '100' })]);
    const contribution = cell.contributions[0];
    contribution.item_flags = {
      dealer_hot_selling: true,
      dealer_hot_selling_where: ['BRW'],
      project_hot_selling: true,
      project_hot_selling_where: ['BRW-BB'],
      dealer_classified: true,
      project_classified: true,
      discontinued: false,
      retail_classification_available: true,
    };
    renderCell(cell);
    openTrail(contribution.key);

    const chips = screen.getByTestId(`trail-flags-${contribution.key}`);
    expect(chips.textContent).toBe('Dealer hot-sellingProject hot-selling');
  });

  it('shows a "Cold at" chip for a class that is classified but never ranked A', () => {
    const cell = cellOf([demand({ qty: '100' })]);
    const contribution = cell.contributions[0];
    contribution.item_flags = {
      dealer_hot_selling: false,
      dealer_hot_selling_where: [],
      project_hot_selling: false,
      project_hot_selling_where: [],
      dealer_classified: true,
      project_classified: true,
      discontinued: false,
      retail_classification_available: true,
    };
    renderCell(cell);
    openTrail(contribution.key);

    const chips = screen.getByTestId(`trail-flags-${contribution.key}`);
    expect(chips.textContent).toBe('Cold at retailCold at project');
  });

  it('says "Not classified" rather than reading an unclassified item as cold', () => {
    const cell = cellOf([demand({ qty: '100' })]);
    const contribution = cell.contributions[0];
    contribution.item_flags = {
      dealer_hot_selling: false,
      dealer_hot_selling_where: [],
      project_hot_selling: false,
      project_hot_selling_where: [],
      dealer_classified: false,
      project_classified: false,
      discontinued: false,
      retail_classification_available: false,
    };
    renderCell(cell);
    openTrail(contribution.key);

    expect(screen.getByTestId(`trail-flags-${contribution.key}`).textContent).toBe(
      'Not classified',
    );
  });

  it('shows no chips at all on a line the ladder never walked', () => {
    const cell = cellOf([demand({ fulfilment_location: null })]);
    const key = cell.contributions[0].key;
    expect(cell.contributions[0].item_flags).toBeNull();
    renderDialog([demand({ fulfilment_location: null })]);
    openTrail(key);

    expect(screen.queryByTestId(`trail-flags-${key}`)).not.toBeInTheDocument();
  });

  it('lays the pool pile out under the pool rung - on hand, SO, SPO, available, free, claimed ahead, left', () => {
    const cell = cellOf([demand({ qty: '1' })]);
    const contribution = cell.contributions[0];
    const pool = contribution.trail?.find((step) => step.kind === 'pool');
    // The captain's B2155-NL-BLUE rung: BRW holds 1, its own line ahead claims it, 0 left.
    Object.assign(pool ?? {}, {
      location: 'BRW',
      warehouse_id: 'wh-BRW',
      answer: 'no',
      took: '0',
      from: null,
      note: null,
      why: "BRW holds 1 on hand (Available 1 in stock), but BRW's own orders ranked ahead of this line claim 1, so 0 is left.",
      pool: {
        location: 'BRW',
        warehouse_id: 'wh-BRW',
        on_hand: '1',
        so_qty: '1',
        spo_qty: '0',
        available: '0',
        reserved: '0',
        free: '1',
        claimed_ahead_qty: '1',
        claimed_ahead_lines: 1,
        left: '0',
        reorder_level: '0',
        cap: null,
      },
    });
    renderCell(cell);
    openTrail(contribution.key);

    expect(stepCells(contribution.key, 'pool').slice(1, 4)).toEqual([
      'Can we take from the pool?',
      'No',
      '0',
    ]);
    expect(screen.getByTestId(`trail-why-${contribution.key}-pool`).textContent).toBe(
      "BRW holds 1 on hand (Available 1 in stock), but BRW's own orders ranked ahead of this line claim 1, so 0 is left.",
    );
    const table = screen.getByTestId(`trail-pool-${contribution.key}`);
    const headers = [...table.querySelectorAll('th')].map((node) => node.textContent);
    expect(headers).toEqual(['On hand', 'SO qty', 'SPO qty', 'Available', 'Free', 'Claimed ahead', 'Left']);
    const values = [...table.querySelectorAll('td')].map((node) => node.textContent);
    expect(values).toEqual(['1', '1', '0', '0', '1', '1 (1 line)', '0']);
  });

  it('shows no pool sub-table when there is no shared pool', () => {
    const cell = cellOf([demand({ qty: '100' })]);
    renderDialog([demand({ qty: '100' })]);
    const key = cell.contributions[0].key;
    openTrail(key);

    expect(screen.getByTestId(`trail-why-${key}-pool`).textContent).toBe(
      'No shared pool holds this product.',
    );
    expect(screen.queryByTestId(`trail-pool-${key}`)).not.toBeInTheDocument();
  });
});

/**
 * The expansions belong to the CELL that is open, not to the dialog.
 *
 * The dialog stays mounted while the board points it at one cell after another, so an expansion
 * left open would show the previous cell's documents underneath the new cell's location row -
 * the same product code and warehouse in the panel heading, entirely the wrong position.
 */
describe('BoardCellBreakdownDialog: the stock expansions belong to the cell', () => {
  function stockedCell(itemCode: string, bucket: string): BoardCell {
    const cell = cellOf([demand()]);
    return {
      ...cell,
      item_code: itemCode,
      bucket_key: bucket,
      locations: [
        {
          ...cell.locations[0],
          location: 'BRW-BB',
          product_id: 'prod-1',
          warehouse_id: 'wh-1',
          qty_on_hand: '478',
        },
      ],
    };
  }

  function dialogFor(cell: BoardCell) {
    return (
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}
      >
        <BoardCellBreakdownDialog
          cell={cell}
          bucketLabel="31 Aug 2026"
          draft={{}}
          onDecide={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>
    );
  }

  it('closes an open expansion when the dialog is pointed at another cell', async () => {
    // Left in flight on purpose: what is under test is which cell the expansion belongs to, and
    // the documents themselves are `StockDocumentsPanel`'s own suite.
    getStockDetail.mockReturnValue(new Promise(() => {}));

    const { rerender } = render(dialogFor(stockedCell('WESERP10B', '2026-08-31')));

    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    expect(await screen.findByTestId('stock-expansion-BRW-BB')).toBeInTheDocument();

    rerender(dialogFor(stockedCell('B2155-NL-BLUE', '2026-09-28')));

    expect(screen.queryByTestId('stock-expansion-BRW-BB')).not.toBeInTheDocument();
    expect(screen.getByTestId('cell-location-BRW-BB')).toBeInTheDocument();
  });
});

/**
 * A line an ACTIVE decision already covers (PLAN 13.4).
 *
 * Live on SO403765 line 1: the planner confirmed "borrow 10 from MWH-IB, buy 33" and the board
 * went on offering Approve / Amend / Reject beside a FRESH proposal of Buy 43, a share note
 * reading "First in the queue at BRW-BB · 0 left for this line", and a trail whose first rung
 * said the pile had offered nothing. Every one of those is a statement about a contest the line
 * had already left.
 *
 * A covered row states what was decided, and offers the only decision that is left: Amend.
 */
describe('BoardCellBreakdownDialog: a line a decision already covers', () => {
  const frozen = {
    revision_no: 1,
    confirmed_at: '2026-08-18T02:00:00',
    timely_spo_qty: '0',
    reserve: [],
    borrow: [
      {
        source: 'other_location' as const,
        warehouse_id: 'wh-mwh-ib',
        location: 'MWH-IB',
        donor_project_id: null,
        qty: '10',
        reason: 'The other site can wait a week.',
      },
    ],
    buy_qty: '33',
    amend_reason: 'Borrowed rather than bought, agreed with the other site.',
  };

  const covered = (overrides: Partial<BoardDemandLine> = {}) =>
    demand({ qty: '43', decision: frozen, ...overrides });

  it('states the revision and the composition that was frozen, not a verdict', () => {
    renderDialog([covered()]);

    expect(
      screen.getByText('Confirmed rev 1 · Borrow (other) 10 MWH-IB · Buy 33'),
    ).toBeInTheDocument();
  });

  it('offers Amend and nothing else: there is no approving what is already decided', () => {
    renderDialog([covered()]);

    const table = contributionTable();
    expect(within(table).getByRole('button', { name: 'Amend' })).toBeInTheDocument();
    expect(within(table).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(within(table).queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();
    expect(within(table).queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });

  it('shows the frozen composition in the source strip, naming where a borrow came from', () => {
    renderDialog([covered()]);

    expect(screen.getByText('Borrow (other) 10 from MWH-IB · Buy 33')).toBeInTheDocument();
  });

  it('says nothing about a queue it is not in', async () => {
    // "0 left for this line" is a claim about a contest. A covered line left the contest, which
    // is exactly why the pile's own queue does not hold it - even though the frozen composition
    // still carries its own reasons behind the icon.
    renderDialog([covered()]);

    expect(await sourceNoteOf('so-a|1|WESERP10B|2026-08-31')).not.toContain('left for this line');
  });

  it('replaces the ladder with the one fact there is: when it was confirmed', () => {
    renderDialog([covered()]);

    fireEvent.click(screen.getByTestId('trail-info-so-a|1|WESERP10B|2026-08-31'));

    const trail = screen.getByTestId('trail-so-a|1|WESERP10B|2026-08-31');
    expect(trail.textContent).toContain('Confirmed in revision 1');
    expect(trail.querySelector('table')).toBeNull();
  });

  it('seeds the amendment from the frozen composition, not from a fresh proposal', () => {
    renderDialog([covered()]);

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));

    // The borrow the planner made is IN the editor, at the quantity they made it, rather
    // than whatever the engine would propose for an undecided line.
    expect(screen.getByLabelText('Borrow from MWH-IB')).toHaveValue(10);
    // Buy is a whole-line switch (AC-L5) and this composition carries stock, so it is off.
    expect(screen.getByLabelText('Buy the whole line')).not.toBeChecked();
  });

  it('behaves like any amended row once it has been amended', () => {
    renderDialog([covered()], {}, {
      'so-a|1|WESERP10B|2026-08-31': {
        verdict: 'amended',
        reserve_qty: '0',
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '43',
        reason: 'The other site needs its stock back.',
      },
    });

    expect(screen.getByText('Buy 43')).toBeInTheDocument();
    const table = contributionTable();
    expect(within(table).getByRole('button', { name: 'Undo' })).toBeInTheDocument();
  });

  it('cannot be swept into a bulk verdict, because Amend is the only verb it has', () => {
    renderDialog([covered()]);

    const table = contributionTable();
    const boxes = within(table).getAllByRole('checkbox');
    // The row's own box, not the header's.
    expect(boxes[boxes.length - 1]).toBeDisabled();
  });

  it('counts as decided in the header, because it is - in the database', () => {
    renderDialog([covered(), demand({ line_no: 2, qty: '21' })]);

    const needed = screen.getByTestId('cell-quantity-needed');
    expect(needed).toHaveTextContent('64');
    expect(needed).toHaveTextContent('1 decided');
  });

  it('counts the frozen line into the outstanding total, decided or not', () => {
    renderDialog([covered(), demand({ line_no: 2, qty: '21', sales_order_id: 'so-a' })], {
      'WESERP10B|BRW-BB': '5',
    });

    // 43 outstanding on the covered line and 21 on the undecided one. A decision is a claim on
    // stock, not a delivery, so it does not take the line out of what is still outstanding.
    expect(footerCells()).toContain('64');
  });
});

describe('BoardCellBreakdownDialog: what purchasing has already been told', () => {
  /**
   * The Decision column says what was PROMISED. It cannot say whether anybody acted on it,
   * and that is the question a planner opens this dialog with a second time: an approved
   * revision with nothing placed against it and one fully placed look identical without the
   * inquiry beside it.
   *
   * Absent is the ordinary case, so the column has to state it rather than leave a blank
   * cell that reads as a rendering fault.
   */
  it('names the inquiry and its state beside the Decision column', () => {
    renderDialog([
      demand({ order_inquiry: { inquiry_no: 'OI-000123', state: 'placed' } }),
    ]);

    const table = contributionTable();
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((node) => node.textContent ?? '');
    expect(headers.some((header) => header.includes('Order inquiry'))).toBe(true);

    const row = table.querySelectorAll('tbody tr')[0] as HTMLElement;
    expect(within(row).getByText('OI-000123')).toBeInTheDocument();
    // The worklist's own wording, so "Placed" cannot mean two things on two screens.
    expect(within(row).getByText('Linked')).toBeInTheDocument();
  });

  it('prints a dash for a line nobody has been told anything about', () => {
    renderDialog([demand({ order_inquiry: null })]);

    const row = contributionTable().querySelectorAll('tbody tr')[0] as HTMLElement;
    expect(within(row).queryByText(/^OI-/)).not.toBeInTheDocument();
    expect(within(row).getAllByText('-').length).toBeGreaterThan(0);
  });
});

/**
 * The Suggestion card names the LOCATIONS WITH THEIR QUANTITIES (AC-A1, AC-A2).
 *
 * The captain, on SO415472: "Use own location, 71 from BRW reads wrong" - BRW is the shared
 * pool, and the line's own location is its `-BB` warehouse. And on SO324132 rev 1: a row reading
 * "932 from DC1-BB, MWH-BB, WH3-BB" left the split to be guessed, when the split IS the
 * instruction: three separate movements of stock, each keyed by hand.
 */
describe('BoardCellBreakdownDialog: how the Suggestion card names its sources', () => {
  function renderWithSources(sources: BoardContribution['sources']) {
    const base = cellOf([demand({ qty: '932' })]);
    const cell: BoardCell = {
      ...base,
      // BOTH, the way the server sends them on an undecided line: `sources` is the live
      // proposal and `proposed` is the same list under the key the Suggestion card reads.
      contributions: base.contributions.map((entry) => ({
        ...entry,
        sources,
        // Stamped `v4`, which is what a confirm writes today. An UNSTAMPED frozen proposal
        // is a suggestion from a ladder that no longer runs, and the card says so - see
        // the test below.
        proposed: { components: sources.map((part) => ({ ...part, ladder: 'v4' })) },
      })),
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <BoardCellBreakdownDialog
          cell={cell}
          bucketLabel="31 Aug 2026"
          draft={{}}
          onDecide={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
  }

  it('calls a pool draw shared stock, and names the pool (AC-A1)', () => {
    renderWithSources([
      { kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW', reason: 'The pool covers it.' },
    ]);

    const card = screen.getByTestId('cell-suggestion');
    expect(card).toHaveTextContent('Use shared stock');
    expect(card).toHaveTextContent('71 from BRW');
    expect(card).not.toHaveTextContent('Use own location');
  });

  it('names each location with what is taken from it on a group take (AC-A2)', () => {
    renderWithSources([
      { kind: 'reserve', rung: 'group_take', qty: '454', location: 'DC1-BB', reason: 'a' },
      { kind: 'reserve', rung: 'group_take', qty: '267', location: 'MWH-BB', reason: 'b' },
      { kind: 'reserve', rung: 'group_take', qty: '211', location: 'WH3-BB', reason: 'c' },
    ]);

    const card = screen.getByTestId('cell-suggestion');
    expect(card).toHaveTextContent('Use own location');
    expect(card).toHaveTextContent('454 from DC1-BB, 267 from MWH-BB, 211 from WH3-BB');
  });

  it('labels a frozen suggestion that a ladder no longer in use composed', () => {
    // "MWH-IB has 30 available in the IB group" is v3 reading ONE warehouse's own
    // availability; under v4 that is not a reading anybody makes, and v5 has no Incoming
    // rung at all. A stamp that is not today's - absent, or an older version - says so.
    const base = cellOf([demand({ qty: '60' })]);
    const stale: BoardContribution['sources'] = [
      {
        kind: 'reserve',
        rung: 'group_take',
        qty: '60',
        location: 'MWH-IB',
        reason: 'MWH-IB has 30 available in the IB group.',
      },
    ];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <BoardCellBreakdownDialog
          cell={{
            ...base,
            contributions: base.contributions.map((entry) => ({
              ...entry,
              covered: true,
              proposed: { components: stale },
            })),
          }}
          bucketLabel="31 Aug 2026"
          draft={{}}
          onDecide={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    const card = screen.getByTestId('cell-suggestion');
    expect(card).toHaveTextContent('Suggestion (before ladder v5)');
    // One short label and no sentence: what a planner needs is to know they are reading
    // history, not a paragraph about ladder versions.
    expect(card).not.toHaveTextContent(/no longer/);
  });

  it('leaves a suggestion the current ladder composed unlabelled', () => {
    renderWithSources([
      {
        kind: 'reserve',
        rung: 'pool',
        qty: '71',
        location: 'BRW',
        ladder: 'v5',
        reason: 'The pool covers it.',
      },
    ]);

    expect(screen.getByTestId('cell-suggestion')).not.toHaveTextContent('before ladder');
  });

  it('never labels an UNDECIDED line, whatever its suggestion carries (AC-V8)', () => {
    // A line with no decision shows the LIVE suggestion, which is today's answer by
    // definition. This is the bug the criterion is about: the test used to be "no `ladder`
    // key", the server stamped the key on neither the live nor the frozen source, and the
    // label therefore appeared on every line on the board.
    const base = cellOf([demand({ qty: '60' })]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <BoardCellBreakdownDialog
          cell={{
            ...base,
            contributions: base.contributions.map((entry) => ({
              ...entry,
              covered: false,
              proposed: {
                components: [
                  {
                    kind: 'reserve',
                    rung: 'group_take',
                    qty: '60',
                    location: 'MWH-IB',
                    reason: 'The IB group nets 60.',
                  },
                ],
              },
            })),
          }}
          bucketLabel="31 Aug 2026"
          draft={{}}
          onDecide={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('cell-suggestion')).not.toHaveTextContent('before ladder');
  });

  it('tells the two borrows apart by rung (AC-A3)', () => {
    renderWithSources([
      {
        kind: 'borrow',
        rung: 'group_borrow',
        qty: '3',
        location: 'BRW-BB',
        reason: 'a',
      },
      {
        kind: 'borrow',
        rung: 'cross_group_borrow',
        qty: '9',
        location: 'BRW-HP',
        reason: 'b',
      },
    ]);

    const card = screen.getByTestId('cell-suggestion');
    expect(card).toHaveTextContent('Borrow from another order');
    expect(card).toHaveTextContent('Borrow other location');
  });
});

/**
 * AC-D3: a Decision card BESIDE the Suggestion card, same shape, same words.
 *
 * The captain, on the board: "one page that shows what was SUGGESTED and what was DECIDED, in
 * the same words". Before this, a covered cell showed its frozen composition under the word
 * "Suggestion" - so an amended line looked as though the engine had suggested exactly what
 * somebody had changed it to.
 */
describe('BoardCellBreakdownDialog: the Decision card', () => {
  function renderComposition(
    over: Partial<BoardContribution>,
    draft: BoardDraft = {},
  ) {
    const base = cellOf([demand({ qty: '71' })]);
    const cell: BoardCell = {
      ...base,
      contributions: base.contributions.map((entry) => ({ ...entry, ...over })),
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <BoardCellBreakdownDialog
          cell={cell}
          bucketLabel="31 Aug 2026"
          draft={draft}
          onDecide={vi.fn()}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    return cell;
  }

  /**
   * AC-E6 / section E: the Decision card ends with the MOVEMENTS the decision implies, so a
   * planner sees the transfers Approve is about to raise before pressing it.
   */
  it('ends with a Moves line naming what has to be carried, and to where', () => {
    renderComposition({
      covered: true,
      proposed: {
        components: [
          { kind: 'buy', rung: 'buy', qty: '71', location: null, reason: 'nothing free' },
        ],
      },
      sources: [],
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [
          { warehouse_id: 'wh-dc1', location: 'DC1-BB', qty: '454', rung: 'group_take' },
          { warehouse_id: 'wh-mwh', location: 'MWH-BB', qty: '267', rung: 'group_take' },
        ],
        borrow: [],
        buy_qty: '0',
      },
    });

    expect(screen.getByTestId('decision-moves')).toHaveTextContent(
      'Moves: 454 DC1-BB -> BRW-BB · 267 MWH-BB -> BRW-BB',
    );
    // Never on the Suggestion card: nothing has been decided to move.
    expect(screen.queryByTestId('suggestion-moves')).not.toBeInTheDocument();
  });

  it('draws no Moves line when everything is already at the line\'s own location', () => {
    renderComposition({
      covered: true,
      proposed: { components: [] },
      sources: [],
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [
          { warehouse_id: 'wh-brw-bb', location: 'BRW-BB', qty: '71', rung: 'group_take' },
        ],
        borrow: [],
        buy_qty: '0',
      },
    });

    expect(screen.getByTestId('cell-decision')).toBeInTheDocument();
    expect(screen.queryByTestId('decision-moves')).not.toBeInTheDocument();
  });

  it('says Not recorded, never "nothing proposed", on a revision that froze no proposal', () => {
    // Verified live on SO324132 rev 1, whose four lines all predate the field: the card read
    // "Nothing proposed for this cell", which is a claim about the LADDER rather than about
    // the record, and it is not true - the ladder proposed plenty, nobody kept it.
    renderComposition({
      covered: true,
      // Null, the way the server sends a revision written before the field existed.
      proposed: null,
      sources: [
        { kind: 'buy', rung: 'buy', qty: '71', location: null, reason: 'Bought, as confirmed.' },
      ],
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '71',
      },
    });

    expect(screen.getByTestId('cell-suggestion')).toHaveTextContent(
      'Not recorded for this revision',
    );
  });

  it('is absent while nothing on the cell is decided', () => {
    renderComposition({
      proposed: {
        components: [
          { kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW', reason: 'pool' },
        ],
      },
    });

    expect(screen.getByTestId('cell-suggestion')).toBeInTheDocument();
    expect(screen.queryByTestId('cell-decision')).not.toBeInTheDocument();
  });

  it('appears beside the suggestion once a line is confirmed, and states the decision', () => {
    renderComposition({
      covered: true,
      proposed: {
        components: [
          { kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW', reason: 'The pool covers it.' },
        ],
      },
      sources: [
        { kind: 'buy', rung: 'buy', qty: '71', location: null, reason: 'Bought, as confirmed.' },
      ],
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '71',
      },
    });

    const suggestion = screen.getByTestId('cell-suggestion');
    const decision = screen.getByTestId('cell-decision');
    expect(suggestion).toHaveTextContent('Use shared stock');
    expect(suggestion).toHaveTextContent('71 from BRW');
    expect(decision).toHaveTextContent('Buy');
    expect(decision).toHaveTextContent('71');
    // Beside it, not under it: the two are read against each other.
    expect(suggestion.compareDocumentPosition(decision)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it('appears on a line merely ticked into this session draft, before anything is posted', () => {
    const cell = cellOf([demand({ qty: '71' })]);
    const key = cell.contributions[0].key;
    renderComposition(
      {
        proposed: {
          components: [
            { kind: 'reserve', rung: 'pool', qty: '71', location: 'BRW', reason: 'pool' },
          ],
        },
      },
      { [key]: { verdict: 'approved' } },
    );

    // An approval takes the proposal as it stands, so the two cards agree - which is itself
    // the answer to "did we do what the engine said".
    expect(screen.getByTestId('cell-decision')).toHaveTextContent('Use shared stock');
  });
});

/**
 * 375px (ADR-PRODUCT-STANDARDS: "usable and non-clipped at 375px AND 1280px").
 *
 * jsdom does no real layout, so what this pins is structural, not a measured pixel width:
 * the table lives inside `PanelDataGrid`'s own `ScrollArea` (`overflow-hidden` on the Radix
 * root, which is what makes its internal viewport scroll rather than the dialog clipping the
 * table), and nothing on the way to it carries a fixed pixel width that would force the
 * dialog itself wider than the viewport at 375px.
 */
describe('BoardCellBreakdownDialog: the table scrolls inside its own container at 375px', () => {
  it('wraps the table in a ScrollArea, not a fixed-width box', () => {
    renderDialog([demand({ qty: '71' })], { 'BRW-BB': '71' });

    const scrollArea = document.querySelector('[data-slot="scroll-area"]');
    expect(scrollArea).not.toBeNull();
    expect(scrollArea).toHaveClass('overflow-hidden');

    // No fixed pixel width anywhere between the scroll area and the dialog's own root: a
    // `w-[960px]` (Tailwind's own fixed-width syntax) or an inline `style.width` in px would
    // force the dialog to overflow a 375px viewport rather than scrolling its table.
    let node: Element | null = scrollArea;
    while (node) {
      expect(node.className).not.toMatch(/\bw-\[\d+px\]/);
      const inlineWidth = (node as HTMLElement).style?.width ?? '';
      expect(inlineWidth).not.toMatch(/^\d+px$/);
      node = node.parentElement;
    }
  });
});
