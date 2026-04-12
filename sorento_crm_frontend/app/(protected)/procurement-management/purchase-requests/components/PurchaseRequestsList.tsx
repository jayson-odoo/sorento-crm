'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { ChevronRight, Columns3, Filter, Plus, Search, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import PurchaseRequestBulkDeleteDialog from './PurchaseRequestBulkDeleteDialog';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import { purchaseRequestNumberFieldLabel } from '../lib/purchase-request-field-labels';

const REQUEST_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

/** API value -> display label for status filter */
const STATUS_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'pending', label: 'Pending approval' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
];

/** Display status: draft → pending_approval → approved (or rejected). Resend sets back to pending_approval. */
function getDisplayStatus(row: PurchaseRequest): string {
  const a = row.approval_status;
  if (!a || a === '') return 'Draft';
  if (a === 'pending') return 'Pending approval';
  if (a === 'approved') return 'Approved';
  if (a === 'rejected') return 'Rejected';
  return a;
}

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
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  const effectiveRequestType =
    requestType ?? (requestTypeFilter && requestTypeFilter !== 'all' ? requestTypeFilter : undefined);
  const effectiveStatusFilter =
    statusFilter && statusFilter !== 'all' ? statusFilter : undefined;

  const { data, isLoading, refetch, isFetching } = usePurchaseRequests({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    requestType: effectiveRequestType,
    approvalStatus: effectiveStatusFilter,
  });

  const statusFilterLabel =
    STATUS_FILTER_OPTIONS.find((o) => o.value === statusFilter)?.label ?? 'Status';

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [statusFilter]);

  const handleRowClick = (row: PurchaseRequest) => {
    router.push(`${basePath}/${row.id}`);
  };

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const pageData = data?.data ?? [];
  const selectAllOnPage = () => {
    if (selectedIds.size === pageData.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(pageData.map((r) => r.id)));
    }
  };
  const isAllSelected = pageData.length > 0 && selectedIds.size === pageData.length;

  const bulkDeleteEntityLabel =
    requestType === 'purchase_request'
      ? 'Purchase Request'
      : requestType === 'sponsorship_form'
        ? 'Sponsorship Form'
        : 'record';

  const requestNumberColumnTitle = purchaseRequestNumberFieldLabel(requestType);

  const columns = useMemo<ColumnDef<PurchaseRequest>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllOnPage}
            aria-label="Select all on page"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedIds.has(row.original.id)}
            onCheckedChange={() => toggleSelection(row.original.id)}
            aria-label={`Select ${row.original.request_number || row.original.id}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
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
        accessorKey: 'request_number',
        header: ({ column }) => (
          <DataGridColumnHeader title={requestNumberColumnTitle} column={column} />
        ),
        cell: ({ row }) => (
          <span className="font-medium tabular-nums">
            {row.original.request_number ?? '—'}
          </span>
        ),
        size: 140,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'request_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Date" column={column} />
        ),
        cell: ({ row }) =>
          row.original.request_date
            ? formatDate(new Date(row.original.request_date))
            : '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Created At" column={column} />
        ),
        cell: ({ row }) =>
          row.original.created_at
            ? formatDateTimeInMalaysia(row.original.created_at)
            : '-',
        size: 160,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'approval_status',
        id: 'status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        size: 140,
        cell: ({ row }) => {
          const status = getDisplayStatus(row.original);
          return (
            <Badge variant={getStatusBadgeVariant(status)} className="capitalize">
              {status}
            </Badge>
          );
        },
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
    [requestType, requestNumberColumnTitle, selectedIds, isAllSelected],
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
      tableLayout={{ columnsVisibility: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
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
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <Filter className="size-4" />
                  {statusFilter !== 'all' ? statusFilterLabel : 'Filter by status'}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-48">
                {STATUS_FILTER_OPTIONS.map((opt) => (
                  <DropdownMenuItem
                    key={opt.value}
                    onClick={() => setStatusFilter(opt.value)}
                  >
                    {opt.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <div className="flex items-center gap-2">
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
            {selectedIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBulkDeleteOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="size-4" />
                Delete ({selectedIds.size})
              </Button>
            )}
            <Button onClick={() => router.push(`${basePath}/new`)}>
              <Plus />
              Create
            </Button>
          </div>
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
      <PurchaseRequestBulkDeleteDialog
        open={bulkDeleteOpen}
        onOpenChange={(open) => {
          setBulkDeleteOpen(open);
          if (!open) setSelectedIds(new Set());
        }}
        ids={Array.from(selectedIds)}
        entityLabel={bulkDeleteEntityLabel}
        onSuccess={() => setSelectedIds(new Set())}
      />
    </DataGrid>
  );
}
