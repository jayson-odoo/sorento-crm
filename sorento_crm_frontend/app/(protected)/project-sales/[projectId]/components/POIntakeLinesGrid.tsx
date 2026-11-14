'use client';

import * as React from 'react';
import {
  CellContext,
  ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  Ban,
  Check,
  Loader2,
  Pencil,
  RotateCcw,
  StickyNote,
  X,
} from 'lucide-react';
import { toast } from '@/lib/toast';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
// The shared products `/select` mapper. Its name says "variant" because that screen needed
// it first; the endpoint and the shape are the generic ones.
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import type {
  POAnnotation,
  POAnnotationEditBody,
  POLineMatchOption,
  POLineUpdateBody,
  POVersionLine,
} from '../../_shared/types/poIntake.types';
import { PO_INTERPRETATION_LABELS } from '../../_shared/types/poIntake.types';
import {
  formatMyrExact,
  formatQty,
  isDecimalString,
  isMoneyZero,
  lineAmount,
  subtractMoney,
} from '../../_shared/lib/money';
import { NumberInput } from '@/components/ui/number-input';
import { parseNumberDraft } from '@/lib/number-field';
import { formatUnitPrice } from './SalesOrderMoney';
import { describeAnnotationEffect } from './POIntakeAnnotationsGrid';
import { POIntakeAnnotationEditDialog } from './POIntakeAnnotationEditDialog';

export interface POIntakeLinesGridHandle {
  focusLine: (lineId: string) => void;
  /** True if a line still had a note to review and the reader was sent to it. */
  focusFirstUnreviewedAnnotation: () => boolean;
}

/**
 * Column preferences are keyed on this, not on the pathname DataGrid would fall back to:
 * the path carries the version id, so the fallback would write one preferences row per
 * uploaded document instead of one per person. `<perm_slug>::<stable_id>`, per
 * docs/LISTING-COLUMN-PREFERENCES.md.
 */
export const PO_INTAKE_LINES_LISTING_KEY =
  'projects.projects.view::po-intake-lines';

interface Props {
  lines: POVersionLine[];
  readOnly: boolean;
  savingLineIds: string[];
  focusedLineId: string | null;
  onFocusLine: (line: POVersionLine) => void;
  onUpdateLine: (lineId: string, body: POLineUpdateBody) => Promise<void>;
  /** Every note the pencil left, including the ones naming no line (those are ignored here). */
  annotations: POAnnotation[];
  savingAnnotationIds: string[];
  onShowPage: (page: number) => void;
  onAcceptAnnotation: (
    annotationId: string,
    note?: string | null,
  ) => Promise<void>;
  onEditAnnotation: (
    annotationId: string,
    body: POAnnotationEditBody,
  ) => Promise<void>;
  onRejectAnnotation: (annotationId: string, note: string) => Promise<void>;
  /**
   * S6-3: the grid opens on "Need attention" while the version is unconfirmed, and on every
   * line once it is - a confirmed PO is a record to check against, not a queue to work.
   */
  defaultFlaggedOnly?: boolean;
  /** PO-UPLOAD-MATCHING: live lines with a suggested product or qty not yet accepted. */
  suggestionCount?: number;
  onAcceptSuggestion?: (line: POVersionLine) => Promise<void>;
  onAcceptAllSuggestions?: () => Promise<void>;
  isAcceptingSuggestions?: boolean;
}

type ProductOption = { value: string; label: string; description?: string };

type LinesView = 'flagged' | 'suggested' | 'all';

type NumericField = 'qty' | 'unit_price' | 'amount';
/** What a person has typed into a row's number boxes and not yet saved. */
type RowDraft = Partial<Record<NumericField, string>>;

/**
 * A server figure as the box shows it: a quantity without trailing zeros ("24.0000" -> "24"),
 * money with at least two decimals ("86.90000" -> "86.90"). No thousands separators: the box
 * is a number field.
 */
function boxFigure(
  field: NumericField,
  value: string | null | undefined,
): string {
  if (value === null || value === undefined || String(value).trim() === '')
    return '';
  if (!isDecimalString(value)) return String(value);
  return field === 'qty'
    ? formatQty(value)
    : formatUnitPrice(value).replace(/,/g, '');
}

/**
 * The row's figures as they stand WHILE a person types: the typed qty and unit price, and the
 * amount they give on a line whose amount the server computes (`amount_computed`: none was
 * printed). A printed or typed amount is never replaced; the Flag checks it against the typed
 * figures instead. `lineAmount` is the server's own rule (5-dp price, half-even).
 */
function liveFigures(line: POVersionLine, draft: RowDraft | undefined) {
  const qty = draft?.qty ?? line.qty;
  const unitPrice = draft?.unit_price ?? line.unit_price;
  const printed = isDecimalString(line.amount) && !line.amount_computed;
  const expected = lineAmount(qty, unitPrice);
  const typedFactor =
    draft?.qty !== undefined || draft?.unit_price !== undefined;
  const amount =
    draft?.amount ?? (!printed && typedFactor ? (expected ?? '') : line.amount);
  const ok =
    draft === undefined
      ? line.arithmetic_ok
      : expected !== null && isMoneyZero(subtractMoney(amount, expected));
  return { qty, unitPrice, amount, expected, ok, printed, typedFactor };
}

/** The Amount box: what was typed into it, else the live qty x unit price on a line whose
 *  amount the server computes, else the server figure. */
function amountBox(line: POVersionLine, draft: RowDraft | undefined): string {
  if (draft?.amount !== undefined) return draft.amount;
  const live = liveFigures(line, draft);
  if (!live.printed && live.typedFactor) return live.amount ?? '';
  return boxFigure('amount', line.amount);
}

/** The short marker on the row: what the pencil is asking for, not why. */
function annotationBadgeLabel(note: POAnnotation): string {
  const json = (note.interpretation_json ?? {}) as Record<string, unknown>;
  switch (note.interpretation) {
    case 'cancel_line':
      return 'Cancel line';
    case 'amend_code': {
      const code = typeof json.code === 'string' ? json.code : '';
      return code ? `Amend code to ${code}` : 'Amend code';
    }
    case 'amend_description':
      return 'Amend description';
    case 'successor_po': {
      const poNumber = typeof json.po_number === 'string' ? json.po_number : '';
      return poNumber ? `Replaced by ${poNumber}` : 'Names a replacement PO';
    }
    case 'signature':
      return 'Signature';
    default:
      return PO_INTERPRETATION_LABELS[note.interpretation] ?? 'Note';
  }
}

/** A suggested product or a suggested qty that a person has not accepted yet. */
export function hasSuggestion(line: POVersionLine): boolean {
  return line.resolution_source === 'suggested' || Boolean(line.qty_suggested);
}

