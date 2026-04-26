'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Filter, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
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
import { useTenantModules } from '@/hooks/useTenantModules';
import { apiFetch } from '@/lib/api';
import { formatDate } from '@/lib/helpers';
import {
  postListQuerySearch,
  type ListQueryFilterGroup,
} from '@/lib/list-query/listQueryService';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import { useListBoardViewPreference } from '@/hooks/useListBoardViewPreference';
import { StatusPill } from '@/components/common/StatusPill';
import { RecordLink } from '@/components/common/RecordLink';
import { GroupBySelect, groupRowsBy } from '@/components/common/GroupBySelect';
import { QuotationTasksKanban } from './QuotationTasksKanban';

const GROUP_OPTIONS = [
  { value: 'quotation', label: 'Quotation', keyField: 'quotation_code', labelField: 'quotation_code' },
  { value: 'tender', label: 'Tender', keyField: 'tender_code', labelField: 'tender_code' },
  { value: 'status', label: 'Status', keyField: 'status_code', labelField: 'status_label' },
  { value: 'assignee', label: 'Assignee', keyField: 'assignee_user_id', labelField: 'assignee_user_id' },
];

export type ActivityTaskRow = {
  id: string;
  master_quotation_id: string;
  title: string;
  quotation_code?: string | null;
  tender_id?: string | null;
  tender_code?: string | null;
  due_at?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status_label?: string | null;
  status_color_hex?: string | null;
  assignee_user_id?: string | null;
};

type ScopeFilter = 'all' | 'mine' | 'overdue' | 'upcoming';

export default function ActivityTasksList() {
  const router = useRouter();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const listEnabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('commercial_activity');

  const { mode, setMode } = useListBoardViewPreference('commercial.activity-tasks');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [searchQuery, setSearchQuery] = useState('');
  const [scope, setScope] = useState<ScopeFilter>('all');
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [groupBy, setGroupBy] = useState<string>('__none__');
  const isGrouped = groupBy !== '__none__';

  const { data: account } = useQuery({
    queryKey: ['account-profile'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/account/');
      if (!response.ok) return null;
      return response.json();
    },
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const myUserId = account?.id as string | undefined;

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: [
      'commercial-activity-tasks',
      pagination,
      searchQuery,
      scope,
      myUserId,
      advancedFilter,
      groupBy,
    ],
    enabled: listEnabled && mode === 'list',
    queryFn: async () => {
      const body: Record<string, unknown> = {
        resource: 'commercial_activity_tasks',
        page: isGrouped ? 1 : pagination.pageIndex + 1,
        limit: isGrouped ? 500 : pagination.pageSize,
        sort: 'due_at',
        dir: 'asc',
        quick_search: searchQuery || undefined,
      };
      if (scope === 'mine' && myUserId) {
        body.activity_task_assignee_user_id = myUserId;
      } else if (scope === 'overdue') {
        body.activity_task_overdue_only = true;
      } else if (scope === 'upcoming') {
        body.activity_task_upcoming_within_days = 7;
      }
      if (advancedFilter) body.filter = advancedFilter;
      return postListQuerySearch<ActivityTaskRow>(body);
    },
    staleTime: 30_000,
  });

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [scope, advancedFilter, groupBy]);

  const groupedRows = useMemo(() => {
    if (!isGrouped) return null;
    const opt = GROUP_OPTIONS.find((o) => o.value === groupBy);
    if (!opt) return null;
    return groupRowsBy<ActivityTaskRow>(data?.data || [], opt.keyField, opt.labelField);
  }, [isGrouped, groupBy, data]);

  const columns = useMemo<ColumnDef<ActivityTaskRow>[]>(
    () => [
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Task" column={column} />,
        cell: ({ row }) => (
          <span className="font-medium truncate" title={row.original.title}>
            {row.original.title}
          </span>
        ),
        size: 240,
      },
      {
        accessorKey: 'quotation_code',
        header: ({ column }) => <DataGridColumnHeader title="Quotation" column={column} />,
        cell: ({ row }) =>
          row.original.tender_code && row.original.quotation_code ? (
            <RecordLink
              href={`/commercial-management/tenders/${encodeURIComponent(row.original.tender_code)}`}
            >
              {row.original.quotation_code}
            </RecordLink>
          ) : (
            row.original.quotation_code || '—'
          ),
        size: 160,
      },
      {
        accessorKey: 'tender_code',
        header: ({ column }) => <DataGridColumnHeader title="Tender" column={column} />,
        cell: ({ row }) =>
          row.original.tender_code ? (
            <RecordLink
              href={`/commercial-management/tenders/${encodeURIComponent(row.original.tender_code)}`}
            >
              {row.original.tender_code}
            </RecordLink>
          ) : (
            '—'
          ),
        size: 160,
      },
      {
        accessorKey: 'status_label',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <StatusPill
            label={row.original.status_label || '—'}
            colorHex={row.original.status_color_hex}
          />
        ),
        size: 140,
      },
      {
        accessorKey: 'start_date',
        header: ({ column }) => <DataGridColumnHeader title="Start date" column={column} />,
        cell: ({ row }) => (row.original.start_date ? formatDate(row.original.start_date) : '—'),
        size: 130,
      },
      {
        accessorKey: 'end_date',
        header: ({ column }) => <DataGridColumnHeader title="End date" column={column} />,
        cell: ({ row }) => (row.original.end_date ? formatDate(row.original.end_date) : '—'),
        size: 130,
      },
    ],
    [],
  );

  const table = useReactTable({
    data: data?.data || [],
    columns,
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
  });

  if (!listEnabled) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <ListBoardViewToggle value={mode} onChange={setMode} />
        <Select value={scope} onValueChange={(v) => setScope(v as ScopeFilter)}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Scope" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All tasks</SelectItem>
            <SelectItem value="mine">Assigned to me</SelectItem>
            <SelectItem value="overdue">Overdue</SelectItem>
            <SelectItem value="upcoming">Due within 7 days</SelectItem>
          </SelectContent>
        </Select>
        {mode === 'list' ? (
          <GroupBySelect
            value={groupBy}
            onChange={setGroupBy}
            options={GROUP_OPTIONS.map(({ value, label }) => ({ value, label }))}
          />
        ) : null}
        <div className="relative">
          <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search task / quotation / tender / customer..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setPagination((p) => ({ ...p, pageIndex: 0 }));
                void refetch();
              }
            }}
            className="ps-9 w-80"
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => {
            setPagination((p) => ({ ...p, pageIndex: 0 }));
            void refetch();
          }}
        >
          Search
        </Button>
        <Button
          type="button"
          variant={advancedFilter ? 'primary' : 'outline'}
          size="sm"
          onClick={() => setFilterDialogOpen(true)}
        >
          <Filter className="mr-1 size-4" />
          Advanced filter{advancedFilter ? ' (active)' : ''}
        </Button>
        {advancedFilter ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => setAdvancedFilter(null)}>
            Clear
          </Button>
        ) : null}
      </div>

      {mode === 'list' && isGrouped ? (
        <ActivityTaskGroupedView
          groups={groupedRows ?? []}
          isLoading={isLoading}
          onRowClick={(row) => {
            if (row?.tender_code) {
              router.push(
                `/commercial-management/tenders/${encodeURIComponent(row.tender_code)}`,
              );
            }
          }}
        />
      ) : mode === 'list' ? (
        <DataGrid
          table={table}
          tableLayout={{ columnsVisibility: true, width: 'fixed', columnsResizable: true }}
          recordCount={data?.pagination.total || 0}
          isLoading={isLoading}
          onRefresh={() => void refetch()}
          isRefreshing={isFetching && !isLoading}
          listingKey="commercial_core.activity_tasks.view"
          emptyMessage="No tasks found."
          onRowClick={(row) => {
            if (row?.tender_code) {
              router.push(
                `/commercial-management/tenders/${encodeURIComponent(row.tender_code)}`,
              );
            }
          }}
        >
          <Card>
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
      ) : (
        <QuotationTasksKanban
          searchQuery={searchQuery}
          assigneeUserId={scope === 'mine' ? myUserId ?? null : null}
          advancedFilter={advancedFilter}
        />
      )}

      <ListQueryFilterDialog
        resourceKey="commercial_activity_tasks"
        open={filterDialogOpen}
        onOpenChange={setFilterDialogOpen}
        initialFilter={advancedFilter}
        onApply={(f) => setAdvancedFilter(f)}
      />
    </div>
  );
}

