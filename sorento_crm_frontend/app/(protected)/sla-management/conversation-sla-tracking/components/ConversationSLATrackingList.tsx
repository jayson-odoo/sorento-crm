'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X, ChevronRight, Clock, AlertCircle, CheckCircle, RefreshCw } from 'lucide-react';
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
import { Progress } from '@/components/ui/progress';
import { useConversationSLATracking } from '../hooks/useConversationSLATracking';
import type { ConversationSLATracking } from '../types/conversationSLATracking.types';
import { formatDate, formatDateTime, formatDuration, formatDurationWithSeconds } from '@/lib/helpers';
import { apiFetch } from '@/lib/api';

export default function ConversationSLATrackingList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [assignedToFilter, setAssignedToFilter] = useState('__all__');

  const { data, isLoading } = useConversationSLATracking({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    assigned_to: assignedToFilter && assignedToFilter !== '__all__' ? assignedToFilter : undefined,
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

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking'] });
    await queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking-detail'] });
    setIsRefreshing(false);
  };

  const handleRowClick = (row: ConversationSLATracking) => {
    const trackingId = row.id;
    router.push(`/sla-management/conversation-sla-tracking/${trackingId}`);
  };

  const getTimeRemaining = (dueAt: Date, backendSeconds?: number | null) => {
    if (backendSeconds !== undefined && backendSeconds !== null) {
      return formatDuration(backendSeconds * 1000);
    }
    const now = new Date();
    const due = new Date(dueAt);
    const diff = due.getTime() - now.getTime();
    return formatDuration(diff);
  };

  const getTimeRemainingPercent = (dueAt: Date, currentTierStartedAt: Date) => {
    const now = new Date();
    const due = new Date(dueAt);
    const started = new Date(currentTierStartedAt);
    const total = due.getTime() - started.getTime();
    const remaining = due.getTime() - now.getTime();
    if (total <= 0) return 0;
    return Math.max(0, Math.min(100, (remaining / total) * 100));
  };

  /** Response overdue: not responded and now > due_at, OR responded after due_at */
  const isResponseOverdue = (o: ConversationSLATracking) => {
    const due = new Date(o.due_at).getTime();
    const now = Date.now();
    if (o.is_responded && o.responded_at) {
      return new Date(o.responded_at).getTime() > due;
    }
    return now > due;
  };

  /** Resolution overdue: not resolved and now > due_at_resolution, OR resolved after due_at_resolution */
  const isResolutionOverdue = (o: ConversationSLATracking) => {
    const dueRes = o.due_at_resolution ?? o.resolution_due_at;
    if (!dueRes) return false;
    const due = new Date(dueRes).getTime();
    const now = Date.now();
    if (o.is_resolved && o.resolved_at) {
      return new Date(o.resolved_at).getTime() > due;
    }
    return now > due;
  };

  const formatSecondsToDuration = (seconds: number | null | undefined) => {
    if (seconds == null) return '—';
    return formatDuration(seconds * 1000);
  };
  const formatSecondsToDurationWithSeconds = (seconds: number | null | undefined) => {
    if (seconds == null) return '—';
    return formatDurationWithSeconds(seconds * 1000);
  };

  const columns = useMemo<ColumnDef<ConversationSLATracking>[]>(
    () => [
      {
        accessorKey: 'contact_phone',
        header: ({ column }) => <DataGridColumnHeader title="Contact Phone" column={column} />,
        cell: ({ row }) => {
          const phone = row.original.contact_phone || 
                       row.original.contact?.phone_number || 
                       '-';
          return phone;
        },
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'contact_name',
        header: ({ column }) => <DataGridColumnHeader title="Contact Name" column={column} />,
        cell: ({ row }) => {
          const name = row.original.contact_name || 
                      row.original.contact?.name || 
                      '-';
          return name;
        },
        size: 220,
        meta: { skeleton: <Skeleton className="h-4 w-36" /> },
      },
      {
        accessorKey: 'policy_name',
        header: ({ column }) => <DataGridColumnHeader title="Policy" column={column} />,
        cell: ({ row }) => {
          const policyName = row.original.policy?.name || 
                            row.original.policy_name || 
                            row.original.policy?.code || 
                            row.original.policy_code || 
                            '-';
          return policyName;
        },
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'current_tier',
        header: ({ column }) => <DataGridColumnHeader title="Current Tier" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary">Tier {row.original.current_tier}</Badge>
        ),
        size: 120,
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
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'initiated_at',
        header: ({ column }) => <DataGridColumnHeader title="Initiated At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.initiated_at)),
        size: 180,
      },
      {
        accessorKey: 'due_at',
        header: ({ column }) => <DataGridColumnHeader title="Due at (response)" column={column} />,
        cell: ({ row }) => {
          const o = row.original;
          const overdue = isResponseOverdue(o);
          return (
            <div className="space-y-1">
              <div className={overdue ? 'text-destructive font-medium' : ''}>
                {formatDateTime(new Date(o.due_at))}
              </div>
              {overdue && (
                <div className="text-xs text-destructive flex items-center gap-1">
                  <AlertCircle className="size-3" />
                  Overdue
                </div>
              )}
            </div>
          );
        },
        size: 180,
      },
      {
        accessorKey: 'due_at_resolution',
        header: ({ column }) => <DataGridColumnHeader title="Due at (resolution)" column={column} />,
        cell: ({ row }) => {
          const o = row.original;
          const dueRes = o.due_at_resolution ?? o.resolution_due_at;
          if (!dueRes) return '—';
          const overdue = isResolutionOverdue(o);
          return (
            <div className="space-y-1">
              <div className={overdue ? 'text-destructive font-medium' : ''}>
                {formatDateTime(new Date(dueRes))}
              </div>
              {overdue && (
                <div className="text-xs text-destructive flex items-center gap-1">
                  <AlertCircle className="size-3" />
                  Overdue
                </div>
              )}
            </div>
          );
        },
        size: 180,
      },
      {
        accessorKey: 'time_elapsed',
        header: ({ column }) => <DataGridColumnHeader title="Time elapsed" column={column} />,
        cell: ({ row }) => {
          const o = row.original;
          // When resolved: resolution time; when only responded: response time; else: live elapsed
          const sec = o.is_resolved && o.resolution_duration != null
            ? o.resolution_duration * 3600
            : o.is_responded && o.response_time != null
              ? o.response_time * 3600
              : (o.time_in_tier_resolution_seconds ?? undefined);
          return (
            <span className="text-sm">
              {formatSecondsToDurationWithSeconds(sec)}
            </span>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'time_remaining_response',
        header: ({ column }) => <DataGridColumnHeader title="Response" column={column} />,
        cell: ({ row }) => {
          const o = row.original;
          if (o.is_responded) {
            const overdue = isResponseOverdue(o);
            const hours = o.response_time ?? 0;
            const str = hours < 1 ? formatSecondsToDurationWithSeconds((o.response_time ?? 0) * 3600) : `${hours.toFixed(1)}h`;
            return (
              <div className="space-y-0.5">
                <div className="text-xs text-muted-foreground">Response time</div>
                <span className={`text-sm font-medium ${overdue ? 'text-destructive' : 'text-green-600'}`}>
                  {str}
                </span>
              </div>
            );
          }
          const timeRemaining = getTimeRemaining(o.due_at, o.time_remaining_response_seconds);
          const percent = getTimeRemainingPercent(o.due_at, o.current_tier_started_at);
          const overdue = timeRemaining.startsWith('-');
          return (
            <div className="space-y-1 w-40">
              <div className="text-xs text-muted-foreground">Time remaining</div>
              <div className="flex items-center gap-2">
                <Clock className={`size-4 ${overdue ? 'text-destructive' : 'text-muted-foreground'}`} />
                <span className={`text-sm ${overdue ? 'text-destructive font-medium' : ''}`}>
                  {overdue ? `${timeRemaining.substring(1)} overdue` : `${timeRemaining} left`}
                </span>
              </div>
              <Progress value={percent} className="h-2" />
            </div>
          );
        },
        size: 200,
      },
      {
        accessorKey: 'time_remaining_resolution',
        header: ({ column }) => <DataGridColumnHeader title="Resolution" column={column} />,
        cell: ({ row }) => {
          const o = row.original;
          if (o.is_resolved) {
            const overdue = isResolutionOverdue(o);
            const hours = o.resolution_duration ?? 0;
            const str = hours < 1 ? formatSecondsToDurationWithSeconds((o.resolution_duration ?? 0) * 3600) : `${hours.toFixed(1)}h`;
            return (
              <div className="space-y-0.5">
                <div className="text-xs text-muted-foreground">Resolution duration</div>
                <span className={`text-sm font-medium ${overdue ? 'text-destructive' : 'text-green-600'}`}>
                  {str}
                </span>
              </div>
            );
          }
          const sec = o.time_remaining_resolution_seconds;
          const str = formatSecondsToDuration(sec ?? undefined);
          const overdue = isResolutionOverdue(o);
          return (
            <div className="space-y-0.5">
              <div className="text-xs text-muted-foreground">Time remaining</div>
              <span className={`text-sm ${overdue ? 'text-destructive font-medium' : ''}`}>
                {overdue ? 'Overdue' : `${str} left`}
              </span>
            </div>
          );
        },
        size: 200,
      },
      {
        accessorKey: 'is_resolved',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          if (row.original.is_resolved) {
            return (
              <Badge variant="success" appearance="ghost">
                <CheckCircle className="size-3 mr-1" />
                Resolved
              </Badge>
            );
          }
          if (row.original.escalated_at) {
            return (
              <Badge variant="warning" appearance="ghost">
                <AlertCircle className="size-3 mr-1" />
                Escalated
              </Badge>
            );
          }
          return (
            <Badge variant="info" appearance="ghost">
              <Clock className="size-3 mr-1" />
              Pending
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
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading} onRowClick={handleRowClick}>
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-3">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search conversation SLA tracking..."
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
            onValueChange={(value) => setAssignedToFilter(value)}
          >
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
          <Button
            variant="outline"
            onClick={handleRefresh}
            disabled={isRefreshing || isLoading}
          >
            <RefreshCw className={`size-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
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
