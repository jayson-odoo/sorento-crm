'use client';

import * as React from 'react';
import { flushSync } from 'react-dom';
import { Info } from 'lucide-react';
import {
  type ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGrid, DataGridContainer } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatInquiryQty } from '../lib/orderInquiryWorklist';
import type {
  LineSplitView,
  LineSplitViewRow,
} from '../types/orderInquiry.types';
import { OrderInquiryVerbPill } from './OrderInquiryVerbPill';

/**
 * OI-SPLIT-VIEW (UAC B1 to B4, B8, D1): the one split chip + (i) popup the Sales Order and
 * Order Inquiry Lines tabs render, and the whole-order popup the planning board, SO and OI
 * gears open. Both read the server's `split_view` (`LineSplitService.split_views`), so the
 * two pages cannot disagree; opening a popup makes no request of its own.
 */

/** `20/10/2026` from an ISO date; empty for none. */
export function splitDateText(iso: string | null | undefined): string {
  return iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '';
}

const STATUS: Record<
  LineSplitView['status'],
  { label: string; variant: 'success' | 'warning' | 'secondary' }
> = {
  confirmed: { label: 'Confirmed', variant: 'success' },
  saved: { label: 'Saved, not confirmed', variant: 'warning' },
  autocount_changed: { label: 'AutoCount changed', variant: 'secondary' },
};

function StatusBadge({ view }: { view: LineSplitView }) {
  const own = STATUS[view.status] ?? STATUS.saved;
  return (
    <Badge
      variant={own.variant}
      appearance="light"
      size="sm"
      className="shrink-0"
    >
      {own.label}
    </Badge>
  );
}

/** "revision 3, 19/10/2026" beside a confirmed plan; nothing otherwise. */
function confirmedText(view: LineSplitView): string {
  if (view.status !== 'confirmed' || view.revision_no == null) return '';
  const on = splitDateText(view.confirmed_on);
  return on
    ? `revision ${view.revision_no}, ${on}`
    : `revision ${view.revision_no}`;
}

function atText(qty: string, iso: string | null): string {
  const date = splitDateText(iso);
  return date ? `${formatInquiryQty(qty)} @ ${date}` : formatInquiryQty(qty);
}

/** "AutoCount 417 @ 20/10/2026, now 14 @ 20/09/2026". */
function baseText(view: LineSplitView): string {
  return `AutoCount ${atText(view.base_qty, view.base_date)}, now ${atText(
    view.now_qty,
    view.now_date,
  )}`;
}

/** Where a row sits, in words (UAC B2). */
function sitsOnText(row: LineSplitViewRow): string {
  if (row.is_cancel) return '';
  if (row.sits_on === 'new') return 'New line (not in AutoCount yet)';
  const line =
    row.sits_on_line_no != null ? `line ${row.sits_on_line_no}` : 'line';
  return row.sits_on === 'extra' ? `${line} (AutoCount extra)` : line;
}

function wasText(row: LineSplitViewRow): string {
  if (!row.changed) return '';
  if (row.was_qty && row.was_date) {
    return `was ${formatInquiryQty(row.was_qty)} @ ${splitDateText(row.was_date)}`;
  }
  if (row.was_date) return `was ${splitDateText(row.was_date)}`;
  if (row.was_qty) return `was ${formatInquiryQty(row.was_qty)}`;
  return '';
}

function ChangePill({ change }: { change: string }) {
  return (
    <OrderInquiryVerbPill
      verb={change === 'CANCEL BALANCE' ? 'CANCEL_BALANCE' : change}
    />
  );
}

/** Tailwind's `sm` is 640px: below it Sits on folds under Change (UAC B8). */
const BELOW_SM_QUERY = '(max-width: 639px)';

function useBelowSm(): boolean {
  const [below, setBelow] = React.useState(false);
  React.useEffect(() => {
    const mql = window.matchMedia(BELOW_SM_QUERY);
    const update = () => setBelow(mql.matches);
    update();
    mql.addEventListener?.('change', update);
    return () => mql.removeEventListener?.('change', update);
  }, []);
  return below;
}

/** The chip's N (UAC B1, B7a): the line's split rows, the AutoCount extra row not counted. */
export function splitCount(view: LineSplitView | null | undefined): number {
  return view ? view.rows.filter((row) => row.sits_on !== 'extra').length : 0;
}

