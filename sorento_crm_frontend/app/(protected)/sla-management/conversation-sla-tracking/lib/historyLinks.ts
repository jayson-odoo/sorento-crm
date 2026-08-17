/**
 * Deep links into the SLA tracking listing, pre-filtered (UAC AC-M2).
 *
 * One place so the drawer's "View history", the worklist's "Recently resolved"
 * and the listing's own param reader cannot drift on a param name. The filters
 * are honoured SERVER-side by the same list query the page always used - these
 * are not client-side slices.
 *
 * Contact refs are the Respond.io contact id or the phone number, never the CRM
 * respond_contacts UUID: the backend resolves all three, and a UUID has no place
 * in a URL a user can see.
 */

export const CONVERSATION_SLA_TRACKING_PATH = '/sla-management/conversation-sla-tracking';

/** Every ticket ever raised by one contact, newest first. */
export function contactHistoryHref(contactRef: string | null | undefined): string {
  const ref = (contactRef ?? '').trim();
  if (!ref) return CONVERSATION_SLA_TRACKING_PATH;
  return `${CONVERSATION_SLA_TRACKING_PATH}?contact=${encodeURIComponent(ref)}`;
}

/**
 * What the viewer has resolved, most recently resolved first.
 *
 * `resolved_by=me` is expanded server-side to the caller. Resolve clears a
 * conversation ticket's assignee, so "mine" after the fact can only be answered
 * by `resolved_by` - an assignee filter would return an empty list.
 */
export function myResolvedHistoryHref(): string {
  return `${CONVERSATION_SLA_TRACKING_PATH}?is_resolved=true&resolved_by=me&sort=resolved_at&dir=desc`;
}
