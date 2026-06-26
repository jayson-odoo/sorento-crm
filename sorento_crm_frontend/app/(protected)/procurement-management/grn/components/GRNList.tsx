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
import { ChevronRight, Plus, Search, Trash2, Upload, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
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
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useGRNs } from '../hooks/useGRN';
import { buildDetailSearch } from '@/lib/listNavQuery';
import type { GRN } from '../types/grn.types';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant, formatStatusLabel } from '@/lib/status-badge';
import { GRNImportDialog } from './GRNImportDialog';
import GRNBulkDeleteDialog from './GRNBulkDeleteDialog';
import { importGRNListing, importGRNLines, validateGRNListing, validateGRNLines } from '../services/grnService';
import { useImportJobDrawer } from '@/components/upload-activity';
import { useQueryClient } from '@tanstack/react-query';

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

  const handleRowClick = (row: GRN) => {
    const grnId = row.id;
    // Carry the active list query (search/sort/status filters) into the detail
    // URL so the detail pager walks the exact same filtered+sorted set.
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
    router.push(
      `/procurement-management/grn/${grnId}${search ? `?${search}` : ''}`,
    );
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
            <Badge variant={getStatusBadgeVariant(status)}>
              {formatStatusLabel(status) || '-'}
            </Badge>
          );
        },
        size: 120,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => (
          <ChevronRight className="text-muted-foreground/70 size-3.5" />
        ),
        size: 40,
        enableHiding: false,
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

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
      tableLayout={{ columnsVisibility: true }}
      standardToolbar={false}
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
                    <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value)}>
                      <SelectTrigger className="mt-1 w-full">
                        <SelectValue placeholder="Status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All statuses</SelectItem>
                        <SelectItem value="draft">Draft</SelectItem>
                        <SelectItem value="approved">Approved</SelectItem>
                        <SelectItem value="rejected">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
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
            primaryAction={
              <Button onClick={() => router.push('/procurement-management/grn/new')}>
                <Plus />
                Create GRN
              </Button>
            }
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
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
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
