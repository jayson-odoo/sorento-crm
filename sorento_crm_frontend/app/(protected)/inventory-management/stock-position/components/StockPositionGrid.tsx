'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  SortingState,
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useQuery } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { getSuppliersSelect } from '@/services/supplierSelectService';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import { useStockPosition } from '../hooks/useStockPosition';
import { exportStockPosition } from '../services/stockPositionService';
import type { SalesBasis, StockPositionRow } from '../services/stockPosition.types';

const QTY = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });

/** A quantity as the sheet prints it: whole units, thousands separated, a blank for none. */
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

const SALES_BASIS_OPTIONS: { value: SalesBasis; label: string }[] = [
  { value: 'so_ordered', label: 'Sales orders (ordered)' },
  { value: 'invoiced', label: 'Invoiced' },
];

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
  const [salesBasis, setSalesBasis] = useState<SalesBasis>('so_ordered');
  const [exporting, setExporting] = useState(false);

  const { data: brands } = useBrandSelectQuery();
  const { data: warehousesData } = useQuery({
    queryKey: ['warehouses-select-stock-position'],
    queryFn: () => getWarehouses({ pageIndex: 0, pageSize: 100, sorting: [], searchQuery: '', is_active: true }),
  });

  const filters = {
    supplierId: supplier?.value,
    brandId: brandId || undefined,
    warehouseId: warehouseId || undefined,
    salesBasis,
  };
  const params = { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery };
  const { data, isLoading, isPlaceholderData, isFetching, error, refetch } = useStockPosition(params, filters);
  const rows = data?.data ?? [];
  const total = data?.pagination.total ?? 0;
  const warehouseCodes = useMemo(() => (data?.warehouses ?? []).map((w) => w.code), [data?.warehouses]);

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
        id: `wh:${code}`,
        accessorFn: (row) => row.stock[code] ?? 0,
        header: ({ column }) => <DataGridColumnHeader title={code} column={column} />,
        cell: ({ row }) => numberCell(row.original.stock[code] ?? 0),
        size: 90,
        meta: { headerTitle: code },
      })),
      ...FIGURE_COLUMNS.map<ColumnDef<StockPositionRow>>((c) => ({
        id: c.id,
        accessorKey: c.id,
        header: ({ column }) => <DataGridColumnHeader title={c.title} column={column} />,
        cell: ({ row }) => numberCell(row.original[c.id] as number),
        size: c.size,
        meta: { headerTitle: c.title },
      })),
    ],
    [warehouseCodes],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.product_id,
    // The item code stays in view while the figures scroll, as on the supplier sheet.
    initialState: { columnPinning: { left: ['item_code'] } },
    state: { pagination, sorting },
    onPaginationChange: setPagination,
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
  const activeCount = (supplier ? 1 : 0) + (brandId ? 1 : 0) + (warehouseId ? 1 : 0) + (salesBasis !== 'so_ordered' ? 1 : 0);

  const onExport = async () => {
    setExporting(true);
    try {
      await exportStockPosition(params, filters);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to export the stock position');
    } finally {
      setExporting(false);
    }
  };

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
      // The warehouse columns are data: a saved column order would name columns that come and go.
      listingKey={null}
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
                placeholder="Search item code..."
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
                      options={(warehousesData?.data ?? []).map((w) => ({
                        value: w.id,
                        label: w.warehouse_code ?? w.warehouse_name ?? '',
                        description: w.warehouse_name ?? undefined,
                      }))}
                      placeholder="All warehouses"
                      clearable
                      triggerClassName="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Monthly sales from</Label>
                    <SearchableSelect
                      value={salesBasis}
                      onChange={(v) => setSalesBasis((v as SalesBasis) || 'so_ordered')}
                      options={SALES_BASIS_OPTIONS}
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
                          setSalesBasis('so_ordered');
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
