'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { useTenders } from '../hooks/useTenders';
import type { TenderListRow } from '../services/tenderService';

export default function TendersList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = searchParams.get('project_id') || undefined;
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const { data, isLoading, isFetching, refetch } = useTenders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting: [],
    searchQuery: '',
    project_id: projectId,
  });

  const rows = data?.data || [];

  const columns = useMemo<ColumnDef<TenderListRow>[]>(
    () => [
      {
        accessorKey: 'tender_code',
        header: ({ column }) => <DataGridColumnHeader title="Tender" column={column} />,
        cell: ({ row }) => <span className="font-medium">{row.original.tender_code}</span>,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Title" column={column} />,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'pipeline_stage',
        header: ({ column }) => <DataGridColumnHeader title="Stage" column={column} />,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'tender_lifecycle',
        header: ({ column }) => <DataGridColumnHeader title="Lifecycle" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.tender_lifecycle === 'open' ? 'success' : 'secondary'} appearance="ghost">
            <BadgeDot />
            {row.original.tender_lifecycle}
          </Badge>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'forecast_amount',
        header: ({ column }) => <DataGridColumnHeader title="Pipeline value" column={column} />,
        cell: ({ row }) => {
          const a = row.original.forecast_amount;
          const c = row.original.forecast_currency;
          if (a == null) return '—';
          return `${a} ${c || ''}`.trim();
        },
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.tender_code,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={(row) => router.push(`/commercial-management/tenders/${encodeURIComponent(row.tender_code)}`)}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2">
          <div className="text-muted-foreground text-sm flex items-center gap-2">
            <Search className="size-4" />
            {projectId ? `Project filter active` : 'All tenders'}
          </div>
          <Button onClick={() => router.push(`/commercial-management/tenders/new${projectId ? `?project_id=${projectId}` : ''}`)}>
            <Plus className="size-4" />
            New tender
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
