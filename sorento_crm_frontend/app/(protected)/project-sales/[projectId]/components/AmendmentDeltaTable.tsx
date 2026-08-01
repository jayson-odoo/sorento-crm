'use client';

import * as React from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ArrowRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { AmendmentDeltaRow } from '../../_shared/types/projectSalesOrder.types';
import { fieldLabel } from './AmendmentDeltaSummary';
import { formatMoney, formatQty } from './SalesOrderMoney';

const DATE_FIELDS = new Set(['delivery_date', 'schedule_date']);
const QTY_FIELDS = new Set(['qty', 'quantity']);
const MONEY_FIELDS = new Set(['unit_price', 'amount']);

/** Verb colouring: a cancellation must not look like a reschedule. */
const VERB_TONE: Record<string, 'secondary' | 'destructive' | 'warning' | 'primary'> = {
  ORDER: 'primary',
  'RESERVE & ORDER': 'primary',
  ADVANCE: 'secondary',
  DELAY: 'secondary',
  'CHANGE SO NO': 'warning',
  'CANCEL BALANCE': 'destructive',
};

export function formatDeltaValue(field: string, value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'None';
  if (DATE_FIELDS.has(field)) return formatDateInMalaysia(value) || value;
  if (QTY_FIELDS.has(field)) return formatQty(value);
  if (MONEY_FIELDS.has(field)) return formatMoney(value);
  return value;
}

export function AmendmentDeltaTable({ rows }: { rows: AmendmentDeltaRow[] }) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [verb, setVerb] = React.useState('');
  const [nonDateOnly, setNonDateOnly] = React.useState(false);

  const verbOptions = React.useMemo(() => {
    const seen = new Map<string, number>();
    rows.forEach((row) => seen.set(row.verb, (seen.get(row.verb) ?? 0) + 1));
    return [
      { value: '', label: 'All actions' },
      ...[...seen.entries()].map(([value, count]) => ({ value, label: `${value} (${count})` })),
    ];
  }, [rows]);

  const filtered = React.useMemo(
    () =>
      rows.filter((row) => {
        if (verb && row.verb !== verb) return false;
        if (nonDateOnly && DATE_FIELDS.has(row.field)) return false;
        return true;
      }),
    [nonDateOnly, rows, verb],
  );

  const columns = React.useMemo<ColumnDef<AmendmentDeltaRow>[]>(
    () => [
      {
        id: 'verb',
        header: ({ column }) => <DataGridColumnHeader title="Action" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={VERB_TONE[row.original.verb] ?? 'secondary'}
            appearance="light"
            size="sm"
            className="whitespace-nowrap"
          >
            {row.original.verb}
          </Badge>
        ),
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'Action', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'line_no',
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.line_no}</span>,
        size: 70,
        minSize: 56,
        meta: { headerTitle: '#', skeleton: <Skeleton className="h-4 w-6" /> },
      },
      {
        id: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const code = row.original.product_code || 'Not resolved';
          return (
            <span className="block truncate font-medium" title={code}>
              {code}
            </span>
          );
        },
        size: 180,
        minSize: 130,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const text = row.original.description || '—';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 280,
        minSize: 150,
        meta: { headerTitle: 'Description', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'field',
        header: ({ column }) => <DataGridColumnHeader title="Field" column={column} />,
        cell: ({ row }) => {
          const text = fieldLabel(row.original.field);
          return (
            <span className="block truncate capitalize" title={text}>
              {text}
            </span>
          );
        },
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Field', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'change',
        header: ({ column }) => <DataGridColumnHeader title="Before and after" column={column} />,
        cell: ({ row }) => {
          const before = formatDeltaValue(row.original.field, row.original.from_value);
          const after = formatDeltaValue(row.original.field, row.original.to_value);
          return (
            <span
              className="flex min-w-0 items-center gap-1.5 tabular-nums"
              title={`${before} to ${after}`}
            >
              <span className="truncate text-muted-foreground line-through">{before}</span>
              <ArrowRight className="size-3.5 shrink-0" aria-hidden />
              <span className="truncate font-medium">{after}</span>
            </span>
          );
        },
        size: 240,
        minSize: 160,
        meta: { headerTitle: 'Before and after', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate tabular-nums" title={row.original.qty ?? ''}>
            {row.original.qty ? formatQty(row.original.qty) : '—'}
          </span>
        ),
        size: 90,
        minSize: 70,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'phase',
        header: ({ column }) => <DataGridColumnHeader title="Phase" column={column} />,
        cell: ({ row }) => {
          const from = row.original.phase_label_from || 'Unlabeled';
          const to = row.original.phase_label_to || 'Unlabeled';
          const text = from === to ? from : `${from} to ${to}`;
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 180,
        minSize: 130,
        meta: { headerTitle: 'Phase', skeleton: <Skeleton className="h-4 w-24" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: filtered,
    pageCount: Math.ceil(filtered.length / pagination.pageSize) || 0,
    getRowId: (row) => `${row.so_line_id}:${row.field}`,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={filtered.length}
      isLoading={false}
      listingKey="projects.projects.view::project-so-amendment-delta"
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 break-words">
              <p className="text-sm font-medium">Line by line</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {`${filtered.length.toLocaleString()} of ${rows.length.toLocaleString()} rows`}
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="w-full sm:w-52">
                <SearchableSelect
                  value={verb}
                  onChange={(next) => {
                    setVerb(next);
                    setPagination((current) => ({ ...current, pageIndex: 0 }));
                  }}
                  options={verbOptions}
                  placeholder="All actions"
                  size="sm"
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="delta-non-date"
                  checked={nonDateOnly}
                  onCheckedChange={(next) => {
                    setNonDateOnly(next === true);
                    setPagination((current) => ({ ...current, pageIndex: 0 }));
                  }}
                />
                <Label htmlFor="delta-non-date" className="text-xs">
                  Hide date moves
                </Label>
              </div>
            </div>
          </div>
        </CardHeader>

        <CardTable>
          {rows.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <h3 className="text-sm font-semibold">No differences</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                The two versions agree line for line.
              </p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-6 py-10 text-center text-sm text-muted-foreground">
              No rows match these filters.
            </div>
          ) : (
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardTable>

        {filtered.length > pagination.pageSize && (
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}
