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
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

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

import PurchaseOrdersList from './PurchaseOrdersList';
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

function mockList(rows: PurchaseOrder[], over: Record<string, unknown> = {}) {
  usePurchaseOrders.mockReturnValue({
    data: { data: rows, pagination: { page: 1, total: rows.length } },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
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
    expect(link).toHaveAttribute('href', '/scm/purchase-orders/po-abc');
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

describe('PurchaseOrdersList — AutoCount mirror rows (read-only gate, Slice 8)', () => {
  it('shows the AutoCount badge and NO Create GR action on an autocount PO', () => {
    mockList([
      po({ id: 'po-ac', po_number: 'AC-SMOKE-PO-1', status: 'active', source: 'autocount', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
    // An active PO would normally offer Create GR — an autocount one must not.
    expect(screen.queryByRole('button', { name: /Create GR/i })).toBeNull();
  });

  it('keeps Create GR on a manual/native active PO', () => {
    mockList([
      po({ id: 'po-native', po_number: 'PO-2026/07-0009', status: 'active', source: 'manual', is_on_order: true }),
    ]);
    render(<PurchaseOrdersList />);
    expect(screen.queryByText('AutoCount')).toBeNull();
    expect(screen.getAllByRole('button', { name: /Create GR/i })).toHaveLength(1);
  });

  it('excludes an autocount PO from bulk-select (its row checkbox is disabled)', () => {
    mockList([
      po({ id: 'po-ac', po_number: 'AC-SMOKE-PO-1', status: 'active', source: 'autocount', is_on_order: true }),
      po({ id: 'po-draft', po_number: 'PO-DRAFT-0001', status: 'draft_recommendation' }),
    ]);
    render(<PurchaseOrdersList />);
    const rowCheckboxes = screen.getAllByLabelText('Select row');
    // Two rows, but the autocount row's checkbox is not selectable.
    const disabledCount = rowCheckboxes.filter((c) => (c as HTMLButtonElement).disabled).length;
    expect(disabledCount).toBe(1);
  });
});
