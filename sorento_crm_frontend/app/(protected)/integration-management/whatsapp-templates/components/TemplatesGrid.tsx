'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { Columns3, RefreshCw, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
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
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs truncate block" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'language',
        header: ({ column }) => <DataGridColumnHeader title="Language" column={column} />,
        cell: ({ row }) => row.original.language,
        size: 90,
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
      },
      {
        accessorKey: 'param_count',
        header: ({ column }) => <DataGridColumnHeader title="Params" column={column} />,
        cell: ({ row }) => row.original.param_count,
        size: 80,
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
      },
      {
        accessorKey: 'synced_at',
        header: ({ column }) => <DataGridColumnHeader title="Synced" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.synced_at),
        size: 170,
      },
    ],
    [],
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
    manualFiltering: true,
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      standardToolbar={false}
      tableLayout={{
        width: 'fixed',
        columnsResizable: true,
        columnsVisibility: true,
      }}
      emptyMessage="No templates synced yet. Click “Sync templates” to pull templates from your Respond.io workspace."
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 flex-1">
            <div className="relative flex-1 max-w-xs">
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
            <Select
              value={statusFilter}
              onValueChange={(v) => setStatusFilter(v as TemplateStatus | 'all')}
            >
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="rejected">Rejected</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DataGridColumnVisibility
            table={table}
            trigger={
              <Button variant="outline" size="sm" className="gap-1">
                <Columns3 className="size-4" />
                Columns
              </Button>
            }
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="shrink-0"
          >
            <RefreshCw className={`size-4 mr-2 ${isRefetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
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
