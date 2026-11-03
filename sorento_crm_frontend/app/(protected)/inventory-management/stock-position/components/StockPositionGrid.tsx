'use client';

import { useMemo, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  VisibilityState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { FileSpreadsheet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { toast } from '@/lib/toast';
import { getSuppliersSelect } from '@/services/supplierSelectService';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { useUserListColumnConfigQuery } from '@/lib/listing-column-preferences/useUserListColumnConfigQuery';
import { useStockPosition } from '../hooks/useStockPosition';
import { exportStockPosition } from '../services/stockPositionService';
import type { StockPositionRow } from '../services/stockPosition.types';

const QTY = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });
/** A warehouse column's id is this prefix plus the warehouse code. */
const WAREHOUSE_COLUMN_PREFIX = 'wh:';

/** A quantity as the sheet prints it: whole units, thousands separated, 0 for none. */
export function formatQty(value: number | null | undefined): string {
  if (!value) return '0';
  return QTY.format(value);
}

/** The figure columns after the warehouse ones, in the sheet's order. Ids are the server's sort keys. */
export const FIGURE_COLUMNS: { id: keyof StockPositionRow; title: string; size: number }[] = [
  { id: 'incoming_pool', title: 'Incoming BRW', size: 130 },
  { id: 'total_stock', title: 'Total stock', size: 100 },
  { id: 'incoming_project', title: 'Incoming (Project)', size: 155 },
  { id: 'total_incoming', title: 'Total incoming', size: 135 },
  { id: 'packing_list_open', title: 'Packing list, no SPO', size: 170 },
  { id: 'outstanding_dealer', title: 'Outstanding dealer', size: 160 },
  { id: 'outstanding_po', title: 'Outstanding PO', size: 140 },
  { id: 'monthly_sales', title: 'Monthly sales', size: 135 },
  { id: 'highest_month', title: 'Highest / month', size: 140 },
];

/** The columns each total adds up, by column id: a hidden one drops out (owner 2 Nov). */
const INCOMING_PARTS = ['incoming_pool', 'incoming_project'] as const;
const isTotalPart = (id: string) =>
  id.startsWith(WAREHOUSE_COLUMN_PREFIX) || (INCOMING_PARTS as readonly string[]).includes(id);

/** The hidden total-part column ids, sorted (one cache entry per set, whatever the toggle order). */
export const hiddenParts = (visibility: VisibilityState) =>
  Object.keys(visibility)
    .filter((id) => visibility[id] === false && isTotalPart(id))
    .sort();

/** What a total header's tooltip says it adds up: the shown parts, by their headers. */
export function totalTooltip(shownParts: string[]): string {
  return `Sum of ${shownParts.length ? shownParts.join(', ') : 'none'}`;
}

/** A row opens Stock status for its item, with its documents behind every figure. */
const stockStatusHref = (row: StockPositionRow) => `/inventory-management/stock-status?product_id=${row.product_id}`;

function numberCell(value: number) {
  return <span className={`block text-right tabular-nums ${value < 0 ? 'text-destructive' : ''}`}>{formatQty(value)}</span>;
}

