/**
 * Mirror of the backend's `app/services/submission_status.py`.
 *
 * A form submitted again after a rejection carries `resubmitted` (owner, 27 Oct 2026)
 * and behaves exactly like the review stage it stands in for: `submitted` for most
 * forms, `pending_project_sales` for a stock inquiry, `pending` for a project
 * registration, `pending_approval` for a quotation or a dealer-kit edition. A button,
 * filter or check that meant "sitting at that stage" calls `isAwaitingReview`, never
 * compares against the bare stage string.
 */
export const SUBMITTED = 'submitted';
export const RESUBMITTED = 'resubmitted';

export function isAwaitingReview(
  status: string | null | undefined,
  stage: string = SUBMITTED,
): boolean {
  const s = (status ?? '').trim().toLowerCase();
  return s === stage || s === RESUBMITTED;
}

/**
 * The verb on a form's send button. A form that was rejected goes back as a
 * resubmission (owner, 27 Oct 2026): every form surfaces a rejected record as
 * `status: 'rejected'` while it is being amended, so this one rule covers them all.
 */
export function submitVerb(status: string | null | undefined): 'Submit' | 'Resubmit' {
  return (status ?? '').trim().toLowerCase() === 'rejected' ? 'Resubmit' : 'Submit';
}
