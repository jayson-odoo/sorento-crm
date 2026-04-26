'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Columns3, Copy, Download, MoreVertical, Plus, Search, SlidersHorizontal } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { useQuotationsList } from '../hooks/useQuotationsList';
import type { MasterQuotationTableRow } from '../types/quotationList.types';
import { masterQuotationDisplayCode } from '../lib/masterQuotationDisplayCode';
import { apiFetch } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useListBoardViewPreference } from '@/hooks/useListBoardViewPreference';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import { MasterQuotationsKanbanClient } from '@/app/(protected)/commercial-management/pipeline/master-quotations/MasterQuotationsKanbanClient';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';
import { useQuery } from '@tanstack/react-query';
import { useHasPermission } from '@/hooks/usePermissions';
import { duplicateMasterQuotation } from '@/app/(protected)/commercial-management/projects/services/commercialProjectService';
import { CreateQuotationDialog } from './CreateQuotationDialog';

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
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return '—';
  }
}

function quotationStageBadgeClass(stageCode: string | null | undefined): string {
  const c = (stageCode || '').toLowerCase();
  if (c.includes('lost') || c.includes('reject') || c.includes('cancel')) return 'bg-[#ffe2e2] text-[#9f0712]';
  if (c.includes('won') || c.includes('accept') || c.includes('approved')) return 'bg-[#dcfce7] text-[#016630]';
  if (c.includes('draft') || c.includes('prep')) return 'bg-zinc-100 text-zinc-700';
  return 'bg-[#dbeafe] text-[#1447e6]';
}

const CONTROL_SURFACE = 'h-9 border-0 bg-[#f3f3f5] shadow-none rounded-lg';

