'use client';

import * as React from 'react';
import { TriangleAlert } from 'lucide-react';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { changedFieldsOf } from '../../_shared/lib/boardChangeAnnotations';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

/**
 * What the book did to this line: ONE amber hazard icon, and a lightbox behind it.
 *
 * Owner feedback, 13 September 2026: the inline Was / Now block this component used to draw
 * on every changed cell was "abit too big", and the list view - the reading a planner
 * actually lives in - could not stay one line tall with a table inside it. So the cell and
 * the row now carry the same warning triangle a Rejected verdict carries, and the detail
 * moves behind a click: "just show whatever changed", as `x -> y`, and nothing else.
 *
 * The icon is the SAME in the grid and in the list, and the dialog is the same component in
 * both, so the two readings of the board cannot come to say different things about one
 * change.
 */
export function BoardChangeTable({
  annotation,
  column,
  compact = false,
  className,
}: {
  annotation: BoardChangeAnnotation;
  /**
   * Which list column this copy of the icon sits in (AC-C9): `required_date` when the date
   * moved, `outstanding` when the quantity did, `suggested` for the composed suggestion.
   * Read by the tests and by nothing else - the grid has one column and passes none.
   */
  column?: 'required_date' | 'outstanding' | 'suggested';
  /** Inside a board cell, where every pixel costs width. */
  compact?: boolean;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <button
        type="button"
        data-testid={`board-change-icon-${annotation.rowId}`}
        data-column={column}
        aria-label="What changed"
        title="What changed"
        onClick={(event) => {
          // The cell and the row are both clickable surfaces of their own (the cell opens
          // its breakdown, the row opens its decision panel); this icon is a third thing
          // on top of them and must not trigger either.
          event.stopPropagation();
          setOpen(true);
        }}
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded text-amber-600',
          'hover:text-amber-700 focus-visible:outline-none focus-visible:ring-1',
          'focus-visible:ring-amber-500',
          compact ? 'size-4' : 'size-5',
          className,
        )}
      >
        <TriangleAlert className={compact ? 'size-3.5' : 'size-4'} aria-hidden />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          data-testid="board-change-dialog"
          className="max-w-[min(28rem,calc(100vw-2rem))]"
        >
          <DialogHeader>
            <DialogTitle>
              {annotation.lineNo
                ? `What changed, ${annotation.soNumber} (Line ${annotation.lineNo})`
                : `What changed, ${annotation.soNumber} (${annotation.itemCode})`}
            </DialogTitle>
            {/* Radix points the dialog's own `aria-describedby` at a description it expects
                to exist; without one the attribute resolves to nothing and a screen reader is
                handed a dangling id (and the console a warning). One sentence, which is also
                what a first-time reader needs to know about this list. */}
            <DialogDescription>
              Only the fields that moved, then the suggestion.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <BoardChangeSummary annotation={annotation} />
          </DialogBody>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * What changed, and what the engine suggests about it - the lightbox's whole body.
 *
 * Only the fields that MOVED, one line each, as `<label> <old> -> <new>`: a date that did
 * not move says nothing, and a row of dashes is not information. Then the composed
 * suggestion, VERBATIM: the sentence is server-composed because only the engine knows which
 * rung covered what, against which document, for whose order, and re-phrasing it here could
 * only drift from what Confirm will post. Then lateness, once.
 *
 * The shortfall has no line of its own any more (AC-C11): the engine's own label already
 * reads "Short 44 by 22 Aug (was Buy 134)", and a bare "Short 44" beside it was the same
 * fact said twice, the second time with less in it.
 */
