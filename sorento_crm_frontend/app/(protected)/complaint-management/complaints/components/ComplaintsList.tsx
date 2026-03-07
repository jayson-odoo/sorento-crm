'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, Search, X, ChevronRight, Paperclip, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
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
import { getUsersSelect } from '@/services/userSelectService';
import { useComplaints } from '../hooks/useComplaints';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import type { Complaint } from '../types/complaint.types';
import ComplaintBulkDeleteDialog from './ComplaintBulkDeleteDialog';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';

export default function ComplaintsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'complaint_date', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  const [assignedToFilter, setAssignedToFilter] = useState<string>('__all__');
  const [statusFilter, setStatusFilter] = useState<string>('__all__');
  const [selectedComplaintIds, setSelectedComplaintIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [searchQuery, assignedToFilter, statusFilter]);

  const { data, isLoading } = useComplaints({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    assigned_to:
      assignedToFilter && assignedToFilter !== '__all__'
        ? assignedToFilter
        : undefined,
    status:
      statusFilter && statusFilter !== '__all__' ? statusFilter : undefined,
  });

  const { data: respondSyncedUsers = [] } = useQuery({
    queryKey: ['users-select', 'respond_synced', 'successful'],
    queryFn: () => getUsersSelect({ respond_synced: 'successful' }),
    staleTime: 60_000,
  });
  const assigneeOptions = respondSyncedUsers.filter((u) => u.respond_user_id);

  const handleRowClick = (row: Complaint) => {
    const complaintId = row.id;
    router.push(`/complaint-management/complaints/${complaintId}`);
  };

  const toggleComplaintSelection = (complaintId: string) => {
    setSelectedComplaintIds((prev) => {
      const next = new Set(prev);
      if (next.has(complaintId)) next.delete(complaintId);
      else next.add(complaintId);
      return next;
    });
  };

  const selectAllComplaints = () => {
    const pageComplaints = data?.data ?? [];
    if (selectedComplaintIds.size === pageComplaints.length) {
      setSelectedComplaintIds(new Set());
    } else {
      setSelectedComplaintIds(new Set(pageComplaints.map((c) => c.id)));
    }
  };

  const pageComplaints = data?.data ?? [];
  const isAllSelected = pageComplaints.length > 0 && selectedComplaintIds.size === pageComplaints.length;

  const columns = useMemo<ColumnDef<Complaint>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllComplaints}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedComplaintIds.has(row.original.id)}
            onCheckedChange={() => toggleComplaintSelection(row.original.id)}
            aria-label={`Select complaint ${row.original.delivery_order_number || row.original.id}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
      {
        accessorKey: 'delivery_order_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="DO Number" column={column} />
        ),
        size: 150,
        cell: ({ row }) => row.original.delivery_order_number || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'complaint_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Complaint Date" column={column} />
        ),
        cell: ({ row }) =>
          row.original.complaint_date
            ? formatDate(new Date(row.original.complaint_date))
            : '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Created at" column={column} />
        ),
        cell: ({ row }) =>
          row.original.created_at
            ? formatDateTimeInMalaysia(row.original.created_at)
            : '-',
        size: 160,
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Customer Name" column={column} />
        ),
        cell: ({ row }) => row.original.customer_name || '-',
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'product_code',
        header: ({ column }) => (
          <DataGridColumnHeader title="Product Code" column={column} />
        ),
        cell: ({ row }) => row.original.product_code || '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'complaint_type',
        header: ({ column }) => (
          <DataGridColumnHeader title="Complaint Type" column={column} />
        ),
        cell: ({ row }) => {
          const type = row.original.complaint_type;
          return type ? (
            <Badge variant="secondary">{type}</Badge>
          ) : (
            '-'
          );
        },
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'project_title',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project Title" column={column} />
        ),
        cell: ({ row }) => row.original.project_title || '-',
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        size: 120,
        cell: ({ row }) => {
          const status = row.original.status;
          if (!status) return '-';
          return (
            <Badge variant={getStatusBadgeVariant(status)} className="capitalize">
              {status}
            </Badge>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'assigned_to',
        header: ({ column }) => (
          <DataGridColumnHeader title="Assigned To" column={column} />
        ),
        cell: ({ row }) =>
          row.original.assigned_to_name ?? row.original.assigned_to ?? '-',
        size: 160,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'attachments',
        header: ({ column }) => (
          <DataGridColumnHeader title="Attachments" column={column} />
        ),
        cell: ({ row }) => {
          const attachmentCount = row.original.attachments?.length || 0;
          return attachmentCount > 0 ? (
            <div className="flex items-center gap-1">
              <Paperclip className="size-3 text-muted-foreground" />
              <span className="text-sm">{attachmentCount}</span>
            </div>
          ) : (
            '-'
          );
        },
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
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
    [selectedComplaintIds, isAllSelected],
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
        <CardHeader className="flex-row items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search complaints..."
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
            <Select
              value={assignedToFilter}
              onValueChange={setAssignedToFilter}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Assigned to" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All assignees</SelectItem>
                <SelectItem value="__unassigned__">Unassigned</SelectItem>
                {assigneeOptions.map((u) => (
                  <SelectItem key={u.id} value={u.respond_user_id!}>
                    {u.name || u.email}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All statuses</SelectItem>
                <SelectItem value="new">New</SelectItem>
                <SelectItem value="updated">Updated</SelectItem>
                <SelectItem value="responded">Responded</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            {selectedComplaintIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBulkDeleteDialogOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="size-4" />
                Bulk Delete ({selectedComplaintIds.size})
              </Button>
            )}
            <Button
              onClick={() =>
                router.push('/complaint-management/complaints/new')
              }
            >
              <Plus />
              Create Complaint
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
      <ComplaintBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={(open) => {
          setBulkDeleteDialogOpen(open);
          if (!open) setSelectedComplaintIds(new Set());
        }}
        complaintIds={Array.from(selectedComplaintIds)}
        onSuccess={() => setSelectedComplaintIds(new Set())}
      />
    </DataGrid>
  );
}
