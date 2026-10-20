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
import { ListLoadFailure } from '@/components/common/ListLoadFailure';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import {
  LineSplitSheet,
  type SheetHandlers,
} from '../../fulfilment-planning/components/LineSplitSheet';
import {
  formatSplitDate,
  fromPayload,
  sortLines,
  type SplitLine,
} from '../../fulfilment-planning/lib/lineSplitModel';
import type { LineSplitView } from '../types/orderInquiry.types';
import type { LineSplitsPayload } from '../types/lineSplit.types';

/**
 * OI-SPLIT-VIEW (UAC B1, B8, D1, E): the one split chip + (i) popup the Sales Order and
 * Order Inquiry Lines tabs render, and the whole-order popup the planning board, SO and OI
 * gears open. The chip reads the line's `split_view`; both popups draw the split delivery
 * edit sheet read-only (`LineSplitSheet readOnly`, UAC E1, E2) off the `LineSplitService.read`
 * payload, turned into the sheet model by the edit dialog's own `fromPayload` / `sortLines`.
 */

/** `20/10/2026` from an ISO date; empty for none. */
export function splitDateText(iso: string | null | undefined): string {
  return iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '';
}

/** The chip's N (UAC B1, B7a): the line's split rows, the AutoCount extra row not counted. */
export function splitCount(view: LineSplitView | null | undefined): number {
  return view ? view.rows.filter((row) => row.sits_on !== 'extra').length : 0;
}

const NO_LINE_IDS: ReadonlySet<string> = new Set();
const noop = () => {};
/** The read-only sheet calls none of them (UAC E2). */
const INERT_HANDLERS: SheetHandlers = {
  open: noop,
  qty: noop,
  date: noop,
  remark: noop,
  add: noop,
  remove: noop,
  fieldBlur: noop,
};

/** The sheet's lines in its own order (item, location, base date, line no). */
function sheetLinesOf(payload: LineSplitsPayload): SplitLine[] {
  return sortLines(fromPayload(payload));
}

/** Lines another line's split sits on (variant B: the moved split is drawn under them). */
function receivingLineIds(lines: SplitLine[]): Set<string> {
  const out = new Set<string>();
  for (const line of lines) {
    for (const split of line.splits) {
      if (
        !split.isCancel &&
        split.sitsOnLineId &&
        split.sitsOnLineId !== line.lineId
      )
        out.add(split.sitsOnLineId);
    }
  }
  return out;
}

/**
 * UAC E3: these lines, and the lines their own splits moved onto (so every split of them
 * shows, under the line it sits on), in the sheet's order.
 */
function linesWithLanding(
  all: SplitLine[],
  ownIds: ReadonlySet<string>,
): SplitLine[] {
  const landing = new Set<string>();
  for (const line of all) {
    if (!ownIds.has(line.lineId)) continue;
    for (const split of line.splits) {
      if (!split.isCancel && split.sitsOnLineId) landing.add(split.sitsOnLineId);
    }
  }
  return all.filter(
    (line) => ownIds.has(line.lineId) || landing.has(line.lineId),
  );
}

/** UAC E4: split-edited (A1, B3), the server's own status, the same the board flag reads. */
function isSplitEdited(
  payload: LineSplitsPayload,
  lineIds: ReadonlySet<string>,
): boolean {
  return payload.lines.some(
    (line) => lineIds.has(line.line_id) && line.split_view?.status === 'saved',
  );
}

/** UAC E4: the edit dialog's status line, "Confirmed dd/mm/yyyy" and one badge. */
function SheetStatus({
  payload,
  edited,
}: {
  payload: LineSplitsPayload;
  edited: boolean;
}) {
  if (!payload.confirmed_at && !edited) return null;
  return (
    <div className="flex min-h-8 flex-wrap items-center gap-x-3.5 gap-y-1 border-b border-border px-4 py-1.5 text-xs">
      {payload.confirmed_at ? (
        <span className="font-medium text-success">
          {`Confirmed ${formatSplitDate(payload.confirmed_at.slice(0, 10))}`}
        </span>
      ) : null}
      {edited ? (
        <Badge variant="warning" appearance="light" size="sm">
          Saved, not confirmed
        </Badge>
      ) : null}
    </div>
  );
}

