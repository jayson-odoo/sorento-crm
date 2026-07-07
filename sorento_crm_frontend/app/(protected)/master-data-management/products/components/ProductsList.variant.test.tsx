/**
 * ProductsList — variant columns + default filter.
 *
 * Covers the variant-manual-curation list additions:
 *  - the "Variant of" column renders the parent's human-readable code (never a UUID),
 *  - the variant (child) count column renders,
 *  - the default query does NOT send a variant_filter (i.e. defaults to "all").
 *
 * The real DataGrid infinitely re-renders in jsdom (virtualization + ResizeObserver
 * measurement), so it is stubbed to capture the react-table instance ProductsList
 * builds. We then invoke the REAL column `cell` renderers (variant_of /
 * variant_child_count) directly against the captured column defs — exercising the
 * shipped rendering logic without mounting the heavy grid.
 *
 * The Base/Variant/All filter's param mapping + refetch-on-change is covered at the
 * seam by productService.variantCuration.test.ts (param mapping) and
 * useProducts.variantFilter.test.tsx (query-key refetch).
 */
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Column } from '@tanstack/react-table';

import type { ProductListItem } from '../types/product.types';

const getProducts = vi.fn();

// Captures the react-table instance ProductsList passes to <DataGrid>.
const grid = vi.hoisted(() => ({ table: null as unknown }));

vi.mock('@/components/ui/data-grid', () => ({
  DataGrid: ({ table }: { table: unknown }) => {
    grid.table = table;
    return null;
  },
}));

vi.mock('../services/productService', () => ({
  getProducts: (...a: unknown[]) => getProducts(...a),
  bulkImportProducts: vi.fn(),
  validateProductsImport: vi.fn(),
}));

// Stable instances — ProductsList's params-restore effect depends on
// searchParams + router; returning fresh objects each render re-fires the effect
// which setStates → infinite render loop (hang).
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

import ProductsList from './ProductsList';

const BASE_ROW: ProductListItem = {
  id: 'row-base',
  product_code: 'SRTKT71SS',
  product_name: 'Kitchen Tap 71 Stainless',
  list_price: 100,
  is_active: true,
  is_variant: false,
  variant_of: null,
  variant_child_count: 7,
  created_at: new Date('2026-01-01T00:00:00Z'),
};

const VARIANT_ROW: ProductListItem = {
  id: 'row-variant',
  product_code: 'SRTKT71SS-BL',
  product_name: 'Kitchen Tap 71 Stainless Black',
  list_price: 110,
  is_active: true,
  is_variant: true,
  variant_of: {
    id: 'parent-uuid-xyz',
    product_code: 'SRTKT71SS',
    product_name: 'Kitchen Tap 71 Stainless',
  },
  variant_child_count: 0,
  created_at: new Date('2026-01-02T00:00:00Z'),
};

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductsList />
    </QueryClientProvider>,
  );
}

/** Locate a captured column by id and render its cell for a given row. */
function renderCell(columnId: string, row: ProductListItem) {
  const table = grid.table as {
    getAllColumns: () => Column<ProductListItem, unknown>[];
  };
  const column = table.getAllColumns().find((c) => c.id === columnId);
  if (!column) throw new Error(`column ${columnId} not found`);
  const cell = column.columnDef.cell;
  if (typeof cell !== 'function') throw new Error(`column ${columnId} has no cell fn`);
  // The variant cells only read `row.original`; a minimal context suffices.
  const el = cell({ row: { original: row } } as never) as ReactElement;
  return render(el);
}

beforeEach(() => {
  grid.table = null;
  getProducts.mockReset();
  getProducts.mockResolvedValue({
    data: [BASE_ROW, VARIANT_ROW],
    pagination: { total: 2, page: 1, limit: 10 },
  });
});

afterEach(() => cleanup());

describe('ProductsList — variant columns', () => {
  it('"Variant of" column renders the parent code human-readable (base shows —), no UUID', async () => {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());

    // Variant row → parent's human-readable code.
    const variantCell = renderCell('variant_of', VARIANT_ROW);
    expect(screen.getByText('SRTKT71SS')).toBeInTheDocument();
    expect(variantCell.container.textContent).not.toContain('parent-uuid-xyz');
    variantCell.unmount();

    // Base row → em dash placeholder.
    renderCell('variant_of', BASE_ROW);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('"Variants" column renders the child count', async () => {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());

    renderCell('variant_child_count', BASE_ROW);
    expect(screen.getByText('7')).toBeInTheDocument();
    cleanup();

    renderCell('variant_child_count', VARIANT_ROW);
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('defaults to fetching without a variant_filter (all)', async () => {
    renderList();
    await waitFor(() => expect(getProducts).toHaveBeenCalled());
    const firstArg = getProducts.mock.calls[0][0] as Record<string, unknown>;
    expect(firstArg.variant_filter).toBeUndefined();
  });
});
