/**
 * Warehouse READ view - pins the "View and Edit are the same layout (binding)" contract
 * from CLAUDE.md ("CRUD UX standard").
 *
 * The read view must present the SAME two tabs, in the same order, holding the same fields
 * in the same order, as the edit view (see `../components/WarehouseForm.test.tsx`, which
 * asserts the identical arrays):
 *
 *   Basic Information : System Location, System Location Description, Warehouse, Active Status
 *   Planning          : Available for planning, Fulfilment planning, Draws stock from
 *
 * Plus the rules the current detail page breaks:
 * - Created / Last Updated are read-only metadata: page header or meta strip, never a tab body.
 * - The detail page carries prev/next record navigation (components/common/RecordNavigation).
 * - Every field renders even when empty; nothing disappears on a missing value.
 * - No multi-sentence explanatory prose.
 *
 * The data layer is mocked at the module boundary; nothing hits the network.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import WarehouseDetailPage from './page';
import type { Warehouse } from '../types/warehouse.types';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CURRENT_ID = '11111111-1111-4111-8111-111111111111';
const POOL_ID = '22222222-2222-4222-8222-222222222222';
const OTHER_ID = '33333333-3333-4333-8333-333333333333';

const CURRENT: Warehouse = {
  id: CURRENT_ID,
  warehouse_code: 'WH-CUR',
  warehouse_name: 'Main Store',
  location: 'Shah Alam DC',
  manager_id: null,
  is_active: true,
  created_at: new Date('2026-01-05T02:00:00Z'),
  updated_at: new Date('2026-02-09T04:30:00Z'),
  counts_as_available: true,
  fulfilment_planning: false,
  pool_warehouse_id: POOL_ID,
  pool_warehouse_code: 'WH-POOL',
};

const POOL: Warehouse = {
  ...CURRENT,
  id: POOL_ID,
  warehouse_code: 'WH-POOL',
  warehouse_name: 'Shared Pool',
  pool_warehouse_id: null,
  pool_warehouse_code: null,
  updated_at: null,
};

const OTHER: Warehouse = {
  ...CURRENT,
  id: OTHER_ID,
  warehouse_code: 'WH-OTHER',
  warehouse_name: 'Overflow',
  location: 'Klang',
  pool_warehouse_id: null,
  pool_warehouse_code: null,
  updated_at: null,
};

const ALL = [CURRENT, POOL, OTHER];

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const h = vi.hoisted(() => ({
  push: vi.fn(),
  deleteWarehouse: vi.fn(),
  updateMutate: vi.fn(),
  /** Every toast raised during a test, in order, by sonner method name. */
  toasts: [] as string[],
  /** Swapped per test to drive the loading / not-found / data states. */
  warehouse: undefined as Warehouse | undefined,
  isLoading: false,
}));

/**
 * Toasts are counted, not rendered. Delete used to run through TWO mutations - the page's
 * own `useDeleteWarehouse` and the one `ConfirmDeleteDialog` wraps `onDelete` in - so a
 * single failure raised the same message twice, in two positions.
 */
vi.mock('sonner', () => {
  const record = (kind: string) => () => {
    h.toasts.push(kind);
    return kind;
  };
  const toast = Object.assign(record('default'), {
    success: record('success'),
    error: record('error'),
    warning: record('warning'),
    info: record('info'),
    message: record('message'),
    custom: record('custom'),
    loading: record('loading'),
    dismiss: () => {},
  });
  return { toast, Toaster: () => null };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: h.push, back: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => `/inventory-management/warehouses/${CURRENT_ID}`,
}));

// Container pulls SettingsProvider context this unit test does not need.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../hooks/useWarehouses', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useWarehouses')>()),
  useWarehouse: () => ({ data: h.warehouse, isLoading: h.isLoading, isError: false }),
  useWarehouses: () => ({
    data: { data: ALL, pagination: { page: 1, limit: 100, total: ALL.length, total_pages: 1 } },
    isLoading: false,
    isError: false,
  }),
  // useDeleteWarehouse is deliberately NOT stubbed. It is a real hook that toasts and
  // invalidates on its own, so leaving it live is what makes a page that ALSO routes the
  // delete through it visibly double-report.
  useUpdateWarehouse: () => ({ mutateAsync: h.updateMutate, isPending: false }),
}));

vi.mock('../services/warehouseService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/warehouseService')>()),
  getWarehouses: vi.fn(async () => ({
    data: ALL,
    pagination: { page: 1, limit: 1000, total: ALL.length, total_pages: 1 },
  })),
  getWarehouse: vi.fn(async () => CURRENT),
  deleteWarehouse: (...args: unknown[]) => h.deleteWarehouse(...args),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      data: ALL,
      pagination: { page: 1, limit: 1000, total: ALL.length, total_pages: 1 },
    }),
  })),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function renderDetail(id: string = CURRENT_ID) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  // The page resolves its route params with `use(params)`, which suspends on the first
  // pass, so the render has to be flushed inside act before anything can be asserted.
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Suspense fallback={<div>Loading route</div>}>
          <WarehouseDetailPage params={Promise.resolve({ id })} />
        </Suspense>
      </QueryClientProvider>,
    );
  });
  return { client, invalidate };
}

