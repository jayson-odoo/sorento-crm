/**
 * STOCK-STATUS round 6 (UAC AC-34): given AutoCount's read, a location's documents foot to its
 * row. Only the S/O lines AutoCount counts are listed, at AutoCount's outstanding qty, and the
 * location's open POs are added (owner OK of mock v6, 18 Oct 07:56).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
const getStockDetail = vi.fn();
vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: (...args: unknown[]) => getStockDetail(...args),
}));

import { StockDocumentsPanel } from './StockDocumentsPanel';
import type { StockDetail } from '../../_shared/types/fulfilmentPlanning.types';
import type { StockStatus } from '@/components/stock-status/stockStatus.types';

const DETAIL: StockDetail = {
  product_id: 'prod-1',
  item_code: 'SRTWB1515',
  warehouse_id: 'wh-BB',
  location: 'BRW-BB',
  qty_on_hand: '0',
  so_qty: '480',
  spo_qty: '50',
  available_qty: '-430',
  qty_reserved: '0',
  qty_held_by_decisions: '0',
  qty_free: '0',
  sales_orders: [
    { sales_order_id: 'so-1', so_number: 'SO421741', customer_name: 'HAANAFLO SDN BHD', so_qty: '468', line_id: 'line-1', delivery_date: '2026-12-15' },
    // Transferable F in AutoCount: not counted there, so not listed here
    { sales_order_id: 'so-2', so_number: 'SO421645', customer_name: 'MENTARI BERSERI', so_qty: '12', line_id: 'line-2', delivery_date: '2026-12-31' },
  ],
  incoming: [{ spo_number: 'SPO-2026/10-0024', spo_qty: '50', supplier_name: 'CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD', expected_date: '2026-10-17' }],
} as unknown as StockDetail;

const STATUS = {
  product_id: 'prod-1',
  locations: [],
  sales_orders: [
    { line_id: 'line-1', sales_order_id: 'so-1', so_number: 'SO421741', qty: 442, warehouse_id: 'wh-BB' },
    // Another location's line: never listed under this one
    { line_id: 'line-9', sales_order_id: 'so-9', so_number: 'SO422380', qty: 2, warehouse_id: 'wh-BRW' },
  ],
  purchase_orders: [
    { line_id: 'pol-1', purchase_order_id: 'po-1', po_number: '202608-S0006', supplier_code: '400-C030', supplier_name: 'CHAOZHOU CHAOAN FENGTANG DAFUYUAN CERAMIC FACTORY', issue_date: '2026-08-01', expected_date: '2026-10-28', qty: 674, warehouse_id: 'wh-BB' },
    { line_id: 'pol-2', purchase_order_id: 'po-2', po_number: '202610-S0011', supplier_code: '400-C030', supplier_name: 'CHAOZHOU CHAOAN FENGTANG DAFUYUAN CERAMIC FACTORY', issue_date: '2026-10-01', expected_date: '2026-10-05', qty: 318, warehouse_id: 'wh-BRW' },
  ],
  spos: [],
} as unknown as StockStatus;

function renderPanel(autoCount?: StockStatus) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <StockDocumentsPanel productId="prod-1" warehouseId="wh-BB" lineIds={['line-1']} autoCount={autoCount} />
    </QueryClientProvider>,
  );
}

describe('StockDocumentsPanel with the AutoCount read', () => {
  it("lists only AutoCount's S/O lines, at AutoCount's outstanding qty", async () => {
    getStockDetail.mockResolvedValue(DETAIL);
    renderPanel(STATUS);
    const so = await screen.findByRole('link', { name: 'SO421741' });
    expect(within(so.closest('tr') as HTMLElement).getByText('442')).toBeInTheDocument();
    expect(screen.queryByText('SO421645')).not.toBeInTheDocument();
    expect(screen.queryByText('SO422380')).not.toBeInTheDocument();
  });

  it('keeps the asking line listed at 0 when AutoCount no longer counts it (delivered)', async () => {
    getStockDetail.mockResolvedValue({
      ...DETAIL,
      sales_orders: [
        ...DETAIL.sales_orders,
        { sales_order_id: 'so-3', so_number: 'SO400001', customer_name: 'DELIVERED SDN BHD', so_qty: '0', line_id: 'line-3', is_this_line: true, fulfilled_qty: '4' },
      ],
    });
    renderPanel(STATUS);
    const mine = await screen.findByRole('link', { name: 'SO400001' });
    expect(within(mine.closest('tr') as HTMLElement).getByText('This line')).toBeInTheDocument();
  });

  it("lists AutoCount's SPO lines at the location, and no holds", async () => {
    getStockDetail.mockResolvedValue(DETAIL);
    renderPanel({
      ...STATUS,
      spos: [
        { allocation_id: 'a-1', spo_number: 'SPO-2026/10-0099', spo_line_number: 1, supplier_code: null, supplier_name: 'ACME', issue_date: null, arrival_date: '2026-10-30', container_number: null, qty: 7, warehouse_id: 'wh-BB' },
        { allocation_id: 'a-2', spo_number: 'SPO-2026/10-0100', spo_line_number: 1, supplier_code: null, supplier_name: 'ACME', issue_date: null, arrival_date: '2026-10-30', container_number: null, qty: 3, warehouse_id: 'wh-BRW' },
      ],
    } as unknown as StockStatus);
    expect(await screen.findByText('SPO-2026/10-0099')).toBeInTheDocument();
    expect(screen.queryByText('SPO-2026/10-0024')).not.toBeInTheDocument();
    expect(screen.queryByText('SPO-2026/10-0100')).not.toBeInTheDocument();
  });

  it("adds the location's open POs, by name, linking to the purchase order", async () => {
    getStockDetail.mockResolvedValue(DETAIL);
    renderPanel(STATUS);
    const po = await screen.findByRole('link', { name: '202608-S0006' });
    expect(po).toHaveAttribute('href', '/scm/purchase-orders/po-1');
    const tr = po.closest('tr') as HTMLElement;
    expect(within(tr).getByText('PO')).toBeInTheDocument();
    expect(within(tr).getByText('CHAOZHOU CHAOAN FENGTANG DAFUYUAN CERAMIC FACTORY')).toBeInTheDocument();
    expect(within(tr).getByText('674')).toBeInTheDocument();
    expect(screen.queryByText('202610-S0011')).not.toBeInTheDocument(); // another location's PO
  });

  it("foots the S/O total to AutoCount's SO qty", async () => {
    getStockDetail.mockResolvedValue(DETAIL);
    renderPanel(STATUS);
    await screen.findByRole('link', { name: 'SO421741' });
    const table = screen.getByRole('link', { name: 'SO421741' }).closest('table') as HTMLElement;
    await waitFor(() => {
      const footer = [...(table.querySelector('tfoot')?.querySelectorAll('td') ?? [])].map((td) => td.textContent ?? '');
      expect(footer).toContain('442');
    });
  });

  it("keeps today's documents without the AutoCount read", async () => {
    getStockDetail.mockResolvedValue(DETAIL);
    renderPanel();
    expect(await screen.findByText('SO421645')).toBeInTheDocument();
    expect(screen.queryByText('202608-S0006')).not.toBeInTheDocument();
  });
});
