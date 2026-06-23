'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Filter, RefreshCw, Search, UserRoundCog, UserRoundPlus, UserRoundCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { toast } from 'sonner';
import { formatDateTime, parseDateTimeAsUTC } from '@/lib/helpers';
import {
  useTeamPendingSLA,
  useVisibleUsers,
  useTakeoverSLATracking,
  useReassignSLATracking,
} from '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA';
import { useSubscribeCoverage } from '@/app/(protected)/account/notifications/hooks/useCoverage';
import ReassignDialog from '@/app/(protected)/sla-management/conversation-sla-tracking/components/ReassignDialog';
import type { TeamPendingItem } from '@/app/(protected)/sla-management/conversation-sla-tracking/services/conversationSLATrackingService';

const ALL = '__all__';

export default function TeamPendingList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [assigneeFilter, setAssigneeFilter] = useState(ALL);
  const [teamFilter, setTeamFilter] = useState(ALL);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [reassignTarget, setReassignTarget] = useState<{ id: string; label: string } | null>(null);

  // Debounce the search box so we don't refetch on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [assigneeFilter, teamFilter, search]);

  const { data, isLoading, isFetching, refetch } = useTeamPendingSLA({
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    assignee: assigneeFilter !== ALL ? assigneeFilter : undefined,
    team: teamFilter !== ALL ? teamFilter : undefined,
    query: search || undefined,
  });

  const { data: visibleUsers = [] } = useVisibleUsers();
  const takeoverMutation = useTakeoverSLATracking();
  const reassignMutation = useReassignSLATracking();
  const subscribeMutation = useSubscribeCoverage();

  const rows = useMemo(() => data?.data ?? [], [data]);

  // Team filter options: distinct {team_id, team_label} from the loaded rows.
  const teamOptions = useMemo(() => {
    const map = new Map<string, string>();
    rows.forEach((r) => map.set(r.team_id, r.team_label));
    return Array.from(map.entries()).map(([id, label]) => ({ id, label }));
  }, [rows]);

  const mutatingId =
    (takeoverMutation.isPending && takeoverMutation.variables?.id) ||
    (reassignMutation.isPending && reassignMutation.variables?.id) ||
    null;

  const taskLabel = (r: TeamPendingItem) =>
    `${r.reference ?? (r.source_entity_type ?? 'Task')}`;

  const handleSubscribe = (r: TeamPendingItem) => {
    subscribeMutation.mutate(
      { targetUserId: r.assignee_id },
      {
        onSuccess: () => toast.success(`Now covering for ${r.assignee_name}.`),
      },
    );
  };

  const columns = useMemo<ColumnDef<TeamPendingItem>[]>(
    () => [
      {
        accessorKey: 'reference',
        header: ({ column }) => <DataGridColumnHeader title="Reference" column={column} />,
        cell: ({ row }) => {
          const r = row.original;
          const ref = r.reference || '—';
          return <span className="truncate block" title={ref}>{ref}</span>;
        },
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'assignee_name',
        header: ({ column }) => <DataGridColumnHeader title="Assignee" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.assignee_name}>
            {row.original.assignee_name}
          </span>
        ),
        size: 180,
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'team_label',
        header: ({ column }) => <DataGridColumnHeader title="Team" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.team_label}>
            {row.original.team_label}
          </span>
        ),
        size: 180,
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'policy_name',
        header: ({ column }) => <DataGridColumnHeader title="Policy" column={column} />,
        cell: ({ row }) => {
          const p = row.original.policy_name || '—';
          return <span className="truncate block" title={p}>{p}</span>;
        },
        size: 160,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'due_at',
        header: ({ column }) => <DataGridColumnHeader title="Due at" column={column} />,
        cell: ({ row }) => {
          const due = row.original.due_at;
          if (!due) return '—';
          const overdue = parseDateTimeAsUTC(due).getTime() < Date.now();
          const text = formatDateTime(parseDateTimeAsUTC(due));
          return (
            <span className={overdue ? 'text-destructive font-medium' : ''} title={text}>
              {text}
            </span>
          );
        },
        size: 180,
      },
      {
        accessorKey: 'current_tier',
        header: ({ column }) => <DataGridColumnHeader title="Tier" column={column} />,
        cell: ({ row }) => <Badge variant="secondary">Tier {row.original.current_tier}</Badge>,
        size: 100,
      },
      {
        accessorKey: 'next_action',
        header: ({ column }) => <DataGridColumnHeader title="Next action" column={column} />,
        cell: ({ row }) => {
          const r = row.original;
          const action = r.is_form_sla ? r.next_action ?? 'Action required' : 'Reply';
          return <span className="truncate block" title={action}>{action}</span>;
        },
        size: 170,
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const r = row.original;
          const rowBusy = mutatingId === r.id;
          return (
            <div className="flex items-center gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    disabled={rowBusy}
                    onClick={() => takeoverMutation.mutate({ id: r.id, teamId: r.team_id })}
                    aria-label="Takeover"
                  >
                    <UserRoundPlus className="size-4 text-muted-foreground" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Takeover — assign this task to me</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    disabled={rowBusy}
                    onClick={() => setReassignTarget({ id: r.id, label: taskLabel(r) })}
                    aria-label="Reassign"
                  >
                    <UserRoundCog className="size-4 text-muted-foreground" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Reassign to a colleague</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    disabled={subscribeMutation.isPending}
                    onClick={() => handleSubscribe(r)}
                    aria-label={`Cover for ${r.assignee_name}`}
                  >
                    <UserRoundCheck className="size-4 text-muted-foreground" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Cover for {r.assignee_name}</TooltipContent>
              </Tooltip>
            </div>
          );
        },
        size: 130,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mutatingId, takeoverMutation, subscribeMutation.isPending],
  );

  const total = data?.total ?? 0;
  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    columnResizeMode: 'onChange',
  });

  const hasActiveFilters = assigneeFilter !== ALL || teamFilter !== ALL;

  return (
    <>
      <DataGrid
        table={table}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        recordCount={total}
        isLoading={isLoading}
        emptyMessage="No open tasks across your teams."
      >
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center gap-2 py-5">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" disabled={isLoading} title="Filters" className="relative">
                  <Filter className="size-4" />
                  {hasActiveFilters && (
                    <span className="absolute -top-1 -end-1 size-2.5 rounded-full bg-primary" />
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-72 space-y-3" align="start">
                <h4 className="text-sm font-medium">Filters</h4>
                <div className="space-y-1.5">
                  <label className="text-xs text-muted-foreground">Assignee</label>
                  <Select value={assigneeFilter} onValueChange={setAssigneeFilter} disabled={isLoading}>
                    <SelectTrigger>
                      <SelectValue placeholder="All assignees" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>All assignees</SelectItem>
                      {visibleUsers.map((u) => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name || u.email}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-muted-foreground">Team</label>
                  <Select value={teamFilter} onValueChange={setTeamFilter} disabled={isLoading}>
                    <SelectTrigger>
                      <SelectValue placeholder="All teams" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>All teams</SelectItem>
                      {teamOptions.map((t) => (
                        <SelectItem key={t.id} value={t.id}>
                          {t.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {hasActiveFilters && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setAssigneeFilter(ALL);
                      setTeamFilter(ALL);
                    }}
                  >
                    Clear filters
                  </Button>
                )}
              </PopoverContent>
            </Popover>
            <div className="relative w-full max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search number, contact, assignee…"
                className="pl-9"
              />
            </div>
            <div className="ml-auto">
              <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
                <RefreshCw className={`size-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
                Refresh
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
      </DataGrid>

      <ReassignDialog
        open={!!reassignTarget}
        onOpenChange={(o) => !o && setReassignTarget(null)}
        taskLabel={reassignTarget?.label}
        submitting={reassignMutation.isPending}
        onConfirm={(userId) => {
          if (!reassignTarget) return;
          reassignMutation.mutate(
            { id: reassignTarget.id, userId },
            { onSuccess: () => setReassignTarget(null) },
          );
        }}
      />
    </>
  );
}
