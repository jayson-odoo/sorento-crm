/**
 * OI-WHOLE-SO-CANCEL F2 (crew ruling: mirror Suggested), red: on the order page's Lines tab the
 * Decided column of a book-cancelled line whose cancel CS saved reads "Cancel line" with the
 * existing "Saved" badge (the saved decision is an approval with an EMPTY composition, so
 * `supply_saved` is `[]`; the line is `cancelled` and a `cancelled` planning change is pending).
 * Unsaved it keeps today's "-"; a normal saved Buy still prints its composition. Harness copied
 * from `SalesOrderDetail.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react';
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

// The header's Plan primary (S2, R3) reaches for the NextAuth session through this hook,
// which is not mounted under jsdom - stubbed off, the same way the sales-orders LIST suite
// stubs it, since this file's own tests are about Edit under the gear, not about the
// permission gate (that is a browser-pass check, AC-S2-6/10).
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

// The Transfers tab renders the SAME grid the Transfers page does; that component has its
// own tests, so here only the wiring (which order it is pinned to) has to be proven.
vi.mock(
  '@/app/(protected)/inventory-management/stock-transfers/components/StockTransfersPanel',
  () => ({
    StockTransfersPanel: (props: { salesOrderId?: string; showFilters?: boolean }) => (
      <div data-testid="stock-transfers-panel" data-sales-order={props.salesOrderId}>
        {String(props.showFilters)}
      </div>
    ),
  }),
);

// The route tests below render the server page, whose `Container` reads the layout settings
// provider; the wrapper is layout only, so a plain div stands in.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const useSalesOrder = vi.fn();
const updateSalesOrderMutateAsync = vi.fn();
vi.mock('../../../hooks/useSalesOrders', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  salesOrdersPagerQuery: {
    listQueryKey: () => ['scm-sales-orders'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useSalesOrder: (...a: unknown[]) => useSalesOrder(...a),
  // The record's gear renders the shared action set, whose Delete needs this.
  useDeleteSalesOrder: () => ({ isPending: false, mutateAsync: vi.fn() }),
  // The header's prev/next pager reads the same list the user came from. An empty page
  // holds no record, so the pager renders nothing and these tests stay about the record.
  useSalesOrders: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 25 } } }),
  useUpdateSalesOrder: () => ({ mutateAsync: updateSalesOrderMutateAsync, isPending: false }),
}));

vi.mock('../../../hooks/useScmOptions', () => ({
  useWarehouseOptions: () => ({
    data: [
      { value: 'BRW-BB', label: 'Brickworks Batu Berendam' },
      { value: 'BRW-IB', label: 'Brickworks Iskandar' },
      { value: 'KL-01', label: 'Kuala Lumpur 01' },
    ],
    isLoading: false,
  }),
}));

// The Customer and Product selects are SERVER-SEARCHED now - `fetchOptions`, not a static
// array - because the two masters behind them hold 6,397 and ~22,000 rows. Mocked as the
// component calls them: `(query, pageIndex) => Promise<Option[]>`.
vi.mock('../../../services/scmOptionsService', () => ({
  SELECT_PAGE_SIZE: 50,
  searchCustomerOptions: vi.fn(async () => [
    { value: '300-R009', label: 'Rowenda Kitchen Sdn Bhd' },
  ]),
  searchProductOptions: vi.fn(async () => [
    { value: 'CW-BASIN-450', label: 'CW-BASIN-450 · Ceramic Wash Basin 450mm' },
  ]),
}));

vi.mock('../../hooks/useSalesAgentOptions', () => ({
  useSalesAgentOptions: () => ({
    options: [
      { value: 'agent-jeremy', label: 'JR001 · JEREMY' },
      { value: 'agent-cindy', label: 'CL002 · CONTACT W' },
    ],
  }),
}));

// `getSalesOrderUoms` is the only export the component reads off this service module - the
// UoM select's own options. Everything else the component uses from it (`updateSalesOrder`)
// is reached through the fully-mocked `useUpdateSalesOrder` above, never this module.
vi.mock('../../../services/salesOrderService', () => ({
  // The Delivery tab's DO list (DO-SO-LINK-SURFACE R3): none here, so the tab's sentence reads
  // the order's own figures (DOC-RELATIONS: the sentence shows only when there is no DO row).
  getSalesOrderDeliveries: () => Promise.resolve({ lines: [], groups: [], others: [] }),
  getSalesOrderUoms: () =>
    Promise.resolve([
      { id: 'uom-pcs', uom_code: 'PCS', uom_name: 'Pieces' },
      { id: 'uom-box', uom_code: 'BOX', uom_name: 'Box' },
    ]),
}));

import { SalesOrderDetail } from './SalesOrderDetail';
import SalesOrderDetailPage from '../page';
import ConsignmentDetailPage from '../../../consignments/[id]/page';
import type { SalesOrder, SalesOrderLine } from '../../../types/scm.types';

function so(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO-2026/07-0042',
    order_type: 'project',
    order_type_label: 'Project',
    // The PLANNING CLASS, which is what the screen both renders and edits. `order_type` is
    // the ERP document type and is NULL on 96% of this book.
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
      },
    ],
    created_at: '2026-07-16T02:00:00',
    ...over,
  } as SalesOrder;
}

function renderDetail() {
  // A real `QueryClient`, not mocked: the UoM select's own `useQuery` (`getSalesOrderUoms`,
  // mocked above) needs a provider to run at all. `retry: false` so an unmet expectation
  // fails fast instead of retrying into the test's own timeout.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderDetail id="so-1" />
    </QueryClientProvider>,
  );
}

/**
 * Open one of the record's tabs. Every section still exists; this is where it lives.
 *
 * `mouseDown`, not `click`: Radix's tab trigger selects on mouse-down (a plain `click` event
 * in jsdom leaves the tab strip exactly where it was, which reads as a section that vanished).
 */
