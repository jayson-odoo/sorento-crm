'use client';

/** The outcome tiles and the report rows grid, shared by Preview and Results (AC-PI-47/48). */

import * as React from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { formatDateSafe } from '@/lib/helpers';
import { useProjectImportRows } from '../../../_shared/hooks/useProjectImport';
import type {
  ProjectImportCounts,
  ProjectImportOutcome,
  ProjectImportReportRow,
  ProjectImportRun,
} from '../../../_shared/types/projectImport.types';
import {
  OUTCOME_DONE_LABELS,
  OUTCOME_LABELS,
  OUTCOME_ROW_LABELS,
} from '../../components/importLabels';

const TILES: ProjectImportOutcome[] = ['created', 'updated', 'unchanged', 'skipped', 'needs_review', 'error'];

const OUTCOME_OPTIONS = (Object.keys(OUTCOME_ROW_LABELS) as ProjectImportOutcome[]).map((value) => ({
  value,
  label: OUTCOME_ROW_LABELS[value],
}));

export function OutcomeTiles({
  counts,
  done = false,
}: {
  counts: ProjectImportCounts | null | undefined;
  /** The import has run: the tiles say what it did ("Created"), not what it will do. */
  done?: boolean;
}) {
  const labels = done ? OUTCOME_DONE_LABELS : OUTCOME_LABELS;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {TILES.map((outcome) => (
        <div key={outcome} className="rounded-lg border bg-card p-3">
          <div className="text-xs text-muted-foreground">{labels[outcome]}</div>
          <div className="text-xl font-semibold tabular-nums">{counts?.[outcome] ?? 0}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * The report rows of a run, filtered and sorted on the server. Shared by Preview and the
 * Results tab, so the two read a row the same way.
 */
export function ReportRowsGrid({
  run,
  onRowClick,
  listingKey,
}: {
  run: ProjectImportRun;
  onRowClick?: (row: ProjectImportReportRow) => void;
  listingKey: string;
}) {
  const { value: search, setValue: setSearch, debouncedValue, isSettling } = useDebouncedSearch();
  const [pagination, setPagination] = React.useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [outcome, setOutcome] = React.useState<string[]>([]);
  const [code, setCode] = React.useState<string[]>([]);
  const [sheet, setSheet] = React.useState<string[]>([]);

  React.useEffect(() => {
    setPagination((p) => (p.pageIndex === 0 ? p : { ...p, pageIndex: 0 }));
  }, [outcome, code, sheet, debouncedValue]);

  const rows = useProjectImportRows(
    run.id,
    { ...pagination, sorting, searchQuery: debouncedValue },
    { outcome, code, sheet },
  );
  const data = rows.data?.data ?? [];
  const activeFilters = [outcome, code, sheet].filter((v) => v.length > 0).length;
  const total = rows.data?.total ?? 0;

  const codes = run.result_codes ?? run.preview_codes ?? {};
  // Labels come from the API (`code_labels`, each row's `labels`); no copy of the table here.
  const codeLabels = run.code_labels ?? {};
  const codeOptions = Object.keys(codes)
    .map((value) => ({ value, label: codeLabels[value] ?? '' }))
    .filter((option) => option.label)
    .sort((a, b) => a.label.localeCompare(b.label));
  const sheetOptions = (run.sheets ?? [])
    .filter((s) => s.has_ps_heading)
    .map((s) => ({ value: s.name, label: s.name_trimmed }));

  const columns = React.useMemo<ColumnDef<ProjectImportReportRow>[]>(
    () => [
      // Sized to fit the 1280 content width with the sidebar open (browser pass D3): PS no. and
      // PO date whole, Outcome and Reason in view; long names truncate with a title.
      {
        accessorKey: 'sheet',
        header: ({ column }) => <DataGridColumnHeader title="Sheet" column={column} />,
        size: 72,
        meta: { headerTitle: 'Sheet', skeleton: <Skeleton className="h-4 w-14" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.sheet.trim()}>
            {row.original.sheet.trim()}
          </span>
        ),
      },
      {
        accessorKey: 'row_number',
        header: ({ column }) => <DataGridColumnHeader title="Row" column={column} />,
        size: 60,
        meta: { headerTitle: 'Row' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.row_number}</span>,
      },
      {
        accessorKey: 'ps_number',
        // Sized to fit and fixed: the grid truncates a resizable cell, and this one must
        // always read whole (browser pass N1 / N2).
        enableResizing: false,
        header: ({ column }) => <DataGridColumnHeader title="PS no." column={column} />,
        size: 120,
        meta: { headerTitle: 'PS no.' },
        cell: ({ row }) => <span className="font-medium">{row.original.ps_number}</span>,
      },
      {
        accessorKey: 'customer',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        size: 120,
        meta: { headerTitle: 'Customer' },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.customer ?? ''}>
            {row.original.customer}
          </span>
        ),
      },
      {
        accessorKey: 'project',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        size: 120,
        meta: { headerTitle: 'Project' },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.project ?? ''}>
            {row.original.project}
          </span>
        ),
      },
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="PO no." column={column} />,
        size: 100,
        meta: { headerTitle: 'PO no.' },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.po_number ?? ''}>
            {row.original.po_number}
          </span>
        ),
      },
      {
        accessorKey: 'po_date',
        // Sized to fit and fixed: the grid truncates a resizable cell, and this one must
        // always read whole (browser pass N1 / N2).
        enableResizing: false,
        header: ({ column }) => <DataGridColumnHeader title="PO date" column={column} />,
        size: 120,
        meta: { headerTitle: 'PO date' },
        cell: ({ row }) => formatDateSafe(row.original.po_date, ''),
      },
      {
        accessorKey: 'outcome',
        header: ({ column }) => <DataGridColumnHeader title="Outcome" column={column} />,
        size: 105,
        meta: { headerTitle: 'Outcome' },
        cell: ({ row }) => OUTCOME_ROW_LABELS[row.original.outcome] ?? row.original.outcome,
      },
      {
        id: 'reason',
        accessorFn: (row) => row.message || (row.labels ?? []).join('; '),
        header: ({ column }) => <DataGridColumnHeader title="Reason" column={column} />,
        size: 125,
        meta: { headerTitle: 'Reason' },
        cell: ({ row }) => {
          const text = row.original.message || (row.original.labels ?? []).join('; ');
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data,
    getRowId: (row) => `${row.sheet}\u0001${row.row_number}`,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={rows.isLoading}
      error={rows.error}
      onRetry={() => void rows.refetch()}
      isPlaceholderData={rows.isPlaceholderData}
      onRowClick={onRowClick}
      listingKey={listingKey}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={
        <div className="px-6 py-10 text-center">
          <p className="text-sm font-semibold">No rows match</p>
        </div>
      }
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={search}
                onChange={setSearch}
                isSettling={isSearchInFlight(isSettling, rows.isFetching, debouncedValue)}
                placeholder="Search PS no., customer, project or PO"
                aria-label="Search rows"
                className="w-full sm:w-64 md:w-80"
              />
            }
            filters={{
              kind: 'custom',
              active: activeFilters > 0,
              activeCount: activeFilters,
              content: (
                <div className="space-y-3">
                  {(
                    [
                      ['Outcome', outcome, setOutcome, OUTCOME_OPTIONS],
                      ['Reason', code, setCode, codeOptions],
                      ['Sheet', sheet, setSheet, sheetOptions],
                    ] as const
                  ).map(([label, value, onChange, options]) => (
                    <div key={label} className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{label}</Label>
                      <SearchableMultiSelect
                        value={[...value]}
                        onChange={onChange}
                        options={[...options]}
                        clearable
                        placeholder={label}
                        aria-label={label}
                      />
                    </div>
                  ))}
                  {activeFilters > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => {
                        setOutcome([]);
                        setCode([]);
                        setSheet([]);
                      }}
                    >
                      Clear filters
                    </Button>
                  )}
                </div>
              ),
            }}
            exportConfig={false}
            onRefresh={() => void rows.refetch()}
            isRefreshing={rows.isFetching && !rows.isLoading}
          />
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
