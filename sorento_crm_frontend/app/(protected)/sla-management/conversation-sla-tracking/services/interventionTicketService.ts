/**
 * Conversation intervention tickets — feature service.
 *
 * Contract: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
 * Plan:     documentation/plans/sla/PLAN-conversation-intervention-tickets.md
 *
 * ============================================================================
 * PHASE 1 (this file today): every function below is served by the in-memory
 * fixtures in `./__mocks__/interventionTickets`. NO backend endpoint is called.
 * This is DEBT until Phase 2 swaps each body for the documented request. The
 * swap is one line per function; the types and the shapes below ARE the
 * contract the backend must satisfy.
 * ============================================================================
 *
 * ---------------------------------------------------------------------------
 * EXPECTED API CONTRACT (Phase 2 targets)
 * ---------------------------------------------------------------------------
 * All paths are under `/api/v1/sla-management/conversation-sla-tracking`.
 * Datetimes are naive UTC strings (backend convention) rendered through
 * `formatDateTimeInMalaysia` / `parseDateTimeAsUTC`.
 *
 * A. CREATE (n8n -> CRM, existing route, extended) — UAC AC-A1/A2/A4
 *    POST /integration
 *    Request (additive to today's `ConversationSLATrackingCreate`):
 *      {
 *        contact_phone_number: string,      // required, existing
 *        agent_code: string,                // required, existing
 *        team_set_code: string,             // required, existing
 *        assigned_to_id?: string,           // existing (round-robin / explicit)
 *        message_id?: string,               // existing (kept for back-compat)
 *        source_message_id: string,         // NEW: the triggering message id.
 *                                           //      Identity + idempotency key.
 *        source_message_text?: string       // NEW: enquiry snippet source text
 *      }
 *    Response 200 (additive; every field n8n reads today is preserved):
 *      {
 *        status: 'success',
 *        message: string,
 *        tracking_id: string,
 *        is_update: boolean,
 *        already_active: boolean,           // true on a same source_message_id retry
 *        in_working_hours: boolean,         // NEW (R4): n8n picks in-hours vs
 *                                           //      out-of-hours auto-reply copy
 *        initiated_at: string,              // real request time
 *        due_at: string | null,             // response deadline (clock start is
 *                                           //      normalized to the next working window)
 *        due_at_resolution: string | null,
 *        assigned_to: string | null,
 *        assigned_to_id: string | null
 *      }
 *    NOTE for the Phase 2 implementer: today's `/integration` route returns only
 *    `status/message/tracking_id/is_update/already_active`. The four clock/assignee
 *    fields AC-A2 requires plus `in_working_hours` are a delta to add there.
 *    Multi-open is the rule: a new `source_message_id` for a contact that already
 *    has an open ticket creates a SECOND open ticket (never merges).
 *
 * B. WORKLIST (existing `/my-pending`, extended) — UAC AC-B1
 *    GET /my-pending?limit=<n>   ->  { data: MyPendingSLAItem[] }
 *    Conversation-scope rows gain (see `InterventionTicketListItem`):
 *      is_intervention_ticket: true   // explicit from the backend, never re-derived
 *                                     //   here (same rule as `is_form_sla`)
 *      contact_name, contact_phone, enquiry_snippet, source_message_id,
 *      team_label, initiated_at, escalated_at
 *    Rows are NOT de-duplicated by contact: two open tickets for one contact are
 *    two rows, each with its own `due_at` / `due_at_resolution` / tier.
 *
 * C. TICKET DETAIL (drawer header + composer state) — UAC AC-C1
 *    GET /{tracking_id}/ticket   ->  InterventionTicketDetail
 *    Assignee-or-manager scoped. `window` + `chat_template` come from the same
 *    backend window/template service the shared composer uses, returned inline so
 *    the drawer opens in one round trip.
 *
 * D. THREAD (shared contact conversation) — UAC AC-C2
 *    GET /{tracking_id}/conversation?limit=&cursor=   (EXISTING route)
 *      -> { items: RespondMessageRenderable[], pagination?: {...}, error?: string }
 *    Siblings for the same contact return the SAME thread; only the header and
 *    clocks differ.
 *
 * E. SEND (ticket-stamped) — UAC AC-D1/D2/D3, AC-E1
 *    POST /{tracking_id}/ticket/send
 *      JSON body when there are no files:
 *        { text: string, reply_to_message_id?: string, reply_to_excerpt?: string }
 *      multipart/form-data when files are attached:
 *        text, reply_to_message_id?, reply_to_excerpt?, files[] (repeated)
 *    Response 200: SendTicketMessageResult
 *    Semantics the backend owns:
 *      - in-window  -> raw text; out-of-window -> the existing `*_chat` template
 *        smart-send (same `send_text_or_template` path as the unified composer)
 *      - attachments are uploaded through CRM storage and delivered to Respond by
 *        URL (CMYK JPEG converted to RGB)
 *      - the send is stamped with THIS tracking id: it sets
 *        is_responded / responded_at / responded_by / response_time on this ticket
 *        only; sibling tickets for the same contact are untouched
 *      - an `integration_log` outbox row is written on success AND failure
 *    R1 (resolved 2026-08-12): Respond.io supports text / attachment
 *    (image, video, audio, file) / quick_reply / whatsapp_template. There is NO
 *    sticker type and NO reply-to/context parameter, so:
 *      - the composer has no sticker affordance at all
 *      - "reply to" is emulated: the quoted excerpt is sent as a ">"-prefixed
 *        line above the body (`buildQuotedReplyText` in lib/respondIoChatRender),
 *        which WhatsApp renders as quoted text and our chat list re-parses via
 *        `splitQuotedPrefix`. `reply_to_message_id` is carried for the event log
 *        / audit trail only, never sent to Respond.
 *
 * F. RESOLVE — UAC AC-C3
 *    POST /{tracking_id}/resolve   (EXISTING route)
 *    For an intervention ticket it resolves THAT row only: sibling tickets stay
 *    open and NO Respond.io conversation-close call is made (Respond is a message
 *    pipe; conversation state is not ours to change).
 * ---------------------------------------------------------------------------
 */

