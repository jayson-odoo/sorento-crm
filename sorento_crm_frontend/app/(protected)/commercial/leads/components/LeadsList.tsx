'use client';

import { useMemo, useState } from 'react';
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
import { Copy, MoreVertical, Search } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { duplicateCommercialLead } from '../services/leadService';
import { useCommercialLeads } from '../hooks/useCommercialLeads';
import { useLeadStagesList } from '../hooks/useLeadStages';
import type { CommercialLead } from '../types/lead.types';
import { useHasPermission } from '@/hooks/usePermissions';
import { useListBoardViewPreference } from '@/hooks/useListBoardViewPreference';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import { LeadsKanbanClient } from '@/app/(protected)/commercial-management/pipeline/leads/LeadsKanbanClient';
import { cn } from '@/lib/utils';

function qualDisplay(q: Record<string, unknown> | undefined, key: string): string {
  if (!q) return '—';
  const v = q[key];
  if (v == null || v === '') return '—';
  if (typeof v === 'string' || typeof v === 'number') return String(v);
  if (typeof v === 'object' && v !== null && 'label' in v) {
    const l = (v as { label?: unknown }).label;
    return l != null && String(l) ? String(l) : '—';
  }
  return '—';
}

/** Table empty cell per Figma (ASCII hyphen). */
function qualTableCell(q: Record<string, unknown> | undefined, key: string): string {
  const s = qualDisplay(q, key);
  return s === '—' ? '-' : s;
}

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

/** Status pills aligned with Figma (rounded 4px, purple proposal / blue new). */
function stageBadgeClass(stageCode: string | null | undefined): string {
  const c = (stageCode || '').toLowerCase();
  if (c.includes('won')) return 'bg-emerald-100 text-emerald-800';
  if (c.includes('lost') || c.includes('withdraw') || c.includes('no_award'))
    return 'bg-red-100 text-red-800';
  if (c.includes('proposal')) return 'bg-[#f3e8ff] text-[#8200db]';
  if (c.includes('new')) return 'bg-[#dbeafe] text-[#1447e6]';
  if (c.includes('qualif')) return 'bg-amber-100 text-amber-900';
  return 'bg-zinc-100 text-zinc-700';
}

const HEADER_MUTED = 'text-[#6a7282] text-xs font-medium uppercase tracking-wide';
const LINK_ACCENT = 'text-[#e7000b] font-medium hover:underline';

