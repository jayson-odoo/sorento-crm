/**
 * Internal ticket comments - feature service (UAC AC-L1 / AC-L2 / AC-L3).
 *
 * Contract: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
 * Plan:     documentation/plans/sla/PLAN-conversation-intervention-tickets.md (slice S4.3)
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT (as implemented)
 * ---------------------------------------------------------------------------
 * All paths are under `/api/v1/sla-management/conversation-sla-tracking`.
 *
 * GET /{tracking_id}/comments  ->  TicketComment[]
 *   Oldest first. Assignee-or-manager scoped (404, never 403, for an outsider).
 *   Carries this ticket's own CRM comments PLUS the CONTACT-scoped ones
 *   ingested from Respond's own inbox - those have `source: 'respond'` and
 *   `tracking_id: null`, and show in every open ticket for the same contact.
 *
 * POST /{tracking_id}/comments
 *   Request:  { body: string, mentioned_user_ids?: string[] }
 *   Response: TicketComment (201)
 *   The body keeps the readable "@Display Name" inline; the ids are what the
 *   in-app mention notification and the Respond `{{@user.<id>}}` mirror resolve
 *   from. A comment is NEVER delivered to the contact - this endpoint touches
 *   no Respond send path at all.
 *
 * Respond-side ingest (AC-L3) is n8n -> POST /api/v1/external/chat-history/comments
 * and never reaches the browser.
 * ---------------------------------------------------------------------------
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/sla-management/conversation-sla-tracking';

export interface TicketComment {
  id: string;
  /** Null on a Respond-ingested comment: those belong to the contact. */
  tracking_id: string | null;
  body: string;
  author_name: string | null;
  /** Display names of the mentioned users. No uuids reach the UI. */
  mentioned_names: string[];
  source: 'crm' | 'respond';
  created_at: string;
}

export interface CreateTicketCommentInput {
  body: string;
  mentioned_user_ids?: string[];
}

/** This ticket's internal notes, oldest first. */
export async function getTicketComments(id: string): Promise<TicketComment[]> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/comments`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the notes on this ticket'));
  }
  return response.json();
}

/** Write an internal note. Never reaches the contact. */
export async function createTicketComment(
  id: string,
  input: CreateTicketCommentInput,
): Promise<TicketComment> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/comments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      body: input.body,
      mentioned_user_ids: input.mentioned_user_ids ?? [],
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to add the note'));
  }
  return response.json();
}
