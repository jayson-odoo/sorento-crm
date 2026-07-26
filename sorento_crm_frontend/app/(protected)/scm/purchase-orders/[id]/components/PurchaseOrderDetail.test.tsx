/**
 * SCM M4 Slice B — PurchaseOrderDetail page (AC-M4.6/M4.15).
 * Always renders header + meta + lines + goods-receipt section (explicit empty
 * states), driven off the PO id. Covers loading / error(not-found) / data /
 * empty-lines / empty-GR states.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/purchase-orders/po-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const usePurchaseOrder = vi.fn();
const annotateMut = { mutate: vi.fn(), isPending: false };
vi.mock('../../../hooks/usePurchaseOrders', () => ({
  usePurchaseOrder: (...a: unknown[]) => usePurchaseOrder(...a),
  useAnnotatePurchaseOrder: () => annotateMut,
}));

import { PurchaseOrderDetail } from './PurchaseOrderDetail';
import type { PurchaseOrder } from '../../../types/scm.types';

function po(over: Partial<PurchaseOrder>): PurchaseOrder {
  return {
    id: 'po-1',
    po_number: 'PO-2026/07-0009',
    supplier_code: 'SUP-ACME',
    supplier_name: 'Acme Sanitary',
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    status: 'active',
    order_date: '2026-07-16',
    expected_date: '2026-07-30',
    total_qty: 320,
    line_count: 1,
    lines: [
      { id: 'l-1', sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm', qty_ordered: 320, qty_received: 0, uom: 'PCS' },
    ],
    created_at: '2026-07-16T00:00:00',
    is_on_order: true,
    source: 'recommendation',
    gr_reference: null,
    ...over,
  } as PurchaseOrder;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PurchaseOrderDetail (AC-M4.6)', () => {
  it('renders the loading skeleton state', () => {
    usePurchaseOrder.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = render(<PurchaseOrderDetail id="po-1" />);
    expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy();
  });

  it('renders the not-found empty state on error / missing PO', () => {
    usePurchaseOrder.mockReturnValue({ data: null, isLoading: false, isError: true });
    render(<PurchaseOrderDetail id="po-x" />);
    expect(screen.getByText('Purchase order not found')).toBeInTheDocument();
  });

  it('renders header + meta + lines for an active PO awaiting receipt', () => {
    usePurchaseOrder.mockReturnValue({ data: po({}), isLoading: false, isError: false });
    render(<PurchaseOrderDetail id="po-1" />);
    // Header (human PO number, never a UUID) + status.
    expect(screen.getByText('PO-2026/07-0009')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    // Meta fields.
    expect(screen.getByText('Acme Sanitary')).toBeInTheDocument();
    expect(screen.getByText('Reorder recommendation')).toBeInTheDocument();
    // Lines table.
    expect(screen.getByText('Order lines')).toBeInTheDocument();
    expect(screen.getByText('CW-BASIN-450')).toBeInTheDocument();
    // Goods-receipt section is ALWAYS rendered, with its empty state here.
    expect(screen.getByText('Goods receipt')).toBeInTheDocument();
    expect(screen.getByText(/No goods receipt yet/i)).toBeInTheDocument();
  });

  it('shows the draft empty-GR hint and "Not on order" for a draft PO', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ status: 'draft_recommendation', po_number: 'PO-DRAFT-0001', is_on_order: false }),
      isLoading: false,
      isError: false,
    });
    render(<PurchaseOrderDetail id="po-1" />);
    expect(screen.getByText(/Not on order \(draft\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Confirm this purchase order before a goods receipt/i)).toBeInTheDocument();
  });

  it('surfaces the goods-receipt reference once a GR exists', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ status: 'received', gr_reference: 'GR-2026/07-0003', line_count: 1 }),
      isLoading: false,
      isError: false,
    });
    render(<PurchaseOrderDetail id="po-1" />);
    expect(screen.getByText('GR-2026/07-0003')).toBeInTheDocument();
  });

  it('renders the empty-lines state when the PO has no lines', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ lines: [], line_count: 0 }),
      isLoading: false,
      isError: false,
    });
    render(<PurchaseOrderDetail id="po-1" />);
    expect(screen.getByText('This purchase order has no lines.')).toBeInTheDocument();
  });
});
