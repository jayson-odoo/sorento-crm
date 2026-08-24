/**
 * SalesOrderDetail - the demand-side twin of `PurchaseOrderDetail`.
 *
 * Two things this file is here to hold. The first is the CRUD standard: every section is
 * rendered, with an explicit empty message, so a panel that is missing means something rather
 * than reading as "not loaded yet". The record is TABBED now (General / Lines / Delivery, the
 * same shape as the user detail page), so "rendered" means "reachable on its tab" - which is
 * why almost every assertion below opens the tab it is about first.
 *
 * The second is specific to this screen. 11,006 of the sales orders in the system were
 * absorbed from a six-year AutoCount export and are closed history; the rest are live
 * commitments the plan is computed from. What the header used to carry - a "Committed demand"
 * / "Not committed (...)" line beside the status - is gone at the captain's request: the
 * status, the Source field and the Delivery tab already say all three of those things, and it
 * was a fourth restatement in the one place with least room for it.
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
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/sales-orders/so-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => searchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const useSalesOrder = vi.fn();
const updateSalesOrderMutateAsync = vi.fn();
vi.mock('../../../hooks/useSalesOrders', () => ({
  useSalesOrder: (...a: unknown[]) => useSalesOrder(...a),
  // The header's prev/next pager reads the same list the user came from. One row means no
  // neighbours, so the pager renders nothing and these tests stay about the record itself.
  useSalesOrders: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 25 } } }),
  useUpdateSalesOrder: () => ({ mutateAsync: updateSalesOrderMutateAsync, isPending: false }),
}));

const EMPTY_OPTS = { data: [], isLoading: false };
vi.mock('../../../hooks/useScmOptions', () => ({
  useOrderTypeOptions: () => ({
    data: [{ value: 'dealer', label: 'Dealer' }, { value: 'project', label: 'Project' }],
    isLoading: false,
  }),
  useCustomerOptions: () => ({
    data: [{ value: '300-R009', label: 'Rowenda Kitchen Sdn Bhd' }],
    isLoading: false,
  }),
  useProductOptions: () => EMPTY_OPTS,
  useWarehouseOptions: () => ({
    data: [
      { value: 'BRW-BB', label: 'Brickworks Batu Berendam' },
      { value: 'BRW-IB', label: 'Brickworks Iskandar' },
      { value: 'KL-01', label: 'Kuala Lumpur 01' },
    ],
    isLoading: false,
  }),
}));

vi.mock('../../hooks/useSalesAgentOptions', () => ({
  useSalesAgentOptions: () => ({
    options: [
      { value: 'agent-jeremy', label: 'JR001 · JEREMY' },
      { value: 'agent-cindy', label: 'CL002 · CINDY LEE' },
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
function openTab(name: 'General' | 'Lines' | 'Delivery') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

beforeEach(() => {
  cleanup();
  useSalesOrder.mockReset();
  // `planning_change_batch: null` - the shape every save's response carries, whether or not
  // it raised one. `handleSave` reads this key unconditionally.
  updateSalesOrderMutateAsync.mockReset().mockResolvedValue({ planning_change_batch: null });
  searchParams = new URLSearchParams();
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
      'Requested delivery', 'Priority', 'Total qty', 'Source',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('carries one tab per concern of the order, General first', () => {
    useSalesOrder.mockReturnValue({ data: so(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'General',
      'Lines',
      'Delivery',
    ]);
    expect(screen.getByRole('tab', { name: 'General' })).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('does not restate the order LOCATIONS on the header - a location belongs to a line', () => {
    // One order routinely ships from two warehouses, so "BRW-BB, KL-01" on the header said
    // less than the Lines tab, which says which line goes where.
    useSalesOrder.mockReturnValue({
      data: so({ stock_locations: ['BRW-BB', 'KL-01'] }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    const summary = screen.getByRole('region', { name: 'Order summary' });
    expect(within(summary).queryByText('Locations')).not.toBeInTheDocument();
    expect(within(summary).queryByText('BRW-BB, KL-01')).not.toBeInTheDocument();
  });

  it('shows each line\'s Location, falling back to "-" only for a line the API sent none for', () => {
    // The gap this guards: a line carrying `warehouse_code` must render the code, and a line
    // without one (closed history with no warehouse assigned) must read "-", not a blank cell
    // that is indistinguishable from a column that failed to render at all.
    useSalesOrder.mockReturnValue({
      data: so({
        lines: [
          {
            id: 'l-open', sku: 'SKU-OPEN', product_name: 'Open line', qty_ordered: 150,
            qty_delivered: 0, uom: 'L', warehouse_code: 'BRW-IB', line_status: 'open',
            required_date: null,
          },
          {
            id: 'l-closed', sku: 'SKU-CLOSED', product_name: 'Closed line', qty_ordered: 500,
            qty_delivered: 0, uom: 'L', warehouse_code: '', line_status: 'closed',
            required_date: '2026-01-10',
          },
        ],
        line_count: 2,
        open_line_count: 1,
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    const openRow = screen.getByText('SKU-OPEN').closest('tr');
    const closedRow = screen.getByText('SKU-CLOSED').closest('tr');
    expect(openRow).not.toBeNull();
    expect(closedRow).not.toBeNull();
    expect(within(openRow as HTMLElement).getByText('BRW-IB')).toBeInTheDocument();
    // The closed row has no location - it prints the same "-" every other empty cell on this
    // grid uses, never a silently blank <td>.
    expect(within(closedRow as HTMLElement).getAllByText('-').length).toBeGreaterThan(0);
  });

  it('renders every section even when the record is bare', () => {
    // The CRUD standard, asserted on the emptiest record the API can return: a section that
    // disappears on missing data reads as a page that failed to load. Tabbed now, so each one
    // is opened rather than expected to be on screen at once.
    useSalesOrder.mockReturnValue({
      data: so({ lines: [], total_qty: 0, committed_qty: 0, line_count: 0, open_line_count: 0 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    expect(screen.getByText('Note')).toBeInTheDocument();
    expect(screen.getByText(/No note\./)).toBeInTheDocument();

    openTab('Lines');
    expect(screen.getByText('Order lines')).toBeInTheDocument();
    expect(screen.getByText('This sales order has no lines.')).toBeInTheDocument();

    openTab('Delivery');
    expect(screen.getByText(/Nothing delivered yet/)).toBeInTheDocument();
  });
});

describe('SalesOrderDetail - the header says what the order IS, once', () => {
  it('states the status as a standard pill and nothing about "committed demand"', () => {
    // The indicator beside the status is gone: the status, the Source field and the Delivery
    // tab each already answer "is this still owed", and a fourth phrasing of it was the
    // captain's complaint about this header.
    useSalesOrder.mockReturnValue({ data: so(), isLoading: false, isError: false });
    renderDetail();

    const badge = screen.getByText('Open').closest('[data-slot="badge"]');
    expect(badge).not.toBeNull();
    expect(screen.queryByText('Committed demand')).not.toBeInTheDocument();
    expect(screen.queryByText(/Not committed/)).not.toBeInTheDocument();
  });

  it('still says an absorbed order is absorbed - on the Source field, where it belongs', () => {
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

    expect(screen.getByText('Absorbed history')).toBeInTheDocument();
    expect(screen.queryByText(/Not committed/)).not.toBeInTheDocument();
  });

  it('paints a cancelled order with the system-wide status colour', () => {
    useSalesOrder.mockReturnValue({
      data: so({ status: 'cancelled', committed_qty: 0, open_line_count: 0 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    const badge = screen.getByText('Cancelled').closest('[data-slot="badge"]');
    expect(badge?.className).toContain('bg-destructive');
    // `-soft` is the light-appearance palette this screen used to fork onto.
    expect(badge?.className).not.toContain('soft');
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
    openTab('Delivery');
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
    openTab('Delivery');
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
    openTab('Lines');
    expect(skuOrder()).toEqual(['SKU-B', 'SKU-C', 'SKU-A']);

    // 45 < 320 < 1200 - a numeric order, not the alphabetical one a formatted string gives.
    fireEvent.click(screen.getByRole('button', { name: 'Qty ordered' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-B', 'SKU-A']);

    fireEvent.click(screen.getByRole('button', { name: 'Qty ordered' }));
    expect(skuOrder()).toEqual(['SKU-A', 'SKU-B', 'SKU-C']);
  });

  it('orders by what has been delivered', () => {
    renderDetail();
    openTab('Lines');
    fireEvent.click(screen.getByRole('button', { name: 'Qty delivered' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-B', 'SKU-A']);
  });

  it('orders "Still owed" by the figure it shows, not by the order the lines arrived in', () => {
    // The computed column: 20, 45, 100 owed. Its order differs from every other column's,
    // so this fails if the header sorts on anything but the number in the cell.
    renderDetail();
    openTab('Lines');
    fireEvent.click(screen.getByRole('button', { name: 'Still owed' }));
    expect(skuOrder()).toEqual(['SKU-B', 'SKU-C', 'SKU-A']);

    fireEvent.click(screen.getByRole('button', { name: 'Still owed' }));
    expect(skuOrder()).toEqual(['SKU-A', 'SKU-C', 'SKU-B']);
  });

  it('orders the required date chronologically, not by how it is printed', () => {
    // Printed as 04 Jul / 15 Aug / 01 Sep, so a sort on the displayed text would read
    // 01, 04, 15 and put September first.
    renderDetail();
    openTab('Lines');
    fireEvent.click(screen.getByRole('button', { name: 'Delivery date' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-A', 'SKU-B']);
  });
});

describe('SalesOrderDetail - finding one product on a long order', () => {
  /**
   * A contract order runs to a couple of hundred lines and the question asked of it is almost
   * always "is this item on here, and how many": scrolling for it is the whole cost. The
   * search is over the lines already loaded - the order is the unit, so there is no request
   * and no paging to work across.
   */
  const LINES: SalesOrderLine[] = [
    {
      id: 'l-basin', sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm',
      qty_ordered: 320, qty_delivered: 0, uom: 'PCS', warehouse_code: 'BRW-BB',
      line_status: 'open', required_date: '2026-08-30',
    },
    {
      id: 'l-tap', sku: 'TAP-CHR-12', product_name: 'Chrome pillar tap',
      qty_ordered: 45, qty_delivered: 0, uom: 'PCS', warehouse_code: 'KL-01',
      line_status: 'open', required_date: '2026-09-04',
    },
  ];

  beforeEach(() => {
    useSalesOrder.mockReturnValue({
      data: so({ lines: LINES, line_count: 2, open_line_count: 2 }),
      isLoading: false,
      isError: false,
    });
  });

  it('filters the lines by product code', () => {
    renderDetail();
    openTab('Lines');

    fireEvent.change(screen.getByLabelText('Search lines'), { target: { value: 'tap-chr' } });

    expect(screen.getByText('TAP-CHR-12')).toBeInTheDocument();
    expect(screen.queryByText('CW-BASIN-450')).not.toBeInTheDocument();
  });

  it('filters by the description too - the code is not always what is remembered', () => {
    renderDetail();
    openTab('Lines');

    fireEvent.change(screen.getByLabelText('Search lines'), { target: { value: 'basin' } });

    expect(screen.getByText('CW-BASIN-450')).toBeInTheDocument();
    expect(screen.queryByText('TAP-CHR-12')).not.toBeInTheDocument();
  });

  it('says the search found nothing, rather than claiming the order has no lines', () => {
    renderDetail();
    openTab('Lines');

    fireEvent.change(screen.getByLabelText('Search lines'), { target: { value: 'zzz' } });

    expect(screen.getByText(/No line on this order matches that product/i)).toBeInTheDocument();
    expect(screen.queryByText('This sales order has no lines.')).not.toBeInTheDocument();
  });

  it('restores every line when the search is cleared', () => {
    renderDetail();
    openTab('Lines');

    fireEvent.change(screen.getByLabelText('Search lines'), { target: { value: 'basin' } });
    fireEvent.click(screen.getByRole('button', { name: 'Clear line search' }));

    expect(screen.getByText('CW-BASIN-450')).toBeInTheDocument();
    expect(screen.getByText('TAP-CHR-12')).toBeInTheDocument();
  });

  it('offers the standard Columns control, so the chosen columns survive the visit', () => {
    renderDetail();
    openTab('Lines');

    expect(screen.getByRole('button', { name: /Columns/ })).toBeInTheDocument();
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

describe('SalesOrderDetail - the agent', () => {
  it("shows the agent's code and the person it is annotated to", () => {
    useSalesOrder.mockReturnValue({
      data: so({ sales_agent_id: 'agent-jeremy', sales_agent_code: 'JR001', sales_agent_label: 'JEREMY' }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    expect(screen.getByText('JR001')).toBeInTheDocument();
    expect(screen.getByText('· JEREMY')).toBeInTheDocument();
  });

  it('reads as "-" when no order line-up names an agent', () => {
    useSalesOrder.mockReturnValue({
      data: so({ sales_agent_id: null, sales_agent_code: null, sales_agent_label: null }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    const summary = screen.getByRole('region', { name: 'Order summary' });
    const agentValue = screen.getByText('Agent').closest('div');
    expect(within(agentValue as HTMLElement).getByText('-')).toBeInTheDocument();
    expect(summary).toContainElement(agentValue);
  });
});

describe('SalesOrderDetail - view and edit are the same layout', () => {
  function record() {
    return so({
      sales_agent_id: 'agent-jeremy',
      sales_agent_code: 'JR001',
      sales_agent_label: 'JEREMY',
    });
  }

  it('has no Edit entry point while the record is still loading or missing', () => {
    useSalesOrder.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderDetail();
    expect(screen.queryByRole('button', { name: /^Edit$/ })).not.toBeInTheDocument();
  });

  it('swaps the header values for inputs in place, in the same field order, on Edit', () => {
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    // Field labels only. A pill is a VALUE and happens to be a `span.text-xs` too, so it is
    // excluded by its slot rather than by being kept a different size than every other pill.
    const labelOrder = () =>
      Array.from(
        screen
          .getByRole('region', { name: 'Order summary' })
          .querySelectorAll('label, span.text-xs:not([data-slot="badge"])'),
      ).map((el) => el.textContent);

    const before = labelOrder();
    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    const after = labelOrder();

    // Same labels, in the same order - editing swaps a value for an input, nothing moves.
    expect(after).toEqual(before);

    // The five editable fields are now real inputs, preloaded with the stored values.
    expect(screen.getByRole('combobox', { name: 'Customer' })).toHaveTextContent(
      'Rowenda Kitchen Sdn Bhd',
    );
    expect(screen.getByRole('combobox', { name: 'Order type' })).toHaveTextContent('Project');
    expect(screen.getByRole('combobox', { name: 'Priority' })).toHaveTextContent('Normal');
    expect(screen.getByRole('combobox', { name: 'Agent' })).toHaveTextContent('JR001 · JEREMY');
    expect(screen.getByLabelText('Requested delivery')).toHaveValue('2026-08-30');

    // Save / Cancel replace the pager and the way out; nothing else changed shape.
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit$/ })).not.toBeInTheDocument();
  });

  it('Cancel discards the session and returns to the read values, unsaved', () => {
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Edit$/ })).toBeInTheDocument();
    expect(updateSalesOrderMutateAsync).not.toHaveBeenCalled();
  });

  it('`?edit=1` opens the edit session on arrival, the same entry the list Pencil uses', () => {
    searchParams = new URLSearchParams('edit=1');
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it('a header-only save (no line touched) omits `lines` from the write, so the BE leaves them alone', async () => {
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    fireEvent.change(screen.getByLabelText('Requested delivery'), {
      target: { value: '2026-09-15' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByRole('button', { name: /^Edit$/ });
    expect(updateSalesOrderMutateAsync).toHaveBeenCalledWith({
      id: 'so-1',
      data: expect.objectContaining({
        requested_delivery_date: '2026-09-15',
        sales_agent_id: 'agent-jeremy',
      }),
    });
    const body = updateSalesOrderMutateAsync.mock.calls[0][0].data;
    expect(body).not.toHaveProperty('lines');
  });

  it('an explicit Agent clear sends `sales_agent_id: null`', async () => {
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    // `clearable` renders an explicit × once a value is selected - the agent select's own
    // stated requirement, since not every order names an agent. Scoped to the Agent combobox:
    // the Location select on the line grid is clearable too and has its own × once a line
    // carries a warehouse.
    const agentCombo = screen.getByRole('combobox', { name: 'Agent' });
    fireEvent.pointerDown(within(agentCombo).getByRole('button', { name: 'Clear selection' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByRole('button', { name: /^Edit$/ });
    expect(updateSalesOrderMutateAsync).toHaveBeenCalledWith({
      id: 'so-1',
      data: expect.objectContaining({ sales_agent_id: null }),
    });
  });

  it('editing a line quantity sends `lines`, replacing the whole set', async () => {
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    openTab('Lines');
    const qtyInputs = screen.getAllByDisplayValue('320');
    fireEvent.change(qtyInputs[0], { target: { value: '400' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByRole('button', { name: /^Edit$/ });
    const body = updateSalesOrderMutateAsync.mock.calls[0][0].data;
    // Every field the line already carried rides along unchanged - `id` so the BE matches
    // by id rather than SKU, and the location/date/UoM the order loaded with.
    expect(body.lines).toEqual([{
      id: 'l-1',
      sku: 'CW-BASIN-450',
      qty_ordered: 400,
      warehouse_code: 'BRW-BB',
      required_date: '2026-08-30',
      uom: 'PCS',
    }]);
  });

  it('the Location select is clearable', () => {
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    openTab('Lines');
    const locationCombo = screen.getByRole('combobox', { name: 'Location on CW-BASIN-450' });
    // Code-first, same as the read view's Location cell (`BRW-BB` above) - a code review
    // nit found this select's option label was the bare warehouse NAME, so the same value
    // read as a code in view and a name in edit.
    expect(locationCombo).toHaveTextContent('BRW-BB - Brickworks Batu Berendam');
    // Same clear affordance the Agent select already carries - a location, once picked,
    // must be unsettable, not just re-pickable.
    expect(within(locationCombo).getByRole('button', { name: 'Clear selection' }))
      .toBeInTheDocument();
  });

  it('editing a line\'s location, delivery date and UoM sends them with the line id', async () => {
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    openTab('Lines');

    fireEvent.click(screen.getByRole('combobox', { name: 'Location on CW-BASIN-450' }));
    fireEvent.click(await screen.findByRole('option', { name: 'BRW-IB - Brickworks Iskandar' }));

    fireEvent.change(screen.getByLabelText('Delivery date on CW-BASIN-450'), {
      target: { value: '2026-10-05' },
    });

    fireEvent.click(screen.getByRole('combobox', { name: 'UoM on CW-BASIN-450' }));
    fireEvent.click(await screen.findByRole('option', { name: 'Box' }));

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByRole('button', { name: /^Edit$/ });
    const body = updateSalesOrderMutateAsync.mock.calls[0][0].data;
    expect(body.lines).toEqual([{
      id: 'l-1',
      sku: 'CW-BASIN-450',
      qty_ordered: 320,
      warehouse_code: 'BRW-IB',
      required_date: '2026-10-05',
      uom: 'BOX',
    }]);
  });

  it('the UoM select is clearable, off the units-of-measure master', async () => {
    // The line UoM: was a free-text `Input`, is now a `SearchableSelect` sourced from
    // `getSalesOrderUoms` (mocked above) - clearable, since a line's own UoM override is
    // optional and falls back to the product's default when unset.
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    openTab('Lines');
    // The options load async (`getSalesOrderUoms`) - the trigger shows the placeholder
    // until they resolve and the value's label can be matched. Re-queried each poll
    // (not a captured reference) since the resolved options swap this node out.
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'UoM on CW-BASIN-450' })).toHaveTextContent(
        'Pieces',
      ),
    );
    const uomCombo = screen.getByRole('combobox', { name: 'UoM on CW-BASIN-450' });
    expect(within(uomCombo).getByRole('button', { name: 'Clear selection' })).toBeInTheDocument();
  });

  it('clearing the UoM select sends an explicit empty override - the product default', async () => {
    // `uom: ''` is the SAME wire value the free-text `Input` this select replaced already
    // sent on clear - the BE reads an empty override as "use the product's own default"
    // (`_upsert_lines`'s `ln.uom or None`), unchanged by this swap.
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    openTab('Lines');
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'UoM on CW-BASIN-450' })).toHaveTextContent(
        'Pieces',
      ),
    );
    const uomCombo = screen.getByRole('combobox', { name: 'UoM on CW-BASIN-450' });
    fireEvent.pointerDown(within(uomCombo).getByRole('button', { name: 'Clear selection' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await screen.findByRole('button', { name: /^Edit$/ });
    const body = updateSalesOrderMutateAsync.mock.calls[0][0].data;
    expect(body.lines[0].uom).toBe('');
  });

  it('shows the planning-change banner when a save raises one, linking to it, and it clears on the next edit', async () => {
    // Same envelope key the SO-book upload's own preview surfaces
    // (`OutstandingUploadDialog`'s `PlanningChangeBatchCard`) - PLAN-so-book-diff
    // -replanning.md section 2.
    updateSalesOrderMutateAsync.mockResolvedValue({
      planning_change_batch: { id: 'batch-77', order_count: 1, line_count: 2 },
    });
    useSalesOrder.mockReturnValue({ data: record(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Planning changes raised on 2 lines')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review' })).toHaveAttribute(
      'href',
      '/project-sales/planning-changes/batch-77',
    );

    // A fresh edit session clears the stale notice - it describes the LAST save, not this one.
    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    expect(screen.queryByText('Planning changes raised on 2 lines')).not.toBeInTheDocument();
  });
});
