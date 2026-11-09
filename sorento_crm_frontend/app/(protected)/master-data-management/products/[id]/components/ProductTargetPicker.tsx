'use client';

/**
 * The product picker behind every "Copy to other products" dialog: the system product grid with
 * search, Category / Brand multi-select filters, shift / drag ticks and "Select all N" (capped at
 * MAX_COPY_TARGETS). Lifted out of CopyAccessoriesDialog (ACC-COPY-TO-PRODUCTS) for the combo copy
 * (COMBO-COPY-TO-PRODUCTS) so there is one picker, not two.
 *
 * A hook, not a component: the dialog swaps the grid for its confirm step and back, and the ticks,
 * search and filters must survive that round trip, so the state lives with the dialog.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import {
  isSearchInFlight,
  useDebouncedSearch,
} from '@/hooks/useDebouncedSearch';
import {
  idFilterLabels,
  joinMulti,
  multiChipLabel,
} from '@/lib/list-filters/multiValue';
import { distinctName } from '@/lib/product-display';
import { toast } from '@/lib/toast';
import { useProductCategorySelectQuery } from '../../../shared/hooks/use-product-category-select-query';
import { useBrandSelectQuery } from '../../../shared/hooks/use-brand-select-query';
import { useProducts } from '../../hooks/useProducts';
import { getProducts } from '../../services/productService';
import type { Product } from '../../types/product.types';

/** The server's cap on one copy (target_product_ids max_length on both copy endpoints). */
export const MAX_COPY_TARGETS = 500;

const SOURCE_REASON = 'This is the product being copied from';

export function plural(count: number, noun: string): string {
  const many = noun.endsWith('y') ? `${noun.slice(0, -1)}ies` : `${noun}s`;
  return `${count.toLocaleString('en-US')} ${count === 1 ? noun : many}`;
}

/** The confirm step's statement of the cap (#2280 hand-test leftover: say it plainly). */
export function CopyCapNote() {
  return (
    <p className="text-sm text-muted-foreground" data-testid="copy-cap-note">
      One copy takes at most {MAX_COPY_TARGETS.toLocaleString('en-US')}{' '}
      products.
    </p>
  );
}

