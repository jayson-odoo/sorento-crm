'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import AccessAgentFormModal from './AccessAgentFormModal';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, ChevronRight, Columns3 } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ListPageToolbar } from '@/components/common/ListPageToolbar';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useAccessAgents } from '../hooks/useAccessAgents';
import type { AccessAgent } from '../types/accessAgent.types';

export default function AccessAgentsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [formModalOpen, setFormModalOpen] = useState(false);

  const { data, isLoading, refetch, isFetching } = useAccessAgents({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const handleRowClick = (row: AccessAgent) => {
    const agentId = row.id;
    router.push(`/user-management/access-agents/${agentId}`);
  };

  const columns = useMemo<ColumnDef<AccessAgent>[]>(
    () => [
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 250,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => (
          <div className="max-w-md truncate" title={row.original.description || ''}>
            {row.original.description || '-'}
          </div>
        ),
        size: 300,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="ghost">
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 100,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
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
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <ListPageToolbar
          searchPlaceholder="Search access agents..."
          searchValue={searchQuery}
          onSearchChange={(v) => {
            setSearchQuery(v);
            setPagination((p) => ({ ...p, pageIndex: 0 }));
          }}
          createButton={
            <>
              <DataGridColumnVisibility
                table={table}
                trigger={
                  <Button variant="outline" size="sm" className="gap-1">
                    <Columns3 className="size-4" />
                    Columns
                  </Button>
                }
              />
              <Button onClick={() => setFormModalOpen(true)}>
                <Plus />
                Create Access Agent
              </Button>
            </>
          }
          isLoading={isLoading}
        />
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

      <AccessAgentFormModal
        open={formModalOpen}
        onOpenChange={setFormModalOpen}
        onSuccess={() => {}}
      />
    </DataGrid>
  );
}
