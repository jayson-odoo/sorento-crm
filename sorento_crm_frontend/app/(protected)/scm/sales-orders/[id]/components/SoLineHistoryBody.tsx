'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { type ColumnDef } from '@tanstack/react-table';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { DrillTable, RIGHT, TOTAL_LABEL } from '../../../components/PlanRowDialog';
import { EM_DASH, fmtDate, fmtInt } from '../../../lib/format';
import { MATCH_LABEL } from '../../../lib/autocountCancel';
import type {
  SalesOrderDeliveries,
  SalesOrderLine,
  SoLineCancelRow,
  SoLineDeliveryRow,
} from '../../../types/scm.types';

/**
 * The lightbox the truck button on a sales-order line opens (SO-DELIVERIES-VIEW): the line's
 * figures, the DOs delivered against it and the Cancel SO documents that cancelled it, plus the
 * product's "not tied to one line" block when the SO holds the product on several lines.
 */

const dash = <span className="text-muted-foreground">{EM_DASH}</span>;

function textCell(value: string | null | undefined) {
  return value ? value : dash;
}

function plural(n: number, one: string, many: string) {
  if (n === 0) return null;
  return `${fmtInt(n)} ${n === 1 ? one : many}`;
}

function Block({ title, count, children }: { title: string; count: string | null; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-sm font-semibold">{title}</span>
        {count ? <span className="text-xs text-muted-foreground">{count}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-24 flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium tabular-nums">{value}</span>
    </div>
  );
}

/** A DO row with the SKU it delivered - only the Delivery tab's all-lines list reads `sku`. */
export type SoDeliveryListRow = SoLineDeliveryRow & { sku?: string };

const SKU_COLUMN: ColumnDef<SoDeliveryListRow> = {
  id: 'sku',
  header: 'SKU',
  cell: ({ row }) =>
    row.original.sku ? (
      <span className="block truncate" title={row.original.sku}>
        {row.original.sku}
      </span>
    ) : (
      dash
    ),
  size: 150,
};

const LOCATION_COLUMN: ColumnDef<SoDeliveryListRow> = {
  id: 'location',
  header: 'Location',
  cell: ({ row }) => textCell(row.original.location),
  size: 110,
};

const STATUS_COLUMN: ColumnDef<SoDeliveryListRow> = {
  id: 'status',
  header: 'Status',
  cell: ({ row }) =>
    row.original.status ? <Badge status={row.original.status}>{row.original.status}</Badge> : dash,
  size: 210,
};

/** The deliveries read failed: say so, with a retry (R7). The lightbox and the Delivery tab. */
export function DeliveriesLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <Alert variant="destructive">
      <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
        <span>Could not load deliveries.</span>
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function DeliveriesTable({
  rows,
  canOpenDo,
  emptyMessage,
  withSku = false,
  onPage = false,
}: {
  rows: SoDeliveryListRow[];
  canOpenDo: boolean;
  emptyMessage: string;
  /** DO-SO-LINK-SURFACE R3: the Delivery tab lists every line's DOs, so it names the SKU. */
  withSku?: boolean;
  /** On a page rather than inside a lightbox: the grid keeps its own bounded scroller. */
  onPage?: boolean;
}) {
  const total = rows.reduce((sum, r) => sum + Number(r.qty ?? 0), 0);
  const columns = useMemo<ColumnDef<SoDeliveryListRow>[]>(
    () => [
      {
        id: 'do_number',
        header: 'DO no.',
        cell: ({ row }) =>
          canOpenDo ? (
            <Link
              href={`/order-management/orders/${row.original.order_id}`}
              className="font-medium text-primary hover:underline"
              title={`Open ${row.original.do_number}`}
            >
              {row.original.do_number}
            </Link>
          ) : (
            row.original.do_number
          ),
        footer: () => TOTAL_LABEL,
        size: 150,
      },
      { id: 'do_date', header: 'DO date', cell: ({ row }) => fmtDate(row.original.do_date), size: 130 },
      // The lightbox reads Location, Status; the Delivery tab's list (mock v2 Panel D) reads
      // Status, SKU, Location, with Status narrowed so Qty is not clipped at 1280.
      ...(withSku
        ? [{ ...STATUS_COLUMN, size: 170 }, SKU_COLUMN, LOCATION_COLUMN]
        : [LOCATION_COLUMN, STATUS_COLUMN]),
      {
        id: 'actual_delivery_date',
        header: 'Actual delivery',
        cell: ({ row }) => (row.original.actual_delivery_date ? fmtDate(row.original.actual_delivery_date) : dash),
        size: 140,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => fmtInt(row.original.qty),
        footer: () => fmtInt(total),
        size: 80,
        meta: RIGHT,
      },
    ],
    [canOpenDo, total, withSku],
  );
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  return (
    <DrillTable
      columns={columns}
      rows={rows}
      getRowId={(r, i) => `${r.do_number}-${i}`}
      emptyMessage={emptyMessage}
      scrollerMaxHeight={onPage ? undefined : false}
    />
  );
}

function CancelsTable({ rows, emptyMessage }: { rows: SoLineCancelRow[]; emptyMessage: string }) {
  const total = rows.reduce((sum, r) => sum + Number(r.qty ?? 0), 0);
  const anyKnown = rows.some((r) => r.qty != null);
  const columns = useMemo<ColumnDef<SoLineCancelRow>[]>(
    () => [
      { id: 'doc_no', header: 'Cancel SO no.', cell: ({ row }) => row.original.doc_no, footer: () => TOTAL_LABEL, size: 150 },
      { id: 'doc_date', header: 'Date', cell: ({ row }) => fmtDate(row.original.doc_date), size: 130 },
      { id: 'location', header: 'Location', cell: ({ row }) => textCell(row.original.location), size: 110 },
      {
        id: 'match_reason',
        header: 'Matched by',
        cell: ({ row }) => textCell(MATCH_LABEL[row.original.match_reason ?? '']),
        size: 190,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => (row.original.qty == null ? dash : fmtInt(row.original.qty)),
        footer: () => (anyKnown ? fmtInt(total) : EM_DASH),
        size: 80,
        meta: RIGHT,
      },
    ],
    [total, anyKnown],
  );
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  return (
    <DrillTable
      columns={columns}
      rows={rows}
      getRowId={(r, i) => `${r.doc_no}-${i}`}
      emptyMessage={emptyMessage}
      scrollerMaxHeight={false}
    />
  );
}

/**
 * DO-SO-LINK-SURFACE R3: every DO row under the SO - each line's own and each "not tied to one
 * line" group's - with its SKU, oldest first (DO date, then DO no.), for the Delivery tab.
 */
export function soDeliveryRows(
  lines: Pick<SalesOrderLine, 'id' | 'sku'>[],
  data: SalesOrderDeliveries | undefined,
): SoDeliveryListRow[] {
  if (!data) return [];
  const skuOf = new Map(lines.map((l) => [l.id, l.sku]));
  const rows: SoDeliveryListRow[] = [
    ...data.lines.flatMap((l) => l.deliveries.map((d) => ({ ...d, sku: skuOf.get(l.line_id) }))),
    ...data.groups.flatMap((g) => g.deliveries.map((d) => ({ ...d, sku: g.sku }))),
  ];
  return rows.sort(
    (a, b) =>
      (a.do_date ?? '9999').localeCompare(b.do_date ?? '9999') || a.do_number.localeCompare(b.do_number),
  );
}

export function SoLineHistoryBody({
  line,
  data,
  isLoading,
  onRetry,
  canOpenDo,
}: {
  line: SalesOrderLine;
  data: SalesOrderDeliveries | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  canOpenDo: boolean;
}) {
  const strip = (
    <div className="flex flex-wrap gap-x-6 gap-y-2">
      <Figure label="Ordered" value={fmtInt(line.qty_ordered)} />
      <Figure label="Delivered" value={fmtInt(line.qty_delivered)} />
      <Figure label="Cancelled" value={fmtInt(line.qty_cancelled ?? 0)} />
      <Figure label="Outstanding" value={fmtInt(line.outstanding_qty)} />
      <Figure label="Location" value={line.warehouse_code || EM_DASH} />
      <Figure label="Delivery date" value={fmtDate(line.required_date)} />
    </div>
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        {strip}
        <SectionSkeleton />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        {strip}
        <DeliveriesLoadError onRetry={onRetry} />
      </div>
    );
  }

  const own = data.lines.find((l) => l.line_id === line.id);
  const deliveries = own?.deliveries ?? [];
  const cancels = own?.cancels ?? [];
  const group = data.groups.find((g) => g.line_ids.includes(line.id));

  return (
    <div className="space-y-6">
      {strip}
      <Block title="Delivered" count={plural(deliveries.length, 'DO line', 'DO lines')}>
        <DeliveriesTable rows={deliveries} canOpenDo={canOpenDo} emptyMessage="No DO in the CRM for this line." />
      </Block>
      <Block title="Cancelled" count={plural(cancels.length, 'Cancel SO line', 'Cancel SO lines')}>
        <CancelsTable rows={cancels} emptyMessage="No Cancel SO for this line." />
      </Block>
      {group ? (
        <section className="space-y-4 rounded-lg border p-4">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-semibold">{`${group.sku} on this SO, not tied to one line`}</span>
            <span className="text-xs text-muted-foreground">{`· ${group.line_ids.length} lines`}</span>
          </div>
          <Block title="Delivered" count={plural(group.deliveries.length, 'DO line', 'DO lines')}>
            <DeliveriesTable
              rows={group.deliveries}
              canOpenDo={canOpenDo}
              emptyMessage="No DO in the CRM for this product here."
            />
          </Block>
          <Block title="Cancelled" count={plural(group.cancels.length, 'Cancel SO line', 'Cancel SO lines')}>
            <CancelsTable rows={group.cancels} emptyMessage="No Cancel SO for this product here." />
          </Block>
        </section>
      ) : null}
    </div>
  );
}

export default SoLineHistoryBody;
