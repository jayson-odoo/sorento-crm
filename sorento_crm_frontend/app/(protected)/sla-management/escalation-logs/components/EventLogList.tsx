'use client';

import { useMemo, useState } from 'react';
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
import { Search, Columns3 } from 'lucide-react';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
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
import { apiFetch } from '@/lib/api';
import { formatDateTime } from '@/lib/helpers';
import { useEventLogs } from '../hooks/useEventLogs';
import type { ConversationSLAEventLog } from '../types/eventLog.types';

export default function EventLogList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'event_at', desc: true }]);
  const [trackingId, setTrackingId] = useState('');
  const [eventType, setEventType] = useState('__all__');
  const [assignedTo, setAssignedTo] = useState('__all__');

  const { data, isLoading } = useEventLogs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    tracking_id: trackingId || undefined,
    event_type: eventType && eventType !== '__all__' ? eventType : undefined,
    assigned_to: assignedTo && assignedTo !== '__all__' ? assignedTo : undefined,
  });

  const { data: respondUsers } = useQuery({
    queryKey: ['respond-synced-users'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/users/select?respond_synced=successful');
      if (!response.ok) {
        throw new Error('Failed to fetch respond synced users');
      }
      return response.json();
    },
    staleTime: 1000 * 60 * 5,
  });

  const columns = useMemo<ColumnDef<ConversationSLAEventLog>[]>(
    () => [
      {
        accessorKey: 'event_type',
        header: ({ column }) => <DataGridColumnHeader title="Event Type" column={column} />,
        size: 140,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'sla_tracking_id',
        header: ({ column }) => <DataGridColumnHeader title="Tracking ID" column={column} />,
        size: 220,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'from_tier',
        header: ({ column }) => <DataGridColumnHeader title="From Tier" column={column} />,
        cell: ({ row }) => row.original.from_tier ? `Tier ${row.original.from_tier}` : '-',
        size: 120,
      },
      {
        accessorKey: 'to_tier',
        header: ({ column }) => <DataGridColumnHeader title="To Tier" column={column} />,
        cell: ({ row }) => row.original.to_tier ? `Tier ${row.original.to_tier}` : '-',
        size: 120,
      },
      {
        accessorKey: 'event_at',
        header: ({ column }) => <DataGridColumnHeader title="Event At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.event_at)),
        size: 200,
      },
      {
        accessorKey: 'assigned_to',
        header: ({ column }) => <DataGridColumnHeader title="Assigned To" column={column} />,
        cell: ({ row }) => row.original.assigned_to || '-',
        size: 160,
      },
      {
        accessorKey: 'response_time',
        header: ({ column }) => <DataGridColumnHeader title="Response Time" column={column} />,
        cell: ({ row }) => row.original.response_time ?? '-',
        size: 140,
      },
      {
        accessorKey: 'resolution_time',
        header: ({ column }) => <DataGridColumnHeader title="Resolution Time" column={column} />,
        cell: ({ row }) => row.original.resolution_time ?? '-',
        size: 140,
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
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-3">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Filter by tracking ID..."
              value={trackingId}
              onChange={(e) => setTrackingId(e.target.value)}
              className="ps-9 w-64"
            />
          </div>
          <Select value={eventType} onValueChange={(value) => setEventType(value)}>
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Event type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All events</SelectItem>
              <SelectItem value="escalation">Escalation</SelectItem>
              <SelectItem value="response">Response</SelectItem>
              <SelectItem value="resolution">Resolution</SelectItem>
            </SelectContent>
          </Select>
          <Select value={assignedTo} onValueChange={(value) => setAssignedTo(value)}>
            <SelectTrigger className="w-64">
              <SelectValue placeholder="Assigned to" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All assignees</SelectItem>
              {(respondUsers || []).map((user: { id: string; name?: string | null; respond_user_id?: string | null; email: string }) => (
                <SelectItem key={user.id} value={user.respond_user_id || user.id}>
                  {user.name || user.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
                    <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
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
