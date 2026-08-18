/**
 * SalesOrderDetail - the demand-side twin of `PurchaseOrderDetail`.
 *
 * Two things this file is here to hold. The first is the CRUD standard: every section is
 * rendered on every state, with an explicit empty message, so a panel that is missing means
 * something rather than reading as "not loaded yet".
 *
 * The second is specific to this screen. 11,006 of the sales orders in the system were
 * absorbed from a six-year AutoCount export and are closed history; the rest are live
 * commitments the plan is computed from. A screen that showed a delivered 2020 order and an
 * open one the same way would be actively misleading, so "committed" and its reason are
 * asserted for both.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

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

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/sales-orders/so-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const useSalesOrder = vi.fn();
vi.mock('../../../hooks/useSalesOrders', () => ({
  useSalesOrder: (...a: unknown[]) => useSalesOrder(...a),
  // The header's prev/next pager reads the same list the user came from. One row means no
  // neighbours, so the pager renders nothing and these tests stay about the record itself.
  useSalesOrders: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 25 } } }),
}));

import { SalesOrderDetail } from './SalesOrderDetail';
import type { SalesOrder, SalesOrderLine } from '../../../types/scm.types';

function so(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO-2026/07-0042',
    order_type: 'project',
    order_type_label: 'Project',
    customer_code: '300-R009',
    customer_name: 'Rowenda Kitchen Sdn Bhd',
    market_segment: 'Project',
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-16',
    requested_delivery_date: '2026-08-30',
    total_qty: 320,
    committed_qty: 320,
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
  return render(<SalesOrderDetail id="so-1" />);
}

beforeEach(() => {
  cleanup();
  useSalesOrder.mockReset();
});

describe('SalesOrderDetail - states', () => {
  it('shows a skeleton and the way back while loading', () => {
    useSalesOrder.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderDetail();
    // The way back is present even before the record is: a slow read must not trap anybody.
    expect(screen.getByText('Back to sales orders')).toBeInTheDocument();
  });

  it('names what is missing rather than rendering an empty shell', () => {
    useSalesOrder.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderDetail();
    expect(screen.getByText('Sales order not found')).toBeInTheDocument();
    expect(screen.getByText('Back to sales orders')).toBeInTheDocument();
  });

  it('renders the document number, the customer and every summary field', () => {
    useSalesOrder.mockReturnValue({ data: so(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getByText('SO-2026/07-0042')).toBeInTheDocument();
    expect(screen.getByText('Rowenda Kitchen Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('300-R009')).toBeInTheDocument();
    for (const label of [
      'Customer', 'Customer code', 'Order type', 'Market segment', 'Order date',
      'Requested delivery', 'Priority', 'Locations', 'Total qty', 'Lines', 'Source',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('renders every section even when the record is bare', () => {
    // The CRUD standard, asserted on the emptiest record the API can return: a section that
    // disappears on missing data reads as a page that failed to load.
    useSalesOrder.mockReturnValue({
      data: so({ lines: [], total_qty: 0, committed_qty: 0, line_count: 0, open_line_count: 0 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    expect(screen.getByText('Order lines')).toBeInTheDocument();
    expect(screen.getByText('This sales order has no lines.')).toBeInTheDocument();
    expect(screen.getByText('Delivery')).toBeInTheDocument();
    expect(screen.getByText(/Nothing delivered yet/)).toBeInTheDocument();
    expect(screen.getByText('Note')).toBeInTheDocument();
    expect(screen.getByText(/No note\./)).toBeInTheDocument();
  });
});

describe('SalesOrderDetail - committed or not, and why', () => {
  it('reads as committed demand while quantity is still owed', () => {
    useSalesOrder.mockReturnValue({ data: so(), isLoading: false, isError: false });
    renderDetail();
    expect(screen.getByText('Committed demand')).toBeInTheDocument();
  });

  it('says absorbed history rather than delivered on a closed imported order', () => {
    // The distinction that matters on this database: 11,006 of these orders were read off a
    // 2020-2026 spreadsheet. Calling one "delivered" claims a delivery this system recorded,
    // when it only ever read one.
    useSalesOrder.mockReturnValue({
      data: so({
        status: 'closed',
        source: 'history',
        committed_qty: 0,
        open_line_count: 0,
        lines: [
          {
            id: 'l-1', sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm',
            qty_ordered: 320, qty_delivered: 320, uom: 'PCS',
            warehouse_code: 'BRW-BB', line_status: 'closed', required_date: '2020-03-15',
          },
        ],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    expect(screen.getByText('Not committed (absorbed history)')).toBeInTheDocument();
    expect(screen.getByText('Absorbed history')).toBeInTheDocument();
    expect(screen.queryByText('Committed demand')).not.toBeInTheDocument();
  });

  it('says cancelled rather than "nothing outstanding" on a cancelled order', () => {
    useSalesOrder.mockReturnValue({
      data: so({ status: 'cancelled', committed_qty: 0, open_line_count: 0 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    expect(screen.getByText('Not committed (cancelled)')).toBeInTheDocument();
  });

  it('hides "Still owed" when it would just repeat the total', () => {
    // A wholly open order has committed == total, and a second identical figure beside the
    // first is noise. On a part-delivered one the gap is the answer, so it appears.
    // Scoped to the summary, because the lines grid carries a column of the same name -
    // deliberately, since it is the same quantity once per order and once per line.
    useSalesOrder.mockReturnValue({ data: so(), isLoading: false, isError: false });
    const { unmount } = renderDetail();
    const summary = () => screen.getByRole('region', { name: 'Order summary' });
    expect(within(summary()).queryByText('Still owed')).not.toBeInTheDocument();
    unmount();

    useSalesOrder.mockReturnValue({
      data: so({ committed_qty: 120 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    expect(within(summary()).getByText('Still owed')).toBeInTheDocument();
  });
});

describe('SalesOrderDetail - delivery panel', () => {
  it('reports a part delivery with what is left and across how many lines', () => {
    useSalesOrder.mockReturnValue({
      data: so({ total_qty: 320, committed_qty: 120, open_line_count: 2 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    expect(screen.getByText(/200 of 320 delivered/)).toBeInTheDocument();
    expect(screen.getByText(/120 still owed across 2 lines/)).toBeInTheDocument();
  });

  it('reports a full delivery once nothing is owed', () => {
    useSalesOrder.mockReturnValue({
      data: so({ committed_qty: 0, open_line_count: 0 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    expect(screen.getByText('delivered in full')).toBeInTheDocument();
  });
});

describe('SalesOrderDetail - sorting the lines', () => {
  /**
   * A header that carries a sort arrow and does nothing is worse than a header that offers
   * no sort at all: the user reads the reordered arrow as a reordered table and trusts the
   * top row. These lines arrive in an order that is ascending in NO column, so a grid that
   * quietly ignores the click cannot pass by accident.
   */
  const SORT_LINES: SalesOrderLine[] = [
    {
      id: 'l-b', sku: 'SKU-B', product_name: 'Beta basin', qty_ordered: 320,
      qty_delivered: 300, uom: 'PCS', warehouse_code: 'BRW-BB', line_status: 'open',
      required_date: '2026-09-01',
    },
    {
      id: 'l-c', sku: 'SKU-C', product_name: 'Gamma tap', qty_ordered: 45,
      qty_delivered: 0, uom: 'PCS', warehouse_code: 'BRW-BB', line_status: 'open',
      required_date: '2026-07-04',
    },
    {
      id: 'l-a', sku: 'SKU-A', product_name: 'Alpha pan', qty_ordered: 1200,
      qty_delivered: 1100, uom: 'PCS', warehouse_code: 'KL-01', line_status: 'open',
      required_date: '2026-08-15',
    },
  ];

  const skuOrder = () =>
    screen
      .getAllByRole('row')
      .map((row) => row.textContent ?? '')
      .filter((text) => text.includes('SKU-'))
      .map((text) => text.match(/SKU-[A-Z]/)?.[0] ?? '');

  beforeEach(() => {
    useSalesOrder.mockReturnValue({
      data: so({ lines: SORT_LINES, line_count: 3, open_line_count: 3 }),
      isLoading: false,
      isError: false,
    });
  });

  it('orders by quantity, ascending then descending, when the header is clicked', () => {
    renderDetail();
    expect(skuOrder()).toEqual(['SKU-B', 'SKU-C', 'SKU-A']);

    // 45 < 320 < 1200 - a numeric order, not the alphabetical one a formatted string gives.
    fireEvent.click(screen.getByRole('button', { name: 'Qty ordered' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-B', 'SKU-A']);

    fireEvent.click(screen.getByRole('button', { name: 'Qty ordered' }));
    expect(skuOrder()).toEqual(['SKU-A', 'SKU-B', 'SKU-C']);
  });

  it('orders by what has been delivered', () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Qty delivered' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-B', 'SKU-A']);
  });

  it('orders "Still owed" by the figure it shows, not by the order the lines arrived in', () => {
    // The computed column: 20, 45, 100 owed. Its order differs from every other column's,
    // so this fails if the header sorts on anything but the number in the cell.
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Still owed' }));
    expect(skuOrder()).toEqual(['SKU-B', 'SKU-C', 'SKU-A']);

    fireEvent.click(screen.getByRole('button', { name: 'Still owed' }));
    expect(skuOrder()).toEqual(['SKU-A', 'SKU-C', 'SKU-B']);
  });

  it('orders the required date chronologically, not by how it is printed', () => {
    // Printed as 04 Jul / 15 Aug / 01 Sep, so a sort on the displayed text would read
    // 01, 04, 15 and put September first.
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Required' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-A', 'SKU-B']);
  });
});

describe('SalesOrderDetail - the note', () => {
  it('shows the customer an absorbed order could not be matched to', () => {
    // 470 of the client's debtor codes are not in the CRM. The order is still absorbed, and
    // this is the only place the name survives - without it the order is anonymous.
    useSalesOrder.mockReturnValue({
      data: so({
        source: 'history',
        customer_name: '',
        internal_note: 'A COMPANY NOT IN THE CRM / 300-NOSUCH',
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    expect(screen.getByText('A COMPANY NOT IN THE CRM / 300-NOSUCH')).toBeInTheDocument();
  });
});
