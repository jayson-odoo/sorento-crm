/* -------------------------------------------------------------------------------------
 * Message push scope preference - PLAN-message-push, slice S0 (Phase 1, MOCKED).
 *
 * One decision, one column: which contacts' inbound WhatsApp messages buzz my phone.
 * The preference is SERVER-side and governs every device the user has enabled browser
 * notifications on - it is not the per-device push subscription (that is `pushService`).
 *
 * ===================================================================================
 * EXPECTED API CONTRACT (built in S1; this file is mock-backed until then)
 * ===================================================================================
 *
 * The scope rides on the EXISTING self-service account preference route rather than a
 * new endpoint (UAC AC-M25 permits "the existing account preference route"), so My
 * Account keeps one read and one write for its notification preferences.
 *
 *   GET /api/v1/notifications/preferences/channels
 *     200 -> {
 *       ...existing boolean channel toggles...,
 *       "notify_push_message_scope": "assigned_and_coverage"
 *                                  | "assigned_only"
 *                                  | "all_contacts"
 *                                  | "off"
 *     }
 *     401 -> not signed in
 *
 *   PATCH /api/v1/notifications/preferences/channels
 *     body -> { "notify_push_message_scope": <one of the four values above> }
 *     200  -> the same object GET returns (the full preference set, echoed back)
 *     422  -> { "detail": "..." } for any value outside the four (AC-M25)
 *     401  -> not signed in
 *
 * Storage (S1): `users.notify_push_message_scope VARCHAR(24) NOT NULL
 * DEFAULT 'assigned_and_coverage'`. The server default is the backfill (AC-M27), and
 * the column MUST be added to BOTH the `get_user` and `get_me` manual dict builders or
 * it never reaches the FE and the select renders its default forever (AC-M26).
 *
 * Not a preference table on purpose: there is exactly one event today. The second event
 * (mentions) is the trigger to migrate this column into
 * `notification_scope_preferences(user_id, event_key, scope)` - see the PLAN.
 *
 * S1 note: `NotificationChannelsPreference` already GETs this same route on the account
 * page (verified in the S0 evidence run), so once the field lands there the value is one
 * response away. Two components reading the route means two requests; fold them onto one
 * react-query key only if that second GET actually shows up as a problem.
 * ----------------------------------------------------------------------------------- */

import {
  mockFetchMessagePushScope,
  mockSaveMessagePushScope,
} from '@/services/__mocks__/messagePushScope';

export type MessagePushScope =
  | 'assigned_and_coverage'
  | 'assigned_only'
  | 'all_contacts'
  | 'off';

export const DEFAULT_MESSAGE_PUSH_SCOPE: MessagePushScope = 'assigned_and_coverage';

/** The four values, in the order AC-M1 lists them. Labels are what the user reads. */
export const MESSAGE_PUSH_SCOPE_OPTIONS: { value: MessagePushScope; label: string }[] = [
  { value: 'assigned_and_coverage', label: 'Contacts assigned to me and my coverage' },
  { value: 'assigned_only', label: 'Contacts assigned to me only' },
  { value: 'all_contacts', label: 'All contacts' },
  { value: 'off', label: 'Off' },
];

export function isMessagePushScope(value: unknown): value is MessagePushScope {
  return MESSAGE_PUSH_SCOPE_OPTIONS.some((o) => o.value === value);
}

/**
 * Current user's message push scope.
 *
 * S1 swaps the mock line for:
 *   const res = await apiFetch('/api/v1/notifications/preferences/channels');
 *   if (!res.ok) throw new Error(await extractApiError(res, 'Unable to load message notification setting'));
 *   const data = (await res.json()) as { notify_push_message_scope?: string };
 *   return isMessagePushScope(data.notify_push_message_scope)
 *     ? data.notify_push_message_scope
 *     : DEFAULT_MESSAGE_PUSH_SCOPE;
 */
export async function getMessagePushScope(): Promise<MessagePushScope> {
  return mockFetchMessagePushScope();
}

/**
 * Persist the scope. Rejects with the extracted API message so the caller can revert
 * the select and toast it (AC-M4).
 *
 * S1 swaps the mock line for:
 *   const res = await apiFetch('/api/v1/notifications/preferences/channels', {
 *     method: 'PATCH',
 *     headers: { 'Content-Type': 'application/json' },
 *     body: JSON.stringify({ notify_push_message_scope: scope }),
 *   });
 *   if (!res.ok) throw new Error(await extractApiError(res, 'Unable to update message notification setting'));
 *   ...same parse as the GET...
 */
export async function updateMessagePushScope(
  scope: MessagePushScope,
): Promise<MessagePushScope> {
  return mockSaveMessagePushScope(scope);
}
