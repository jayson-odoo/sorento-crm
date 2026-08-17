/**
 * Conversations inbox - feature service (UAC AC-N1 / AC-N2 / AC-N3 / AC-N4).
 *
 * Contract: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
 * Plan:     documentation/plans/sla/PLAN-conversation-intervention-tickets.md (slice S4.9)
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT (as built, verified against the running backend)
 * ---------------------------------------------------------------------------
 * Everything is under `/api/v1/sla-management`. Reads need
 * `sla_management.conversations.view`, the reply needs
 * `sla_management.conversations.reply` - a PERMISSION, not ticket assignment,
 * which is the whole point of this surface: a reassigned-away colleague, a
 * mentioned one and a manager can all read the thread.
 *
 * `contact_ref` is whatever the list row gave us (a Respond.io contact id, a
 * `respond_contacts.id` or a phone number). Pass it back verbatim; an
 * unresolvable one is a 404.
 *
 * 1. GET /conversations?tab=&q=&cursor=&limit=   -> ConversationInboxPage
 *      tab: mine | mentioned | unassigned | all (default all; unknown -> 400)
 *      limit: default 30, max 100. Keyset: pass `next_cursor` back verbatim,
 *      stop when it is null. `mentioned` is newest-NOTE first, the rest are
 *      newest-MESSAGE first, and `last_message_*` can be null on the ticket
 *      tabs (an open ticket with no stored message).
 * 2. GET /conversations/{ref}/page?before=|after=|around=&limit=
 *      Byte-identical to the ticket-keyed
 *      `.../conversation-sla-tracking/{id}/conversation/page`, so
 *      `useConversationThread` works unchanged with contact-keyed loaders.
 * 3. GET /conversations/{ref}/search?q=&limit=   -> { items: [...] }
 * 4. GET /conversations/{ref}/comments -> TicketComment[], oldest first.
 *      WIDER than the ticket-keyed list on purpose (AC-N3): contact-scoped
 *      notes AND every conversation ticket's notes for that contact.
 * 5. GET /conversations/{ref}/media?url=  -> the bytes (allowlisted hosts).
 * 6. POST /conversations/{ref}/reply - JSON `{text}` or multipart (`text` +
 *      repeated `files`). The route still accepts an optional, audit-only
 *      `reply_to_message_id` / `reply_to_excerpt` pair, but nothing sends it:
 *      Respond has no reply-to parameter, and the ">" quote-prefix emulation
 *      was removed on 2026-08-16 rather than left reading like a real quote.
 *      `stamped_ticket_id` is non-null only when the sender holds EXACTLY ONE
 *      open ticket for the contact; zero or several is an unstamped human send
 *      that still goes out, still writes the outbox and still fires the
 *      human-intervention signal - so the FE must not block on it.
 * 7. POST /conversations/{ref}/comments - `{body, mentioned_user_ids}` -> 201
 *      with the same `TicketComment` the drawer renders (`tracking_id` null: the
 *      note belongs to the CONTACT). Gated by `.view`, not by assignment - a
 *      note is internal staff context. Blank body -> 422, unknown mentioned
 *      user -> 400 (the whole note is refused).
 * 8. GET /conversations/{ref}/window -> `{window, chat_template}` - the SAME
 *      pair the drawer reads off the ticket detail, so it feeds
 *      `windowStateOverride` directly. NOT DB-only: a live Respond call.
 * 9. POST /conversations/{ref}/template-message - `{template_id, params}`,
 *      synchronous, gated by `.reply`. Stamps by the same exactly-one-open-
 *      ticket rule as the reply. Unknown template -> 404, missing parameter ->
 *      400, a Respond refusal -> 502 with the outbox row still written.
 * ---------------------------------------------------------------------------
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ConversationSearchMatch,
  ConversationThreadPage,
} from '@/components/common/conversation/useConversationThread';
import type {
  CreateTicketCommentInput,
  TicketComment,
} from '@/app/(protected)/sla-management/conversation-sla-tracking/services/ticketCommentService';
import type { ChatTemplatePreview } from '@/services/whatsappTemplateService';

const BASE = '/api/v1/sla-management/conversations';

export const CONVERSATION_INBOX_TABS = ['mine', 'mentioned', 'unassigned', 'all'] as const;
export type ConversationInboxTab = (typeof CONVERSATION_INBOX_TABS)[number];

/** Default page size; the backend caps at 100. */
export const CONVERSATION_INBOX_PAGE_SIZE = 30;

export interface ConversationInboxItem {
  /** Opaque handle for every `/{contact_ref}/...` call on this row. */
  contact_ref: string;
  respond_io_id: string | null;
  phone: string | null;
  name: string | null;
  /** Naive UTC. Render through `formatDateTimeInMalaysia`. */
  last_message_at: string | null;
  last_message_snippet: string | null;
  last_message_direction: 'incoming' | 'outgoing' | null;
  /** Non-null only on tab=mentioned. */
  mentioned_at: string | null;
  open_ticket_count: number;
  my_open_ticket_count: number;
  /** Null unless `my_open_ticket_count === 1` - what a reply stamps. */
  my_open_ticket_id: string | null;
}

