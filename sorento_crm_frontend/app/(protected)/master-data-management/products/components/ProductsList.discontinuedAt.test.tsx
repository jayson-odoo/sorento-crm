/**
 * Products list - "Discontinued at" column, sort and date-range filter (issue #1287).
 *
 * UAC: `documentation/plans/products/products-discontinued-at-26sep-acceptance-criteria.md`.
 * Plan: `documentation/plans/products/PLAN-products-discontinued-at-26sep.md`.
 *
 * RED for Phase 2: `ProductsList.tsx` has no `discontinued_at` column, no "Discontinued
 * between" range control, `getExportPayload` does not carry `discontinued_from` /
 * `discontinued_to`, and the toolbar's `filters` prop carries no `activeSummary`. Every
 * assertion below fails against TODAY's code for one of those reasons - a missing column /
 * an element `getByLabelText`/`getByRole` cannot find / a param missing from a captured
 * call - never an import typo or fixture bug.
 *
 * Harness copied from `ProductsList.discontinued.test.tsx` (DataGrid stubbed, real column
 * `cell` renderers invoked directly against the captured react-table instance). The
 * `DataGridListToolbar` is ALSO stubbed here (captured, not rendered) so its props can be
 * inspected directly, but it renders `props.searchSlot` and `props.filters.content` into the
 * DOM so the real `DateRangePicker` the coder wires into that content actually mounts.
 */
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Column, Table } from '@tanstack/react-table';

import type { ProductListItem } from '../types/product.types';

type RowWithDiscontinuedAt = ProductListItem & { discontinued_at?: string | null };

const getProducts = vi.fn();

const grid = vi.hoisted(() => ({ table: null as unknown }));

vi.mock('@/components/ui/data-grid', () => ({
  // Unlike `ProductsList.discontinued.test.tsx`'s stub (which returns `null` and never
  // mounts anything nested), this one renders `children` - the toolbar mock below lives
  // inside them, and it has to actually mount for its `filters.content` (the real
  // `DateRangePicker`) to reach the DOM. `DataGridTable` / `DataGridPagination` are stubbed
  // separately below: both call the real `useDataGrid()` context hook this bare stub never
  // provides, and neither is under test here.
  DataGrid: ({ table, children }: { table: unknown; children?: ReactElement }) => {
    grid.table = table;
    return children ?? null;
  },
}));

vi.mock('@/components/ui/data-grid-table', () => ({ DataGridTable: () => null }));
vi.mock('@/components/ui/data-grid-pagination', () => ({ DataGridPagination: () => null }));

// Captures the toolbar's own props (never rendered by the real component here), but still
// mounts `searchSlot` and a `kind: 'custom'` filter's `content` into the DOM - the page's
// OWN filters popover content - so the real `DateRangePicker` the coder adds there mounts
// for real and can be typed into / read from.
const toolbar = vi.hoisted(() => ({ props: null as unknown }));

vi.mock('@/components/ui/data-grid-list-toolbar', () => ({
  DataGridListToolbar: (props: Record<string, unknown>) => {
    toolbar.props = props;
    const filters = props.filters as { kind?: string; content?: ReactElement } | undefined;
    return (
      <div data-testid="toolbar-stub">
        {props.searchSlot as ReactElement | undefined}
        {filters?.kind === 'custom' ? filters.content : null}
      </div>
    );
  },
}));

vi.mock('../services/productService', () => ({
  getProducts: (...a: unknown[]) => getProducts(...a),
  bulkImportProducts: vi.fn(),
  validateProductsImport: vi.fn(),
}));

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  router: { replace: () => {}, push: () => {} },
}));
vi.mock('next/navigation', () => ({
  useRouter: () => nav.router,
  usePathname: () => '/master-data-management/products',
  useSearchParams: () => nav.params,
}));

vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [] }),
}));

vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));

vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/hooks/useAutocountPull', () => ({
  useAutocountPullAction: () => ({ visible: false, label: '', onSelect: () => {} }),
}));

import ProductsList from './ProductsList';

const ACTIVE_ROW: RowWithDiscontinuedAt = {
  id: 'row-active',
  product_code: 'SRTWT8305-GM',
  product_name: 'SRTWT8305-GM',
  list_price: 850,
  is_active: true,
  is_discontinued: false,
  discontinued_at: null,
  created_at: new Date('2026-03-10T00:00:00Z'),
};

const DISCONTINUED_ROW: RowWithDiscontinuedAt = {
  id: 'row-discontinued',
  product_code: 'SRTWT6233-FRG',
  product_name: 'SRTWT6233-FRG',
  list_price: 3500,
  is_active: false,
  is_discontinued: true,
  discontinued_at: '2026-09-25T16:30:00',
  created_at: new Date('2026-03-10T00:00:00Z'),
};

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductsList />
    </QueryClientProvider>,
  );
}

