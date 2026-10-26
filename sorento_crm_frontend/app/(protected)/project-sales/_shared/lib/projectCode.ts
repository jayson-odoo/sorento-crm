/**
 * A portal registration has no project code until it is approved (PROJECT-REG-PORTAL R2).
 * Every place a code renders goes through this one helper, so nothing ever reads "None",
 * "null" or an empty slot: a refused registration reads "Rejected", any other code-less one
 * "Awaiting approval".
 */
export const AWAITING_APPROVAL_LABEL = 'Awaiting approval';
export const REJECTED_LABEL = 'Rejected';

export function projectCodeLabel(project: {
  project_code?: string | null;
  approval_state?: string | null;
}): string {
  const code = project.project_code;
  if (code && code.trim()) return code;
  return project.approval_state === 'rejected' ? REJECTED_LABEL : AWAITING_APPROVAL_LABEL;
}