/**
 * A line our arithmetic disagrees with, one with no product, one with a suggestion to accept,
 * or one that was cancelled.
 */
export function isFlaggedLine(line: POVersionLine): boolean {
  return (
    !line.arithmetic_ok ||
    !line.resolved_product_id ||
    hasSuggestion(line) ||
    line.is_cancelled
  );
}

/**
 * A line that wants a person to do something. A cancelled line is deliberately NOT one of
 * these: somebody already decided about it by accepting a card, so counting it as work
 * outstanding would mean accepting a cancellation ADDS to the pile.
 */
export function lineNeedsAttention(line: POVersionLine): boolean {
  return (
    !line.is_cancelled &&
    (!line.arithmetic_ok || !line.resolved_product_id || hasSuggestion(line))
  );
}

/**
 * The notes that hold Confirm: still proposed AND naming a line on this version. The server's
 * `blocking_annotations` (`project_po_confirm.py`) is the same rule, so the button, the
 * "Need attention" rows and the server's refusal always agree (owner re-test 25 Sep 2026: the
 * server once counted 11 notes this screen did not show). A note naming no line here has no
 * row to be reviewed from, so it never blocks.
 */
export function blockingNotes(
  annotations: POAnnotation[],
  lines: Pick<POVersionLine, 'line_no'>[],
): POAnnotation[] {
  const lineNos = new Set(lines.map((line) => line.line_no));
  return annotations.filter(
    (note) =>
      note.state === 'proposed' &&
      note.refers_to_lines.some((lineNo) => lineNos.has(lineNo)),
  );
}

/**
 * The 52 lines, editable in place.
 *
 * Cells are UNCONTROLLED and commit on blur or Enter; Escape puts the cell back to what the
 * server holds. Qty, unit price and amount are the shared `NumberInput`; what is typed travels
 * as the typed STRING to the API (never a re-serialised float), and the grid holds it as a
 * per-row draft only so the Amount and the Flag can follow it live.
 *
 * The real task on this document is three exceptions out of fifty-two rows, so the flagged
 * lines can be shown on their own. That filter opens ON while the version is unconfirmed
 * (S6-3, `defaultFlaggedOnly`) - the exceptions are the work; "All lines" is one click away
 * for reconciling a total against the whole document.
 */
export const POIntakeLinesGrid = React.forwardRef<
  POIntakeLinesGridHandle,
  Props
