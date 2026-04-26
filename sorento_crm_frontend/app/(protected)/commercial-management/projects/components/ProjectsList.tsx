'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
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
import { Columns3, Copy, Download, Info, MoreVertical, Search, SlidersHorizontal, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
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
import { duplicateCommercialProject } from '../services/commercialProjectService';
import { useCommercialProjects } from '../hooks/useCommercialProjects';
import type { CommercialProjectListRow } from '../types/commercialProject.types';
import { apiFetch } from '@/lib/api';
import { cn } from '@/lib/utils';
import { TruncatedTextCell } from '@/components/common/TruncatedTextCell';
import CreateProjectDialog from './CreateProjectDialog';
import { ProjectsKanbanClient } from './ProjectsKanbanClient';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';
import { useListBoardViewPreference } from '@/hooks/useListBoardViewPreference';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import { useHasPermission } from '@/hooks/usePermissions';

type UserSelectRow = { id: string; name: string | null; email: string };

const HEADER_MUTED = 'text-[#6a7282] text-xs font-medium uppercase tracking-wide';
const LINK_ACCENT = 'text-[#e7000b] font-medium hover:underline';

function formatListDate(iso: string | undefined): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(iso));
  } catch {
    return '—';
  }
}

function projectStageBadgeClass(stageCode: string | null | undefined): string {
  const c = (stageCode || '').toLowerCase();
  if (c.includes('complet')) return 'bg-emerald-100 text-emerald-800';
  if (c.includes('cancel')) return 'bg-[#ffe2e2] text-[#9f0712]';
  if (c.includes('inactive')) return 'bg-[#ffe2e2] text-[#9f0712]';
  if (c.includes('hold')) return 'bg-amber-100 text-amber-900';
  if (c.includes('plan')) return 'bg-[#dbeafe] text-[#1447e6]';
  if (c.includes('active')) return 'bg-[#dcfce7] text-[#016630]';
  return 'bg-zinc-100 text-zinc-700';
}

const CONTROL_SURFACE = 'h-9 border-0 bg-[#f3f3f5] shadow-none rounded-lg';

