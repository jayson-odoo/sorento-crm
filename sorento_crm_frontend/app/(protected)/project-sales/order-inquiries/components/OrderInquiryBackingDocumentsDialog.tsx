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
import { ackStateOf } from '../../_shared/lib/orderInquiryAck';
import { formatInquiryQty, linkedSummary } from '../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';
import { OrderInquiryDocumentLink } from './OrderInquiryDocumentDialog';

/**
 * Everything backing ONE worklist row, behind the info icon the "Outstanding PO/SPO" cell
 * offers (slice A, owner's 8 Sep cut of the mock).
 *
 * The cell itself prints only the draft/confirmed mark, the coverage headline and this
 * icon - no document, no count, no bar, no lateness (a bar is a proportion of a number the
 * cell already prints in full, and lateness is "said, never acted on", per the plan). Every
 * fact that used to sit in the cell now lives here instead: kind, document number, location,
 * quantity, expected date, and the row's own standing. NOTHING ELSE - no tier, no rank, no
 * reasoning for why a document was chosen (the owner explicitly rejected that richer
 * version).
 *
 * A separate file from `orderInquiryWorklistColumns.tsx` on purpose, so the column
 * definitions stay the shape a `ColumnDef[]` array is meant to be.
 */
export function OrderInquiryBackingDocumentsDialog({
  row,
  open,
  onOpenChange,
}: {
  row: OrderInquiryWorklistRow;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const links = row.links ?? [];
  // The row's own handshake state (DraftMark's own read), never a state on the link
  // itself - every document backing an unrejected row shares one standing.
  const standing = ackStateOf(row) === 'acknowledged' ? 'Confirmed' : 'Proposed';
  const summary = linkedSummary(row.qty, row.linked_qty, row.links);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid={`backing-documents-${row.id}`}>
        <DialogHeader>
          <DialogTitle>Backing documents</DialogTitle>
          <DialogDescription>
            {summary?.headline ?? 'Not found (new order)'}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          {links.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing backs this row yet.</p>
          ) : (
            <ul className="space-y-2">
              {links.map((link) => (
                <li
                  key={link.id}
                  className="flex items-start justify-between gap-3 rounded-md border p-2.5 text-sm"
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-1.5">
                      <span className="shrink-0 rounded-sm bg-muted px-1 py-0.5 text-2xs font-medium uppercase text-muted-foreground">
                        {link.kind}
                      </span>
                      <OrderInquiryDocumentLink
                        kind={link.kind}
                        document={link.document}
                        poId={link.po_id}
                      />
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {link.location || 'no location'} · {formatInquiryQty(link.qty)}
                    </div>
                  </div>
                  <div className="shrink-0 text-right text-xs text-muted-foreground">
                    <div>
                      {link.expected_date ? formatDateInMalaysia(link.expected_date) : 'No date'}
                    </div>
                    <div>{standing}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default OrderInquiryBackingDocumentsDialog;
