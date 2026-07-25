'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Download, X } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useImportJobRows } from '../hooks/useImportJobs';
import { downloadImportJobRowsCsv } from '../services/importJobService';
import type {
  ImportJobResultEnvelope,
  ImportJobRow,
  ImportRowOutcome,
} from '../types/importJob.types';

const OUTCOME_OPTIONS = [
  { value: '', label: 'All outcomes' },
  { value: 'created', label: 'Created' },
  { value: 'updated', label: 'Updated' },
  { value: 'unchanged', label: 'Unchanged' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'failed', label: 'Failed' },
];

const OUTCOME_BADGE: Record<ImportRowOutcome, string> = {
  created: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400',
  updated: 'bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-400',
  unchanged: 'bg-muted text-muted-foreground',
  skipped: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-500',
  failed: 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400',
};

/** Business keys only — identity never carries UUIDs, so this is safe to print. */
function formatIdentity(identity?: Record<string, unknown> | null): string {
  if (!identity || typeof identity !== 'object') return '—';
  const parts = Object.entries(identity)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${String(v)}`);
  return parts.length ? parts.join(' · ') : '—';
}

export interface ImportJobRowsCardProps {
  jobId: string;
  result?: ImportJobResultEnvelope | null;
  /** Reason code selected from the breakdown card. */
  codeFilter?: string;
  outcomeFilter?: string;
  onChangeCode?: (code: string) => void;
  onChangeOutcome?: (outcome: string) => void;
}

export function ImportJobRowsCard({
  jobId,
  result,
  codeFilter = '',
  outcomeFilter = '',
  onChangeCode,
  onChangeOutcome,
}: ImportJobRowsCardProps) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [downloading, setDownloading] = useState(false);

  const query = {
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    outcome: outcomeFilter || undefined,
    code: codeFilter || undefined,
    query: search || undefined,
  };

  const { data, isLoading, isError, error } = useImportJobRows(jobId, query);

  // Reason options come from the job's own breakdown, so the filter can only offer
  // codes this job actually produced.
  const codeOptions = useMemo(() => {
    const breakdown = result?.breakdown;
    const seen = new Map<string, string>();
    (['successful', 'skipped', 'failed'] as const).forEach((group) => {
      (breakdown?.[group] ?? []).forEach((entry) => {
        if (!seen.has(entry.code)) seen.set(entry.code, entry.label || entry.code);
      });
    });
    return [
      { value: '', label: 'All reasons' },
      ...[...seen.entries()].map(([value, label]) => ({ value, label })),
    ];
  }, [result]);

  const columns = useMemo<ColumnDef<ImportJobRow>[]>(
    () => [
      {
        accessorKey: 'row_number',
        header: ({ column }) => <DataGridColumnHeader title="Row #" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono tabular-nums">{row.original.row_number ?? '—'}</span>
        ),
        size: 90,
        minSize: 70,
        meta: { headerTitle: 'Row #', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        accessorKey: 'outcome',
        header: ({ column }) => <DataGridColumnHeader title="Outcome" column={column} />,
        cell: ({ row }) => (
          <span
            className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${
              OUTCOME_BADGE[row.original.outcome] ?? 'bg-muted text-muted-foreground'
            }`}
          >
            {row.original.outcome}
          </span>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Outcome', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Reason" column={column} />,
        cell: ({ row }) => {
          const text = row.original.label || row.original.code;
          return (
            <span className="block truncate" title={`${text} (${row.original.code})`}>
              {text}
            </span>
          );
        },
        size: 240,
        minSize: 140,
        meta: { headerTitle: 'Reason', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'message',
        header: ({ column }) => <DataGridColumnHeader title="Detail" column={column} />,
        cell: ({ row }) => {
          const text = row.original.message || '—';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 320,
        minSize: 160,
        meta: { headerTitle: 'Detail', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'identity',
        header: ({ column }) => <DataGridColumnHeader title="Identity" column={column} />,
        cell: ({ row }) => {
          const text = formatIdentity(row.original.identity);
          return (
            <span className="block truncate text-muted-foreground" title={text}>
              {text}
            </span>
          );
        },
        size: 320,
        minSize: 160,
        meta: { headerTitle: 'Identity', skeleton: <Skeleton className="h-4 w-40" /> },
      },
    ],
    [],
  );

  const total = data?.pagination?.total ?? 0;

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil(total / pagination.pageSize) || 0,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    columnResizeMode: 'onChange',
  });

  const resetPage = () => setPagination((p) => ({ ...p, pageIndex: 0 }));

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await downloadImportJobRowsCsv(jobId, {
        outcome: outcomeFilter || undefined,
        code: codeFilter || undefined,
        query: search || undefined,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `import-job-${jobId}-rows.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to export rows');
    } finally {
      setDownloading(false);
    }
  };

  const activeFilterCount = (outcomeFilter ? 1 : 0) + (codeFilter ? 1 : 0) + (search ? 1 : 0);

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <p className="text-sm font-medium">Rows</p>
              <Badge variant="secondary" appearance="ghost">
                {total.toLocaleString()} matching
              </Badge>
              {result?.rows_truncated && (
                <span className="text-xs text-amber-600 dark:text-amber-500">
                  showing the first {(result.rows_total ?? 0).toLocaleString()} rows captured —
                  counts above remain exact
                </span>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={downloading || total === 0}
            >
              <Download className="size-4" />
              {downloading ? 'Preparing…' : 'Download CSV'}
            </Button>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="w-full sm:w-48">
              <SearchableSelect
                value={outcomeFilter}
                onChange={(value) => {
                  onChangeOutcome?.(value);
                  resetPage();
                }}
                options={OUTCOME_OPTIONS}
                placeholder="All outcomes"
                size="sm"
              />
            </div>
            <div className="w-full sm:w-64">
              <SearchableSelect
                value={codeFilter}
                onChange={(value) => {
                  onChangeCode?.(value);
                  resetPage();
                }}
                options={codeOptions}
                placeholder="All reasons"
                size="sm"
              />
            </div>
            <form
              className="flex w-full items-center gap-2 sm:w-auto sm:flex-1"
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(searchInput.trim());
                resetPage();
              }}
            >
              <Input
                placeholder="Search detail, value or identity…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="h-8"
              />
              <Button type="submit" variant="outline" size="sm">
                Search
              </Button>
            </form>
            {activeFilterCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  onChangeOutcome?.('');
                  onChangeCode?.('');
                  setSearchInput('');
                  setSearch('');
                  resetPage();
                }}
              >
                <X className="size-4" />
                Clear
              </Button>
            )}
          </div>
        </CardHeader>
        <CardTable>
          {isError ? (
            <div className="px-6 py-10 text-center text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load rows'}
            </div>
          ) : !isLoading && total === 0 ? (
            <div className="px-6 py-10 text-center">
              <p className="text-sm text-muted-foreground">
                {activeFilterCount > 0
                  ? 'No rows match these filters.'
                  : 'No per-row detail was captured for this job.'}
              </p>
              {activeFilterCount === 0 && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Jobs that ran before row capture existed, or whose row detail has passed its
                  retention window, keep their counts but not their rows.
                </p>
              )}
            </div>
          ) : (
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardTable>
        {total > 0 && (
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}

export default ImportJobRowsCard;
