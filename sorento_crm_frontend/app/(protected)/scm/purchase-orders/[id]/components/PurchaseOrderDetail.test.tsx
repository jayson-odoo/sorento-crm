/**
 * SCM M4 Slice B - PurchaseOrderDetail page (AC-M4.6/M4.15).
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

const usePurchaseOrder = vi.fn();
vi.mock('../../../hooks/usePurchaseOrders', () => ({
  usePurchaseOrder: (...a: unknown[]) => usePurchaseOrder(...a),
  // The header's prev/next pager reads the same list the user came from. One row means no
  // neighbours, so the pager renders nothing and these tests stay about the record itself.
  usePurchaseOrders: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 25 } } }),
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

  it('reads an imported historical order as bought, not as incoming', () => {
    // The 1,586 orders the purchase-history upload writes. Two things were wrong when the
    // real file first went in: "Total qty" counted open lines only, so every historical
    // order rendered empty, and the source said "Manual" for something nobody keyed.
    usePurchaseOrder.mockReturnValue({
      data: po({
        po_number: '202001-S0001',
        status: 'closed',
        total_qty: 450,
        line_count: 1,
        open_qty: 0,
        open_line_count: 0,
        is_on_order: false,
        source: 'import',
      }),
      isLoading: false,
      isError: false,
    });
    render(<PurchaseOrderDetail id="po-1" />);

    expect(screen.getByText('450')).toBeInTheDocument();
    expect(screen.getByText('Imported history')).toBeInTheDocument();
    // The gap between ordered and still-coming IS the answer on this row, so it is shown.
    expect(screen.getByText('Still incoming')).toBeInTheDocument();
  });

  it('does not repeat the quantity as "still incoming" on a fully open order', () => {
    // Equal figures, so a second identical number is noise rather than information.
    usePurchaseOrder.mockReturnValue({
      data: po({ total_qty: 320, open_qty: 320 }),
      isLoading: false,
      isError: false,
    });
    render(<PurchaseOrderDetail id="po-1" />);

    expect(screen.queryByText('Still incoming')).toBeNull();
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

describe('PurchaseOrderDetail - why a PO is not on order', () => {
  it('does not call a closed historical order a draft', () => {
    // An imported 2020 order is closed and fully received. "Not on order (draft)" says
    // somebody has yet to confirm a purchase that arrived six years ago.
    usePurchaseOrder.mockReturnValue({
      data: po({ status: 'closed', source: 'import', is_on_order: false }),
      isLoading: false,
      isError: false,
    });
    render(<PurchaseOrderDetail id="po-1" />);

    expect(screen.getByText('Not on order (nothing outstanding)')).toBeInTheDocument();
    expect(screen.queryByText('Not on order (draft)')).toBeNull();
  });

  it('still calls a draft a draft', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ status: 'draft_recommendation', is_on_order: false }),
      isLoading: false,
      isError: false,
    });
    render(<PurchaseOrderDetail id="po-1" />);

    expect(screen.getByText('Not on order (draft)')).toBeInTheDocument();
  });
});
