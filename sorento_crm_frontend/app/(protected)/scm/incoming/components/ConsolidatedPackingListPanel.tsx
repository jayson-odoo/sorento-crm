'use client';

import { useMemo } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { useMutation } from '@tanstack/react-query';
import { Download, LoaderCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { EM_DASH, fmtDate, fmtDecimal, fmtInt } from '../../lib/format';
import { useConsolidatedPackingList } from '../../hooks/useFulfilment';
import {
  downloadPackingListExport,
  type PackingListCompany,
  type PackingListFactory,
  type PackingListLine,
  type PackingListSplitRow,
  type PackingListTotals,
} from '../../services/fulfilmentService';

/**
 * The container as one list, in the order Ms Tee reads it: factory by factory, each with its
 * own subtotal, then the grand total and the company split.
 *
 * She used to build this file by hand from two or three supplier packing lists. What made it
 * work by hand was the remarks column - where the shipment differs from the loading plan that
 * supplier was sent - so that column is derived here rather than left for her to re-check.
 *
 * The not-packed rows sit UNDER their factory's grid rather than inside it: they are lines the
 * supplier did not ship, so giving them a quantity column would print a figure for something
 * that is not on the container.
 */

/** Shares the page with the allocation grid; an empty key opts out of column persistence. */
const NO_COLUMN_PERSISTENCE = '';

/** CBM is the figure the container is filled by, and four decimals is what the file carries. */
const CBM_DP = 4;

const numMeta = { headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' };

const COMPANIES: PackingListCompany[] = ['SORENTO', 'MOCHA'];

export function ConsolidatedPackingListPanel({ shipmentId }: { shipmentId: string | null }) {
  const list = useConsolidatedPackingList(shipmentId);
  const data = list.data;

  const exportList = useMutation({
    // The name the file falls back to is the container, never the shipment id: a workbook in
    // a downloads folder called after a UUID cannot be told from any other one.
    mutationFn: () =>
      downloadPackingListExport(
        shipmentId as string,
        data?.container_no ?? data?.shipment_number ?? 'container',
      ),
    onError: (e: Error) => toast.error(e.message),
  });

  if (!shipmentId) return null;

  const factories = data?.factories ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-sm font-semibold">
          Sorento packing list
          {data ? (
            <span className="ms-2 text-2xs font-normal text-muted-foreground">
              {fmtInt(data.total.lines)} lines
            </span>
          ) : null}
        </h3>
        <Button
          size="sm"
          variant="outline"
          onClick={() => exportList.mutate()}
          disabled={!factories.length || exportList.isPending}
        >
          {exportList.isPending ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
          ) : (
            <Download className="size-4" aria-hidden />
          )}
          Download .xlsx
        </Button>
      </CardHeader>

      <div className="space-y-4 px-4 pb-4">
        {list.isLoading ? (
          <Skeleton className="h-40 w-full rounded-lg" data-testid="packing-list-loading" />
        ) : list.isError ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            {list.error instanceof Error ? list.error.message : 'Failed to load the packing list.'}
          </p>
        ) : !data || !data.factories.length ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            No lines on this container yet.
          </p>
        ) : (
          <>
            {data.factories.map((factory) => (
              <FactorySection key={factoryKey(factory)} factory={factory} />
            ))}
            <PackingListFooter total={data.total} split={data.split} />
          </>
        )}
      </div>
    </Card>
  );
}

/** The Unassigned group has no supplier id, so the name is what keeps its key stable. */
function factoryKey(factory: PackingListFactory): string {
  return factory.supplier_id ?? `unassigned:${factory.supplier_name ?? ''}`;
}

function factoryLabel(factory: PackingListFactory): string {
  return factory.supplier_name ?? factory.supplier_code ?? 'Unassigned';
}

