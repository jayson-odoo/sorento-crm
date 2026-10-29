/**
 * LINKAGE-UNIFY U4 (PLAN section 12, item 4, F3): the SCM PO detail Lines tab says
 * "Transferred" where it said "Qty received", and carries an SPO column per PO line drawn
 * with the shared pills ("Received 486 at BRW-BB", red "SPO withdrawn"), no "In transit".
 * Harness copied from `PurchaseOrderDetail.test.tsx`; `spos` is not on the app's line type
 * yet, so the fixture casts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

// A `let`, not a literal return, so the `?edit=1` auto-open test can point it at a URL
// carrying the param without a second mock module.
let searchParams = new URLSearchParams();
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

// The tab lives in the URL, not component state (see `handleTabChange`), so `openTab`
// below has to reach a REAL `router.replace` - one that feeds back into `searchParams`
// and wakes up every subscriber - or the controlled `<Tabs>` never sees the new value
// and stays on whichever tab it opened on.
const searchParamsListeners = new Set<() => void>();
function replaceSearchParams(next: URLSearchParams) {
  searchParams = next;
  searchParamsListeners.forEach((listener) => listener());
}
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/purchase-orders/po-1',
  useRouter: () => ({
    push: vi.fn(),
    replace: (url: string) => {
      const qIndex = url.indexOf('?');
      replaceSearchParams(new URLSearchParams(qIndex >= 0 ? url.slice(qIndex + 1) : ''));
    },
  }),
  useSearchParams: () =>
    React.useSyncExternalStore(
      (listener) => {
        searchParamsListeners.add(listener);
        return () => searchParamsListeners.delete(listener);
      },
      () => searchParams,
    ),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// The route tests render the server page, whose `Container` reads the layout settings
// provider; the wrapper is layout only, so a plain div stands in.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const usePurchaseOrder = vi.fn();
const updatePurchaseOrderMutateAsync = vi.fn();
vi.mock('../../../hooks/usePurchaseOrders', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  purchaseOrdersPagerQuery: {
    listQueryKey: () => ['scm-purchase-orders'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  usePurchaseOrder: (...a: unknown[]) => usePurchaseOrder(...a),
  // The header's prev/next pager reads the same list the user came from. An empty page
  // holds no record, so the pager renders nothing and these tests stay about the record.
  usePurchaseOrders: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 25 } } }),
  useUpdatePurchaseOrder: () => ({
    mutateAsync: updatePurchaseOrderMutateAsync,
    isPending: false,
  }),
}));

vi.mock('../../../hooks/useScmOptions', () => ({
  useWarehouseOptions: () => ({
    data: [
      { value: 'BRW-BB', label: 'Brickworks Batu Berendam' },
      { value: 'WH-KL', label: 'Kuala Lumpur DC' },
    ],
    isLoading: false,
  }),
}));

// The Supplier and Product selects are SERVER-SEARCHED - `fetchOptions`, not a static array.
// Mocked as the component calls them: `(query, pageIndex) => Promise<Option[]>`.
vi.mock('../../../services/scmOptionsService', () => ({
  SELECT_PAGE_SIZE: 50,
  searchSupplierOptions: vi.fn(async () => [
    { value: 'SUP-ACME', label: 'SUP-ACME · Acme Sanitary' },
  ]),
  searchProductOptions: vi.fn(async () => [
    { value: 'CW-BASIN-450', label: 'CW-BASIN-450 · Ceramic Wash Basin 450mm' },
  ]),
}));

// `getSalesOrderUoms` is the only export this component reads off that service module: the
// UoM select's own options, which are the same `units_of_measure` rows either book needs.
vi.mock('../../../services/salesOrderService', () => ({
  getSalesOrderUoms: () =>
    Promise.resolve([
      { id: 'uom-pcs', uom_code: 'PCS', uom_name: 'Pieces' },
      { id: 'uom-box', uom_code: 'BOX', uom_name: 'Box' },
    ]),
}));

import { PurchaseOrderDetail } from './PurchaseOrderDetail';
import PurchaseOrderDetailPage from '../page';
import type { PurchaseOrder, PurchaseOrderLine } from '../../../types/scm.types';

function po(over: Partial<PurchaseOrder> = {}): PurchaseOrder {
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
    open_qty: 320,
    open_line_count: 1,
    total_amount: '31985.00',
    currency: 'MYR',
    lines: [
      {
        id: 'l-1',
        sku: 'CW-BASIN-450',
        product_name: 'Ceramic Wash Basin 450mm',
        qty_ordered: 320,
        qty_received: 0,
        uom: 'PCS',
        warehouse_code: 'WH-KL',
        line_status: 'open',
        expected_date: '2026-07-30',
        unit_price: '100.00',
        discount: '15.00',
        line_total: '31985.00',
        currency: 'MYR',
      },
    ],
    created_at: '2026-07-16T00:00:00',
    is_on_order: true,
    source: 'recommendation',
    gr_reference: null,
    ...over,
  } as PurchaseOrder;
}

function renderDetail() {
  // A real `QueryClient`, not mocked: the UoM select's own `useQuery` needs a provider to run
  // at all. `retry: false` so an unmet expectation fails fast.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrderDetail id="po-1" />
    </QueryClientProvider>,
  );
}

/**
 * Open one of the record's tabs.
 *
 * `mouseDown`, not `click`: Radix's tab trigger selects on mouse-down (a plain `click` event
 * in jsdom leaves the tab strip exactly where it was, which reads as a section that vanished).
 */
