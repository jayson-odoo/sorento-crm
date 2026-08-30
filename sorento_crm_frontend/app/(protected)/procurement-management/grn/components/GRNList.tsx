'use client';

import { useMemo, useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, Search, Trash2, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useGRNs } from '../hooks/useGRN';
import { GrnRowActions } from '../actions';
import { buildDetailSearch } from '@/lib/listNavQuery';
import type { GRN } from '../types/grn.types';
import { formatDate } from '@/lib/helpers';
import { formatStatusLabel } from '@/lib/status-badge';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { GRNImportDialog } from './GRNImportDialog';
import GRNBulkDeleteDialog from './GRNBulkDeleteDialog';
import { importGRNListing, importGRNLines, validateGRNListing, validateGRNLines } from '../services/grnService';
import { useImportJobDrawer } from '@/components/upload-activity';
import { useQueryClient } from '@tanstack/react-query';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';

export default function GRNList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { notifyImportQueued } = useImportJobDrawer();
  const spoAllocationId = searchParams.get('spo_allocation_id');

  const [uploadMode, setUploadMode] = useState<'listing' | 'lines' | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Back hands the list its own query string back, and the pager keeps
  // rewriting it, so the list reads it (S3-01). One hook, every list.
  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    setSearchQuery(state.searchQuery);
    setStatusFilter(state.filters.picking_status ?? 'all');
  });

  const { data, isLoading } = useGRNs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    picking_status: statusFilter === 'all' ? undefined : statusFilter,
    spo_allocation_id: spoAllocationId || undefined,
  });

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [searchQuery, statusFilter, spoAllocationId]);

  // The whole row opens the record, carrying the list query the pager rebuilds
  // its key from.
  const rowHref = (row: GRN) => {
    const search = buildDetailSearch(
      {
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
      },
      {
        picking_status: statusFilter === 'all' ? undefined : statusFilter,
      },
    );
    return `/procurement-management/grn/${row.id}${search ? `?${search}` : ''}`;
  };

  const columns = useMemo<ColumnDef<GRN>[]>(
    () => [
      buildSelectColumn<GRN>(),
      {
        accessorKey: 'picking_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="GRN Number" column={column} />
        ),
        size: 150,
        meta: { headerTitle: 'GRN Number', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'spo_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="SPO Number" column={column} />
        ),
        cell: ({ row }) => row.original.spo_number ?? '-',
        size: 140,
        meta: { headerTitle: 'SPO Number', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'picking_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Picking Date" column={column} />
        ),
        cell: ({ row }) =>
          row.original.picking_date
            ? formatDate(new Date(row.original.picking_date))
            : '-',
        size: 120,
        meta: { headerTitle: 'Picking Date', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'items_count',
        header: ({ column }) => (
          <DataGridColumnHeader title="Number of Items" column={column} />
        ),
        cell: ({ row }) =>
          row.original.items_count != null ? String(row.original.items_count) : '0',
        size: 120,
        meta: { headerTitle: 'Number of Items', skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        accessorKey: 'picking_status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        cell: ({ row }) => {
          const status = row.original.picking_status;
          return (
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(status)}`}>
              {formatStatusLabel(status) || '-'}
            </span>
          );
        },
        size: 120,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => <GrnRowActions grn={row.original} />,
        size: 60,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button onClick={() => router.push('/procurement-management/grn/new')}>
      <Plus />
      Create GRN
    </Button>
  );

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      rowHref={rowHref}
      tableLayout={{ columnsVisibility: true }}
      standardToolbar={false}
      emptyAction={listPrimaryAction}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search GRN, SPO, or product..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-64 ps-9"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                    onClick={() => setSearchQuery('')}
                    aria-label="Clear search"
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            filters={{
              kind: 'custom',
              active: statusFilter !== 'all',
              activeCount: statusFilter !== 'all' ? 1 : 0,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Status</Label>
                    <SearchableSelect
                      value={statusFilter}
                      onChange={(value) => setStatusFilter(value)}
                      placeholder="Status"
                      triggerClassName="mt-1 w-full"
                      options={[
                        { value: 'all', label: 'All statuses' },
                        { value: 'draft', label: 'Draft' },
                        { value: 'approved', label: 'Approved' },
                        { value: 'rejected', label: 'Rejected' },
                      ]}
                    />
                  </div>
                  {statusFilter !== 'all' && (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={() => setStatusFilter('all')}>
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'grn_export.xlsx' }}
            primaryAction={listPrimaryAction}
            secondaryActions={[
              {
                key: 'upload-grn',
                label: 'Upload GRN',
                icon: Upload,
                onClick: () => setUploadMode('listing'),
                dataGuideTarget: 'procurement.grn.import-options-button',
              },
              {
                key: 'upload-grn-lines',
                label: 'Upload GRN Lines',
                icon: Upload,
                onClick: () => setUploadMode('lines'),
              },
            ]}
            bulkActions={[
              {
                key: 'delete',
                label: 'Delete',
                icon: Trash2,
                destructive: true,
                onClick: () => setBulkDeleteDialogOpen(true),
              },
            ]}
          />
        </CardHeader>
        {uploadMode === 'listing' && (
          <GRNImportDialog
            open={true}
            onOpenChange={(open) => !open && setUploadMode(null)}
            title="Upload GRN"
            description="Upload GRN listing Excel"
            onTest={validateGRNListing}
            onUpload={async (file) => {
              const result = await importGRNListing(file);
              notifyImportQueued();
              queryClient.invalidateQueries({ queryKey: ['grn'] });
              queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
              return result;
            }}
          />
        )}
        {uploadMode === 'lines' && (
          <GRNImportDialog
            open={true}
            onOpenChange={(open) => !open && setUploadMode(null)}
            title="Upload GRN Lines"
            description="Upload GRN lines Excel"
            onTest={validateGRNLines}
            onUpload={async (file) => {
              const result = await importGRNLines(file);
              notifyImportQueued();
              queryClient.invalidateQueries({ queryKey: ['grn'] });
              queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
              return result;
            }}
          />
        )}
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
      <GRNBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={(open) => {
          setBulkDeleteDialogOpen(open);
          if (!open) setRowSelection({});
        }}
        grnIds={selectedRowIds(table)}
        onSuccess={() => setRowSelection({})}
      />
    </DataGrid>
  );
}
