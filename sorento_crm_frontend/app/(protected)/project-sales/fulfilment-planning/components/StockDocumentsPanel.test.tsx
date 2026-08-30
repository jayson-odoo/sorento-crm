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
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
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

function renderPanel(group?: string) {
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
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
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

  it('marks our own line and jumps to it', async () => {
    getStockDetail.mockResolvedValue(groupPosition());

    renderPanel('IB');
    const mine = await screen.findByTestId('stock-document-this-line');
    // The board's own row emphasis, so the eye lands on it in a list of other people's
    // documents.
    expect(mine.closest('tr')?.textContent).toContain('SO381895');
    expect(screen.getByText('SO381895').className).toContain('font-semibold');

    fireEvent.click(screen.getByTestId('stock-documents-my-line'));

    expect(mine.closest('tr')?.scrollIntoView).toHaveBeenCalled();
  });

  it('offers no jump when the asker has no row in this set', async () => {
    getStockDetail.mockResolvedValue({
      ...groupPosition(),
      sales_orders: groupPosition().sales_orders.map((order) => ({
        ...order,
        is_this_line: false,
      })),
    });

    renderPanel('IB');
    await screen.findByRole('table');

    expect(screen.queryByTestId('stock-documents-my-line')).not.toBeInTheDocument();
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
