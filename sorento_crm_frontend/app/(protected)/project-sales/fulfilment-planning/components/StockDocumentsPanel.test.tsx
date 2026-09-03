/**
 * Stock Status with Detail: what the numbers on a location row are made of.
 *
 * AutoCount shows the position and then the documents that produce it, and the captain reads it
 * there before coming here. So this mirrors that shape: the documents, and a total that adds up
 * to the position on the row this panel expands from.
 *
 * The panel used to repeat that position as a header line of its own ("On hand 478 - SO 47,009
 * + SPO 0 = Available -46,531") and the captain called it redundant: the row immediately above
 * carries the same four figures (PLAN-scm-cs-planning-uat.md item 7, AC-A4).
 *
 * These tests were the `StockDetailDialog` suite. The captain asked for the documents to expand
 * UNDER the location row instead of opening a second dialog ("expandable details instead of
 * clicking in"), so the dialog is gone and the panel it wrapped is what stands on its own.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The shared grid's OWN async gate (`data-grid.tsx`: `isLoading: props.isLoading ||
 * isColumnPreferencesLoading`), controllable per test. Every other test in this file leaves
 * `columnPrefsGate.delayMs` at 0, which is the ORIGINAL always-`isLoading:false` mock every
 * other suite in the repo uses - only the regression test below sets it, to reproduce the
 * real second async gate that made the row land a tick after the stock query resolved.
 */
const columnPrefsGate = vi.hoisted(() => ({ delayMs: 0 }));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => {
    const [isLoading, setIsLoading] = React.useState(columnPrefsGate.delayMs > 0);
    React.useEffect(() => {
      if (columnPrefsGate.delayMs <= 0) return;
      const timer = setTimeout(() => setIsLoading(false), columnPrefsGate.delayMs);
      return () => clearTimeout(timer);
    }, []);
    return { resetToDefaults: vi.fn(), isLoading };
  },
}));

const getStockDetail = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: (...args: unknown[]) => getStockDetail(...args),
}));

import { StockDocumentsPanel } from './StockDocumentsPanel';
import type { StockDetail } from '../../_shared/types/fulfilmentPlanning.types';

/** The captain's own position, in the shape the backend actually sends it. */
function captainsPosition(overrides: Partial<StockDetail> = {}): StockDetail {
  return {
    product_id: 'prod-1',
    item_code: 'B2155-NL-BLUE',
    description: 'BLUE NYLON LEAF 2155',
    warehouse_id: 'wh-1',
    location: 'BRW-BB',
    qty_on_hand: '478',
    so_qty: '47009',
    spo_qty: '0',
    available_qty: '-46531',
    qty_reserved: '0',
    qty_held_by_decisions: '0',
    qty_free: '478',
    sales_orders: [
      {
        sales_order_id: 'so-a',
        so_number: 'SO391698',
        customer_name: 'OIB CONSTRUCTION SDN BHD',
        project_label: 'MYRA DAHLIA 9307',
        demand_class: 'project',
        doc_date: '2026-01-05',
        delivery_date: '2026-09-04',
        so_qty: '47000',
        line_id: 'line-a',
        is_this_line: true,
      },
      {
        sales_order_id: 'so-b',
        so_number: 'SO324265',
        customer_name: 'MASUKA BINA SDN BHD',
        doc_date: '2025-11-02',
        delivery_date: '2026-10-01',
        so_qty: '9',
        line_id: 'line-b',
        is_this_line: false,
      },
    ],
    incoming: [],
    ...overrides,
  };
}

function renderPanel(
  group?: string,
  extra: Partial<React.ComponentProps<typeof StockDocumentsPanel>> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <StockDocumentsPanel
        productId="prod-1"
        warehouseId={group ? null : 'wh-1'}
        group={group}
        lineIds={['line-a']}
        {...extra}
      />
    </QueryClientProvider>,
  );
}

/**
 * jsdom implements no layout, so it has no `scrollIntoView` at all - several tests below
 * assign `Element.prototype.scrollIntoView = vi.fn()` to give it one, and none of them ever
 * put it back (review round, S3), so a mock from one test could still be sitting on the
 * prototype for the next. Captured once, restored after every test, regardless of which one
 * assigned it.
 */
const ORIGINAL_SCROLL_INTO_VIEW = Element.prototype.scrollIntoView;

beforeEach(() => {
  vi.clearAllMocks();
  columnPrefsGate.delayMs = 0;
});