export default function QuotationsList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('__all__');
  const { mode, setMode, hydrated } = useListBoardViewPreference('commercial-quotations');
  const canAddQuotation = useHasPermission('commercial_core.master_quotations.add');
  const [createQuotationOpen, setCreateQuotationOpen] = useState(false);
  const prefillCustomerId = searchParams.get('customer_id');
  const prefillProjectId = searchParams.get('project_id');
  const prefillLeadId = searchParams.get('lead_id');
  const autoOpenCreate = searchParams.get('open_create_quotation') === '1';

  useEffect(() => {
    if (!autoOpenCreate) return;
    setCreateQuotationOpen(true);
  }, [autoOpenCreate]);

  const { data: usersSelect = [] } = useQuery({
    queryKey: ['user-select-commercial-quotations-list'],
    queryFn: async () => {
      const r = await apiFetch('/api/user-management/users/select');
      if (!r.ok) return [];
      return (await r.json()) as UserSelectRow[];
    },
    staleTime: 60_000,
  });

  const { data: mqStages = [] } = useQuery({
    queryKey: ['workflow-stages', 'quotation'],
    queryFn: () => getWorkflowStages({ domain: 'quotation' }),
    staleTime: 60_000,
  });

  const { data, isLoading, isFetching, refetch } = useQuotationsList(
    {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      owner_user_id: ownerFilter || undefined,
      quotation_stage_code: stageFilter === '__all__' ? undefined : stageFilter,
      scope: 'all',
    },
    { enabled: !hydrated || mode === 'list' },
  );

  const workspaceHref = useCallback((row: MasterQuotationTableRow) => {
    return `/commercial-management/quotation-revisions?tender=${encodeURIComponent(row.tender_code)}&quotation=${encodeURIComponent(row.quotation_code)}${row.project_id ? `&project=${encodeURIComponent(row.project_id)}` : ''}`;
  }, []);

  const columns = useMemo<ColumnDef<MasterQuotationTableRow>[]>(
    () => [
      {
        accessorKey: 'quotation_code',
        header: ({ column }) => (
          <DataGridColumnHeader title="Quotation" column={column} className={HEADER_MUTED} />
        ),
        size: 220,
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="min-w-0">
              <Link href={workspaceHref(r)} className={LINK_ACCENT} onClick={(e) => e.stopPropagation()}>
                {masterQuotationDisplayCode(r)}
              </Link>
              {r.title ? <div className="text-muted-foreground truncate text-xs">{r.title}</div> : null}
            </div>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'quotation_stage',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} className={HEADER_MUTED} />
        ),
        size: 140,
        cell: ({ row }) => {
          const st = row.original.quotation_stage;
          const label = st?.stage_name || '—';
          return (
            <span
              className={cn(
                'inline-flex max-w-full truncate rounded px-2 py-1 text-xs font-medium',
                quotationStageBadgeClass(st?.stage_code),
              )}
            >
              {label}
            </span>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'project_title',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project" column={column} className={HEADER_MUTED} />
        ),
        size: 200,
        cell: ({ row }) => {
          const r = row.original;
          if (!r.project_id) return '—';
          return (
            <Link
              href={`/commercial-management/projects/${r.project_id}`}
              className={LINK_ACCENT}
              onClick={(e) => e.stopPropagation()}
            >
              {r.project_title || '—'}
            </Link>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-36" /> },
      },
      {
        accessorKey: 'lead_code',
        header: ({ column }) => <DataGridColumnHeader title="Lead" column={column} className={HEADER_MUTED} />,
        size: 132,
        cell: ({ row }) => {
          const r = row.original;
          if (!r.lead_id) return '—';
          return (
            <Link href={`/commercial/leads/${r.lead_id}`} className={LINK_ACCENT} onClick={(e) => e.stopPropagation()}>
              {r.lead_code}
            </Link>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'client_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Client" column={column} className={HEADER_MUTED} />
        ),
        size: 180,
        cell: ({ row }) => (
          <span className="text-[#101828] text-sm">{row.original.client_name?.trim() || '—'}</span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'amount',
        header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} className={HEADER_MUTED} />,
        size: 120,
        cell: ({ row }) => {
          const r = row.original;
          if (!r.quoted_amount) return '—';
          const cur = r.quoted_currency ? ` ${r.quoted_currency}` : '';
          return (
            <span className="text-[#101828] text-sm tabular-nums">
              {r.quoted_amount}
              {cur}
            </span>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
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
        size: 160,
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
                {canAddQuotation ? (
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={async () => {
                      try {
                        const dup = await duplicateMasterQuotation(row.original.id);
                        const label = masterQuotationDisplayCode({
                          quotation_code: dup.quotation_code,
                          current_working_revision_number: 1,
                        });
                        toast.success(`Quotation ${label} copied successfully`);
                        const pid = dup.project_id ?? row.original.project_id;
                        router.push(
                          `/commercial-management/quotation-revisions?tender=${encodeURIComponent(dup.tender_code)}&quotation=${encodeURIComponent(dup.quotation_code)}${pid ? `&project=${encodeURIComponent(pid)}` : ''}`,
                        );
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : 'Failed to duplicate quotation');
                      }
                    }}
                  >
                    <Copy className="size-4 shrink-0" aria-hidden />
                    Duplicate
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem onClick={() => router.push(workspaceHref(row.original))}>Open</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
        meta: { skeleton: <Skeleton className="h-8 w-8" /> },
      },
    ],
    [canAddQuotation, router, workspaceHref],
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
    <DataGrid
      table={table}
      recordCount={data?.pagination?.total ?? 0}
      isLoading={!showBoard && (isLoading || isFetching)}
      standardToolbar={!showBoard}
      onRowClick={(row) => router.push(workspaceHref(row))}
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
          <h1 className="text-[30px] font-semibold leading-9 tracking-tight text-[#101828]">Quotations</h1>
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
                placeholder="Search…"
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
                {mqStages.map((s) => (
                  <SelectItem key={s.id} value={s.code}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ListBoardViewToggle value={mode} onChange={setMode} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {canAddQuotation ? (
              <Button
                type="button"
                variant="primary"
                size="lg"
                className="h-10 shrink-0 rounded-[14px] px-6 text-base font-medium"
                onClick={() => setCreateQuotationOpen(true)}
              >
                <Plus className="size-4" aria-hidden />
                New quotation
              </Button>
            ) : null}
          </div>
        </div>

        {showBoard ? (
          <MasterQuotationsKanbanClient />
        ) : (
          <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white shadow-none">
            <CardHeader className="sr-only">
              <span>Quotations</span>
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

      <CreateQuotationDialog
        open={createQuotationOpen}
        onOpenChange={setCreateQuotationOpen}
        initialCustomerId={prefillCustomerId}
        initialProjectId={prefillProjectId}
        initialLeadId={prefillLeadId}
        onCreated={() => void refetch()}
      />
    </DataGrid>
  );
}
