import { APPEALED_LABEL } from '@/lib/submission-status';

/**
 * A portal registration has no project code until it is approved (PROJECT-REG-PORTAL R2).
 * Every place a code renders goes through this one helper, so nothing ever reads "None",
 * "null" or an empty slot: a refused registration reads "Rejected", one sent back after a
 * rejection "Resubmitted", any other code-less one "Awaiting approval". Mirrors the backend's
 * `project_label`.
 */
export const AWAITING_APPROVAL_LABEL = 'Awaiting approval';
export const REJECTED_LABEL = 'Rejected';
export const RESUBMITTED_LABEL = APPEALED_LABEL;
export const DRAFT_LABEL = 'Draft';

export function projectCodeLabel(project: {
  project_code?: string | null;
  approval_state?: string | null;
}): string {
  const code = project.project_code;
  if (code && code.trim()) return code;
  if (project.approval_state === 'draft') return DRAFT_LABEL;
  if (project.approval_state === 'rejected') return REJECTED_LABEL;
  if (project.approval_state === 'resubmitted') return RESUBMITTED_LABEL;
  return AWAITING_APPROVAL_LABEL;
}
