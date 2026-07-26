'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Card, CardContent, CardFooter, CardHeader, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { AutoCountSourceBadge } from '@/components/common/AutoCountSourceBadge';
import { MirrorAnnotationCard } from '@/components/common/MirrorAnnotationCard';
import {
  useStockBalanceRuns,
  useStockBalanceRun,
  useAnnotateStockBalanceRun,
} from '../hooks/useStockBalance';
import type { StockBalanceRow } from '../types/stockBalance.types';
import { formatDateTime } from '@/lib/helpers';

function fmtNum(v: string | number | null): string {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(v);
  return Number.isNaN(n) ? String(v) : String(n);
}

export default function StockBalanceSnapshots() {
  const { data: runsData, isLoading: runsLoading } = useStockBalanceRuns();
  const runs = useMemo(() => runsData?.data ?? [], [runsData]);

  const [selectedRunId, setSelectedRunId] = useState<string>('');
  // Default to the newest run once runs load.
  useEffect(() => {
    if (!selectedRunId && runs.length > 0) setSelectedRunId(runs[0].id);
  }, [runs, selectedRunId]);

  const { data: run, isLoading: runLoading } = useStockBalanceRun(selectedRunId || null);
  const annotate = useAnnotateStockBalanceRun();

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });

  const runOptions = useMemo(
    () =>
      runs.map((r) => ({
        value: r.id,
        label: formatDateTime(new Date(r.captured_at)),
        description: `${r.row_count} rows${r.follow_up ? ' · flagged' : ''}`,
      })),
    [runs],
  );

  const columns = useMemo<ColumnDef<StockBalanceRow>[]>(
    () => [
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item" column={column} />,
        size: 160,
        cell: ({ row }) => <span className="font-medium">{row.original.item_code}</span>,
        meta: { headerTitle: 'Item' },
      },
      {
        accessorKey: 'product_name',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        size: 220,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.product_name || ''}>
            {row.original.product_name || <span className="text-muted-foreground">Unresolved</span>}
          </span>
        ),
        meta: { headerTitle: 'Product' },
      },
      {
        accessorKey: 'location_code',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        size: 120,
        cell: ({ row }) => row.original.location_code || '-',
        meta: { headerTitle: 'Location' },
      },
      {
        accessorKey: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UOM" column={column} />,
        size: 90,
        cell: ({ row }) => row.original.uom || '-',
        meta: { headerTitle: 'UOM' },
      },
      {
        accessorKey: 'batch_no',
        header: ({ column }) => <DataGridColumnHeader title="Batch" column={column} />,
        size: 110,
        cell: ({ row }) => row.original.batch_no || '-',
        meta: { headerTitle: 'Batch' },
      },
      {
        accessorKey: 'balance',
        header: ({ column }) => <DataGridColumnHeader title="Balance" column={column} />,
        size: 110,
        cell: ({ row }) => {
          const n = Number(row.original.balance);
          const neg = !Number.isNaN(n) && n < 0;
          return <span className={neg ? 'text-destructive font-medium' : ''}>{fmtNum(row.original.balance)}</span>;
        },
        meta: { headerTitle: 'Balance' },
      },
      {
        accessorKey: 'average_cost',
        header: ({ column }) => <DataGridColumnHeader title="Avg Cost" column={column} />,
        size: 110,
        cell: ({ row }) => fmtNum(row.original.average_cost),
        meta: { headerTitle: 'Avg Cost' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: run?.rows ?? [],
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <div className="space-y-6">
      {/* Run selector + provenance */}
      <Card>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between pt-6">
          <div className="space-y-2 sm:w-96">
            <Label>Snapshot run</Label>
            {runsLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : runs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No snapshots have synced yet.</p>
            ) : (
              <SearchableSelect
                value={selectedRunId}
                onChange={setSelectedRunId}
                options={runOptions}
                placeholder="Select a run…"
              />
            )}
          </div>
          <div className="flex items-center gap-3">
            {run && (
              <span className="text-sm text-muted-foreground">
                Captured {formatDateTime(new Date(run.captured_at))} · {run.row_count} rows
              </span>
            )}
            <AutoCountSourceBadge source="autocount" />
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Balance grid */}
        <div className="lg:col-span-2">
          <DataGrid table={table} recordCount={run?.rows?.length ?? 0} isLoading={runLoading}
            tableLayout={{ width: 'fixed', columnsResizable: true }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Stock balance</CardTitle>
              </CardHeader>
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
        </div>

        {/* Run annotation */}
        <div>
          {run ? (
            <MirrorAnnotationCard
              value={{ internal_note: run.internal_note, follow_up: run.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id: run.id, data: next })}
            />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Internal notes</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">Select a run to add a note.</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
