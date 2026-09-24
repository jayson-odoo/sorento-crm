/**
 * S2 - the cell drill (AC-S2-7, AC-S2-11, R28/R30/R31/R37).
 *
 * Two TABS behind one cell, and four sentences that are easy to get subtly wrong: Plan
 * hands the ORDER to the board, an overdue document says it counts as nothing, a PO's
 * bought-for date is stated as what it is and never as an arrival, and the two footers
 * foot with the cell that opened them (`Free` less `Uncovered` is the balance in the
 * title, R37).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  StockDebtCell,
  StockDebtDemandLine,
  StockDebtSupplyEvent,
} from '../types/stockDebt.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/stock-debt',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getStockDebtCell = vi.fn();

vi.mock('../services/stockDebtService', () => ({
  getStockDebtList: vi.fn(),
  getStockDebtCell: (...args: unknown[]) => getStockDebtCell(...args),
}));

import { StockDebtCellDialog } from './StockDebtCellDialog';

// R22/R25: `qty_ordered`/`qty_delivered` (on each demand line) and `demand_total_qty`/
// `supply_total_qty` (on the envelope) are not on the types yet - the coder's
// schema/type change this round. Cast (an `as` assertion, not a `:` annotation) so the
// fixture states the WIRE shape the coder is adding without an excess-property error
// blocking the whole file from compiling in the meantime.
//
// R23: the second supply row used to be a `kind: 'po'` (a PO's own `bought_for` date,
// tested separately below) - Stock Debt's own walk never emits one any more ("got PO
// doesn't mean got supply"), so the SHARED fixture carries only `on_hand`/`spo` kinds
// now, matching what the real service actually sends. `free_qty` on BOTH rows stays 0:
// the R37 footing test below (`Free 0`) depends on the shared fixture's total free
// quantity being zero, so a Free-sum fixture with real free stock lives in its own
// dedicated test instead of here.
const CELL = {
  demand: [
    {
      so_number: 'SO390918',
      agent_code: 'JENNIFER',
      warehouse_code: 'BRW-BB',
      required_date: '2026-10-15',
      open_qty: 12,
      qty_ordered: 20,
      qty_delivered: 8,
      assigned_qty: 12,
      assigned_source: 'On hand BRW-BB',
      short_qty: 0,
      status: 'covered',
    } as StockDebtDemandLine,
    {
      so_number: 'SO375875',
      agent_code: 'JAY',
      warehouse_code: 'MWH-BB',
      required_date: '2026-10-26',
      open_qty: 32,
      qty_ordered: 32,
      qty_delivered: 0,
      assigned_qty: 16,
      assigned_source: 'On hand BRW-BB',
      short_qty: 16,
      status: 'short',
    } as StockDebtDemandLine,
  ],
  supply: [
    {
      kind: 'spo',
      ref: 'SPO 2026/09-0088',
      warehouse_code: 'MWH-BB',
      date: '2026-10-12',
      bought_for: null,
      qty: 40,
      free_qty: 0,
      overdue: false,
      assigned_to: [{ so_number: 'SO407114', qty: 40 }],
    },
    {
      kind: 'spo',
      ref: 'SPO 2026/07-0021',
      warehouse_code: 'BRW-BB',
      date: '2026-08-16',
      bought_for: null,
      qty: 12,
      free_qty: 0,
      overdue: true,
      assigned_to: [],
    },
  ],
  // R25: the envelope's own quantity totals - sum of `open_qty` (44 = 12 + 32) and sum
  // of `qty` (52 = 40 + 12) over these same rows, echoed rather than recomputed by the
  // FE (`app/services/scm/stock_debt_service.py` owns the arithmetic).
  demand_total_qty: 44,
  supply_total_qty: 52,
} as StockDebtCell;

function renderDialog(cell: StockDebtCell = CELL) {
  getStockDebtCell.mockResolvedValue(cell);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockDebtCellDialog
        productId="p1"
        productCode="SRTWB242"
        productName="Sorento basin 242"
        month="2026-10"
        monthLabel="Oct 26"
        balance={-16}
        // R16 retired the ownership group entirely - the board narrows the drill with a
        // due date range and a book now, never a group; `dateFrom`/`dateTo`/`book` are
        // real props on the dialog (the coder's rename landed).
        dateFrom="2026-11-01"
        dateTo="2026-11-30"
        book="retail"
        onClose={() => {}}
      />
    </QueryClientProvider>,
  );
}

/** Radix's TabsTrigger switches on mouse down; a bare `click` leaves the old panel up. */
function switchTab(name: string) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}

beforeEach(() => vi.clearAllMocks());

