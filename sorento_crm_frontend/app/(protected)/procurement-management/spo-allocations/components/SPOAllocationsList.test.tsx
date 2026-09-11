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

/** The dropdown-menu stub renders children and, for an item, wires the click - that is
 *  the whole surface this list touches, so it is typed rather than left as `any`. */
type MenuSlotProps = { children?: React.ReactNode };
type MenuItemProps = MenuSlotProps & { onClick?: () => void; disabled?: boolean };

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuSlotProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuSlotProps) => (
    <div data-testid="menu-content">{children}</div>
  ),
  DropdownMenuItem: ({ children, onClick, disabled }: MenuItemProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuCheckboxItem: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: MenuSlotProps) => <>{children}</>,
  DropdownMenuSub: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: MenuSlotProps) => <div>{children}</div>,
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
    // PLAN-spo-list-container-number.md AC-1/AC-2: `containers` is not yet on the
    // `SPODocumentRow` type (Phase 2 backend/frontend wiring), so this is spread onto
    // the plain object literal below rather than typed into the `SPODocumentRow`
    // return annotation - it does not fail the (type-check-free) vitest run, and it
    // means every existing mock row already carries an (empty) `containers` array
    // once the type gains the field.
    containers: [],
    ...over,
  } as SPODocumentRow;
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

// ── AC-S1.1: Date column right of SPO No, no sub-line under the SPO number ──

describe('SPOAllocationsList - Date column (AC-S1.1)', () => {
  it('renders a Date header and the row doc_date, dd/mm/yyyy', () => {
    mockList([row({ id: 'SPO-1', spo_number: 'SPO-1', doc_date: '2026-08-05' })]);
    renderList();

    expect(screen.getByRole('columnheader', { name: /Date/i })).toBeInTheDocument();
    expect(rows().getByText('05/08/2026')).toBeInTheDocument();
  });

  it('no longer stacks the date under the SPO No cell', () => {
    mockList([row({ id: 'SPO-1', spo_number: 'SPO-1', doc_date: '2026-08-05' })]);
    renderList();

    const spoLink = screen.getByRole('link', { name: 'SPO-1' });
    // The date used to render as a sibling <span> under the link, inside the same cell.
    const cell = spoLink.closest('td') as HTMLElement;
    expect(within(cell).queryByText('05/08/2026')).toBeNull();
  });
});

// ── PLAN-spo-list-container-number.md AC-6/AC-7: Container No column + search ──

