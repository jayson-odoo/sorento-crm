'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
// PHASE 1 MOCK - swap for a real query hook when S8 (issue #67) lands.
import {
  MOCK_OBSERVATIONS,
  summarize,
  type TrackingObservationRow,
  type Verdict,
} from '../__mocks__/trackingValidation';

const VERDICT_LABEL: Record<Verdict, string> = {
  agree: 'Agree',
  disagree: 'Disagree',
  integration_led: 'Feed knew first',
};

/** Restrained colour, and never colour alone - the label carries the meaning too. */
function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const variant =
    verdict === 'agree' ? 'success' : verdict === 'disagree' ? 'destructive' : 'primary';
  return <Badge variant={variant as never}>{VERDICT_LABEL[verdict]}</Badge>;
}

export default function TrackingValidationList() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'observed_at', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');

  const rows = useMemo(() => {
    const q = searchQuery.trim().toUpperCase();
    if (!q) return MOCK_OBSERVATIONS;
    return MOCK_OBSERVATIONS.filter(
      (r) =>
        r.container_number.includes(q) ||
        r.field_label.toUpperCase().includes(q) ||
        r.source_label.toUpperCase().includes(q),
    );
  }, [searchQuery]);

  const summary = useMemo(() => summarize(rows), [rows]);

  const columns = useMemo<ColumnDef<TrackingObservationRow>[]>(
    () => [
      {
        accessorKey: 'container_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="Container" column={column} />
        ),
        cell: ({ row }) => (
          <span className="font-medium">{row.original.container_number}</span>
        ),
        size: 150,
        meta: { headerTitle: 'Container', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'field_label',
        header: ({ column }) => (
          <DataGridColumnHeader title="Field" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.field_label}>
            {row.original.field_label}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Field', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'sheet_value',
        header: ({ column }) => (
          <DataGridColumnHeader title="Sheet Value" column={column} />
        ),
        cell: ({ row }) =>
          row.original.sheet_value
            ? formatDate(new Date(row.original.sheet_value))
            : '-',
        size: 130,
        meta: { headerTitle: 'Sheet Value', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'observed_value',
        header: ({ column }) => (
          <DataGridColumnHeader title="Observed" column={column} />
        ),
        cell: ({ row }) =>
          row.original.observed_value ? (
            formatDate(new Date(row.original.observed_value))
          ) : (
            <span className="text-muted-foreground">Not observed</span>
          ),
        size: 130,
        meta: { headerTitle: 'Observed', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'verdict',
        header: ({ column }) => (
          <DataGridColumnHeader title="Verdict" column={column} />
        ),
        cell: ({ row }) => <VerdictBadge verdict={row.original.verdict} />,
        size: 150,
        meta: { headerTitle: 'Verdict', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'lag_days',
        header: ({ column }) => (
          <DataGridColumnHeader title="Lag (days)" column={column} />
        ),
        cell: ({ row }) =>
          row.original.lag_days === null ? (
            <span className="text-muted-foreground">-</span>
          ) : (
            <span className="font-medium tabular-nums">{row.original.lag_days}</span>
          ),
        size: 110,
        meta: { headerTitle: 'Lag (days)', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        accessorKey: 'source_label',
        header: ({ column }) => (
          <DataGridColumnHeader title="Source" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.source_label}>
            {row.original.source_label}
          </span>
        ),
        size: 160,
        meta: { headerTitle: 'Source', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'observed_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Observed At" column={column} />
        ),
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.observed_at),
        size: 160,
        meta: { headerTitle: 'Observed At', skeleton: <Skeleton className="h-4 w-28" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(rows.length / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    columnResizeMode: 'onChange',
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <div className="space-y-5">
      {/* The sentence that earns the cutover. Kept above the grid deliberately. */}
      <Card>
        <CardHeader className="block">
          <p className="text-sm text-muted-foreground">Validation to date</p>
          <p className="mt-1 text-base">
            Over <span className="font-semibold">{summary.containers}</span> containers and{' '}
            <span className="font-semibold">{summary.observations}</span> observations:{' '}
            <span className="font-semibold">{summary.agree_pct}%</span> agree,{' '}
            <span className="font-semibold">{summary.integration_led_pct}%</span> the feed knew
            first by an average of{' '}
            <span className="font-semibold">{summary.avg_lag_days}</span> days, and{' '}
            <span className="font-semibold">{summary.disagree_pct}%</span> disagree.
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Observed values are recorded for comparison only. They never overwrite what a person
            entered, and they are not shown on the packing list itself.
          </p>
        </CardHeader>
      </Card>

      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={false}
        standardToolbar={false}
        tableLayout={{ width: 'fixed', columnsVisibility: true, columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search container, field or source..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="ps-9 w-72"
                  />
                  {searchQuery && (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                      onClick={() => setSearchQuery('')}
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              exportConfig={{ filename: 'tracking_validation_export.xlsx' }}
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
    </div>
  );
}