function openTab(name: 'General' | 'Lines' | 'Delivery' | 'Transfers') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

/**
 * Edit lives behind the gear now (S2, R3): the header's primary slot is Plan. Radix opens
 * its menu on POINTER-down (see the Columns button elsewhere in this file), so open it the
 * same way, then press the Edit item.
 */
function clickEdit() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Sales order options' }), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  fireEvent.click(screen.getByRole('menuitem', { name: /^Edit$/ }));
}

beforeEach(() => {
  cleanup();
  useSalesOrder.mockReset();
  // `planning_change_batch: null` - the shape every save's response carries, whether or not
  // it raised one. `handleSave` reads this key unconditionally.
  updateSalesOrderMutateAsync.mockReset().mockResolvedValue({ planning_change_batch: null });
  searchParams = new URLSearchParams();
});

function lineOf(over: Partial<SalesOrderLine>): SalesOrder {
  return so({
    lines: [
      {
        id: 'l-cancel',
        sku: 'SKU-CANCEL',
        product_name: 'Cancel line',
        qty_ordered: 10,
        qty_delivered: 0,
        uom: 'PCS',
        warehouse_code: 'BRW-BB',
        line_status: 'cancelled',
        required_date: '2026-08-30',
        planning_change: { id: 'pcr-1', kind: 'cancelled', applied_state: 'pending', result: null },
        decision_revision: null,
        ...over,
      } as SalesOrderLine,
    ],
    line_count: 1,
  });
}

function decidedCell(): HTMLElement {
  const row = screen.getByText('SKU-CANCEL').closest('tr') as HTMLElement;
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
  const index = headers.findIndex((name) => name === 'Decided');
  expect(index, 'the Lines grid has a Decided column').toBeGreaterThanOrEqual(0);
  return within(row).getAllByRole('cell')[index] as HTMLElement;
}

describe('SalesOrderDetail: the Decided column of a book-cancelled line (F2)', () => {
  it('reads "Cancel line" with the Saved badge once the cancel is saved', () => {
    useSalesOrder.mockReturnValue({
      data: lineOf({ supply_saved: [], saved_by: 'Leena', saved_at: '2026-11-12T02:30:00Z', saved_stale: false }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    const cell = decidedCell();
    expect(cell).toHaveTextContent('Cancel line');
    expect(within(cell).getByTestId('saved-decision-badge-l-cancel')).toHaveTextContent('Saved');
  });

  it('keeps today\'s dash while the cancel is unsaved', () => {
    useSalesOrder.mockReturnValue({
      data: lineOf({ supply_saved: null }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    expect(decidedCell()).not.toHaveTextContent('Cancel line');
    expect(decidedCell()).toHaveTextContent('-');
  });

  describe('with the old revision 1 Buy still in supply_decided', () => {
    const OLD_BUY = [{ kind: 'buy', qty: '2', source_location: null, rung: null }];

    it('unsaved (supply_saved null): Decided does not read "Buy 2", it shows the empty marker', () => {
      useSalesOrder.mockReturnValue({
        data: lineOf({ supply_decided: OLD_BUY, decision_revision: 1, supply_saved: null }),
        isLoading: false,
        isError: false,
      });
      renderDetail();
      openTab('Lines');

      const cell = decidedCell();
      expect(cell).not.toHaveTextContent('Buy 2');
      expect(cell).not.toHaveTextContent('Cancel line');
      expect(cell).toHaveTextContent('-');
    });

    it('saved (supply_saved []): Decided reads "Cancel line" with the Saved badge', () => {
      useSalesOrder.mockReturnValue({
        data: lineOf({
          supply_decided: OLD_BUY,
          decision_revision: 1,
          supply_saved: [],
          saved_by: 'Leena',
          saved_at: '2026-11-12T02:30:00Z',
          saved_stale: false,
        }),
        isLoading: false,
        isError: false,
      });
      renderDetail();
      openTab('Lines');

      const cell = decidedCell();
      expect(cell).toHaveTextContent('Cancel line');
      expect(cell).not.toHaveTextContent('Buy 2');
      expect(within(cell).getByTestId('saved-decision-badge-l-cancel')).toHaveTextContent('Saved');
    });
  });

  it('guard: a normal saved Buy still prints its composition', () => {
    useSalesOrder.mockReturnValue({
      data: lineOf({
        line_status: 'open',
        planning_change: null,
        supply_saved: [{ kind: 'buy', qty: '3', source_location: null, rung: null }],
        saved_by: 'Leena',
        saved_at: '2026-11-12T02:30:00Z',
        saved_stale: false,
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    expect(decidedCell()).toHaveTextContent('Buy 3');
    expect(decidedCell()).not.toHaveTextContent('Cancel line');
  });
});