function ActivityTaskGroupedView({
  groups,
  isLoading,
  onRowClick,
}: {
  groups: { key: string; label: string; rows: ActivityTaskRow[] }[];
  isLoading: boolean;
  onRowClick: (row: ActivityTaskRow) => void;
}) {
  if (isLoading && groups.length === 0) return <Skeleton className="h-40 w-full" />;
  if (groups.length === 0) {
    return (
      <Card>
        <CardHeader>
          <span className="text-sm text-muted-foreground">No tasks found.</span>
        </CardHeader>
      </Card>
    );
  }
  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <Card key={g.key}>
          <CardHeader className="flex items-center justify-between py-3">
            <span className="font-semibold">{g.label}</span>
            <span className="text-xs text-muted-foreground">{g.rows.length} tasks</span>
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Task</th>
                    <th className="px-3 py-2 font-medium">Quotation</th>
                    <th className="px-3 py-2 font-medium">Tender</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Start date</th>
                    <th className="px-3 py-2 font-medium">End date</th>
                  </tr>
                </thead>
                <tbody>
                  {g.rows.map((r) => (
                    <tr
                      key={r.id}
                      className="cursor-pointer border-t hover:bg-muted/40"
                      onClick={() => onRowClick(r)}
                    >
                      <td className="px-3 py-2 font-medium">{r.title}</td>
                      <td className="px-3 py-2">
                        {r.tender_code && r.quotation_code ? (
                          <RecordLink
                            href={`/commercial-management/tenders/${encodeURIComponent(r.tender_code)}`}
                          >
                            {r.quotation_code}
                          </RecordLink>
                        ) : (
                          r.quotation_code || '—'
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {r.tender_code ? (
                          <RecordLink
                            href={`/commercial-management/tenders/${encodeURIComponent(r.tender_code)}`}
                          >
                            {r.tender_code}
                          </RecordLink>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <StatusPill label={r.status_label || '—'} colorHex={r.status_color_hex} />
                      </td>
                      <td className="px-3 py-2">
                        {r.start_date ? formatDate(r.start_date) : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {r.end_date ? formatDate(r.end_date) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      ))}
    </div>
  );
}
