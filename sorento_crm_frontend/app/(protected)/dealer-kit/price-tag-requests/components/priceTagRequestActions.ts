/**
 * What can be done to a price tag request right now, in lifecycle order (D52).
 *
 * The FIRST entry is the page's one primary CTA and everything after it lives
 * in the gear menu, so "one loud button, the rest in the dropdown" is a
 * property of this list rather than something each render has to remember.
 * Kept out of the component so the whole table can be asserted without a DOM.
 */

import {
  isTerminalPriceTagStatus,
  type PrintBy,
} from '@/lib/dealer-kit/print-collection';

export type PriceTagAction =
  | 'claim'
  | 'design'
  | 'mark_proof_ready'
  | 'mark_ready_for_collection'
  | 'mark_collected'
  | 'export'
  | 'void';

export interface PriceTagActionSpec {
  action: PriceTagAction;
  label: string;
  /** Needs a confirmation dialog before it runs. */
  destructive?: boolean;
}

/** Statuses where a request is finished or abandoned: nothing left to do. */
const CLOSED = new Set(['void', 'rejected', 'collected']);

/** The three statuses a finished design can be exported from (D8). */
const EXPORTABLE = new Set(['approved', 'ready_for_collection', 'collected']);

export function priceTagActions(
  status: string | null | undefined,
  assignedToId: string | null | undefined,
  /**
   * How many of the salesperson's pinned change requests are still open (r9
   * D6). The count rides on the `Mark design ready` label so marketing sees it
   * without opening anything; it never BLOCKS the transition (D2) - somebody
   * who has decided a comment does not apply must still be able to send the
   * design back.
   */
  openChangeRequests = 0,
  /**
   * Who prints (r9 D7). `approved` means two different things depending on it:
   * the end of the line for a salesperson printing their own tags, and the
   * moment the office starts printing for everyone else. Null (a row from
   * before the choice existed) offers neither, and the card says so.
   */
  printBy: PrintBy | null | undefined = null,
): PriceTagActionSpec[] {
  const current = (status ?? '').trim().toLowerCase();
  const actions: PriceTagActionSpec[] = [];

  // Claiming comes before designing: an unclaimed request has no owner, and
  // the design belongs to whoever takes it.
  //
  // There is no `draft` STATUS. A request the salesperson has not submitted
  // carries status `new` and a `portal_draft_at` timestamp, and the CRM queue
  // does not list it at all, so branching on a status the backend never writes
  // only described a state that cannot occur.
  if (current === 'new' && !assignedToId) {
    actions.push({ action: 'claim', label: 'Claim' });
  } else if (current === 'new' || current === 'designing' || current === 'changes_requested') {
    actions.push({ action: 'design', label: 'Design tags' });
  } else if (current === 'proof_ready') {
    // The proof is with the salesperson; marketing can still look at what was sent.
    actions.push({ action: 'design', label: 'View design' });
  }

  if (current === 'designing' || current === 'changes_requested') {
    actions.push({
      action: 'mark_proof_ready',
      label:
        openChangeRequests > 0
          ? `Mark design ready (${openChangeRequests} open)`
          : 'Mark design ready',
    });
  }

  // The office hand-over (D8): only an office print reaches it, and only once
  // somebody has said so - a request with no choice on it offers nothing here
  // rather than guessing.
  if (current === 'approved' && printBy === 'office') {
    actions.push({
      action: 'mark_ready_for_collection',
      label: 'Mark ready for collection',
    });
  }

  if (current === 'ready_for_collection') {
    actions.push({ action: 'mark_collected', label: 'Mark collected' });
  }

  if (EXPORTABLE.has(current)) {
    actions.push({ action: 'export', label: 'Export PDF' });
  }

  // Void is still legal wherever the graph allows a transition out. It does
  // not at `ready_for_collection` (whose only exit is `collected`), nor once
  // the request is terminal for its own print choice.
  if (
    current &&
    !CLOSED.has(current) &&
    current !== 'ready_for_collection' &&
    !isTerminalPriceTagStatus(current, printBy)
  ) {
    actions.push({ action: 'void', label: 'Void', destructive: true });
  }

  return actions;
}