afterEach(() => {
  Element.prototype.scrollIntoView = ORIGINAL_SCROLL_INTO_VIEW;
});

describe('StockDocumentsPanel', () => {
  it('asks by IDS, because two products share the code B2155-NL-BLUE on the live book', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();

    await waitFor(() =>
      expect(getStockDetail).toHaveBeenCalledWith('prod-1', 'wh-1', ['line-a'], undefined),
    );
  });

  it('heads the panel with nothing at all: the row it expands from already says it', async () => {
    // Item 7 / AC-A4 took the arithmetic line; the captain took the rest on 30 August 2026 -
    // "B2155-NL-BLUE · BRW-BB" and the word "Documents" stood between the location row and
    // the columns that explain it, saying what that row already says. The column headers now
    // start directly under it.
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();

    await screen.findByRole('table');
    expect(screen.queryByTestId('stock-detail-arithmetic')).not.toBeInTheDocument();
    expect(screen.queryByText(/On hand 478 - SO 47009/)).not.toBeInTheDocument();
    expect(screen.queryByText('Documents')).not.toBeInTheDocument();
    expect(screen.queryByText('B2155-NL-BLUE · BRW-BB')).not.toBeInTheDocument();
  });

  it('names an overdue arrival as overdue, and still lists its quantity', async () => {
    // TRUST THE BOOK (captain, 26 August 2026): a promised date that has passed does not
    // remove the supply, it changes what the row SAYS. The buyer reading this is the person
    // who can chase the supplier, and they cannot do that if the row reads as though the
    // date were fine.
    getStockDetail.mockResolvedValue(
      captainsPosition({
        incoming: [
          {
            spo_number: 'SPO-2026/08-0061',
            supplier_name: 'FOSHAN WORKS',
            expected_date: '2026-08-01',
            spo_qty: '332',
            overdue_days: 25,
          },
        ],
      }),
    );

    renderPanel();

    const table = await screen.findByRole('table');
    expect(table.textContent).toContain('SPO-2026/08-0061');
    expect(table.textContent).toContain('(overdue 25 days)');
    expect(table.textContent).toContain('332');
  });

  it('a late document reads its ASSUMED date beside the stated one (R-O)', async () => {
    // R-O (3 September 2026): an overdue document counts as supply landing
    // `today + overdue_grace_days`, so the ledger row has to say which day the walk is
    // planning against AND which day the paperwork claims - the first is what a promise
    // gets made on, the second is what the buyer chases the supplier about.
    getStockDetail.mockResolvedValue(
      captainsPosition({
        incoming: [
          {
            spo_number: 'SPO-2026/07-0031',
            supplier_name: 'FOSHAN WORKS',
            expected_date: '2026-07-24',
            spo_qty: '100',
            overdue_days: 41,
            assumed_date: '2026-09-17',
            counted: true,
          },
        ],
      }),
    );

    renderPanel();

    const table = await screen.findByRole('table');
    // Through the shared `formatDateInMalaysia`, so the two dates read the same way as
    // every other date in this table rather than in a spelling of their own.
    expect(table.textContent).toContain('assumed 17/09/2026, stated 24/07/2026');
    expect(table.textContent).toContain('(overdue 41 days)');
  });

  it('a DEAD document reads "not counted" and no date at all (R-O / R31)', async () => {
    getStockDetail.mockResolvedValue(
      captainsPosition({
        incoming: [
          {
            spo_number: 'SPO-2026/01-0002',
            supplier_name: 'FOSHAN WORKS',
            expected_date: '2026-01-05',
            spo_qty: '500',
            overdue_days: 241,
            assumed_date: null,
            counted: false,
          },
        ],
      }),
    );

    renderPanel();

    const table = await screen.findByRole('table');
    expect(table.textContent).toContain('Not counted');
    expect(table.textContent).not.toContain('overdue 241');
  });

  it('says nothing about overdue when the arrival is still ahead', async () => {
    getStockDetail.mockResolvedValue(
      captainsPosition({
        incoming: [
          {
            spo_number: 'SPO-2026/09-0001',
            supplier_name: 'FOSHAN WORKS',
            expected_date: '2026-09-12',
            spo_qty: '500',
            overdue_days: 0,
          },
        ],
      }),
    );

    renderPanel();

    const table = await screen.findByRole('table');
    expect(table.textContent).not.toContain('overdue');
  });

  it('lists every document behind the position, typed', async () => {
    getStockDetail.mockResolvedValue(
      captainsPosition({
        incoming: [
          {
            spo_number: '202601-S0003',
            supplier_name: 'FOSHAN WORKS',
            expected_date: '2026-09-12',
            spo_qty: '500',
          },
        ],
      }),
    );

    renderPanel();

    const table = await screen.findByRole('table');
    const rows = table.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(3);
    expect(table.textContent).toContain('SO391698');
    expect(table.textContent).toContain('202601-S0003');
    // The doc type column is what lets a reader see why an SPO adds where an SO subtracts.
    expect(within(table).getAllByText('S/O').length).toBe(2);
    expect(within(table).getAllByText('SPO').length).toBe(1);
  });

  it('totals the documents so the table adds up to its own header', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();

    const table = await screen.findByRole('table');
    const footer = [...(table.querySelector('tfoot')?.querySelectorAll('td') ?? [])].map(
      (cell) => cell.textContent ?? '',
    );
    expect(footer).toContain('Total');
    // 47000 + 9, which is the SO qty in the header.
    expect(footer).toContain('47009');
  });

  it('links a sales order the same way every other listing does', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();

    expect(await screen.findByRole('link', { name: 'SO391698' })).toHaveAttribute(
      'href',
      '/scm/sales-orders/so-a',
    );
  });

  /**
   * R5, 27 August 2026: no `#` rank and no queue state in this list. The rank is the queue
   * screen's question; here it competed with the one this list answers, which is what else is
   * claiming the stock and when. What stays is the tag on the line the drawer was opened for.
   */
  it('tags the line the drawer was opened for, and carries no rank or state column', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();

    const table = await screen.findByRole('table');
    expect(within(table).queryByText('Rank')).not.toBeInTheDocument();
    expect(within(table).queryByText('State')).not.toBeInTheDocument();
    expect(within(table).queryByText('Covered')).not.toBeInTheDocument();
    expect(screen.getByTestId('stock-document-this-line')).toBeInTheDocument();
    expect(screen.getAllByTestId('stock-document-this-line')).toHaveLength(1);
  });

  /**
   * The live book tops out at 501 documents for one product at one location, and this now opens
   * INSIDE a row of the cell dialog. So the documents scroll in a region of their own rather
   * than growing the dialog until nothing else is reachable.
   */
  it('scrolls inside its own container', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();
    await screen.findByRole('table');

    const panel = screen.getByTestId('stock-documents-panel');
    expect(panel.className).toContain('overflow-y-auto');
    expect(panel.className).toContain('max-h-');
  });

  it('says so when the detail cannot be loaded, rather than showing an empty table', async () => {
    getStockDetail.mockRejectedValue(new Error('Backend is down'));

    renderPanel();

    expect(await screen.findByText('Backend is down')).toBeInTheDocument();
  });

  it('states an empty position rather than an empty grid', async () => {
    getStockDetail.mockResolvedValue(
      captainsPosition({
        sales_orders: [],
        incoming: [],
        so_qty: '0',
        spo_qty: '0',
        available_qty: '478',
      }),
    );

    renderPanel();

    expect(await screen.findByText('Nothing is claiming this stock')).toBeInTheDocument();
  });

  it('says it is loading rather than showing a position it does not have yet', () => {
    getStockDetail.mockReturnValue(new Promise(() => {}));

    renderPanel();

    expect(screen.getByTestId('stock-documents-loading')).toBeInTheDocument();
  });
});

