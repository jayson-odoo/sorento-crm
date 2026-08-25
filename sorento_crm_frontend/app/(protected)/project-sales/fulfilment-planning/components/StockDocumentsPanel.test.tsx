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
import { render, screen, waitFor, within } from '@testing-library/react';
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
        is_covered: false,
      },
      {
        sales_order_id: 'so-b',
        so_number: 'SO324265',
        customer_name: 'MASUKA BINA SDN BHD',
        doc_date: '2025-11-02',
        delivery_date: '2026-10-01',
        so_qty: '9',
        is_covered: true,
      },
    ],
    incoming: [],
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <StockDocumentsPanel
        productId="prod-1"
        warehouseId="wh-1"
        itemCode="B2155-NL-BLUE"
        locationCode="BRW-BB"
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

    await waitFor(() => expect(getStockDetail).toHaveBeenCalledWith('prod-1', 'wh-1'));
  });

  it('does not head the panel with the arithmetic: the row it expands from already says it', async () => {
    // Item 7 / AC-A4. "TPE-9204 . BRW  On hand 241 - SO 3334 + SPO 0 = Available -3093" sat
    // directly under the location row that carries all four of those figures, and the
    // captain's verdict was "redundant. Remove."
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();

    await screen.findByText('Documents');
    expect(screen.queryByTestId('stock-detail-arithmetic')).not.toBeInTheDocument();
    expect(screen.queryByText(/On hand 478 - SO 47009/)).not.toBeInTheDocument();
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

  it('marks an order already covered by a decision, because it is not competing any more', async () => {
    getStockDetail.mockResolvedValue(captainsPosition());

    renderPanel();

    await screen.findByRole('table');
    expect(screen.getByText('Covered')).toBeInTheDocument();
  });

  /**
   * The captain, reading the list sorted by delivery date: "is this sorted by the rank also? or
   * just delivery date, we should have a rank column and be able to sort by that (default sort
   * by that), along with the reason tooltip like How this rank was calculated". The rank is the
   * pile queue's own; a covered line is not in the queue and says so instead of going blank.
   */
  it('shows each document\'s rank in the queue with the calculation behind it, and names an unqueued line', async () => {
    getStockDetail.mockResolvedValue(
      captainsPosition({
        policy_name: 'Board preview',
        sales_orders: [
          {
            sales_order_id: 'so-a',
            so_number: 'SO391698',
            customer_name: 'OIB CONSTRUCTION SDN BHD',
            doc_date: '2026-01-05',
            delivery_date: '2026-09-04',
            so_qty: '47000',
            is_covered: false,
            line_id: 'line-a',
            rank_position: 1,
            rank_score: 1,
            rank_factors: [
              { key: 'need_by_date', weight: 3, value: 1, present: true, raw: '2026-09-04' },
            ],
          },
          {
            sales_order_id: 'so-b',
            so_number: 'SO324265',
            customer_name: 'MASUKA BINA SDN BHD',
            doc_date: '2025-11-02',
            delivery_date: '2026-10-01',
            so_qty: '9',
            is_covered: true,
            line_id: 'line-b',
            rank_position: null,
            rank_score: null,
            rank_factors: [],
          },
        ],
      }),
    );

    renderPanel();

    const table = await screen.findByRole('table');
    expect(within(table).getByText('Rank')).toBeInTheDocument();
    expect(within(table).getByText('#1')).toBeInTheDocument();
    expect(within(table).getByText('1.00')).toBeInTheDocument();
    expect(
      within(table).getByRole('button', { name: 'How this rank was calculated' }),
    ).toBeInTheDocument();
    expect(within(table).getByText('Not queued')).toBeInTheDocument();
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
