'use client';

import * as React from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Ban, Check, Filter, Loader2, Pencil, RotateCcw, X } from 'lucide-react';
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
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
// The shared products `/select` mapper. Its name says "variant" because that screen needed
// it first; the endpoint and the shape are the generic ones.
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import type {
  POAnnotation,
  POAnnotationEditBody,
  POLineUpdateBody,
  POVersionLine,
} from '../../_shared/types/poIntake.types';
import { PO_INTERPRETATION_LABELS } from '../../_shared/types/poIntake.types';
import { formatMyrExact, formatQty, isDecimalString, multiplyMoney } from '../../_shared/lib/money';
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
export const PO_INTAKE_LINES_LISTING_KEY = 'projects.projects.view::po-intake-lines';

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
  onAcceptAnnotation: (annotationId: string, note?: string | null) => Promise<void>;
  onEditAnnotation: (annotationId: string, body: POAnnotationEditBody) => Promise<void>;
  onRejectAnnotation: (annotationId: string, note: string) => Promise<void>;
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

/** How many lines still have a note nobody has looked at, as a sentence with a number in it. */
export function describeAnnotationHealth(count: number): string {
  return `${count} line${count === 1 ? '' : 's'} with handwriting to review`;
}

/** A line our arithmetic disagrees with, one with no product, or one that was cancelled. */
export function isFlaggedLine(line: POVersionLine): boolean {
  return !line.arithmetic_ok || !line.resolved_product_id || line.is_cancelled;
}

/**
 * A line that wants a person to do something. A cancelled line is deliberately NOT one of
 * these: somebody already decided about it by accepting a card, so counting it as work
 * outstanding would mean accepting a cancellation ADDS to the pile.
 */
export function lineNeedsAttention(line: POVersionLine): boolean {
  return !line.is_cancelled && (!line.arithmetic_ok || !line.resolved_product_id);
}

/**
 * The 52 lines, editable in place.
 *
 * Cells are UNCONTROLLED and commit on blur. A controlled input would re-render the whole
 * grid on every keystroke, and a person correcting a misread quantity is typing into a table
 * of fifty-two rows. Escape puts the cell back to what the server holds.
 *
 * Numeric cells are text inputs, not `type="number"`: money and quantity are strings from
 * the API to the API, and a number input invites the float round trip the contract forbids.
 *
 * The real task on this document is three exceptions out of fifty-two rows, so the flagged
 * lines can be shown on their own. That filter starts OFF: somebody reconciling a total has
 * to see the whole document first, and a screen that hid rows before being asked would make
 * the totals at the top unverifiable.
 */
