'use client';

import { useMemo, useState } from 'react';
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
import { useQuery } from '@tanstack/react-query';
import { Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  listTemplates,
  type TemplateStatus,
  type WhatsAppTemplate,
} from '@/services/whatsappTemplateService';

const STATUS_BADGE_VARIANT: Record<TemplateStatus, 'success' | 'warning' | 'destructive'> = {
  approved: 'success',
  pending: 'warning',
  rejected: 'destructive',
};

export default function TemplatesGrid() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<TemplateStatus | 'all'>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: [
      'whatsapp-templates',
      pagination.pageIndex,
      pagination.pageSize,
      searchQuery,
      statusFilter,
    ],
    queryFn: () =>
      listTemplates({
        page: pagination.pageIndex + 1,
        limit: pagination.pageSize,
        query: searchQuery,
        status: statusFilter,
      }),
  });

  const columns = useMemo<ColumnDef<WhatsAppTemplate>[]>(
    () => [
      buildSelectColumn<WhatsAppTemplate>(),
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs truncate block" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        size: 200,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'language',
        header: ({ column }) => <DataGridColumnHeader title="Language" column={column} />,
        cell: ({ row }) => row.original.language,
        size: 90,
        meta: { headerTitle: 'Language' },
      },
      {
        accessorKey: 'category',
        header: ({ column }) => <DataGridColumnHeader title="Category" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.category}
          </Badge>
        ),
        size: 130,
        meta: { headerTitle: 'Category' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={STATUS_BADGE_VARIANT[row.original.status]}
            appearance="ghost"
            className="capitalize"
          >
            {row.original.status}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'body_text',
        header: ({ column }) => <DataGridColumnHeader title="Body" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block text-muted-foreground" title={row.original.body_text}>
            {row.original.body_text}
          </span>
        ),
        size: 360,
        enableSorting: false,
        meta: { headerTitle: 'Body' },
      },
      {
        accessorKey: 'param_count',
        header: ({ column }) => <DataGridColumnHeader title="Params" column={column} />,
        cell: ({ row }) => row.original.param_count,
        size: 80,
        meta: { headerTitle: 'Params' },
      },
      {
        accessorKey: 'channel_name',
        header: ({ column }) => <DataGridColumnHeader title="Channel" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.channel_name}>
            {row.original.channel_name}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Channel' },
      },
      {
        accessorKey: 'synced_at',
        header: ({ column }) => <DataGridColumnHeader title="Synced" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.synced_at),
        size: 170,
        meta: { headerTitle: 'Synced' },
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
    manualFiltering: true,
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      tableLayout={{
        width: 'fixed',
        columnsResizable: true,
        columnsVisibility: true,
      }}
      emptyMessage="No templates synced yet. Click “Sync templates” to pull templates from your Respond.io workspace."
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative w-full max-w-xs">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search templates..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9"
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
            }
            filters={{
              kind: 'custom',
              active: statusFilter !== 'all',
              activeCount: statusFilter !== 'all' ? 1 : 0,
              content: (
                <div className="space-y-3">
                  <Select
                    value={statusFilter}
                    onValueChange={(v) => setStatusFilter(v as TemplateStatus | 'all')}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Status</SelectItem>
                      <SelectItem value="approved">Approved</SelectItem>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="rejected">Rejected</SelectItem>
                    </SelectContent>
                  </Select>
                  {statusFilter !== 'all' && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setStatusFilter('all')}
                      className="w-full"
                    >
                      Clear Filters
                    </Button>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'whatsapp_templates_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isRefetching}
          />
        </CardHeader>
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
    </DataGrid>
  );
}
