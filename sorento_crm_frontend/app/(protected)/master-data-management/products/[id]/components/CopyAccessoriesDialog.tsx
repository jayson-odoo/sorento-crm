'use client';

/**
 * ACC-COPY-TO-PRODUCTS: copy this product's "Accessories included" list to hand-picked products.
 * The parent mounts it only while open, so every open starts from a clean slate.
 *
 * Plan: documentation/plans/dealer-kit/PLAN-acc-copy-to-products-09nov.md. Two steps in one
 * modal: pick on the system product grid (search, Category / Brand filters, shift / drag ticks,
 * "Select all N"), then a confirm that reads the server's dry run, then one write.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { idFilterLabels, joinMulti, multiChipLabel } from '@/lib/list-filters/multiValue';
import { distinctName } from '@/lib/product-display';
import { toast } from '@/lib/toast';
import { useProductCategorySelectQuery } from '../../../shared/hooks/use-product-category-select-query';
import { useBrandSelectQuery } from '../../../shared/hooks/use-brand-select-query';
import { useProducts } from '../../hooks/useProducts';
import { getProducts } from '../../services/productService';
import type { ProductListItem } from '../../types/product.types';
import { useCopyProductAccessories } from '../../../accessories/hooks/useAccessories';
import type { AccessoryCopySummary } from '../../../accessories/services/accessoryService';

/** The server's cap on one copy (AccessoryCopyIn.target_product_ids). */
export const MAX_COPY_TARGETS = 500;

const SOURCE_REASON = 'This is the product being copied from';

function plural(count: number, noun: string): string {
  const many = noun.endsWith('y') ? `${noun.slice(0, -1)}ies` : `${noun}s`;
  return `${count.toLocaleString('en-US')} ${count === 1 ? noun : many}`;
}

/** The confirm step's sentences, from the dry run. */
export function copySummaryLines(summary: AccessoryCopySummary): string[] {
  const lines = [`${plural(summary.targets, 'product')} picked.`];
  const fresh = summary.targets - summary.targets_with_a_list;
  if (fresh > 0) {
    lines.push(`${plural(fresh, 'product')} with no list ${fresh === 1 ? 'gets' : 'get'} the whole list.`);
  }
  if (summary.targets_with_a_list > 0) {
    lines.push(
      `${plural(summary.targets_with_a_list, 'product')} already ${summary.targets_with_a_list === 1 ? 'has' : 'have'} a list: their entries stay, the missing ones are added at the end.`,
    );
  }
  lines.push(
    `${plural(summary.entries_added, 'entry')} will be added` +
      (summary.entries_already_there > 0
        ? `, ${plural(summary.entries_already_there, 'entry')} already there ${summary.entries_already_there === 1 ? 'is' : 'are'} left as ${summary.entries_already_there === 1 ? 'it is' : 'they are'}.`
        : '.'),
  );
  if (summary.box_style_set > 0) {
    lines.push(`The box style is set on ${plural(summary.box_style_set, 'product')} that had none.`);
  }
  return lines;
}

