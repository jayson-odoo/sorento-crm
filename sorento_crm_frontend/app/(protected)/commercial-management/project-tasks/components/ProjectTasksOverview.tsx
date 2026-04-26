'use client';

import Link from 'next/link';
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
import { ProjectTasksKanban } from './ProjectTasksKanban';

const GROUP_OPTIONS = [
  { value: 'project', label: 'Project', keyField: 'project_id', labelField: 'project_title' },
  { value: 'developer', label: 'Developer', keyField: 'developer_id', labelField: 'developer_name' },
  { value: 'customer', label: 'Customer', keyField: 'customer_id', labelField: 'customer_name' },
  { value: 'status', label: 'Status', keyField: 'status_code', labelField: 'status_label' },
  { value: 'assignee', label: 'Assignee', keyField: 'assignee_user_id', labelField: 'assignee_user_id' },
];

export type ProjectTaskRow = {
  id: string;
  project_id: string;
  title: string;
  status_code?: string | null;
  status_label?: string | null;
  status_color_hex?: string | null;
  assignee_user_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  project_title?: string | null;
  lead_code?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  developer_id?: string | null;
  developer_name?: string | null;
};

type ScopeFilter = 'all' | 'mine' | 'overdue' | 'upcoming';

export default function ProjectTasksOverview() {
  const router = useRouter();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const enabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('commercial_core');

  const { mode, setMode } = useListBoardViewPreference('commercial.project-tasks');
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

  const buildPayload = (forKanban = false): Record<string, unknown> => {
    const body: Record<string, unknown> = {
      resource: 'commercial_project_tasks',
      page: isGrouped ? 1 : pagination.pageIndex + 1,
      limit: forKanban || isGrouped ? 500 : pagination.pageSize,
      sort: 'end_date',
      dir: 'asc',
      quick_search: searchQuery || undefined,
    };
    if (scope === 'mine' && myUserId) {
      body.project_task_assignee_user_id = myUserId;
    } else if (scope === 'overdue') {
      body.project_task_overdue_only = true;
    } else if (scope === 'upcoming') {
      body.project_task_upcoming_within_days = 7;
    }
    if (advancedFilter) body.filter = advancedFilter;
    return body;
  };

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: [
      'commercial-project-tasks-list',
      pagination,
      searchQuery,
      scope,
      myUserId,
      advancedFilter,
      groupBy,
    ],
    enabled: enabled && mode === 'list',
    queryFn: async () => postListQuerySearch<ProjectTaskRow>(buildPayload(false)),
    staleTime: 30_000,
  });

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [scope, advancedFilter, groupBy]);

  const groupedRows = useMemo(() => {
    if (!isGrouped) return null;
    const opt = GROUP_OPTIONS.find((o) => o.value === groupBy);
    if (!opt) return null;
    return groupRowsBy<ProjectTaskRow>(
      data?.data || [],
      opt.keyField,
      opt.labelField,
    );
  }, [isGrouped, groupBy, data]);

  const columns = useMemo<ColumnDef<ProjectTaskRow>[]>(
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
        accessorKey: 'project_title',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        cell: ({ row }) =>
          row.original.project_id ? (
            <RecordLink href={`/commercial-management/projects/${row.original.project_id}`}>
              {row.original.project_title || '—'}
            </RecordLink>
          ) : (
            row.original.project_title || '—'
          ),
        size: 220,
      },
      {
        accessorKey: 'developer_name',
        header: ({ column }) => <DataGridColumnHeader title="Developer" column={column} />,
        cell: ({ row }) =>
          row.original.developer_id ? (
            <RecordLink href={`/order-management/customers/${row.original.developer_id}`}>
              {row.original.developer_name || '—'}
            </RecordLink>
          ) : (
            row.original.developer_name || '—'
          ),
        size: 180,
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) =>
          row.original.customer_id ? (
            <RecordLink href={`/order-management/customers/${row.original.customer_id}`}>
              {row.original.customer_name || '—'}
            </RecordLink>
          ) : (
            row.original.customer_name || '—'
          ),
        size: 180,
      },
      {
        accessorKey: 'status_label',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <StatusPill label={row.original.status_label || '—'} colorHex={row.original.status_color_hex} />
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

  if (!enabled) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <ListBoardViewToggle value={mode} onChange={setMode} />
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as ScopeFilter)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="all">All tasks</option>
          <option value="mine">Assigned to me</option>
          <option value="overdue">Overdue</option>
          <option value="upcoming">Due within 7 days</option>
        </select>
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
            placeholder="Search task / project / developer / customer..."
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
        <ProjectTaskGroupedView
          groups={groupedRows ?? []}
          isLoading={isLoading}
          onRowClick={(row) => {
            if (row?.project_id) {
              router.push(`/commercial-management/projects/${row.project_id}/edit`);
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
          listingKey="commercial_core.project_tasks.view"
          emptyMessage="No tasks found."
          onRowClick={(row) => {
            if (row?.project_id) {
              router.push(`/commercial-management/projects/${row.project_id}/edit`);
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
        <ProjectTasksKanban
          searchQuery={searchQuery}
          assigneeUserId={scope === 'mine' ? myUserId ?? null : null}
          advancedFilter={advancedFilter}
        />
      )}

      <ListQueryFilterDialog
        resourceKey="commercial_project_tasks"
        open={filterDialogOpen}
        onOpenChange={setFilterDialogOpen}
        initialFilter={advancedFilter}
        onApply={(f) => setAdvancedFilter(f)}
      />
    </div>
  );
}

function ProjectTaskGroupedView({
  groups,
  isLoading,
  onRowClick,
}: {
  groups: { key: string; label: string; rows: ProjectTaskRow[] }[];
  isLoading: boolean;
  onRowClick: (row: ProjectTaskRow) => void;
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
                    <th className="px-3 py-2 font-medium">Project</th>
                    <th className="px-3 py-2 font-medium">Developer</th>
                    <th className="px-3 py-2 font-medium">Customer</th>
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
                        {r.project_id ? (
                          <RecordLink href={`/commercial-management/projects/${r.project_id}`}>
                            {r.project_title || '—'}
                          </RecordLink>
                        ) : (
                          r.project_title || '—'
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {r.developer_id ? (
                          <RecordLink href={`/order-management/customers/${r.developer_id}`}>
                            {r.developer_name || '—'}
                          </RecordLink>
                        ) : (
                          r.developer_name || '—'
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {r.customer_id ? (
                          <RecordLink href={`/order-management/customers/${r.customer_id}`}>
                            {r.customer_name || '—'}
                          </RecordLink>
                        ) : (
                          r.customer_name || '—'
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
