'use client';

import { useMemo } from 'react';
import {
  ColumnDef,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useConversationSLATrackingDetail } from '../hooks/useConversationSLATracking';
import { formatDateTime } from '@/lib/helpers';
import type { ConversationSLAEventLog } from '../types/conversationSLATracking.types';

interface EventLogTableProps {
  trackingId: string;
}

export default function EventLogTable({ trackingId }: EventLogTableProps) {
  const { data: tracking, isLoading } = useConversationSLATrackingDetail(trackingId);

  const columns = useMemo<ColumnDef<ConversationSLAEventLog>[]>(
    () => [
      {
        accessorKey: 'event_type',
        header: ({ column }) => <DataGridColumnHeader title="Event Type" column={column} />,
        cell: ({ row }) => {
          const eventType = row.original.event_type;
          return <span className="capitalize">{eventType}</span>;
        },
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'from_tier',
        header: ({ column }) => <DataGridColumnHeader title="From Tier" column={column} />,
        cell: ({ row }) => row.original.from_tier ? `Tier ${row.original.from_tier}` : '-',
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'to_tier',
        header: ({ column }) => <DataGridColumnHeader title="To Tier" column={column} />,
        cell: ({ row }) => row.original.to_tier ? `Tier ${row.original.to_tier}` : '-',
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'event_at',
        header: ({ column }) => <DataGridColumnHeader title="Event At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.event_at)),
        size: 200,
      },
      {
        accessorKey: 'reason',
        header: ({ column }) => <DataGridColumnHeader title="Reason" column={column} />,
        size: 300,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'assigned_user_name',
        header: ({ column }) => <DataGridColumnHeader title="Assigned To" column={column} />,
        cell: ({ row }) => {
          const userName = row.original.assigned_user_name || 
                          row.original.assigned_user?.name || 
                          row.original.assigned_user?.email || 
                          row.original.assigned_to || 
                          '-';
          return userName;
        },
        size: 150,
      },
      {
        accessorKey: 'due_at',
        header: ({ column }) => <DataGridColumnHeader title="Due At" column={column} />,
        cell: ({ row }) => row.original.due_at ? formatDateTime(new Date(row.original.due_at)) : '-',
        size: 180,
      },
      {
        accessorKey: 'response_time',
        header: ({ column }) => <DataGridColumnHeader title="Response Time" column={column} />,
        cell: ({ row }) => row.original.response_time ? `${row.original.response_time}h` : '-',
        size: 120,
      },
      {
        accessorKey: 'resolution_time',
        header: ({ column }) => <DataGridColumnHeader title="Resolution Time" column={column} />,
        cell: ({ row }) => row.original.resolution_time ? `${row.original.resolution_time}h` : '-',
        size: 120,
      },
      {
        accessorKey: 'reminder_count',
        header: ({ column }) => <DataGridColumnHeader title="Reminders" column={column} />,
        size: 100,
      },
    ],
    [],
  );

  const eventLogs = tracking?.event_logs || [];

  const table = useReactTable({
    columns,
    data: eventLogs,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Event Log</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">Loading event log...</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Event Log</CardTitle>
      </CardHeader>
      <CardContent>
        {eventLogs.length > 0 ? (
          <DataGrid table={table} recordCount={eventLogs.length} isLoading={isLoading}>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </DataGrid>
        ) : (
          <div className="text-center py-8 text-muted-foreground">No event logs found</div>
        )}
      </CardContent>
    </Card>
  );
}
