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
  // `ORDER BACK` since migration 421 renamed the stored value (PLAN-scm-cs-planning-uat.md
  // section 1c + PLAN-scm-purchasing-uat-journey.md 4b): it is the order the donor's own
  // line now needs raising for it, or the quantity CS wrote ORDER BACK against on the
  // inquiry form. The old spelling stays in this map alone, so a row written before the
  // migration - or an export somebody kept - still reads as words rather than as a
  // constant.
  ORDER_BACK: 'ORDER BACK',
  BORROW_SHORTFALL: 'ORDER BACK',
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
  ORDER_BACK: 'pending',
  BORROW_SHORTFALL: 'pending',
  // A planning-change release moved the Buy off this line's own location onto the pool -
  // still money about to be spent, just no longer for this line (PLAN-so-book-diff
  // -replanning.md section 6).
  RELEASE: 'pending',
};

/**
 * The verbs that still cost money. `ORDER_BACK` is one of them: a borrow left its donor
 * location oversold, or CS wrote ORDER BACK on the form, and either way the hole has to
 * be bought (PLAN-fulfilment-planning 13.11).
 */
export const BUYING_VERBS = ['ORDER', 'RESERVE_AND_ORDER', 'ORDER_BACK', 'BORROW_SHORTFALL'];

/**
 * Which raised rows can be linked to a document - the same set the backend's
 * `_assert_linkable` checks. `ORDER_BACK` joined it in section 3.I: an order back is a
 * shortfall against something already ordered or already shipped, so it is the ONE verb
 * that may name an SPO allocation as well as a purchase order line (captain, 25 Aug).
 */
export const PLACEABLE_VERBS = ['ORDER', 'RESERVE_AND_ORDER', 'ORDER_BACK'];

/** The verbs whose links may name an SPO allocation. Only the order back (4b). */
export const SPO_LINKABLE_VERBS = ['ORDER_BACK'];

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
  // The whole quantity sits on documents (AC-I1). The stored value is still `placed`,
  // because renaming it would rewrite `scm.committed_v`, the worklist filter and every
  // saved column preference to say the same thing in a different word.
  placed: 'Linked',
  // Some of it does, the rest is still demand - the middle the links table made
  // expressible, and exactly what `committed_v` now nets.
  partly_linked: 'Partly linked',
};

const STATE_PALETTE: Record<string, string> = {
  raised: 'pending',
  actioned: 'processed_by_cs',
  cancelled: 'voided',
  placed: 'approved',
  partly_linked: 'submitted',
};

export function OrderInquiryStatePill({ state }: { state: string }) {
  const label = STATE_LABEL[state] ?? state;
  return (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(STATE_PALETTE[state] ?? 'draft')}`}>
      {label}
    </span>
  );
}