const CHANGED_ROW = 'bg-amber-50 dark:bg-amber-950/40';

/**
 * The split rows of one line on the shared DataGrid (UAC B2, B5a): one per saved split in
 * the saved order, then the AutoCount extra row. Not sortable (the saved order is the
 * plan's), no column persistence (`listingKey={null}`: a popup's columns are not a personal
 * preference), unbounded so the dialog body owns the scroll.
 */
function SplitGrid({ view }: { view: LineSplitView }) {
  const narrow = useBelowSm();
  const columns = React.useMemo<ColumnDef<LineSplitViewRow>[]>(
    () => [
      {
        id: 'qty',
        accessorFn: (row) => Number(row.qty),
        header: ({ column }) => (
          <DataGridColumnHeader title="Qty" column={column} />
        ),
        cell: ({ row }) => formatInquiryQty(row.original.qty),
        size: 72,
        enableSorting: false,
        meta: { headerTitle: 'Qty', cellClassName: 'text-right' },
      },
      {
        id: 'delivery_date',
        accessorFn: (row) => row.delivery_date ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Delivery date" column={column} />
        ),
        cell: ({ row }) => {
          const was = wasText(row.original);
          return (
            <>
              <span className="block">
                {splitDateText(row.original.delivery_date)}
              </span>
              {was ? (
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={was}
                >
                  {was}
                </span>
              ) : null}
            </>
          );
        },
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Delivery date' },
      },
      {
        id: 'change',
        accessorFn: (row) => row.change,
        header: ({ column }) => (
          <DataGridColumnHeader title="Change" column={column} />
        ),
        cell: ({ row }) => {
          const sitsOn = narrow ? sitsOnText(row.original) : '';
          return (
            <>
              <ChangePill change={row.original.change} />
              {/* B8: at 375 the Sits on column folds under Change. */}
              {sitsOn ? (
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={sitsOn}
                >
                  {sitsOn}
                </span>
              ) : null}
            </>
          );
        },
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Change' },
      },
      {
        id: 'sits_on',
        accessorFn: (row) => sitsOnText(row),
        header: ({ column }) => (
          <DataGridColumnHeader title="Sits on" column={column} />
        ),
        cell: ({ row }) => {
          const sitsOn = sitsOnText(row.original);
          return (
            <span
              className="block truncate text-muted-foreground"
              title={sitsOn}
            >
              {sitsOn}
            </span>
          );
        },
        size: 210,
        enableSorting: false,
        meta: { headerTitle: 'Sits on' },
      },
      {
        id: 'remark',
        accessorFn: (row) => row.remark,
        header: ({ column }) => (
          <DataGridColumnHeader title="Remark" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.remark}>
            {row.original.remark}
          </span>
        ),
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Remark' },
      },
    ],
    [narrow],
  );
  const table = useReactTable({
    columns,
    data: view.rows,
    getRowId: (_row, index) => String(index),
    getCoreRowModel: getCoreRowModel(),
    state: { columnVisibility: { sits_on: !narrow } },
    columnResizeMode: 'onChange',
  });
  return (
    <DataGridContainer>
      <DataGrid
        table={table}
        recordCount={view.rows.length}
        isLoading={false}
        listingKey={null}
        rowClassName={(row) => (row.changed ? CHANGED_ROW : undefined)}
        tableLayout={{
          width: 'fixed',
          columnsResizable: true,
          dense: true,
          scrollerMaxHeight: false,
        }}
      >
        <DataGridTable />
      </DataGrid>
    </DataGridContainer>
  );
}

export interface LineSplitInfoProps {
  lineNo: number | null | undefined;
  itemCode: string | null | undefined;
  soNumber: string | null | undefined;
  /** The OI page names its inquiry: "<OI number> line <n>" under the title. */
  oiNumber?: string | null;
  /** The line's purchasing State (the OI page passes its own pill). */
  purchasingState?: React.ReactNode;
  po?: string | null;
  view: LineSplitView | null | undefined;
}

