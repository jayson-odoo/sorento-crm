/**
 * PurchaseOrderDetail - the supply-side twin of `SalesOrderDetail`, and held to the same
 * shape on purpose: the captain's instruction was that the two books must look very alike,
 * one buying and one selling.
 *
 * Two things this file holds. The first is the CRUD standard: every section is rendered, with
 * an explicit empty message, so a panel that is missing means something rather than reading
 * as "not loaded yet". The record is TABBED (General / Lines / Goods receipt), so "rendered"
 * means "reachable on its tab" - which is why almost every assertion below opens the tab it
 * is about first.
 *
 * The second is the wording. There is no `on_order` status in the database: being on order is
 * DERIVED, and the screen used to say it three times over (a status chip, an "On order" line
 * beside it, and an "On order: Yes/No" field). It now says it once, in the two words the
 * client reads all day - Outstanding and Completed.
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
  usePathname: () => '/scm/purchase-orders/po-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => searchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const usePurchaseOrder = vi.fn();
const updatePurchaseOrderMutateAsync = vi.fn();
vi.mock('../../../hooks/usePurchaseOrders', () => ({
  usePurchaseOrder: (...a: unknown[]) => usePurchaseOrder(...a),
  // The header's prev/next pager reads the same list the user came from. One row means no
  // neighbours, so the pager renders nothing and these tests stay about the record itself.
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
  updatePurchaseOrderMutateAsync.mockReset().mockResolvedValue({});
  searchParams = new URLSearchParams();
});

describe('PurchaseOrderDetail - states', () => {
  it('shows a skeleton and the way back while loading', () => {
    usePurchaseOrder.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderDetail();
    expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy();
    // The way back is present even before the record is: a slow read must not trap anybody.
    expect(screen.getByText('Back to purchase orders')).toBeInTheDocument();
  });

  it('names what is missing rather than rendering an empty shell', () => {
    usePurchaseOrder.mockReturnValue({ data: null, isLoading: false, isError: true });
    renderDetail();
    expect(screen.getByText('Purchase order not found')).toBeInTheDocument();
    expect(screen.getByText('Back to purchase orders')).toBeInTheDocument();
  });

  it('carries one tab per concern of the order, General first', () => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'General',
      'Lines',
      'Goods receipt',
    ]);
    expect(screen.getByRole('tab', { name: 'General' })).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('groups the summary into three cards of at most two columns each', () => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    renderDetail();

    for (const name of ['Order', 'Supplier', 'Totals']) {
      const region = screen.getByRole('region', { name });
      expect(region).toBeInTheDocument();
      // Never a third column: the four-across grid is what made it a wall.
      expect(region.className).toContain('sm:grid-cols-2');
      expect(region.className).not.toMatch(/grid-cols-[34]/);
    }
  });

  it('renders the document number, the supplier and every summary field', () => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getByText('PO-2026/07-0009')).toBeInTheDocument();
    // Per card, because "Supplier" is now both a card TITLE and a field label inside it.
    const fields: Record<string, string[]> = {
      Order: ['Order date', 'Delivery date', 'Source', 'Currency'],
      Supplier: ['Supplier', 'Supplier code'],
      Totals: ['Total amount', 'Total qty', 'Outstanding qty', 'Lines'],
    };
    for (const [card, labels] of Object.entries(fields)) {
      const region = screen.getByRole('region', { name: card });
      for (const label of labels) {
        expect(within(region).getByText(label)).toBeInTheDocument();
      }
    }
    expect(within(screen.getByRole('region', { name: 'Supplier' })).getByText('Acme Sanitary'))
      .toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Supplier' })).getByText('SUP-ACME'))
      .toBeInTheDocument();
    expect(screen.getByText('Reorder recommendation')).toBeInTheDocument();
  });

  it('states what the order is worth, and a dash when nobody priced it', () => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    const { unmount } = renderDetail();
    expect(
      within(screen.getByRole('region', { name: 'Totals' })).getByText('RM 31,985.00'),
    ).toBeInTheDocument();
    unmount();

    // Not RM 0.00: an order nobody priced is not an order worth nothing.
    usePurchaseOrder.mockReturnValue({
      data: po({
        total_amount: null,
        lines: [
          {
            id: 'l-1', sku: 'CW-BASIN-450', product_name: 'Basin', qty_ordered: 320,
            qty_received: 0, uom: 'PCS', line_status: 'open',
          },
        ],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    const amount = screen.getByText('Total amount').closest('div');
    expect(within(amount as HTMLElement).getByText('-')).toBeInTheDocument();
  });

  it('prices a USD order in USD, never in ringgit', () => {
    // The book is 8,438 lines USD against 4,186 MYR, so "RM 12.50" against a USD purchase
    // order is a wrong number stated as a fact.
    usePurchaseOrder.mockReturnValue({
      data: po({ currency: 'USD', lines: [{ ...po().lines[0], currency: 'USD' }] }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    const totals = screen.getByRole('region', { name: 'Totals' });
    expect(within(totals).getByText('USD 31,985.00')).toBeInTheDocument();
    expect(within(totals).queryByText(/^RM /)).toBeNull();
  });

  it('shows Outstanding qty even when it equals the total', () => {
    // It used to appear only when the two differed. A field that comes and goes is worse
    // than a repeated figure: the reader has to infer from its ABSENCE that nothing has
    // arrived yet.
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    renderDetail();

    const totals = screen.getByRole('region', { name: 'Totals' });
    expect(within(totals).getByText('Outstanding qty')).toBeInTheDocument();
    // Ordered 320, received 0 - the same figure twice, deliberately.
    expect(within(totals).getAllByText('320')).toHaveLength(2);
  });

  it('renders the empty-lines state when the PO has no lines', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ lines: [], line_count: 0 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');
    expect(screen.getByText('This purchase order has no lines.')).toBeInTheDocument();
  });
});

describe('PurchaseOrderDetail - how the status is worded', () => {
  it('says Outstanding once, and never "On order"', () => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getAllByText('Outstanding')).toHaveLength(1);
    expect(screen.queryByText('On order')).toBeNull();
    expect(screen.queryByText(/Not on order/)).toBeNull();
    expect(screen.queryByText('Active')).toBeNull();
  });

  it('does not call a closed historical order a draft - it calls it Completed', () => {
    // An imported 2020 order is closed and fully received. "Not on order (draft)" said
    // somebody had yet to confirm a purchase that arrived six years ago.
    usePurchaseOrder.mockReturnValue({
      data: po({ status: 'closed', source: 'import', is_on_order: false }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Imported history')).toBeInTheDocument();
    expect(screen.queryByText('Closed')).toBeNull();
  });

  it('still calls a draft a draft', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ status: 'draft_recommendation', is_on_order: false }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    expect(screen.getByText('Draft')).toBeInTheDocument();
  });
});

describe('PurchaseOrderDetail - the goods-receipt tab', () => {
  it('surfaces the goods-receipt reference once a GR exists', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ status: 'received', gr_reference: 'GR-2026/07-0003' }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Goods receipt');
    expect(screen.getByText('GR-2026/07-0003')).toBeInTheDocument();
  });

  it('does not send the reader to a list button that no longer exists', () => {
    // The empty state used to read "Create one from the purchase orders list" - and that
    // button came off the list. Pointing at a control that is not there is worse than
    // saying nothing.
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    renderDetail();
    openTab('Goods receipt');

    expect(screen.getByText(/Nothing received yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/from the purchase orders list/i)).toBeNull();
  });

  it('reports a part-received order as part-received', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({
        lines: [{ ...po().lines[0], qty_received: 120 }],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Goods receipt');

    expect(screen.getByText(/120 of 320 received/i)).toBeInTheDocument();
    expect(screen.getByText(/200 still to arrive/i)).toBeInTheDocument();
  });
});

describe('PurchaseOrderDetail - the lines grid', () => {
  const SORT_LINES: PurchaseOrderLine[] = [
    {
      id: 'l-b', sku: 'SKU-B', product_name: 'Beta basin', qty_ordered: 320, qty_received: 300,
      uom: 'PCS', line_status: 'open',
    },
    {
      id: 'l-c', sku: 'SKU-C', product_name: 'Gamma tap', qty_ordered: 45, qty_received: 0,
      uom: 'PCS', line_status: 'open',
    },
    {
      id: 'l-a', sku: 'SKU-A', product_name: 'Alpha pan', qty_ordered: 1200, qty_received: 1100,
      uom: 'PCS', line_status: 'closed',
    },
  ];

  const skuOrder = () =>
    screen
      .getAllByRole('row')
      .map((row) => row.textContent ?? '')
      .filter((text) => text.includes('SKU-'))
      .map((text) => text.match(/SKU-[A-Z]/)?.[0] ?? '');

  beforeEach(() => {
    usePurchaseOrder.mockReturnValue({
      data: po({ lines: SORT_LINES, line_count: 3 }),
      isLoading: false,
      isError: false,
    });
  });

  it('carries the money columns the order was written with', () => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');

    const row = screen.getByText('CW-BASIN-450').closest('tr') as HTMLElement;
    expect(within(row).getByText('RM 100.00')).toBeInTheDocument();
    expect(within(row).getByText('RM 15.00')).toBeInTheDocument();
    expect(within(row).getByText('RM 31,985.00')).toBeInTheDocument();
    // Outstanding is computed from the two columns beside it, so it cannot disagree: 320
    // ordered, 0 received, 320 still to come - the same figure printed twice on purpose.
    expect(within(row).getAllByText('320')).toHaveLength(2);
  });

  it('words a line the same two ways the header pill does', () => {
    renderDetail();
    openTab('Lines');

    const openRow = screen.getByText('SKU-C').closest('tr') as HTMLElement;
    const closedRow = screen.getByText('SKU-A').closest('tr') as HTMLElement;
    expect(within(openRow).getByText('Outstanding')).toBeInTheDocument();
    expect(within(closedRow).getByText('Completed')).toBeInTheDocument();
  });

  it('orders by quantity, ascending then descending, when the header is clicked', () => {
    renderDetail();
    openTab('Lines');
    expect(skuOrder()).toEqual(['SKU-B', 'SKU-C', 'SKU-A']);

    // 45 < 320 < 1200 - numeric, not the alphabetical order a formatted string would give.
    fireEvent.click(screen.getByRole('button', { name: 'Qty ordered' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-B', 'SKU-A']);

    fireEvent.click(screen.getByRole('button', { name: 'Qty ordered' }));
    expect(skuOrder()).toEqual(['SKU-A', 'SKU-B', 'SKU-C']);
  });

  it('orders by what has been received', () => {
    renderDetail();
    openTab('Lines');
    fireEvent.click(screen.getByRole('button', { name: 'Qty received' }));
    expect(skuOrder()).toEqual(['SKU-C', 'SKU-B', 'SKU-A']);
  });

  it('searches the lines already loaded, and says so when nothing matches', () => {
    renderDetail();
    openTab('Lines');

    fireEvent.change(screen.getByLabelText('Search lines'), { target: { value: 'SKU-C' } });
    expect(skuOrder()).toEqual(['SKU-C']);

    fireEvent.change(screen.getByLabelText('Search lines'), { target: { value: 'nothing' } });
    expect(
      screen.getByText('No line on this order matches that product.'),
    ).toBeInTheDocument();
  });

  it('totals the quantities and the money under the columns they sum', () => {
    renderDetail();
    openTab('Lines');

    const footer = document.querySelector('tfoot') as HTMLElement;
    expect(footer).toBeTruthy();
    // 320 + 45 + 1200 ordered, 300 + 0 + 1100 received. Outstanding is 20 + 45 + 0 = 65,
    // NOT 165: the 1200/1100 line is CLOSED, and a closed line has nothing still to arrive
    // however the two quantities read. `qty_received` is left at 1100 rather than being
    // back-filled to 1200 - what actually arrived is what it is.
    expect(within(footer).getByText('1,565')).toBeInTheDocument();
    expect(within(footer).getByText('1,400')).toBeInTheDocument();
    expect(within(footer).getByText('65')).toBeInTheDocument();
  });

  /**
   * The sales book's own defect, on this side of the same rule (SO397450): a book re-upload
   * closes a line by absence without knowing what arrived, so `qty_received` stays where it
   * is and `ordered - received` would report the whole quantity as still coming.
   */
  it('reads 0 outstanding on a CLOSED line, however little was received', () => {
    usePurchaseOrder.mockReturnValue({
      data: po({ lines: SORT_LINES, line_count: 3 }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    const closed = screen.getByText('SKU-A').closest('tr') as HTMLElement;
    expect(within(closed).getByText('1,200')).toBeInTheDocument();
    expect(within(closed).getByText('1,100')).toBeInTheDocument();
    // Not 100: the line is closed, so nothing on it is still to arrive.
    expect(within(closed).queryByText('100')).not.toBeInTheDocument();
  });
});

describe('PurchaseOrderDetail - correcting the order in place', () => {
  beforeEach(() => {
    usePurchaseOrder.mockReturnValue({ data: po(), isLoading: false, isError: false });
  });

  it('offers Edit, and swaps the values for inputs in the SAME cards', () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    // The same three cards, in the same order, with the same labels.
    for (const name of ['Order', 'Supplier', 'Totals']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
    expect(screen.getByLabelText('Order date')).toBeInTheDocument();
    expect(screen.getByLabelText('Delivery date')).toBeInTheDocument();
    expect(screen.getByText('Nothing is written until you press Save.')).toBeInTheDocument();
  });

  it('opens the session straight away on ?edit=1', () => {
    searchParams = new URLSearchParams('edit=1');
    renderDetail();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it('writes the header alone when no line moved', async () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Order date'), { target: { value: '2026-05-04' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updatePurchaseOrderMutateAsync).toHaveBeenCalled());
    const payload = updatePurchaseOrderMutateAsync.mock.calls[0][0];
    expect(payload.data.order_date).toBe('2026-05-04');
    expect(payload.data.supplier_code).toBe('SUP-ACME');
    // `lines` is left off entirely: sending it would have the backend re-upsert every line
    // of the order for nothing.
    expect(payload.data.lines).toBeUndefined();
  });

  it('sends every line once one of them moved, price and discount included', async () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    openTab('Lines');
    fireEvent.change(screen.getByLabelText('Unit price on CW-BASIN-450'), {
      target: { value: '88.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updatePurchaseOrderMutateAsync).toHaveBeenCalled());
    const [line] = updatePurchaseOrderMutateAsync.mock.calls[0][0].data.lines;
    expect(line).toMatchObject({
      id: 'l-1',
      sku: 'CW-BASIN-450',
      qty_ordered: 320,
      unit_price: '88.5',
      // Untouched keys still ride along, carrying exactly what the order loaded with.
      discount: '15.00',
      uom: 'PCS',
      warehouse_code: 'WH-KL',
      expected_date: '2026-07-30',
    });
  });

  it('recomputes the line total from the parts once a priced line is touched', () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    openTab('Lines');

    // The stated total wins until one of the figures it was charged ON is edited.
    fireEvent.change(screen.getByLabelText('Qty ordered on CW-BASIN-450'), {
      target: { value: '10' },
    });
    const row = screen.getByLabelText('Qty ordered on CW-BASIN-450').closest('tr') as HTMLElement;
    // 10 x 100.00 - 15.00
    expect(within(row).getByText('RM 985.00')).toBeInTheDocument();
    expect(within(row).queryByText('RM 31,985.00')).toBeNull();
  });

  it('refuses a line with no quantity rather than writing it', async () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    openTab('Lines');
    fireEvent.change(screen.getByLabelText('Qty ordered on CW-BASIN-450'), {
      target: { value: '0' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(
      screen.getByText('Every line needs a product and a quantity above zero.'),
    ).toBeInTheDocument();
    expect(updatePurchaseOrderMutateAsync).not.toHaveBeenCalled();
  });

  it('leaves the record alone on Cancel', () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Order date'), { target: { value: '2026-05-04' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(updatePurchaseOrderMutateAsync).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });
});