function tableRef() {
  return grid.table as Table<ProductListItem>;
}

function renderCell(columnId: string, row: RowWithDiscontinuedAt) {
  const table = tableRef() as unknown as {
    getAllColumns: () => Column<ProductListItem, unknown>[];
  };
  const column = table.getAllColumns().find((c) => c.id === columnId);
  if (!column) throw new Error(`column ${columnId} not found`);
  const cell = column.columnDef.cell;
  if (typeof cell !== 'function') throw new Error(`column ${columnId} has no cell fn`);
  const el = cell({ row: { original: row } } as never) as ReactElement;
  return render(el);
}

function lastGetProductsCall(): Record<string, unknown> {
  const calls = getProducts.mock.calls;
  if (!calls.length) throw new Error('getProducts was never called');
  return calls[calls.length - 1][0] as Record<string, unknown>;
}

beforeEach(() => {
  grid.table = null;
  toolbar.props = null;
  getProducts.mockReset();
  getProducts.mockResolvedValue({
    data: [ACTIVE_ROW, DISCONTINUED_ROW],
    // 500 with pageSize 50 -> 10 pages, so `setPageIndex(2)` in the "typing a range"
    // test lands on a real page instead of being clamped back to 0 by TanStack (a
    // `total: 2` fixture gives pageCount = 1, so the precondition it sets up - "start
    // on a later page" - could never hold).
    pagination: { total: 500, page: 1, limit: 50 },
  });
});

afterEach(() => cleanup());

describe('ProductsList - Discontinued at column (AC-COL-1/2)', () => {
  it('renders a Discontinued at column right after Discontinued', async () => {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());

    const columns = tableRef().getAllColumns();
    const discontinuedIdx = columns.findIndex((c) => c.id === 'is_discontinued');
    expect(discontinuedIdx).toBeGreaterThanOrEqual(0);

    const column = columns.find((c) => c.id === 'discontinued_at');
    expect(column).toBeTruthy();
    expect(columns[discontinuedIdx + 1]?.id).toBe('discontinued_at');

    expect(column!.columnDef.enableHiding).not.toBe(false);
    expect(column!.columnDef.enableSorting).not.toBe(false);
    expect(column!.columnDef.meta?.headerTitle).toBe('Discontinued at');

    // Visible by default: no explicit `false` in the initial columnVisibility state.
    expect(tableRef().getState().columnVisibility['discontinued_at']).not.toBe(false);
  });

  it('shows the Malaysia date for a stamped row and a blank cell for null', async () => {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());

    const stamped = renderCell('discontinued_at', DISCONTINUED_ROW);
    expect(screen.getByText('26/09/2026')).toBeInTheDocument();
    cleanup(); // unmounts the rendered cell (and the list); `grid.table` itself is untouched

    const blank = renderCell('discontinued_at', ACTIVE_ROW);
    expect(blank.container.textContent).toBe('');
    expect(stamped).toBeTruthy();
  });
});

describe('ProductsList - Discontinued at sort (AC-SORT-2)', () => {
  it('sorting by the column sends sort=discontinued_at', async () => {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());
    await waitFor(() => expect(getProducts).toHaveBeenCalled());

    const column = tableRef()
      .getAllColumns()
      .find((c) => c.id === 'discontinued_at');
    if (!column) throw new Error('discontinued_at column not found - cannot sort by it');

    act(() => {
      column.toggleSorting(true); // desc
    });

    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.sorting).toEqual([{ id: 'discontinued_at', desc: true }]);
    });
  });
});

