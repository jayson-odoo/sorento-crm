'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
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
import { Plus, Search, X, ChevronRight } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useCampaigns } from '../hooks/useCampaigns';
import type { Campaign } from '../types/campaign.types';
import { CAMPAIGN_STATUSES, campaignStatusLabel } from '../types/campaign.types';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant } from '@/lib/status-badge';

export default function CampaignsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [statusFilter]);

  const { data, isLoading, refetch, isFetching } = useCampaigns({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const columns = useMemo<ColumnDef<Campaign>[]>(
    () => [
      buildSelectColumn<Campaign>(),
      {
        accessorKey: 'campaign_code',
        header: ({ column }) => <DataGridColumnHeader title="Campaign Code" column={column} />,
        size: 150,
        meta: { headerTitle: 'Campaign Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'campaign_name',
        header: ({ column }) => <DataGridColumnHeader title="Campaign Name" column={column} />,
        size: 250,
        meta: { headerTitle: 'Campaign Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'campaign_type.type_name',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => row.original.campaign_type?.type_name || '-',
        size: 150,
        meta: { headerTitle: 'Type' },
      },
      {
        accessorKey: 'start_date',
        header: ({ column }) => <DataGridColumnHeader title="Start Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.start_date)),
        size: 120,
        meta: { headerTitle: 'Start Date' },
      },
      {
        accessorKey: 'end_date',
        header: ({ column }) => <DataGridColumnHeader title="End Date" column={column} />,
        cell: ({ row }) => row.original.end_date ? formatDate(new Date(row.original.end_date)) : '-',
        size: 120,
        meta: { headerTitle: 'End Date' },
      },
      {
        accessorKey: 'budget',
        header: ({ column }) => <DataGridColumnHeader title="Budget" column={column} />,
        cell: ({ row }) => {
          const budget = row.original.budget;
          return budget ? new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(budget) : '-';
        },
        size: 120,
        meta: { headerTitle: 'Budget' },
      },
      {
        accessorKey: 'spent',
        header: ({ column }) => <DataGridColumnHeader title="Spent" column={column} />,
        cell: ({ row }) => {
          const spent = row.original.spent;
          return spent ? new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(spent) : '-';
        },
        size: 120,
        meta: { headerTitle: 'Spent' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.status;
          return (
            <Badge variant={getStatusBadgeVariant(status)} appearance="ghost">
              {campaignStatusLabel(status)}
            </Badge>
          );
        },
        size: 120,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
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
      standardToolbar={false}
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
                      onChange={setStatusFilter}
                      options={[
                        { value: 'all', label: 'All statuses' },
                        ...CAMPAIGN_STATUSES.map((s) => ({ value: s.value, label: s.label })),
                      ]}
                      placeholder="All statuses"
                      triggerClassName="mt-1"
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
            exportConfig={{ filename: 'campaigns_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button onClick={() => router.push('/marketing-management/campaigns/new')}>
                <Plus />
                Create Campaign
              </Button>
            }
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