/** Open the confirmation dialog from the header, then confirm inside it. */
async function confirmDelete() {
  fireEvent.click(screen.getAllByRole('button', { name: /^delete$/i })[0]);
  const dialog = await screen.findByRole('dialog');
  await act(async () => {
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
  });
}

/** How many times ['warehouses'] was invalidated. Two means two mutations ran. */
const warehousesInvalidations = (invalidate: { mock: { calls: unknown[][] } }) =>
  invalidate.mock.calls.filter((call) => {
    const arg = call[0] as { queryKey?: unknown[] } | undefined;
    return JSON.stringify(arg?.queryKey) === JSON.stringify(['warehouses']);
  }).length;

const tabNames = () =>
  screen.getAllByRole('tab').map((t) => (t.textContent ?? '').trim());

/**
 * Radix TabsTrigger activates on mousedown; click alone is not enough in jsdom.
 * Tolerant of a tab-less layout so the field-level tests below fail on their own
 * subject rather than cascading off the (separately asserted) tab structure.
 */
function selectTab(name: string) {
  const tab = screen.queryByRole('tab', { name });
  if (!tab) return;
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

const activePanel = () => screen.getByRole('tabpanel');

/** Assert the given strings appear in this DOM order inside `scope`. */
function expectTextOrder(scope: HTMLElement, texts: string[]) {
  const content = (scope.textContent ?? '').replace(/\s+/g, ' ');
  let cursor = -1;
  for (const text of texts) {
    const at = content.indexOf(text, cursor + 1);
    expect(
      at,
      `expected "${text}" to appear after the preceding field, in: ${content}`,
    ).toBeGreaterThan(cursor);
    cursor = at;
  }
}

/**
 * The column span each field takes in the two-column grid, keyed by label.
 *
 * DOM order agreeing between the two views is not enough: at >= md a field given
 * `md:col-span-2` in one view and a single cell in the other lands in a different row
 * AND a different column, so "Active Status" appears at row2-right in one and row3-full
 * in the other. That is the drift the "nothing moves" clause exists to stop, and text
 * order is blind to it.
 *
 * This map is asserted VERBATIM in `../components/WarehouseForm.test.tsx`. Change one side
 * and the other's copy goes red.
 */
const FIELD_SPANS: Record<string, 'full' | 'half'> = {
  'System Location': 'half',
  'System Location Description': 'half',
  Warehouse: 'full',
  'Active Status': 'full',
  'Available for planning': 'full',
  // Borrow ladder v7.1 S1 (AC-S1-3): the flag sits directly under `Available for planning`,
  // full width, in BOTH views - the read view mirrors it in the same position.
  'Fulfilment planning': 'full',
  'Draws stock from': 'half',
  'Sells to': 'half',
};

/**
 * Span per field label for the grid inside the active tab panel.
 *
 * The grid cell is a direct child of the grid container: a read-only `Field` wrapper on
 * this view, a `FormItem` on the edit view. Its label is the leading `<p>` (read) or a
 * `<label>` (edit), so one helper serves both files.
 */
function gridSpans(): Record<string, 'full' | 'half'> {
  const panel = activePanel();
  const grid = (panel.querySelector('.grid') ?? panel) as HTMLElement;
  const spans: Record<string, 'full' | 'half'> = {};
  for (const cell of Array.from(grid.children) as HTMLElement[]) {
    const labelEl = cell.querySelector('label') ?? cell.querySelector('p');
    const label = (labelEl?.textContent ?? '').replace(/\*$/, '').trim();
    if (!label) continue;
    spans[label] = cell.className.includes('md:col-span-2') ? 'full' : 'half';
  }
  return spans;
}

/** The subset of FIELD_SPANS covering the given labels. */
const expectedSpans = (labels: string[]) =>
  Object.fromEntries(labels.map((label) => [label, FIELD_SPANS[label]]));

const BANNED_PROSE = [
  'Turn this off for held, reserved, defective or clearance locations',
  'The shared pool this location draws on',
  'A shortage here is covered',
  'Stock here is ignored when the plan decides what to buy',
];

beforeEach(() => {
  h.push.mockClear();
  h.deleteWarehouse.mockReset().mockResolvedValue(undefined);
  h.updateMutate.mockReset().mockResolvedValue(CURRENT);
  h.toasts.length = 0;
  h.warehouse = CURRENT;
  h.isLoading = false;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Warehouse detail - Fulfilment planning (AC-S1-3)', () => {
  it('reads Off for a record whose flag is off, in the Planning tab', async () => {
    await renderDetail();
    selectTab('Planning');

    const panel = (activePanel().textContent ?? '').replace(/\s+/g, ' ');
    expect(panel).toContain('Fulfilment planning');
    expect(panel).toContain('Off');
  });
});

describe('Warehouse detail - same layout as the edit view', () => {
  it('renders exactly two tabs: Basic Information then Planning', async () => {
    await renderDetail();
    expect(tabNames()).toEqual(['Basic Information', 'Planning']);
  });

  it('opens on Basic Information, holding the identity fields in the edit view order', async () => {
    await renderDetail();

    expect(screen.getByRole('tab', { name: 'Basic Information' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expectTextOrder(activePanel(), [
      'System Location',
      'System Location Description',
      'Warehouse',
      'Active Status',
    ]);
  });

  it('keeps the planning fields on the Planning tab, in the edit view order', async () => {
    await renderDetail();
    selectTab('Planning');

    expectTextOrder(activePanel(), [
      'Available for planning',
      'Fulfilment planning',
      'Draws stock from',
    ]);
    // Resolved to the code, never a UUID (cursor rule).
    expect(activePanel().textContent).toContain('WH-POOL');
    expect(activePanel().textContent).not.toContain(POOL_ID);
  });

  it('gives the Basic Information fields the spans the edit view uses', async () => {
    await renderDetail();

    expect(gridSpans()).toEqual(
      expectedSpans([
        'System Location',
        'System Location Description',
        'Warehouse',
        'Active Status',
      ]),
    );
  });

  it('gives the Planning fields the spans the edit view uses', async () => {
    await renderDetail();
    selectTab('Planning');

    expect(gridSpans()).toEqual(
      expectedSpans([
        'Available for planning',
        'Fulfilment planning',
        'Draws stock from',
        'Sells to',
      ]),
    );
  });

  it('renders the Warehouse field even when the record has no value for it', async () => {
    h.warehouse = { ...CURRENT, location: null };
    await renderDetail();

    // Never hide a field on a missing value; show the empty placeholder instead.
    expect(activePanel().textContent).toContain('Warehouse');
  });
});

describe('Warehouse detail - metadata placement', () => {
  it('keeps Created and Last Updated out of the Basic Information tab body', async () => {
    await renderDetail();

    const basic = (activePanel().textContent ?? '').replace(/\s+/g, ' ');
    expect(basic).not.toContain('Created');
    expect(basic).not.toContain('Last Updated');
  });

  it('still shows Created and Last Updated somewhere on the page (header / meta strip)', async () => {
    await renderDetail();

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    expect(page).toContain('Created');
    expect(page).toContain('Last Updated');
  });
});

describe('Warehouse detail - record navigation', () => {
  it('renders prev/next record navigation', async () => {
    await renderDetail();

    expect(screen.getByLabelText(/^Previous /i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Next /i)).toBeInTheDocument();
  });
});

describe('Warehouse detail - prose', () => {
  it('carries no multi-sentence explanatory prose', async () => {
    await renderDetail();
    selectTab('Planning');

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    for (const prose of BANNED_PROSE) {
      expect(page, `explanatory prose still in the UI: "${prose}"`).not.toContain(prose);
    }
  });
});

describe('Warehouse detail - delete reports once', () => {
  /**
   * `ConfirmDeleteDialog` owns the toast and the invalidation, so the page must hand it a
   * bare service call. Routing through `useDeleteWarehouse` as well makes both mutations
   * fire: the user sees one message twice, in two positions.
   */
  it('deletes through the service and toasts once', async () => {
    const { invalidate } = await renderDetail();

    await confirmDelete();

    await waitFor(() => expect(h.toasts).toContain('custom'));
    expect(h.deleteWarehouse).toHaveBeenCalledWith(CURRENT_ID);
    expect(h.toasts).toEqual(['custom']);
    expect(h.push).toHaveBeenCalledWith('/inventory-management/warehouses');
    // Still invalidated, exactly once: queryKeysToInvalidate must stay on the dialog.
    expect(warehousesInvalidations(invalidate)).toBe(1);
  });

  it('reports a rejected delete once, not twice', async () => {
    h.deleteWarehouse.mockRejectedValue(
      new Error('Warehouse has linked stock, zones, allocations, or picking lines.'),
    );
    const { invalidate } = await renderDetail();

    await confirmDelete();

    await waitFor(() => expect(h.toasts).toContain('custom'));
    expect(h.toasts).toEqual(['custom']);
    expect(h.push).not.toHaveBeenCalledWith('/inventory-management/warehouses');
    expect(warehousesInvalidations(invalidate)).toBe(0);
  });
});

describe('Warehouse detail - states', () => {
  it('shows no tabs while the record is still loading', async () => {
    h.warehouse = undefined;
    h.isLoading = true;
    await renderDetail();

    expect(screen.queryAllByRole('tab')).toHaveLength(0);
  });

  it('shows a not-found message when the record does not exist', async () => {
    h.warehouse = undefined;
    h.isLoading = false;
    await renderDetail('missing-id');

    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });
});
