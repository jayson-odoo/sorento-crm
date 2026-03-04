'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  Row,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Trash2 } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import { useConversationSLATrackingDetail, useDeleteConversationSLAEventLog } from '../hooks/useConversationSLATracking';
import { formatDateTime, formatDateTimeInMalaysia, formatDuration, parseDateTimeAsUTC, parseNaiveDateTimeAsLocal } from '@/lib/helpers';
import type { ConversationSLAEventLog } from '../types/conversationSLATracking.types';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

interface EventLogTableProps {
  trackingId: string;
}

export default function EventLogTable({ trackingId }: EventLogTableProps) {
  const { data: tracking, isLoading } = useConversationSLATrackingDetail(trackingId);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [logToDelete, setLogToDelete] = useState<ConversationSLAEventLog | null>(null);
  const deleteMutation = useDeleteConversationSLAEventLog();

  // Get current user to check if admin
  const { data: currentUser } = useQuery({
    queryKey: ['account-profile'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/account/');
      if (!response.ok) return null;
      return response.json();
    },
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
  });

  const isAdmin = currentUser?.role === 'admin';

  const handleDeleteClick = (log: ConversationSLAEventLog) => {
    setLogToDelete(log);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!logToDelete) return;
    
    try {
      await deleteMutation.mutateAsync(logToDelete.id);
      toast.success('Event log deleted successfully');
      setDeleteDialogOpen(false);
      setLogToDelete(null);
    } catch (error: any) {
      toast.error(error.message || 'Failed to delete event log');
    }
  };

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
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.event_at),
        size: 200,
      },
      {
        accessorKey: 'from_time',
        header: ({ column }) => <DataGridColumnHeader title="From Time" column={column} />,
        cell: ({ row }) => row.original.from_time ? formatDateTimeInMalaysia(row.original.from_time) : '-',
        size: 200,
      },
      {
        accessorKey: 'duration',
        header: ({ column }) => <DataGridColumnHeader title="Duration" column={column} />,
        cell: ({ row }) => {
          const log = row.original;
          // Recalculate duration from from_time and event_at (both stored as UTC in DB)
          if (log.from_time && log.event_at) {
            const fromTime = parseDateTimeAsUTC(log.from_time);
            const eventAt = parseDateTimeAsUTC(log.event_at);
            const diff = eventAt.getTime() - fromTime.getTime();
            return formatDuration(diff);
          }
          // Fallback to stored duration if from_time is not available
          if (log.duration !== null && log.duration !== undefined) {
            // duration is in hours, convert to milliseconds for formatDuration
            return formatDuration(log.duration * 3600 * 1000);
          }
          return '-';
        },
        size: 120,
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
        cell: ({ row }) => row.original.due_at ? formatDateTime(parseNaiveDateTimeAsLocal(row.original.due_at)) : '-',
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
      ...(isAdmin ? [{
        id: 'actions',
        header: () => <div className="text-right">Actions</div>,
        cell: ({ row }: { row: Row<ConversationSLAEventLog> }) => (
          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleDeleteClick(row.original)}
              className="h-8 w-8 p-0 text-destructive hover:text-destructive"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ),
        size: 80,
      }] : []),
    ],
    [isAdmin],
  );

  // Event logs are already sorted by backend (latest first), but ensure they're sorted here too
  const eventLogs = useMemo(() => {
    const logs = tracking?.event_logs || [];
    // Sort by event_at descending (latest first) - backend should already do this, but ensure it here
    return [...logs].sort((a, b) => {
      const dateA = new Date(a.event_at).getTime();
      const dateB = new Date(b.event_at).getTime();
      return dateB - dateA; // Descending order (latest first)
    });
  }, [tracking?.event_logs]);

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
    <>
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

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Event Log</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this event log? This action cannot be undone.
              {logToDelete && (
                <div className="mt-2 text-sm">
                  <strong>Event Type:</strong> {logToDelete.event_type}
                  <br />
                  <strong>Event At:</strong> {formatDateTimeInMalaysia(logToDelete.event_at)}
                </div>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
