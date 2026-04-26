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
import { formatDate } from '@/lib/helpers';
import {
  postListQuerySearch,
  type ListQueryFilterGroup,
} from '@/lib/list-query/listQueryService';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { StatusPill } from '@/components/common/StatusPill';
import { RecordLink } from '@/components/common/RecordLink';

export type ActivityRow = {
  id: string;
  entity_type: string;
  entity_id: string;
  scope: string;
  is_system: boolean;
  body_html: string;
  author_user_id?: string | null;
  author_name?: string | null;
  created_at: string;
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  commercial_project: 'Project',
  commercial_master_quotation: 'Quotation',
  commercial_lead: 'Lead',
  commercial_project_task: 'Project task',
  commercial_master_quotation_task: 'Quotation task',
};

const ENTITY_TYPE_COLORS: Record<string, string> = {
  commercial_project: '#2563eb',
  commercial_master_quotation: '#7c3aed',
  commercial_lead: '#0d9488',
  commercial_project_task: '#0891b2',
  commercial_master_quotation_task: '#9333ea',
};

function entityHref(entityType: string, entityId: string): string | null {
  switch (entityType) {
    case 'commercial_project':
      return `/commercial-management/projects/${entityId}`;
    default:
      return null;
  }
}

function stripHtml(html: string): string {
  if (!html) return '';
  const tmp = html.replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
  return tmp;
}

export default function ActivitiesList() {
  const router = useRouter();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const enabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('commercial_core');

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [searchQuery, setSearchQuery] = useState('');
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>('all');
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: [
      'commercial-activities-list',
      pagination,
      searchQuery,
      entityTypeFilter,
      advancedFilter,
    ],
    enabled,
    queryFn: async () => {
      const body: Record<string, unknown> = {
        resource: 'commercial_activities',
        page: pagination.pageIndex + 1,
        limit: pagination.pageSize,
        sort: 'created_at',
        dir: 'desc',
        quick_search: searchQuery || undefined,
      };
      if (entityTypeFilter !== 'all') body.activity_entity_type = entityTypeFilter;
      if (advancedFilter) body.filter = advancedFilter;
      return postListQuerySearch<ActivityRow>(body);
    },
    staleTime: 30_000,
  });

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [entityTypeFilter, advancedFilter]);

  const columns = useMemo<ColumnDef<ActivityRow>[]>(
    () => [
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="When" column={column} />,
        cell: ({ row }) => formatDate(row.original.created_at),
        size: 160,
      },
      {
        accessorKey: 'entity_type',
        header: ({ column }) => <DataGridColumnHeader title="Document" column={column} />,
        cell: ({ row }) => {
          const label = ENTITY_TYPE_LABELS[row.original.entity_type] ?? row.original.entity_type;
          const href = entityHref(row.original.entity_type, row.original.entity_id);
          const pill = (
            <StatusPill
              label={label}
              colorHex={ENTITY_TYPE_COLORS[row.original.entity_type] ?? null}
            />
          );
          return href ? <RecordLink href={href}>{pill}</RecordLink> : pill;
        },
        size: 160,
      },
      {
        accessorKey: 'author_name',
        header: ({ column }) => <DataGridColumnHeader title="Author" column={column} />,
        cell: ({ row }) =>
          row.original.is_system ? <span className="italic text-muted-foreground">system</span> : row.original.author_name || '—',
        size: 160,
      },
      {
        accessorKey: 'body_html',
        header: ({ column }) => <DataGridColumnHeader title="Message" column={column} />,
        cell: ({ row }) => (
          <span className="line-clamp-2" title={stripHtml(row.original.body_html)}>
            {stripHtml(row.original.body_html)}
          </span>
        ),
        size: 480,
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
        <Select value={entityTypeFilter} onValueChange={setEntityTypeFilter}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Document type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All documents</SelectItem>
            <SelectItem value="commercial_project">Projects</SelectItem>
            <SelectItem value="commercial_master_quotation">Quotations</SelectItem>
            <SelectItem value="commercial_lead">Leads</SelectItem>
            <SelectItem value="commercial_project_task">Project tasks</SelectItem>
            <SelectItem value="commercial_master_quotation_task">Quotation tasks</SelectItem>
          </SelectContent>
        </Select>
        <div className="relative">
          <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search messages..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setPagination((p) => ({ ...p, pageIndex: 0 }));
                void refetch();
              }
            }}
            className="ps-9 w-72"
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

      <DataGrid
        table={table}
        tableLayout={{ columnsVisibility: true, width: 'fixed', columnsResizable: true }}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        onRefresh={() => void refetch()}
        isRefreshing={isFetching && !isLoading}
        listingKey="commercial_core.activities.view"
        emptyMessage="No activities found."
        onRowClick={(row) => {
          const href = entityHref(row.entity_type, row.entity_id);
          if (href) router.push(href);
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

      <ListQueryFilterDialog
        resourceKey="commercial_activities"
        open={filterDialogOpen}
        onOpenChange={setFilterDialogOpen}
        initialFilter={advancedFilter}
        onApply={(f) => setAdvancedFilter(f)}
      />
    </div>
  );
}
