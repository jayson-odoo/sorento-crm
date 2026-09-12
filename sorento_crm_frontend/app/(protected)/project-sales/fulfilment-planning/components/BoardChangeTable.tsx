'use client';

import * as React from 'react';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

/**
 * What the change did to this line, as a table (AC-P3-2), and what the engine suggests for it
 * (AC-C1).
 *
 * The captain, 25 August 2026: structure, not words. Three rows - Qty, Date, Decision - and
 * two columns, Was and Now. A sentence ("delayed 14 days, quantity down 6") reads fine once
 * and cannot be compared against the line beside it; a table can be scanned down a column.
 *
 * Under the table, the composed suggestion: one line per component, in the engine's own order
 * (held first, then new sourcing), printed VERBATIM. The sentence is server-composed because
 * only the engine knows which rung covered what, against which document, for whose order;
 * re-phrasing it here could only drift from what Confirm will post. Then the two facts a
 * composition cannot carry inside a component - the unit is late by N days (S12), or N is
 * short with nothing able to cover it in time (S11).
 *
 * A line the change CANCELLED reads `Cancelled` across the Now column and states no quantity or
 * date there: there is nothing to deliver, so a zero would be a quantity somebody could act on.
 *
 * NOT a `DataGrid`. It is three rows of two values inside a 150px grid cell, with no sort, no
 * column config and no resize - the same carve-out `FulfilmentBoardMatrix` documents for
 * itself, and for the same reason.
 */
export function BoardChangeTable({
  annotation,
  compact = false,
  omitDecision = false,
  omitHeader = false,
}: {
  annotation: BoardChangeAnnotation;
  /** Inside a board cell, where every character costs width. */
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

      {/* The product this line used to be (S7): ONE row, not a cancelled plus an added
          pair, so the swap reads as the one thing it is. The header above already names the
          NEW product. */}
      {annotation.productChangedFrom ? (
        <p
          data-testid={`board-change-product-${annotation.rowId}`}
          className="truncate font-medium text-amber-900"
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
          className="mt-0.5 space-y-0.5 text-amber-900"
        >
          {annotation.suggestionLines.map((line, index) => (
            <li
              // The engine's order IS the meaning (held first, then new sourcing), and two
              // components can legitimately carry the same sentence, so the position is the
              // only honest key.
              key={`${index}-${line}`}
              data-testid="board-change-suggestion-line"
              className="truncate font-medium"
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
          className="truncate font-medium text-amber-900"
        >
          {`Late by ${annotation.lateDays} day${annotation.lateDays === 1 ? '' : 's'}`}
        </p>
      ) : null}

      {/* Nothing covers this much in time (S11). Shown plainly: CS decides, the engine does
          not quietly promise a date it cannot keep. */}
      {annotation.shortfallQty !== null ? (
        <p
          data-testid={`board-change-short-${annotation.rowId}`}
          className="truncate font-medium text-amber-900"
        >
          {`Short ${annotation.shortfallQty}`}
        </p>
      ) : null}

      {/* Stock that is already physically somewhere else (AC-P3-9). Stated, never reversed:
          a movement is a person's decision, and the plan does not get to undo one. */}
      {annotation.movedTransfer ? (
        <p
          data-testid={`board-change-moved-${annotation.rowId}`}
          className="truncate font-medium text-amber-900"
          title={annotation.movedTransfer}
        >
          {annotation.movedTransfer}
        </p>
      ) : null}
    </div>
  );
}

export default BoardChangeTable;