describe('ProductsList - Discontinued between filter (AC-TYPE-1, AC-FLT-5, AC-FLT-6, AC-EXP-3)', () => {
  async function findRangeInput() {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());
    await waitFor(() => expect(toolbar.props).not.toBeNull());
    return screen.getByRole('textbox', { name: 'Discontinued between' });
  }

  it('typing a range in Discontinued between filters the list from page 1', async () => {
    const { fireEvent } = await import('@testing-library/react');
    const input = await findRangeInput();

    // Start on a later page, so the reset-to-page-1 behaviour is observable.
    act(() => {
      tableRef().setPageIndex(2);
    });
    await waitFor(() => {
      expect(lastGetProductsCall().pageIndex).toBe(2);
    });

    await act(async () => {
      fireEvent.change(input, { target: { value: '01/09/2026 - 26/09/2026' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.discontinued_from).toBe('2026-09-01');
      expect(call.discontinued_to).toBe('2026-09-26');
      expect(call.pageIndex).toBe(0);
    });

    act(() => {
      tableRef().setPageIndex(1);
    });
    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.pageIndex).toBe(1);
      expect(call.discontinued_from).toBe('2026-09-01');
      expect(call.discontinued_to).toBe('2026-09-26');
    });
  });

  it('the range shows one filter chip whose clear removes both ends', async () => {
    const { fireEvent } = await import('@testing-library/react');
    const input = await findRangeInput();

    await act(async () => {
      fireEvent.change(input, { target: { value: '01/09/2026 - 26/09/2026' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await waitFor(() => {
      expect(lastGetProductsCall().discontinued_from).toBe('2026-09-01');
    });

    const filters = (toolbar.props as { filters?: Record<string, unknown> })?.filters;
    expect(filters?.active).toBe(true);
    const rawSummary = filters?.activeSummary as
      | { label: string; onClear: () => void }
      | { label: string; onClear: () => void }[]
      | undefined;
    const chips = Array.isArray(rawSummary) ? rawSummary : rawSummary ? [rawSummary] : [];
    const chip = chips.find((c) => c.label?.startsWith('Discontinued:'));
    expect(chip).toBeTruthy();
    expect(chip!.label).toBe('Discontinued: 1 Sep 26 - 26 Sep 26');

    act(() => {
      chip!.onClear();
    });

    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.discontinued_from).toBeUndefined();
      expect(call.discontinued_to).toBeUndefined();
    });
  });

  it('Clear Filters clears the range', async () => {
    const { fireEvent } = await import('@testing-library/react');
    const input = await findRangeInput();

    await act(async () => {
      fireEvent.change(input, { target: { value: '01/09/2026 - 26/09/2026' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await waitFor(() => {
      expect(lastGetProductsCall().discontinued_from).toBe('2026-09-01');
    });

    const clearButton = screen.getByRole('button', { name: 'Clear Filters' });
    await act(async () => {
      fireEvent.click(clearButton);
    });

    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.discontinued_from).toBeUndefined();
      expect(call.discontinued_to).toBeUndefined();
    });
  });

  it('export payload carries the range', async () => {
    const { fireEvent } = await import('@testing-library/react');
    const input = await findRangeInput();

    await act(async () => {
      fireEvent.change(input, { target: { value: '01/09/2026 - 26/09/2026' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await waitFor(() => {
      expect(lastGetProductsCall().discontinued_from).toBe('2026-09-01');
    });

    const exportConfig = (toolbar.props as { exportConfig?: { getPayload: () => Record<string, unknown> } })
      ?.exportConfig;
    expect(exportConfig).toBeTruthy();
    const payload = exportConfig!.getPayload();
    expect(payload.discontinued_from).toBe('2026-09-01');
    expect(payload.discontinued_to).toBe('2026-09-26');
  });

  it('one-sided ranges read from X / to Y', async () => {
    // A one-sided range cannot be TYPED (`parseRangeInput` always sets both ends
    // together, or a single date sets from = to), so it is seeded the same way a
    // Back navigation would: through the URL the list restores from
    // (`useListStateFromUrl`), one field at a time.
    nav.params = new URLSearchParams({ discontinued_from: '2026-09-01' });
    renderList();
    await waitFor(() => expect(toolbar.props).not.toBeNull());

    const fromOnlyFilters = (toolbar.props as { filters?: Record<string, unknown> })?.filters;
    const fromOnlySummary = fromOnlyFilters?.activeSummary as
      | { label: string; onClear: () => void }
      | { label: string; onClear: () => void }[]
      | undefined;
    const fromOnlyChips = Array.isArray(fromOnlySummary)
      ? fromOnlySummary
      : fromOnlySummary
        ? [fromOnlySummary]
        : [];
    const fromOnlyChip = fromOnlyChips.find((c) => c.label?.startsWith('Discontinued:'));
    expect(fromOnlyChip?.label).toBe('Discontinued: from 1 Sep 26');
    cleanup();

    nav.params = new URLSearchParams({ discontinued_to: '2026-09-26' });
    renderList();
    await waitFor(() => expect(toolbar.props).not.toBeNull());

    const toOnlyFilters = (toolbar.props as { filters?: Record<string, unknown> })?.filters;
    const toOnlySummary = toOnlyFilters?.activeSummary as
      | { label: string; onClear: () => void }
      | { label: string; onClear: () => void }[]
      | undefined;
    const toOnlyChips = Array.isArray(toOnlySummary) ? toOnlySummary : toOnlySummary ? [toOnlySummary] : [];
    const toOnlyChip = toOnlyChips.find((c) => c.label?.startsWith('Discontinued:'));
    expect(toOnlyChip?.label).toBe('Discontinued: to 26 Sep 26');

    nav.params = new URLSearchParams();
  });
});
