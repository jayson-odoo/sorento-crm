'use client';

import * as React from 'react';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';

/**
 * What the re-uploaded book did to this line, as a table (AC-P3-2).
 *
 * The captain, 25 August 2026: structure, not words. Three rows - Qty, Date, Decision - and
 * two columns, Was and Now. A sentence ("delayed 14 days, quantity down 6") reads fine once
 * and cannot be compared against the line beside it; a table can be scanned down a column.
 *
 * A line the book CLOSED reads `Closed` across the Now column and states no quantity or date
 * there: there is nothing to deliver, so a zero would be a quantity somebody could act on.
 *
 * NOT a `DataGrid`. It is three rows of two values inside a 150px grid cell, with no sort, no
 * column config and no resize - the same carve-out `FulfilmentBoardMatrix` documents for
 * itself, and for the same reason.
 */
export function BoardChangeTable({
  annotation,
  compact = false,
}: {
  annotation: BoardChangeAnnotation;
  /** Inside a board cell, where every character costs width. */
  compact?: boolean;
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
      <div className="flex items-center justify-between gap-1">
        <span className="truncate font-medium text-amber-900" title={annotation.itemCode}>
          {`Line ${annotation.lineNo}`}
        </span>
        <span className="truncate text-amber-800" title={annotation.soNumber}>
          {annotation.soNumber}
        </span>
      </div>
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
              {annotation.closed ? 'Closed' : annotation.now.qty ?? '-'}
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
                ? 'Closed'
                : annotation.now.date
                  ? formatDateInMalaysia(annotation.now.date)
                  : '-'}
            </td>
          </tr>
          <tr>
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
              {annotation.closed ? 'Closed' : annotation.now.decision ?? 'Not decided'}
            </td>
          </tr>
        </tbody>
      </table>

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