export default function StockPositionGrid() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'item_code', desc: false }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const [supplier, setSupplier] = useState<{ value: string; label: string } | null>(null);
  const [brandId, setBrandId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [exporting, setExporting] = useState(false);
  // Controlled so the hidden columns reach the query: the saved layout and saved views apply
  // through `table.setColumnVisibility`, which writes here.
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  // Kept the same array while the hidden SET is unchanged (hiding a non-total column changes
  // `columnVisibility` but no total), so the query key and the page reset below ignore it.
  const hiddenKey = JSON.stringify(hiddenParts(columnVisibility));
  const hiddenColumns = useMemo<string[]>(() => JSON.parse(hiddenKey), [hiddenKey]);

  // The saved column layout, read through the SAME cached query the DataGrid's preferences hook
  // applies it from (the page path is the listing key), so the first stock request already
  // carries its hidden columns: no total briefly counts a column the user hid. Seeded once, during
  // render; the hook's later apply sets the same visibility, so it changes no total.
  const savedLayout = useUserListColumnConfigQuery(usePathname());
  const layoutSettled = savedLayout.isSuccess || savedLayout.isError;
  const [seeded, setSeeded] = useState(false);
  if (layoutSettled && !seeded) {
    setSeeded(true);
    const saved = (savedLayout.data?.config as { columnVisibility?: Record<string, unknown> } | null | undefined)
      ?.columnVisibility;
    if (saved && typeof saved === 'object') {
      const fromSaved: VisibilityState = {};
      for (const [id, visible] of Object.entries(saved)) if (typeof visible === 'boolean') fromSaved[id] = visible;
      setColumnVisibility((prev) => ({ ...fromSaved, ...prev }));
    }
  }

  // A total changes on every row with its parts, so the server re-sorts: back to page 1, in the
  // SAME render the hidden set changes, so no request goes out for the old page with the new set.
  const [pagedFor, setPagedFor] = useState(hiddenKey);
  const pageIndex = pagedFor === hiddenKey ? pagination.pageIndex : 0;
  if (pagedFor !== hiddenKey) {
    setPagedFor(hiddenKey);
    if (pagination.pageIndex !== 0) setPagination((p) => ({ ...p, pageIndex: 0 }));
  }

  const { data: brands } = useBrandSelectQuery();

  const filters = {
    supplierId: supplier?.value,
    brandId: brandId || undefined,
    warehouseId: warehouseId || undefined,
    hiddenColumns,
  };
  const params = { pageIndex, pageSize: pagination.pageSize, sorting, searchQuery };
  const { data, isLoading, isPlaceholderData, isFetching, error, refetch } = useStockPosition(params, filters, {
    enabled: layoutSettled && seeded,
  });
  const rows = data?.data ?? [];
  const total = data?.pagination.total ?? 0;
  const warehouseCodes = useMemo(() => (data?.warehouses ?? []).map((w) => w.code), [data?.warehouses]);
  const tooltips = useMemo(() => {
    const hidden = new Set(hiddenColumns);
    const shown = (id: string) => !hidden.has(id);
    const shownCodes = warehouseCodes.filter((code) => shown(`${WAREHOUSE_COLUMN_PREFIX}${code}`));
    const pool = shown('incoming_pool') ? ['Incoming BRW'] : [];
    const project = shown('incoming_project') ? ['Incoming (Project)'] : [];
    return {
      total_stock: totalTooltip([...shownCodes, ...pool]),
      total_incoming: totalTooltip([...pool, ...project]),
    } as Partial<Record<keyof StockPositionRow, string>>;
  }, [warehouseCodes, hiddenColumns]);

  const columns = useMemo<ColumnDef<StockPositionRow>[]>(
    () => [
      {
        id: 'item_code',
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item code" column={column} />,
        cell: ({ row }) => (
          <Link
            href={stockStatusHref(row.original)}
            onClick={(e) => e.stopPropagation()}
            className="block truncate font-medium text-primary hover:underline"
            title={row.original.description ?? row.original.item_code}
          >
            {row.original.item_code}
          </Link>
        ),
        size: 160,
        meta: { headerTitle: 'Item code' },
      },
      {
        id: 'supplier_name',
        accessorKey: 'supplier_name',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.supplier_name ?? undefined}>
            {row.original.supplier_name ?? '-'}
          </span>
        ),
        size: 180,
        meta: { headerTitle: 'Supplier' },
      },
      {
        id: 'brand_name',
        accessorKey: 'brand_name',
        header: ({ column }) => <DataGridColumnHeader title="Brand" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.brand_name ?? undefined}>
            {row.original.brand_name ?? '-'}
          </span>
        ),
        size: 120,
        meta: { headerTitle: 'Brand' },
      },
      // One column per site-pool warehouse holding stock, as the server lists them (owner: no
      // "Stock" word in the header, the code alone).
      ...warehouseCodes.map<ColumnDef<StockPositionRow>>((code) => ({
        id: `${WAREHOUSE_COLUMN_PREFIX}${code}`,
        accessorFn: (row) => row.stock[code] ?? 0,
        header: ({ column }) => <DataGridColumnHeader title={code} column={column} />,
        cell: ({ row }) => numberCell(row.original.stock[code] ?? 0),
        size: 90,
        meta: { headerTitle: code },
      })),
      ...FIGURE_COLUMNS.map<ColumnDef<StockPositionRow>>((c) => ({
        id: c.id,
        accessorKey: c.id,
        // A total's header names the shown columns it adds up (hover).
        header: ({ column }) =>
          tooltips[c.id] ? (
            <div title={tooltips[c.id]}>
              <DataGridColumnHeader title={c.title} column={column} />
            </div>
          ) : (
            <DataGridColumnHeader title={c.title} column={column} />
          ),
        cell: ({ row }) => numberCell(row.original[c.id] as number),
        size: c.size,
        meta: { headerTitle: c.title },
      })),
    ],
    [warehouseCodes, tooltips],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.product_id,
    // The item code stays in view while the figures scroll, as on the supplier sheet.
    initialState: { columnPinning: { left: ['item_code'] } },
    state: { pagination, sorting, columnVisibility },
    onPaginationChange: setPagination,
    onColumnVisibilityChange: setColumnVisibility,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const resetPage = () => setPagination((p) => ({ ...p, pageIndex: 0 }));
  const activeCount = (supplier ? 1 : 0) + (brandId ? 1 : 0) + (warehouseId ? 1 : 0);

  const onExport = async () => {
    setExporting(true);
    try {
      // The same hidden columns as the grid: the workbook's warehouse columns and totals are the screen's.
      await exportStockPosition(params, filters);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to export the stock position');
    } finally {
      setExporting(false);
    }
  };

  // The grid mounts once the warehouse columns are known: the saved column choices (which
  // warehouses show, owner ruling Q5) are applied once, at mount, to the columns that exist then.
  if (!data) {
    return error ? (
      <Card>
        <CardHeader className="flex flex-col items-start gap-2">
          <span className="text-sm font-medium">The stock position could not be loaded</span>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </CardHeader>
      </Card>
    ) : (
      <Card>
        <CardHeader className="space-y-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-64 w-full" />
        </CardHeader>
      </Card>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      isPlaceholderData={isPlaceholderData}
      rowHref={stockStatusHref}
      standardToolbar={false}
      // Column choices are saved per user (owner ruling Q5: the user picks which warehouses show);
      // the page path is the listing key.
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true, columnsPinnable: true }}
      emptyMessage={
        <div className="flex w-full flex-col items-center gap-1 py-6">
          <span className="text-sm font-medium">No items to show</span>
          <span className="text-xs text-muted-foreground">Clear the search or filters to see every item.</span>
        </div>
      }
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={searchInput}
                onChange={(v) => {
                  setSearchInput(v);
                  resetPage();
                }}
                isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                placeholder="Search item code or description..."
                className="w-full sm:w-64"
              />
            }
            filters={{
              kind: 'custom',
              active: activeCount > 0,
              activeCount,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Supplier</Label>
                    <SearchableSelect
                      value={supplier?.value ?? ''}
                      selectedOption={supplier ?? undefined}
                      fetchOptions={(q, pageIndex) => getSuppliersSelect(q, pageIndex)}
                      onChange={(v) => {
                        if (!v) setSupplier(null);
                        resetPage();
                      }}
                      onOptionChange={(option) => setSupplier(option ? { value: option.value, label: option.label } : null)}
                      placeholder="All suppliers"
                      clearable
                      triggerClassName="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Brand</Label>
                    <SearchableSelect
                      value={brandId}
                      onChange={(v) => {
                        setBrandId(v);
                        resetPage();
                      }}
                      options={(brands ?? []).map((b) => ({ value: b.id, label: b.brand_name }))}
                      placeholder="All brands"
                      clearable
                      triggerClassName="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Warehouse</Label>
                    <SearchableSelect
                      value={warehouseId}
                      onChange={(v) => {
                        setWarehouseId(v);
                        resetPage();
                      }}
                      // The report's own warehouse columns: any other location could never match.
                      options={(data?.warehouses ?? []).map((w) => ({ value: w.id, label: w.code }))}
                      placeholder="All warehouses"
                      clearable
                      triggerClassName="mt-1"
                    />
                  </div>
                  {activeCount > 0 && (
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSupplier(null);
                          setBrandId('');
                          setWarehouseId('');
                          resetPage();
                        }}
                      >
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={false}
            secondaryActions={[
              {
                key: 'export',
                label: exporting ? 'Exporting...' : 'Export to Excel',
                icon: FileSpreadsheet,
                disabled: exporting,
                onClick: () => void onExport(),
              },
            ]}
          />
        </CardHeader>
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
