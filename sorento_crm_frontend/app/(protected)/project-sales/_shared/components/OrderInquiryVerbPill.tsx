'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

/**
 * The verb, in the words purchasing already uses (AC-I2).
 *
 * Stored as `RESERVE_AND_ORDER`; written on their own spreadsheet as `RESERVE & ORDER`.
 * The spelling belongs on screen too, because the screen and the spreadsheet are read by
 * the same person in the same hour and two names for one instruction is a question.
 */
export const VERB_LABEL: Record<string, string> = {
  ORDER: 'ORDER',
  RESERVE_AND_ORDER: 'RESERVE & ORDER',
  ADVANCE: 'ADVANCE',
  DELAY: 'DELAY',
  CHANGE_SO: 'CHANGE SO NO',
  CANCEL_BALANCE: 'CANCEL BALANCE',
  PRE_ORDERED_DO_NOT_ORDER: 'PRE-ORDERED, DO NOT ORDER',
  ALREADY_INBOUND: 'ALREADY INBOUND',
  BORROW_SHORTFALL: 'BORROW SHORTFALL',
  RELEASE: 'RELEASE',
};

/**
 * Colour carries the only distinction that changes what purchasing DOES: buy it, or do
 * not. Amber is money about to be spent, emerald is money already spent, sky is a change
 * to something already on order, red is a cancellation.
 */
export const VERB_PALETTE_KEY: Record<string, string> = {
  ORDER: 'pending',
  RESERVE_AND_ORDER: 'pending',
  PRE_ORDERED_DO_NOT_ORDER: 'processed_by_cs',
  ALREADY_INBOUND: 'processed_by_cs',
  ADVANCE: 'submitted',
  DELAY: 'submitted',
  CHANGE_SO: 'submitted',
  CANCEL_BALANCE: 'rejected',
  // Money about to be spent, like an ORDER: the donor is short and somebody must buy it.
  BORROW_SHORTFALL: 'pending',
  // A planning-change release moved the Buy off this line's own location onto the pool -
  // still money about to be spent, just no longer for this line (PLAN-so-book-diff
  // -replanning.md section 6).
  RELEASE: 'pending',
};

/**
 * The verbs that still cost money. `BORROW_SHORTFALL` is one of them: a borrow left its
 * donor location oversold, and the hole has to be bought (PLAN-fulfilment-planning 13.11).
 */
export const BUYING_VERBS = ['ORDER', 'RESERVE_AND_ORDER', 'BORROW_SHORTFALL'];

export function OrderInquiryVerbPill({ verb }: { verb: string }) {
  const label = VERB_LABEL[verb] ?? verb;
  return (
    <span
      className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(VERB_PALETTE_KEY[verb] ?? 'draft')}`}
      title={label}
    >
      {label}
    </span>
  );
}

const STATE_LABEL: Record<string, string> = {
  raised: 'Raised',
  actioned: 'Actioned',
  cancelled: 'Cancelled',
};

const STATE_PALETTE: Record<string, string> = {
  raised: 'pending',
  actioned: 'processed_by_cs',
  cancelled: 'voided',
};

export function OrderInquiryStatePill({ state }: { state: string }) {
  const label = STATE_LABEL[state] ?? state;
  return (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(STATE_PALETTE[state] ?? 'draft')}`}>
      {label}
    </span>
  );
}
