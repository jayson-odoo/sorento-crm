'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, Search, X, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useCampaigns } from '../hooks/useCampaigns';
import type { Campaign } from '../types/campaign.types';
import { formatDate } from '@/lib/helpers';

export default function CampaignsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading } = useCampaigns({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<Campaign>[]>(
    () => [
      {
        accessorKey: 'campaign_code',
        header: ({ column }) => <DataGridColumnHeader title="Campaign Code" column={column} />,
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'campaign_name',
        header: ({ column }) => <DataGridColumnHeader title="Campaign Name" column={column} />,
        size: 250,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'campaign_type.type_name',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => row.original.campaign_type?.type_name || '-',
        size: 150,
      },
      {
        accessorKey: 'start_date',
        header: ({ column }) => <DataGridColumnHeader title="Start Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.start_date)),
        size: 120,
      },
      {
        accessorKey: 'end_date',
        header: ({ column }) => <DataGridColumnHeader title="End Date" column={column} />,
        cell: ({ row }) => row.original.end_date ? formatDate(new Date(row.original.end_date)) : '-',
        size: 120,
      },
      {
        accessorKey: 'budget',
        header: ({ column }) => <DataGridColumnHeader title="Budget" column={column} />,
        cell: ({ row }) => {
          const budget = row.original.budget;
          return budget ? new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(budget) : '-';
        },
        size: 120,
      },
      {
        accessorKey: 'spent',
        header: ({ column }) => <DataGridColumnHeader title="Spent" column={column} />,
        cell: ({ row }) => {
          const spent = row.original.spent;
          return spent ? new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(spent) : '-';
        },
        size: 120,
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.status;
          const variants: Record<string, 'success' | 'secondary' | 'warning' | 'destructive'> = {
            planning: 'secondary',
            active: 'success',
            completed: 'secondary',
            cancelled: 'destructive',
          };
          return (
            <Badge variant={variants[status] || 'secondary'} appearance="ghost">
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Badge>
          );
        },
        size: 120,
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
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}>
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search campaigns..."
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
          <Button onClick={() => router.push('/marketing-management/campaigns/new')}>
            <Plus />
            Create Campaign
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
