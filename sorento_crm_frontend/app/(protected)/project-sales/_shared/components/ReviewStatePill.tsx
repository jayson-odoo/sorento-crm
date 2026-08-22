'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  REVIEW_STATE_LABELS,
  type ReviewState,
} from '../types/fulfilmentPlanning.types';

/**
 * The whole sales order's one pre-confirmation state (AC-A03).
 *
 * Deliberately NOT folded into `SalesOrderStatusPill`: a sales order's status (draft,
 * blocked, published) and its review state are two different questions, and a published
 * order that is still awaiting reconciliation has to be able to say both. One pill
 * carrying both would force a choice between them.
 *
 * Mapped onto the shared palette's existing keys the way every other pill in this module
 * is: not started is work nobody has picked up, so it takes the neutral `draft` grey and
 * reads as quiet rather than as a problem (there are hundreds of them and they are not
 * faults); awaiting reconciliation is a wait, so it takes `pending`'s amber; needs CS review
 * is work that has come back to us and wants a decision, which is exactly what `submitted`'s
 * sky already means elsewhere; confirmed is a decision that stands, so it takes the same
 * emerald `active` wears everywhere.
 *
 * Confirmed means an ACTIVE supply decision. A superseded or challenged one reads Needs CS
 * review again, so the pill never states a decision the order no longer holds.
 *
 * Renders nothing when the state is absent, so the surfaces that merely carry it (the SO
 * list row, the SO detail header) are unchanged against a backend that has not shipped the
 * field yet.
 */
const PALETTE_KEY: Record<ReviewState, string> = {
  not_started: 'draft',
  awaiting_reconciliation: 'pending',
  needs_cs_review: 'submitted',
  confirmed: 'active',
};

export function ReviewStatePill({
  state,
  exceptionCount,
}: {
  state?: ReviewState | null;
  /** Shown beside the label when there is anything to clear. Never shown as a bare zero. */
  exceptionCount?: number | null;
}) {
  if (!state) return null;
  const label = REVIEW_STATE_LABELS[state] ?? state;
  const count = exceptionCount ?? 0;
  const text = count > 0 ? `${label} · ${count} exception${count === 1 ? '' : 's'}` : label;
  return (
    <span
      className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(PALETTE_KEY[state])}`}
      title={text}
    >
      {text}
    </span>
  );
}