function FactorySection({ factory }: { factory: PackingListFactory }) {
  const columns = useMemo<ColumnDef<PackingListLine>[]>(
    () => [
      {
        accessorKey: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Model" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.product_code}>
            {row.original.product_code}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Model' },
      },
      {
        accessorKey: 'product_name',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.product_name ?? undefined}>
            {row.original.product_name ?? EM_DASH}
          </span>
        ),
        size: 260,
        meta: { headerTitle: 'Description' },
      },
      {
        accessorKey: 'brand',
        header: ({ column }) => <DataGridColumnHeader title="Logo" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.brand ?? undefined}>
            {row.original.brand ?? EM_DASH}
          </span>
        ),
        size: 120,
        meta: { headerTitle: 'Logo' },
      },
      {
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty),
        size: 100,
        meta: { headerTitle: 'Qty', ...numMeta },
      },
      {
        accessorKey: 'cartons',
        header: ({ column }) => <DataGridColumnHeader title="Ctn" column={column} />,
        cell: ({ row }) => fmtInt(row.original.cartons),
        size: 100,
        meta: { headerTitle: 'Ctn', ...numMeta },
      },
      {
        accessorKey: 'cbm',
        header: ({ column }) => <DataGridColumnHeader title="CBM" column={column} />,
        cell: ({ row }) => fmtDecimal(row.original.cbm, CBM_DP),
        size: 120,
        meta: { headerTitle: 'CBM', ...numMeta },
      },
      {
        id: 'remarks',
        header: ({ column }) => <DataGridColumnHeader title="Remarks" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0">
            {row.original.remarks ? (
              <span className="block truncate" title={row.original.remarks}>
                {row.original.remarks}
              </span>
            ) : null}
            {/* Ours, not the supplier's: kept apart in colour so the two are never confused. */}
            {row.original.discrepancies.map((d) => (
              <span
                key={d}
                className="block truncate text-amber-600 dark:text-amber-500"
                title={d}
              >
                {d}
              </span>
            ))}
            {!row.original.remarks && !row.original.discrepancies.length ? EM_DASH : null}
          </div>
        ),
        size: 320,
        enableSorting: false,
        meta: { headerTitle: 'Remarks' },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: factory.lines,
    columns,
    getRowId: (r) => r.line_id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <section className="space-y-2">
      <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
        <h4 className="truncate text-xs font-semibold" title={factoryLabel(factory)}>
          {factoryLabel(factory)}
        </h4>
        <div className="flex flex-wrap items-center gap-1.5">
          <NoticeChip factory={factory} />
          <SubtotalChip label="qty" value={fmtInt(factory.subtotal.qty)} />
          <SubtotalChip label="ctn" value={fmtInt(factory.subtotal.cartons)} />
          <SubtotalChip
            label="cbm"
            value={fmtDecimal(factory.subtotal.cbm, CBM_DP)}
            hint={cbmHint(factory.subtotal)}
          />
        </div>
      </div>

      <DataGrid
        table={table}
        recordCount={factory.lines.length}
        listingKey={NO_COLUMN_PERSISTENCE}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="Nothing from this factory on this container."
      >
        <div className="overflow-hidden rounded-lg border">
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      </DataGrid>

      {factory.not_packed.length ? (
        <ul className="rounded-lg border border-dashed px-3 py-2">
          {factory.not_packed.map((np) => (
            <li key={np.product_id} className="truncate py-0.5 text-2xs text-muted-foreground">
              <span className="font-medium">{np.product_code}</span> - not packed - loading plan
              asked {fmtInt(np.planned_qty)}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/**
 * Which loading plan the remarks column is comparing against, or that there is none.
 *
 * A discrepancy only means anything next to the plan it was measured from, and a factory that
 * was never sent one has an empty remarks column for a different reason than a factory that
 * packed its plan exactly.
 */
function NoticeChip({ factory }: { factory: PackingListFactory }) {
  const sent = factory.notice_sent_at ?? factory.notice_created_at;
  return (
    <Badge variant="secondary" size="sm" className="font-normal text-muted-foreground">
      {factory.notice_id ? `vs plan of ${fmtDate(sent)}` : 'no plan sent'}
    </Badge>
  );
}

function SubtotalChip({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: CbmHint | null;
}) {
  return (
    <Badge
      variant="secondary"
      size="sm"
      className="font-normal tabular-nums"
      title={hint?.title}
    >
      {value} {label}
      {hint ? <span className="text-muted-foreground">{hint.text}</span> : null}
    </Badge>
  );
}

interface CbmHint {
  text: string;
  title: string;
}

/**
 * Null when every line's volume is known, so the figure needs no qualification.
 *
 * A cbm sum over half the lines looks exactly like a cbm sum over all of them, and it is the
 * number a container gets planned against. Said where the figure is, not in a legend.
 */
function cbmHint(totals: PackingListTotals): CbmHint | null {
  const known = totals.cbm_known_lines;
  if (known === undefined || known === null || known >= totals.lines) return null;
  return {
    text: ` (${known}/${totals.lines} lines)`,
    title: `CBM known for ${known} of ${totals.lines} lines`,
  };
}

/**
 * Both company rows are always printed, zeros included: a split that shows one company reads
 * as the whole container belonging to it.
 */
function PackingListFooter({
  total,
  split,
}: {
  total: PackingListTotals;
  split: PackingListSplitRow[];
}) {
  const rows = COMPANIES.map(
    (company) =>
      split.find((s) => s.company === company) ?? {
        company,
        lines: 0,
        qty: 0,
        cartons: 0,
        cbm: 0,
      },
  );

  return (
    <div className="rounded-lg border bg-muted/40 px-3 py-2" data-testid="packing-list-footer">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold">
        <span>Total</span>
        <Figures totals={total} />
      </div>
      {rows.map((row) => (
        <div
          key={row.company}
          className="mt-1 flex flex-wrap items-center justify-between gap-2 text-2xs text-muted-foreground"
        >
          <span>{row.company}</span>
          <Figures totals={row} />
        </div>
      ))}
    </div>
  );
}

function Figures({ totals }: { totals: PackingListTotals }) {
  const hint = cbmHint(totals);
  return (
    <span className="tabular-nums" title={hint?.title}>
      {`${fmtInt(totals.qty)} qty · ${fmtInt(totals.cartons)} ctn · ${fmtDecimal(
        totals.cbm,
        CBM_DP,
      )} cbm`}
      {hint ? <span className="font-normal text-muted-foreground">{hint.text}</span> : null}
    </span>
  );
}

export default ConsolidatedPackingListPanel;