export function BoardChangeSummary({
  annotation,
}: {
  annotation: BoardChangeAnnotation;
}) {
  const fields = changedFieldsOf(annotation);
  return (
    <div className="space-y-3 text-sm">
      {fields.length > 0 ? (
        <ul
          data-testid={`board-change-fields-${annotation.rowId}`}
          className="space-y-1"
        >
          {fields.map((field) => {
            // A field with no sides is a statement, not a move (a cancelled line): the label
            // IS the line.
            const line =
              field.from || field.to
                ? `${field.label} ${field.from} → ${field.to}`
                : field.label;
            return (
              <li key={field.key} className="truncate" title={line}>
                {line}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-muted-foreground">
          The book moved this line without changing its quantity, its date or its decision.
        </p>
      )}

      {/* The product this line used to be (S7): ONE line, not a cancelled plus an added
          pair, so the swap reads as the one thing it is. */}
      {annotation.productChangedFrom ? (
        <p
          data-testid={`board-change-product-${annotation.rowId}`}
          className="truncate font-medium"
          title={`Product changed, was ${annotation.productChangedFrom}`}
        >
          {`Product changed, was ${annotation.productChangedFrom}`}
        </p>
      ) : null}

      {/* The suggestion, verbatim (AC-C1). A list, because each line is a separate thing
          that happens to a separate component, and a reader has to be able to count them. */}
      {annotation.suggestionLines.length > 0 ? (
        <ul
          data-testid={`board-change-suggestion-${annotation.rowId}`}
          className="space-y-1 font-medium"
        >
          {annotation.suggestionLines.map((line, index) => (
            <li
              // The engine's order IS the meaning (held first, then new sourcing), and two
              // components can legitimately carry the same sentence, so the position is the
              // only honest key.
              key={`${index}-${line}`}
              data-testid="board-change-suggestion-line"
              className="truncate"
              title={line}
            >
              {line}
            </li>
          ))}
        </ul>
      ) : null}

      {/* Kept, but landing after the date the customer now asks for (S12, AC-C6). Said in
          days, never left for the reader to subtract two dates. */}
      {annotation.lateDays !== null ? (
        <p
          data-testid={`board-change-late-${annotation.rowId}`}
          className="truncate font-medium"
        >
          {`Late by ${annotation.lateDays} day${annotation.lateDays === 1 ? '' : 's'}`}
        </p>
      ) : null}

      {/* Stock that is already physically somewhere else (AC-P3-9). Stated, never reversed:
          a movement is a person's decision, and the plan does not get to undo one. */}
      {annotation.movedTransfer ? (
        <p
          data-testid={`board-change-moved-${annotation.rowId}`}
          className="truncate font-medium"
          title={annotation.movedTransfer}
        >
          {annotation.movedTransfer}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The Was / Now table, kept for the ORDER INQUIRIES worklist alone.
 *
 * That column's own lightbox (`OrderInquiryQtyAnnotationDialog`) is a different journey: a
 * settled amendment, two values, no suggestion and no board behind it, already inside a
 * dialog of its own - so the reading that was too big for a board cell is exactly right
 * there, and putting an icon inside an icon's dialog would not be.
 */
export function BoardChangeWasNowTable({
  annotation,
  compact = false,
  omitDecision = false,
  omitHeader = false,
}: {
  annotation: BoardChangeAnnotation;
  compact?: boolean;
  /**
   * Drop the Decision row (`PLAN-scm-oi-handshake.md`, the Order Inquiries list). An
   * order inquiry row carries a quantity and a date and no decision of its own, and a
   * Decision row reading "Not decided" on both sides would be a fact about nothing.
   */
  omitDecision?: boolean;
  /**
   * Drop the item-code/SO-number line (review of PR #471: the Order Inquiries lightbox
   * already states both in its `DialogTitle`/`DialogDescription`, so this table's own
   * header would repeat them for no reason).
   */
  omitHeader?: boolean;
}) {
  const text = compact ? 'text-[10px]' : 'text-xs';
  return (
    <div
      data-testid={`board-change-${annotation.rowId}`}
      className={cn(
        'w-full rounded border border-amber-300 bg-amber-50/70 px-1.5 py-1 text-start',
        text,
      )}
    >
      {omitHeader ? null : (
        <div className="flex items-center justify-between gap-1">
          {/* `lineNo` 0 means the caller has no line number to print - the order inquiry
              list, whose row IS the line - so the item code stands in its place. */}
          <span className="truncate font-medium text-amber-900" title={annotation.itemCode}>
            {annotation.lineNo ? `Line ${annotation.lineNo}` : annotation.itemCode}
          </span>
          <span className="truncate text-amber-800" title={annotation.soNumber}>
            {annotation.soNumber}
          </span>
        </div>
      )}
      <ScrollArea>
        <table className="w-full table-fixed">
          <thead>
            <tr className="text-amber-800">
              <th scope="col" className="w-[26%] text-start font-normal">
                <span className="sr-only">What changed</span>
              </th>
              <th scope="col" className="w-[37%] text-start font-normal">
                Was
              </th>
              <th scope="col" className="w-[37%] text-start font-normal">
                Now
              </th>
            </tr>
          </thead>
          <tbody className="text-amber-900">
            <tr>
              <th scope="row" className="text-start font-normal text-amber-800">
                Qty
              </th>
              <td className="tabular-nums">{annotation.was.qty ?? '-'}</td>
              <td className="font-medium tabular-nums" data-testid="change-now-qty">
                {annotation.closed ? 'Cancelled' : annotation.now.qty ?? '-'}
              </td>
            </tr>
            <tr>
              <th scope="row" className="text-start font-normal text-amber-800">
                Date
              </th>
              <td className="tabular-nums">
                {annotation.was.date ? formatDateInMalaysia(annotation.was.date) : '-'}
              </td>
              <td className="font-medium tabular-nums">
                {annotation.closed
                  ? 'Cancelled'
                  : annotation.now.date
                    ? formatDateInMalaysia(annotation.now.date)
                    : '-'}
              </td>
            </tr>
            <tr className={omitDecision ? 'hidden' : undefined}>
              <th scope="row" className="text-start font-normal align-top text-amber-800">
                Decision
              </th>
              <td className="truncate align-top" title={annotation.was.decision ?? ''}>
                {annotation.was.decision ?? 'Not decided'}
              </td>
              <td
                className="truncate align-top font-medium"
                data-testid="change-now-decision"
                title={annotation.now.decision ?? ''}
              >
                {annotation.closed ? 'Cancelled' : annotation.now.decision ?? 'Not decided'}
              </td>
            </tr>
          </tbody>
        </table>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
}

export default BoardChangeTable;
