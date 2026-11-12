/**
 * DATE-PICKER-UNIFY slice B: SalesOrderDetail edit mode. Order date, Delivery date and the
 * per-line Delivery date are single typeable DatePickerFields sending the same YYYY-MM-DD.
 * Harness copied from SalesOrderDetail.test.tsx.
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

/**
 * SO-DETAIL-DUP-BACK (owner, 21 Oct): the page showed TWO "Back to sales orders" while the
 * order loaded - the header's and the component's. The composed route is what the owner
 * sees, so it is what these render: the server page, awaited, around the real component.
 */
async function renderPage(page: 'sales-order' | 'consignment' = 'sales-order') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const params = Promise.resolve({ id: 'so-1' });
  const tree =
    page === 'consignment'
      ? await ConsignmentDetailPage({ params })
      : await SalesOrderDetailPage({ params });
  return render(<QueryClientProvider client={client}>{tree}</QueryClientProvider>);
}


function typeDate(el: HTMLElement, text: string) {
  fireEvent.change(el, { target: { value: text } });
  fireEvent.blur(el);
}

describe('SalesOrderDetail - dates (DATE-PICKER-UNIFY slice B)', () => {
  beforeEach(() => {
    useSalesOrder.mockReturnValue({ data: so(), isLoading: false, isError: false });
  });

  it('AC1/AC3: Edit shows the order and delivery dates as dd/mm/yyyy, no native input', () => {
    renderDetail();
    clickEdit();
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getByLabelText('Order date')).toHaveValue('16/07/2026');
    expect(screen.getByLabelText('Delivery date')).toHaveValue('30/08/2026');
  });

  it('AC2/AC9: typing both header dates saves order_date and requested_delivery_date as YYYY-MM-DD', async () => {
    renderDetail();
    clickEdit();
    typeDate(screen.getByLabelText('Order date'), '04/05/2026');
    typeDate(screen.getByLabelText('Delivery date'), '15/09/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Save sales order' }));
    await screen.findByRole('button', { name: 'Sales order options' });
    expect(updateSalesOrderMutateAsync.mock.calls[0][0].data).toMatchObject({
      order_date: '2026-05-04',
      requested_delivery_date: '2026-09-15',
    });
  });

  it('AC1/AC2: the per-line Delivery date is a typeable box and saves required_date as YYYY-MM-DD', async () => {
    renderDetail();
    clickEdit();
    openTab('Lines');
    const line = screen.getByLabelText('Delivery date on CW-BASIN-450');
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(line).toHaveValue('30/08/2026');
    typeDate(line, '05/10/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Save sales order' }));
    await screen.findByRole('button', { name: 'Sales order options' });
    expect(updateSalesOrderMutateAsync.mock.calls[0][0].data.lines[0]).toMatchObject({
      id: 'l-1',
      required_date: '2026-10-05',
    });
  });
});
