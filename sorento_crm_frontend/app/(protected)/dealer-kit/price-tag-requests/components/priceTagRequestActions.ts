/**
 * What can be done to a price tag request right now, in lifecycle order (D52).
 *
 * The FIRST entry is the page's one primary CTA and everything after it lives
 * in the gear menu, so "one loud button, the rest in the dropdown" is a
 * property of this list rather than something each render has to remember.
 * Kept out of the component so the whole table can be asserted without a DOM.
 */

export type PriceTagAction =
  | 'claim'
  | 'design'
  | 'mark_proof_ready'
  | 'export'
  | 'void';

export interface PriceTagActionSpec {
  action: PriceTagAction;
  label: string;
  /** Needs a confirmation dialog before it runs. */
  destructive?: boolean;
}

/** Statuses where a request is finished or abandoned: nothing left to do. */
const CLOSED = new Set(['void', 'rejected']);

export function priceTagActions(
  status: string | null | undefined,
  assignedToId: string | null | undefined,
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
    actions.push({ action: 'mark_proof_ready', label: 'Mark proof ready' });
  }

  if (current === 'approved' || current === 'ready') {
    actions.push({ action: 'export', label: 'Export PDF' });
  }

  if (current && current !== 'ready' && !CLOSED.has(current)) {
    actions.push({ action: 'void', label: 'Void', destructive: true });
  }

  return actions;
}
