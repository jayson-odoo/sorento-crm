/**
 * DEALER-PLANNING PR 2, R6: the sales order detail page offers Plan for an admitted retail
 * order (a retail or other order with a line at a dealer location, `plannable_lines` above
 * zero) and not for an order that cannot be planned. Today Plan shows for project orders
 * only. Mocking copied from `SalesOrderDetail.consignment.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
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

let searchParams = new URLSearchParams();
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

const searchParamsListeners = new Set<() => void>();
function replaceSearchParams(next: URLSearchParams) {
  searchParams = next;
  searchParamsListeners.forEach((listener) => listener());
}
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/sales-orders/so-1',
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

vi.mock(
  '@/app/(protected)/inventory-management/stock-transfers/components/StockTransfersPanel',
  () => ({
    StockTransfersPanel: () => <div data-testid="stock-transfers-panel" />,
  }),
);

// AC-S2-6: the header's Plan primary is gated on `projects.projects.view`, same as the
// list's own "Plan selected". A `let`, flipped per-test, the same convention
// `SalesOrdersGrid.test.tsx` already uses for this hook.
let hasPermission = false;
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPermission,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const useSalesOrder = vi.fn();
const updateSalesOrderMutateAsync = vi.fn();
vi.mock('../../../hooks/useSalesOrders', () => ({
  salesOrdersPagerQuery: {
    listQueryKey: () => ['scm-sales-orders'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useSalesOrder: (...a: unknown[]) => useSalesOrder(...a),
  useDeleteSalesOrder: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useSalesOrders: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 25 } } }),
  useUpdateSalesOrder: () => ({ mutateAsync: updateSalesOrderMutateAsync, isPending: false }),
}));

vi.mock('../../../hooks/useScmOptions', () => ({
  useWarehouseOptions: () => ({ data: [], isLoading: false }),
}));

vi.mock('../../../services/scmOptionsService', () => ({
  SELECT_PAGE_SIZE: 50,
  searchCustomerOptions: vi.fn(async () => []),
  searchProductOptions: vi.fn(async () => []),
}));

vi.mock('../../hooks/useSalesAgentOptions', () => ({
  useSalesAgentOptions: () => ({ options: [] }),
}));

vi.mock('../../../services/salesOrderService', () => ({
  getSalesOrderUoms: () => Promise.resolve([]),
}));

import { SalesOrderDetail } from './SalesOrderDetail';
import type { SalesOrder, SalesOrderLine } from '../../../types/scm.types';

function so(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO-2026/07-0042',
    order_type: 'project',
    order_type_label: 'Project',
    demand_class: 'project',
    customer_code: '300-R009',
    customer_name: 'Rowenda Kitchen Sdn Bhd',
    market_segment: 'Project',
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-16',
    requested_delivery_date: '2026-08-30',
    total_qty: 320,
    committed_qty: 320,
    total_amount: '31985.00',
    line_count: 1,
    open_line_count: 1,
    stock_locations: ['BRW-BB'],
    source: 'manual',
    internal_note: null,
    lines: [
      {
        id: 'l-1',
        sku: 'CW-BASIN-450',
        product_name: 'Ceramic Wash Basin 450mm',
        qty_ordered: 320,
        qty_delivered: 0,
        uom: 'PCS',
        unit_price: '100.00',
        discount: '15.00',
        line_total: '31985.00',
        warehouse_code: 'BRW-BB',
        line_status: 'open',
        required_date: '2026-08-30',
        line_no: 1,
        source: 'autocount',
      },
    ],
    created_at: '2026-07-16T02:00:00',
    ...over,
  } as SalesOrder;
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderDetail id="so-1" />
    </QueryClientProvider>,
  );
}

function openTab(name: 'General' | 'Lines' | 'Delivery' | 'Transfers') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

/** Radix opens its menu on pointer-down. */
function openGear() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Sales order options' }), {
    button: 0,
    pointerType: 'mouse',
  });
}

beforeEach(() => {
  cleanup();
  useSalesOrder.mockReset();
  updateSalesOrderMutateAsync.mockReset().mockResolvedValue({ planning_change_batch: null });
  searchParams = new URLSearchParams();
  hasPermission = false;
});


const lines = (qtyReturned?: number) => [
  {
    id: 'l-1', sku: 'SKU-A', product_name: 'A', qty_ordered: 10, qty_delivered: 0,
    uom: 'PCS', warehouse_code: 'BRW-BB', line_status: 'open', required_date: null,
    line_no: 1, source: 'autocount',
    ...(qtyReturned === undefined ? {} : { qty_returned: qtyReturned }),
  },
];

function stub(over: Record<string, unknown>) {
  useSalesOrder.mockReturnValue({ data: so(over), isLoading: false, isError: false });
}

describe('R6: Plan on the sales order page follows whether the order can be planned', () => {
  const plan = () => screen.queryByRole('link', { name: /^plan$/i });

  it.each(['retail', 'other'])('a %s order with a plannable line shows Plan, to the board', (klass) => {
    hasPermission = true;
    stub({ doc_type: 'sales_order', demand_class: klass, planned_lines: 0, plannable_lines: 1, lines: lines(0) });
    renderDetail();
    expect(plan()).not.toBeNull();
    expect(plan()?.getAttribute('href')).toBe(
      `/project-sales/fulfilment-planning?orders=${encodeURIComponent('SO-2026/07-0042')}`,
    );
  });

  it('a retail order with no plannable line shows no Plan', () => {
    hasPermission = true;
    stub({ doc_type: 'sales_order', demand_class: 'retail', planned_lines: 0, plannable_lines: 0, lines: lines(0) });
    renderDetail();
    expect(plan()).toBeNull();
  });

  it('an order with no class shows no Plan', () => {
    hasPermission = true;
    stub({ doc_type: 'sales_order', demand_class: null, planned_lines: 0, plannable_lines: 0, lines: lines(0) });
    renderDetail();
    expect(plan()).toBeNull();
  });

  it('a plannable retail order shows no Plan without projects.projects.view', () => {
    hasPermission = false;
    stub({ doc_type: 'sales_order', demand_class: 'retail', planned_lines: 0, plannable_lines: 1, lines: lines(0) });
    renderDetail();
    expect(plan()).toBeNull();
  });

  it('a project order keeps its Plan', () => {
    hasPermission = true;
    stub({ doc_type: 'sales_order', demand_class: 'project', planned_lines: 0, plannable_lines: 1, lines: lines(0) });
    renderDetail();
    expect(plan()).not.toBeNull();
  });
});