>(function POIntakeLinesGrid(
  {
    lines,
    readOnly,
    savingLineIds,
    focusedLineId,
    onFocusLine,
    onUpdateLine,
    annotations,
    savingAnnotationIds,
    onShowPage,
    onAcceptAnnotation,
    onEditAnnotation,
    onRejectAnnotation,
    defaultFlaggedOnly,
    suggestionCount = 0,
    onAcceptSuggestion,
    onAcceptAllSuggestions,
    isAcceptingSuggestions,
  },
  ref,
) {
  // The row a right-click landed on, when it has a suggestion to accept.
  const [menuLine, setMenuLine] = React.useState<POVersionLine | null>(null);
  const rowRefs = React.useRef<Record<string, HTMLElement | null>>({});
  const [confirming, setConfirming] = React.useState<{
    kind: 'cancel' | 'clear-product';
    line: POVersionLine;
  } | null>(null);
  // Which rows the grid shows: the ones needing attention, the suggestions still to accept
  // (exactly what "Accept all suggestions (N)" counts), or every line.
  const [view, setView] = React.useState<LinesView>(
    defaultFlaggedOnly ? 'flagged' : 'all',
  );
  const flaggedOnly = view !== 'all';
  // A row asked for while it is filtered out cannot be scrolled to until it mounts.
  const pendingFocusId = React.useRef<string | null>(null);
  // Which line's notes popover is open, if any - one at a time, and closed by default. Set
  // from "Review them" (the header's call to action) landing on a note-only line, never on
  // an ordinary row click, so a popover opens only when the reader asked to review notes.
  const [openNotesLineId, setOpenNotesLineId] = React.useState<string | null>(
    null,
  );
  const pendingOpenNotesId = React.useRef<string | null>(null);

  // Accept / reject / edit dialogs are shared across every row, the same way the old
  // "Handwriting" card shared one set of dialogs across every note: a note naming three
  // lines is still one thing to decide about, decided once.
  const [acceptingAnnotation, setAcceptingAnnotation] = React.useState<{
    note: POAnnotation;
    lineId: string;
  } | null>(null);
  const [rejectingAnnotation, setRejectingAnnotation] = React.useState<{
    note: POAnnotation;
    lineId: string;
  } | null>(null);
  const [editingAnnotation, setEditingAnnotation] =
    React.useState<POAnnotation | null>(null);
  const [rejectNote, setRejectNote] = React.useState('');
  // Which note (and which row it was cleared from) to watch for, so that once the parent's
  // data confirms it is no longer proposed, focus moves on to the next warning on its own
  // rather than leaving the reader to scroll and find it.
  const lastActionedAnnotationId = React.useRef<string | null>(null);
  const lastActionedLineId = React.useRef<string | null>(null);

  // Notes that name at least one line, grouped by the line number they name. A note naming
  // three lines lives in three buckets, so it shows, and clears, on every one of them.
  const annotationsByLineNo = React.useMemo(() => {
    const map = new Map<number, POAnnotation[]>();
    for (const note of annotations) {
      for (const lineNo of note.refers_to_lines) {
        const bucket = map.get(lineNo);
        if (bucket) bucket.push(note);
        else map.set(lineNo, [note]);
      }
    }
    return map;
  }, [annotations]);

  // "Identified" (S6-3): an arithmetic mismatch, an unresolved product, a cancellation, or
  // a handwritten note still waiting on a decision - everything a person has to look at
  // before this document can be trusted, not only what `isFlaggedLine` alone catches.
  const flagged = React.useMemo(
    () =>
      lines.filter(
        (line) =>
          isFlaggedLine(line) ||
          (annotationsByLineNo.get(line.line_no) ?? []).some(
            (note) => note.state === 'proposed',
          ),
      ),
    [lines, annotationsByLineNo],
  );
  // Live lines with a suggestion: the server's `suggestion_count` rule, so this filter's row
  // count and the accept-all button's N are the same number.
  const suggested = React.useMemo(
    () => lines.filter((line) => !line.is_cancelled && hasSuggestion(line)),
    [lines],
  );
  const visibleLines =
    view === 'flagged' ? flagged : view === 'suggested' ? suggested : lines;
  const nothingLeftToShow = flaggedOnly && visibleLines.length === 0;

  // Once the last suggestion is accepted the Suggested view is empty, but a line with no qty
  // can still hold Confirm: fall back to "Need attention" rather than "Nothing left to fix".
  React.useEffect(() => {
    if (view === 'suggested' && suggested.length === 0) setView('flagged');
  }, [view, suggested.length]);
  // When the filter has emptied itself the way back lives in the all-clear panel, so the
  // toolbar toggle stands down rather than offering the same thing twice.
  const showFilterToggle =
    (flagged.length > 0 || flaggedOnly) && !nothingLeftToShow;

  const linesWithUnreviewedAnnotations = React.useMemo(
    () =>
      lines
        .filter((line) =>
          (annotationsByLineNo.get(line.line_no) ?? []).some(
            (note) => note.state === 'proposed',
          ),
        )
        .sort((a, b) => a.line_no - b.line_no),
    [lines, annotationsByLineNo],
  );

  const scrollToLine = React.useCallback((lineId: string) => {
    // jsdom implements no scrollIntoView, hence the optional call.
    rowRefs.current[lineId]?.scrollIntoView?.({
      block: 'center',
      behavior: 'smooth',
    });
  }, []);

  const focusLineInternal = React.useCallback(
    (lineId: string, options?: { openNotes?: boolean }) => {
      const line = lines.find((item) => item.id === lineId);
      if (!line) return;
      onFocusLine(line);
      // The banner and the handwriting notes both point at specific lines, and a note can
      // name a perfectly healthy one. Landing on it has to work with the filter on, so the
      // filter gives way rather than swallowing the jump - but only when the line is not
      // already one of the ones "Need attention" shows (N1: a note-only line is already
      // visible there, and flipping to "All lines" on its own call to action defeats the
      // guided view).
      if (flaggedOnly && !visibleLines.some((item) => item.id === lineId)) {
        pendingFocusId.current = lineId;
        if (options?.openNotes) pendingOpenNotesId.current = lineId;
        setView('all');
        return;
      }
      scrollToLine(lineId);
      if (options?.openNotes) setOpenNotesLineId(lineId);
    },
    [lines, onFocusLine, flaggedOnly, visibleLines, scrollToLine],
  );

  // Where "clear the warning and move on" goes next: the first line, after the one just
  // cleared, that still has a note nobody has looked at. Wraps back to the top of the list
  // rather than stopping, since the document does not end where the reader started.
  const goToNextUnreviewed = React.useCallback(
    (afterLineId: string | null) => {
      if (linesWithUnreviewedAnnotations.length === 0) return;
      const anchor = lines.find((item) => item.id === afterLineId);
      const anchorLineNo = anchor?.line_no ?? -Infinity;
      const next =
        linesWithUnreviewedAnnotations.find(
          (line) => line.line_no > anchorLineNo,
        ) ?? linesWithUnreviewedAnnotations[0];
      focusLineInternal(next.id);
    },
    [linesWithUnreviewedAnnotations, lines, focusLineInternal],
  );

  React.useImperativeHandle(ref, () => ({
    focusLine: focusLineInternal,
    focusFirstUnreviewedAnnotation: () => {
      if (linesWithUnreviewedAnnotations.length === 0) return false;
      // "Review them" (the header link) opens the first unreviewed line's popover
      // directly, rather than merely scrolling to a row the reader still has to click.
      focusLineInternal(linesWithUnreviewedAnnotations[0].id, {
        openNotes: true,
      });
      return true;
    },
  }));

  React.useEffect(() => {
    const pending = pendingFocusId.current;
    if (!pending) return;
    pendingFocusId.current = null;
    scrollToLine(pending);
    if (pendingOpenNotesId.current === pending) {
      pendingOpenNotesId.current = null;
      setOpenNotesLineId(pending);
    }
  }, [view, scrollToLine]);

  // Runs after the parent's data confirms the note just accepted or rejected is no longer
  // proposed (a fresh fetch, not the click itself), and only then moves focus on: acting on
  // stale data would send the reader to a line whose warning has not actually cleared yet.
  React.useEffect(() => {
    const noteId = lastActionedAnnotationId.current;
    if (!noteId) return;
    const stillProposed = annotations.some(
      (note) => note.id === noteId && note.state === 'proposed',
    );
    if (stillProposed) return;
    const fromLineId = lastActionedLineId.current;
    lastActionedAnnotationId.current = null;
    lastActionedLineId.current = null;
    // The just-resolved line's popover has nothing left to show - close it rather than
    // leaving it open over an empty indicator while focus moves on to the next one.
    setOpenNotesLineId(null);
    goToNextUnreviewed(fromLineId);
  }, [annotations, goToNextUnreviewed]);

  const openAcceptAnnotation = React.useCallback(
    (note: POAnnotation, lineId: string) =>
      setAcceptingAnnotation({ note, lineId }),
    [],
  );
  const openRejectAnnotation = React.useCallback(
    (note: POAnnotation, lineId: string) => {
      setRejectNote('');
      setRejectingAnnotation({ note, lineId });
    },
    [],
  );

  const fetchProducts = React.useCallback(
    async (query: string): Promise<ProductOption[]> => {
      const rows = await getProductsForVariantSelect(query || undefined);
      return rows.map((row) => ({
        value: row.id,
        label: row.product_code,
        description: row.product_name,
      }));
    },
    [],
  );

  const commit = React.useCallback(
    (line: POVersionLine, body: POLineUpdateBody) => {
      void onUpdateLine(line.id, body);
    },
    [onUpdateLine],
  );

  // Typed, unsaved figures per row. The boxes show these while they exist, so a re-render
  // (another line's save, the server's echo) never rewrites what is being typed, and the
  // Amount and the Flag can follow qty x unit price live.
  const [drafts, setDrafts] = React.useState<Record<string, RowDraft>>({});
  const setDraft = React.useCallback(
    (lineId: string, field: NumericField, value: string | undefined) =>
      setDrafts((current) => {
        const row: RowDraft = { ...(current[lineId] ?? {}) };
        if (value === undefined) delete row[field];
        else row[field] = value;
        const next = { ...current };
        if (Object.keys(row).length > 0) next[lineId] = row;
        else delete next[lineId];
        return next;
      }),
    [],
  );

  const clearIfUnchanged = React.useCallback(
    (lineId: string, field: NumericField, sent: string) =>
      setDrafts((current) => {
        if (current[lineId]?.[field] !== sent) return current;
        const row: RowDraft = { ...current[lineId] };
        delete row[field];
        const next = { ...current };
        if (Object.keys(row).length > 0) next[lineId] = row;
        else delete next[lineId];
        return next;
      }),
    [],
  );

  /**
   * Blur / Enter on a number box: one save of the typed figure; the draft gives way to the
   * server's figure once that save lands.
   */
  const commitNumber = React.useCallback(
    (line: POVersionLine, field: NumericField, label: string) => {
      const draft = drafts[line.id];
      const typed = draft?.[field];
      if (typed === undefined) return;
      const next = typed.trim();
      const clear = () => setDraft(line.id, field, undefined);
      if (!isDecimalString(next)) {
        toast.error(`${label} must be a number`);
        clear();
        return;
      }
      if (parseNumberDraft(next) === parseNumberDraft(line[field])) {
        clear();
        return;
      }
      // Only the typed figure: the server moves a computed amount itself (`amount_computed`).
      const body: POLineUpdateBody = { [field]: next };
      void onUpdateLine(line.id, body).finally(() =>
        // A second edit typed while this save was in flight is kept: the draft is dropped
        // only if it still holds exactly what was sent.
        clearIfUnchanged(line.id, field, typed),
      );
    },
    [drafts, onUpdateLine, setDraft, clearIfUnchanged],
  );

  const liveColumns = React.useMemo<ColumnDef<POVersionLine>[]>(() => {
    const cellWrap = (
      line: POVersionLine,
      children: React.ReactNode,
      first = false,
    ) => (
      <div
        ref={
          first
            ? (element) => {
                rowRefs.current[line.id] = element;
              }
            : undefined
        }
        className="min-w-0"
        onFocusCapture={() => onFocusLine(line)}
        onClick={() => onFocusLine(line)}
      >
        {children}
      </div>
    );

    return [
      {
        accessorKey: 'line_no',
        header: ({ column }) => (
          <DataGridColumnHeader title="#" column={column} />
        ),
        cell: ({ row }) =>
          cellWrap(
            row.original,
            <span className="flex items-center gap-1 text-sm tabular-nums">
              {row.original.line_no}
              <SavingSpinner lineId={row.original.id} />
            </span>,
            true,
          ),
        size: 64,
        minSize: 56,
        meta: { headerTitle: '#', skeleton: <Skeleton className="h-4 w-6" /> },
      },
      {
        accessorKey: 'stock_code_raw',
        header: ({ column }) => (
          <DataGridColumnHeader title="Code on the PO" column={column} />
        ),
        cell: ({ row }) =>
          cellWrap(
            row.original,
            <CellInput
              line={row.original}
              field="stock_code_raw"
              value={row.original.stock_code_raw ?? ''}
              readOnly={readOnly}
              label={`Code on line ${row.original.line_no}`}
              onCommit={(value) =>
                commit(row.original, { stock_code_raw: value || null })
              }
            />,
          ),
        size: 160,
        minSize: 120,
        meta: {
          headerTitle: 'Code on the PO',
          skeleton: <Skeleton className="h-4 w-20" />,
        },
      },
      {
        accessorKey: 'description_raw',
        header: ({ column }) => (
          <DataGridColumnHeader title="Description" column={column} />
        ),
        cell: ({ row }) =>
          cellWrap(
            row.original,
            <CellInput
              line={row.original}
              field="description_raw"
              value={row.original.description_raw ?? ''}
              readOnly={readOnly}
              label={`Description on line ${row.original.line_no}`}
              onCommit={(value) =>
                commit(row.original, { description_raw: value || null })
              }
            />,
          ),
        size: 260,
        minSize: 160,
        meta: {
          headerTitle: 'Description',
          skeleton: <Skeleton className="h-4 w-40" />,
        },
      },
      {
        accessorKey: 'qty',
        header: ({ column }) => (
          <DataGridColumnHeader title="Qty" column={column} />
        ),
        cell: ({ row }) =>
          cellWrap(
            row.original,
            <NumberCell
              line={row.original}
              field="qty"
              readOnly={readOnly}
              label={`Quantity on line ${row.original.line_no}`}
            />,
          ),
        size: 92,
        minSize: 72,
        meta: {
          headerTitle: 'Qty',
          skeleton: <Skeleton className="h-4 w-10" />,
        },
      },
      {
        accessorKey: 'uom_raw',
        header: ({ column }) => (
          <DataGridColumnHeader title="UOM" column={column} />
        ),
        cell: ({ row }) =>
          cellWrap(
            row.original,
            <CellInput
              line={row.original}
              field="uom_raw"
              value={row.original.uom_raw ?? ''}
              readOnly={readOnly}
              label={`UOM on line ${row.original.line_no}`}
              onCommit={(value) =>
                commit(row.original, { uom_raw: value || null })
              }
            />,
          ),
        size: 88,
        minSize: 72,
        meta: {
          headerTitle: 'UOM',
          skeleton: <Skeleton className="h-4 w-10" />,
        },
      },
      {
        accessorKey: 'unit_price',
        header: ({ column }) => (
          <DataGridColumnHeader title="Unit price" column={column} />
        ),
        cell: ({ row }) =>
          cellWrap(
            row.original,
            <NumberCell
              line={row.original}
              field="unit_price"
              readOnly={readOnly}
              label={`Unit price on line ${row.original.line_no}`}
            />,
          ),
        size: 116,
        minSize: 96,
        meta: {
          headerTitle: 'Unit price',
          skeleton: <Skeleton className="h-4 w-14" />,
        },
      },
      {
        accessorKey: 'amount',
        header: ({ column }) => (
          <DataGridColumnHeader title="Amount" column={column} />
        ),
        cell: ({ row }) =>
          cellWrap(
            row.original,
            <NumberCell
              line={row.original}
              field="amount"
              readOnly={readOnly}
              label={`Amount on line ${row.original.line_no}`}
            />,
          ),
        size: 124,
        minSize: 100,
        meta: {
          headerTitle: 'Amount',
          skeleton: <Skeleton className="h-4 w-16" />,
        },
      },
      {
        id: 'check',
        header: ({ column }) => (
          <DataGridColumnHeader title="Flag" column={column} />
        ),
        cell: ({ row }) => {
          const line = row.original;
          const lineNotes = annotationsByLineNo.get(line.line_no) ?? [];
          return cellWrap(
            line,
            <FlagRow line={line}>
              {line.is_cancelled && (
                <Badge variant="secondary" className="text-[11px]">
                  Cancelled
                </Badge>
              )}
              {!line.resolved_product_id && (
                <Badge variant="outline" className="text-[11px]">
                  No product
                </Badge>
              )}
              {hasSuggestion(line) && (
                <Badge
                  variant="info"
                  className="text-[11px]"
                  title={suggestionTitle(line)}
                >
                  Suggested
                </Badge>
              )}
              {line.resolution_source === 'manual' && (
                <Badge variant="outline" className="text-[11px]">
                  Matched by hand
                </Badge>
              )}
              <LineNotesIndicator
                line={line}
                // A viewer without edit rights has nothing to do about a note, but it
                // must still show here, muted - otherwise a read-only viewer sees no
                // pending handwriting at all. An editor only ever needs the ones still
                // waiting on a decision; once resolved, a note has nothing left to show.
                notes={
                  readOnly
                    ? lineNotes
                    : lineNotes.filter((note) => note.state === 'proposed')
                }
                readOnly={readOnly}
                open={openNotesLineId === line.id}
                onOpenChange={(next) =>
                  setOpenNotesLineId(next ? line.id : null)
                }
                savingAnnotationIds={savingAnnotationIds}
                onShowPage={onShowPage}
                onAccept={(note) => openAcceptAnnotation(note, line.id)}
                onEdit={(note) => setEditingAnnotation(note)}
                onReject={(note) => openRejectAnnotation(note, line.id)}
              />
            </FlagRow>,
          );
        },
        size: 190,
        minSize: 130,
        meta: {
          headerTitle: 'Flag',
          skeleton: <Skeleton className="h-4 w-20" />,
        },
      },
      {
        id: 'product',
        header: ({ column }) => (
          <DataGridColumnHeader title="Our product" column={column} />
        ),
        cell: ({ row }) => {
          const line = row.original;
          const selected = line.resolved_product_id
            ? {
                value: line.resolved_product_id,
                label: line.resolved_product_code ?? 'Matched product',
              }
            : undefined;
          return cellWrap(
            line,
            readOnly ? (
              <span
                className="block truncate text-sm"
                title={line.resolved_product_code ?? ''}
              >
                {line.resolved_product_code ?? 'Not matched'}
              </span>
            ) : (
              <>
                {/* SearchableSelect forwards `id`, not arbitrary aria props, so the
                      accessible name has to come from a real label. */}
                <label
                  className="sr-only"
                  htmlFor={`po-line-${line.line_no}-product`}
                >
                  {`Product on line ${line.line_no}`}
                </label>
                <LineProductPicker
                  id={`po-line-${line.line_no}-product`}
                  value={line.resolved_product_id ?? ''}
                  matchOptions={line.match_options}
                  fetchProducts={fetchProducts}
                  selectedOption={selected}
                  onChange={(value) => {
                    if (!value && line.resolved_product_id) {
                      setConfirming({ kind: 'clear-product', line });
                      return;
                    }
                    if (value !== (line.resolved_product_id ?? '')) {
                      commit(line, { resolved_product_id: value || null });
                    }
                  }}
                />
              </>
            ),
          );
        },
        size: 210,
        minSize: 150,
        meta: {
          headerTitle: 'Our product',
          skeleton: <Skeleton className="h-4 w-24" />,
        },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const line = row.original;
          if (readOnly) return null;
          return cellWrap(
            line,
            line.is_cancelled ? (
              <Button
                type="button"
                mode="icon"
                variant="ghost"
                size="sm"
                aria-label={`Restore line ${line.line_no}`}
                onClick={() => commit(line, { is_cancelled: false })}
              >
                <RotateCcw className="size-3.5" />
              </Button>
            ) : (
              <Button
                type="button"
                mode="icon"
                variant="ghost"
                size="sm"
                aria-label={`Cancel line ${line.line_no}`}
                onClick={() => setConfirming({ kind: 'cancel', line })}
              >
                <Ban className="size-3.5 text-destructive" />
              </Button>
            ),
          );
        },
        size: 68,
        minSize: 56,
        meta: {
          headerTitle: 'Actions',
          skeleton: <Skeleton className="h-4 w-6" />,
        },
      },
    ];
  }, [
    annotationsByLineNo,
    commit,
    fetchProducts,
    onFocusLine,
    onShowPage,
    openAcceptAnnotation,
    openNotesLineId,
    openRejectAnnotation,
    readOnly,
    savingAnnotationIds,
  ]);

  // tanstack renders each column's `cell` function AS A COMPONENT, so a new column set
  // remounts every cell, and the column set changed on every save (the owner's "jitter").
  // The table gets one stable set whose cells render the CURRENT definitions from context.
  const columns = React.useMemo<ColumnDef<POVersionLine>[]>(
    () => liveColumns.map((column) => ({ ...column, cell: LiveCell })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Typing and saving reach the cells through context too, so a keystroke never rebuilds
  // the column definitions at all.
  const liveRows = React.useMemo(
    () => ({ drafts, setDraft, commitNumber, savingLineIds }),
    [drafts, setDraft, commitNumber, savingLineIds],
  );

  const table = useReactTable({
    columns,
    data: visibleLines,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  const showAcceptAll =
    !readOnly && suggestionCount > 0 && Boolean(onAcceptAllSuggestions);

  return (
    <LiveColumnsContext.Provider value={liveColumns}>
      <LiveRowsContext.Provider value={liveRows}>
        <div className="min-w-0 space-y-2">
          {(showFilterToggle || showAcceptAll) && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              {showFilterToggle ? (
                <ToggleGroup
                  type="single"
                  variant="outline"
                  size="sm"
                  value={view}
                  onValueChange={(next) => next && setView(next as LinesView)}
                >
                  <ToggleGroupItem value="flagged" className="px-3">
                    {`Need attention (${flagged.length})`}
                  </ToggleGroupItem>
                  {(suggested.length > 0 || view === 'suggested') && (
                    <ToggleGroupItem value="suggested" className="px-3">
                      {`Suggested (${suggested.length})`}
                    </ToggleGroupItem>
                  )}
                  <ToggleGroupItem value="all" className="px-3">
                    {`All lines (${lines.length})`}
                  </ToggleGroupItem>
                </ToggleGroup>
              ) : (
                <span />
              )}
              {showAcceptAll && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isAcceptingSuggestions}
                  onClick={() => void onAcceptAllSuggestions?.()}
                >
                  {isAcceptingSuggestions && (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden />
                  )}
                  {`Accept all suggestions (${suggestionCount})`}
                </Button>
              )}
            </div>
          )}

          {nothingLeftToShow ? (
            <div className="rounded-lg border border-emerald-500/40 bg-emerald-50 px-6 py-10 text-center dark:bg-emerald-950/30">
              <h3 className="text-sm font-semibold text-emerald-900 dark:text-emerald-300">
                Nothing left to fix
              </h3>
              <Button
                type="button"
                variant="outline"
                className="mt-4"
                onClick={() => setView('all')}
              >
                {`All lines (${lines.length})`}
              </Button>
            </div>
          ) : (
            <ContextMenu>
              <ContextMenuTrigger
                asChild
                onContextMenu={(event) => {
                  // Right-click is the row action (owner standing rule: no row icon buttons for
                  // it). Only a row with something to accept opens the menu.
                  const id = (event.target as HTMLElement)
                    .closest('[data-po-line-id]')
                    ?.getAttribute('data-po-line-id');
                  const hit = lines.find((item) => item.id === id) ?? null;
                  const actionable =
                    !readOnly &&
                    Boolean(onAcceptSuggestion) &&
                    hit !== null &&
                    hasSuggestion(hit);
                  setMenuLine(actionable ? hit : null);
                  if (!actionable) event.preventDefault();
                }}
              >
                <div className="min-w-0">
                  <DataGrid
                    rowAttributes={(row: POVersionLine) => ({
                      'data-po-line-id': row.id,
                    })}
                    table={table}
                    recordCount={visibleLines.length}
                    isLoading={false}
                    listingKey={PO_INTAKE_LINES_LISTING_KEY}
                    tableLayout={{
                      width: 'fixed',
                      columnsResizable: true,
                      // The grid's OWN scroller (`data-grid-scroller`) carries both axes - a
                      // Radix `ScrollArea` wrapped around `DataGridTable` used to sit here
                      // instead, but that gives the table a `display: table` ancestor which
                      // shrink-fits, so the scroller never measured an overflow and the Amount
                      // column clipped with no way to reach it (owner hand test, 25 Sep 2026,
                      // item 1). A plain height string keeps the same vertical budget the
                      // ScrollArea's viewport used to cap at, with the horizontal scroll the
                      // scroller already brings for free.
                      scrollerMaxHeight:
                        'max-h-[calc(100vh-14rem)] overflow-y-auto',
                    }}
                  >
                    <div className="min-w-0 rounded-lg border border-border">
                      <DataGridTable />
                    </div>
                  </DataGrid>
                </div>
              </ContextMenuTrigger>
              {menuLine && (
                <ContextMenuContent>
                  <ContextMenuItem
                    disabled={savingLineIds.includes(menuLine.id)}
                    onSelect={() => void onAcceptSuggestion?.(menuLine)}
                  >
                    <Check className="size-3.5" aria-hidden />
                    Accept suggestion
                  </ContextMenuItem>
                </ContextMenuContent>
              )}
            </ContextMenu>
          )}

          <AlertDialog
            open={Boolean(confirming)}
            onOpenChange={(next) => !next && setConfirming(null)}
          >
            <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {confirming?.kind === 'cancel'
                    ? `Cancel line ${confirming.line.line_no}?`
                    : 'Remove the matched product?'}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {confirming?.kind === 'cancel'
                    ? `${describeLine(confirming.line)} stays on the record, marked cancelled, and is left out of our total. This action cannot be undone from the document.`
                    : confirming
                      ? `Line ${confirming.line.line_no} goes back to unmatched, and nothing on it will resolve to ${confirming.line.resolved_product_code ?? 'our catalogue'}.`
                      : ''}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep it</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  onClick={() => {
                    if (!confirming) return;
                    if (confirming.kind === 'cancel') {
                      commit(confirming.line, { is_cancelled: true });
                    } else {
                      commit(confirming.line, { resolved_product_id: null });
                    }
                    setConfirming(null);
                  }}
                >
                  {confirming?.kind === 'cancel'
                    ? 'Cancel the line'
                    : 'Remove it'}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <AlertDialog
            open={Boolean(acceptingAnnotation)}
            onOpenChange={(next) => !next && setAcceptingAnnotation(null)}
          >
            <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
              <AlertDialogHeader>
                <AlertDialogTitle>Accept this note?</AlertDialogTitle>
                <AlertDialogDescription>
                  {acceptingAnnotation
                    ? describeAnnotationEffect(acceptingAnnotation.note, lines)
                    : ''}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Not yet</AlertDialogCancel>
                <AlertDialogAction
                  className={
                    acceptingAnnotation?.note.interpretation === 'cancel_line'
                      ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                      : undefined
                  }
                  onClick={() => {
                    if (acceptingAnnotation) {
                      lastActionedAnnotationId.current =
                        acceptingAnnotation.note.id;
                      lastActionedLineId.current = acceptingAnnotation.lineId;
                      void onAcceptAnnotation(acceptingAnnotation.note.id);
                    }
                    setAcceptingAnnotation(null);
                  }}
                >
                  {acceptingAnnotation?.note.interpretation === 'cancel_line'
                    ? 'Accept and cancel'
                    : 'Accept'}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <AlertDialog
            open={Boolean(rejectingAnnotation)}
            onOpenChange={(next) => !next && setRejectingAnnotation(null)}
          >
            <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
              <AlertDialogHeader>
                <AlertDialogTitle>Reject this note?</AlertDialogTitle>
                <AlertDialogDescription>
                  Nothing is applied. The note stays on the record as rejected,
                  with your reason.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <div className="space-y-1.5">
                <label
                  className="text-xs font-medium"
                  htmlFor="po-line-annot-reject-note"
                >
                  Reason
                </label>
                <Textarea
                  id="po-line-annot-reject-note"
                  rows={3}
                  value={rejectNote}
                  onChange={(event) => setRejectNote(event.target.value)}
                  placeholder="Why this does not change the PO"
                />
              </div>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep it open</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  disabled={!rejectNote.trim()}
                  onClick={() => {
                    if (rejectingAnnotation) {
                      lastActionedAnnotationId.current =
                        rejectingAnnotation.note.id;
                      lastActionedLineId.current = rejectingAnnotation.lineId;
                      void onRejectAnnotation(
                        rejectingAnnotation.note.id,
                        rejectNote.trim(),
                      );
                    }
                    setRejectingAnnotation(null);
                  }}
                >
                  Reject the note
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          {editingAnnotation && (
            <POIntakeAnnotationEditDialog
              annotation={editingAnnotation}
              saving={savingAnnotationIds.includes(editingAnnotation.id)}
              onClose={() => setEditingAnnotation(null)}
              onSubmit={async (body) => {
                const note = editingAnnotation;
                await onEditAnnotation(note.id, body);
                setEditingAnnotation(null);
                // An edit resolves the note the same way an accept does: whichever line's
                // panel opened this dialog, that is where focus moves on from.
                const fromLine = lines.find((line) =>
                  (annotationsByLineNo.get(line.line_no) ?? []).some(
                    (candidate) => candidate.id === note.id,
                  ),
                );
                lastActionedAnnotationId.current = note.id;
                lastActionedLineId.current = fromLine?.id ?? null;
              }}
            />
          )}

          {focusedLineId && (
            <p className="sr-only" aria-live="polite">
              {`Line ${lines.find((line) => line.id === focusedLineId)?.line_no ?? ''} in focus`}
            </p>
          )}
        </div>
      </LiveRowsContext.Provider>
    </LiveColumnsContext.Provider>
  );
});