export function CopyAccessoriesDialog({
  open,
  onOpenChange,
  sourceProductId,
  entryCount,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  sourceProductId: string;
  /** Entries on the source's saved list, for the title. */
  entryCount: number;
}) {
  const search = useDebouncedSearch('');
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [brandIds, setBrandIds] = useState<string[]>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'product_code', desc: false }]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [matchingActive, setMatchingActive] = useState(false);
  const [matchingPending, setMatchingPending] = useState(false);
  const [summary, setSummary] = useState<AccessoryCopySummary | null>(null);
  // Bumped whenever the result set changes, so a "Select all" fetch that lands late is dropped.
  const matchingSeq = useRef(0);
  const { preview, copy } = useCopyProductAccessories(sourceProductId);
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

  const { data, isLoading, isFetching, isPlaceholderData } = useProducts(params);
  const rows = useMemo(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;

  const columns = useMemo<ColumnDef<ProductListItem>[]>(
    () => [
      buildSelectColumn<ProductListItem>({
        enableRow: (row) => row.original.id !== sourceProductId,
        disabledReason: (row) => (row.original.id === sourceProductId ? SOURCE_REASON : undefined),
        rowLabel: (row) => `Select ${row.original.product_code}`,
      }),
      {
        accessorKey: 'product_code',
        id: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product Code" column={column} />,
        cell: ({ row }) => (
          <div className="truncate text-sm font-medium" title={row.original.product_code}>
            {row.original.product_code}
          </div>
        ),
        size: 160,
        meta: { headerTitle: 'Product Code' },
        enableSorting: true,
      },
      {
        accessorKey: 'product_name',
        id: 'product_name',
        header: ({ column }) => <DataGridColumnHeader title="Product Name" column={column} />,
        cell: ({ row }) => {
          const name = distinctName(row.original.product_code, row.original.product_name);
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
        accessorKey: 'category_name',
        id: 'category_name',
        header: ({ column }) => <DataGridColumnHeader title="Category" column={column} />,
        cell: ({ row }) => (
          <div className="truncate text-sm" title={row.original.category_name ?? ''}>
            {row.original.category_name || ' - '}
          </div>
        ),
        size: 160,
        meta: { headerTitle: 'Category' },
        enableSorting: true,
      },
      {
        accessorKey: 'brand_name',
        id: 'brand_name',
        header: ({ column }) => <DataGridColumnHeader title="Brand" column={column} />,
        cell: ({ row }) => (
          <div className="truncate text-sm" title={row.original.brand_name ?? ''}>
            {row.original.brand_name || ' - '}
          </div>
        ),
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
    () => Object.keys(rowSelection).filter((id) => rowSelection[id] && id !== sourceProductId),
    [rowSelection, sourceProductId],
  );
  const overCap = picked.length > MAX_COPY_TARGETS;

  const selectAllMatching = async () => {
    const mine = ++matchingSeq.current;
    setMatchingPending(true);
    try {
      const res = await getProducts({ ...params, pageIndex: 0, pageSize: MAX_COPY_TARGETS + 1 });
      if (matchingSeq.current !== mine) return;
      const ids = res.data.map((p) => p.id).filter((id) => id !== sourceProductId).slice(0, MAX_COPY_TARGETS);
      setRowSelection(Object.fromEntries(ids.map((id) => [id, true])));
      setMatchingActive(true);
    } catch (err) {
      if (matchingSeq.current !== mine) return;
      toast.error(err instanceof Error ? err.message : 'Could not select all matching products');
    } finally {
      if (matchingSeq.current === mine) setMatchingPending(false);
    }
    // A superseded fetch leaves `pending` to the effect that superseded it, which clears it.
  };

  const goToConfirm = () => {
    preview.mutate(picked, { onSuccess: setSummary });
  };

  const runCopy = () => {
    copy.mutate(picked, { onSuccess: () => onOpenChange(false) });
  };

  const busy = preview.isPending || copy.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent
        className="flex max-h-[90vh] w-[calc(100vw-2rem)] max-w-5xl flex-col"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>
            {summary ? 'Copy accessories' : `Copy ${plural(entryCount, 'entry')} to other products`}
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto">
          {summary ? (
            <div className="space-y-2 text-sm" data-testid="copy-accessories-summary">
              {copySummaryLines(summary).map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          ) : (
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
                      isSettling={isSearchInFlight(search.isSettling, isFetching, search.debouncedValue)}
                      placeholder="Search products..."
                      className="w-full sm:w-64"
                    />
                  }
                  filters={{
                    kind: 'custom',
                    active: categoryIds.length + brandIds.length > 0,
                    activeCount: (categoryIds.length ? 1 : 0) + (brandIds.length ? 1 : 0),
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
                              <span className="text-muted-foreground">Category: any</span>
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
          )}
        </DialogBody>
        <DialogFooter className="flex-wrap items-center gap-2">
          {!summary ? (
            <span className="mr-auto text-sm text-muted-foreground" aria-live="polite">
              {overCap
                ? `${plural(picked.length, 'product')} picked; one copy takes at most ${MAX_COPY_TARGETS}.`
                : `${plural(picked.length, 'product')} picked`}
            </span>
          ) : null}
          {summary ? (
            <Button variant="outline" onClick={() => setSummary(null)} disabled={busy}>
              Back
            </Button>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
          )}
          {summary ? (
            <Button onClick={runCopy} disabled={busy}>
              {copy.isPending ? <LoaderCircle className="mr-1 size-4 animate-spin" /> : null}
              Copy
            </Button>
          ) : (
            <Button onClick={goToConfirm} disabled={busy || picked.length === 0 || overCap}>
              {preview.isPending ? <LoaderCircle className="mr-1 size-4 animate-spin" /> : null}
              Next
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default CopyAccessoriesDialog;
