/**
 * OI-SPLIT-VIEW (UAC B1, D1): the Sales Order page > Lines tab carries a "Split" column right
 * after Product (the chip and the (i) button of the shared `LineSplitInfo`), the Product cell no
 * longer carries it, the Columns menu lists it, and the gear "Sales order options" has "View
 * splits". Scaffolding is `SalesOrderDetail.test.tsx`'s. Red until the build.
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
  getSalesOrderUoms: () =>
    Promise.resolve([
      { id: 'uom-pcs', uom_code: 'PCS', uom_name: 'Pieces' },
      { id: 'uom-box', uom_code: 'BOX', uom_name: 'Box' },
    ]),
}));

import { SalesOrderDetail } from './SalesOrderDetail';
import type { SalesOrder } from '../../../types/scm.types';

const VIEW_480 = {
  status: 'confirmed',
  revision_no: 3,
  confirmed_on: '2026-10-19',
  base_qty: '417',
  base_date: '2026-10-20',
  now_qty: '14',
  now_date: '2026-09-20',
  total_qty: '417',
  rows: [
    { qty: '14', delivery_date: '2026-09-20', change: 'ADVANCE', sits_on: 'own', sits_on_line_no: 480, remark: '', is_cancel: false, changed: false, was_qty: null, was_date: null },
    { qty: '236', delivery_date: '2026-11-20', change: 'DELAY', sits_on: 'new', sits_on_line_no: null, remark: '', is_cancel: false, changed: false, was_qty: null, was_date: null },
    { qty: '167', delivery_date: '2026-11-20', change: 'DELAY', sits_on: 'new', sits_on_line_no: null, remark: '', is_cancel: false, changed: false, was_qty: null, was_date: null },
  ],
};

function line(id: string, no: number, over: Record<string, unknown> = {}) {
  return {
    id, line_no: no, sku: 'CSK14B', product_name: 'Basin', qty_ordered: 14, qty_delivered: 0,
    uom: 'PCS', warehouse_code: 'BRW-BB', line_status: 'open', required_date: '2026-09-20',
    unit_price: '100.00', discount: null, line_total: null, ...over,
  };
}

function order(withSplit = true): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO417636',
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
    total_qty: 646,
    committed_qty: 646,
    total_amount: '0',
    line_count: 2,
    open_line_count: 2,
    stock_locations: ['BRW-BB'],
    source: 'manual',
    internal_note: null,
    lines: [
      line('l-480', 480, withSplit ? { split_view: VIEW_480 } : { split_view: null }),
      line('l-608', 608, { qty_ordered: 632, split_view: null }),
    ],
    created_at: '2026-07-16T02:00:00',
  } as unknown as SalesOrder;
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderDetail id="so-1" />
    </QueryClientProvider>,
  );
}

function openTab(name: string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

function renderLines(withSplit = true) {
  useSalesOrder.mockReturnValue({ data: order(withSplit), isLoading: false, isError: false });
  renderDetail();
  openTab('Lines');
}

beforeEach(() => {
  cleanup();
  useSalesOrder.mockReset();
  updateSalesOrderMutateAsync.mockReset().mockResolvedValue({ planning_change_batch: null });
  searchParams = new URLSearchParams();
});

describe('SalesOrderDetail Lines: the Split column (B1)', () => {
  it('has a "Split" header right after Product', () => {
    renderLines();
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent ?? '').trim());
    const product = heads.indexOf('Product');
    expect(product).toBeGreaterThan(-1);
    expect(heads[product + 1]).toBe('Split');
  });

  it('shows "Split 3" and the (i) button on the split line only', () => {
    renderLines();
    const split = screen.getByText('480').closest('tr') as HTMLElement;
    expect(within(split).getByText('Split 3')).toBeInTheDocument();
    expect(
      within(split).getByRole('button', { name: 'Show the splits of line 480' }),
    ).toBeInTheDocument();
    const plain = screen.getByText('608').closest('tr') as HTMLElement;
    expect(within(plain).queryByText(/^Split \d/)).not.toBeInTheDocument();
    expect(within(plain).queryByRole('button', { name: /Show the splits of line/ })).not.toBeInTheDocument();
  });

  it('keeps "Split N" out of the Product cell', () => {
    renderLines();
    const row = screen.getByText('480').closest('tr') as HTMLElement;
    const cells = within(row).getAllByRole('cell');
    const productCell = cells.find((c) => (c.textContent ?? '').includes('CSK14B'))!;
    expect(productCell.textContent).not.toMatch(/Split \d/);
  });

  it('lists "Split" in the Columns menu', async () => {
    renderLines();
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Columns' }), {
      button: 0, ctrlKey: false, pointerType: 'mouse',
    });
    expect(await screen.findByRole('menuitemcheckbox', { name: 'Split' })).toBeInTheDocument();
  });

  it('opens the line popup from the (i) button, titled "Line 480 CSK14B: split"', () => {
    renderLines();
    fireEvent.click(screen.getByRole('button', { name: 'Show the splits of line 480' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Line 480 CSK14B: split')).toBeInTheDocument();
    expect(dialog.textContent).toContain('SO417636');
    expect(dialog.textContent).toContain('New line (not in AutoCount yet)');
  });
});

describe('SalesOrderDetail gear: View splits (D1)', () => {
  function openGear() {
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Sales order options' }), {
      button: 0, ctrlKey: false, pointerType: 'mouse',
    });
  }

  it('has "View splits" in the gear and opens "SO417636: splits" with the split line', async () => {
    renderLines();
    openGear();
    fireEvent.click(await screen.findByRole('menuitem', { name: 'View splits' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('SO417636: splits')).toBeInTheDocument();
    expect(dialog.textContent).toContain('Line 480 CSK14B');
    expect(dialog.textContent).not.toContain('Line 608');
  });

  it('shows the empty state when no line is split', async () => {
    renderLines(false);
    openGear();
    fireEvent.click(await screen.findByRole('menuitem', { name: 'View splits' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('No split lines')).toBeInTheDocument();
    expect(within(dialog).getByText('Every line ships as AutoCount has it.')).toBeInTheDocument();
  });
});