/** Why the Suggested pill is there, in plain words (crew pass item 4). */
function suggestionTitle(line: POVersionLine): string {
  const parts: string[] = [];
  if (line.resolution_source === 'suggested') {
    parts.push(
      `The code on the paper did not exactly match one of our codes, so ${
        line.resolved_product_code ?? 'a product'
      } is suggested. Accept it or change it.`,
    );
  }
  if (line.qty_suggested) {
    parts.push(
      `The quantity was worked out from the amount divided by the unit price. Accept it or change it.`,
    );
  }
  return parts.join(' ');
}

/**
 * The product picker on one line. The products the matcher offered come first (AC-U3), then
 * the catalogue search, without repeating an offered product.
 */
function LineProductPicker({
  id,
  value,
  matchOptions,
  fetchProducts,
  selectedOption,
  onChange,
}: {
  id: string;
  value: string;
  matchOptions?: POLineMatchOption[];
  fetchProducts: (query: string) => Promise<ProductOption[]>;
  selectedOption?: { value: string; label: string };
  onChange: (value: string) => void;
}) {
  const fetchOptions = React.useCallback(
    async (query: string) => {
      const rows = await fetchProducts(query);
      const needle = query.trim().toLowerCase();
      const offered: ProductOption[] = (matchOptions ?? [])
        .filter(
          (option) =>
            !needle ||
            `${option.product_code ?? ''} ${option.product_name ?? ''}`
              .toLowerCase()
              .includes(needle),
        )
        .map((option) => ({
          value: option.product_id,
          label: option.product_code ?? option.product_name ?? 'Product',
          description: option.product_name ?? undefined,
        }));
      if (offered.length === 0) return rows;
      const offeredIds = new Set(offered.map((option) => option.value));
      return [...offered, ...rows.filter((row) => !offeredIds.has(row.value))];
    },
    [fetchProducts, matchOptions],
  );

  return (
    <SearchableSelect
      id={id}
      value={value}
      size="sm"
      clearable
      fetchOptions={fetchOptions}
      selectedOption={selectedOption}
      placeholder="Not matched"
      emptyMessage="No products match"
      onChange={onChange}
    />
  );
}

