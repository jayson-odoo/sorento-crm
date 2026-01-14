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
import type { ConversationSLAEscalationLog } from '../types/conversationSLATracking.types';

interface EscalationLogTableProps {
  trackingId: string;
}

export default function EscalationLogTable({ trackingId }: EscalationLogTableProps) {
  const { data: tracking, isLoading } = useConversationSLATrackingDetail(trackingId);

  const columns = useMemo<ColumnDef<ConversationSLAEscalationLog>[]>(
    () => [
      {
        accessorKey: 'from_tier',
        header: ({ column }) => <DataGridColumnHeader title="From Tier" column={column} />,
        cell: ({ row }) => `Tier ${row.original.from_tier}`,
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'to_tier',
        header: ({ column }) => <DataGridColumnHeader title="To Tier" column={column} />,
        cell: ({ row }) => {
          const isEscalation = row.original.from_tier !== row.original.to_tier;
          return (
            <div className="flex items-center gap-2">
              <span>Tier {row.original.to_tier}</span>
              {!isEscalation && (
                <span className="text-xs text-muted-foreground">(Assignment)</span>
              )}
            </div>
          );
        },
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'escalated_at',
        header: ({ column }) => <DataGridColumnHeader title="Escalated / Assigned At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.escalated_at)),
        size: 200,
      },
      {
        accessorKey: 'reason',
        header: ({ column }) => <DataGridColumnHeader title="Reason" column={column} />,
        size: 300,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'assigned_to',
        header: ({ column }) => <DataGridColumnHeader title="Assigned To" column={column} />,
        cell: ({ row }) => row.original.assigned_to || '-',
        size: 150,
      },
      {
        accessorKey: 'due_at',
        header: ({ column }) => <DataGridColumnHeader title="Due At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.due_at)),
        size: 180,
      },
      {
        accessorKey: 'reminder_count',
        header: ({ column }) => <DataGridColumnHeader title="Reminders" column={column} />,
        size: 100,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: tracking?.escalation_logs || [],
    getCoreRowModel: getCoreRowModel(),
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Escalation Log</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">Loading escalation log...</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Escalation Log</CardTitle>
      </CardHeader>
      <CardContent>
        {tracking?.escalation_logs && tracking.escalation_logs.length > 0 ? (
          <DataGrid table={table} recordCount={tracking.escalation_logs.length} isLoading={isLoading}>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </DataGrid>
        ) : (
          <div className="text-center py-8 text-muted-foreground">No escalation logs found</div>
        )}
      </CardContent>
    </Card>
  );
}
