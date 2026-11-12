/**
 * DATE-PICKER-UNIFY slice B: PurchaseOrderDetail edit mode. Order date, Delivery date and the
 * per-line Delivery date are single typeable DatePickerFields sending the same YYYY-MM-DD.
 * Harness copied from PurchaseOrderDetail.test.tsx.
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

// PO-LINK-HISTORY: the History tab is shown only with `scm.dashboard.view`, the permission that
// opens the PO page and the one the audit read checks (crew ruling, 4 Nov). Granted by default; one test takes it away.
let grantedPermissions = new Set(['scm.dashboard.view']);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => grantedPermissions.has(slug),
}));

// PO-LINK-HISTORY: the History tab is the shared trail; what it is pointed at is the contract.
vi.mock('@/components/audit/AuditTrail', () => ({
  __esModule: true,
  default: ({ entityType, entityId, title }: { entityType: string; entityId: string; title?: string }) => (
    <div data-testid="audit-trail" data-entity-type={entityType} data-entity-id={entityId}>
      {title}
    </div>
  ),
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
function openTab(name: 'General' | 'Lines' | 'Goods receipt' | 'History') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

/** U4 (LINKAGE-UNIFY): the new SPO column prints its own muted dash for a line with no SPO,
 * so the book S/O assertions below look only inside the S/O cell. */
function soCell(row: HTMLElement): HTMLElement {
  const headers = screen.getAllByRole('columnheader').map((h) => (h.textContent ?? '').trim());
  const at = headers.findIndex((h) => h === 'S/O');
  return row.querySelectorAll('td')[at] as HTMLElement;
}

beforeEach(() => {
  cleanup();
  usePurchaseOrder.mockReset();
  updatePurchaseOrderMutateAsync.mockReset().mockResolvedValue({});
  searchParams = new URLSearchParams();
  grantedPermissions = new Set(['scm.dashboard.view']);
});


function typeDate(el: HTMLElement, text: string) {
  fireEvent.change(el, { target: { value: text } });
  fireEvent.blur(el);
}

describe('PurchaseOrderDetail - dates (DATE-PICKER-UNIFY slice B)', () => {
  beforeEach(() => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
  });

  it('AC1/AC3: Edit shows the order and delivery dates as dd/mm/yyyy, no native input', () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getByLabelText('Order date')).toHaveValue('16/07/2026');
    expect(screen.getByLabelText('Delivery date')).toHaveValue('30/07/2026');
  });

  it('AC2/AC9: typing both header dates saves order_date and expected_date as YYYY-MM-DD', async () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    typeDate(screen.getByLabelText('Order date'), '04/05/2026');
    typeDate(screen.getByLabelText('Delivery date'), '15/09/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Save purchase order' }));
    await waitFor(() => expect(updatePurchaseOrderMutateAsync).toHaveBeenCalled());
    const payload = updatePurchaseOrderMutateAsync.mock.calls[0][0];
    expect(payload.data.order_date).toBe('2026-05-04');
    expect(payload.data.expected_date).toBe('2026-09-15');
  });

  it('AC1/AC2: the per-line Delivery date is a typeable box and saves expected_date as YYYY-MM-DD', async () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    openTab('Lines');
    const line = screen.getByLabelText('Delivery date on CW-BASIN-450');
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(line).toHaveValue('30/07/2026');
    typeDate(line, '05/10/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Save purchase order' }));
    await waitFor(() => expect(updatePurchaseOrderMutateAsync).toHaveBeenCalled());
    expect(updatePurchaseOrderMutateAsync.mock.calls[0][0].data.lines[0]).toMatchObject({
      id: 'l-1',
      expected_date: '2026-10-05',
    });
  });
});
