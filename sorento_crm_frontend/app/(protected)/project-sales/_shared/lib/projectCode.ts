/**
 * A portal registration has no project code until it is approved (PROJECT-REG-PORTAL R2).
 * Every place a code renders goes through this one helper, so nothing ever reads "None",
 * "null" or an empty slot.
 */
export const AWAITING_APPROVAL_LABEL = 'Awaiting approval';

export function projectCodeLabel(project: { project_code?: string | null }): string {
  const code = project.project_code;
  return code && code.trim() ? code : AWAITING_APPROVAL_LABEL;
}
