import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * "Does this form type get a Revisions tab" - the office side of the portal
 * revision policy (UAC H2, round 6).
 *
 * Contract:
 *   GET /api/v1/forms-management/revision-configs/enabled
 *     -> { types: { stock_inquiry: boolean, purchase_request: boolean,
 *                   sponsorship_form: boolean, complaint: boolean } }
 *
 * Each boolean is the EFFECTIVE answer the backend would give a submission of
 * that type: the global kill switch, the per-type config row, a missing row
 * (fail closed) and a zero cap are already collapsed server-side, so nothing
 * here re-derives the rule.
 *
 * Any authenticated principal may read it - the admin-gated CRUD for the same
 * rows lives in `user-management/settings/portal-revisions`.
 */
export type RevisionEnabledMap = Record<string, boolean>;

export async function getRevisionEnabledMap(): Promise<RevisionEnabledMap> {
  const response = await apiFetch('/api/v1/forms-management/revision-configs/enabled');
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to load revision settings'),
    );
  }
  const data = await response.json();
  return (data?.types ?? {}) as RevisionEnabledMap;
}
