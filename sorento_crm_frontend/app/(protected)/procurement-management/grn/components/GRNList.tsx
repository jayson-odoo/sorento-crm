'use client';

import { useMemo, useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, Search, X, ChevronRight, Settings, Upload, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useGRNs } from '../hooks/useGRN';
import type { GRN } from '../types/grn.types';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant, formatStatusLabel } from '@/lib/status-badge';
import { GRNImportDialog } from './GRNImportDialog';
import GRNBulkDeleteDialog from './GRNBulkDeleteDialog';
import { importGRNListing, importGRNLines } from '../services/grnService';
import { useQueryClient } from '@tanstack/react-query';

export default function GRNList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const spoAllocationId = searchParams.get('spo_allocation_id');

  const [uploadMode, setUploadMode] = useState<'listing' | 'lines' | null>(null);
  const [selectedGrnIds, setSelectedGrnIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading } = useGRNs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    spo_allocation_id: spoAllocationId || undefined,
  });

  const handleRowClick = (row: GRN) => {
    const grnId = row.id;
    router.push(`/procurement-management/grn/${grnId}`);
  };

  const toggleGrnSelection = (grnId: string) => {
    setSelectedGrnIds((prev) => {
      const next = new Set(prev);
      if (next.has(grnId)) next.delete(grnId);
      else next.add(grnId);
      return next;
    });
  };

  const selectAllGrns = () => {
    const pageGrns = data?.data ?? [];
    if (selectedGrnIds.size === pageGrns.length) {
      setSelectedGrnIds(new Set());
    } else {
      setSelectedGrnIds(new Set(pageGrns.map((g) => g.id)));
    }
  };

  const pageGrns = data?.data ?? [];
  const isAllSelected = pageGrns.length > 0 && selectedGrnIds.size === pageGrns.length;

  const columns = useMemo<ColumnDef<GRN>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllGrns}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedGrnIds.has(row.original.id)}
            onCheckedChange={() => toggleGrnSelection(row.original.id)}
            aria-label={`Select ${row.original.picking_number ?? row.original.id}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
      {
        accessorKey: 'picking_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="GRN Number" column={column} />
        ),
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'spo_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="SPO Number" column={column} />
        ),
        cell: ({ row }) => row.original.spo_number ?? '-',
        size: 140,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
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
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'lines_count',
        header: ({ column }) => (
          <DataGridColumnHeader title="Number of Items" column={column} />
        ),
        cell: ({ row }) =>
          row.original.lines_count != null ? String(row.original.lines_count) : '0',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-12" /> },
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
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => (
          <ChevronRight className="text-muted-foreground/70 size-3.5" />
        ),
        size: 40,
      },
    ],
    [selectedGrnIds, isAllSelected],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
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
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search GRN..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ps-9 w-64"
            />
            {searchQuery && (
              <Button
                mode="icon"
                variant="dim"
                className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                onClick={() => setSearchQuery('')}
              >
                <X />
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {selectedGrnIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBulkDeleteDialogOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="size-4" />
                Bulk Delete ({selectedGrnIds.size})
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" title="Import options">
                  <Settings className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setUploadMode('listing')}>
                  <Upload className="size-4" />
                  Upload GRN
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setUploadMode('lines')}>
                  <Upload className="size-4" />
                  Upload GRN Lines
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              onClick={() => router.push('/procurement-management/grn/new')}
            >
              <Plus />
              Create GRN
            </Button>
          </div>
        </CardHeader>
        {uploadMode === 'listing' && (
          <GRNImportDialog
            open={true}
            onOpenChange={(open) => !open && setUploadMode(null)}
            title="Upload GRN"
            description="Upload GRN listing Excel"
            onUpload={async (file) => {
              const result = await importGRNListing(file);
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
            onUpload={async (file) => {
              const result = await importGRNLines(file);
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
          if (!open) setSelectedGrnIds(new Set());
        }}
        grnIds={Array.from(selectedGrnIds)}
        onSuccess={() => setSelectedGrnIds(new Set())}
      />
    </DataGrid>
  );
}
