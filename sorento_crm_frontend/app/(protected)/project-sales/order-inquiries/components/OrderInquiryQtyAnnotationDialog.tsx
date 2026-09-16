'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import { ackStateOf, movedNoteOf, previousValueOf } from '../../_shared/lib/orderInquiryAck';
import { BoardChangeWasNowTable } from '../../fulfilment-planning/components/BoardChangeTable';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

/**
 * Whatever the Qty cell's second line used to say, behind the info icon it offers instead
 * (owner's 9 Sep feedback against the running lane: the same one-line defect slice A fixed
 * for the Outstanding column also sat in this column - a rejected or changed row read two
 * lines tall while every plain row read one).
 *
 * The cell prints the quantity alone, plus this icon only when there is something to say -
 * a rejection reason, a change stamp, or both (a row rejected after once being amended
 * carries both facts; the dialog states both rather than the old rule that let a rejection
 * hide a change's own history from the reader).
 *
 * `RejectedNote` and `ChangedBadge` moved in here from `orderInquiryWorklistColumns.tsx` -
 * nothing else in the tree rendered either of them. A sibling file to
 * `OrderInquiryBackingDocumentsDialog.tsx`, matching its shape (Dialog/DialogHeader/
 * DialogBody, mounted only once asked for), rather than a shared wrapper: the two dialogs'
 * BODIES have nothing in common (a list of documents here, a rejection reason and a
 * Was/Now table there) - what is worth sharing is the Dialog/trigger IDIOM, and each file
 * already provides that on its own without a third abstraction over content that does not
 * overlap.
 */
export function OrderInquiryQtyAnnotationDialog({
  row,
  open,
  onOpenChange,
}: {
  row: OrderInquiryWorklistRow;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const rejected = ackStateOf(row) === 'rejected';
  const previous = previousValueOf(row);
  // AC-RL-04 (17 Sep rulings): a replan could not carry this row forward because its
  // only coverage had already landed elsewhere - the row's own note states where and
  // when, verbatim, never re-parsed into figures.
  const redirected = Boolean(row.redirected_to_pool);
  const redirectedNote = redirected ? (row.note ?? '').trim() : '';
  // AC-RL-46 (`PLAN-oi-replan-received-links.md` S5): a row the book redirected off -
  // a settle never touched it, so `previous` is null, but the note names where its
  // documents went. Never checked on a `redirected_to_pool` row: that row's own note is
  // handled above and reads differently.
  const moved = !redirected ? movedNoteOf(row) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid={`qty-annotation-${row.id}`}>
        <DialogHeader>
          <DialogTitle className="tabular-nums">
            {row.item_code ?? row.so_number ?? 'Quantity'}
          </DialogTitle>
          <DialogDescription>
            {rejected && previous
              ? 'Rejected, and changed before that'
              : rejected
                ? 'Rejected'
                : previous
                  ? 'Changed'
                  : 'Redirected'}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-5">
          {rejected ? <RejectedSection row={row} /> : null}
          {previous ? <ChangedSection row={row} previous={previous} /> : null}
          {redirected && redirectedNote ? <MovedSection note={redirectedNote} /> : null}
          {moved ? <MovedSection note={moved} /> : null}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

/** Who rejected the row and why - the same words `RejectedNote` used to print inline. */
function RejectedSection({ row }: { row: OrderInquiryWorklistRow }) {
  const reason = (row.rejected_reason ?? '').trim();
  const who = row.rejected_by_name || 'Purchasing';
  return (
    <section className="space-y-1">
      <h3 className="text-sm font-semibold">Rejected</h3>
      <p className="text-sm text-muted-foreground">
        {reason ? `${who}: ${reason}` : `Rejected by ${who}`}
      </p>
    </section>
  );
}

/** The Was/Now of a settled amendment - the same table `ChangedBadge` used to open. */
function ChangedSection({
  row,
  previous,
}: {
  row: OrderInquiryWorklistRow;
  previous: { qty: string; date: string | null };
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">
        {row.changed_at ? `Changed ${formatDateInMalaysia(row.changed_at)}` : 'Changed'}
      </h3>
      <BoardChangeWasNowTable
        omitDecision
        omitHeader
        annotation={{
          rowId: row.id,
          soNumber: row.so_number ?? '',
          lineNo: 0,
          itemCode: row.item_code ?? '',
          // The batch's own change vocabulary is never shown (part 3) and this table
          // prints none of it; `qty_up` is the nearest true word for a row CS amended,
          // and nothing reads it here.
          kind: 'qty_up',
          closed: false,
          was: { qty: previous.qty, date: previous.date, decision: null },
          now: { qty: row.qty, date: row.delivery_date ?? null, decision: null },
          // A settled amendment is not a planning change: it has no composed suggestion,
          // nothing to be late or short against, and no product swap behind it.
          suggestionLines: [],
          lateDays: null,
          shortfallQty: null,
          productChangedFrom: null,
          movedTransfer: null,
          projectLineId: null,
        }}
      />
    </section>
  );
}

/**
 * The row's own note, verbatim, never parsed back into figures - the same convention
 * every other note on this row already follows. Shared by two callers: AC-RL-04's
 * `used` trigger (a replan redirected the row's coverage elsewhere) and AC-RL-46's
 * `note` trigger (AutoCount's own book pairing moved or cleared the row's link, the
 * `follow_book_repairing` note).
 */
function MovedSection({ note }: { note: string }) {
  return (
    <section className="space-y-1">
      <h3 className="text-sm font-semibold">Redirected</h3>
      <p className="text-sm text-muted-foreground">{note}</p>
    </section>
  );
}

export default OrderInquiryQtyAnnotationDialog;
