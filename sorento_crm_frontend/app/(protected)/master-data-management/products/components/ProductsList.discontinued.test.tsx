/**
 * ProductsList - Status + Discontinued status pills.
 *
 * Covers the design-language alignment for the boolean status columns:
 *  - Status (is_active) renders "Active"/"Inactive",
 *  - the new Discontinued (is_discontinued) column renders "Discontinued"
 *    when set and "Available" otherwise.
 *
 * Same technique as ProductsList.variant.test.tsx: the heavy DataGrid is stubbed
 * to capture the react-table instance, then the REAL column `cell` renderers are
 * invoked directly against the captured column defs.
 */
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Column } from '@tanstack/react-table';

import type { ProductListItem } from '../types/product.types';

const getProducts = vi.fn();

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

const ACTIVE_ROW: ProductListItem = {
  id: 'row-active',
  product_code: 'SRTWT8305-GM',
  product_name: 'SRTWT8305-GM',
  list_price: 850,
  is_active: true,
  is_discontinued: false,
  created_at: new Date('2026-03-10T00:00:00Z'),
};

const DISCONTINUED_ROW: ProductListItem = {
  id: 'row-discontinued',
  product_code: 'SRTWT6233-FRG',
  product_name: 'SRTWT6233-FRG',
  list_price: 3500,
  is_active: false,
  is_discontinued: true,
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

function renderCell(columnId: string, row: ProductListItem) {
  const table = grid.table as {
    getAllColumns: () => Column<ProductListItem, unknown>[];
  };
  const column = table.getAllColumns().find((c) => c.id === columnId);
  if (!column) throw new Error(`column ${columnId} not found`);
  const cell = column.columnDef.cell;
  if (typeof cell !== 'function') throw new Error(`column ${columnId} has no cell fn`);
  const el = cell({ row: { original: row } } as never) as ReactElement;
  return render(el);
}

beforeEach(() => {
  grid.table = null;
  getProducts.mockReset();
  getProducts.mockResolvedValue({
    data: [ACTIVE_ROW, DISCONTINUED_ROW],
    pagination: { total: 2, page: 1, limit: 10 },
  });
});

afterEach(() => cleanup());

describe('ProductsList - status + discontinued pills', () => {
  it('Status column renders Active/Inactive from is_active', async () => {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());

    renderCell('is_active', ACTIVE_ROW);
    expect(screen.getByText('Active')).toBeInTheDocument();
    cleanup();

    renderCell('is_active', DISCONTINUED_ROW);
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('Discontinued column renders Discontinued when set, Available otherwise', async () => {
    renderList();
    await waitFor(() => expect(grid.table).not.toBeNull());

    renderCell('is_discontinued', DISCONTINUED_ROW);
    expect(screen.getByText('Discontinued')).toBeInTheDocument();
    cleanup();

    renderCell('is_discontinued', ACTIVE_ROW);
    expect(screen.getByText('Available')).toBeInTheDocument();
  });
});
