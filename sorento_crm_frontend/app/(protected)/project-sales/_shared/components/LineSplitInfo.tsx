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
  /** Only the SO number and date the sheet prints are read. */
  payload: Pick<LineSplitsPayload, 'so_number' | 'so_date'>;
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
  // OI-SPLIT-GUIDE (UAC F29): no line number on the popup (its (i) button's label keeps it).
  const sub = [soNumber, oiNumber || null]
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
              <DialogTitle className="truncate">{`${itemCode ?? ''}: split`}</DialogTitle>
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

/** OI-SPLIT-GUIDE (UAC F2, F10): one line a Confirm covers, as the board states it. */
export interface CoveredSheetLine {
  /** The planning line id; null on an order nobody has adopted yet. */
  lineId: string | null;
  /** The board's own key, the identity of a line with no planning line. */
  key: string;
  lineNo: number | null;
  itemCode: string;
  location: string;
  qty: number;
  date: string | null;
  /** The purchasing email's words for what Confirm sends (server `saved_remark`). */
  savedRemark: string | null;
}

/**
 * OI-SPLIT-GUIDE (UAC F2, F3, F10): the read-only sheet's lines for the lines one Confirm
 * covers on an order. A covered line the split read shows split keeps its split rows, with
 * the lines they land on (UAC E3 of #1794); every other covered line is ONE row built from
 * the board's own statement of it, whose Remark is the email's words (`savedRemark`). So an
 * order with no planning record yet (no split read) and a line the read never lists (the
 * book cancelled it) still get their row, and the shared split read stays as it is.
 */
export function coveredSheetLines(
  payload: LineSplitsPayload | null,
  covered: readonly CoveredSheetLine[],
): { all: SplitLine[]; lines: SplitLine[] } {
  const read = payload ? sheetLinesOf(payload) : [];
  const byId = new Map(read.map((line) => [line.lineId, line]));
  const words = new Map(
    covered.flatMap((line) => (line.lineId ? [[line.lineId, line.savedRemark] as const] : [])),
  );
  const splitIds = new Set(
    covered.flatMap((line) =>
      line.lineId && (byId.get(line.lineId)?.splits.length ?? 0) > 0 ? [line.lineId] : [],
    ),
  );
  const fromRead = linesWithLanding(read, splitIds).map((line) =>
    words.has(line.lineId) ? { ...line, savedRemark: words.get(line.lineId) ?? null } : line,
  );
  const shown = new Set(fromRead.map((line) => line.lineId));
  const built: SplitLine[] = covered
    .filter((line) => !(line.lineId && shown.has(line.lineId)))
    .map((line) => ({
      lineId: line.lineId ?? `board:${line.key}`,
      lineNo: line.lineNo,
      itemCode: line.itemCode,
      // PRODUCT-CHANGE-TALLY: the product AutoCount swapped the line from, off the read.
      wasItemCode: (line.lineId ? byId.get(line.lineId)?.wasItemCode : null) ?? null,
      location: line.location,
      baseQty: line.qty,
      baseDate: line.date,
      nowQty: line.qty,
      nowDate: line.date,
      pendingChange: false,
      splits: [],
      savedRemark: line.savedRemark,
      // The read's own words for the line's row (the email's REMARK), muted under none saved.
      remarkGenerated: (line.lineId ? byId.get(line.lineId)?.remarkGenerated : undefined) ?? '',
    }));
  const builtIds = new Set(built.map((line) => line.lineId));
  return {
    all: [...read.filter((line) => !builtIds.has(line.lineId)), ...built],
    lines: sortLines([...fromRead, ...built]),
  };
}

/** OI-SPLIT-GUIDE: `coveredSheetLines` as the read-only sheet, inside the guide's page. */
export function SplitLinesSheet({
  payload,
  soNumber,
  sheet,
}: {
  /** Only the SO number and date the sheet prints are read. */
  payload: Pick<LineSplitsPayload, 'so_number' | 'so_date'> | null;
  soNumber: string;
  sheet: { all: SplitLine[]; lines: SplitLine[] };
}) {
  if (sheet.lines.length === 0) return <NoSplitLines />;
  return (
    <ReadOnlySheet
      payload={payload ?? { so_number: soNumber, so_date: null }}
      lines={sheet.lines}
      all={sheet.all}
    />
  );
}
