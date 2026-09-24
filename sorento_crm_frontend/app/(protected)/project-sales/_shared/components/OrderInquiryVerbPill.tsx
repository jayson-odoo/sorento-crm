'use client';

import { Check } from 'lucide-react';
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

// Exported (AC-OH-61): the worklist's own State filter labels its options with these
// SAME words, off `summary.by_state`'s keys - one map, so the pill on a row and the
// option that filters to it never say the state two different ways.
//
// S5 (`PLAN-board-oi-mechanical-22sep.md`, AC-B5-1/AC-B5-2, owner's pick, 22 Sep 2026):
// plain words for what PURCHASING DOES with the row, not the internal verb ("Raised" /
// "Actioned" explained nothing on screen without also knowing the workflow). Stored
// values are UNCHANGED - `raised`/`partly_linked`/`placed`/`actioned`/`cancelled` still
// key `scm.committed_v`, the worklist filter and every saved column preference; only the
// word a person reads moves. This is the ONE map every reader of the state (this pill,
// the worklist's own State filter, the Lines tab, the board chips, any email template)
// must read off - a second spelling anywhere is a defect (AC-B5-2).
export const STATE_LABEL: Record<string, string> = {
  raised: 'To buy',
  actioned: 'Done',
  cancelled: 'Cancelled',
  placed: 'On PO/SPO',
  partly_linked: 'Partly on PO/SPO',
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

/**
 * `PLAN-oi-request-cs-reserve.md` 3.5 (AC-RS-20/AC-RS-25): `requested` while an open
 * reserve request row exists, `reserved` once CS has actually reserved something (and no
 * open request). Rendered BESIDE the state pill on the worklist (its own read-only
 * usage). Round 4 (section 6e.2, AC-RS-83/84): "The pill is no longer a button" - the
 * Lines grid's own reserve action moved to its own `reserve_actions` icon-button column
 * (`orderInquiryHeaderLinesColumns.tsx`); this pill is plain text everywhere now, amber
 * `Request to reserve N` printing the OPEN request's own `qty_requested`, green
 * `Reserved N` with the owner's own tick.
 */
export function ReservePill({
  reserveState,
  reservedQty,
  requestedQty,
}: {
  reserveState: 'requested' | 'reserved' | 'declined' | string | null | undefined;
  reservedQty?: string | null;
  /** AC-RS-83: the open request row's own `qty_requested` for this row - printed only
   * when `reserveState === 'requested'`. */
  requestedQty?: string | null;
}) {
  if (!reserveState) return null;
  if (reserveState === 'requested') {
    return (
      <span className={`${STATUS_PILL_BASE} normal-case ${statusPillClass('pending')}`}>
        Request to reserve {requestedQty ?? ''}
      </span>
    );
  }
  if (reserveState === 'reserved') {
    // Nit (review round): the GREEN key (`done`/`completed`), not `approved` (blue) -
    // a reserve is a finished outcome, the same reading `done` carries everywhere
    // else in `lib/status-pill.ts`.
    return (
      <span className={`${STATUS_PILL_BASE} normal-case gap-1 ${statusPillClass('done')}`}>
        {/* The owner's own tick ("after confirmed the product should have a ticked
            icon", round 3 owner words). */}
        <Check className="size-3" aria-hidden />
        Reserved {reservedQty ?? ''}
      </span>
    );
  }
  if (reserveState === 'declined') {
    // 6e.4 (AC-RS-83b): CS answered "Reserve 0" - neutral, not an error and not done.
    return (
      <span className={`${STATUS_PILL_BASE} normal-case ${statusPillClass('draft')}`}>
        Not reserved
      </span>
    );
  }
  return null;
}
