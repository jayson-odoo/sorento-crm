/**
 * Stock Status with Detail: what the four numbers on a location pill are made of.
 *
 * AutoCount shows the position and then the documents that produce it, and the captain reads it
 * there before coming here. So this mirrors that shape: a header line that IS the arithmetic
 * ("On hand 478 - SO 47,009 + SPO 0 = Available -46,531"), the documents beneath it, and a total
 * that adds back up to the header. A detail view whose total disagrees with its own header is
 * the one thing that would make somebody stop trusting the board.
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

import { StockDetailDialog } from './StockDetailDialog';
import type { StockDetail } from '../../_shared/types/fulfilmentPlanning.types';

/** The captain's own cell, as the live book reports it. */
function captainsCell(overrides: Partial<StockDetail> = {}): StockDetail {
  return {
    item_code: 'B2155-NL-BLUE',
    warehouse_code: 'BRW-BB',
    qty_on_hand: '478',
    so_qty: '47009',
    spo_qty: '0',
    available_qty: '-46531',
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

function renderDialog(onClose = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <StockDetailDialog
        productId="prod-1"
        warehouseId="wh-1"
        locationCode="BRW-BB"
        itemCode="B2155-NL-BLUE"
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('StockDetailDialog', () => {
  it('asks by IDS, because two products share the code B2155-NL-BLUE on the live book', async () => {
    getStockDetail.mockResolvedValue(captainsCell());

    renderDialog();

    await waitFor(() => expect(getStockDetail).toHaveBeenCalledWith('prod-1', 'wh-1'));
  });

  it('heads the dialog with the arithmetic itself', async () => {
    getStockDetail.mockResolvedValue(captainsCell());

    renderDialog();

    expect(
      await screen.findByText('On hand 478 - SO 47009 + SPO 0 = Available -46531'),
    ).toBeInTheDocument();
  });

  it('renders a negative available plainly, never clamped and never hidden', async () => {
    getStockDetail.mockResolvedValue(captainsCell());

    renderDialog();

    const header = await screen.findByTestId('stock-detail-arithmetic');
    expect(header.textContent).toContain('-46531');
    expect(header.textContent).not.toContain('Available 0');
  });

  it('lists every document behind the position, typed', async () => {
    getStockDetail.mockResolvedValue(
      captainsCell({
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

    renderDialog();

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
    getStockDetail.mockResolvedValue(captainsCell());

    renderDialog();

    const table = await screen.findByRole('table');
    const footer = [...(table.querySelector('tfoot')?.querySelectorAll('td') ?? [])].map(
      (cell) => cell.textContent ?? '',
    );
    expect(footer).toContain('Total');
    // 47000 + 9, which is the SO qty in the header.
    expect(footer).toContain('47009');
  });

  it('links a sales order the same way every other listing does', async () => {
    getStockDetail.mockResolvedValue(captainsCell());

    renderDialog();

    expect(await screen.findByRole('link', { name: 'SO391698' })).toHaveAttribute(
      'href',
      '/scm/sales-orders/so-a',
    );
  });

  it('marks an order already covered by a decision, because it is not competing any more', async () => {
    getStockDetail.mockResolvedValue(captainsCell());

    renderDialog();

    await screen.findByRole('table');
    expect(screen.getByText('Covered')).toBeInTheDocument();
  });

  it('scrolls inside its own container, with the X outside the scroll region', async () => {
    getStockDetail.mockResolvedValue(captainsCell());

    renderDialog();
    await screen.findByRole('table');

    const body = screen.getByTestId('stock-detail-body');
    expect(body.className).toContain('overflow-y-auto');
    expect(body.className).toContain('min-h-0');
    expect(screen.getAllByRole('button', { name: 'Close' })).toHaveLength(1);
  });

  it('says so when the detail cannot be loaded, rather than showing an empty table', async () => {
    getStockDetail.mockRejectedValue(new Error('Backend is down'));

    renderDialog();

    expect(await screen.findByText('Backend is down')).toBeInTheDocument();
  });

  it('states an empty position rather than an empty grid', async () => {
    getStockDetail.mockResolvedValue(
      captainsCell({ sales_orders: [], incoming: [], so_qty: '0', spo_qty: '0', available_qty: '478' }),
    );

    renderDialog();

    expect(await screen.findByText('Nothing is claiming this stock')).toBeInTheDocument();
  });
});
