/**
 * SCM M4 Slice B - PurchaseOrdersList (AC-M4.6), brought to parity with the sales-order list.
 * - rows render with ONE status pill worded the way the book is read: Outstanding /
 *     Completed / Draft / Cancelled. The separate "On order" icon column is gone, and so is
 *     the per-row "Create GR" button
 * - PO number is a hyperlink to the detail page (human number, no UUID) and the whole ROW
 *     opens it
 * - select-all selects ALL rows (drafts + active); the Actions dropdown shows
 *     "Confirm N drafts" scoped to the draft subset and is HIDDEN when the
 *     selection has no drafts
 * - loading / empty / error states, with an over-filtered book saying something different
 *     from a book nobody has ever uploaded
 *
 * Data + action hooks are mocked; the dropdown-menu module is stubbed inline so
 * the bulk Actions item is assertable without a Radix portal.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

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

const routerPush = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/purchase-orders',
  useRouter: () => ({ push: routerPush }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: any) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuCheckboxItem: ({ children }: any) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: any) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: any) => <>{children}</>,
  DropdownMenuSub: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: any) => <div>{children}</div>,
}));

const usePurchaseOrders = vi.fn();
const confirmMut = { mutateAsync: vi.fn(), isPending: false };
const createGrMut = { mutateAsync: vi.fn(), isPending: false };
const bulkDeleteMut = { mutateAsync: vi.fn(), isPending: false };
vi.mock('../../hooks/usePurchaseOrders', () => ({
  usePurchaseOrders: (...a: unknown[]) => usePurchaseOrders(...a),
}));
vi.mock('../../hooks/usePurchaseOrderActions', () => ({
  usePurchaseOrderActions: () => ({
    confirm: confirmMut,
    createGr: createGrMut,
    bulkDelete: bulkDeleteMut,
  }),
}));

// The upload dialog is exercised by its own suite; here we only care that this screen
// mounts it for the PURCHASE-ORDER book and refreshes itself once an upload is queued.
type UploadDialogProps = {
  open: boolean;
  kind: string;
  onQueued?: () => void;
};
let uploadProps: UploadDialogProps | null = null;
vi.mock('../../reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: (props: UploadDialogProps) => {
    uploadProps = props;
    return props.open ? <div>{`outstanding-upload:${props.kind}`}</div> : null;
  },
}));

import PurchaseOrdersList from './PurchaseOrdersList';
import type { PurchaseOrder } from '../../types/scm.types';

// The override is optional: the product-cost tests care about the banner, not about the row,
// and `po()` reading as "one plain purchase order" is the point. Without the default those
// six calls are a type error the test runner never sees, because vitest does not type-check.
function po(over: Partial<PurchaseOrder> = {}): PurchaseOrder {
  return {
    id: 'po-1',
    po_number: 'PO-DRAFT-0001',
    supplier_code: 'SUP-ACME',
    supplier_name: 'Acme Sanitary',
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    status: 'draft_recommendation',
    order_date: '2026-07-16',
    expected_date: null,
    total_qty: 320,
    line_count: 1,
    lines: [],
    created_at: '2026-07-16T00:00:00',
    ...over,
  } as PurchaseOrder;
}

/** Stable across a render so the upload's refresh is assertable. */
const refetch = vi.fn();

function mockList(rows: PurchaseOrder[], over: Record<string, unknown> = {}) {
  usePurchaseOrders.mockReturnValue({
    data: { data: rows, pagination: { page: 1, total: rows.length } },
    isLoading: false,
    isFetching: false,
    refetch,
    ...over,
  });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  uploadProps = null;
});

describe('PurchaseOrdersList - states (AC-M4.6)', () => {
  it('renders the never-uploaded empty state when nothing is filtered', () => {
    mockList([], { data: { data: [], pagination: { page: 1, total: 0 } } });
    render(<PurchaseOrdersList />);
    // The screen opens on Outstanding, which IS a filter - so the honest empty state only
    // appears once the reader has widened it to All.
    fireEvent.click(screen.getByRole('radio', { name: 'All' }));
    expect(screen.getByText(/No purchase orders yet/i)).toBeInTheDocument();
  });

  it('says an over-filtered book is filtered, not empty', () => {
    // An empty book and an over-filtered one look identical in the grid. A buyer whose
    // Outstanding view is empty has not lost his purchase orders; they are all completed.
    mockList([], { data: { data: [], pagination: { page: 1, total: 0 } } });
    render(<PurchaseOrdersList />);
    expect(
      screen.getByText(/No purchase order matches this search and filter/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No purchase orders yet/i)).toBeNull();
  });

  it('renders the loading skeleton state', () => {
    usePurchaseOrders.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: vi.fn() });
    const { container } = render(<PurchaseOrdersList />);
    expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy();
  });
});