export const POIntakeLinesGrid = React.forwardRef<POIntakeLinesGridHandle, Props>(
  function POIntakeLinesGrid(
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
    },
    ref,
  ) {
    const rowRefs = React.useRef<Record<string, HTMLElement | null>>({});
    const [confirming, setConfirming] = React.useState<{
      kind: 'cancel' | 'clear-product';
      line: POVersionLine;
    } | null>(null);
    const [flaggedOnly, setFlaggedOnly] = React.useState(false);
    // A row asked for while it is filtered out cannot be scrolled to until it mounts.
    const pendingFocusId = React.useRef<string | null>(null);

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
    const [editingAnnotation, setEditingAnnotation] = React.useState<POAnnotation | null>(
      null,
    );
    const [rejectNote, setRejectNote] = React.useState('');
    // Which note (and which row it was cleared from) to watch for, so that once the parent's
    // data confirms it is no longer proposed, focus moves on to the next warning on its own
    // rather than leaving the reader to scroll and find it.
    const lastActionedAnnotationId = React.useRef<string | null>(null);
    const lastActionedLineId = React.useRef<string | null>(null);

    const flagged = React.useMemo(() => lines.filter(isFlaggedLine), [lines]);
    const attentionCount = React.useMemo(
      () => lines.filter(lineNeedsAttention).length,
      [lines],
    );
    const cancelledCount = React.useMemo(
      () => lines.filter((line) => line.is_cancelled).length,
      [lines],
    );
    const visibleLines = flaggedOnly ? flagged : lines;
    const nothingLeftToShow = flaggedOnly && visibleLines.length === 0;
    // When the filter has emptied itself the way back lives in the all-clear panel, so the
    // toolbar toggle stands down rather than offering the same thing twice.
    const showFilterToggle = (flagged.length > 0 || flaggedOnly) && !nothingLeftToShow;

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
      (lineId: string) => {
        const line = lines.find((item) => item.id === lineId);
        if (!line) return;
        onFocusLine(line);
        // The banner and the handwriting notes both point at specific lines, and a note can
        // name a perfectly healthy one. Landing on it has to work with the filter on, so the
        // filter gives way rather than swallowing the jump.
        if (flaggedOnly && !isFlaggedLine(line)) {
          pendingFocusId.current = lineId;
          setFlaggedOnly(false);
          return;
        }
        scrollToLine(lineId);
      },
      [lines, onFocusLine, flaggedOnly, scrollToLine],
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
          linesWithUnreviewedAnnotations.find((line) => line.line_no > anchorLineNo) ??
          linesWithUnreviewedAnnotations[0];
        focusLineInternal(next.id);
      },
      [linesWithUnreviewedAnnotations, lines, focusLineInternal],
    );

    React.useImperativeHandle(ref, () => ({
      focusLine: focusLineInternal,
      focusFirstUnreviewedAnnotation: () => {
        if (linesWithUnreviewedAnnotations.length === 0) return false;
        focusLineInternal(linesWithUnreviewedAnnotations[0].id);
        return true;
      },
    }));

    React.useEffect(() => {
      const pending = pendingFocusId.current;
      if (!pending) return;
      pendingFocusId.current = null;
      scrollToLine(pending);
    }, [flaggedOnly, scrollToLine]);

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
      goToNextUnreviewed(fromLineId);
    }, [annotations, goToNextUnreviewed]);

    const openAcceptAnnotation = React.useCallback(
      (note: POAnnotation, lineId: string) => setAcceptingAnnotation({ note, lineId }),
      [],
    );
    const openRejectAnnotation = React.useCallback((note: POAnnotation, lineId: string) => {
      setRejectNote('');
      setRejectingAnnotation({ note, lineId });
    }, []);

    const fetchProducts = React.useCallback(async (query: string) => {
      const rows = await getProductsForVariantSelect(query || undefined);
      return rows.map((row) => ({
        value: row.id,
        label: row.product_code,
        description: row.product_name,
      }));
    }, []);

    const commit = React.useCallback(
      (line: POVersionLine, body: POLineUpdateBody) => {
        void onUpdateLine(line.id, body);
      },
      [onUpdateLine],
    );

    const columns = React.useMemo<ColumnDef<POVersionLine>[]>(() => {
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
          header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <span className="flex items-center gap-1 text-sm tabular-nums">
                {row.original.line_no}
                {savingLineIds.includes(row.original.id) && (
                  <Loader2
                    className="size-3 animate-spin text-muted-foreground"
                    aria-hidden
                  />
                )}
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
          header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="qty"
                value={row.original.qty}
                numeric
                readOnly={readOnly}
                label={`Quantity on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { qty: value })}
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
          header: ({ column }) => <DataGridColumnHeader title="UOM" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="uom_raw"
                value={row.original.uom_raw ?? ''}
                readOnly={readOnly}
                label={`UOM on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { uom_raw: value || null })}
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
              <CellInput
                line={row.original}
                field="unit_price"
                value={row.original.unit_price}
                numeric
                readOnly={readOnly}
                label={`Unit price on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { unit_price: value })}
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
          header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="amount"
                value={row.original.amount}
                numeric
                invalid={!row.original.arithmetic_ok}
                readOnly={readOnly}
                label={`Amount on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { amount: value })}
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
          header: ({ column }) => <DataGridColumnHeader title="Check" column={column} />,
          cell: ({ row }) => {
            const line = row.original;
            const expected = multiplyMoney(line.qty, line.unit_price);
            const lineNotes = annotationsByLineNo.get(line.line_no) ?? [];
            return cellWrap(
              line,
              <div className="flex flex-wrap items-center gap-1">
                {!line.arithmetic_ok && (
                  <Badge
                    variant="destructive"
                    className="text-[11px]"
                    title={
                      expected
                        ? `Quantity times unit price is ${formatMyrExact(expected)}`
                        : undefined
                    }
                  >
                    {expected
                      ? `Should be ${formatMyrExact(expected)}`
                      : 'Does not multiply out'}
                  </Badge>
                )}
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
                {line.resolution_source === 'manual' && (
                  <Badge variant="outline" className="text-[11px]">
                    Matched by hand
                  </Badge>
                )}
                {readOnly
                  ? // A viewer without edit rights gets no action panel (there is
                    // nothing for them to do about it), but a note still awaiting
                    // review must still show here, muted - otherwise a read-only
                    // viewer sees no pending handwriting at all.
                    lineNotes.map((note) => (
                      <Badge
                        key={note.id}
                        variant="secondary"
                        className="text-[11px] opacity-70"
                        title={note.raw_text ?? undefined}
                      >
                        {note.state === 'rejected'
                          ? `Rejected: ${annotationBadgeLabel(note)}`
                          : note.state === 'proposed'
                            ? `Pending: ${annotationBadgeLabel(note)}`
                            : annotationBadgeLabel(note)}
                      </Badge>
                    ))
                  : lineNotes
                      .filter((note) => note.state === 'proposed')
                      .map((note) => (
                        <Badge
                          key={note.id}
                          variant="warning"
                          className="text-[11px]"
                          title={note.raw_text ?? undefined}
                        >
                          {annotationBadgeLabel(note)}
                        </Badge>
                      ))}
              </div>,
            );
          },
          size: 190,
          minSize: 130,
          meta: {
            headerTitle: 'Check',
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
                  <SearchableSelect
                    id={`po-line-${line.line_no}-product`}
                    value={line.resolved_product_id ?? ''}
                    size="sm"
                    clearable
                    fetchOptions={fetchProducts}
                    selectedOption={selected}
                    placeholder="Not matched"
                    emptyMessage="No products match"
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
            // Below the row, full width: the note the pencil left on this line, and the
            // three ways to answer it, right where the warning badge already pointed.
            expandedContent: (line: POVersionLine) => {
              const unreviewed = (annotationsByLineNo.get(line.line_no) ?? []).filter(
                (note) => note.state === 'proposed',
              );
              if (unreviewed.length === 0) return null;
              return (
                <LineAnnotationPanel
                  line={line}
                  notes={unreviewed}
                  savingAnnotationIds={savingAnnotationIds}
                  onShowPage={onShowPage}
                  onAccept={(note) => openAcceptAnnotation(note, line.id)}
                  onEdit={(note) => setEditingAnnotation(note)}
                  onReject={(note) => openRejectAnnotation(note, line.id)}
                  onSkip={() => goToNextUnreviewed(line.id)}
                />
              );
            },
          },
        },
      ];
    }, [
      annotationsByLineNo,
      commit,
      fetchProducts,
      goToNextUnreviewed,
      onFocusLine,
      onShowPage,
      openAcceptAnnotation,
      openRejectAnnotation,
      readOnly,
      savingAnnotationIds,
      savingLineIds,
    ]);

    // Every line with an unreviewed note is expanded on its own: the whole point is that
    // there is nothing to click open, the answer is already sitting under the row.
    const expandedState = React.useMemo(() => {
      const state: Record<string, boolean> = {};
      if (readOnly) return state;
      for (const line of linesWithUnreviewedAnnotations) state[line.id] = true;
      return state;
    }, [linesWithUnreviewedAnnotations, readOnly]);

    const table = useReactTable({
      columns,
      data: visibleLines,
      state: { expanded: expandedState },
      getRowId: (row) => row.id,
      getCoreRowModel: getCoreRowModel(),
      getExpandedRowModel: getExpandedRowModel(),
      columnResizeMode: 'onChange',
    });

    return (
      <div className="min-w-0 space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="min-w-0 text-xs text-muted-foreground">
            {describeLineHealth(lines.length, attentionCount, cancelledCount)}
          </p>
          {showFilterToggle && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0"
              aria-pressed={flaggedOnly}
              onClick={() => setFlaggedOnly((previous) => !previous)}
            >
              <Filter className="size-3.5" aria-hidden />
              {flaggedOnly
                ? `Show all ${lines.length} lines`
                : `Show only these ${flagged.length}`}
            </Button>
          )}
        </div>

        {!readOnly && linesWithUnreviewedAnnotations.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-50/60 px-3 py-1.5 dark:bg-amber-950/20">
            <span className="text-xs font-medium text-amber-900 dark:text-amber-300">
              {describeAnnotationHealth(linesWithUnreviewedAnnotations.length)}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 shrink-0 px-2 text-[11px]"
              onClick={() => goToNextUnreviewed(focusedLineId)}
            >
              Next unreviewed
            </Button>
          </div>
        )}

        {nothingLeftToShow ? (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-50 px-6 py-10 text-center dark:bg-emerald-950/30">
            <h3 className="text-sm font-semibold text-emerald-900 dark:text-emerald-300">
              Nothing left to fix
            </h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-emerald-900/80 dark:text-emerald-300/80">
              Every line adds up and resolves to a product.
            </p>
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              onClick={() => setFlaggedOnly(false)}
            >
              {`Show all ${lines.length} lines`}
            </Button>
          </div>
        ) : (
          <DataGrid
            table={table}
            recordCount={visibleLines.length}
            isLoading={false}
            listingKey={PO_INTAKE_LINES_LISTING_KEY}
            tableLayout={{
              width: 'fixed',
              columnsResizable: true,
              headerSticky: true,
              // The ScrollArea below already bounds the vertical viewport
              // (M5-05: DataGridScroller's own max-height default would
              // double-bound it otherwise).
              scrollerMaxHeight: false,
            }}
          >
            <div className="min-w-0 rounded-lg border border-border">
              {/* The cap goes on the scrolling VIEWPORT, never on the box around it. Radix
                  gives the viewport `h-full`, and a percentage height against a parent
                  that only has a max-height resolves to auto: the viewport grew to all 51
                  rows and the root clipped it, so every row rendered and none below the
                  fold could be reached. `type="auto"` enables the overflow from the
                  content rather than from a pointer hover, so a wheel, a keyboard and a
                  jump from the banner all reach the last line. */}
              <ScrollArea
                type="auto"
                className="w-full"
                viewportClassName="max-h-[calc(100vh-14rem)]"
              >
                <DataGridTable />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            </div>
          </DataGrid>
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
                {confirming?.kind === 'cancel' ? 'Cancel the line' : 'Remove it'}
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
                    lastActionedAnnotationId.current = acceptingAnnotation.note.id;
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
                Nothing is applied. The note stays on the record as rejected, with your
                reason.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="po-line-annot-reject-note">
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
                    lastActionedAnnotationId.current = rejectingAnnotation.note.id;
                    lastActionedLineId.current = rejectingAnnotation.lineId;
                    void onRejectAnnotation(rejectingAnnotation.note.id, rejectNote.trim());
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
    );
  },
);

