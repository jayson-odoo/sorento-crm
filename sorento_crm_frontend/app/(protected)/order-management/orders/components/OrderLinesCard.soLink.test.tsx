/**
 * DO-SO-LINK-SURFACE R1 - the SO column on the delivery order lines grid
 * (documentation/plans/scm/PLAN-do-so-link-surface-25oct.md, mock
 * documentation/mockups/DO-SO-LINK-SURFACE). A link to the SO when the CRM has it (with the
 * line no. only when AutoCount named the line), AutoCount's own number as plain text when it
 * does not, "-" for a direct DO.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({ usePathname: () => '/order-management/orders/o-1' }));
vi.mock('../hooks/useOrders', () => ({
  useBulkDeleteOrderLines: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateOrderLine: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('../services/orderService', () => ({ importDeliveryOrderDetail: vi.fn() }));
vi.mock('./OrderLineDeleteDialog', () => ({ __esModule: true, default: () => null }));

import OrderLinesCard from './OrderLinesCard';
import type { OrderLine } from '../types/order.types';

function line(id: string, code: string, extra: Partial<OrderLine>): OrderLine {
  return {
    id,
    order_id: 'o-1',
    product_id: `p-${id}`,
    warehouse_id: 'w-1',
    quantity: 1,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    product: { id: `p-${id}`, product_code: code, product_name: 'Item' },
    ...extra,
  } as OrderLine;
}

const LINES: OrderLine[] = [
  line('l-1', 'WESERP10B', {
    from_doc_no: 'SO419866',
    sales_order: { id: 'so-a', so_number: 'SO419866', line_no: 3 },
  }),
  line('l-2', 'C-FH14', {
    from_doc_no: 'SO419866',
    sales_order: { id: 'so-a', so_number: 'SO419866', line_no: null },
  }),
  line('l-3', 'BT012-CR', { from_doc_no: 'SO400001', sales_order: null }),
  line('l-4', 'SRTWB1515', { from_doc_no: null, sales_order: null }),
];

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <OrderLinesCard orderId="o-1" lines={LINES} readOnly />
    </QueryClientProvider>,
  );
}

function soCell(code: string) {
  const headers = screen.getAllByRole('columnheader');
  const index = headers.findIndex((h) => (h.textContent ?? '').trim() === 'SO');
  expect(index).toBeGreaterThanOrEqual(0);
  return rowOf(code).querySelectorAll('td')[index] as HTMLElement;
}

function rowOf(code: string) {
  return screen.getByText(new RegExp(`^${code} - `)).closest('tr') as HTMLElement;
}

describe('OrderLinesCard - SO column (DO-SO-LINK-SURFACE R1)', () => {
  it('has an SO header', () => {
    renderCard();
    expect(screen.getByText('SO')).toBeInTheDocument();
  });

  it('links an exact SO line to the SO, naming the line', () => {
    renderCard();
    const link = within(rowOf('WESERP10B')).getByRole('link', { name: /SO419866 · line 3/ });
    expect(link).toHaveAttribute('href', '/scm/sales-orders/so-a');
  });

  it('links an SO-only line to the SO with no line', () => {
    renderCard();
    const link = within(rowOf('C-FH14')).getByRole('link', { name: /SO419866/ });
    expect(link).toHaveAttribute('href', '/scm/sales-orders/so-a');
    expect(link.textContent).not.toMatch(/line/);
  });

  it("shows AutoCount's number as plain text when the SO is not in the CRM", () => {
    renderCard();
    const cell = soCell('BT012-CR');
    expect((cell.textContent ?? '').trim()).toBe('SO400001');
    expect(within(cell).queryByRole('link')).toBeNull();
  });

  it('shows "-" for a direct DO line', () => {
    renderCard();
    const cell = soCell('SRTWB1515');
    expect((cell.textContent ?? '').trim()).toBe('-');
    expect(within(cell).queryByRole('link')).toBeNull();
  });
});