/** The grid's own rows. The All / Outstanding / Completed toggle carries the SAME two
 *  words on purpose, so an unscoped `getByText('Outstanding')` would find the control
 *  rather than the pill it is meant to be reading. */
const rows = () => within(document.querySelector('tbody') as HTMLElement);

describe('PurchaseOrdersList - draft + active rows (AC-M4.6)', () => {
  it('words a draft as Draft and an on-order PO as Outstanding, in ONE column', () => {
    mockList([
      po({ id: 'po-draft', po_number: 'PO-DRAFT-0001', status: 'draft_recommendation' }),
      po({ id: 'po-active', po_number: 'PO-2026/07-0009', status: 'active', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    expect(screen.getByText('PO-DRAFT-0001')).toBeInTheDocument();
    expect(screen.getByText('PO-2026/07-0009')).toBeInTheDocument();
    expect(rows().getByText('Draft')).toBeInTheDocument();
    expect(rows().getByText('Outstanding')).toBeInTheDocument();
    // The old "On order" / "Not on order" column said the same thing again in different
    // words, in a column whose only two values are the two the pill now carries.
    expect(screen.queryByText('On order')).toBeNull();
    expect(screen.queryByText('Not on order')).toBeNull();
  });

  it('words a live order with nothing left to come as Completed', () => {
    mockList([
      po({ id: 'po-done', po_number: 'PO-2020/03-0004', status: 'closed', is_on_order: false }),
    ]);
    render(<PurchaseOrdersList />);
    // Not "Closed", and not "Received": a 2020 order that arrived six years ago is
    // completed, and the captain asked for exactly these two words.
    expect(rows().getByText('Completed')).toBeInTheDocument();
    expect(screen.queryByText('Closed')).toBeNull();
  });

  it('opens the order when the row is clicked, carrying the list query', () => {
    mockList([po({ id: 'po-row-click', po_number: 'PO-2026/07-0011', status: 'active' })]);
    render(<PurchaseOrdersList />);
    routerPush.mockClear();

    fireEvent.click(screen.getByText('Acme Sanitary'));

    expect(routerPush).toHaveBeenCalledTimes(1);
    const href = routerPush.mock.calls[0][0] as string;
    expect(href.startsWith('/scm/purchase-orders/po-row-click')).toBe(true);
    expect(href).toContain('page=1');
  });

  it('renders the PO number as a hyperlink to the detail page', () => {
    mockList([po({ id: 'po-abc', po_number: 'PO-DRAFT-0002' })]);
    render(<PurchaseOrdersList />);
    const link = screen.getByRole('link', { name: /PO-DRAFT-0002/ });
    // The link carries the active list query so the detail page's prev/next pager walks the
    // SAME filtered, sorted page the user was reading.
    const href = link.getAttribute('href') ?? '';
    expect(href.startsWith('/scm/purchase-orders/po-abc')).toBe(true);
    expect(href).toContain('page=1');
  });

  it('offers no per-row Create GR on any status', () => {
    // Recording what arrived is a receiving decision made against the delivery in hand, not
    // a button beside a row on a list of 13,000 orders - the same reason "Create DO" came
    // off the sales-order list.
    mockList([
      po({ id: 'po-draft', status: 'draft_recommendation' }),
      po({ id: 'po-active', po_number: 'PO-2026/07-0009', status: 'active', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    expect(screen.queryByRole('button', { name: /Create GR/i })).toBeNull();
  });
});

describe('PurchaseOrdersList - select-all + bulk Confirm gating (AC-M4.6)', () => {
  it('select-all selects ALL rows and Confirm is scoped to the draft subset', () => {
    mockList([
      po({ id: 'po-draft-1', status: 'draft_recommendation' }),
      po({ id: 'po-draft-2', po_number: 'PO-DRAFT-0002', status: 'draft_recommendation' }),
      po({ id: 'po-active', po_number: 'PO-2026/07-0009', status: 'active', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    // All rows selectable (drafts + active).
    expect(screen.getAllByLabelText('Select row')).toHaveLength(3);
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    // Confirm label counts only the 2 drafts, not the active PO.
    expect(screen.getByRole('button', { name: /Confirm 2 drafts/i })).toBeInTheDocument();
  });

  it('HIDES the Actions Confirm item when the selection has no drafts', () => {
    mockList([po({ id: 'po-active', po_number: 'PO-2026/07-0009', status: 'active', is_on_order: true })]);
    render(<PurchaseOrdersList />);
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    expect(screen.queryByRole('button', { name: /Confirm .* draft/i })).toBeNull();
  });

  it('confirming a draft selection opens the confirm dialog then calls the mutation', async () => {
    confirmMut.mutateAsync.mockResolvedValue({ confirmed_count: 1 });
    mockList([po({ id: 'po-draft-1', status: 'draft_recommendation' })]);
    render(<PurchaseOrdersList />);
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /Confirm 1 draft/i }));
    // The count-bearing confirm dialog appears.
    expect(screen.getByText(/Confirm purchase orders\?/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Confirm POs$/ }));
    expect(confirmMut.mutateAsync).toHaveBeenCalledWith(['po-draft-1']);
  });
});

describe('PurchaseOrdersList - bulk delete (captain, 20 Aug)', () => {
  it('offers Delete for an all-active selection (no drafts) with the count in the label', () => {
    mockList([
      po({ id: 'po-active-1', po_number: 'PO-2026/07-0001', status: 'active', is_on_order: true }),
      po({ id: 'po-active-2', po_number: 'PO-2026/07-0002', status: 'active', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    expect(screen.getByRole('button', { name: /Delete 2/i })).toBeInTheDocument();
  });

  it('opens a destructive confirm dialog naming the selected count, then deletes on confirm', async () => {
    bulkDeleteMut.mutateAsync.mockResolvedValue({ deleted: 2, unplaced_rows: 0 });
    mockList([
      po({ id: 'po-1', po_number: 'PO-2026/07-0001', status: 'active', is_on_order: true }),
      po({ id: 'po-2', po_number: 'PO-2026/07-0002', status: 'active', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /Delete 2/i }));

    expect(screen.getByText('Confirm delete')).toBeInTheDocument();
    expect(
      screen.getByText(/Delete 2 purchase orders\? This action cannot be undone\./i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Delete$/ }));
    await waitFor(() => {
      expect(bulkDeleteMut.mutateAsync).toHaveBeenCalledWith(['po-1', 'po-2']);
    });
  });

  it('singular copy for a one-row selection', () => {
    mockList([po({ id: 'po-only', status: 'active', is_on_order: true })]);
    render(<PurchaseOrdersList />);
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /Delete 1/i }));
    expect(
      screen.getByText(/Delete 1 purchase order\? This action cannot be undone\./i),
    ).toBeInTheDocument();
  });
});

// ── the outstanding PURCHASE-ORDER book (AC-A6) ─────────────────────────────
// The extract spec defines two books, outstanding SO and outstanding PO. The PO book
// says what is already on order, and it belongs to the actor working THIS screen, not
// to the planner on the reorder screen. Nothing loads it unless this toolbar opens it.

describe('PurchaseOrdersList - upload the order book', () => {
  /**
   * Refresh and the book upload are two secondary actions, so the shared toolbar collapses
   * them into one "Actions" dropdown - the same shape as the sales-order list, and the
   * reason this toolbar no longer wraps onto a second row. Radix's trigger opens on
   * pointerdown rather than click, the same as `openFilters()` further down.
   */
  const openActions = () => {
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
  };

  it('opens the outstanding PURCHASE-ORDER upload from the toolbar', () => {
    mockList([po({ id: 'po-draft-1' })]);
    render(<PurchaseOrdersList />);
    expect(screen.queryByText(/^outstanding-upload:/)).toBeNull();

    openActions();
    fireEvent.click(screen.getByRole('button', { name: /Upload purchase orders/i }));
    // The kind is the whole point: this screen must not open the sales-order book.
    expect(screen.getByText('outstanding-upload:purchase-orders')).toBeInTheDocument();
  });

  it('offers the same upload from the empty state', () => {
    // A fresh install has no POs at all - the upload has to be reachable from the
    // state the user actually lands in, not only from a populated list.
    mockList([], { data: { data: [], pagination: { page: 1, total: 0 } } });
    render(<PurchaseOrdersList />);

    openActions();
    fireEvent.click(screen.getByRole('button', { name: /Upload purchase orders/i }));
    expect(screen.getByText('outstanding-upload:purchase-orders')).toBeInTheDocument();
  });

  it('refreshes the list once the upload is queued', () => {
    /**
     * The upload writes on the worker now, so this screen has no counts to report: what it
     * CAN do is drop what it holds, so the rows appear as soon as the job lands rather than
     * after a manual reload. The "queued" message belongs to the dialog, which is the thing
     * that knows the job id.
     */
    mockList([po({ id: 'po-draft-1' })]);
    render(<PurchaseOrdersList />);
    openActions();
    fireEvent.click(screen.getByRole('button', { name: /Upload purchase orders/i }));
    refetch.mockClear();

    const onQueued = uploadProps?.onQueued;
    if (!onQueued) throw new Error('the screen mounted the upload dialog without an onQueued');
    act(() => {
      onQueued();
    });

    expect(refetch).toHaveBeenCalled();
  });
});

describe('PurchaseOrdersList - find a SKU and what we last paid for it', () => {
  // > "in PO can I search this product also ... I want to see its PO and its last purchase
  // >  price (unit cost), so at least I know if it doesn't appear in planning, I can check
  // >  from here"

  const openFilters = async () => {
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Filters/ }), { button: 0 });
    await screen.findByLabelText('Product code');
  };

  it('sends the product code to the list query', async () => {
    mockList([po()]);
    render(<PurchaseOrdersList />);
    await openFilters();

    fireEvent.change(screen.getByLabelText('Product code'), {
      target: { value: ' mwc7624-rl-s10 ' },
    });
    fireEvent.blur(screen.getByLabelText('Product code'));

    await waitFor(() => {
      const last = usePurchaseOrders.mock.calls[usePurchaseOrders.mock.calls.length - 1][0];
      expect(last).toMatchObject({ productCode: 'mwc7624-rl-s10' });
    });
  });

  it('reports what we last paid, from whom and on which order', async () => {
    mockList([po()], {
      data: {
        data: [po()],
        pagination: { page: 1, total: 1 },
        product_cost: {
          unit_cost: 42,
          currency: 'MYR',
          po_number: '202606-S0024',
          issue_date: '2026-06-01',
          supplier_name: 'Kaiping Kaixin',
        },
      },
    });
    render(<PurchaseOrdersList />);
    await openFilters();
    fireEvent.change(screen.getByLabelText('Product code'), { target: { value: 'SKU-1' } });
    fireEvent.blur(screen.getByLabelText('Product code'));

    const banner = await screen.findByRole('status', { name: 'Last purchase price' });
    expect(banner).toHaveTextContent('Last paid');
    expect(banner).toHaveTextContent('RM 42');
    expect(banner).toHaveTextContent('Kaiping Kaixin');
    expect(banner).toHaveTextContent('202606-S0024');
  });

  it('says nobody has ever priced it, which is why the plan has no cost', async () => {
    // The whole point of the screen for this user: never-bought and bought-for-nothing are
    // different answers, and a plan line with no cost is explained by the first.
    mockList([], {
      data: { data: [], pagination: { page: 1, total: 0 }, product_cost: null },
    });
    render(<PurchaseOrdersList />);
    await openFilters();
    fireEvent.change(screen.getByLabelText('Product code'), { target: { value: 'SKU-NEW' } });
    fireEvent.blur(screen.getByLabelText('Product code'));

    const banner = await screen.findByRole('status', { name: 'Last purchase price' });
    expect(banner).toHaveTextContent(/No purchase order records a price for/i);
    expect(banner).toHaveTextContent('SKU-NEW');
  });

  it('reads a recorded zero as free, not as missing', async () => {
    mockList([po()], {
      data: {
        data: [po()],
        pagination: { page: 1, total: 1 },
        product_cost: {
          unit_cost: 0,
          currency: 'MYR',
          po_number: '202606-S0024',
          issue_date: '2026-06-01',
          supplier_name: 'Kaiping Kaixin',
        },
      },
    });
    render(<PurchaseOrdersList />);
    await openFilters();
    fireEvent.change(screen.getByLabelText('Product code'), { target: { value: 'SKU-FREE' } });
    fireEvent.blur(screen.getByLabelText('Product code'));

    const banner = await screen.findByRole('status', { name: 'Last purchase price' });
    expect(banner).toHaveTextContent('RM 0');
    expect(banner).not.toHaveTextContent(/No purchase order records a price/i);
  });

  it('shows nothing about cost until a product is asked for', () => {
    mockList([po()]);
    render(<PurchaseOrdersList />);

    expect(screen.queryByRole('status', { name: 'Last purchase price' })).toBeNull();
  });
});

// ── the Outstanding / All / Completed toggle (the captain, 20 Aug) ─────────
// "how do i know the open PO / outstanding PO" - a glance-able control, defaulting to
// Outstanding, mapping straight onto the list's `outstanding` query param.

describe('PurchaseOrdersList - Outstanding / All / Completed toggle', () => {
  it('defaults to Outstanding and sends outstanding: true on the first call', () => {
    mockList([po()]);
    render(<PurchaseOrdersList />);

    const toggle = screen.getByRole('radio', { name: 'Outstanding' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    const last = usePurchaseOrders.mock.calls[usePurchaseOrders.mock.calls.length - 1][0];
    expect(last).toMatchObject({ outstanding: true });
  });

  it('switching to All sends outstanding: null and closed rows appear', () => {
    mockList([
      po({ id: 'po-active', po_number: 'PO-ACTIVE-1', status: 'active', is_on_order: true }),
      po({ id: 'po-closed', po_number: 'PO-CLOSED-1', status: 'cancelled', is_on_order: false }),
    ]);
    render(<PurchaseOrdersList />);

    fireEvent.click(screen.getByRole('radio', { name: 'All' }));

    const last = usePurchaseOrders.mock.calls[usePurchaseOrders.mock.calls.length - 1][0];
    expect(last).toMatchObject({ outstanding: null });
    // The mocked list already returns both rows once the toggle asks for "all" - the
    // screen renders whatever the hook hands it, closed row included.
    expect(screen.getByText('PO-ACTIVE-1')).toBeInTheDocument();
    expect(screen.getByText('PO-CLOSED-1')).toBeInTheDocument();
  });

  it('switching to Completed sends outstanding: false', () => {
    mockList([po({ id: 'po-cancelled', status: 'cancelled' })]);
    render(<PurchaseOrdersList />);

    fireEvent.click(screen.getByRole('radio', { name: 'Completed' }));

    const last = usePurchaseOrders.mock.calls[usePurchaseOrders.mock.calls.length - 1][0];
    expect(last).toMatchObject({ outstanding: false });
  });
});

// ── null-supplier rows ──────────────────────────────────────────────────────
// An imported historical PO can carry no supplier at all; blank must never read as the
// warehouse standing in for it (the captain's "why is BRW under supplier?"). There is
// deliberately NO header-level Location column (captain, same day: "PO's location is at
// line level ... at header level we don't need location") - the warehouse renders only
// on the detail page's per-line grid.

describe('PurchaseOrdersList - null-supplier rows', () => {
  it('shows an em dash naming why when a row carries no supplier, and no header Location', () => {
    mockList([
      po({
        id: 'po-no-supplier',
        po_number: 'PO-IMPORTED-1',
        supplier_name: null as unknown as string,
        warehouse_name: 'Brickfields DC',
      }),
    ]);
    render(<PurchaseOrdersList />);

    const dash = screen.getByTitle('No supplier on this imported PO');
    expect(dash).toHaveTextContent('-');
    // The header-level warehouse must not render anywhere on the list row.
    expect(screen.queryByText('Brickfields DC')).not.toBeInTheDocument();
  });
});