export interface ConversationInboxPage {
  items: ConversationInboxItem[];
  next_cursor: string | null;
  has_more: boolean;
  limit: number;
  tab: ConversationInboxTab;
  query: string;
}

export interface ListConversationsParams {
  tab: ConversationInboxTab;
  q?: string;
  cursor?: string | null;
  limit?: number;
}

export async function listConversations(
  params: ListConversationsParams,
): Promise<ConversationInboxPage> {
  const sp = new URLSearchParams({ tab: params.tab });
  if (params.q?.trim()) sp.set('q', params.q.trim());
  if (params.cursor) sp.set('cursor', params.cursor);
  sp.set('limit', String(params.limit ?? CONVERSATION_INBOX_PAGE_SIZE));
  const response = await apiFetch(`${BASE}?${sp.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load conversations'));
  }
  return response.json();
}

export async function getContactThreadPage(
  contactRef: string,
  params: { before?: string; after?: string; around?: string; limit?: number } = {},
): Promise<ConversationThreadPage> {
  const sp = new URLSearchParams();
  if (params.before) sp.set('before', params.before);
  if (params.after) sp.set('after', params.after);
  if (params.around) sp.set('around', params.around);
  if (params.limit != null) sp.set('limit', String(params.limit));
  const qs = sp.toString();
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(contactRef)}/page${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the conversation'));
  }
  return response.json();
}

export async function searchContactThread(
  contactRef: string,
  query: string,
  limit = 100,
): Promise<ConversationSearchMatch[]> {
  const sp = new URLSearchParams({ q: query, limit: String(limit) });
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(contactRef)}/search?${sp.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Search failed'));
  }
  const body = (await response.json()) as { items?: ConversationSearchMatch[] };
  return body.items ?? [];
}

/** Every internal note on this contact, oldest first (AC-N3). */
export async function getContactComments(contactRef: string): Promise<TicketComment[]> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(contactRef)}/comments`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the notes on this contact'));
  }
  return response.json();
}

/**
 * Contact-scoped byte proxy for a chat attachment (AC-N4). Returns the raw
 * `Response`: its only consumer is `AttachmentPreviewModal`'s `fetchBytes`,
 * which reads `.blob()` / `.arrayBuffer()` itself.
 */
export async function fetchContactMedia(contactRef: string, url: string): Promise<Response> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(contactRef)}/media?url=${encodeURIComponent(url)}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load this attachment'));
  }
  return response;
}

/** Write an internal note on the CONTACT (no ticket owns it). */
export async function createContactComment(
  contactRef: string,
  input: CreateTicketCommentInput,
): Promise<TicketComment> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(contactRef)}/comments`, {
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

/** Composer state for a contact: the 24h window plus the out-of-window template. */
export interface ContactComposerState {
  window: { open: boolean; expires_at: string | null };
  chat_template: ChatTemplatePreview;
}

export async function getContactWindow(contactRef: string): Promise<ContactComposerState> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(contactRef)}/window`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to check the messaging window'));
  }
  return response.json();
}

export interface ContactTemplateSendResult {
  ok: boolean;
  queued: boolean;
  template_name: string | null;
  rendered_body: string | null;
  /** Null = the send was not attached to one of the sender's open enquiries. */
  stamped_ticket_id: string | null;
}

/** Send an approved template to the contact. Synchronous: this IS the outcome. */
export async function sendContactTemplateMessage(
  contactRef: string,
  input: { template_id: string; params: Record<string, string> },
): Promise<ContactTemplateSendResult> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(contactRef)}/template-message`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: input.template_id, params: input.params }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to send template'));
  }
  return response.json();
}

export interface ContactReplyInput {
  text: string;
  files?: File[];
}

export interface ContactReplyResult {
  sent_as: 'text' | 'template' | 'attachment';
  rendered_text: string;
  flattened: boolean;
  window: { open: boolean; expires_at: string | null };
  attachments?: { delivered: string[]; failed: { filename: string; error: string } | null } | null;
  /** Null = the send was not attached to one of the sender's open enquiries. */
  stamped_ticket_id: string | null;
}

export async function replyToContact(
  contactRef: string,
  input: ContactReplyInput,
): Promise<ContactReplyResult> {
  const files = input.files ?? [];
  const url = `${BASE}/${encodeURIComponent(contactRef)}/reply`;
  const response = await (files.length > 0
    ? apiFetch(url, { method: 'POST', body: buildReplyFormData(input, files) })
    : apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: input.text }),
      }));
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to send message'));
  }
  return response.json();
}

function buildReplyFormData(input: ContactReplyInput, files: File[]): FormData {
  const formData = new FormData();
  formData.append('text', input.text);
  for (const file of files) formData.append('files', file);
  return formData;
}