describe('SPOAllocationsList - Container No column (AC-6)', () => {
  it('renders a "Container No" column header', () => {
    mockList([row()]);
    renderList();

    expect(screen.getByRole('columnheader', { name: /Container No/i })).toBeInTheDocument();
  });

  it('shows the first container as a link to its packing list, a "+1" pill linking to the second, and the joined title', () => {
    mockList([
      row({
        id: 'SPO-CONT-2',
        spo_number: 'SPO-CONT-2',
        containers: [
          { container_number: 'ZZTU1111111', shipment_id: 'S1' },
          { container_number: 'ZZTU2222222', shipment_id: 'S2' },
        ],
      } as Partial<SPODocumentRow>),
    ]);
    renderList();

    const rowEl = screen.getByText('SPO-CONT-2').closest('tr') as HTMLElement;

    const firstLink = within(rowEl).getByRole('link', { name: 'ZZTU1111111' });
    expect(firstLink).toHaveAttribute(
      'href',
      expect.stringContaining('/procurement-management/packing-lists/S1'),
    );

    const pill = within(rowEl).getByRole('link', { name: '+1' });
    expect(pill).toHaveAttribute(
      'href',
      expect.stringContaining('/procurement-management/packing-lists/S2'),
    );

    expect(within(rowEl).getByTitle('ZZTU1111111, ZZTU2222222')).toBeInTheDocument();
  });

  it('collapses three or more containers into a "+2" pill that opens a popover listing the extras as links', () => {
    mockList([
      row({
        id: 'SPO-CONT-3',
        spo_number: 'SPO-CONT-3',
        containers: [
          { container_number: 'ZZTU1111111', shipment_id: 'S1' },
          { container_number: 'ZZTU2222222', shipment_id: 'S2' },
          { container_number: 'ZZTU3333333', shipment_id: 'S3' },
        ],
      } as Partial<SPODocumentRow>),
    ]);
    renderList();

    const rowEl = screen.getByText('SPO-CONT-3').closest('tr') as HTMLElement;
    const pill = within(rowEl).getByText('+2');

    // Not yet expanded: the extra containers are not links on the page.
    expect(screen.queryByRole('link', { name: 'ZZTU2222222' })).toBeNull();

    fireEvent.click(pill);

    const secondLink = screen.getByRole('link', { name: 'ZZTU2222222' });
    expect(secondLink).toHaveAttribute(
      'href',
      expect.stringContaining('/procurement-management/packing-lists/S2'),
    );
    const thirdLink = screen.getByRole('link', { name: 'ZZTU3333333' });
    expect(thirdLink).toHaveAttribute(
      'href',
      expect.stringContaining('/procurement-management/packing-lists/S3'),
    );
  });

  it('renders a single raw (unlinked) container as plain text, no link and no pill', () => {
    mockList([
      row({
        id: 'SPO-CONT-RAW',
        spo_number: 'SPO-CONT-RAW',
        containers: [{ container_number: 'ZZTU4444444', shipment_id: null }],
      } as Partial<SPODocumentRow>),
    ]);
    renderList();

    const rowEl = screen.getByText('SPO-CONT-RAW').closest('tr') as HTMLElement;
    expect(within(rowEl).getByText('ZZTU4444444')).toBeInTheDocument();
    expect(within(rowEl).queryByRole('link', { name: 'ZZTU4444444' })).toBeNull();
    expect(within(rowEl).queryByText(/^\+\d/)).toBeNull();
  });

  it('renders "-" when the document has no container', () => {
    mockList([
      row({
        id: 'SPO-CONT-NONE',
        spo_number: 'SPO-CONT-NONE',
        // Non-zero so this row's own Overdue cell never also reads "-" (AC-2), which
        // would make the assertion below ambiguous about which cell it matched.
        worst_overdue_days: 5,
        containers: [],
      } as Partial<SPODocumentRow>),
    ]);
    renderList();

    const rowEl = screen.getByText('SPO-CONT-NONE').closest('tr') as HTMLElement;
    expect(within(rowEl).getByText('-')).toBeInTheDocument();
  });
});

describe('SPOAllocationsList - search placeholder mentions container (AC-7)', () => {
  it('reads "Search SPO, product or container..."', () => {
    mockList([row()]);
    renderList();

    expect(screen.getByPlaceholderText('Search SPO, product or container...')).toBeInTheDocument();
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

    // Two secondaryActions (Create SPO Allocation, Delete selected) collapse into the
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

// ── AC-C1: Upload SPO primary, Create SPO Allocation in the gear (R5) ───────

describe('SPOAllocationsList - Upload SPO is primary, Create SPO Allocation in the gear (AC-C1)', () => {
  it('shows Upload SPO as the primary button', () => {
    mockList([row()]);
    renderList();

    expect(screen.getByRole('button', { name: /Upload SPO/i })).toBeInTheDocument();
  });

  it('puts Create SPO Allocation inside the Actions (gear) menu', () => {
    mockList([row()]);
    renderList();

    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    expect(screen.getByRole('button', { name: /Create SPO Allocation/i })).toBeInTheDocument();
  });

  it('Create SPO Allocation in the gear routes to the manual form', () => {
    mockList([row()]);
    renderList();

    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    fireEvent.click(screen.getByRole('button', { name: /Create SPO Allocation/i }));

    expect(routerPush).toHaveBeenCalledWith('/procurement-management/spo-allocations/new');
  });
});