/** The read-only split sheet of these lines, the moved splits drawn under where they sit. */
function ReadOnlySheet({
  payload,
  lines,
  all,
}: {
  payload: LineSplitsPayload;
  lines: SplitLine[];
  all: SplitLine[];
}) {
  return (
    <div className="min-h-0 flex-1 [&>[data-slot=table-wrapper]]:h-full">
      <LineSplitSheet
        readOnly
        lines={lines}
        allLines={all}
        savedLines={all}
        soNumber={payload.so_number ?? ''}
        soDate={formatSplitDate(payload.so_date ?? null)}
        openLineIds={NO_LINE_IDS}
        drag={null}
        overTarget={null}
        flashLineId={null}
        handlers={INERT_HANDLERS}
      />
    </div>
  );
}

/** The body while the sheet is not in yet: the read's failure with a Retry, else a skeleton. */
function SheetPending({
  error,
  onRetry,
}: {
  error?: unknown;
  onRetry?: () => void;
}) {
  return error ? (
    <div className="flex items-center justify-center p-6 text-sm">
      <ListLoadFailure error={error} onRetry={onRetry} />
    </div>
  ) : (
    <SectionSkeleton rows={4} className="p-4" />
  );
}

/** UAC D1: the whole-order popup's empty state, also a guided Confirm page's. */
function NoSplitLines() {
  return (
    <div className="py-6 text-center">
      <p className="text-sm font-medium">No split lines</p>
      <p className="text-sm text-muted-foreground">
        Every line ships as AutoCount has it.
      </p>
    </div>
  );
}

/** Full screen on a phone, as wide as the sheet needs on a desktop (UAC E6). */
const SHEET_DIALOG_CLASS =
  'gap-0 overflow-hidden p-0 max-md:inset-0 max-md:rounded-none';

export interface LineSplitInfoProps {
  lineNo: number | null | undefined;
  itemCode: string | null | undefined;
  soNumber: string | null | undefined;
  /** The OI page names its inquiry: "<OI number> line <n>" under the title. */
  oiNumber?: string | null;
  /** The chip (`split_view`): "Split N", nothing for a line without splits. */
  view: LineSplitView | null | undefined;
  /** The order's split sheet (`LineSplitService.read`); a skeleton until it is in. */
  payload?: LineSplitsPayload | null;
  /** The sheet read failed: said in the popup with a Retry, never a skeleton forever. */
  loadError?: unknown;
  onRetry?: () => void;
}

/** "Split N" and the (i) button; nothing for a line without splits (UAC B1). */
export function LineSplitInfo({
  lineNo,
  itemCode,
  soNumber,
  oiNumber,
  view,
  payload,
  loadError,
  onRetry,
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
  const sheet = React.useMemo(() => {
    if (!open || !payload) return null;
    const all = sheetLinesOf(payload);
    const own = all.find((line) => line.lineNo === lineNo);
    if (!own) return { all, lines: [] as SplitLine[], ids: NO_LINE_IDS };
    // UAC E3: this line, and the lines its own splits moved onto; splits moved onto it
    // are drawn under it.
    const ids = new Set([own.lineId]) as ReadonlySet<string>;
    return { all, lines: linesWithLanding(all, ids), ids };
  }, [open, payload, lineNo]);
  if (!view) return null;
  const count = splitCount(view);
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
          <DialogContent variant="fullscreen" className={SHEET_DIALOG_CLASS}>
            <DialogHeader className="mb-0 space-y-0 border-b border-border px-4 py-3 pe-12 text-start sm:text-start">
              <DialogTitle className="truncate">{`Line ${lineNo ?? ''} ${itemCode ?? ''}: split`}</DialogTitle>
              {sub ? (
                <DialogDescription className="truncate text-xs">
                  {sub}
                </DialogDescription>
              ) : null}
            </DialogHeader>
            {payload && sheet ? (
              <>
                <SheetStatus
                  payload={payload}
                  edited={isSplitEdited(payload, sheet.ids)}
                />
                <ReadOnlySheet
                  payload={payload}
                  lines={sheet.lines}
                  all={sheet.all}
                />
              </>
            ) : (
              <SheetPending error={loadError} onRetry={onRetry} />
            )}
          </DialogContent>
        </Dialog>
      ) : null}
    </span>
  );
}

