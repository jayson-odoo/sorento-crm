'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { formatStatusLabel } from '@/lib/status-badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateInMalaysia } from '@/lib/helpers';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { searchSuppliersForSelect } from '../../suppliers/services/supplierService';
import { useCostPriceChangeSets } from '../hooks/useCostPriceChangeSets';
import { formatPlainDate } from '../lib/formatPlainDate';
import type { CostPriceChangeSetListItem } from '../types/costPrice.types';
import { UploadPriceListDialog } from './UploadPriceListDialog';

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'pending_verification', label: 'Pending verification' },
  { value: 'applied', label: 'Applied' },
];

function validityLabel(row: CostPriceChangeSetListItem): string {
  if (!row.start_date && !row.end_date) return 'Always';
  if (row.start_date && !row.end_date) return `From ${formatPlainDate(row.start_date)}`;
  if (!row.start_date && row.end_date) return `Until ${formatPlainDate(row.end_date)}`;
  return `${formatPlainDate(row.start_date)} - ${formatPlainDate(row.end_date)}`;
}

function verifiedLabel(row: CostPriceChangeSetListItem): string {
  if (row.verified === null) return '-';
  return row.verified ? `Verified by ${row.verified_by_name ?? 'a verifier'}` : 'Not verified';
}

export default function CostPriceUploadsList() {
  const canUpload = useHasPermission('procurement.cost_price_changes.upload');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [supplierId, setSupplierId] = useState('');
  const [supplierOption, setSupplierOption] = useState<{ value: string; label: string } | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();

  useResetPageOnFilterChange(setPagination, [statuses, supplierId, searchQuery]);

  const { data, isLoading, isPlaceholderData, isFetching, isError, error } = useCostPriceChangeSets({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statuses.length ? statuses : undefined,
    supplier_id: supplierId || undefined,
  });

  const rowHref = (row: CostPriceChangeSetListItem) => {
    const search = buildDetailSearch({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
    }, { status: statuses.join(','), supplier_id: supplierId });
    return `/procurement-management/cost-price-uploads/${row.id}${search ? `?${search}` : ''}`;
  };

  const columns = useMemo<ColumnDef<CostPriceChangeSetListItem>[]>(
    () => [
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 100,
        cell: ({ row }) => <span className="font-medium">{row.original.code}</span>,
      },
      {
        id: 'supplier',
        header: 'Supplier and file',
        size: 330,
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium" title={row.original.supplier.supplier_name}>
              {row.original.supplier.supplier_name}
            </div>
            <div className="truncate text-xs text-muted-foreground" title={row.original.file_name ?? ''}>
              {row.original.file_name ?? '-'}
            </div>
          </div>
        ),
      },
      {
        id: 'source',
        header: 'Source',
        size: 110,
        cell: ({ row }) => (row.original.channel === 'staff_upload' ? 'Staff upload' : row.original.channel === 'supplier_page' ? 'Supplier page' : 'Supplier upload'),
      },
      {
        id: 'validity',
        header: 'Valid',
        size: 170,
        cell: ({ row }) => <span className="truncate text-sm" title={validityLabel(row.original)}>{validityLabel(row.original)}</span>,
      },
      {
        id: 'status',
        header: 'Status',
        size: 110,
        cell: ({ row }) => <Badge status={row.original.status}>{formatStatusLabel(row.original.status)}</Badge>,
      },
      {
        id: 'lines_changed',
        header: 'Lines changed',
        size: 110,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.lines_changed}</span>,
      },
      {
        id: 'uploaded_by',
        header: 'Uploaded by',
        size: 130,
        cell: ({ row }) => row.original.uploaded_by_name ?? '-',
      },
      {
        id: 'applied_at',
        header: 'Applied',
        size: 120,
        cell: ({ row }) => (row.original.applied_at ? formatDateInMalaysia(row.original.applied_at) : '-'),
      },
      {
        id: 'verified',
        header: 'Verified',
        size: 160,
        cell: ({ row }) => <span className="truncate text-sm" title={verifiedLabel(row.original)}>{verifiedLabel(row.original)}</span>,
      },
    ],
    [],
  );

  const rows = data?.data ?? [];
  const total = data?.total ?? 0;

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const primaryAction = canUpload ? (
    <Button onClick={() => setUploadOpen(true)}>
      <Plus className="size-4" />
      Upload cost list
    </Button>
  ) : null;

  return (
    <>
      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        isPlaceholderData={isPlaceholderData}
        rowHref={rowHref}
        listingKey="procurement.cost_price_changes.view"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No uploads match your filters yet."
      >
        <Card className="hidden sm:block">
          <CardHeader className="flex flex-wrap items-center gap-2">
            <ListSearchInput
              value={searchInput}
              onChange={setSearchInput}
              isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
              placeholder="Search code, supplier or file name"
              className="w-full sm:w-64"
            />
            <SearchableMultiSelect
              value={statuses}
              onChange={setStatuses}
              options={STATUS_OPTIONS}
              placeholder="Status"
              triggerClassName="w-48"
            />
            <SearchableSelect
              value={supplierId}
              onChange={setSupplierId}
              onOptionChange={(opt) => setSupplierOption(opt)}
              selectedOption={supplierOption ?? undefined}
              fetchOptions={searchSuppliersForSelect}
              clearable
              placeholder="All suppliers"
              triggerClassName="w-56"
            />
            <div className="ms-auto">{primaryAction}</div>
          </CardHeader>
          {isError ? (
            <div className="px-5 pb-2 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load uploads'}
            </div>
          ) : null}
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      {/* Mobile card layout (mockup: cost-price-uploads.html), 375px - the DataGrid above
          stays mounted for its query + pager state, but only renders the table at sm+. */}
      <div className="space-y-3 sm:hidden">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <ListSearchInput
              value={searchInput}
              onChange={setSearchInput}
              isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
              placeholder="Search uploads"
              className="flex-1"
            />
            {primaryAction}
          </div>
          <SearchableMultiSelect value={statuses} onChange={setStatuses} options={STATUS_OPTIONS} placeholder="Status" />
          <SearchableSelect
            value={supplierId}
            onChange={setSupplierId}
            onOptionChange={(opt) => setSupplierOption(opt)}
            selectedOption={supplierOption ?? undefined}
            fetchOptions={searchSuppliersForSelect}
            clearable
            placeholder="All suppliers"
          />
        </div>
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No uploads match your filters yet.</p>
        ) : (
          rows.map((row) => (
            <Link
              key={row.id}
              href={rowHref(row)}
              className="block rounded-lg border border-border bg-card p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{row.code}</span>
                <Badge status={row.status}>{formatStatusLabel(row.status)}</Badge>
              </div>
              <div className="mt-1 truncate text-sm">{row.supplier.supplier_name}</div>
              <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                <span>{validityLabel(row)}</span>
                <span>{row.lines_changed} changed</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                <span>{row.uploaded_by_name ?? '-'}</span>
                <span>{row.applied_at ? formatDateInMalaysia(row.applied_at) : 'Not applied'}</span>
              </div>
            </Link>
          ))
        )}
      </div>

      <UploadPriceListDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </>
  );
}
