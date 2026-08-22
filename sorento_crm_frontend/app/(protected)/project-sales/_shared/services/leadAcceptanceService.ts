/**
 * P1 - assign, accept, decline, and the marketing worklist.
 *
 * Endpoints per `documentation/plans/CONTRACT-project-lead-to-so.md` section 1. The
 * informant fields ride on the existing lead POST and PUT, so they live in
 * `projectService` and not here; this file owns the handshake only.
 *
 * Path prefix note: the contract's frontend rule says `/api/project-sales/...`, but
 * `lib/api.ts` has no rewrite entry for that prefix (it would be treated as a Next.js
 * route handler and 404). Phase 1's `projectService` already calls
 * `/api/v1/project-sales/...` directly, which `lib/api.ts` passes straight through, so
 * that is what we use here too.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  AssignLeadBody,
  AwaitingAcceptanceEnvelope,
  AwaitingAcceptanceParams,
  AwaitingAcceptanceRow,
  LeadWithAcceptance,
} from '../types/leadAcceptance.types';

const LEADS = '/api/v1/project-sales/leads';

/**
 * Leads assigned to somebody who has not accepted them yet.
 *
 * Nobody's job until accepted, so this is a worklist for the person who assigned it
 * rather than a report.
 *
 * The endpoint takes no `sort`: the server's order (newest assignment first) IS the
 * answer the screen gives, and `min_hours` is how "nobody has answered me since Tuesday"
 * is asked.
 *
 * Envelope: the route answers in the repo's standard `ListResponse`
 * (`{data, pagination: {total, page, limit}, empty}`). The contract's original flat
 * `{data, total, page, limit}` is read as a fallback so a screen cannot silently lose its
 * record count, but `pagination` is the shape that ships.
 */
export async function listAwaitingAcceptance(
  params: AwaitingAcceptanceParams,
): Promise<AwaitingAcceptanceEnvelope> {
  const { owner_user_id, min_hours, ...grid } = params;
  const sp = buildDataGridParams(grid, {
    owner_user_id,
    min_hours,
  });
  const response = await apiFetch(`${LEADS}/awaiting-acceptance?${sp.toString()}`);
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to load leads awaiting acceptance'),
    );
  const body: {
    data?: AwaitingAcceptanceRow[];
    total?: number;
    page?: number;
    limit?: number;
    pagination?: { total?: number; page?: number; limit?: number };
  } = await response.json();
  return {
    data: body.data ?? [],
    total: body.pagination?.total ?? body.total ?? 0,
    page: body.pagination?.page ?? body.page ?? 1,
    limit: body.pagination?.limit ?? body.limit ?? params.pageSize,
  };
}

/**
 * Assign, or re-assign. Re-assigning an already-assigned lead is allowed and resets the
 * clock, which is how a lead moves off somebody who never opened it.
 */
export async function assignLead(
  leadId: string,
  body: AssignLeadBody,
): Promise<LeadWithAcceptance> {
  const response = await apiFetch(`${LEADS}/${leadId}/assign`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to assign the lead'));
  return response.json();
}

export async function acceptLead(leadId: string): Promise<LeadWithAcceptance> {
  const response = await apiFetch(`${LEADS}/${leadId}/accept`, { method: 'POST' });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to accept the lead'));
  return response.json();
}

/** Returns the lead to the pool: the owner is cleared and the reason is kept. */
export async function declineLead(
  leadId: string,
  reason: string,
): Promise<LeadWithAcceptance> {
  const response = await apiFetch(`${LEADS}/${leadId}/decline`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to decline the lead'));
  return response.json();
}

/**
 * Nudge the current assignee.
 *
 * The contract has no nudge endpoint, so this re-assigns the lead to the SAME person,
 * which the contract defines as allowed, as notifying the assignee, and as resetting the
 * clock. When a dedicated endpoint lands, only this function changes.
 */
export async function nudgeLeadAssignee(
  leadId: string,
  ownerUserId: string,
  note?: string | null,
): Promise<LeadWithAcceptance> {
  return assignLead(leadId, { owner_user_id: ownerUserId, note: note ?? null });
}
