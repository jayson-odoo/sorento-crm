'use client';

import * as React from 'react';
import { Info } from 'lucide-react';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { purchasingRefusalTitle, type PurchasingRefusal } from '../lib/orderInquiryAck';

/**
 * The pill and info icon alone, no interaction of its own: for a place that is already one
 * big button (the board's Grid cell), where a nested button would be invalid HTML.
 * The caller puts the refusal sentence in a `title` and the cell's own click opens the
 * drill-down, whose Order inquiry column carries the full `OrderInquiryRejectedBadge`.
 */
export function OrderInquiryRejectedMark() {
  return (
    <>
      <span className={`${STATUS_PILL_BASE} ${statusPillClass('rejected')}`}>Rejected</span>
      <Info aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
    </>
  );
}

/**
 * PR 1622 (owner, mock v3): a purchasing refusal is the ORDER INQUIRY's status on a line.
 *
 * SO-LINE-OI-STATUS-UNIFY (owner, 5 Nov 2026, Q4): the "Rejected" pill with the reason
 * beside it (truncated, the whole sentence in the title), and a click opens a lightbox
 * with the full reason, who and when. ONE component for every screen that shows a
 * refusal: the Sales Order Lines tab, the OI Lines tab's State cell and the board.
 */
export function OrderInquiryRejectedBadge({
  refusal,
  testId,
  showReason = true,
}: {
  refusal: PurchasingRefusal;
  testId?: string;
  /** The reason text beside the pill. Off where the cell is too narrow to hold it. */
  showReason?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const text = purchasingRefusalTitle(refusal);
  const reason = refusal.rejected_reason || 'No reason given';
  const stamp = refusal.rejected_at ? formatDateTimeInMalaysia(refusal.rejected_at) : '';
  return (
    <>
      <button
        type="button"
        aria-label={text}
        title={text}
        data-testid={testId}
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
        className="inline-flex min-w-0 items-center gap-1 rounded-sm text-start outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className={`${STATUS_PILL_BASE} shrink-0 ${statusPillClass('rejected')}`}>
          Rejected
        </span>
        {showReason ? (
          <span className="min-w-0 truncate text-xs text-muted-foreground">{reason}</span>
        ) : null}
        <Info aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="max-w-md"
          data-testid={testId ? `${testId}-dialog` : undefined}
          onClick={(event) => event.stopPropagation()}
        >
          <DialogHeader>
            <DialogTitle>Rejected by purchasing</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-3 text-sm">
            <p className="whitespace-pre-wrap break-words">{reason}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-muted-foreground">
              <dt>By</dt>
              <dd className="text-foreground">{refusal.rejected_by_name || '-'}</dd>
              <dt>When</dt>
              <dd className="text-foreground">{stamp || '-'}</dd>
            </dl>
          </DialogBody>
        </DialogContent>
      </Dialog>
    </>
  );
}
