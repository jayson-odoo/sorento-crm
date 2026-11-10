/**
 * The Columns menu is the truth about the grid (COLUMNS-TOGGLE-TRUTH, every listing app-wide).
 *
 * Read top to bottom, the menu must say what the grid says left to right: the same columns
 * ticked, in the same order. It used to list columns in DEFINITION order while the grid
 * renders the user's saved order, so on Products > All Products (owner, 10 Nov 2026) Type,
 * Variant Of and Variants sat ticked at the top of the menu while the grid drew them past
 * Updated, off-screen. Their saved order was written while `mergeColumnOrder` still
 * appended unseen columns at the far right (before 17 Aug), so every Products layout saved
 * in that window carries them there.
 *
 * The integration case below replays that owner's real saved row (prod copy, 10 Nov), plus
 * a stale key the grid no longer has, through the real DataGrid and preference hook.
 */
import React, { useMemo, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnPinningState,
  type Table,
  type VisibilityState,
} from '@tanstack/react-table';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/products',
}));

vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({
    listing_key: listingKey,
    config,
  })),
  resetUserListColumnConfig: vi.fn(),
}));

import { getUserListColumnConfig } from '@/lib/listing-column-preferences/listColumnPreferencesService';
import { DataGrid, DataGridContainer } from './data-grid';
import { DataGridTable } from './data-grid-table';
import { DataGridColumnVisibility, leafColumnsInScreenOrder } from './data-grid-column-visibility';

// --- unit: the order the menu reads ----------------------------------------------------

type GroupRow = { id: string; agent: string; value: number; y1: boolean; y2: boolean };

const GROUP_ROWS: GroupRow[] = [{ id: '1', agent: 'Alice', value: 1, y1: true, y2: false }];

const GROUP_COLUMNS: ColumnDef<GroupRow>[] = [
  { accessorKey: 'agent', id: 'agent', header: 'Sales agent' },
  { accessorKey: 'value', id: 'value', header: 'Project value' },
  {
    id: 'delivery',
    header: 'Expected year of delivery',
    columns: [
      { accessorKey: 'y1', id: 'y1', header: '2026' },
      { accessorKey: 'y2', id: 'y2', header: '2027' },
    ],
  },
];

function tableWith(state: {
  columnOrder?: string[];
  columnPinning?: ColumnPinningState;
  columnVisibility?: VisibilityState;
}): Table<GroupRow> {
  let table: Table<GroupRow> | null = null;
  function Probe() {
    table = useReactTable({
      data: GROUP_ROWS,
      columns: GROUP_COLUMNS,
      getRowId: (row) => row.id,
      state: {
        columnOrder: state.columnOrder ?? [],
        columnPinning: state.columnPinning ?? { left: [], right: [] },
        columnVisibility: state.columnVisibility ?? {},
      },
      onColumnOrderChange: () => {},
      onColumnPinningChange: () => {},
      onColumnVisibilityChange: () => {},
      getCoreRowModel: getCoreRowModel(),
    });
    return null;
  }
  render(<Probe />);
  return table as unknown as Table<GroupRow>;
}

describe('leafColumnsInScreenOrder', () => {
  it('lists every leaf, group members included, in definition order when nothing was moved', () => {
    const table = tableWith({});
    expect(leafColumnsInScreenOrder(table).map((c) => c.id)).toEqual(['agent', 'value', 'y1', 'y2']);
  });

  it('follows a dragged column, because that is where the grid draws it', () => {
    const table = tableWith({ columnOrder: ['value', 'agent', 'y1', 'y2'] });
    expect(leafColumnsInScreenOrder(table).map((c) => c.id)).toEqual(['value', 'agent', 'y1', 'y2']);
  });

  it('puts left-pinned columns first and right-pinned last, as the grid does', () => {
    const table = tableWith({ columnPinning: { left: ['y2'], right: ['agent'] } });
    expect(leafColumnsInScreenOrder(table).map((c) => c.id)).toEqual(['y2', 'value', 'y1', 'agent']);
  });

  it('keeps a hidden column in its slot, so ticking it back shows it where the menu said', () => {
    const table = tableWith({
      columnOrder: ['value', 'agent', 'y1', 'y2'],
      columnVisibility: { agent: false },
    });
    expect(leafColumnsInScreenOrder(table).map((c) => c.id)).toEqual(['value', 'agent', 'y1', 'y2']);
  });
});

// --- integration: the owner's saved Products row through the real grid -----------------

type ProductRow = Record<string, string>;

/** Products > All Products' column ids, in the order `ProductsList.tsx` defines them. */
const PRODUCT_IDS = [
  'product_code',
  'product_name',
  'variant_type',
  'variant_of',
  'variant_child_count',
  'category_name',
  'brand_name',
  'item_class',
  'list_price',
  'list_price_changed_at',
  'is_active',
  'is_discontinued',
  'discontinued_at',
  'is_searchable',
  'exclude_from_planning',
  'created_at',
  'updated_at',
];
const NOT_HIDEABLE = new Set(['product_code', 'product_name']);

const PRODUCT_COLUMNS = [
  ...PRODUCT_IDS.map((id) => ({
    accessorKey: id,
    id,
    header: `H:${id}`,
    size: 100,
    enableHiding: !NOT_HIDEABLE.has(id),
    meta: { headerTitle: `T:${id}` },
  })),
  { accessorKey: 'actions', id: 'actions', header: '', size: 60, enableHiding: false },
] as ColumnDef<ProductRow>[];

const PRODUCT_ROWS: ProductRow[] = [
  Object.fromEntries([['id', 'r1'], ...PRODUCT_IDS.map((id) => [id, id])]),
];

