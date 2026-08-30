'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { AlertCircle, Search, ShieldQuestion, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { EM_DASH, fmtInt, fmtMoney } from '../../lib/format';
import type { ScenarioRow, ScenarioStatus } from '../types/simulation.types';

/** Shares no listing personalization - the harness has exactly one grid, and column
 *  order/visibility here is not worth persisting. */
const NO_COLUMN_PERSISTENCE = '';

const numMeta = { headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' };

/** Reuses the shared soft-pastel palette (no new colour vocabulary). */
const STATUS_PILL_CODE: Record<ScenarioStatus, string> = {
  SAME: 'new',
  CHANGED: 'pending',
  NEW: 'approved',
  GONE: 'rejected',
  NO_BASELINE: 'voided',
};

const STATUS_LABEL: Record<ScenarioStatus, string> = {
  SAME: 'Same',
  CHANGED: 'Changed',
  NEW: 'New',
  GONE: 'Gone',
  NO_BASELINE: 'No baseline',
};

const REC_TYPE_VARIANT: Record<string, 'info' | 'warning' | 'secondary' | 'success'> = {
  buy: 'info',
  exception: 'warning',
  disposition: 'secondary',
  covered: 'success',
  needs_level: 'secondary',
};

function RecTypeChip({ recType }: { recType: string | null }) {
  if (!recType) {
    return <span className="text-2xs text-muted-foreground">None</span>;
  }
  return (
    <Badge variant={REC_TYPE_VARIANT[recType] ?? 'secondary'} appearance="light" size="md">
      {recType}
    </Badge>
  );
}

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'CHANGED', label: 'Changed' },
  { value: 'NEW', label: 'New' },
  { value: 'GONE', label: 'Gone' },
  { value: 'SAME', label: 'Same' },
  { value: 'NO_BASELINE', label: 'No baseline' },
];

export interface ScenariosGridProps {
  rows: ScenarioRow[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  onRetry: () => void;
  onSelectRow: (code: string) => void;
}

export function ScenariosGrid({
  rows,
  isLoading,
  isError,
  error,
  onRetry,
  onSelectRow,
}: ScenariosGridProps) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const filtered = useMemo(() => {
    if (statusFilter === 'all') return rows;
    return rows.filter((r) => r.status === statusFilter);
  }, [rows, statusFilter]);

