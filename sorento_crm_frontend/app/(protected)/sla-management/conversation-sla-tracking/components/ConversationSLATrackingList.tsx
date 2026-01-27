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
import { formatDate, formatDateTime, formatDuration } from '@/lib/helpers';
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

  const getTimeRemaining = (dueAt: Date) => {
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
        header: ({ column }) => <DataGridColumnHeader title="Due At" column={column} />,
        cell: ({ row }) => {
          const timeRemaining = getTimeRemaining(row.original.due_at);
          const isOverdue = timeRemaining.startsWith('-');
          return (
            <div className="space-y-1">
              <div className={isOverdue ? 'text-destructive font-medium' : ''}>
                {formatDateTime(new Date(row.original.due_at))}
              </div>
              {isOverdue && (
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
        accessorKey: 'time_remaining',
        header: ({ column }) => <DataGridColumnHeader title="Time Remaining" column={column} />,
        cell: ({ row }) => {
          if (row.original.is_resolved) {
            return (
              <div className="flex items-center gap-2">
                <CheckCircle className="size-4 text-green-600" />
                <span className="text-sm text-green-600">Resolved</span>
              </div>
            );
          }
          const timeRemaining = getTimeRemaining(row.original.due_at);
          const percent = getTimeRemainingPercent(row.original.due_at, row.original.current_tier_started_at);
          const isOverdue = timeRemaining.startsWith('-');
          return (
            <div className="space-y-1 w-40">
              <div className="flex items-center gap-2">
                <Clock className={`size-4 ${isOverdue ? 'text-destructive' : 'text-muted-foreground'}`} />
                <span className={`text-sm ${isOverdue ? 'text-destructive font-medium' : ''}`}>
                  {isOverdue ? `${timeRemaining.substring(1)} overdue` : `${timeRemaining} left`}
                </span>
              </div>
              <Progress value={percent} className="h-2" />
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