export default function LeadsList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const customerIdFromUrl = searchParams.get('customer_id') || undefined;
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 20 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchDraft, setSearchDraft] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [leadStageId, setLeadStageId] = useState<string | undefined>(undefined);
  const [pipelineFilter, setPipelineFilter] = useState<'all' | 'open'>('all');
  const canAdd = useHasPermission('commercial_core.leads.add');
  const { mode, setMode, hydrated } = useListBoardViewPreference('commercial-leads');

  const { data, isLoading, refetch, isFetching } = useCommercialLeads(
    {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      customer_id: customerIdFromUrl,
      lead_stage_id: leadStageId,
      open_pipeline_only: pipelineFilter === 'open',
    },
    { enabled: !hydrated || mode === 'list' },
  );

  const { data: stages = [] } = useLeadStagesList();

  const columns = useMemo<ColumnDef<CommercialLead>[]>(
    () => [
      {
        accessorKey: 'lead_code',
        header: ({ column }) => (
          <DataGridColumnHeader title="Lead Ref" column={column} className={HEADER_MUTED} />
        ),
        size: 132,
        cell: ({ row }) => (
          <Link
            href={`/commercial/leads/${row.original.id}`}
            className={LINK_ACCENT}
            onClick={(e) => e.stopPropagation()}
          >
            {row.original.lead_code}
          </Link>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Title" column={column} className={HEADER_MUTED} />,
        size: 200,
        enableSorting: true,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'customer_name',
        accessorKey: 'customer_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Client Name" column={column} className={HEADER_MUTED} />
        ),
        size: 180,
        cell: ({ row }) => {
          const name = row.original.customer_name || '—';
          const cid = row.original.customer_id;
          if (!cid || name === '—') {
            return <span className="text-muted-foreground">{name}</span>;
          }
          return (
            <Link
              href={`/order-management/customers/${cid}`}
              className={LINK_ACCENT}
              onClick={(e) => e.stopPropagation()}
            >
              {name}
            </Link>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'property_type',
        accessorFn: (row) => qualDisplay(row.qualification, 'property_type'),
        header: () => <span className={HEADER_MUTED}>Property Type</span>,
        size: 120,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-[#101828] text-sm">
            {qualTableCell(row.original.qualification, 'property_type')}
          </span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'budget_range',
        accessorFn: (row) => qualDisplay(row.qualification, 'budget_range'),
        header: () => <span className={HEADER_MUTED}>Budget Range</span>,
        size: 130,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-[#101828] text-sm">
            {qualTableCell(row.original.qualification, 'budget_range')}
          </span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'stage_name',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} className={HEADER_MUTED} />,
        size: 130,
        enableSorting: true,
        cell: ({ row }) => (
          <span
            className={cn(
              'inline-flex max-w-full truncate rounded px-2 py-1 text-xs font-medium',
              stageBadgeClass(row.original.stage_code),
            )}
          >
            {row.original.stage_name || row.original.stage_code || '—'}
          </span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
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
        id: 'created_by_name',
        accessorKey: 'created_by_name',
        header: () => <span className={HEADER_MUTED}>Created By</span>,
        size: 140,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-[#101828] text-sm">
            {row.original.created_by_name || row.original.owner_name || '—'}
          </span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
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
                  <MoreVertical className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {canAdd ? (
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={async () => {
                      try {
                        const dup = await duplicateCommercialLead(row.original.id);
                        toast.success(`Lead ${dup.lead_code} copied successfully`);
                        router.push(`/commercial/leads/${dup.id}`);
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : 'Failed to duplicate lead');
                      }
                    }}
                  >
                    <Copy className="size-4 shrink-0" aria-hidden />
                    Duplicate
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem onClick={() => router.push(`/commercial/leads/${row.original.id}`)}>
                  View lead
                </DropdownMenuItem>
                {row.original.customer_id ? (
                  <DropdownMenuItem
                    onClick={() => router.push(`/order-management/customers/${row.original.customer_id}`)}
                  >
                    View client
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      },
    ],
    [router, canAdd],
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
    initialState: {
      columnVisibility: {
        title: false,
      },
    },
  });

  const showBoard = hydrated && mode === 'board';

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading && !showBoard}
      standardToolbar={!showBoard}
      onRowClick={(row) => router.push(`/commercial/leads/${row.id}`)}
      tableLayout={{
        columnsVisibility: false,
        rowBorder: true,
        headerBorder: true,
        headerBackground: true,
      }}
      tableClassNames={{
        headerRow: 'bg-[#f9fafb] hover:bg-[#f9fafb] [&_th]:h-11 [&_th]:border-b [&_th]:border-[#e5e7eb] [&_th]:align-middle',
        bodyRow: 'h-12 border-b border-[#e5e7eb] last:border-b-0',
      }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            <div className="relative max-w-md min-w-[min(100%,280px)] flex-1">
              <Search className="text-muted-foreground pointer-events-none absolute start-3 top-1/2 size-[18px] -translate-y-1/2" />
              <Input
                className="h-11 rounded-[10px] border-border ps-10 text-base shadow-none placeholder:text-[rgba(10,10,10,0.5)]"
                placeholder="Search leads..."
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setSearchQuery(searchDraft.trim());
                }}
              />
            </div>
            <Select value={leadStageId ?? 'all'} onValueChange={(v) => setLeadStageId(v === 'all' ? undefined : v)}>
              <SelectTrigger className="h-[38px] w-[140px] shrink-0 rounded-[10px] shadow-none">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {stages.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.stage_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={pipelineFilter} onValueChange={(v) => setPipelineFilter(v as 'all' | 'open')}>
              <SelectTrigger className="h-[38px] w-[140px] shrink-0 rounded-[10px] shadow-none">
                <SelectValue placeholder="Pipeline" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All pipeline</SelectItem>
                <SelectItem value="open">Open stages only</SelectItem>
              </SelectContent>
            </Select>
            <ListBoardViewToggle value={mode} onChange={setMode} />
          </div>
          {canAdd ? (
            <Button
              variant="primary"
              size="lg"
              className="h-10 shrink-0 rounded-[10px] px-6 text-base font-medium"
              onClick={() =>
                router.push(
                  customerIdFromUrl
                    ? `/commercial/leads/new?customer_id=${encodeURIComponent(customerIdFromUrl)}`
                    : '/commercial/leads/new',
                )
              }
            >
              + Create Lead
            </Button>
          ) : null}
        </div>

        {showBoard ? (
          <LeadsKanbanClient />
        ) : (
          <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white shadow-none">
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
  );
}