describe('StockDebtCellDialog', () => {
  it('asks for the cell it was opened on', async () => {
    renderDialog();
    // AC-11/AC-11b/R14: the drill carries the board's due date range and book - never an
    // ownership group, which R16 retired.
    await waitFor(() =>
      expect(getStockDebtCell).toHaveBeenCalledWith(
        'p1', '2026-10', '2026-11-01', '2026-11-30', 'retail',
      ),
    );
  });

  it('lists the demand with its bin, its due date and its status', async () => {
    renderDialog();

    expect(await screen.findByText('SO390918')).toBeInTheDocument();
    expect(screen.getByText('JENNIFER')).toBeInTheDocument();
    // The Bin column (AC-S2-7): which pile the line sits in decides everything else. Both
    // codes also appear in the Supply table, so the assertion is scoped to Demand's row.
    const shortRow = screen.getByText('SO375875').closest('tr') as HTMLElement;
    expect(within(shortRow).getByText('MWH-BB')).toBeInTheDocument();
    const coveredRow = screen.getByText('SO390918').closest('tr') as HTMLElement;
    expect(within(coveredRow).getByText('BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('covered')).toBeInTheDocument();
    // A short line says HOW short, because the quantity is the thing to act on.
    expect(screen.getByText('short 16')).toBeInTheDocument();
  });

  it('lists the R22 Demand columns, in order, with no Plan button left (R21/R22)', async () => {
    // R21 retires the Plan button column from the Demand grid entirely - RED today: the
    // "hands the ORDER to the board on Plan" behaviour this test replaces is still there,
    // and neither Ordered nor Delivered is a column yet ("Open" is still the header, not
    // "Outstanding").
    renderDialog();
    await screen.findByText('SO390918');

    const headers = screen.getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers).toEqual([
      'Sales order', 'Agent', 'Bin', 'Due', 'Ordered', 'Delivered', 'Outstanding',
      'Assigned', 'From', 'Status',
    ]);
    expect(screen.queryByRole('link', { name: 'Plan' })).not.toBeInTheDocument();
  });

  it('sorts the Demand grid on every column, toggling asc/desc (R20)', async () => {
    // RED today: the grid is not sortable at all - `PanelDataGrid` is not given
    // `sortable`, so clicking "Due" does nothing and the row order never changes.
    renderDialog({
      demand: [
        {
          so_number: 'SO-LATE', agent_code: 'A', warehouse_code: 'W1',
          required_date: '2026-10-26', open_qty: 1, qty_ordered: 1, qty_delivered: 0,
          assigned_qty: 1, assigned_source: null, short_qty: 0, status: 'covered',
        } as StockDebtDemandLine,
        {
          so_number: 'SO-EARLY', agent_code: 'B', warehouse_code: 'W2',
          required_date: '2026-10-05', open_qty: 1, qty_ordered: 1, qty_delivered: 0,
          assigned_qty: 1, assigned_source: null, short_qty: 0, status: 'covered',
        } as StockDebtDemandLine,
      ],
      supply: [],
    });
    await screen.findByText('SO-LATE');

    function firstRowSo() {
      return within(screen.getAllByRole('row')[1]).getAllByRole('cell')[0].textContent;
    }

    // Unsorted (service order): the later-due row is fed first and stays first.
    expect(firstRowSo()).toBe('SO-LATE');

    fireEvent.click(screen.getByText('Due'));
    await waitFor(() => expect(firstRowSo()).toBe('SO-EARLY'));

    fireEvent.click(screen.getByText('Due'));
    await waitFor(() => expect(firstRowSo()).toBe('SO-LATE'));
  });

  it('searches the Demand grid by sales order, agent or bin, and the tab follows the filter BY QUANTITY (R20/R25)', async () => {
    // RED today: there is no search box on the dialog at all - `PanelDataGrid` is not
    // given `searchOf`, so `getByRole('searchbox')` throws. R25 (folded in here rather
    // than kept a record-count check that would go stale the moment R25 lands beside
    // R20): the filtered half of the label is the SUM of Outstanding over the rows still
    // matching, not how many rows there are - 7 and 3 are deliberately unequal so a
    // record-count reading ("1 of 2") and a quantity reading ("7 of 10") cannot be
    // confused for one another.
    renderDialog({
      demand: [
        {
          so_number: 'SO-A', agent_code: 'JUSTIN', warehouse_code: 'W1',
          required_date: '2026-10-05', open_qty: 7, qty_ordered: 7, qty_delivered: 0,
          assigned_qty: 7, assigned_source: null, short_qty: 0, status: 'covered',
        } as StockDebtDemandLine,
        {
          so_number: 'SO-B', agent_code: 'MARIA', warehouse_code: 'W2',
          required_date: '2026-10-06', open_qty: 3, qty_ordered: 3, qty_delivered: 0,
          assigned_qty: 3, assigned_source: null, short_qty: 0, status: 'covered',
        } as StockDebtDemandLine,
      ],
      supply: [],
      demand_total_qty: 10,
      supply_total_qty: 0,
    } as StockDebtCell);
    await screen.findByText('SO-A');
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Demand (10)', 'Supply (0)',
    ]);

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'JUSTIN' } });

    await waitFor(() => expect(screen.queryByText('SO-B')).not.toBeInTheDocument());
    expect(screen.getByText('SO-A')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Demand (7 of 10)' })).toBeInTheDocument();
  });

  it('prints Ordered, Delivered and Outstanding from the fixture (R22)', async () => {
    renderDialog();
    const row = (await screen.findByText('SO390918')).closest('tr') as HTMLElement;

    expect(within(row).getByText('20')).toBeInTheDocument();
    expect(within(row).getByText('8')).toBeInTheDocument();
    expect(within(row).getByText('12')).toBeInTheDocument();
  });

  it('shows a Total footer row on both grids, over ALL rows of the tab (R24)', async () => {
    // RED today: neither grid has a footer row at all. Demand totals Ordered/Delivered/
    // Outstanding/Assigned (52/8/44/28, from `CELL.demand`'s own two rows); Supply
    // totals Qty and Free - a dedicated fixture here, not the shared `CELL` (whose two
    // supply rows both carry `free_qty: 0` on purpose, for the R37 footing test above).
    renderDialog({
      demand: CELL.demand,
      supply: [
        {
          kind: 'spo', ref: 'SPO A', warehouse_code: 'W1', date: '2026-10-01',
          bought_for: null, qty: 40, free_qty: 10, overdue: false, assigned_to: [],
        },
        {
          kind: 'spo', ref: 'SPO B', warehouse_code: 'W2', date: '2026-10-02',
          bought_for: null, qty: 20, free_qty: 5, overdue: false, assigned_to: [],
        },
      ],
      demand_total_qty: 44,
      supply_total_qty: 60,
    } as StockDebtCell);
    await screen.findByText('SO390918');

    const demandTotalRow = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(demandTotalRow).getByText('52')).toBeInTheDocument();
    expect(within(demandTotalRow).getByText('8')).toBeInTheDocument();
    expect(within(demandTotalRow).getByText('44')).toBeInTheDocument();
    expect(within(demandTotalRow).getByText('28')).toBeInTheDocument();
    // R24 addendum: Short (sum of `short_qty`, 0 + 16) sits in the Status column of the
    // Demand Total row - there is no separate "Uncovered" line under the grid any more.
    expect(within(demandTotalRow).getByText('Short 16')).toBeInTheDocument();

    switchTab('Supply (60)');
    const supplyTotalRow = (await screen.findByText('Total')).closest('tr') as HTMLElement;
    expect(within(supplyTotalRow).getByText('60')).toBeInTheDocument();
    // R24 addendum: Free (sum of `free_qty`, 10 + 5) sits in the Supply Total row itself.
    expect(within(supplyTotalRow).getByText('Free 15')).toBeInTheDocument();
  });

  it('lists the supply with its document, arrival and who holds it', async () => {
    renderDialog();
    await screen.findByText('SO390918');
    switchTab('Supply (52)');

    expect(await screen.findByText('SPO 2026/09-0088')).toBeInTheDocument();
    expect(screen.getByText('SO407114 (40)')).toBeInTheDocument();
    // Nobody has it: "Free" rather than a blank cell, which reads as a missing figure.
    expect(screen.getByText('Free')).toBeInTheDocument();
  });

  it('says an overdue document counts as nothing, and only a PO says what it was bought for', async () => {
    // R23 retired `kind: 'po'` from Stock Debt's own SERVICE, not from the shared
    // `SupplyKind` schema - a `po` event stays a legal shape for the dialog to render if
    // one is ever passed, so this pins the DIALOG's own display rule on its own fixture
    // rather than the shared `CELL` (which now carries only `on_hand`/`spo`, matching
    // what the real service sends).
    renderDialog({
      demand: CELL.demand,
      supply: [
        {
          kind: 'spo',
          ref: 'SPO 2026/09-0088',
          warehouse_code: 'MWH-BB',
          date: '2026-10-12',
          bought_for: null,
          qty: 40,
          free_qty: 0,
          overdue: false,
          assigned_to: [{ so_number: 'SO407114', qty: 40 }],
        },
        {
          kind: 'po',
          ref: 'PO 202605-S0072 line 5',
          warehouse_code: 'BRW-BB',
          date: '2026-08-16',
          bought_for: '2026-10-15',
          qty: 12,
          free_qty: 0,
          overdue: true,
          assigned_to: [],
        },
      ],
      demand_total_qty: 44,
      supply_total_qty: 52,
    } as StockDebtCell);
    await screen.findByText('SO390918');
    switchTab('Supply (52)');

    expect(await screen.findByText('overdue, not counted')).toBeInTheDocument();
    // R30: the PO's `expected_date` is the SO date it was typed against, so it is worded as
    // that and never as an arrival - and an SPO has no such date to state.
    expect(screen.getByText('bought for 15/10/2026')).toBeInTheDocument();
    expect(screen.queryByText(/bought for 12\/10\/2026/)).not.toBeInTheDocument();
  });

  it('renders each tab own empty state rather than a blank table', async () => {
    renderDialog({
      demand: [], supply: [], demand_total_qty: 0, supply_total_qty: 0,
    } as StockDebtCell);

    expect(await screen.findByText('Nothing is due here')).toBeInTheDocument();
    switchTab('Supply (0)');
    expect(await screen.findByText('Nothing arrives here')).toBeInTheDocument();
  });

  it('names the product, the column and the balance the reader pressed', async () => {
    renderDialog();

    const dialog = await screen.findByTestId('stock-debt-cell-dialog');
    // The SCM family's shell: `<Kind> · <code>` with the qualifier beside it, and the
    // product name on the muted line under it.
    expect(within(dialog).getByText('Product · SRTWB242')).toBeInTheDocument();
    // The month and the signed balance - R16 retired the ownership-group qualifier that
    // used to sit beside them, and no dateFrom/dateTo/book slot has replaced it on this
    // dialog's own subtitle yet, so the context line is just the two.
    expect(within(dialog).getByText('Oct 26 · -16')).toBeInTheDocument();
    expect(within(dialog).getByText('Sorento basin 242')).toBeInTheDocument();
  });

  it('never repeats the code as the muted description line when the name equals the code (R27)', async () => {
    // RED today: the dialog renders `productName ?? productCode` unconditionally as the
    // description - when the two are the same string, the code prints TWICE (once in the
    // title, once again on the muted line under it). R27: the second line renders ONLY
    // when `product_name` is set AND differs from `product_code` (the BE already nulls
    // an equal name on LIST rows - AC-9 - the dialog must not reintroduce the repeat).
    getStockDebtCell.mockResolvedValue({
      demand: [], supply: [], demand_total_qty: 0, supply_total_qty: 0,
    } as StockDebtCell);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <StockDebtCellDialog
          productId="p1"
          productCode="SRTWB242"
          productName="SRTWB242"
          month="2026-10"
          monthLabel="Oct 26"
          balance={-16}
          dateFrom="2026-11-01"
          dateTo="2026-11-30"
          book="retail"
          onClose={() => {}}
        />
      </QueryClientProvider>,
    );

    const dialog = await screen.findByTestId('stock-debt-cell-dialog');
    expect(within(dialog).getByText('Product · SRTWB242')).toBeInTheDocument();
    const description = dialog.querySelector('[data-slot="dialog-description"]');
    expect(description?.textContent?.trim() ?? '').toBe('');
  });

  it('is two tabs, Demand first, each saying the total QUANTITY the tab holds, not a record count (R25)', async () => {
    // RED today: the tab label is `demand.length`/`supply.length` (a record count) - "2"
    // either way regardless of the envelope's own `demand_total_qty`/`supply_total_qty`
    // fields, which do not exist on the wire yet at all.
    renderDialog();
    await screen.findByText('SO390918');

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Demand (44)', 'Supply (52)']);
    // Demand is what the reader came for: which orders go without.
    expect(tabs[0]).toHaveAttribute('data-state', 'active');
  });

  it('formats the tab quantity with thousands separators (R25)', async () => {
    renderDialog({
      demand: CELL.demand,
      supply: CELL.supply,
      demand_total_qty: 5619,
      supply_total_qty: 1000,
    } as StockDebtCell);
    await screen.findByText('SO390918');

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Demand (5,619)', 'Supply (1,000)',
    ]);
  });

  it('foots with the cell that opened it: Free less Short is the balance, both in the Total rows now (R37/R24 addendum)', async () => {
    // R24 addendum (owner, 24 Sep): the standalone "Uncovered N" / "Free N" footer LINES
    // under each grid retire - their numbers move INTO the Total row instead (Status
    // column on Demand, sum of `short_qty`; the Supply Total row's own Free, sum of
    // `free_qty`). RED today: `getByText('Uncovered 16')` still finds the old standalone
    // line, and there is no Total row for either grid to carry "Short 16" / "Free 0"
    // instead.
    renderDialog();
    await screen.findByText('SO390918');

    // The short line went without 16 on its own date; nothing in the month is free, so the
    // cell reads -16 - which is the balance in the title.
    expect(screen.queryByText('Uncovered 16')).not.toBeInTheDocument();
    const demandTotalRow = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(demandTotalRow).getByText('Short 16')).toBeInTheDocument();

    switchTab('Supply (52)');
    expect(screen.queryByText('Free 0')).not.toBeInTheDocument();
    const supplyTotalRow = (await screen.findByText('Total')).closest('tr') as HTMLElement;
    expect(within(supplyTotalRow).getByText('Free 0')).toBeInTheDocument();
  });

  it('states the short quantity a LATE line still books, although it ends fully assigned (R37)', async () => {
    // Gap case: a `late` line is one later supply cleared - `assigned_qty` equals
    // `open_qty` by the end of the walk - but it still went without ON ITS OWN DATE, and
    // `short_qty` is the server's own figure for that (re-deriving `open - assigned` gives
    // 0 for exactly this row, which is the defect R37's fixture correction exists to catch:
    // "the drill for those columns was empty" while the cell it opened from was in debt).
    renderDialog({
      demand: [
        {
          so_number: 'SO398214',
          agent_code: 'CYNDI',
          warehouse_code: 'BRW-BB',
          required_date: '2026-10-20',
          open_qty: 20,
          assigned_qty: 20,
          assigned_source: 'SPO 2026/09-0088',
          short_qty: 20,
          status: 'late',
        },
      ],
      supply: [],
    });

    expect(await screen.findByText('SO398214')).toBeInTheDocument();
    const row = screen.getByText('SO398214').closest('tr') as HTMLElement;
    // Fully assigned by the time the whole walk is over: Open and Assigned both read 20.
    expect(within(row).getAllByText('20')).toHaveLength(2);
    // ...but the status cell still states what it went without on its own date, not just
    // the word "late" with the figure that made it so left unsaid.
    expect(within(row).getByText('short 20')).toBeInTheDocument();
  });

  it('shows Qty, Received and Outstanding per SPO row, blank for an on-hand row, and all four in the Supply Total (R26)', async () => {
    // RED today: the Supply columns are still Kind/Document/Bin/Arrival/Qty/Assigned to/
    // Note - no Received or Outstanding column exists, and `qty` on a supply row is
    // still the single netted figure (R26 splits it into three: Qty is the SPO line's
    // raw ordered quantity, Received/Outstanding are new fields).
    renderDialog({
      demand: [],
      supply: [
        {
          kind: 'on_hand', ref: null, warehouse_code: 'BRW-BB', date: '2026-10-01',
          bought_for: null, qty: 40, free_qty: 40, overdue: false, assigned_to: [],
        },
        {
          kind: 'spo', ref: 'SPO 2026/09-0088', warehouse_code: 'MWH-BB',
          date: '2026-10-12', bought_for: null, qty: 100, received_qty: 30,
          outstanding_qty: 70, free_qty: 20, overdue: false,
          assigned_to: [{ so_number: 'SO390918', qty: 50 }],
        } as StockDebtSupplyEvent,
      ],
      demand_total_qty: 0,
      supply_total_qty: 110,
    } as StockDebtCell);
    await screen.findByText('Nothing is due here');
    switchTab('Supply (110)');

    const headers = screen.getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers).toEqual([
      'Kind', 'Document', 'Bin', 'Arrival', 'Qty', 'Received', 'Outstanding',
      'Assigned to', 'Note',
    ]);

    const onHandRow = screen.getByText('On hand').closest('tr') as HTMLElement;
    expect(within(onHandRow).getByText('40')).toBeInTheDocument();

    const spoRow = (await screen.findByText('SPO 2026/09-0088')).closest('tr') as HTMLElement;
    expect(within(spoRow).getByText('100')).toBeInTheDocument();
    expect(within(spoRow).getByText('30')).toBeInTheDocument();
    expect(within(spoRow).getByText('70')).toBeInTheDocument();

    const totalRow = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(totalRow).getByText('140')).toBeInTheDocument(); // Qty: 40 + 100
    expect(within(totalRow).getByText('30')).toBeInTheDocument(); // Received: 0 + 30
    expect(within(totalRow).getByText('70')).toBeInTheDocument(); // Outstanding: 0 + 70
    expect(within(totalRow).getByText('Free 60')).toBeInTheDocument(); // Free: 40 + 20
  });
});
