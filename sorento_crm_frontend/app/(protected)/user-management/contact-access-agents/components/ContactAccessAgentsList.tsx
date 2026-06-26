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
import { useContactAccessAgents } from '../hooks/useContactAccessAgents';
import type { ContactAccessAgent } from '../types/contactAccessAgent.types';
import { formatDate } from '@/lib/helpers';

export default function ContactAccessAgentsList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, refetch, isFetching } = useContactAccessAgents({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<ContactAccessAgent>[]>(
    () => [
      buildSelectColumn<ContactAccessAgent>(),
      {
        accessorKey: 'respond_contact_phone',
        header: ({ column }) => <DataGridColumnHeader title="Respond Contact Phone" column={column} />,
        size: 200,
        meta: { headerTitle: 'Respond Contact Phone', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'respond_contact_name',
        header: ({ column }) => <DataGridColumnHeader title="Respond Contact Name" column={column} />,
        size: 220,
        meta: { headerTitle: 'Respond Contact Name', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'agent_code',
        header: ({ column }) => <DataGridColumnHeader title="Agent Code" column={column} />,
        size: 150,
        meta: { headerTitle: 'Agent Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'agent_name',
        header: ({ column }) => <DataGridColumnHeader title="Agent Name" column={column} />,
        size: 250,
        meta: { headerTitle: 'Agent Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'is_allowed',
        header: ({ column }) => <DataGridColumnHeader title="Allowed" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_allowed ? 'success' : 'secondary'} appearance="ghost">
            {row.original.is_allowed ? 'Yes' : 'No'}
          </Badge>
        ),
        size: 100,
        meta: { headerTitle: 'Allowed' },
      },
      {
        accessorKey: 'valid_from',
        header: ({ column }) => <DataGridColumnHeader title="Valid From" column={column} />,
        cell: ({ row }) => row.original.valid_from ? formatDate(new Date(row.original.valid_from)) : '-',
        size: 150,
        meta: { headerTitle: 'Valid From' },
      },
      {
        accessorKey: 'valid_to',
        header: ({ column }) => <DataGridColumnHeader title="Valid To" column={column} />,
        cell: ({ row }) => row.original.valid_to ? formatDate(new Date(row.original.valid_to)) : '-',
        size: 150,
        meta: { headerTitle: 'Valid To' },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.created_at)),
        size: 150,
        meta: { headerTitle: 'Created At' },
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
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    enableRowSelection: true,
  });

  return (
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search contact access agents..."
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
            }
            exportConfig={{ filename: 'contact_access_agents_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
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
