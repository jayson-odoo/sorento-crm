/**
 * SCM M4 Slice B — PurchaseOrdersList (AC-M4.6).
 *   - draft + active rows render (draft = "Not on order", active = "On order")
 *   - PO number is a hyperlink to the detail page (human number, no UUID)
 *   - select-all selects ALL rows (drafts + active); the Actions dropdown shows
 *     "Confirm N drafts" scoped to the draft subset and is HIDDEN when the
 *     selection has no drafts
 *   - Create GR is a per-row action on active POs only
 *   - loading / empty / error states
 *
 * Data + action hooks are mocked; the dropdown-menu module is stubbed inline so
 * the bulk Actions item is assertable without a Radix portal.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, cleanup } from '@testing-library/react';

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

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/purchase-orders',
  useRouter: () => ({ push: vi.fn() }),
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
vi.mock('../../hooks/usePurchaseOrders', () => ({
  usePurchaseOrders: (...a: unknown[]) => usePurchaseOrders(...a),
}));
vi.mock('../../hooks/usePurchaseOrderActions', () => ({
  usePurchaseOrderActions: () => ({ confirm: confirmMut, createGr: createGrMut }),
}));

// The upload dialog is exercised by its own suite; here we only care that this screen
// mounts it for the PURCHASE-ORDER book and refreshes itself when it applies.
type UploadDialogProps = {
  open: boolean;
  kind: string;
  onApplied?: (result: OutstandingApplyResult) => void;
};
let uploadProps: UploadDialogProps | null = null;
vi.mock('../../reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: (props: UploadDialogProps) => {
    uploadProps = props;
    return props.open ? <div>{`outstanding-upload:${props.kind}`}</div> : null;
  },
}));

import { toast } from 'sonner';
import PurchaseOrdersList from './PurchaseOrdersList';
import type { OutstandingApplyResult } from '../../reorder/services/outstandingImportService';
import type { PurchaseOrder } from '../../types/scm.types';

function po(over: Partial<PurchaseOrder>): PurchaseOrder {
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

describe('PurchaseOrdersList — states (AC-M4.6)', () => {
  it('renders the empty state when there are no POs', () => {
    mockList([], { data: { data: [], pagination: { page: 1, total: 0 } } });
    render(<PurchaseOrdersList />);
    expect(screen.getByText(/No purchase orders yet/i)).toBeInTheDocument();
  });

  it('renders the loading skeleton state', () => {
    usePurchaseOrders.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: vi.fn() });
    const { container } = render(<PurchaseOrdersList />);
    expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy();
  });
});

describe('PurchaseOrdersList — draft + active rows (AC-M4.6)', () => {
  it('renders a draft ("Not on order") and an active ("On order") row', () => {
    mockList([
      po({ id: 'po-draft', po_number: 'PO-DRAFT-0001', status: 'draft_recommendation' }),
      po({ id: 'po-active', po_number: 'PO-2026/07-0009', status: 'active', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    expect(screen.getByText('PO-DRAFT-0001')).toBeInTheDocument();
    expect(screen.getByText('PO-2026/07-0009')).toBeInTheDocument();
    expect(screen.getByText('Not on order')).toBeInTheDocument();
    expect(screen.getAllByText('On order').length).toBeGreaterThanOrEqual(1);
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

  it('shows Create GR only on active POs (not on drafts)', () => {
    mockList([
      po({ id: 'po-draft', status: 'draft_recommendation' }),
      po({ id: 'po-active', po_number: 'PO-2026/07-0009', status: 'active', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    // Exactly one Create GR button — for the single active PO.
    expect(screen.getAllByRole('button', { name: /Create GR/i })).toHaveLength(1);
  });
});

describe('PurchaseOrdersList — select-all + bulk Confirm gating (AC-M4.6)', () => {
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

// ── the outstanding PURCHASE-ORDER book (AC-A6) ─────────────────────────────
// The extract spec defines two books, outstanding SO and outstanding PO. The PO book
// says what is already on order, and it belongs to the actor working THIS screen, not
// to the planner on the reorder screen. Nothing loads it unless this toolbar opens it.

describe('PurchaseOrdersList - upload the order book', () => {
  it('opens the outstanding PURCHASE-ORDER upload from the toolbar', () => {
    mockList([po({ id: 'po-draft-1' })]);
    render(<PurchaseOrdersList />);
    expect(screen.queryByText(/^outstanding-upload:/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Upload order book/i }));
    // The kind is the whole point: this screen must not open the sales-order book.
    expect(screen.getByText('outstanding-upload:purchase-orders')).toBeInTheDocument();
  });

  it('offers the same upload from the empty state', () => {
    // A fresh install has no POs at all - the upload has to be reachable from the
    // state the user actually lands in, not only from a populated list.
    mockList([], { data: { data: [], pagination: { page: 1, total: 0 } } });
    render(<PurchaseOrdersList />);

    fireEvent.click(screen.getByRole('button', { name: /Upload order book/i }));
    expect(screen.getByText('outstanding-upload:purchase-orders')).toBeInTheDocument();
  });

  it('refreshes the list and says what changed once the upload is applied', () => {
    mockList([po({ id: 'po-draft-1' })]);
    render(<PurchaseOrdersList />);
    fireEvent.click(screen.getByRole('button', { name: /Upload order book/i }));
    refetch.mockClear();

    const onApplied = uploadProps?.onApplied;
    if (!onApplied) throw new Error('the screen mounted the upload dialog without an onApplied');
    act(() => {
      onApplied({
        ok: true,
        counts: {},
        applied: { added: 2, updated: 3, closed: 1, unchanged: 9 },
        scope_documents: ['PO-2026/07-0009'],
        resolution_issues: [],
        row_problems: [],
      });
    });

    // Without the refresh the applied rows are invisible until a manual reload.
    expect(refetch).toHaveBeenCalled();
    // 2 + 3 + 1 changed; `unchanged` is not a change.
    expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/6 lines changed/i));
  });
});
