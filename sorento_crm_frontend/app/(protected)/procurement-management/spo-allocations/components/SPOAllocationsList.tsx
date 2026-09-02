'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus, Trash2, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { pendingEntityKey, usePendingEntityKeys } from '@/lib/pending-entity-store';
import { useDeferredBulkAction } from '@/hooks/useDeferredBulkAction';
import { useImportJobDrawer } from '@/components/upload-activity';
import { useQueryClient } from '@tanstack/react-query';
import { useSPODocuments } from '../hooks/useSPODocuments';
import { importSPOAllocations, validateSPOAllocations } from '../services/spoAllocationService';
import { SPOImportDialog } from './SPOImportDialog';
import { ProductCombobox } from './ProductCombobox';
import { WarehouseCombobox } from './WarehouseCombobox';
import { getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import type { Warehouse } from '@/app/(protected)/inventory-management/warehouses/types/warehouse.types';
import { spoDocumentStatusPill, fmtEta, fmtQty, overdueClassName } from '../lib/spoDocumentStatus';
import type { SPODocumentRow, SPODocumentState } from '../types/spoDocument.types';

interface ProductOption {
  id: string;
  product_code: string;
  product_name?: string;
}

/**
 * The SPO document list (plan: "the page should read like the Purchase Orders page").
 * One row per `spo_number`; the form view (`[spoNumber]/page.tsx`) shows the lines.
 *
 * Bulk delete is the D7/S6 deferred-countdown UI, `useDeferredBulkAction` (review B4) -
 * NOT a hand-rolled client timer: that shape's unmount cleanup cancelled `setTimeout`
 * without cancelling the SERVER's countdown, so navigating away mid-window silently
 * dropped the delete the toast promised was still running. The hook parks one
 * `spo_document.delete` pending action per selected `spo_number`
 * (`app/services/record_actions.py`) behind ONE countdown; the server commits on lapse
 * even if the tab closes, exactly like every other deferred delete in the product.
 */
export default function SPOAllocationsList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { notifyImportQueued } = useImportJobDrawer();

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearchQuery,
  } = useDebouncedSearch();
  // Default Outstanding - the question this screen exists to answer (plan Journey).
  const [stateFilter, setStateFilter] = useState<SPODocumentState>('outstanding');
  const [productFilter, setProductFilter] = useState('');
  const [warehouseFilter, setWarehouseFilter] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [importDialogOpen, setImportDialogOpen] = useState(false);

  // Product picker: SERVER search, never a capped local list (standing rule) - the same
  // real `/products` endpoint the create form already reads.
  const [productSearch, setProductSearch] = useState('');
  const [products, setProducts] = useState<ProductOption[]>([]);
  useEffect(() => {
    let cancelled = false;
    getProducts({ pageIndex: 0, pageSize: 50, sorting: [], searchQuery: productSearch, status: 'active' }).then(
      (res) => {
        if (!cancelled) setProducts(res.data ?? []);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [productSearch]);

  // Warehouses fully enumerated once - a small table, unlike the product catalogue.
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  useEffect(() => {
    getWarehouses({ pageIndex: 0, pageSize: 100, sorting: [], searchQuery: '', is_active: true }).then((res) =>
      setWarehouses(res.data ?? []),
    );
  }, []);

  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearchQuery(state.searchQuery);
    setStateFilter((state.filters.state as SPODocumentState) || 'outstanding');
    setProductFilter(state.filters.product_id ?? '');
    setWarehouseFilter(state.filters.warehouse_id ?? '');
  });

  const { data, isLoading, isFetching, refetch } = useSPODocuments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    state: stateFilter,
    productId: productFilter || null,
    warehouseId: warehouseFilter || null,
  });

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
    setRowSelection({});
  }, [searchQuery, stateFilter, productFilter, warehouseFilter]);

  const rows = useMemo<SPODocumentRow[]>(() => data?.data ?? [], [data]);

  const detailSearch = useMemo(
    () =>
      buildDetailSearch(
        { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
        {
          state: stateFilter !== 'outstanding' ? stateFilter : undefined,
          product_id: productFilter || undefined,
          warehouse_id: warehouseFilter || undefined,
        },
      ),
    [pagination.pageIndex, pagination.pageSize, sorting, searchQuery, stateFilter, productFilter, warehouseFilter],
  );

  // Slash-encoded (Q7): an SPO number can carry a literal `/` (e.g. `SPO-2026/08-0061`),
  // which a Next.js `[spoNumber]` segment must receive as ONE encoded path piece.
  const detailHref = (row: SPODocumentRow) =>
    `/procurement-management/spo-allocations/${encodeURIComponent(row.spo_number)}${detailSearch ? `?${detailSearch}` : ''}`;

  const columns = useMemo<ColumnDef<SPODocumentRow>[]>(
    () => [
      buildSelectColumn<SPODocumentRow>({ rowLabel: (row) => `Select ${row.original.spo_number}` }),
      {
        accessorKey: 'spo_number',
        header: ({ column }) => <DataGridColumnHeader title="SPO No" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <Link
              href={detailHref(row.original)}
              onClick={(e) => e.stopPropagation()}
              className="font-medium text-primary hover:underline"
              title={`Open ${row.original.spo_number}`}
            >
              {row.original.spo_number}
            </Link>
            <span className="text-xs text-muted-foreground">{fmtEta(row.original.doc_date)}</span>
          </div>
        ),
        size: 190,
        meta: { headerTitle: 'SPO No', skeleton: <Skeleton className="h-8 w-28" /> },
      },
      {
        accessorKey: 'supplier_name',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => {
          const { supplier_name, supplier_extra_count } = row.original;
          return (
            <span className="truncate" title={supplier_name ?? undefined}>
              {supplier_name ?? '-'}
              {supplier_extra_count > 0 ? (
                <span className="ms-1 text-xs text-muted-foreground">
                  +{supplier_extra_count} more
                </span>
              ) : null}
            </span>
          );
        },
        size: 200,
        meta: { headerTitle: 'Supplier' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const pill = spoDocumentStatusPill(row.original.status);
          return (
            <Badge variant={pill.variant} appearance="light" size="md">
              {pill.label}
            </Badge>
          );
        },
        size: 130,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'earliest_eta',
        header: ({ column }) => <DataGridColumnHeader title="Earliest ETA" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{fmtEta(row.original.earliest_eta)}</span>
        ),
        size: 130,
        meta: { headerTitle: 'Earliest ETA' },
      },
      {
        accessorKey: 'total_allocated',
        header: ({ column }) => <DataGridColumnHeader title="Total qty" column={column} />,
        cell: ({ row }) => fmtQty(row.original.total_allocated),
        size: 100,
        meta: { headerTitle: 'Total qty', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'line_count',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        cell: ({ row }) => fmtQty(row.original.line_count),
        size: 80,
        meta: { headerTitle: 'Lines', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'balance',
        header: ({ column }) => <DataGridColumnHeader title="Balance" column={column} />,
        cell: ({ row }) => fmtQty(row.original.balance),
        size: 100,
        meta: { headerTitle: 'Balance', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'worst_overdue_days',
        header: ({ column }) => <DataGridColumnHeader title="Overdue" column={column} />,
        cell: ({ row }) => {
          const days = row.original.worst_overdue_days;
          return <span className={overdueClassName(days)}>{days > 0 ? `${days}d` : '-'}</span>;
        },
        size: 100,
        meta: { headerTitle: 'Overdue', headerClassName: 'text-right', cellClassName: 'text-right' },
      },
    ],
    [detailSearch],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.spo_number,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const selectedSpoNumbers = table.getSelectedRowModel().rows.map((r) => r.original.spo_number);

  // A document counting down its delete stays on the list, dimmed, until the window
  // lapses or is cancelled - the toast holds the Cancel, this says which rows they are.
  const pendingKeys = usePendingEntityKeys();
  const rowPending = (row: SPODocumentRow) =>
    pendingKeys.has(pendingEntityKey('spo_document', row.spo_number));

  // Delete selected asks nothing (D7): one `spo_document.delete` pending action per
  // selected SPO number, ONE countdown over them, one Cancel that withdraws the lot -
  // the server commits on lapse even if this tab closes (review B4).
  const bulkDeletion = useDeferredBulkAction({
    actionKey: 'spo_document.delete',
    entityType: 'spo_document',
    describe: (count) => `${count} SPO document${count === 1 ? '' : 's'}`,
    invalidateKeys: [['spo-allocations']],
    onStarted: () => table.resetRowSelection(),
  });

  const listPrimaryAction = (
    <Button onClick={() => router.push('/procurement-management/spo-allocations/new')}>
      <Plus className="size-4" />
      Create SPO Allocation
    </Button>
  );

  const filtersActive = (productFilter ? 1 : 0) + (warehouseFilter ? 1 : 0);

  const emptyMessage =
    filtersActive || searchQuery || stateFilter !== 'outstanding' ? (
      'No SPO document matches this search and filter.'
    ) : (
      <span>No SPO allocations yet. Import the SPO book from the Actions menu, or create one.</span>
    );

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={emptyMessage}
      emptyAction={listPrimaryAction}
      rowHref={(row) => detailHref(row)}
      rowPending={rowPending}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <>
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                  placeholder="Search SPO or product..."
                  className="w-56"
                />
                <ToggleGroup
                  type="single"
                  variant="outline"
                  value={stateFilter}
                  onValueChange={(v) => v && setStateFilter(v as SPODocumentState)}
                >
                  <ToggleGroupItem value="all" className="px-3">
                    All
                  </ToggleGroupItem>
                  <ToggleGroupItem value="outstanding" className="px-3">
                    Outstanding
                  </ToggleGroupItem>
                  <ToggleGroupItem value="completed" className="px-3">
                    Completed
                  </ToggleGroupItem>
                </ToggleGroup>
                {/* Overdue-only toggle retired (UAT AC-4): worst_overdue_days is
                    already a sortable column, and the query filter now reaches
                    warehouse code and packing list number too (AC-25), which made
                    the standalone toggle redundant. */}
              </>
            }
            filters={{
              kind: 'custom',
              active: filtersActive > 0,
              activeCount: filtersActive,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="spo-doc-product" className="mb-1 block">
                      Product
                    </Label>
                    <ProductCombobox
                      value={productFilter}
                      onChange={setProductFilter}
                      products={products}
                      placeholder="Any product"
                      onSearch={setProductSearch}
                      clearable
                    />
                  </div>
                  <div>
                    <Label htmlFor="spo-doc-warehouse" className="mb-1 block">
                      Warehouse
                    </Label>
                    <WarehouseCombobox
                      value={warehouseFilter}
                      onChange={setWarehouseFilter}
                      warehouses={warehouses}
                      placeholder="Any warehouse"
                      clearable
                    />
                  </div>
                  {filtersActive > 0 ? (
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setProductFilter('');
                          setWarehouseFilter('');
                        }}
                      >
                        Clear filters
                      </Button>
                    </div>
                  ) : null}
                </div>
              ),
            }}
            exportConfig={{ filename: 'spo_allocations_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching}
            secondaryActions={[
              {
                key: 'import',
                label: 'Import SPO',
                icon: Upload,
                onClick: () => setImportDialogOpen(true),
                dataGuideTarget: 'procurement.spo-allocations.import-options-button',
              },
              {
                key: 'delete-selected',
                label: 'Delete selected',
                icon: Trash2,
                destructive: true,
                disabled: !selectedSpoNumbers.length || bulkDeletion.isStarting,
                disabledReason: 'Select one or more SPO documents to delete',
                onClick: () =>
                  bulkDeletion.run(selectedSpoNumbers.map((spoNumber) => ({ id: spoNumber }))),
              },
            ]}
            primaryAction={listPrimaryAction}
          />
        </CardHeader>
        <SPOImportDialog
          open={importDialogOpen}
          onOpenChange={setImportDialogOpen}
          onTest={validateSPOAllocations}
          onUpload={async (files) => {
            const result = await importSPOAllocations(files);
            notifyImportQueued();
            queryClient.invalidateQueries({ queryKey: ['spo-allocations'] });
            queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
            return result;
          }}
        />
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
