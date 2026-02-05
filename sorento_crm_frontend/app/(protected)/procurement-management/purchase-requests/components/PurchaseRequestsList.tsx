'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  type Column,
  type ColumnDef,
  type Row,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { usePurchaseRequests } from '../hooks/usePurchaseRequests';
import type { PurchaseRequest } from '../types/purchaseRequest.types';
import { formatDate } from '@/lib/helpers';

const REQUEST_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

const DEFAULT_BASE_PATH = '/procurement-management/purchase-requests';

interface PurchaseRequestsListProps {
  /** When set, only this type is shown and type filter is hidden (single-type page). */
  requestType?: 'purchase_request' | 'sponsorship_form';
  /** Base path for list, new, and detail links. Defaults to purchase-requests path. */
  basePath?: string;
}

export default function PurchaseRequestsList({
  requestType,
  basePath = DEFAULT_BASE_PATH,
}: PurchaseRequestsListProps = {}) {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'request_date', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  const [requestTypeFilter, setRequestTypeFilter] = useState<string>(
    requestType ?? 'all',
  );

  const effectiveRequestType =
    requestType ?? (requestTypeFilter && requestTypeFilter !== 'all' ? requestTypeFilter : undefined);

  const { data, isLoading } = usePurchaseRequests({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    requestType: effectiveRequestType,
  });

  const handleRowClick = (row: PurchaseRequest) => {
    router.push(`${basePath}/${row.id}`);
  };

  const columns = useMemo<ColumnDef<PurchaseRequest>[]>(
    () => [
      ...(!requestType
        ? [
            {
              accessorKey: 'request_type',
              header: ({ column }: { column: Column<PurchaseRequest> }) => (
                <DataGridColumnHeader title="Type" column={column} />
              ),
              size: 140,
              cell: ({ row }: { row: Row<PurchaseRequest> }) => {
                const type_ = row.original.request_type;
                const label = REQUEST_TYPE_LABELS[type_] ?? type_;
                return (
                  <Badge variant="secondary" className="capitalize">
                    {label}
                  </Badge>
                );
              },
              meta: { skeleton: <Skeleton className="h-4 w-24" /> },
            },
          ]
        : []),
      {
        accessorKey: 'request_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Request Date" column={column} />
        ),
        cell: ({ row }) =>
          row.original.request_date
            ? formatDate(new Date(row.original.request_date))
            : '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Customer" column={column} />
        ),
        size: 160,
        cell: ({ row }) => row.original.customer_name || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'project_title',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project Title" column={column} />
        ),
        size: 200,
        cell: ({ row }) => row.original.project_title || '-',
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'purpose',
        header: ({ column }) => (
          <DataGridColumnHeader title="Purpose" column={column} />
        ),
        size: 120,
        cell: ({ row }) => row.original.purpose || '-',
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'requested_by',
        header: ({ column }) => (
          <DataGridColumnHeader title="Requested By" column={column} />
        ),
        size: 120,
        cell: ({ row }) => row.original.requested_by || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
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
    [requestType],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination?.total ?? 0) / pagination.pageSize),
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
      recordCount={data?.pagination?.total ?? 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search..."
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
            {!requestType && (
              <Select
                value={requestTypeFilter}
                onValueChange={setRequestTypeFilter}
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  <SelectItem value="purchase_request">Purchase Request</SelectItem>
                  <SelectItem value="sponsorship_form">Sponsorship Form</SelectItem>
                </SelectContent>
              </Select>
            )}
          </div>
          <Button
            onClick={() => router.push(`${basePath}/new`)}
          >
            <Plus />
            Create
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