import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';
import type { ChatTemplatePreview } from '@/services/whatsappTemplateService';
import type { MyPendingSLAItem } from './conversationSLATrackingService';
import {
  mockGetMyInterventionTickets,
  mockGetInterventionTicket,
  mockGetInterventionTicketThread,
  mockResolveInterventionTicket,
  mockSendInterventionTicketMessage,
  phase1TicketMocksEnabled,
} from './__mocks__/interventionTickets';

/** Send types the composer may offer. Bounded by R1: no sticker, no native reply-to. */
export type TicketSendCapability = 'text' | 'attachment';

/** Attachment subtypes Respond.io accepts on an outgoing message. */
export type TicketAttachmentKind = 'image' | 'video' | 'audio' | 'file';

/** 24h messaging-window state for the ticket's contact. */
export interface TicketWindowState {
  open: boolean;
  /** When the window closes (or closed). Null when unknown. */
  expires_at: string | null;
}

/**
 * A worklist row. Extends the existing `/my-pending` item so the dashboard widget
 * renders tickets and legacy rows through one code path.
 */
export interface InterventionTicketListItem extends MyPendingSLAItem {
  /** Always true on ticket rows. Absent on pre-migration conversation rows. */
  is_intervention_ticket: true;
  contact_name: string | null;
  contact_phone: string | null;
  /** First ~140 chars of the message that triggered the intervention. */
  enquiry_snippet: string | null;
  /** Respond.io message id of the trigger message (identity + thread highlight). */
  source_message_id: string | null;
  team_label: string | null;
  /** Real request time (may sit outside working hours; the clock start does not). */
  initiated_at: string;
  /** Set ONLY by a real escalation. Tier alone never means escalated. */
  escalated_at: string | null;
}

export interface InterventionTicketDetail {
  id: string;
  contact_name: string | null;
  contact_phone: string | null;
  respond_io_id: string | null;
  /** The triggering message, quoted in the drawer header. */
  source_message_id: string | null;
  source_message_text: string | null;
  source_message_at: string | null;
  team_label: string | null;
  assignee_name: string | null;
  policy_name: string | null;
  initiated_at: string;
  current_tier: number;
  escalated_at: string | null;
  escalation_reason: string | null;
  due_at: string | null;
  due_at_resolution: string | null;
  is_responded: boolean;
  responded_at: string | null;
  is_resolved: boolean;
  resolved_at: string | null;
  /** Viewer-relative gates, server-computed (assignee / RBAC). */
  can_send: boolean;
  can_resolve: boolean;
  /** What the composer may offer. Anything absent here is absent from the UI. */
  send_capabilities: TicketSendCapability[];
  window: TicketWindowState;
  /** Out-of-window fill-in template; null when the window is open or none configured. */
  chat_template: ChatTemplatePreview | null;
}

export interface InterventionTicketThread {
  items: RespondMessageRenderable[];
  /** Non-fatal loader message (e.g. Respond unreachable); items may still be empty. */
  error?: string | null;
}

export interface SendTicketMessageInput {
  text: string;
  attachments?: File[];
  /** Audit-only: Respond has no reply-to parameter (R1). */
  reply_to_message_id?: string | null;
  /** Excerpt quoted as a ">" prefix in the outgoing text. */
  reply_to_excerpt?: string | null;
}

export interface SendTicketMessageResult {
  sent_as: 'text' | 'template' | 'attachment';
  /** Exactly what the contact received. */
  rendered_text: string;
  /** True when the text was flattened to fit a template parameter. */
  flattened: boolean;
  window: TicketWindowState;
}

/**
 * PHASE 1 ONLY. True while the dashboard widget merges mock ticket rows into the
 * live pending list. Delete this, the merge and `./__mocks__/` in Phase 2 (S2.7).
 */
export const PHASE1_TICKET_MOCKS = phase1TicketMocksEnabled;

/** B. The viewer's open intervention tickets (one row per enquiry, never per contact). */
export async function getMyInterventionTickets(): Promise<InterventionTicketListItem[]> {
  return mockGetMyInterventionTickets();
}

/** C. Drawer header + composer state for one ticket. */
export async function getInterventionTicket(id: string): Promise<InterventionTicketDetail> {
  return mockGetInterventionTicket(id);
}

/** D. The shared contact thread this ticket was raised in. */
export async function getInterventionTicketThread(
  id: string,
): Promise<InterventionTicketThread> {
  return mockGetInterventionTicketThread(id);
}

/** E. Ticket-stamped send: stops THIS ticket's first-response clock only. */
export async function sendInterventionTicketMessage(
  id: string,
  input: SendTicketMessageInput,
): Promise<SendTicketMessageResult> {
  return mockSendInterventionTicketMessage(id, input);
}

/** F. Resolve THIS ticket. Siblings stay open; Respond conversation untouched. */
export async function resolveInterventionTicket(id: string): Promise<void> {
  return mockResolveInterventionTicket(id);
}
