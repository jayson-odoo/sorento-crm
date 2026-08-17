'use client';

import * as React from 'react';
import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ColumnBlocker, ColumnState } from '../lib/scheduleTotals';
import { DeliveryScheduleProductPicker } from './DeliveryScheduleProductPicker';

/**
 * The columns that do not reconcile, each one carrying the fix for its own problem.
 *
 * This list used to be a wall of sentences with nothing to press: "The PO version does not
 * order this item" is a diagnosis, and the reviewer's answer to it was "ya I know I need to
 * fix this, but how". Clicking a row scrolled the matrix sideways to the column, which is
 * near the fix but is not the fix. So every blocker now states the problem AND offers the one
 * action that ends it, in the place the problem is read.
 *
 * A row is NOT one big button any more. It holds real buttons (a picker, a link, a jump), and
 * a button inside a button is invalid markup that a keyboard user cannot reach past.
 *
 * Full width, one row per column that does not reconcile, and never truncated: the sentence
 * carries the numbers that say WHAT disagrees, and cut to "Our total is 927. The PO version
 * does not or..." it is decoration. Not the shared DataGrid for the same reason: a fixed
 * table layout keeps its columns from overlapping by truncating what overflows, which is the
 * one thing this section must not do.
 */
export function DeliveryScheduleReconciliationList({
  columns,
  canEdit,
  poHref,
  onJump,
  onFixQuantities,
  onResolveProduct,
}: {
  /** Only the columns that do not reconcile. */
  columns: ColumnState[];
  canEdit: boolean;
  /** The PO version this schedule is checked against, when there is one to open. */
  poHref: string | null;
  onJump: (columnKey: string) => void;
  /** Jump to the column AND put the cursor in the first quantity that can be typed into. */
  onFixQuantities: (columnKey: string) => void;
  onResolveProduct: (columnIndex: number, productId: string) => void;
}) {
  return (
    <ul
      data-testid="reconciliation-list"
      className="divide-y divide-border rounded-lg border border-border"
    >
      {columns.map((column) => {
        const name =
          column.productCode ?? column.customerCode ?? 'Unidentified column';
        return (
          <li
            key={column.key}
            className="flex flex-col gap-2 border-s-2 border-destructive px-3 py-2.5 sm:flex-row sm:gap-4"
          >
            <div className="min-w-0 sm:w-[200px] sm:shrink-0">
              {/* The jump survives, as the column's own name: the reviewer still wants to go
                  and look at it, and a name is a more honest target than a whole row. */}
              <button
                type="button"
                onClick={() => onJump(column.key)}
                aria-label={`Go to ${
                  column.productCode ?? column.customerCode ?? 'the unidentified column'
                } in the schedule`}
                className="break-words rounded-sm text-start text-sm font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
              >
                {name}
              </button>
              {column.productCode && column.customerCode && (
                <span className="mt-0.5 block break-words text-xs text-muted-foreground">
                  {column.customerCode}
                </span>
              )}
            </div>

            {/* Not a nested <ul>: the rows of this list are counted, and a list inside a
                list makes every blocker read as another column to fix. */}
            <div className="min-w-0 flex-1 space-y-2.5">
              {column.blockers.map((blocker) => (
                <div key={blocker.code} className="space-y-1.5">
                  <p
                    data-testid="reconciliation-detail"
                    className="break-words text-sm text-muted-foreground"
                  >
                    {blocker.detail}
                  </p>
                  {canEdit && (
                    // Wraps under the sentence at 375px rather than pushing the row wide.
                    <BlockerActions
                      column={column}
                      blocker={blocker}
                      poHref={poHref}
                      onFixQuantities={onFixQuantities}
                      onResolveProduct={onResolveProduct}
                    />
                  )}
                </div>
              ))}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * One blocker, one next action.
 *
 * Nothing is offered that cannot be carried out: a column with no product has disabled cells,
 * so "Fix the quantities" would land the cursor nowhere, and picking the product is the step
 * that comes first anyway.
 */
function BlockerActions({
  column,
  blocker,
  poHref,
  onFixQuantities,
  onResolveProduct,
}: {
  column: ColumnState;
  blocker: ColumnBlocker;
  poHref: string | null;
  onFixQuantities: (columnKey: string) => void;
  onResolveProduct: (columnIndex: number, productId: string) => void;
}) {
  const picker = (action: string) => (
    <div className="w-full sm:w-[280px]">
      <DeliveryScheduleProductPicker
        idPrefix="schedule-fix"
        columnIndex={column.index}
        customerCode={column.customerCode}
        action={action}
        onPick={(productId) => onResolveProduct(column.index, productId)}
      />
    </div>
  );

  if (blocker.code === 'needs_product') {
    return <div className="flex flex-wrap items-center gap-2">{picker('Pick the product')}</div>;
  }

  if (blocker.code === 'not_on_po') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        {/* The usual cause is not a missing PO line, it is this column resolving to the
            wrong product, so correcting the product leads. Amending the PO is the other
            answer and stays reachable, one step quieter. A column with no product at all
            is already being picked by its own blocker above, so it is not offered twice. */}
        {column.productId && picker('Pick a different product')}
        {poHref && (
          <Button asChild variant="ghost" size="sm">
            <Link href={poHref}>
              Open the PO to amend it
              <ExternalLink className="size-4" aria-hidden />
            </Link>
          </Button>
        )}
      </div>
    );
  }

  if (!column.productId) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onFixQuantities(column.key)}
      >
        Fix the quantities
      </Button>
    </div>
  );
}
