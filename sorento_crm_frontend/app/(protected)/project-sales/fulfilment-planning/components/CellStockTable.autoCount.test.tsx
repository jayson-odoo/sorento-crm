/**
 * STOCK-STATUS round 6 (owner OK of mock v6, 18 Oct 07:56; UAC AC-30 to AC-33): today's stock
 * table, no Where column ("rmb to drop where column in the ui"), AutoCount's figures when given
 * the AutoCount read, every location AutoCount holds, and one Incoming PL row under the Total.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: vi.fn(() => new Promise(() => {})),
}));

import { CellStockTable } from './CellStockTable';
import type { BoardCellLocation } from '../../_shared/types/fulfilmentPlanning.types';
import type { StockStatus } from '@/components/stock-status/stockStatus.types';

function row(location: string, extra: Partial<BoardCellLocation> = {}): BoardCellLocation {
  return {
    location,
    product_id: 'prod-1',
    warehouse_id: `wh-${location}`,
    qty: '0',
    qty_on_hand: '0',
    so_qty: '0',
    spo_qty: '0',
    available_qty: '0',
    po_open_qty: '0',
    ...extra,
  };
}

const TODAY: BoardCellLocation[] = [
  row('BRW-IB', { where: 'own', net_of: 'IB', qty_on_hand: '6', so_qty: '2156', spo_qty: '24', available_qty: '-2126', po_open_qty: '338', net: '-1986' }),
  row('MWH-IB', { where: 'group', net_of: 'IB', qty_on_hand: '140', available_qty: '140', net: '-1986' }),
];

const STATUS = {
  product_id: 'prod-1',
  item_code: 'SRTWB1515',
  locations: [
    { warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', warehouse_name: 'BRW-BB', is_active: true, on_hand: 0, so_qty: 7312, po_qty: 1734, spo_qty: 50, forecast: -5528 },
    { warehouse_id: 'wh-MWH-IB', warehouse_code: 'MWH-IB', warehouse_name: 'MWH-IB', is_active: true, on_hand: 140, so_qty: 0, po_qty: 0, spo_qty: 0, forecast: 140 },
    { warehouse_id: 'wh-BRW-IB', warehouse_code: 'BRW-IB', warehouse_name: 'BRW-IB', is_active: true, on_hand: 6, so_qty: 2158, po_qty: 338, spo_qty: 24, forecast: -1790 },
  ],
  totals: { on_hand: 146, so_qty: 9470, po_qty: 2072, spo_qty: 74, forecast: -7178, incoming_pl: 227, forecast_incl_pl: -6951 },
  incoming_pl: [
    { shipment_id: 'sh-1', shipment_number: 'PL-2610-001', container_number: 'SEKU5230843', eta: '2026-10-19', still_to_land: 118, on_spo: 0, counted: 118 },
    { shipment_id: 'sh-2', shipment_number: 'PL-2610-010', container_number: 'GAOU6617710', eta: '2026-10-20', still_to_land: 109, on_spo: 0, counted: 109 },
    { shipment_id: 'sh-3', shipment_number: 'PL-2609-040', container_number: 'SEKU1741573 (KUCHING)', eta: '2026-10-01', still_to_land: 50, on_spo: 50, counted: 0 },
  ],
  sales_orders: [],
  purchase_orders: [],
  spos: [],
} as unknown as StockStatus;

function renderTable(props: Partial<React.ComponentProps<typeof CellStockTable>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <CellStockTable locations={TODAY} {...props} />
    </QueryClientProvider>,
  );
}

const headers = () =>
  [...screen.getByRole('table').querySelectorAll('thead th')].map((cell) => cell.textContent ?? '');

describe('CellStockTable: round 6', () => {
  it('has no Where column, with or without the AutoCount read (AC-30)', () => {
    renderTable();
    expect(headers()).not.toContain('Where');
    expect(screen.queryByText('Own location')).not.toBeInTheDocument();
  });

  it("shows AutoCount's figures and every location AutoCount holds (AC-31, AC-32)", () => {
    renderTable({ autoCount: STATUS });
    expect(screen.getByTestId('stock-so-BRW-IB').textContent).toBe('2158');
    expect(screen.getByTestId('stock-available-BRW-IB').textContent).toBe('-2128');
    expect(screen.getByTestId('stock-so-BRW-BB').textContent).toBe('7312');
    expect(screen.getByTestId('stock-po-BRW-BB').textContent).toBe('1734');
    expect(screen.getByTestId('stock-subtotal-other_group')).toHaveTextContent('Other group subtotal');
    expect(screen.getByTestId('stock-total-on-hand').textContent).toBe('146');
    expect(screen.getByTestId('stock-total-so').textContent).toBe('9470');
    expect(screen.getByTestId('stock-total-po').textContent).toBe('2072');
    expect(screen.getByTestId('stock-total-spo').textContent).toBe('74');
  });

  it('carries one Incoming PL row under the Total that opens its packing lists (AC-33)', () => {
    renderTable({ autoCount: STATUS });
    const pl = screen.getByTestId('stock-incoming-pl');
    expect(within(pl).getByText('Incoming PL')).toBeInTheDocument();
    expect(within(pl).getByText('+227')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'PL-2610-001' })).not.toBeInTheDocument();
    fireEvent.click(within(pl).getByRole('button', { name: /incoming packing lists/i }));
    expect(screen.getByRole('link', { name: 'PL-2610-001' })).toHaveAttribute('href', '/procurement-management/packing-lists/sh-1');
    expect(screen.getByRole('link', { name: 'PL-2609-040' })).toBeInTheDocument();
  });

  it('has no Incoming PL row without the AutoCount read (a failed read keeps today)', () => {
    renderTable();
    expect(screen.queryByTestId('stock-incoming-pl')).not.toBeInTheDocument();
    expect(screen.getByTestId('stock-so-BRW-IB').textContent).toBe('2156');
  });

  it("keeps PO qty in the stock-only view (the quotation's table)", () => {
    renderTable({ autoCount: STATUS, stockOnly: true });
    expect(headers()).toEqual(['Location', 'On hand', 'SO qty', 'SPO qty', 'Available', 'PO qty']);
  });
});
