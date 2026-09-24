/**
 * Who is assigned to a conversation SLA row, as a human name.
 *
 * Owner ruling S4 (23 Sep 2026, PLAN-keep-assignee-on-resolve-22sep): resolve
 * keeps `assigned_to_id` for audit now, so "Assigned to" names the assignee on
 * BOTH an open and a resolved row - there is no longer a role swap here. Who
 * resolved it is a separate fact with its own place: the detail header
 * subtitle reads `resolved_by_user_name` / `resolved_by` directly (see
 * `ConversationSLATrackingDetail.tsx`), not through this helper.
 *
 * No UUIDs reach the screen: the backend falls back to the raw `assigned_to`
 * column when no user matches the id, so an id-shaped value is treated as
 * "unknown" rather than printed.
 */

export interface SlaHandlerSource {
  assigned_user_name?: string | null;
  assigned_user?: { name?: string | null; email?: string | null } | null;
  assigned_to?: string | null;
}

export interface SlaHandler {
  /** Label for the name, kept as a field (not a hardcoded string in callers)
   * so a caller can build a title/aria-label without repeating it. */
  prefix: 'Assigned to';
  /** Human-readable name/email, or null when nobody can be named. */
  name: string | null;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The first candidate that is a name a person can read: non-blank, not a raw
 * UUID. The backend falls back to the raw `resolved_by` column when no user
 * row matches, so every surface that prints a handler has to filter, not just
 * the ones that call `slaHandler`. */
export function humanName(...candidates: (string | null | undefined)[]): string | null {
  return firstHumanValue(candidates);
}

function firstHumanValue(candidates: (string | null | undefined)[]): string | null {
  for (const candidate of candidates) {
    const value = (candidate ?? '').trim();
    if (!value) continue;
    if (UUID_RE.test(value)) continue;
    return value;
  }
  return null;
}

export function slaHandler(row: SlaHandlerSource): SlaHandler {
  return {
    prefix: 'Assigned to',
    name: firstHumanValue([
      row.assigned_user_name,
      row.assigned_user?.name,
      row.assigned_user?.email,
      row.assigned_to,
    ]),
  };
}
