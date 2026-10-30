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

/** The review stage of each stage-based form, i.e. the stage `resubmitted` stands in for. */
export const SI_REVIEW_STAGE = 'pending_project_sales';

export function isAwaitingReview(
  status: string | null | undefined,
  stage: string = SUBMITTED,
): boolean {
  const s = (status ?? '').trim().toLowerCase();
  return s === stage || s === RESUBMITTED;
}

/**
 * What a person reads for `resubmitted` and for the action that sends a rejected form back
 * (owner, 28 Oct 2026: "Appealed" / "Appeal" on every form). Display only: the stored value
 * stays `resubmitted`. Every label map and button names these, never the bare string.
 */
export const APPEALED_LABEL = 'Appealed';
export const APPEAL_VERB = 'Appeal';

/**
 * The verb on a form's send button. A form that was rejected goes back as an appeal:
 * every form surfaces a rejected record as `status: 'rejected'` while it is being amended,
 * so this one rule covers them all.
 */
export function submitVerb(status: string | null | undefined): 'Submit' | typeof APPEAL_VERB {
  return (status ?? '').trim().toLowerCase() === 'rejected' ? APPEAL_VERB : 'Submit';
}

/**
 * A status line with "resubmitted" read as "appealed", case kept
 * ("status: rejected → resubmitted" -> "status: rejected → appealed").
 */
export function appealWording(text: string): string {
  return text.replace(/\b(r)esubmitted\b/gi, (_m, r: string) => (r === 'R' ? 'Appealed' : 'appealed'));
}