export default function ProjectsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('__all__');
  const [createOpen, setCreateOpen] = useState(false);
  const { mode, setMode, hydrated } = useListBoardViewPreference('commercial-projects');
  const canDuplicateProject = useHasPermission('commercial_core.projects.add');

  const { data: usersSelect = [] } = useQuery({
    queryKey: ['user-select-commercial-projects'],
    queryFn: async () => {
      const r = await apiFetch('/api/user-management/users/select');
      if (!r.ok) return [];
      return (await r.json()) as UserSelectRow[];
    },
    staleTime: 60_000,
  });

  const { data: workflowProjectStages = [] } = useQuery({
    queryKey: ['workflow-stages', 'project'],
    queryFn: () => getWorkflowStages({ domain: 'project' }),
    staleTime: 60_000,
  });

  const { data, isLoading, isFetching, refetch } = useCommercialProjects(
    {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      owner_user_id: ownerFilter || undefined,
      project_stage_id: stageFilter === '__all__' ? undefined : stageFilter,
    },
    { enabled: !hydrated || mode === 'list' },
  );

  const columns = useMemo<ColumnDef<CommercialProjectListRow>[]>(
    () => [
      {
        accessorKey: 'title',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project" column={column} className={HEADER_MUTED} />
        ),
        size: 240,
        cell: ({ row }) => (
          <TruncatedTextCell
            text={row.original.title}
            dialogTitle="Project title"
            renderLabel={(label) => (
              <Link
                href={`/commercial-management/projects/${row.original.id}`}
                className={cn(LINK_ACCENT, 'block min-w-0')}
                onClick={(e) => e.stopPropagation()}
              >
                {label}
              </Link>
            )}
          />
        ),
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'project_stage_name',
        id: 'project_stage_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} className={HEADER_MUTED} />
        ),
        size: 140,
        cell: ({ row }) => (
          <span
            className={cn(
              'inline-flex max-w-full truncate rounded px-2 py-1 text-xs font-medium',
              projectStageBadgeClass(row.original.project_stage_code || row.original.status),
            )}
          >
            {row.original.project_stage_name || row.original.status || '—'}
          </span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'project_lead_count',
        header: ({ column }) => <DataGridColumnHeader title="No. of Leads" column={column} className={HEADER_MUTED} />,
        size: 132,
        cell: ({ row }) => {
          const leads = row.original.project_leads ?? [];
          const count = row.original.project_lead_count ?? leads.length ?? (row.original.lead_code ? 1 : 0);
          return (
            <div className="flex items-center gap-2">
              <Link
                href={`/commercial-management/projects/${row.original.id}`}
                className="inline-flex items-center gap-1 text-[#101828]"
                onClick={(e) => e.stopPropagation()}
                title="View leads in this project"
              >
                <Users className="size-4 text-[#e7000b]" />
                <span className="text-sm font-medium">{count || 0}</span>
              </Link>
              <Popover>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className="text-[#6a7282] hover:text-[#101828]"
                    onClick={(e) => e.stopPropagation()}
                    aria-label="View lead details"
                  >
                    <Info className="size-4" />
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-72" align="start">
                  <p className="mb-2 text-sm font-medium text-[#101828]">Leads in this project</p>
                  {leads.length ? (
                    <div className="space-y-1">
                      {leads.map((lead) => (
                        <div key={lead.id} className="text-sm text-[#364153]">
                          {(lead.lead_code || lead.id) + (lead.lead_title ? ` — ${lead.lead_title}` : '')}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-[#6a7282]">No linked leads.</div>
                  )}
                </PopoverContent>
              </Popover>
            </div>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="No. of Clients" column={column} className={HEADER_MUTED} />
        ),
        size: 180,
        cell: ({ row }) => {
          const leads: Array<{
            id: string;
            customer_id?: string | null;
            customer_name?: string | null;
          }> = (row.original.project_leads ?? []) as Array<{
            id: string;
            customer_id?: string | null;
            customer_name?: string | null;
          }>;
          const clients = Array.from(
            new Map(
              leads
                .filter((lead) => Boolean(lead.customer_id || lead.customer_name))
                .map((lead) => [lead.customer_id || lead.customer_name || lead.id, lead.customer_name || lead.customer_id || '—']),
            ).values(),
          );
          const count = clients.length || (row.original.customer_name ? 1 : 0);
          return (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 text-[#101828]">
                <Users className="size-4 text-[#e7000b]" />
                <span className="text-sm font-medium">{count || 0}</span>
              </span>
              <Popover>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className="text-[#6a7282] hover:text-[#101828]"
                    onClick={(e) => e.stopPropagation()}
                    aria-label="View client details"
                  >
                    <Info className="size-4" />
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-72" align="start">
                  <p className="mb-2 text-sm font-medium text-[#101828]">Clients in this project</p>
                  {clients.length ? (
                    <div className="space-y-1">
                      {clients.map((client, idx) => (
                        <div key={`${client}-${idx}`} className="text-sm text-[#364153]">
                          {client}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-[#6a7282]">
                      {(row.original.customer_name || '').trim() || 'No linked clients.'}
                    </div>
                  )}
                </PopoverContent>
              </Popover>
            </div>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'owner_name',
        header: ({ column }) => <DataGridColumnHeader title="Owner" column={column} className={HEADER_MUTED} />,
        size: 140,
        cell: ({ row }) => row.original.owner_name || '—',
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created" column={column} className={HEADER_MUTED} />,
        size: 110,
        cell: ({ row }) => (
          <span className="text-[#101828] text-sm tabular-nums">{formatListDate(row.original.created_at)}</span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        size: 48,
        cell: ({ row }) => (
          <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="size-8">
                  <MoreVertical className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {canDuplicateProject ? (
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={async () => {
                      try {
                        const dup = await duplicateCommercialProject(row.original.id);
                        toast.success(`Project ${dup.title} copied successfully`);
                        router.push(`/commercial-management/projects/${dup.id}`);
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : 'Failed to duplicate project');
                      }
                    }}
                  >
                    <Copy className="size-4 shrink-0" aria-hidden />
                    Duplicate
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem onClick={() => router.push(`/commercial-management/projects/${row.original.id}`)}>
                  Open
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      },
    ],
    [router, canDuplicateProject],
  );

  const showBoard = hydrated && mode === 'board';

  const table = useReactTable({
    data: data?.data ?? [],
    columns,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    pageCount: data?.pagination
      ? Math.max(1, Math.ceil(data.pagination.total / pagination.pageSize))
      : 1,
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination?.total ?? 0}
        isLoading={!showBoard && (isLoading || isFetching)}
        standardToolbar={!showBoard}
        onRowClick={(row) => router.push(`/commercial-management/projects/${row.id}`)}
        tableLayout={{
          columnsVisibility: false,
          rowBorder: true,
          headerBorder: true,
          headerBackground: true,
        }}
        tableClassNames={{
          headerRow:
            'bg-[#f9fafb] hover:bg-[#f9fafb] [&_th]:h-11 [&_th]:border-b [&_th]:border-[#e5e7eb] [&_th]:align-middle',
          bodyRow: 'h-12 border-b border-[#e5e7eb] last:border-b-0',
        }}
        onRefresh={() => void refetch()}
        isRefreshing={isFetching && !isLoading}
      >
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-1">
            <h1 className="text-[30px] font-semibold leading-9 tracking-tight text-[#101828]">Projects</h1>
            <nav aria-label="Breadcrumb" className="text-sm text-[#6a7282]">
              <Link href="/" className="hover:text-[#101828]">
                Home
              </Link>
              <span className="mx-2 text-[#e5e7eb]">›</span>
              <span className="text-[#101828]">Commercial</span>
            </nav>
          </div>

          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
              <div className="relative max-w-md min-w-[min(100%,280px)] flex-1">
                <Search className="text-muted-foreground pointer-events-none absolute start-3 top-1/2 size-[18px] -translate-y-1/2" />
                <Input
                  className={cn(CONTROL_SURFACE, 'ps-10 text-sm placeholder:text-[rgba(10,10,10,0.45)]')}
                  placeholder="Search projects…"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setPagination((p) => ({ ...p, pageIndex: 0 }));
                  }}
                />
              </div>
              <Select
                value={ownerFilter || '__all__'}
                onValueChange={(v) => {
                  setOwnerFilter(v === '__all__' ? '' : v);
                  setPagination((p) => ({ ...p, pageIndex: 0 }));
                }}
              >
                <SelectTrigger className={cn(CONTROL_SURFACE, 'w-[180px] shrink-0')}>
                  <SelectValue placeholder="Owner" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All owners</SelectItem>
                  {usersSelect.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {(u.name || '').trim() || u.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={stageFilter}
                onValueChange={(v) => {
                  setStageFilter(v);
                  setPagination((p) => ({ ...p, pageIndex: 0 }));
                }}
              >
                <SelectTrigger className={cn(CONTROL_SURFACE, 'w-[180px] shrink-0')}>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All statuses</SelectItem>
                  {workflowProjectStages.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <ListBoardViewToggle value={mode} onChange={setMode} />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="primary"
                size="lg"
                className="h-10 shrink-0 rounded-[10px] px-6 text-base font-medium"
                onClick={() => setCreateOpen(true)}
              >
                + New project
              </Button>
            </div>
          </div>

          {showBoard ? (
            <ProjectsKanbanClient searchQuery={searchQuery} ownerUserId={ownerFilter || undefined} />
          ) : (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white shadow-none">
              <CardHeader className="sr-only">
                <span>Projects</span>
              </CardHeader>
              <CardTable className="overflow-hidden">
                <ScrollArea className="min-h-[12rem]">
                  <DataGridTable />
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              </CardTable>
              <CardFooter className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e5e7eb] bg-white py-3">
                <DataGridPagination />
              </CardFooter>
            </Card>
          )}
        </div>
      </DataGrid>
      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
    </>
  );
}
