/** Absolute URLs for sharing workflow form work in the CRM (requires sign-in). */

export function getOrigin(): string {
  if (typeof window === 'undefined') return '';
  return window.location.origin.replace(/\/$/, '');
}

export function workflowSubmissionUrl(origin: string, submissionId: string): string {
  return `${origin}/workflow-forms-management/submissions/${submissionId}`;
}

export function workflowNewBlankUrl(origin: string, definitionId: string): string {
  return `${origin}/workflow-forms-management/forms/${definitionId}/new`;
}

export function workflowNewPrefilledUrl(
  origin: string,
  definitionId: string,
  duplicateFromSubmissionId: string,
): string {
  return `${workflowNewBlankUrl(origin, definitionId)}?duplicateFrom=${encodeURIComponent(duplicateFromSubmissionId)}`;
}