function describeLine(line: POVersionLine): string {
  const parts = [
    `Line ${line.line_no}`,
    line.stock_code_raw ?? undefined,
    `${formatQty(line.qty)} ${line.uom_raw ?? ''}`.trim(),
    formatMyrExact(line.amount),
  ].filter(Boolean);
  return parts.join(', ');
}

/**
 * The line's handwritten notes, collapsed to one compact indicator (owner hand test 25 Sep
 * 2026, item 2): the stacked note cards that used to sit under every flagged row read as
 * noise ("looks messy and bulky, like so many expanded sections") once more than one or two
 * lines carried a note. One icon-and-count button per row instead, opening a popover with the
 * same three actions the card offered - row height stays the grid's ordinary one line whether
 * a line has zero notes or five.
 */
function LineNotesIndicator({
  line,
  notes,
  readOnly,
  open,
  onOpenChange,
  savingAnnotationIds,
  onShowPage,
  onAccept,
  onEdit,
  onReject,
}: {
  line: POVersionLine;
  /** Already filtered to what this reader should see: every note for a viewer, only the
   *  unreviewed ones for an editor (a resolved note has nothing left for them to do). */
  notes: POAnnotation[];
  readOnly: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  savingAnnotationIds: string[];
  onShowPage: (page: number) => void;
  onAccept: (note: POAnnotation) => void;
  onEdit: (note: POAnnotation) => void;
  onReject: (note: POAnnotation) => void;
}) {
  if (notes.length === 0) return null;

  const unreviewedCount = notes.filter(
    (note) => note.state === 'proposed',
  ).length;
  const label = `${notes.length} note${notes.length === 1 ? '' : 's'}${
    unreviewedCount > 0 ? ' to review' : ''
  } on line ${line.line_no}`;

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      {/* `cellWrap` (the caller) puts an onClick on the whole cell that focuses the line -
          harmless on its own, but this trigger and everything in the portalled content below
          are still part of the SAME REACT tree as that div (a portal only moves where a node
          paints, not where its events bubble), so a plain click would also fire that outer
          handler. That collided with the popover's own Page-N button: clicking it called
          onShowPage(note's page) AND, via the bubble, onFocusLine(line) -> setPage(the LINE's
          own page), and the second call always won. Stopped at the source instead of chasing
          it through every action inside. */}
      <PopoverTrigger asChild onClick={(event) => event.stopPropagation()}>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={`h-6 gap-1 px-1.5 text-[11px] ${
            unreviewedCount > 0
              ? 'border-amber-500/50 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:bg-amber-950/30 dark:text-amber-300'
              : ''
          }`}
          aria-label={label}
          title={label}
        >
          <StickyNote className="size-3" aria-hidden />
          {notes.length}
        </Button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          align="start"
          className="w-80 space-y-2"
          onClick={(event) => event.stopPropagation()}
        >
          {notes.map((note, index) => {
            const saving = savingAnnotationIds.includes(note.id);
            const noteLabel =
              notes.length > 1 ? `note ${index + 1} on` : 'the note on';
            return (
              <div
                key={note.id}
                className="space-y-1.5 rounded-md border border-border px-3 py-2 last:mb-0"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge
                    variant={
                      note.state === 'proposed' ? 'warning' : 'secondary'
                    }
                    className="text-[11px]"
                  >
                    {note.state === 'rejected'
                      ? `Rejected: ${annotationBadgeLabel(note)}`
                      : annotationBadgeLabel(note)}
                  </Badge>
                  {note.written_date && (
                    <span className="text-xs text-muted-foreground">
                      {note.written_date}
                    </span>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => onShowPage(note.page_no)}
                  >
                    {`Page ${note.page_no}`}
                  </Button>
                </div>
                <p
                  className="text-sm break-words"
                  title={note.raw_text ?? undefined}
                >
                  {note.raw_text || (
                    <span className="text-muted-foreground">
                      Nothing legible was read
                    </span>
                  )}
                </p>
                {!readOnly && note.state === 'proposed' && (
                  <div className="flex flex-wrap items-center gap-1 pt-0.5">
                    <Button
                      type="button"
                      size="sm"
                      disabled={saving}
                      aria-label={`Accept ${noteLabel} line ${line.line_no}`}
                      onClick={() => onAccept(note)}
                    >
                      {saving ? (
                        <Loader2
                          className="size-3.5 animate-spin"
                          aria-hidden
                        />
                      ) : (
                        <Check className="size-3.5" aria-hidden />
                      )}
                      Accept
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={saving}
                      aria-label={`Edit ${noteLabel} line ${line.line_no}`}
                      onClick={() => onEdit(note)}
                    >
                      <Pencil className="size-3.5" aria-hidden />
                      Edit
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={saving}
                      aria-label={`Reject ${noteLabel} line ${line.line_no}`}
                      onClick={() => onReject(note)}
                    >
                      <X className="size-3.5" aria-hidden />
                      Reject
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

const LiveColumnsContext = React.createContext<ColumnDef<POVersionLine>[]>([]);

/** The one `cell` the table ever sees: renders the current definition of its column. */
function LiveCell(context: CellContext<POVersionLine, unknown>) {
  const live = React.useContext(LiveColumnsContext);
  const definition = live.find(
    (column) =>
      (column.id ?? (column as { accessorKey?: string }).accessorKey) ===
      context.column.id,
  );
  const render = definition?.cell;
  return (
    <>{typeof render === 'function' ? render(context) : (render ?? null)}</>
  );
}

interface LiveRows {
  drafts: Record<string, RowDraft>;
  setDraft: (
    lineId: string,
    field: NumericField,
    value: string | undefined,
  ) => void;
  commitNumber: (
    line: POVersionLine,
    field: NumericField,
    label: string,
  ) => void;
  savingLineIds: string[];
}

const LiveRowsContext = React.createContext<LiveRows>({
  drafts: {},
  setDraft: () => undefined,
  commitNumber: () => undefined,
  savingLineIds: [],
});

function SavingSpinner({ lineId }: { lineId: string }) {
  const { savingLineIds } = React.useContext(LiveRowsContext);
  if (!savingLineIds.includes(lineId)) return null;
  return (
    <Loader2
      className="size-3 animate-spin text-muted-foreground"
      aria-hidden
    />
  );
}

/**
 * The Flag cell's row of badges, on one line that never wraps: a badge appearing or going
 * must not change the row height (owner hand test: the row jumped on every save). The
 * arithmetic badge follows the typed qty / unit price live.
 */
function FlagRow({
  line,
  children,
}: {
  line: POVersionLine;
  children: React.ReactNode;
}) {
  const { drafts } = React.useContext(LiveRowsContext);
  const { expected, ok } = liveFigures(line, drafts[line.id]);
  const arithmetic = ok
    ? null
    : expected
      ? `Should be ${formatMyrExact(expected)}`
      : 'Does not multiply out';
  const title = [
    arithmetic,
    line.is_cancelled ? 'Cancelled' : null,
    !line.resolved_product_id ? 'No product' : null,
    hasSuggestion(line) ? 'Suggested' : null,
    line.resolution_source === 'manual' ? 'Matched by hand' : null,
  ]
    .filter(Boolean)
    .join(', ');
  return (
    <div
      className="flex items-center gap-1 overflow-hidden whitespace-nowrap"
      title={title || undefined}
    >
      {arithmetic && (
        <Badge
          variant="destructive"
          className="text-[11px]"
          title={
            expected
              ? `Quantity times unit price is ${formatMyrExact(expected)}`
              : undefined
          }
        >
          {arithmetic}
        </Badge>
      )}
      {children}
    </div>
  );
}

/**
 * A qty / unit price / amount box: the shared `NumberInput`, controlled by the grid's draft so
 * it keeps exactly what is typed and is never remounted by a save. Commits on blur or Enter;
 * Escape puts back what the server holds.
 */
function NumberCell({
  line,
  field,
  readOnly,
  label,
}: {
  line: POVersionLine;
  field: NumericField;
  readOnly: boolean;
  label: string;
}) {
  const { drafts, setDraft, commitNumber } = React.useContext(LiveRowsContext);
  const draft = drafts[line.id];
  const value =
    field === 'amount'
      ? amountBox(line, draft)
      : (draft?.[field] ?? boxFigure(field, line[field]));
  const invalid = field === 'amount' && !liveFigures(line, draft).ok;
  const onDraft = (next: string | undefined) => setDraft(line.id, field, next);
  const onCommit = (name: string) => commitNumber(line, field, name);
  const escaping = React.useRef(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // The box is uncontrolled so it keeps exactly what is typed ("1." included: a controlled
  // number box is re-set after every keystroke). A figure from outside - the server's echo,
  // Escape, a refused save, the live amount - is written in only when it is a DIFFERENT
  // number from what the box holds, so "1" never turns into "1.0000".
  React.useLayoutEffect(() => {
    const node = inputRef.current;
    if (node && parseNumberDraft(node.value) !== parseNumberDraft(value)) {
      node.value = value;
    }
  }, [value]);

  if (readOnly) {
    const shown = boxFigure(field, line[field]);
    return (
      <span
        className={`block truncate text-right text-sm tabular-nums ${line.is_cancelled ? 'line-through' : ''}`}
        title={shown}
      >
        {shown || '-'}
      </span>
    );
  }

  return (
    <NumberInput
      ref={inputRef}
      defaultValue={value}
      aria-label={label}
      title={value}
      inputMode="decimal"
      className={`h-8 text-right tabular-nums ${
        invalid ? 'border-destructive focus-visible:ring-destructive/30' : ''
      } ${line.is_cancelled ? 'line-through' : ''}`}
      onChange={(event) => onDraft(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          event.currentTarget.blur();
        }
        if (event.key === 'Escape') {
          escaping.current = true;
          onDraft(undefined);
          event.currentTarget.blur();
        }
      }}
      onBlur={() => {
        if (escaping.current) {
          escaping.current = false;
          return;
        }
        onCommit(label);
      }}
    />
  );
}

/**
 * Cell-commit editing, deliberately NOT the staged `InlineLineTable` paradigm the
 * quotation editor uses: these rows are the extractor's reading of the customer's paper,
 * corrected one misread cell at a time against the scan beside the grid, and each
 * correction is a fact worth keeping the moment it is typed. The full argument is
 * ADR-0008; a third editing paradigm needs that ADR revisited first.
 */
function CellInput({
  line,
  field,
  value,
  readOnly,
  label,
  onCommit,
}: {
  line: POVersionLine;
  field: string;
  value: string;
  readOnly: boolean;
  label: string;
  onCommit: (value: string) => void;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  if (readOnly) {
    return (
      <span
        className={`block truncate text-sm ${line.is_cancelled ? 'line-through' : ''}`}
        title={value}
      >
        {value || '-'}
      </span>
    );
  }

  return (
    <Input
      // Remount when the server's value changes, so an uncontrolled cell never shows a
      // stale reading after a card is applied or a save is refused.
      key={`${line.id}-${field}-${value}`}
      ref={inputRef}
      defaultValue={value}
      aria-label={label}
      title={value}
      className={`h-8 ${line.is_cancelled ? 'line-through' : ''}`}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          inputRef.current?.blur();
        }
        if (event.key === 'Escape') {
          if (inputRef.current) inputRef.current.value = value;
          inputRef.current?.blur();
        }
      }}
      onBlur={(event) => {
        const next = event.target.value.trim();
        if (next === value) return;
        onCommit(next);
      }}
    />
  );
}
