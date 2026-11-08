/**
 * Products list - "List price changed at" column, sort, "List price changed between" filter
 * and the List Price cell's history icon (LIST-PRICE-CHANGE-UI).
 *
 * Plan: `documentation/plans/products/PLAN-list-price-change-ui-08nov.md`. Mirrors
 * `ProductsList.discontinuedAt.test.tsx` (same harness: DataGrid and toolbar stubbed, real
 * column cell renderers, the real `DateRangePicker` mounted from the filters content).
 * All values are fake.
 */
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Column, Table } from '@tanstack/react-table';

import type { ProductListItem } from '../types/product.types';

type Row = ProductListItem & { list_price_changed_at?: string | null };

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
// The Import barcodes action is gated on master_data.products.edit.
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('next/navigation', () => ({
  useRouter: () => nav.router,
  usePathname: () => '/master-data-management/products',
  useSearchParams: () => nav.params,
}));

vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [] }),
}));

vi.mock('../../shared/hooks/use-item-class-select-query', () => ({
  useItemClassSelectQuery: () => ({ data: [] }),
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

const historyDialog = vi.hoisted(() => ({ props: null as unknown }));
vi.mock('./ListPriceHistoryDialog', () => ({
  default: (props: Record<string, unknown>) => {
    historyDialog.props = props;
    return null;
  },
}));

import ProductsList from './ProductsList';

const UNCHANGED_ROW: Row = {
  id: 'row-unchanged',
  product_code: 'FAKE-UNCHANGED',
  product_name: 'Fake Unchanged',
  list_price: 850,
  is_active: true,
  is_discontinued: false,
  list_price_changed_at: null,
  created_at: new Date('2026-03-10T00:00:00Z'),
};

const CHANGED_ROW: Row = {
  id: 'row-changed',
  product_code: 'FAKE-CHANGED',
  product_name: 'Fake Changed',
  list_price: 3500,
  is_active: true,
  is_discontinued: false,
  list_price_changed_at: '2026-11-07T16:30:00',
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

function renderCell(columnId: string, row: Row) {
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
  historyDialog.props = null;
  nav.params = new URLSearchParams();
  getProducts.mockReset();
  getProducts.mockResolvedValue({
    data: [UNCHANGED_ROW, CHANGED_ROW],
    // 500 with pageSize 50 -> 10 pages, so `setPageIndex(2)` in the "typing a range"
    // test lands on a real page instead of being clamped back to 0 by TanStack (a
    // `total: 2` fixture gives pageCount = 1, so the precondition it sets up - "start
    // on a later page" - could never hold).
    pagination: { total: 500, page: 1, limit: 50 },
  });
});

afterEach(() => cleanup());


type Chip = { label: string; onClear: () => void };

function chips(): Chip[] {
  const filters = (toolbar.props as { filters?: Record<string, unknown> })?.filters;
  const raw = filters?.activeSummary as Chip | Chip[] | undefined;
  return Array.isArray(raw) ? raw : raw ? [raw] : [];
}

async function typeRange(name: string, value: string) {
  const { fireEvent } = await import('@testing-library/react');
  const input = screen.getByRole('textbox', { name });
  await act(async () => {
    fireEvent.change(input, { target: { value } });
    fireEvent.keyDown(input, { key: 'Enter' });
  });
}

async function mounted() {
  renderList();
  await waitFor(() => expect(grid.table).not.toBeNull());
  await waitFor(() => expect(toolbar.props).not.toBeNull());
}

describe('ProductsList - List price changed at column', () => {
  it('sits right after List Price, sortable, hideable, visible by default', async () => {
    await mounted();
    const columns = tableRef().getAllColumns();
    const priceIdx = columns.findIndex((c) => c.id === 'list_price');
    expect(priceIdx).toBeGreaterThanOrEqual(0);
    const column = columns[priceIdx + 1];
    expect(column?.id).toBe('list_price_changed_at');
    expect(column!.columnDef.enableSorting).not.toBe(false);
    expect(column!.columnDef.enableHiding).not.toBe(false);
    expect(column!.columnDef.meta?.headerTitle).toBe('List price changed at');
    expect(typeof column!.columnDef.size).toBe('number');
    expect(tableRef().getState().columnVisibility['list_price_changed_at']).not.toBe(false);
  });

  it('shows the Malaysia date when changed and a blank cell when never changed', async () => {
    await mounted();
    renderCell('list_price_changed_at', CHANGED_ROW);
    expect(screen.getByText('08/11/2026')).toBeInTheDocument();
    cleanup();
    const blank = renderCell('list_price_changed_at', UNCHANGED_ROW);
    expect(blank.container.textContent).toBe('');
  });

  it('sorting by the column sends sort=list_price_changed_at', async () => {
    await mounted();
    await waitFor(() => expect(getProducts).toHaveBeenCalled());
    const column = tableRef().getAllColumns().find((c) => c.id === 'list_price_changed_at');
    if (!column) throw new Error('list_price_changed_at column not found');
    act(() => column.toggleSorting(true));
    await waitFor(() =>
      expect(lastGetProductsCall().sorting).toEqual([{ id: 'list_price_changed_at', desc: true }]),
    );
  });
});

describe('ProductsList - List Price cell history icon', () => {
  it('a changed row shows the price and a history button that opens the lightbox', async () => {
    const { fireEvent } = await import('@testing-library/react');
    await mounted();
    renderCell('list_price', CHANGED_ROW);
    expect(screen.getByText(/MYR\s3,500\.00/)).toBeInTheDocument();
    const button = screen.getByRole('button', { name: 'List price history' });

    expect((historyDialog.props as { product: unknown } | null)?.product ?? null).toBeNull();
    await act(async () => {
      fireEvent.click(button);
    });
    await waitFor(() =>
      expect((historyDialog.props as { product: { id: string; product_code: string } }).product).toMatchObject({
        id: 'row-changed',
        product_code: 'FAKE-CHANGED',
      }),
    );

    // Closing hands the product back.
    await act(async () => {
      (historyDialog.props as { onOpenChange: (open: boolean) => void }).onOpenChange(false);
    });
    await waitFor(() => expect((historyDialog.props as { product: unknown }).product).toBeNull());
  });

  it('a saved layout narrower than the price + icon still renders List Price at its minimum', async () => {
    // Every saved Products layout carried list_price: 120 from before the icon (crew pass).
    await mounted();
    const column = tableRef().getColumn('list_price')!;
    const min = column.columnDef.minSize ?? 0;
    expect(min).toBeGreaterThanOrEqual(170);
    act(() => tableRef().setColumnSizing({ list_price: 120 }));
    expect(tableRef().getColumn('list_price')!.getSize()).toBe(min);
  });

  it('a never-changed row shows the price without the icon', async () => {
    await mounted();
    renderCell('list_price', UNCHANGED_ROW);
    expect(screen.getByText(/MYR\s850\.00/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'List price history' })).toBeNull();
  });
});

describe('ProductsList - List price changed between filter', () => {
  it('typing a range filters the list from page 1 and keeps it across pages', async () => {
    await mounted();
    act(() => tableRef().setPageIndex(2));
    await waitFor(() => expect(lastGetProductsCall().pageIndex).toBe(2));

    await typeRange('List price changed between', '01/11/2026 - 08/11/2026');
    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.list_price_changed_from).toBe('2026-11-01');
      expect(call.list_price_changed_to).toBe('2026-11-08');
      expect(call.discontinued_from).toBeUndefined();
      expect(call.pageIndex).toBe(0);
    });

    act(() => tableRef().setPageIndex(1));
    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.pageIndex).toBe(1);
      expect(call.list_price_changed_from).toBe('2026-11-01');
    });
  });

  it('both ranges show side by side as two chips, each clearing only its own range', async () => {
    await mounted();
    await typeRange('Discontinued between', '01/09/2026 - 26/09/2026');
    await typeRange('List price changed between', '01/11/2026 - 08/11/2026');
    await waitFor(() => expect(lastGetProductsCall().list_price_changed_from).toBe('2026-11-01'));

    const filters = (toolbar.props as { filters?: Record<string, unknown> })?.filters;
    expect(filters?.activeCount).toBe(2);
    const labels = chips().map((c) => c.label);
    expect(labels).toContain('Discontinued: 01/09/2026 - 26/09/2026');
    expect(labels).toContain('List price changed: 01/11/2026 - 08/11/2026');

    const lp = chips().find((c) => c.label.startsWith('List price changed:'))!;
    act(() => lp.onClear());
    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.list_price_changed_from).toBeUndefined();
      expect(call.list_price_changed_to).toBeUndefined();
      expect(call.discontinued_from).toBe('2026-09-01');
    });
  });

  it('Clear Filters clears the range', async () => {
    const { fireEvent } = await import('@testing-library/react');
    await mounted();
    await typeRange('List price changed between', '01/11/2026 - 08/11/2026');
    await waitFor(() => expect(lastGetProductsCall().list_price_changed_from).toBe('2026-11-01'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Clear Filters' }));
    });
    await waitFor(() => {
      const call = lastGetProductsCall();
      expect(call.list_price_changed_from).toBeUndefined();
      expect(call.list_price_changed_to).toBeUndefined();
    });
  });

  it('export payload carries the range', async () => {
    await mounted();
    await typeRange('List price changed between', '01/11/2026 - 08/11/2026');
    await waitFor(() => expect(lastGetProductsCall().list_price_changed_from).toBe('2026-11-01'));
    const exportConfig = (toolbar.props as { exportConfig?: { getPayload: () => Record<string, unknown> } })
      ?.exportConfig;
    const payload = exportConfig!.getPayload();
    expect(payload.list_price_changed_from).toBe('2026-11-01');
    expect(payload.list_price_changed_to).toBe('2026-11-08');
  });

  it('a one-sided range restored from the URL reads from X / to Y', async () => {
    nav.params = new URLSearchParams({ list_price_changed_from: '2026-11-01' });
    await mounted();
    await waitFor(() => expect(lastGetProductsCall().list_price_changed_from).toBe('2026-11-01'));
    expect(chips().find((c) => c.label.startsWith('List price changed:'))?.label).toBe(
      'List price changed: from 01/11/2026',
    );
    cleanup();

    nav.params = new URLSearchParams({ list_price_changed_to: '2026-11-08' });
    await mounted();
    expect(chips().find((c) => c.label.startsWith('List price changed:'))?.label).toBe(
      'List price changed: to 08/11/2026',
    );
  });
});