function openTab(name: 'General' | 'Lines' | 'Goods receipt') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

beforeEach(() => {
  cleanup();
  usePurchaseOrder.mockReset();
  searchParams = new URLSearchParams();
});

function withSpos() {
  const base = po();
  return {
    ...base,
    lines: [
      {
        ...base.lines![0],
        qty_ordered: 780,
        qty_received: 780,
        spos: [
          { spo_number: 'SPO-2026/09-0107', line_label: 'L9',
            receipts: [{ qty: '486', bin: 'BRW-BB' }], dead_reason: null },
          { spo_number: 'SPO-2026/09-0107', line_label: 'L7', receipts: [], dead_reason: 'spo_withdrawn' },
        ],
      } as unknown as PurchaseOrderLine,
    ],
  } as PurchaseOrder;
}

describe('F3 PurchaseOrderDetail Lines tab', () => {
  it('seed: the Lines tab opens on the line', () => {
    usePurchaseOrder.mockReturnValue({ data: withSpos(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    expect(screen.getByText('CW-BASIN-450')).toBeInTheDocument();
  });

  it('heads the figure "Transferred", not "Qty received"', () => {
    usePurchaseOrder.mockReturnValue({ data: withSpos(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    expect(screen.getByRole('button', { name: 'Transferred' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Qty received' })).not.toBeInTheDocument();
  });

  it('carries an SPO column with the shared pills and no "In transit" tag', () => {
    usePurchaseOrder.mockReturnValue({ data: withSpos(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    expect(screen.getByRole('button', { name: 'SPO' })).toBeInTheDocument();
    expect(screen.getByText('Received 486 at BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('SPO withdrawn')).toBeInTheDocument();
    expect(screen.queryByText(/in transit/i)).not.toBeInTheDocument();
  });
});

describe('P2 the SCM PO Lines SPO column uses the one shared pill', () => {
  it('the receipt is the shared Badge pill (truncating, full title) and the SPO number never truncates', () => {
    usePurchaseOrder.mockReturnValue({ data: withSpos(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    const text = screen.getByText('Received 486 at BRW-BB');
    const badge = text.closest('[data-slot="badge"]') as HTMLElement | null;
    expect(badge).not.toBeNull();
    expect(text.className).toContain('truncate');
    expect(badge!.className).toContain('min-w-0');
    expect((text.closest('[title]') as HTMLElement).getAttribute('title')).toBe(
      'Received 486 at BRW-BB',
    );
    const number = screen.getAllByText('SPO-2026/09-0107')[0] as HTMLElement;
    expect(number.className).toContain('shrink-0');
    expect(number.className).not.toMatch(/truncate|overflow-hidden|text-ellipsis|(^|\s)max-w-/);
  });
});

describe('P3 the Goods receipt card says "transferred" for the AutoCount figure (owner ruling c)', () => {
  it('reads "<qty> of <ordered> transferred", never "received"', () => {
    usePurchaseOrder.mockReturnValue({ data: withSpos(), isLoading: false, isError: false });
    renderDetail();
    openTab('Goods receipt');
    expect(screen.getByText(/780 of 780 transferred/)).toBeInTheDocument();
    expect(screen.queryByText(/of [\d,.]+ received/)).not.toBeInTheDocument();
  });
});

describe('R4-D3 the SCM PO Lines tab marks a cancelled PO line red "PO cancelled"', () => {
  const withDead = (dead_reason: string | null) => {
    const base = po();
    return {
      ...base,
      lines: [{ ...base.lines![0], qty_received: 0, spos: [], dead_reason } as unknown as PurchaseOrderLine],
    } as PurchaseOrder;
  };

  it('a line whose dead_reason is po_cancelled draws the shared red pill', () => {
    usePurchaseOrder.mockReturnValue({ data: withDead('po_cancelled'), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    const pill = screen.getByText('PO cancelled').closest('[data-slot="badge"]') as HTMLElement;
    expect(pill).not.toBeNull();
    expect(pill.className).toMatch(/destructive/);
  });

  it('a line whose dead_reason is null draws no such pill', () => {
    usePurchaseOrder.mockReturnValue({ data: withDead(null), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    expect(screen.queryByText('PO cancelled')).not.toBeInTheDocument();
  });
});

describe('R4b both pills when both apply (mock case 2)', () => {
  it('a cancelled PO line with a withdrawn SPO draws red "PO cancelled" and red "SPO withdrawn"', () => {
    const base = po();
    const data = {
      ...base,
      lines: [{
        ...base.lines![0], qty_received: 0, dead_reason: 'po_cancelled',
        spos: [{ spo_number: 'SPO-2026/09-0138', line_label: 'L138', receipts: [], dead_reason: 'spo_withdrawn' }],
      } as unknown as PurchaseOrderLine],
    } as PurchaseOrder;
    usePurchaseOrder.mockReturnValue({ data, isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    expect(screen.getByText('SPO-2026/09-0138')).toBeInTheDocument();
    for (const label of ['PO cancelled', 'SPO withdrawn']) {
      const pill = screen.getByText(label).closest('[data-slot="badge"]') as HTMLElement;
      expect(pill.className).toMatch(/destructive/);
    }
  });
});