  const columns = useMemo<ColumnDef<ScenarioRow>[]>(
    () => [
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        cell: ({ row }) => <span className="font-medium">{row.original.code}</span>,
        size: 110,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-6 w-20" /> },
      },
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Scenario" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.title}>
            {row.original.title}
          </span>
        ),
        size: 240,
        meta: { headerTitle: 'Scenario' },
      },
      {
        accessorKey: 'expected_note',
        header: ({ column }) => <DataGridColumnHeader title="Probe" column={column} />,
        cell: ({ row }) => (
          <span
            className="truncate text-2xs text-muted-foreground"
            title={row.original.expected_note}
          >
            {row.original.expected_note}
          </span>
        ),
        enableSorting: false,
        size: 320,
        meta: { headerTitle: 'Probe' },
      },
      {
        accessorKey: 'segment',
        header: ({ column }) => <DataGridColumnHeader title="Segment" column={column} />,
        cell: ({ row }) => <span className="capitalize">{row.original.segment}</span>,
        size: 100,
        meta: { headerTitle: 'Segment' },
      },
      {
        id: 'on_hand',
        accessorFn: (r) => r.inputs.on_hand ?? -Infinity,
        header: ({ column }) => <DataGridColumnHeader title="On hand" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.inputs.on_hand)}</span>,
        size: 100,
        meta: { headerTitle: 'On hand', ...numMeta },
      },
      {
        id: 'demand',
        accessorFn: (r) => r.inputs.committed ?? -Infinity,
        header: ({ column }) => <DataGridColumnHeader title="SO / OI" column={column} />,
        cell: ({ row }) => {
          const { committed, demand_label } = row.original.inputs;
          return (
            <span className="tabular-nums">
              {fmtInt(committed)}
              <span className="ms-1 text-2xs text-muted-foreground">{demand_label}</span>
            </span>
          );
        },
        size: 110,
        meta: { headerTitle: 'SO / OI', ...numMeta },
      },
      {
        id: 'spo_incoming',
        accessorFn: (r) => r.inputs.spo_incoming ?? -Infinity,
        header: ({ column }) => <DataGridColumnHeader title="SPO" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.inputs.spo_incoming)}</span>,
        size: 90,
        meta: { headerTitle: 'SPO', ...numMeta },
      },
      {
        id: 'po_open',
        accessorFn: (r) => r.inputs.po_open,
        header: ({ column }) => <DataGridColumnHeader title="PO" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.inputs.po_open)}</span>,
        size: 90,
        meta: { headerTitle: 'PO', ...numMeta },
      },
      {
        id: 'rec',
        accessorFn: (r) => r.current?.rec_type ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Rec" column={column} />,
        cell: ({ row }) => <RecTypeChip recType={row.original.current?.rec_type ?? null} />,
        size: 130,
        meta: { headerTitle: 'Rec' },
      },
      {
        id: 'qty',
        accessorFn: (r) => r.current?.rounded_qty ?? -Infinity,
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => {
          const r = row.original;
          const cur = r.current?.rounded_qty ?? null;
          const base = r.baseline?.rounded_qty ?? null;
          const changed = r.status === 'CHANGED' && cur !== base;
          return (
            <span className="tabular-nums">
              {fmtInt(cur)}
              {changed ? (
                <span className="ms-1 text-2xs text-muted-foreground">
                  (was {fmtInt(base)})
                </span>
              ) : null}
            </span>
          );
        },
        size: 150,
        meta: { headerTitle: 'Qty', ...numMeta },
      },
      {
        id: 'cash_impact',
        accessorFn: (r) => r.current?.cash_impact ?? -Infinity,
        header: ({ column }) => <DataGridColumnHeader title="Cash impact" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtMoney(row.original.current?.cash_impact ?? null)}</span>,
        size: 140,
        meta: { headerTitle: 'Cash impact', ...numMeta },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(STATUS_PILL_CODE[row.original.status])}`}>
            {STATUS_LABEL[row.original.status]}
          </span>
        ),
        size: 130,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'changed_groups',
        header: ({ column }) => <DataGridColumnHeader title="Changed groups" column={column} />,
        cell: ({ row }) => {
          const groups = row.original.changed_groups;
          if (!groups.length) return <span className="text-muted-foreground">{EM_DASH}</span>;
          return (
            <div className="flex flex-wrap gap-1">
              {groups.map((g) => (
                <span
                  key={g}
                  className="rounded-full bg-muted px-2 py-0.5 text-2xs text-muted-foreground"
                >
                  {g}
                </span>
              ))}
            </div>
          );
        },
        enableSorting: false,
        size: 220,
        meta: { headerTitle: 'Changed groups' },
      },
    ],
    [],
  );

  const handleRowClick = (row: ScenarioRow) => onSelectRow(row.code);

  const table = useReactTable({
    data: filtered,
    columns,
    getRowId: (r) => r.code,
    state: { pagination, sorting, globalFilter: searchQuery },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearchQuery,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    globalFilterFn: (row, _id, value) => {
      const q = String(value ?? '').toLowerCase();
      if (!q) return true;
      const r = row.original;
      return (
        r.code.toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q) ||
        r.expected_note.toLowerCase().includes(q)
      );
    },
  });

  if (isLoading) {
    return <Skeleton className="h-96 w-full rounded-xl" data-testid="scenarios-grid-loading" />;
  }

  if (isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="size-5" />
        </span>
        <p className="text-sm font-medium">Scenarios could not be loaded.</p>
        <p className="text-2xs text-muted-foreground">{error?.message}</p>
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      </Card>
    );
  }

  if (rows.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <ShieldQuestion className="size-5" />
        </span>
        <p className="text-sm font-medium">No scenarios are registered.</p>
        <p className="text-2xs text-muted-foreground">
          The harness ships with 38 frozen scenarios - this should not be empty.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute start-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Code, title or probe"
            className="h-8 w-56 ps-8"
            aria-label="Search scenarios"
          />
          {searchQuery ? (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute end-2 top-1/2 -translate-y-1/2 text-muted-foreground"
              aria-label="Clear search"
            >
              <X className="size-3.5" />
            </button>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setStatusFilter(opt.value)}
              className={`rounded-full px-2.5 py-1 text-2xs font-medium transition ${
                statusFilter === opt.value
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/70'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <DataGrid
        table={table}
        recordCount={table.getFilteredRowModel().rows.length}
        listingKey={NO_COLUMN_PERSISTENCE}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No scenario matches this search and filter."
        onRowClick={handleRowClick}
      >
        <Card>
          <CardHeader className="py-3">
            <span className="text-2xs text-muted-foreground">
              Click a row to see the full field-level diff against the blessed baseline.
            </span>
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>
    </div>
  );
}

export default ScenariosGrid;