/**
 * The GROUP reading (captain, 30 August 2026).
 *
 * The board proposed "use own location - 60 from BRW-IB" beside an Available of -24,186, and
 * the two could not be reconciled on screen: the ladder's first step draws the whole ownership
 * group's pile at the line's own date, and Available is the bin's whole undated book. So the
 * subtotal row opens a drill over the SET, walked in the order the engine reads the dates,
 * with what is left of the pile after each document.
 */
describe('StockDocumentsPanel: the group reading', () => {
  /** Two bins of one group, a claim ahead of us, ours, and one behind. */
  function groupPosition(): StockDetail {
    return {
      product_id: 'prod-1',
      item_code: 'B2155-NL-BLUE',
      warehouse_id: null,
      location: null,
      group: 'IB',
      bins: [
        { warehouse_id: 'wh-brw-ib', location: 'BRW-IB', qty_on_hand: '100' },
        { warehouse_id: 'wh-mwh-ib', location: 'MWH-IB', qty_on_hand: '20' },
        { warehouse_id: 'wh-dc1-ib', location: 'DC1-IB', qty_on_hand: '0' },
      ],
      qty_on_hand: '120',
      so_qty: '150',
      spo_qty: '30',
      available_qty: '0',
      qty_reserved: '0',
      qty_held_by_decisions: '0',
      qty_free: '120',
      sales_orders: [
        {
          sales_order_id: 'so-late',
          so_number: 'SO999999',
          customer_name: 'LATE CUSTOMER',
          location: 'BRW-IB',
          doc_date: '2026-02-01',
          delivery_date: '2026-12-01',
          so_qty: '90',
          line_id: 'line-z',
          is_this_line: false,
        },
        {
          sales_order_id: 'so-a',
          so_number: 'SO381895',
          customer_name: 'OIB CONSTRUCTION SDN BHD',
          location: 'BRW-IB',
          doc_date: '2026-01-05',
          delivery_date: '2026-08-24',
          so_qty: '30',
          line_id: 'line-a',
          is_this_line: true,
        },
        {
          sales_order_id: 'so-early',
          so_number: 'SO111111',
          customer_name: 'EARLY CUSTOMER',
          location: 'MWH-IB',
          doc_date: '2026-01-02',
          delivery_date: '2026-08-01',
          so_qty: '30',
          line_id: 'line-b',
          is_this_line: false,
        },
      ],
      incoming: [
        {
          spo_number: 'SPO-2026/09-0001',
          supplier_name: 'FOSHAN WORKS',
          location: 'BRW-IB',
          expected_date: '2026-09-15',
          spo_qty: '30',
        },
      ],
    };
  }

  function rowsOf(): string[][] {
    return [...screen.getByRole('table').querySelectorAll('tbody tr')].map((row) =>
      [...row.querySelectorAll('td')].map((cell) => cell.textContent ?? ''),
    );
  }

  beforeEach(() => {
    // jsdom has no layout, so it implements no scrolling. The button's job is to call it.
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('asks for the SET, never for a bin', async () => {
    getStockDetail.mockResolvedValue(groupPosition());

    renderPanel('IB');

    await waitFor(() =>
      expect(getStockDetail).toHaveBeenCalledWith('prod-1', null, ['line-a'], 'IB'),
    );
  });

  it('walks the pile in the order the engine reads the dates, and states what is left', async () => {
    getStockDetail.mockResolvedValue(groupPosition());

    renderPanel('IB');
    await screen.findByRole('table');

    // On hand opens the walk (it is held now), then 1 Aug, then our own 24 Aug, then the
    // SPO arriving 15 Sep, then the 1 Dec claim behind us. A bin holding nothing states no
    // opening row - there is no pile to open on.
    // Document, bin, balance after: an On hand row has no document, and the Bin column is
    // what says which pile it opened. There is no Doc date column on this reading, so Bin
    // is the sixth cell.
    const documents = rowsOf().map((cells) => [cells[1], cells[5], cells[7]]);
    expect(documents).toEqual([
      ['-', 'BRW-IB', '100'],
      ['-', 'MWH-IB', '120'],
      ['SO111111', 'MWH-IB', '90'],
      ['SO381895This line', 'BRW-IB', '60'],
      ['SPO-2026/09-0001', 'BRW-IB', '90'],
      ['SO999999', 'BRW-IB', '0'],
    ]);
  });

  it('colours a balance the pile cannot meet, and leaves a positive one plain', async () => {
    getStockDetail.mockResolvedValue({
      ...groupPosition(),
      sales_orders: [
        {
          sales_order_id: 'so-a',
          so_number: 'SO381895',
          customer_name: 'OIB CONSTRUCTION SDN BHD',
          location: 'BRW-IB',
          doc_date: '2026-01-05',
          delivery_date: '2026-08-24',
          so_qty: '500',
          line_id: 'line-a',
          is_this_line: true,
        },
      ],
      incoming: [],
    });

    renderPanel('IB');
    await screen.findByRole('table');

    const opening = screen.getByTestId('stock-balance-on-hand-wh-brw-ib');
    expect(opening.className).not.toContain('text-destructive');
    const short = screen.getByTestId('stock-balance-so-0-so-a');
    expect(short.textContent).toBe('-380');
    expect(short.className).toContain('text-destructive');
  });

  // NO LOCAL "My line" BUTTON HERE ANYMORE (retired, review round S3): it duplicated the
  // sticky toolbar's own "My line" (`BoardCellBreakdownDialog`), which already reaches this
  // exact row through `jumpTarget` and lands it WITH the flash this local button never had -
  // see `StockDocumentsPanel: the S3 badges, search and jump` below for that jump's own
  // coverage. What is still this component's own job is marking the row in the first place.
  it('marks our own line', async () => {
    getStockDetail.mockResolvedValue(groupPosition());

    renderPanel('IB');
    const mine = await screen.findByTestId('stock-document-this-line');
    // The board's own row emphasis, so the eye lands on it in a list of other people's
    // documents.
    expect(mine.closest('tr')?.textContent).toContain('SO381895');
    expect(screen.getByText('SO381895').className).toContain('font-semibold');
  });

  it('marks no row when the asker has no row in this set', async () => {
    getStockDetail.mockResolvedValue({
      ...groupPosition(),
      sales_orders: groupPosition().sales_orders.map((order) => ({
        ...order,
        is_this_line: false,
      })),
    });

    renderPanel('IB');
    await screen.findByRole('table');

    expect(screen.queryByTestId('stock-document-this-line')).not.toBeInTheDocument();
  });

  it('subtracts a hold taken by a line booked outside the set (R40)', async () => {
    // Cross-group stock moves only as a PINNED hold, and such a hold is in no sales-order row
    // of this group: without it the walk would count a pile nobody can draw on. 25 of the 35
    // confirmed holds on the 30 August dev copy are cross-group.
    getStockDetail.mockResolvedValue({
      ...groupPosition(),
      sales_orders: [],
      incoming: [],
      holds: [
        {
          so_number: 'SO404352',
          location: 'BRW-IB',
          required_date: '2026-06-29',
          qty: '6',
        },
      ],
    });

    renderPanel('IB');
    await screen.findByRole('table');

    const documents = rowsOf().map((cells) => [cells[0], cells[1], cells[cells.length - 1]]);
    expect(documents).toEqual([
      // The hold is dated before either bin's stock is opened on, and it still comes after
      // them: stock is held NOW, and the pile has to exist before anything is taken from it.
      ['On hand', '-', '100'],
      ['On hand', '-', '120'],
      ['Hold', 'SO404352', '114'],
    ]);
  });

  it('says which bin each document sits at, which the per-bin reading never has to', async () => {
    getStockDetail.mockResolvedValue(groupPosition());

    renderPanel('IB');
    const table = await screen.findByRole('table');

    expect(within(table).getByText('Bin')).toBeInTheDocument();
    expect(within(table).getAllByText('MWH-IB').length).toBeGreaterThan(0);
  });

  it('carries no balance and no bin on the per-bin reading', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();
    const table = await screen.findByRole('table');

    expect(within(table).queryByText('Balance after')).not.toBeInTheDocument();
    expect(within(table).queryByText('Bin')).not.toBeInTheDocument();
  });
});

/**
 * S3 (PLAN-scm-planning-feedback-31aug): the "Donor" and "This document" badges (AC-3.3/3.4),
 * the search (AC-3.5) and the jump flash (AC-3.1/3.11).
 */
describe('StockDocumentsPanel: the site pool ledger (R-K, AC-2.6b)', () => {
  /**
   * The five-pool SET, which is the one section whose running column is not the raw pile:
   * it reads `Available for Project` - the share of each balance a project line may take,
   * capped by the five-pool net - so the ledger and the walk quote one number.
   */
  function poolsPosition(): StockDetail {
    return {
      product_id: 'prod-1',
      item_code: 'SRTWCX8840-S-RL',
      warehouse_id: null,
      location: null,
      group: 'pools',
      bins: [{ warehouse_id: 'wh-brw', location: 'BRW', qty_on_hand: '102' }],
      qty_on_hand: '102',
      so_qty: '1',
      spo_qty: '510',
      available_qty: '611',
      qty_reserved: '0',
      qty_held_by_decisions: '0',
      qty_free: '102',
      five_pool_net: '900',
      pool_share_pct: 50,
      sales_orders: [
        {
          sales_order_id: 'so-dealer',
          so_number: 'SO400001',
          customer_name: 'A DEALER',
          location: 'BRW',
          doc_date: '2026-01-05',
          delivery_date: '2026-09-05',
          so_qty: '1',
          line_id: 'line-d',
          is_this_line: false,
        },
      ],
      incoming: [
        {
          spo_number: 'SPO-2026/09-0001',
          supplier_name: 'FOSHAN WORKS',
          location: 'BRW',
          expected_date: '2026-09-20',
          spo_qty: '510',
        },
      ],
    };
  }

  function balancesOf(): (string | null)[] {
    return [
      ...document.querySelectorAll('[data-testid^="stock-balance-"]'),
    ].map((cell) => cell.textContent);
  }

  it('heads the running column Available for Project and shares every balance', async () => {
    getStockDetail.mockResolvedValue(poolsPosition());

    renderPanel('pools');
    await screen.findByRole('table');

    expect(screen.getByText('Available for Project')).toBeTruthy();
    // 102 on hand -> 51, less the 1-unit dealer order -> 50, plus the 510 SPO -> 305.
    // The share is applied to the BALANCE the walk landed on, never to the row's own qty.
    expect(balancesOf()).toEqual(['51', '50', '305']);
  });

  it('caps every shared balance by the five-pool net, so the ledger cannot promise past the pile', async () => {
    getStockDetail.mockResolvedValue({ ...poolsPosition(), five_pool_net: '52' });

    renderPanel('pools');
    await screen.findByRole('table');

    // R-D: the pool's own free pile says WHERE, the net says HOW MUCH. 305 is what the
    // share alone would read and 52 is what the five pools actually net between them.
    expect(balancesOf()).toEqual(['51', '50', '52']);
  });

  /**
   * D9 (captain, 3 Sep, SRTWB241's site pool subtotal ledger). The Total row's Quantity used
   * to sum only the S/O rows - on hand 49 + 586 + 20, S/O 1, SPO 113 + 4 read "1" beside a
   * closing Available for Project of 385. The rule: Total Quantity is the SIGNED NET of every
   * row listed (on hand and SPO add, S/O and Hold subtract) - the same arithmetic that
   * produces the last running value, so it reads 771 here and the running column's own total
   * stays the last running value (385), unchanged.
   */
  it('totals Quantity as the signed net of every row, not only the S/O rows', async () => {
    getStockDetail.mockResolvedValue({
      ...poolsPosition(),
      bins: [
        { warehouse_id: 'wh-1', location: 'BRW', qty_on_hand: '49' },
        { warehouse_id: 'wh-2', location: 'BRW', qty_on_hand: '586' },
        { warehouse_id: 'wh-3', location: 'BRW', qty_on_hand: '20' },
      ],
      sales_orders: [
        {
          sales_order_id: 'so-dealer',
          so_number: 'SO400001',
          customer_name: 'A DEALER',
          location: 'BRW',
          doc_date: '2026-01-05',
          delivery_date: '2026-09-05',
          so_qty: '1',
          line_id: 'line-d',
          is_this_line: false,
        },
      ],
      incoming: [
        {
          spo_number: 'SPO-2026/09-0001',
          supplier_name: 'FOSHAN WORKS',
          location: 'BRW',
          expected_date: '2026-09-20',
          spo_qty: '113',
        },
        {
          spo_number: 'SPO-2026/09-0002',
          supplier_name: 'FOSHAN WORKS',
          location: 'BRW',
          expected_date: '2026-09-21',
          spo_qty: '4',
        },
      ],
      five_pool_net: '400',
      pool_share_pct: 50,
    });

    renderPanel('pools');

    const table = await screen.findByRole('table');
    const footer = [...(table.querySelector('tfoot')?.querySelectorAll('td') ?? [])].map(
      (cell) => cell.textContent ?? '',
    );
    // 49 + 586 + 20 (on hand) + 113 + 4 (SPO) - 1 (S/O) = 771, never the "1" a sum of the
    // S/O rows alone used to print.
    expect(footer).toContain('771');
    // The running column's own total is untouched: the last running value, shared and capped
    // exactly as `balancesOf` already proves for this section.
    expect(footer).toContain('385');
  });
});

describe('StockDocumentsPanel: the S3 badges, search and jump', () => {
  it('AC-3.3: badges the donor row by its core line id, and leaves other rows plain', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel(undefined, { donor: [{ soNumber: 'SO391698', lineId: 'line-a' }] });

    const table = await screen.findByRole('table');
    // `line-a` is the FIRST sales order in `captainsPosition` (SO391698, also "This line" -
    // AC-3.3 states the two badges may coexist on one row).
    expect(within(table).getByTestId('stock-document-donor')).toBeInTheDocument();
    expect(within(table).getByTestId('stock-document-this-line')).toBeInTheDocument();
  });

  it('AC-3.3: falls back to the SO number when no core line id was named', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel(undefined, { donor: [{ soNumber: 'SO324265' }] });

    const table = await screen.findByRole('table');
    expect(within(table).getByTestId('stock-document-donor').closest('tr')?.textContent).toContain(
      'SO324265',
    );
  });

  /**
   * AC-3.3/3.13: an on-hand borrow's donor jump, with real assertions (scroll + flash), not
   * only the badge - the badge-only tests above (and `CellStockTable`'s own "jumpToDonor
   * opens the SECTION" tests, which deliberately leave `getStockDetail` unresolved) never
   * exercised the actual landing. `SO324265` (line-b) is chosen over `SO391698` (line-a)
   * deliberately - line-a is ALSO "This line" in `captainsPosition`, so a donor jump that
   * accidentally matched the wrong test id would still pass against it. AC-3.13 shares this
   * exact mechanism: a Borrow-incoming's donor is still an `S/O` row matched the same way,
   * whether or not that same source also carries a `supply_document` (asserted separately,
   * at the sentence level, in `BoardCellBreakdownDialog.test.tsx`'s "AC-3.4/3.13" case).
   */
  it('AC-3.3/3.13: a donor jump scrolls to and flashes the donor row, distinct from "This line"', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Element.prototype.scrollIntoView = vi.fn();
    getStockDetail.mockResolvedValue(captainsPosition());

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <StockDocumentsPanel
          productId="prod-1"
          warehouseId="wh-1"
          lineIds={['line-a']}
          donor={[{ soNumber: 'SO324265', lineId: 'line-b' }]}
          jumpTarget={{ kind: 'donor', nonce: 1 }}
        />
      </QueryClientProvider>,
    );

    const donorRow = (await screen.findByTestId('stock-document-donor')).closest('tr');
    expect(donorRow?.textContent).toContain('SO324265');
    expect(donorRow?.className).toContain('jump-flash');
    expect(donorRow?.scrollIntoView).toHaveBeenCalled();
    // The OTHER row ("This line", SO391698) never flashes - the jump targets its own kind.
    const thisLineRow = screen.getByTestId('stock-document-this-line').closest('tr');
    expect(thisLineRow?.className).not.toContain('jump-flash');

    vi.useRealTimers();
  });

  it('AC-3.4: badges the SPO row, normalising the "SPO " prefix either side', async () => {
    getStockDetail.mockResolvedValue(
      captainsPosition({
        incoming: [
          {
            spo_number: '202609-0041',
            supplier_name: 'FOSHAN WORKS',
            expected_date: '2026-10-20',
            spo_qty: '30',
          },
        ],
      }),
    );

    renderPanel(undefined, {
      documentInfo: { spoNumber: 'SPO 202609-0041' },
    });

    const table = await screen.findByRole('table');
    expect(within(table).getByTestId('stock-document-this-document')).toBeInTheDocument();
  });

  /**
   * AC-3.4: the document jump, with real assertions - the badge-only test above (and
   * `CellStockTable`'s "jumpToDocument opens the SECTION" test, which deliberately leaves
   * `getStockDetail` unresolved) never proved the row actually lands and highlights.
   */
  it('AC-3.4: a document jump scrolls to and flashes the SPO row', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Element.prototype.scrollIntoView = vi.fn();
    getStockDetail.mockResolvedValue(
      captainsPosition({
        incoming: [
          {
            spo_number: '202609-0041',
            supplier_name: 'FOSHAN WORKS',
            expected_date: '2026-10-20',
            spo_qty: '30',
          },
        ],
      }),
    );

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <StockDocumentsPanel
          productId="prod-1"
          warehouseId="wh-1"
          lineIds={['line-a']}
          documentInfo={{ spoNumber: 'SPO 202609-0041' }}
          jumpTarget={{ kind: 'document', nonce: 1 }}
        />
      </QueryClientProvider>,
    );

    const documentRow = (
      await screen.findByTestId('stock-document-this-document')
    ).closest('tr');
    expect(documentRow?.textContent).toContain('202609-0041');
    expect(documentRow?.className).toContain('jump-flash');
    expect(documentRow?.scrollIntoView).toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('AC-3.5: search filters by SO number, customer or agent, case-insensitively', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel(undefined, { filterText: 'masuka' });

    const table = await screen.findByRole('table');
    expect(within(table).queryByText('SO391698')).not.toBeInTheDocument();
    expect(within(table).getByText('SO324265')).toBeInTheDocument();
  });

  it('AC-3.5: an explicit empty state on a miss, distinct from "nothing is claiming this stock"', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel(undefined, { filterText: 'no such order anywhere' });

    expect(await screen.findByTestId('stock-documents-search-empty')).toBeInTheDocument();
    expect(screen.getByText('No document matches your search')).toBeInTheDocument();
  });

  it('AC-3.5: clearing the search restores the full table', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const props = { productId: 'prod-1', warehouseId: 'wh-1', lineIds: ['line-a'] };

    const { rerender } = render(
      <QueryClientProvider client={client}>
        <StockDocumentsPanel {...props} filterText="masuka" />
      </QueryClientProvider>,
    );
    await screen.findByRole('table');
    expect(screen.queryByText('SO391698')).not.toBeInTheDocument();

    rerender(
      <QueryClientProvider client={client}>
        <StockDocumentsPanel {...props} filterText="" />
      </QueryClientProvider>,
    );

    expect(screen.getByText('SO391698')).toBeInTheDocument();
    expect(screen.getByText('SO324265')).toBeInTheDocument();
  });

  it('AC-3.1/3.3/3.4: a jump scrolls to and flashes the matching row, then the flash clears', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Element.prototype.scrollIntoView = vi.fn();
    getStockDetail.mockResolvedValue(captainsPosition());

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <StockDocumentsPanel
          productId="prod-1"
          warehouseId="wh-1"
          lineIds={['line-a']}
          jumpTarget={null}
        />
      </QueryClientProvider>,
    );
    await screen.findByRole('table');

    rerender(
      <QueryClientProvider client={client}>
        <StockDocumentsPanel
          productId="prod-1"
          warehouseId="wh-1"
          lineIds={['line-a']}
          jumpTarget={{ kind: 'this-line', nonce: 1 }}
        />
      </QueryClientProvider>,
    );

    const row = screen.getByTestId('stock-document-this-line').closest('tr');
    expect(row?.className).toContain('jump-flash');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();

    // The pulse fades - never a persistent second selection colour (AC-3.11).
    vi.advanceTimersByTime(1600);
    expect(row?.className).not.toContain('jump-flash');

    vi.useRealTimers();
  });

  /**
   * AC-3.1 bug-fix round (S3, 31 Aug 2026 browser evidence): the auto-land on a cell's OWN
   * mount fired against ZERO rows in the DOM even though the stock query had already
   * resolved with the matching line inside it. The test above never caught it, because it
   * always let the table paint FIRST (`await screen.findByRole('table')`) and only THEN
   * flipped `jumpTarget` - so the row's node already existed the moment the jump effect ran,
   * which is the one case that never needed a fix.
   *
   * The real gap is the shared grid's OWN second async gate - `data-grid.tsx` combines
   * `isLoading: props.isLoading || isColumnPreferencesLoading` - so the stock query can
   * resolve (`detail.isLoading` false, `visibleRows` populated) a full render BEFORE the
   * grid's column-preference fetch clears and the `<tr>` actually lands. `columnPrefsGate`
   * (this file's own stateful mock of that hook, module doc above) reproduces exactly that
   * extra tick: `jumpTarget` is set from the FIRST render, the stock query resolves
   * immediately, and the grid still holds its loading state for `columnPrefsGate.delayMs`
   * after that.
   */
  it('AC-3.1: lands the jump even when the grid paints the row a tick after jumpTarget is already set', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Element.prototype.scrollIntoView = vi.fn();
    getStockDetail.mockResolvedValue(captainsPosition());
    columnPrefsGate.delayMs = 20;

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <StockDocumentsPanel
          productId="prod-1"
          warehouseId="wh-1"
          lineIds={['line-a']}
          jumpTarget={{ kind: 'this-line', nonce: 1 }}
        />
      </QueryClientProvider>,
    );

    // The exact defect: the stock detail is back, but the grid has not painted a row yet.
    await waitFor(() => expect(getStockDetail).toHaveBeenCalled());
    expect(screen.queryByTestId('stock-document-this-line')).not.toBeInTheDocument();

    // The grid's own gate clears - nothing re-fires `jumpTarget` or `visibleRows` from here.
    await act(async () => {
      vi.advanceTimersByTime(20);
    });

    const row = await screen.findByTestId('stock-document-this-line');
    expect(row.closest('tr')?.className).toContain('jump-flash');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();

    vi.useRealTimers();
  });
});
