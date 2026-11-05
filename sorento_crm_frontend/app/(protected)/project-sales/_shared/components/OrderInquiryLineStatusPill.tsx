'use client';

import { statusPillClass } from '@/lib/status-pill';
import { ackOverrideHint, ackStateOf, ackStatusText } from '../lib/orderInquiryAck';
import type { OrderInquiryLine } from '../lib/orderInquiryLineFold';
import { OrderInquiryLineStatePill, ReservePill } from './OrderInquiryVerbPill';
import { OrderInquiryRejectedBadge } from './OrderInquiryRejectedBadge';

/** The status pill keeps the text's own case ("To order · 220 left"), so no capitalize. */
const ACK_PILL_BASE =
  'inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold';

function ackPalette(row: Parameters<typeof ackStateOf>[0]): string {
  const state = ackStateOf(row);
  return state === 'acknowledged' ? 'approved' : state === 'rejected' ? 'voided' : 'pending';
}

/**
 * SO-LINE-OI-STATUS-UNIFY (owner, 5 Nov 2026): the ONE status of a sales order line's
 * order inquiry rows, folded by `foldInquiryLines`. The OI Lines tab's State cell and the
 * Sales Order Lines tab's Order inquiry cell both render this, so the two screens can no
 * longer say two different things about the same line.
 *
 * In order: an open reserve (Request to reserve N / Reserved N / Not reserved), a refusal
 * (Rejected + reason, lightbox on click), the purchasing status of a live line (To order,
 * To order · N left, Done; OI-AUTO-CONFIRM), else the line's own state (Line cancelled,
 * Nothing to buy, Cancelled).
 */
export function OrderInquiryLineStatusPill({
  line,
  rejectedTestId,
}: {
  line: OrderInquiryLine;
  rejectedTestId?: string;
}) {
  const primary = line.primary;
  const reserveState = line.liveRows.length > 0 ? primary.reserve_state : null;
  if (reserveState === 'requested' || reserveState === 'reserved' || reserveState === 'declined') {
    return (
      <ReservePill
        reserveState={reserveState}
        reservedQty={primary.reserved_qty}
        requestedQty={primary.requested_qty}
      />
    );
  }
  if (!['raised', 'partly_linked', 'placed', 'to_confirm'].includes(line.state)) {
    return <OrderInquiryLineStatePill state={line.state} />;
  }
  if (ackStateOf(primary) === 'rejected') {
    return <OrderInquiryRejectedBadge refusal={primary} testId={rejectedTestId} />;
  }
  const text = ackStatusText(primary);
  return (
    <span
      className={`${ACK_PILL_BASE} ${statusPillClass(ackPalette(primary))}`}
      title={[text, ackOverrideHint(primary)].filter(Boolean).join('. ')}
    >
      {text}
    </span>
  );
}