export function useProductTargetPicker(sourceProductId: string): {
  picked: string[];
  overCap: boolean;
  cappedFrom: number | null;
  grid: ReactNode;
} {
  const search = useDebouncedSearch('');
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [brandIds, setBrandIds] = useState<string[]>([]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'product_code', desc: false },
  ]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [matchingActive, setMatchingActive] = useState(false);
  const [matchingTotal, setMatchingTotal] = useState<number | null>(null);
  const [matchingPending, setMatchingPending] = useState(false);
  // Bumped whenever the result set changes, so a "Select all" fetch that lands late is dropped.
  const matchingSeq = useRef(0);
  const categories = useProductCategorySelectQuery();
  const brands = useBrandSelectQuery();

  const params = useMemo(
    () => ({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery: search.debouncedValue,
      category_id: joinMulti(categoryIds) || undefined,
      brand_id: joinMulti(brandIds) || undefined,
      status: 'active' as const,
    }),
    [pagination, sorting, search.debouncedValue, categoryIds, brandIds],
  );

  // A new search or filter is a new result set: a "Select all" made on the old one no longer
  // describes what is on screen, so it is dropped (ticks made by hand stay).
  useEffect(() => {
    matchingSeq.current += 1;
    setMatchingActive(false);
    setMatchingPending(false);
    setPagination((p) => (p.pageIndex === 0 ? p : { ...p, pageIndex: 0 }));
  }, [search.debouncedValue, categoryIds, brandIds]);

  const { data, isLoading, isFetching, isPlaceholderData } =
    useProducts(params);
  const rows = useMemo(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;

  const columns = useMemo<ColumnDef<Product>[]>(
    () => [
      buildSelectColumn<Product>({
        enableRow: (row) => row.original.id !== sourceProductId,
        disabledReason: (row) =>
          row.original.id === sourceProductId ? SOURCE_REASON : undefined,
        rowLabel: (row) => `Select ${row.original.product_code}`,
      }),
      {
        accessorKey: 'product_code',
        id: 'product_code',
        header: ({ column }) => (
          <DataGridColumnHeader title="Product Code" column={column} />
        ),
        cell: ({ row }) => (
          <div
            className="truncate text-sm font-medium"
            title={row.original.product_code}
          >
            {row.original.product_code}
            {/* Owner, 7 Nov: a discontinued product stays pickable, with a grey hint. */}
            {row.original.is_discontinued ? (
              <span className="ms-1.5 text-xs font-normal text-muted-foreground">
                Discontinued
              </span>
            ) : null}
          </div>
        ),
        size: 160,
        meta: { headerTitle: 'Product Code' },
        enableSorting: true,
      },
      {
        accessorKey: 'product_name',
        id: 'product_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Product Name" column={column} />
        ),
        cell: ({ row }) => {
          const name =
            distinctName(
              row.original.product_code,
              row.original.product_name,
            ) ?? '';
          return (
            <div className="truncate text-sm" title={name}>
              {name}
            </div>
          );
        },
        size: 280,
        meta: { headerTitle: 'Product Name' },
        enableSorting: true,
      },
      {
        accessorFn: (row) => row.category?.category_name ?? '',
        id: 'category_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Category" column={column} />
        ),
        cell: ({ row }) => {
          const name = row.original.category?.category_name ?? '';
          return (
            <div className="truncate text-sm" title={name}>
              {name || ' - '}
            </div>
          );
        },
        size: 160,
        meta: { headerTitle: 'Category' },
        enableSorting: true,
      },
      {
        accessorFn: (row) => row.brand?.brand_name ?? '',
        id: 'brand_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Brand" column={column} />
        ),
        cell: ({ row }) => {
          const name = row.original.brand?.brand_name ?? '';
          return (
            <div className="truncate text-sm" title={name}>
              {name || ' - '}
            </div>
          );
        },
        size: 140,
        meta: { headerTitle: 'Brand' },
        enableSorting: true,
      },
    ],
    [sourceProductId],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    columnResizeMode: 'onChange',
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: (updater) => {
      // A hand tick or untick after "Select all" makes it a hand-picked set again.
      setMatchingActive(false);
      setRowSelection(updater);
    },
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    enableRowSelection: (row) => row.original.id !== sourceProductId,
  });

  // Ticks survive paging and filtering, so the picked set is the selection state, not the page.
  const picked = useMemo(
    () =>
      Object.keys(rowSelection).filter(
        (id) => rowSelection[id] && id !== sourceProductId,
      ),
    [rowSelection, sourceProductId],
  );
  const overCap = picked.length > MAX_COPY_TARGETS;

  const selectAllMatching = async () => {
    const mine = ++matchingSeq.current;
    setMatchingPending(true);
    try {
      const res = await getProducts({
        ...params,
        pageIndex: 0,
        pageSize: MAX_COPY_TARGETS + 1,
      });
      if (matchingSeq.current !== mine) return;
      const eligible = res.data
        .map((p) => p.id)
        .filter((id) => id !== sourceProductId);
      const ids = eligible.slice(0, MAX_COPY_TARGETS);
      setMatchingTotal(
        eligible.length > MAX_COPY_TARGETS ? res.pagination.total : null,
      );
      setRowSelection(Object.fromEntries(ids.map((id) => [id, true])));
      setMatchingActive(true);
    } catch (err) {
      if (matchingSeq.current !== mine) return;
      toast.error(
        err instanceof Error
          ? err.message
          : 'Could not select all matching products',
      );
    } finally {
      if (matchingSeq.current === mine) setMatchingPending(false);
    }
    // A superseded fetch leaves `pending` to the effect that superseded it, which clears it.
  };

  const grid = (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <div className="space-y-3">
        <DataGridListToolbar
          table={table}
          keepSearchWhileSelected
          showColumns={false}
          showExport={false}
          searchSlot={
            <ListSearchInput
              value={search.value}
              onChange={search.setValue}
              isSettling={isSearchInFlight(
                search.isSettling,
                isFetching,
                search.debouncedValue,
              )}
              placeholder="Search products..."
              className="w-full sm:w-64"
            />
          }
          filters={{
            kind: 'custom',
            active: categoryIds.length + brandIds.length > 0,
            activeCount:
              (categoryIds.length ? 1 : 0) + (brandIds.length ? 1 : 0),
            content: (
              <div className="space-y-3">
                <SearchableMultiSelect
                  value={categoryIds}
                  onChange={setCategoryIds}
                  placeholder="Category"
                  loadError={categories.error}
                  onRetry={() => void categories.refetch()}
                  options={(categories.data ?? []).map((cat) => ({
                    value: cat.id,
                    label: cat.category_name,
                  }))}
                  clearable
                  renderTriggerLabel={(chosen) =>
                    chosen.length ? (
                      <span className="block truncate">
                        {multiChipLabel('Category', idFilterLabels(chosen))}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">
                        Category: any
                      </span>
                    )
                  }
                />
                <SearchableMultiSelect
                  value={brandIds}
                  onChange={setBrandIds}
                  placeholder="Brand"
                  loadError={brands.error}
                  onRetry={() => void brands.refetch()}
                  options={(brands.data ?? []).map((brand) => ({
                    value: brand.id,
                    label: brand.brand_name,
                  }))}
                  clearable
                  renderTriggerLabel={(chosen) =>
                    chosen.length ? (
                      <span className="block truncate">
                        {multiChipLabel('Brand', idFilterLabels(chosen))}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Brand: any</span>
                    )
                  }
                />
              </div>
            ),
          }}
          selectAllMatching={{
            total,
            loadedCount: rows.length,
            active: matchingActive,
            pending: matchingPending,
            limit: MAX_COPY_TARGETS,
            onSelectAll: () => void selectAllMatching(),
            onClear: () => {
              setMatchingActive(false);
              setRowSelection({});
            },
          }}
        />
        <DataGridTable />
        <DataGridPagination />
      </div>
    </DataGrid>
  );

  // The matching total of a Select all that was cut to the cap; null once the set is hand-edited.
  const cappedFrom = matchingActive ? matchingTotal : null;
  return { picked, overCap, cappedFrom, grid };
}

/** The picker step's footer count. */
export function pickedLine(count: number): string {
  return count > MAX_COPY_TARGETS
    ? `${plural(count, 'product')} picked; one copy takes at most ${MAX_COPY_TARGETS}.`
    : `${plural(count, 'product')} picked`;
}
