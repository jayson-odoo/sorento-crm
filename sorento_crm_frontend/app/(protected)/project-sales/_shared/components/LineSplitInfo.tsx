'use client';

import * as React from 'react';
import { flushSync } from 'react-dom';
import { Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
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

/** The split rows of one line: one per saved split, then the AutoCount extra row. */
function SplitRows({ view }: { view: LineSplitView }) {
  return (
    <>
      {view.rows.map((row, index) => {
        const sitsOn = sitsOnText(row);
        const was = wasText(row);
        return (
          <tr
            key={index}
            className={cn(
              'border-b border-border',
              row.changed && 'bg-amber-50 dark:bg-amber-950/40',
            )}
          >
            <td className="px-2 py-1.5 text-right align-top tabular-nums">
              {formatInquiryQty(row.qty)}
            </td>
            <td className="px-2 py-1.5 align-top">
              <span className="block">{splitDateText(row.delivery_date)}</span>
              {was ? (
                <span className="block text-xs text-muted-foreground">
                  {was}
                </span>
              ) : null}
            </td>
            <td className="px-2 py-1.5 align-top">
              <ChangePill change={row.change} />
              {/* B8: at 375 the Sits on column folds under Change. */}
              {sitsOn ? (
                <span className="block text-xs text-muted-foreground sm:hidden">
                  {sitsOn}
                </span>
              ) : null}
            </td>
            <td className="hidden px-2 py-1.5 align-top sm:table-cell">
              <span
                className="block truncate text-muted-foreground"
                title={sitsOn}
              >
                {sitsOn}
              </span>
            </td>
            <td className="px-2 py-1.5 align-top">
              <span className="block truncate" title={row.remark}>
                {row.remark}
              </span>
            </td>
          </tr>
        );
      })}
    </>
  );
}

function SplitTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table className="w-full table-fixed border-collapse text-sm">
        <colgroup>
          <col className="w-16 sm:w-20" />
          <col className="w-28 sm:w-32" />
          <col className="w-32 sm:w-40" />
          <col className="hidden sm:table-column sm:w-52" />
          <col className="w-32 sm:w-auto" />
        </colgroup>
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="px-2 py-1.5 text-right font-medium">Qty</th>
            <th className="px-2 py-1.5 font-medium">Delivery date</th>
            <th className="px-2 py-1.5 font-medium">Change</th>
            <th className="hidden px-2 py-1.5 font-medium sm:table-cell">
              Sits on
            </th>
            <th className="px-2 py-1.5 font-medium">Remark</th>
          </tr>
        </thead>
        {children}
      </table>
    </div>
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
  const count = view.rows.filter((row) => row.sits_on !== 'extra').length;
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
            <SplitTable>
              <tbody>
                <SplitRows view={view} />
              </tbody>
              <tfoot>
                <tr className="text-sm">
                  <td className="px-2 py-1.5 text-right font-medium tabular-nums">
                    {formatInquiryQty(view.total_qty)}
                  </td>
                  <td colSpan={4} className="px-2 py-1.5 text-muted-foreground">
                    {baseText(view)}
                  </td>
                </tr>
              </tfoot>
            </SplitTable>
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
    sorted.length > 0 ? `${sorted.length} split lines` : null,
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
          <SplitTable>
            {sorted.map((line, index) => (
              <tbody key={`${line.lineNo ?? ''}-${index}`}>
                <tr
                  className="border-b border-border bg-muted/50"
                  aria-label={`Line ${line.lineNo ?? ''} ${line.itemCode ?? ''}`}
                >
                  <th
                    scope="rowgroup"
                    colSpan={5}
                    className="px-2 py-1.5 text-left font-normal"
                  >
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-medium">{`Line ${line.lineNo ?? ''} ${line.itemCode ?? ''}`}</span>
                      <StatusBadge view={line.view} />
                      <span className="text-xs text-muted-foreground">
                        {baseText(line.view)}
                      </span>
                    </span>
                  </th>
                </tr>
                <SplitRows view={line.view} />
              </tbody>
            ))}
          </SplitTable>
        )}
      </DialogContent>
    </Dialog>
  );
}
