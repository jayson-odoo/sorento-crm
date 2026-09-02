/**
 * SPOAllocationsList - the SPO document list (PLAN-spo-investigation-grid.md S2;
 * UAC AC-1..AC-4, AC-8).
 *
 *   - AC-1: tabs All / Outstanding (default) / Completed drive `useSPODocuments`'s
 *     `state` param.
 *   - AC-4: the Overdue-only toggle sends `overdueOnly: true` and composes with
 *     the active tab.
 *   - AC-2: status pill (Outstanding GREEN), Overdue reads amber once > 0.
 *   - AC-8: bulk delete (review B4) calls `useDeferredBulkAction`'s `run()` with one
 *     target per selected `spo_number` - the countdown/commit ENGINE itself is
 *     `hooks/useDeferredBulkAction.test.tsx`'s job, not restated here.
 *
 * `useSPODocuments` is mocked so these tests pin call ARGUMENTS, never a
 * restated copy of the query-building logic that belongs to the hook/service
 * layer (that is `spoDocumentService.test.ts`'s job).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
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

const routerPush = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spo-allocations',
  useRouter: () => ({ push: routerPush }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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

// The list only needs a REAL react-query context because it calls `useQueryClient()`
// directly (invalidate-on-delete/import). No data flows through it - `useSPODocuments`
// itself is mocked below.
vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

vi.mock(
  '@/app/(protected)/master-data-management/products/services/productService',
  () => ({ getProducts: vi.fn(async () => ({ data: [], pagination: { total: 0 } })) }),
);
vi.mock(
  '@/app/(protected)/inventory-management/warehouses/services/warehouseService',
  () => ({ getWarehouses: vi.fn(async () => ({ data: [], pagination: { total: 0 } })) }),
);

vi.mock('../services/spoAllocationService', () => ({
  importSPOAllocations: vi.fn(),
  validateSPOAllocations: vi.fn(),
}));

const useSPODocuments = vi.fn();
vi.mock('../hooks/useSPODocuments', () => ({
  useSPODocuments: (...a: unknown[]) => useSPODocuments(...a),
}));

// The engine (park-per-target, one countdown, commit/cancel) is
// `hooks/useDeferredBulkAction.test.tsx`'s job - this only pins that the LIST wires
// the right action key, entity type and selected `spo_number`s into it (review B4).
const bulkDeletionRun = vi.fn();
const useDeferredBulkActionInput = vi.fn();
vi.mock('@/hooks/useDeferredBulkAction', () => ({
  useDeferredBulkAction: (input: unknown) => {
    useDeferredBulkActionInput(input);
    return { run: bulkDeletionRun, isStarting: false };
  },
}));

import SPOAllocationsList from './SPOAllocationsList';
import type { SPODocumentRow } from '../types/spoDocument.types';

function row(over: Partial<SPODocumentRow> = {}): SPODocumentRow {
  return {
    id: 'SPO-2026/08-0061',
    spo_number: 'SPO-2026/08-0061',
    doc_date: '2026-08-01',
    supplier_name: 'Acme Sanitary',
    supplier_extra_count: 0,
    status: 'outstanding',
    earliest_eta: '2026-08-15',
    total_allocated: 500,
    total_received: 100,
    balance: 400,
    line_count: 2,
    worst_overdue_days: 0,
    ...over,
  };
}

function mockList(rows: SPODocumentRow[], over: Record<string, unknown> = {}) {
  useSPODocuments.mockReturnValue({
    data: { data: rows, pagination: { page: 1, total: rows.length } },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
    ...over,
  });
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SPOAllocationsList />
    </QueryClientProvider>,
  );
}

const rows = () => within(document.querySelector('tbody') as HTMLElement);

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ── AC-1: All / Outstanding (default) / Completed drives `state` ───────────

describe('SPOAllocationsList - state tabs (AC-1)', () => {
  it('defaults to the Outstanding tab and sends state: "outstanding" on the first call', () => {
    mockList([row()]);
    renderList();

    const toggle = screen.getByRole('radio', { name: 'Outstanding' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    const last = useSPODocuments.mock.calls[useSPODocuments.mock.calls.length - 1][0];
    expect(last).toMatchObject({ state: 'outstanding' });
  });

  it('switching to All sends state: "all"', () => {
    mockList([row()]);
    renderList();

    fireEvent.click(screen.getByRole('radio', { name: 'All' }));

    const last = useSPODocuments.mock.calls[useSPODocuments.mock.calls.length - 1][0];
    expect(last).toMatchObject({ state: 'all' });
  });

  it('switching to Completed sends state: "completed"', () => {
    mockList([row({ status: 'completed' })]);
    renderList();

    fireEvent.click(screen.getByRole('radio', { name: 'Completed' }));

    const last = useSPODocuments.mock.calls[useSPODocuments.mock.calls.length - 1][0];
    expect(last).toMatchObject({ state: 'completed' });
  });
});

// AC-4 retired (UAT batch): the Overdue-only toggle came off the list toolbar.
// `worst_overdue_days` stays a sortable/readable column (AC-2 below); the standalone
// toggle and its `overdueOnly` param are gone from this list, its hook and its
// service - the route still accepts `overdue_only` for other callers.

describe('SPOAllocationsList - overdue-only toggle retired (AC-4)', () => {
  it('does not render an Overdue only switch', () => {
    mockList([row()]);
    renderList();

    expect(screen.queryByRole('switch', { name: /Overdue only/i })).toBeNull();
  });

  it('never sends overdueOnly to useSPODocuments', () => {
    mockList([row()]);
    renderList();

    const last = useSPODocuments.mock.calls[useSPODocuments.mock.calls.length - 1][0];
    expect(last).not.toHaveProperty('overdueOnly');
  });
});

// ── AC-2: status pill + overdue formatting ──────────────────────────────────

describe('SPOAllocationsList - status pill + overdue formatting (AC-2)', () => {
  it('words Outstanding in green (success/light -> a green token in its class)', () => {
    mockList([row({ status: 'outstanding' })]);
    renderList();

    const pill = rows().getByText('Outstanding');
    expect(pill.className).toMatch(/green/);
  });

  it('reads worst_overdue_days amber once positive, and a dash at zero', () => {
    mockList([
      row({ id: 'SPO-LATE', spo_number: 'SPO-LATE', worst_overdue_days: 31 }),
      row({ id: 'SPO-ONTIME', spo_number: 'SPO-ONTIME', worst_overdue_days: 0 }),
    ]);
    renderList();

    const lateRow = screen.getByText('SPO-LATE').closest('tr') as HTMLElement;
    const onTimeRow = screen.getByText('SPO-ONTIME').closest('tr') as HTMLElement;
    const lateOverdue = within(lateRow).getByText('31d');
    expect(lateOverdue.className).toMatch(/amber/);
    expect(within(onTimeRow).getByText('-')).toBeInTheDocument();
  });
});

// ── AC-8: bulk delete wires the selected spo_numbers into useDeferredBulkAction ─

describe('SPOAllocationsList - bulk delete (AC-8, AC-16b, review B4)', () => {
  it('configures the hook with the spo_document.delete action key and entity type', () => {
    mockList([row({ id: 'SPO-1', spo_number: 'SPO-1' })]);
    renderList();

    const input = useDeferredBulkActionInput.mock.calls[0][0] as {
      actionKey: string;
      entityType: string;
    };
    expect(input.actionKey).toBe('spo_document.delete');
    expect(input.entityType).toBe('spo_document');
  });

  it('Delete selected calls run() with one target per selected spo_number', () => {
    mockList([
      row({ id: 'SPO-1', spo_number: 'SPO-1' }),
      row({ id: 'SPO-2', spo_number: 'SPO-2' }),
    ]);
    renderList();

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));

    // Two secondaryActions (Import SPO, Delete selected) collapse into the
    // "Actions" dropdown - Radix opens it on pointerdown, not click.
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    fireEvent.click(screen.getByRole('button', { name: /Delete selected/i }));

    expect(bulkDeletionRun).toHaveBeenCalledWith([{ id: 'SPO-1' }, { id: 'SPO-2' }]);
  });

  it('Delete selected is disabled with nothing selected', () => {
    mockList([row({ id: 'SPO-1', spo_number: 'SPO-1' })]);
    renderList();

    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    expect(screen.getByRole('button', { name: /Delete selected/i })).toBeDisabled();
    expect(bulkDeletionRun).not.toHaveBeenCalled();
  });
});