/** The owner's saved row, verbatim from the prod copy (10 Nov 2026). */
const OWNER_SAVED_CONFIG = {
  version: 1,
  pageSize: 100,
  columnOrder: [
    'select',
    'product_code',
    'product_name',
    'category_name',
    'brand_name',
    'item_class',
    'list_price',
    'is_active',
    'created_at',
    'updated_at',
    'variant_type',
    'variant_of',
    'variant_child_count',
    'is_discontinued',
    'discontinued_at',
    'is_searchable',
    'actions',
    'exclude_from_planning',
  ],
  columnSizing: {
    is_active: 100,
    brand_name: 150,
    created_at: 180,
    item_class: 249,
    list_price: 120,
    updated_at: 212,
    variant_of: 160,
    product_code: 225,
    product_name: 213,
    variant_type: 100,
    category_name: 150,
    is_searchable: 140,
    discontinued_at: 140,
    is_discontinued: 187,
    variant_child_count: 90,
    exclude_from_planning: 140,
  },
  columnVisibility: {
    is_active: true,
    brand_name: true,
    created_at: true,
    item_class: true,
    list_price: true,
    updated_at: true,
    variant_of: true,
    variant_type: true,
    category_name: true,
    is_searchable: true,
    discontinued_at: true,
    is_discontinued: true,
    variant_child_count: true,
    exclude_from_planning: false,
  },
};

function ProductsHarness() {
  const columns = useMemo(() => PRODUCT_COLUMNS, []);
  // Same initial state ProductsList.tsx gives its table.
  const [columnOrder, setColumnOrder] = useState<string[]>(columns.map((c) => c.id as string));
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({
    exclude_from_planning: false,
  });
  const table = useReactTable({
    columns,
    data: PRODUCT_ROWS,
    getRowId: (row) => row.id,
    state: { columnOrder, columnVisibility },
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={PRODUCT_ROWS.length}
      tableLayout={{
        columnsResizable: true,
        columnsPinnable: true,
        columnsMovable: true,
        columnsVisibility: true,
      }}
    >
      <DataGridColumnVisibility table={table} trigger={<button type="button">Columns</button>} />
      <DataGridContainer>
        <DataGridTable />
      </DataGridContainer>
    </DataGrid>
  );
}

/** What the grid draws left to right, and what the menu says top to bottom. */
async function readGridAndMenu(savedConfig: unknown) {
  vi.mocked(getUserListColumnConfig).mockResolvedValue({
    listing_key: '/master-data-management/products',
    config: savedConfig,
  } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ProductsHarness />
    </QueryClientProvider>,
  );

  // Wait for the saved row to be applied (the skeleton gives way to the real header).
  await waitFor(() => expect(screen.getAllByText(/^H:/).length).toBeGreaterThan(0));
  if (savedConfig) {
    await waitFor(() =>
      expect(screen.getAllByText(/^H:/).map((h) => h.textContent)).toContain('H:updated_at'),
    );
  }

  const rendered = screen
    .getAllByRole('columnheader')
    .map((header) => header.textContent ?? '')
    .filter((text) => text.startsWith('H:'))
    .map((text) => text.slice(2));

  await userEvent.click(screen.getByRole('button', { name: 'Columns' }));
  const items = await screen.findAllByRole('menuitemcheckbox');
  const menu = items.map((item) => ({
    id: (item.textContent ?? '').replace(/^T:/, ''),
    ticked: item.getAttribute('aria-checked') === 'true',
  }));
  return { rendered, menu };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Columns menu == rendered columns', () => {
  it("the owner's saved Products row: ticked items read in exactly the grid's order", async () => {
    const { rendered, menu } = await readGridAndMenu(OWNER_SAVED_CONFIG);

    // The grid draws the variant columns past Updated, where the saved order put them.
    expect(rendered.indexOf('variant_type')).toBeGreaterThan(rendered.indexOf('updated_at'));

    const hideableRendered = rendered.filter((id) => !NOT_HIDEABLE.has(id));
    expect(menu.filter((item) => item.ticked).map((item) => item.id)).toEqual(hideableRendered);
  });

  it('a saved row with stale keys (renamed or removed columns) still matches the grid', async () => {
    const { rendered, menu } = await readGridAndMenu({
      ...OWNER_SAVED_CONFIG,
      columnOrder: ['is_variant', ...OWNER_SAVED_CONFIG.columnOrder, 'product_type'],
      columnVisibility: {
        ...OWNER_SAVED_CONFIG.columnVisibility,
        is_variant: false,
        product_type: true,
        brand_name: false,
      },
    });

    expect(rendered).not.toContain('brand_name');
    const hideableRendered = rendered.filter((id) => !NOT_HIDEABLE.has(id));
    expect(menu.filter((item) => item.ticked).map((item) => item.id)).toEqual(hideableRendered);
    // The stale ids are nowhere: not in the grid, not in the menu.
    expect(menu.map((item) => item.id)).not.toContain('is_variant');
    expect(menu.map((item) => item.id)).not.toContain('product_type');
    // The hidden column sits unticked in its own slot, between its rendered neighbours.
    const ids = menu.map((item) => item.id);
    expect(ids.indexOf('brand_name')).toBe(ids.indexOf('category_name') + 1);
    expect(menu.find((item) => item.id === 'brand_name')?.ticked).toBe(false);
  });

  it('a fresh user (no saved row) sees the definition order in both', async () => {
    const { rendered, menu } = await readGridAndMenu(null);

    const hideableRendered = rendered.filter((id) => !NOT_HIDEABLE.has(id));
    expect(menu.filter((item) => item.ticked).map((item) => item.id)).toEqual(hideableRendered);
    expect(menu.find((item) => item.id === 'exclude_from_planning')?.ticked).toBe(false);
  });
});