/**
 * How much of this document is actually work, as a sentence with numbers in it. A bare
 * toggle would leave "is this a clean read?" unanswered, which is the question.
 *
 * Cancelled lines are counted separately from lines needing attention: they are in the
 * filtered view because they are exceptions worth seeing, but they are not outstanding work.
 */
export function describeLineHealth(
  total: number,
  attention: number,
  cancelled: number,
): string {
  if (total === 0) return 'No lines';
  const cancelledClause =
    cancelled === 0
      ? ''
      : `${cancelled} ${cancelled === 1 ? 'is' : 'are'} cancelled`;

  if (attention === 0) {
    const clean = `All ${total} lines add up and resolve`;
    return cancelledClause ? `${clean}, ${cancelledClause}` : clean;
  }

  const head = `${attention} of ${total} lines need attention`;
  return cancelledClause ? `${head}, and ${cancelledClause}` : head;
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
 * The note itself, under the line it warns about, with the three ways to answer it. This is
 * the whole point of moving handwriting onto the grid: a person clears it here and the next
 * one is where they land, rather than scrolling to a separate card and back for every note.
 *
 * Enter answers with the confirm step Accept already asks for (the first note if there is
 * more than one); Escape skips to the next line without touching this one. Both live only on
 * this panel, never the row itself, so tabbing through a cell never accidentally does either.
 */
function LineAnnotationPanel({
  line,
  notes,
  savingAnnotationIds,
  onShowPage,
  onAccept,
  onEdit,
  onReject,
  onSkip,
}: {
  line: POVersionLine;
  notes: POAnnotation[];
  savingAnnotationIds: string[];
  onShowPage: (page: number) => void;
  onAccept: (note: POAnnotation) => void;
  onEdit: (note: POAnnotation) => void;
  onReject: (note: POAnnotation) => void;
  onSkip: () => void;
}) {
  if (notes.length === 0) return null;

  return (
    <div
      className="space-y-2 border-t border-amber-500/30 bg-amber-50/60 px-4 py-3 dark:bg-amber-950/20"
      onKeyDown={(event) => {
        // A button inside this panel (Accept / Edit / Reject / Page N / Skip) already
        // answers Enter itself - the native activate. Without this guard the keydown
        // still bubbles up here afterwards, so pressing Enter on the focused Reject
        // button both rejects it AND calls `onAccept(notes[0])`, opening the accept
        // dialog on top of whatever the button's own click just did.
        const target = event.target as HTMLElement;
        if (target.closest('button')) return;
        if (event.key === 'Enter') {
          event.preventDefault();
          onAccept(notes[0]);
        } else if (event.key === 'Escape') {
          event.preventDefault();
          onSkip();
        }
      }}
    >
      {notes.map((note, index) => {
        const saving = savingAnnotationIds.includes(note.id);
        const noteLabel = notes.length > 1 ? `note ${index + 1} on` : 'the note on';
        return (
          <div
            key={note.id}
            className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-amber-500/40 bg-white px-3 py-2 dark:bg-transparent"
          >
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="warning" className="text-[11px]">
                  {annotationBadgeLabel(note)}
                </Badge>
                {note.written_date && (
                  <span className="text-xs text-muted-foreground">{note.written_date}</span>
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
              <p className="text-sm break-words" title={note.raw_text ?? undefined}>
                {note.raw_text || (
                  <span className="text-muted-foreground">Nothing legible was read</span>
                )}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-1">
              <Button
                type="button"
                size="sm"
                disabled={saving}
                aria-label={`Accept ${noteLabel} line ${line.line_no}`}
                onClick={() => onAccept(note)}
              >
                {saving ? (
                  <Loader2 className="size-3.5 animate-spin" aria-hidden />
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
          </div>
        );
      })}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-[11px]"
        onClick={onSkip}
      >
        Skip to the next unreviewed line
      </Button>
    </div>
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
  numeric,
  invalid,
  readOnly,
  label,
  onCommit,
}: {
  line: POVersionLine;
  field: string;
  value: string;
  numeric?: boolean;
  invalid?: boolean;
  readOnly: boolean;
  label: string;
  onCommit: (value: string) => void;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  if (readOnly) {
    return (
      <span
        className={`block truncate text-sm ${numeric ? 'text-right tabular-nums' : ''} ${line.is_cancelled ? 'line-through' : ''}`}
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
      inputMode={numeric ? 'decimal' : undefined}
      className={`h-8 ${numeric ? 'text-right tabular-nums' : ''} ${
        invalid ? 'border-destructive focus-visible:ring-destructive/30' : ''
      } ${line.is_cancelled ? 'line-through' : ''}`}
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
        if (numeric && !isDecimalString(next)) {
          toast.error(`${label} must be a number`);
          event.target.value = value;
          return;
        }
        onCommit(next);
      }}
    />
  );
}