/** UAC D1, E3, E4: every split line of one order, as the read-only split sheet. */
export function OrderSplitsDialog({
  title,
  subtitle,
  payload,
  open,
  onOpenChange,
  returnFocusRef,
  loadError,
  onRetry,
}: {
  title: string;
  subtitle?: string | null;
  /**
   * The order's split sheet (`LineSplitService.read`): `undefined` while it loads (a
   * skeleton), `null` when no line of the order is split (the empty state).
   */
  payload: LineSplitsPayload | null | undefined;
  /** The sheet read failed: said with a Retry, never a skeleton forever. */
  loadError?: unknown;
  onRetry?: () => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * UAC B8: the control that opened the popup (the gear button). A gear menu item that
   * opens a dialog leaves Radix nothing to return focus to, so Escape and Close hand it
   * back here.
   */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  const sheet = React.useMemo(() => {
    if (!payload) return null;
    const all = sheetLinesOf(payload);
    // UAC E3: the lines with saved splits, and a line that only receives a moved split.
    const receiving = receivingLineIds(all);
    const split = all.filter((line) => line.splits.length > 0);
    const lines = all.filter(
      (line) => line.splits.length > 0 || receiving.has(line.lineId),
    );
    return {
      all,
      lines,
      splitCount: split.length,
      ids: new Set(lines.map((line) => line.lineId)) as ReadonlySet<string>,
    };
  }, [payload]);
  const sub = [
    subtitle,
    sheet && sheet.splitCount > 0
      ? `${sheet.splitCount} ${sheet.splitCount === 1 ? 'split line' : 'split lines'}`
      : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        variant="fullscreen"
        className={SHEET_DIALOG_CLASS}
        onCloseAutoFocus={(event) => {
          const opener = returnFocusRef?.current;
          if (!opener || !opener.isConnected) return;
          event.preventDefault();
          opener.focus();
        }}
      >
        <DialogHeader className="mb-0 space-y-0 border-b border-border px-4 py-3 pe-12 text-start sm:text-start">
          <DialogTitle className="truncate">{title}</DialogTitle>
          {sub ? (
            <DialogDescription className="truncate text-xs">
              {sub}
            </DialogDescription>
          ) : null}
        </DialogHeader>
        {payload === undefined ? (
          <SheetPending error={loadError} onRetry={onRetry} />
        ) : !payload || !sheet || sheet.lines.length === 0 ? (
          <NoSplitLines />
        ) : (
          <>
            <SheetStatus
              payload={payload}
              edited={isSplitEdited(payload, sheet.ids)}
            />
            <ReadOnlySheet
              payload={payload}
              lines={sheet.lines}
              all={sheet.all}
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * OI-SPLIT-GUIDE (UAC B2): only the named lines of one order (the saved split edits a
 * Confirm applies), each as the line popup shows a line (UAC E3 of #1794: the line and the
 * lines its splits land on), as the same read-only split sheet. No dialog of its own: the
 * guided Confirm draws it inside its Split page.
 */
export function SplitLinesSheet({
  payload,
  lineIds,
}: {
  /** The order's split sheet; `null` when no line of the order is split. */
  payload: LineSplitsPayload | null;
  lineIds: readonly string[];
}) {
  const sheet = React.useMemo(() => {
    const all = payload ? sheetLinesOf(payload) : [];
    return { all, lines: linesWithLanding(all, new Set(lineIds)) };
  }, [payload, lineIds]);
  if (!payload || sheet.lines.length === 0) return <NoSplitLines />;
  return <ReadOnlySheet payload={payload} lines={sheet.lines} all={sheet.all} />;
}
