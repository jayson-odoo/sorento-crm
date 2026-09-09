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
 * What a bundled row's lightbox adds on top of the plain one (UAC D1-D3, D10): the
 * item(s) it rides with, named - never the word "host" - since the cell itself never
 * lists the codes. `fullyBundled` rows show only this note (their own `row` here is
 * already the ANCHOR, so its links ARE what backs the note); a partly-bundled row shows
 * this note ABOVE its own links, which back the ala carte remainder.
 */
export interface OrderInquiryBundleNote {
  itemCodes: string[];
  fullyBundled: boolean;
  /** The bundled portion's own quantity. Only meaningful (and only passed) when partial. */
  qty?: string;
}

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
 * version) - except one thing added 9 Sep: an SPO entry also names the purchase order it
 * came from (`link.source_po_number`), because a buyer reading a shipping-order reservation
 * had no way back to the document they actually work with.
 *
 * A separate file from `orderInquiryWorklistColumns.tsx` on purpose, so the column
 * definitions stay the shape a `ColumnDef[]` array is meant to be.
 */
export function OrderInquiryBackingDocumentsDialog({
  row,
  open,
  onOpenChange,
  bundleNote,
}: {
  row: OrderInquiryWorklistRow;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bundleNote?: OrderInquiryBundleNote;
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
            {/* The CELL collapses two-or-more items to a count (UAC D10: never the word
                "host", no code list in the cell); the lightbox is where the codes
                themselves live, always joined in full - never the count. */}
            {bundleNote?.fullyBundled
              ? `Included with ${bundleNote.itemCodes.join(' + ')}`
              : (summary?.headline ?? 'Not found (new order)')}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          {bundleNote && !bundleNote.fullyBundled ? (
            <div className="mb-2 rounded-md border bg-muted/30 p-2.5 text-sm">
              <div className="text-xs text-muted-foreground">Included with</div>
              <div className="font-medium">{bundleNote.itemCodes.join(' + ')}</div>
              <div className="text-xs text-muted-foreground">
                {formatInquiryQty(bundleNote.qty ?? '0')} units
              </div>
            </div>
          ) : null}
          {links.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {bundleNote?.fullyBundled
                ? 'Nothing backs this yet.'
                : 'Nothing backs this row yet.'}
            </p>
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
                    {/* Owner's 9 Sep feedback: "if we link by SPO, where do we see the PO
                        number of this SPO?" - named here, clearly subordinate to the SPO
                        number above it (smaller, muted, no badge of its own). Never a
                        link yet - a later slice decides where it goes. Absent rather than
                        an empty label when the book named no source (AC-A14). */}
                    {link.kind === 'spo' && link.source_po_number ? (
                      <div className="truncate text-2xs text-muted-foreground">
                        from PO {link.source_po_number}
                      </div>
                    ) : null}
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