/** "Split N" and the (i) button; nothing for a line without splits (UAC B1). */
export function LineSplitInfo({
  lineNo,
  itemCode,
  soNumber,
  oiNumber,
  purchasingState,
  po,
  view,
}: LineSplitInfoProps) {
  const [open, setOpen] = React.useState(false);
  const triggerRef = React.useRef<HTMLButtonElement | null>(null);
  // Escape and Close take the popup down on the same frame and hand focus straight back
  // to the (i) button (UAC B8), rather than after the exit animation.
  const close = React.useCallback((next: boolean) => {
    if (next) return;
    flushSync(() => setOpen(false));
    triggerRef.current?.focus();
  }, []);
  if (!view) return null;
  const count = splitCount(view);
  const confirmed = confirmedText(view);
  const sub = [
    soNumber,
    oiNumber ? `${oiNumber} line ${lineNo ?? ''}`.trim() : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <span className="inline-flex min-w-0 items-center gap-0.5">
      <Badge
        variant="secondary"
        appearance="light"
        size="sm"
        className="shrink-0"
      >
        {`Split ${count}`}
      </Badge>
      <Button
        ref={triggerRef}
        type="button"
        mode="icon"
        variant="ghost"
        size="sm"
        className="size-6 shrink-0"
        aria-label={`Show the splits of line ${lineNo ?? ''}`.trim()}
        aria-haspopup="dialog"
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <Info className="size-3.5" aria-hidden />
      </Button>
      {open ? (
        <Dialog open onOpenChange={close}>
          <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col">
            <DialogHeader>
              <DialogTitle>{`Line ${lineNo ?? ''} ${itemCode ?? ''}: split`}</DialogTitle>
              {sub ? <DialogDescription>{sub}</DialogDescription> : null}
            </DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <StatusBadge view={view} />
                {confirmed ? (
                  <span className="text-muted-foreground">{confirmed}</span>
                ) : null}
                {purchasingState ? (
                  <span className="inline-flex items-center gap-1">
                    <span className="text-muted-foreground">Purchasing</span>
                    {purchasingState}
                  </span>
                ) : null}
                {po ? (
                  <span className="text-muted-foreground">{`PO ${po}`}</span>
                ) : null}
              </div>
              <SplitGrid view={view} />
              {/* B5a: the total is a line of text under the grid, never a table row. */}
              <p className="text-sm text-muted-foreground">
                {`Total ${formatInquiryQty(view.total_qty)} · ${baseText(view)}`}
              </p>
            </div>
          </DialogContent>
        </Dialog>
      ) : null}
    </span>
  );
}

export interface OrderSplitLine {
  lineNo: number | null | undefined;
  itemCode: string | null | undefined;
  view: LineSplitView;
}

/** UAC D1: every split line of one order in one popup, a group per line in line order. */
export function OrderSplitsDialog({
  title,
  subtitle,
  lines,
  open,
  onOpenChange,
}: {
  title: string;
  subtitle?: string | null;
  lines: OrderSplitLine[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const sorted = React.useMemo(
    () =>
      [...lines].sort(
        (a, b) =>
          (a.lineNo ?? Number.POSITIVE_INFINITY) -
          (b.lineNo ?? Number.POSITIVE_INFINITY),
      ),
    [lines],
  );
  const sub = [
    subtitle,
    sorted.length > 0
      ? `${sorted.length} ${sorted.length === 1 ? 'split line' : 'split lines'}`
      : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {sub ? <DialogDescription>{sub}</DialogDescription> : null}
        </DialogHeader>
        {sorted.length === 0 ? (
          <div className="py-6 text-center">
            <p className="text-sm font-medium">No split lines</p>
            <p className="text-sm text-muted-foreground">
              Every line ships as AutoCount has it.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {sorted.map((line, index) => {
              const heading =
                `Line ${line.lineNo ?? ''} ${line.itemCode ?? ''}`.trim();
              return (
                // B5a: one section per split line, its heading above its own DataGrid.
                <section
                  key={`${line.lineNo ?? ''}-${index}`}
                  aria-label={heading}
                  className="flex flex-col gap-2"
                >
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <h3 className="text-sm font-medium">{heading}</h3>
                    <StatusBadge view={line.view} />
                    <span className="text-xs text-muted-foreground">
                      {baseText(line.view)}
                    </span>
                  </div>
                  <SplitGrid view={line.view} />
                </section>
              );
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
